"""MiniClosedAI — FastAPI app exposing a multi-backend local LLM playground.

Each saved conversation (bot) is pinned to a single backend via
`conversations.backend_id`. Backends can be Ollama or any OpenAI-compatible
server (LM Studio, vLLM, llama.cpp's `server`, etc.). All backend handling
lives in llm.py — this module is HTTP routing + persistence.
"""
import asyncio
import base64
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import pypdf

import db
import evals
import knowledge
import voice
import llm
import logs as chat_logs
import mcp_host
import sdkgen

# Embedding model used for the per-bot knowledge base. Defaults to a small,
# widely-available Ollama embedding model; override via env. Embeddings are
# requested through the bot's own backend, so this model must be served there.
EMBED_MODEL = os.environ.get("MINICLOSEDAI_EMBED_MODEL", "nomic-embed-text")
# Cap on how many retrieved chunks get injected into the prompt per turn.
KB_TOP_K = int(os.environ.get("MINICLOSEDAI_KB_TOP_K", "8"))
# Safety cap on MCP tool-call rounds per turn (model→tools→model→…). Prevents a
# runaway loop where the model keeps calling tools without ever answering.
MCP_MAX_TOOL_ITERS = int(os.environ.get("MINICLOSEDAI_MCP_MAX_ITERS", "6"))

# In-flight server-side generations, keyed by conversation_id. A generation runs
# in a background asyncio task decoupled from the client's SSE connection, so a
# reply keeps generating — and gets persisted — even if the user refreshes or
# closes the tab. The client streams from (and can re-attach to) the buffer.
# See _run_generation / _attach_generation_sse.
_generations: dict[int, dict] = {}
_GEN_EVICT_GRACE_S = 20  # keep a finished generation this long so a reloading client can read the tail


def _new_generation() -> dict:
    return {
        "status": "running",   # running | done | error
        "chunks": [],          # visible content chunks (strings)
        "thinking": [],        # reasoning chunks
        "truncated": False,
        "error": None,
        "task": None,          # the background asyncio.Task, so Stop can cancel it
        "cond": asyncio.Condition(),
    }

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="MiniClosedAI", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas ----------

class Message(BaseModel):
    """A single chat turn.

    `content` is either a plain string (legacy / text-only) or an OpenAI-style
    list of typed parts (multimodal):

        [{"type": "text", "text": "what's this?"},
         {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]

    The two extra display fields are persisted alongside the LLM-visible
    `content` so the UI can reconstruct the original look of a past turn:

      - `display_text`  — the user's typed text only, with no `[Attached: …]`
                          file-body prefixes. Used for rendering the chat
                          bubble so the user doesn't see a wall of extracted
                          PDF text in their own message.
      - `attachments`   — lightweight metadata for each file attached to this
                          turn (name, kind, page count, etc.). Used to render
                          document chips in the bubble.
    """
    model_config = ConfigDict(extra="allow")  # tolerate `params`, future fields

    role: str
    content: str | list[dict]
    display_text: str | None = None
    attachments: list[dict] | None = None


class AttachmentSpec(BaseModel):
    """Single attachment carried by a chat request.

    Frontend builds these per file before sending. For images, `data_url`
    holds the full `data:image/...;base64,...` URL. For text/PDF, `text`
    holds the extracted content.
    """
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=1, max_length=400)
    kind: Literal["image", "text", "pdf"]
    mime: str | None = None
    data_url: str | None = None
    text: str | None = None
    page_count: int | None = None
    char_count: int | None = None
    truncated: bool = False


ThinkValue = bool | str | None  # None = unset, True/False, or "low"/"medium"/"high"


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=32000)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    top_k: int = Field(40, ge=1, le=500)
    think: ThinkValue = None
    max_thinking_tokens: int | None = Field(None, ge=1, le=100000)
    conversation_id: int | None = None
    backend_id: int | None = None   # None → default to 1 (built-in Ollama)


class ConversationCreate(BaseModel):
    model: str
    system_prompt: str = "You are a helpful AI assistant."
    title: str = "New Chat"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=32000)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    top_k: int = Field(40, ge=1, le=500)
    think: ThinkValue = None
    max_thinking_tokens: int | None = Field(None, ge=1, le=100000)
    backend_id: int = 1   # default: built-in Ollama


class ConversationUpdate(BaseModel):
    title: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=32000)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    top_k: int | None = Field(None, ge=1, le=500)
    think: ThinkValue = None
    max_thinking_tokens: int | None = Field(None, ge=1, le=100000)
    backend_id: int | None = None
    # Voice settings (TTS voice id + language). Persisted into the
    # `voice_settings` JSON column. Pass {} to clear back to defaults.
    voice_settings: dict | None = None


class AvatarUpdate(BaseModel):
    avatar: str   # a `data:image/*;base64,...` URL (downscaled client-side)


class AppCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    link: str = ""


class AppUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    link: str | None = None


class AppBotAdd(BaseModel):
    conversation_id: int


class ConversationChatRequest(BaseModel):
    """Body for POST /api/conversations/{id}/chat.

    Bot config (model, system prompt, sampling params, backend) is locked to
    whatever the GUI saved. API callers only supply the conversation content.
    """
    model_config = ConfigDict(extra="forbid")

    message: str | None = None
    messages: list[Message] | None = None
    persist: bool = False
    # When true + `message` is provided, the server prepends the conversation's
    # saved turns to the LLM context. Needed for conversational bots (FAQ chat,
    # doctor's office, support agent) where the model must remember earlier
    # turns. Default false preserves the one-shot microservice pattern callers
    # rely on (classifiers, routers, extractors).
    include_history: bool = False
    # Optional file attachments to merge into the user's turn. Server combines
    # `message` (the user's typed text) + each attachment into a multimodal
    # content array — text/PDF bodies are prepended with a "[Attached: name]"
    # header, images become {type:"image_url"} parts. Only valid with the
    # single-`message` form; the `messages=[…]` form must include any
    # multimodal content arrays in-line itself.
    attachments: list[AttachmentSpec] | None = None
    # Hint that this turn is part of a live spoken conversation (📞 call mode).
    # The server appends a short addendum to the system prompt asking the model
    # to keep replies to 1-2 sentences so TTS starts speaking sooner and the
    # user doesn't sit through a wall of audio.
    voice_mode: bool = False


class BackendCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    # 'voice' is a dockerized ASR + TTS service registered via Settings → Add
    # endpoint, same flow as Ollama / OpenAI-compat. See voice.py + the new
    # voice-branch in /status, /test, /models.
    kind: Literal["ollama", "openai", "voice"]
    base_url: str = Field(..., min_length=1)
    api_key: str | None = None
    headers: dict[str, str] = {}
    enabled: bool = True


class BackendUpdate(BaseModel):
    """Everything except `kind` is updatable. `is_builtin` is server-controlled."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None


# ---------- Helpers ----------

_PARAM_KEYS = ("temperature", "max_tokens", "top_p", "top_k", "think", "max_thinking_tokens")


def _load_backend(backend_id: int | None) -> dict:
    """Load a backend row by id (defaults to 1 = built-in Ollama)."""
    bid = backend_id if backend_id is not None else 1
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backends WHERE id = ?", (bid,)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Backend {bid} not found")
    return db.row_to_dict(row)


# ---------- Relay auto-route override ----------
#
# When a chat's model is one served by an "authoritative" remote relay
# (currently any enabled backend with `app.interdataresearch` in its
# base_url), we override whichever backend the conversation is technically
# pinned to and send the request through the relay instead. Goal: the
# relay's request_logs become the source of truth for that model's usage,
# regardless of which group in the dashboard's model dropdown the user
# happened to click. Without this, two backends advertising the same model
# name silently divide the traffic — and any side-channel logging the
# relay does only sees its share.
#
# Cache the relay's model list briefly (60 s) so we're not probing
# `/api/tags` on every chat call. Cache invalidates on backend change
# (id mismatch).

_RELAY_HOST_FRAGMENTS = ("app.interdataresearch",)
_RELAY_MODEL_CACHE_TTL_S = 60.0
_relay_model_cache: dict = {"backend_id": None, "models": set(), "last_fetched": 0.0}
# Emergency stop. Set `MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE=1` to bypass the
# override entirely while debugging a degraded relay. With this set, chats
# follow the conversation's pinned `backend_id` strictly. Restart the server
# after toggling (the env var is read once per-call so re-export is enough
# — but uvicorn caches the process env at startup).


def _find_relay_backend() -> dict | None:
    """First enabled backend whose `base_url` contains a relay host fragment.
    Returns the full backend dict (including api_key for client auth) or None
    if no relay is registered or all relay candidates are disabled."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backends WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    for r in rows:
        d = db.row_to_dict(r)
        url = (d.get("base_url") or "").lower()
        if any(frag in url for frag in _RELAY_HOST_FRAGMENTS):
            return d
    return None


async def _maybe_override_to_relay(backend: dict, model_name: str) -> dict:
    """If a relay is registered, enabled, and serves `model_name`, return the
    relay backend dict instead of the caller-supplied one. Otherwise return
    `backend` unchanged.

    Probe failure (network error, 4xx, malformed response) returns the
    original backend — never silently breaks chat by routing to an
    unreachable relay.

    Env-var emergency stop: `MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE=1` short-
    circuits the entire override so chats follow the conv's pinned
    `backend_id` strictly. Useful while debugging a degraded relay.
    """
    if os.environ.get("MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE") == "1":
        return backend
    if not model_name:
        return backend
    relay = _find_relay_backend()
    if not relay:
        return backend
    # Don't override if we're already on the relay — would be a wasted check
    # in the hot path of every relay-bound conversation.
    if backend.get("id") == relay["id"]:
        return backend

    now = time.time()
    fresh = (
        _relay_model_cache["backend_id"] == relay["id"]
        and (now - _relay_model_cache["last_fetched"]) < _RELAY_MODEL_CACHE_TTL_S
    )
    if not fresh:
        try:
            models = await llm.list_models(relay)
            _relay_model_cache["models"] = {
                m.get("name") for m in (models or []) if m and m.get("name")
            }
        except Exception:
            # Relay unreachable — cache an empty set so we don't re-probe on
            # every chat call while the relay is down. With a 5 s probe
            # timeout, the un-cached failure path would add 5 s to every
            # request. Empty-set caching → at most one probe per TTL window.
            _relay_model_cache["models"] = set()
        # Always advance the cache window, even on failure. A relay that
        # comes back up gets re-detected after the next TTL boundary.
        _relay_model_cache["last_fetched"] = now
        _relay_model_cache["backend_id"] = relay["id"]

    if model_name in _relay_model_cache["models"]:
        return relay
    return backend


def _scrub_backend(b: dict) -> dict:
    """Public-safe view of a backend row (hide api_key, show only api_key_set)."""
    out = {k: v for k, v in b.items() if k != "api_key"}
    out["api_key_set"] = bool(b.get("api_key"))
    return out


def _normalize_base_url(url: str) -> str:
    return (url or "").rstrip("/")


def _backend_err(backend: dict) -> str:
    return f"Cannot reach '{backend.get('name','backend')}' at {backend.get('base_url','?')}"


# ---------- Backends CRUD ----------

@app.get("/api/backends")
def api_list_backends():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backends ORDER BY id"
        ).fetchall()
    return [_scrub_backend(db.row_to_dict(r)) for r in rows]


@app.post("/api/backends")
def api_create_backend(data: BackendCreate):
    base_url = _normalize_base_url(data.base_url)
    with db.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO backends (name, kind, base_url, api_key, headers, enabled, is_builtin)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (
                data.name,
                data.kind,
                base_url,
                data.api_key,
                json.dumps(data.headers or {}),
                1 if data.enabled else 0,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM backends WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _scrub_backend(db.row_to_dict(row))


@app.patch("/api/backends/{backend_id}")
def api_update_backend(backend_id: int, data: BackendUpdate):
    supplied = data.model_dump(exclude_none=True)
    if not supplied:
        # Load + return current state so clients can refresh.
        return _scrub_backend(_load_backend(backend_id))

    fields: list[str] = []
    values: list = []
    if "name" in supplied:
        fields.append("name = ?")
        values.append(supplied["name"])
    if "base_url" in supplied:
        fields.append("base_url = ?")
        values.append(_normalize_base_url(supplied["base_url"]))
    if "api_key" in supplied:
        fields.append("api_key = ?")
        values.append(supplied["api_key"])
    if "headers" in supplied:
        fields.append("headers = ?")
        values.append(json.dumps(supplied["headers"] or {}))
    if "enabled" in supplied:
        fields.append("enabled = ?")
        values.append(1 if supplied["enabled"] else 0)

    values.append(backend_id)
    with db.get_conn() as conn:
        cur = conn.execute(
            f"UPDATE backends SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, f"Backend {backend_id} not found")
        row = conn.execute("SELECT * FROM backends WHERE id = ?", (backend_id,)).fetchone()
    return _scrub_backend(db.row_to_dict(row))


@app.delete("/api/backends/{backend_id}")
def api_delete_backend(backend_id: int, force: bool = False):
    """Delete a backend.

    Three guard clauses, all overridable with `?force=true`:

    - **Built-in backend**: 403 without `force` (the GUI's two-step confirm
      sets `force=true` after warning the user). The seed logic in `db.py`
      only re-creates the built-in on a *fully empty* backends table, so
      once you delete it AND keep at least one other backend, it stays
      gone across restarts.

    - **Bound conversations**: 409 with the bound list. With `force`, those
      conversations are deleted in the same transaction.

    - **Both at once** (built-in with bound bots): with `force`, deletes
      the bots and the backend together.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, is_builtin FROM backends WHERE id = ?", (backend_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Backend {backend_id} not found")
        if row["is_builtin"] and not force:
            raise HTTPException(
                403,
                {
                    "message": "The built-in backend can't be deleted by default. "
                               "Retry with `?force=true` to confirm — the GUI's "
                               "Delete button does this automatically after a "
                               "two-step confirm.",
                    "is_builtin": True,
                },
            )

        bound = conn.execute(
            "SELECT id, title FROM conversations WHERE backend_id = ?", (backend_id,)
        ).fetchall()
        if bound and not force:
            raise HTTPException(
                409,
                {
                    "message": f"Backend {backend_id} is still bound to "
                               f"{len(bound)} conversation(s). Rebind them first, "
                               f"or retry with `?force=true` to cascade-delete the bots.",
                    "bound_conversations": [
                        {"id": r["id"], "title": r["title"]} for r in bound
                    ],
                },
            )

        if force and bound:
            conn.execute(
                "DELETE FROM conversations WHERE backend_id = ?", (backend_id,)
            )
        conn.execute("DELETE FROM backends WHERE id = ?", (backend_id,))
        conn.commit()
    return {
        "ok": True,
        "deleted_conversations": len(bound) if force else 0,
    }


class BackendTestRequest(BackendCreate):
    """Draft-probe body. Adds an optional `use_saved_key_from` so the Edit-mode
    Test button can fall back to the saved key without the frontend having to
    echo secrets into the DOM.
    """
    # Allow the frontend to omit api_key (blank field in Edit mode) and signal
    # "substitute the saved key from backend id N" for the probe only.
    use_saved_key_from: int | None = None


@app.post("/api/backends/test")
async def api_backend_test(data: BackendTestRequest):
    """Probe a draft (unsaved) backend config. Used by the Settings modal's
    Test-connection button, so the browser doesn't have to make a cross-origin
    call that CORS would block.

    When editing an existing backend, the frontend clears the api_key field so
    the saved secret isn't echoed into the DOM. If it's blank at test-time and
    `use_saved_key_from` is set, we fetch the saved key server-side and use it
    for the probe only (never returned to the client).
    """
    api_key = data.api_key
    if not api_key and data.use_saved_key_from is not None:
        try:
            existing = _load_backend(data.use_saved_key_from)
            api_key = existing.get("api_key")
        except HTTPException:
            # Referenced a non-existent backend — fall through with api_key=None.
            pass

    probe = {
        "id": 0,
        "name": data.name or "draft",
        "kind": data.kind,
        "base_url": _normalize_base_url(data.base_url),
        "api_key": api_key,
        "headers": data.headers or {},
    }
    try:
        running = await llm.is_running(probe)
    except Exception as e:
        return {"running": False, "message": f"{type(e).__name__}: {e}"}
    if not running:
        return {
            "running": False,
            "message": f"No response at {probe['base_url']}.",
        }
    try:
        models = await llm.list_models(probe)
    except Exception as e:
        unit = "voices catalog" if probe["kind"] == "voice" else "/models"
        return {"running": True, "models_count": 0, "message": f"Reachable but {unit} failed: {e}"}
    count = len(models)
    # Voice backends serve voices, not LLM models — the reshape into the
    # Ollama-style list is internal plumbing; the human-facing label should
    # match the user's mental model.
    unit = "voice" if probe["kind"] == "voice" else "model"
    if count == 0:
        if probe["kind"] == "voice":
            empty = "Reachable, but the voices catalog is empty. (Add voices to tts.py's VOICE_CATALOG.)"
        else:
            empty = ("Reachable, but 0 models available. "
                     "(If this is LM Studio, is a model loaded? Also confirm the URL ends with '/v1'.)")
        return {"running": True, "models_count": 0, "message": empty}
    return {"running": True, "models_count": count, "message": f"Reachable · {count} {unit}(s)"}


@app.get("/api/backends/{backend_id}/models")
async def api_backend_models(backend_id: int):
    backend = _load_backend(backend_id)
    if not backend.get("enabled"):
        return {"running": False, "models": [], "disabled": True}
    running = await llm.is_running(backend)
    models = await llm.list_models(backend) if running else []
    return {"running": running, "models": models}


@app.get("/api/backends/{backend_id}/status")
async def api_backend_status(backend_id: int):
    backend = _load_backend(backend_id)
    running = await llm.is_running(backend) if backend.get("enabled") else False
    return {
        "running": running,
        "base_url": backend["base_url"],
        "kind": backend["kind"],
        "enabled": bool(backend.get("enabled")),
    }


# ---------- Model pulls (Ollama only) ----------
#
# In-memory registry of pull jobs. Lost on restart; the underlying download
# continues on the Ollama side either way, so the only thing lost is the
# progress UI for whatever was in flight at restart time. Acceptable for v1.

class PullRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


def _pull_key(backend_id: int, name: str) -> str:
    return f"{backend_id}:{name}"


_pulls: dict[str, dict] = {}
_pull_tasks: dict[str, asyncio.Task] = {}


def _public_pull(state: dict) -> dict:
    return {k: v for k, v in state.items() if k != "_lock"}


async def _run_pull(key: str, backend: dict, name: str) -> None:
    state = _pulls[key]
    try:
        async for ev in llm.pull_ollama_model(backend, name):
            status = ev.get("status")
            if status:
                state["status"] = status
            if "total" in ev:
                state["total"] = ev["total"]
            if "completed" in ev:
                state["completed"] = ev["completed"]
            if status == "success":
                state["done"] = True
                state["completed"] = state.get("total") or state.get("completed") or 0
        state["done"] = True
        if not state.get("status"):
            state["status"] = "success"
    except asyncio.CancelledError:
        state["error"] = "cancelled"
        state["status"] = "cancelled"
        state["done"] = True
        raise
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
        state["done"] = True
    finally:
        _pull_tasks.pop(key, None)


@app.post("/api/backends/{backend_id}/pull")
async def api_start_pull(backend_id: int, data: PullRequest):
    backend = _load_backend(backend_id)
    if backend.get("kind") != "ollama":
        raise HTTPException(400, "Pull is only supported on Ollama backends")
    if not backend.get("enabled"):
        raise HTTPException(400, "Backend is disabled")

    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Model name is required")

    key = _pull_key(backend_id, name)
    existing = _pulls.get(key)
    if existing and not existing.get("done"):
        raise HTTPException(409, f"A pull for '{name}' is already running")

    state = {
        "key": key,
        "backend_id": backend_id,
        "backend_name": backend.get("name"),
        "name": name,
        "status": "starting",
        "completed": 0,
        "total": 0,
        "error": None,
        "done": False,
        "started_at": time.time(),
    }
    _pulls[key] = state
    task = asyncio.create_task(_run_pull(key, backend, name))
    _pull_tasks[key] = task
    return _public_pull(state)


@app.get("/api/pulls")
def api_list_pulls():
    items = sorted(
        (_public_pull(s) for s in _pulls.values()),
        key=lambda s: s.get("started_at") or 0,
        reverse=True,
    )
    return {"pulls": items}


# ---------- LLM request/response logs ----------
# In-memory ring buffer of chat calls — the GUI's Logs page polls this every
# few seconds to display recent activity (request metadata + response preview),
# LM-Studio-style. Buffer is reset on server restart by design.

@app.get("/api/logs")
def api_list_logs(limit: int | None = None, since_id: int | None = None):
    """Return chat log entries, newest first.

    Query params:
      - `limit`: cap the number of entries returned (default: all in buffer).
      - `since_id`: only entries with `id > since_id` — supports cheap incremental
        polling, the GUI sends the max id it's already seen on each tick.
    """
    items = chat_logs.get_all()
    if since_id is not None:
        items = [e for e in items if e.get("id", 0) > since_id]
    if limit is not None and limit > 0:
        items = items[:limit]
    return {"logs": items}


@app.delete("/api/logs")
def api_clear_logs():
    chat_logs.clear()
    return {"ok": True}


@app.get("/api/logs/export")
def api_export_logs():
    """Paired request/response CSV — two columns, the entire LLM input as text
    and the entire LLM output as text. Messages are JSON-stringified so the
    full system prompt + history + user turn is preserved in one cell. Used by
    the Logs page Export button. QUOTE_ALL keeps Excel/Sheets happy when the
    content contains commas, newlines, or quotes."""
    import csv
    import io as _io
    items = chat_logs.get_all_full()
    buf = _io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["request", "response"])
    for e in items:
        request_text = json.dumps(
            e.get("request_messages") or [], ensure_ascii=False
        )
        response_text = e.get("response_text") or ""
        w.writerow([request_text, response_text])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="miniclosedai-logs-'
                f'{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.csv"'
            )
        },
    )


@app.delete("/api/backends/{backend_id}/pulls/{name:path}")
async def api_cancel_pull(backend_id: int, name: str):
    key = _pull_key(backend_id, name)
    state = _pulls.get(key)
    if not state:
        raise HTTPException(404, "No such pull")
    task = _pull_tasks.get(key)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _pulls.pop(key, None)
    return {"ok": True}


# ---------- File attachments (PDF text extraction) ----------
#
# Images and plain-text files are handled entirely in the browser — no need
# for a server round-trip. PDFs are the one attachment type that requires
# Python-side processing because no local LLM runtime accepts a raw PDF
# document and pdf.js would balloon the frontend bundle by ~3 MB. We extract
# text with pypdf, cap the work at 50 pages and 30 000 chars, and return
# plain text the frontend can prepend to the user message just like any
# other attached document.
#
# This endpoint is the only file-upload path; everything else (.txt, .md,
# .csv, .json, source code, images) is read in JS via FileReader.

# Caps for the CHAT-ATTACHMENT path (a PDF stuffed into one chat turn): modest,
# so a giant doc can't blow the model's context.
PDF_MAX_BYTES = int(os.environ.get("MINICLOSEDAI_PDF_MAX_MB", "10")) * 1024 * 1024
PDF_MAX_PAGES = int(os.environ.get("MINICLOSEDAI_PDF_MAX_PAGES", "50"))
PDF_MAX_CHARS = int(os.environ.get("MINICLOSEDAI_PDF_MAX_CHARS", "30000"))
# Book-friendly caps for the KNOWLEDGE-BASE path (?full=1): the full text is
# chunked + embedded, so length is not a context concern — let whole books in.
PDF_FULL_MAX_BYTES = int(os.environ.get("MINICLOSEDAI_PDF_FULL_MAX_MB", "200")) * 1024 * 1024
PDF_FULL_MAX_PAGES = int(os.environ.get("MINICLOSEDAI_PDF_FULL_MAX_PAGES", "5000"))
PDF_FULL_MAX_CHARS = int(os.environ.get("MINICLOSEDAI_PDF_FULL_MAX_CHARS", "5000000"))


@app.post("/api/extract-pdf")
async def api_extract_pdf(file: UploadFile = File(...), full: bool = False):
    """Extract plain text from an uploaded PDF.

    `full=true` uses the book-friendly caps (knowledge-base ingestion — whole
    books); the default modest caps are for the chat-attachment path. Returns
    ``{filename, page_count, char_count, truncated, text}``. ``truncated`` is
    true if a page/char cap was hit. Image-only / scanned PDFs come back with
    short or empty ``text`` — a pypdf limitation, not a bug here.
    """
    max_bytes = PDF_FULL_MAX_BYTES if full else PDF_MAX_BYTES
    max_pages = PDF_FULL_MAX_PAGES if full else PDF_MAX_PAGES
    max_chars = PDF_FULL_MAX_CHARS if full else PDF_MAX_CHARS

    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large ({len(raw) / 1024 / 1024:.1f} MB > {max_bytes // 1024 // 1024} MB cap)",
        )
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")

    total_pages = len(reader.pages)
    pages_scanned = min(total_pages, max_pages)
    chunks: list[str] = []
    chars = 0
    truncated = total_pages > max_pages
    for i in range(pages_scanned):
        try:
            page_text = reader.pages[i].extract_text() or ""
        except Exception:
            page_text = ""
        # Header lets the model see page boundaries when scanning multi-page docs.
        chunks.append(f"--- Page {i + 1} ---\n{page_text.strip()}")
        chars += len(page_text)
        if chars >= max_chars:
            truncated = True
            break

    text = "\n\n".join(chunks)
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return {
        "filename": file.filename,
        "page_count": total_pages,
        "char_count": len(text),
        "truncated": truncated,
        "text": text,
    }


# ---------- Models (aggregated across all backends) ----------

@app.get("/api/models")
async def api_models():
    """Aggregated view for the Dashboard model dropdown.

    Returns one entry per LLM backend with its model list. Disabled backends
    are included with `running=False` + empty models so the UI can still
    show them greyed out. Preserves `ollama_running` for older front-end
    code until the frontend is updated.

    Voice backends (kind='voice') are excluded — they advertise a TTS voice
    catalog, not LLM models, and were leaking into the chat-topbar model
    picker. Voice selection has its own surface (`backendCache` on the
    client filters by `kind='voice'` for the voice features that need it);
    this endpoint is explicitly for the LLM picker.
    """
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backends WHERE kind != 'voice' ORDER BY id"
        ).fetchall()
    backends = [db.row_to_dict(r) for r in rows]

    result = []
    any_ollama_running = False
    flat_ollama_models: list[dict] = []

    for b in backends:
        enabled = bool(b.get("enabled"))
        running = await llm.is_running(b) if enabled else False
        models = await llm.list_models(b) if (enabled and running) else []
        if b["kind"] == "ollama" and running:
            any_ollama_running = True
            flat_ollama_models = models
        result.append({
            "id": b["id"],
            "name": b["name"],
            "kind": b["kind"],
            "base_url": b["base_url"],
            "enabled": enabled,
            "is_builtin": bool(b.get("is_builtin")),
            "running": running,
            "models": models,
        })

    return {
        # Aggregated shape — new frontend consumes this.
        "backends": result,
        # Back-compat: any still-alive Ollama client reads these two:
        "ollama_running": any_ollama_running,
        "models": flat_ollama_models,
    }


# ---------- Conversations ----------

@app.get("/api/conversations")
def api_list_conversations():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, model, backend_id, avatar, app_id, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/conversations")
def api_create_conversation(data: ConversationCreate):
    # Validate the backend exists before inserting.
    _load_backend(data.backend_id)

    params = {k: getattr(data, k) for k in _PARAM_KEYS}
    with db.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO conversations (title, model, system_prompt, params, backend_id)
               VALUES (?, ?, ?, ?, ?)""",
            (data.title, data.model, data.system_prompt, json.dumps(params), data.backend_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return db.row_to_dict(row)


@app.get("/api/conversations/{conv_id}")
def api_get_conversation(conv_id: int):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")
    d = db.row_to_dict(row)
    # True when a reply is being generated server-side (survives client refresh).
    # The client uses this to resume the waiting/streaming state on reload.
    g = _generations.get(conv_id)
    d["generating"] = bool(g and g["status"] == "running")
    return d


@app.patch("/api/conversations/{conv_id}")
def api_update_conversation(conv_id: int, data: ConversationUpdate):
    # exclude_unset=True (not exclude_none) so the client can distinguish
    # "didn't supply this field" from "explicitly set it to null". For param
    # keys, null means "clear the saved value" — e.g. blanking out
    # max_thinking_tokens or flipping Thinking back to Default.
    supplied = data.model_dump(exclude_unset=True)

    # Validate a backend_id change points to a real backend (reject null; the
    # column is NOT NULL with a logical FK).
    if "backend_id" in supplied:
        if supplied["backend_id"] is None:
            raise HTTPException(400, "backend_id cannot be null")
        _load_backend(supplied["backend_id"])

    fields, values = [], []
    # Plain columns on the conversations table — all NOT NULL, so a null value
    # here means "ignore" (client shouldn't have sent it, but be lenient).
    for col in ("title", "model", "system_prompt", "backend_id"):
        if col in supplied and supplied[col] is not None:
            fields.append(f"{col} = ?")
            values.append(supplied[col])

    # Voice settings (JSON column). Whole-object replace — caller sends the
    # full desired voice_settings dict. Passing {} clears the column back to
    # defaults (resolver falls back to first English voice on the backend).
    if "voice_settings" in supplied:
        vs = supplied["voice_settings"]
        if vs is None:
            vs = {}
        if not isinstance(vs, dict):
            raise HTTPException(400, "voice_settings must be an object")
        fields.append("voice_settings = ?")
        values.append(json.dumps(vs))

    # Sampling params go into the JSON `params` column. null = clear the key.
    with db.get_conn() as conn:
        param_updates = {k: supplied[k] for k in _PARAM_KEYS if k in supplied}
        if param_updates:
            row = conn.execute(
                "SELECT params FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Conversation not found")
            merged = json.loads(row["params"] or "{}")
            for k, v in param_updates.items():
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            fields.append("params = ?")
            values.append(json.dumps(merged))
        if not fields:
            return {"ok": True}
        values.append(conv_id)
        cur = conn.execute(
            f"UPDATE conversations SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
    return {"ok": True}


# ~1MB cap on the stored data URL. The client downscales avatars to a small
# square before upload, so a real avatar is a few KB; this just guards against
# someone POSTing a full-res image straight to the API.
AVATAR_MAX_CHARS = 1_500_000


@app.put("/api/conversations/{conv_id}/avatar")
def api_set_avatar(conv_id: int, data: AvatarUpdate):
    """Set the bot's circle avatar (a base64 image data URL). Doesn't bump
    updated_at — changing an avatar isn't conversation activity."""
    url = (data.avatar or "").strip()
    if not url.startswith("data:image/"):
        raise HTTPException(400, "avatar must be a data:image/* URL")
    if len(url) > AVATAR_MAX_CHARS:
        raise HTTPException(413, "avatar image too large")
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE conversations SET avatar = ? WHERE id = ?", (url, conv_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
    return {"ok": True}


@app.delete("/api/conversations/{conv_id}/avatar")
def api_clear_avatar(conv_id: int):
    """Remove the bot's avatar, falling back to the initial-letter circle."""
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE conversations SET avatar = NULL WHERE id = ?", (conv_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
    return {"ok": True}


@app.delete("/api/conversations/{conv_id}")
def api_delete_conversation(conv_id: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        # Logical-FK cleanup: drop this bot's knowledge base + eval cases too.
        conn.execute("DELETE FROM kb_chunks WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM kb_documents WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM eval_cases WHERE conversation_id = ?", (conv_id,))
        conn.commit()
    return {"ok": True}


@app.post("/api/conversations/{conv_id}/clear")
def api_clear_conversation(conv_id: int):
    """Wipe messages for this conversation, keep its config."""
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE conversations SET messages = '[]', updated_at = datetime('now') WHERE id = ?",
            (conv_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
    return {"ok": True}


# ---------- Applications (groups of bots) ----------

def _app_row(conn, app_id: int):
    row = conn.execute("SELECT * FROM apps WHERE id = ?", (app_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Application not found")
    return row


@app.get("/api/apps")
def api_list_apps():
    """Every application with its bot count, newest-first."""
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT a.id, a.name, a.description, a.link, a.avatar,
                      a.created_at, a.updated_at, COUNT(c.id) AS bot_count
               FROM apps a
               LEFT JOIN conversations c ON c.app_id = a.id
               GROUP BY a.id
               ORDER BY a.updated_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/apps", status_code=201)
def api_create_app(data: AppCreate):
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO apps (name, description, link) VALUES (?, ?, ?)",
            (data.name.strip(), data.description or "", data.link or ""),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM apps WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/apps/{app_id}")
def api_get_app(app_id: int):
    """An application plus the bots in it."""
    with db.get_conn() as conn:
        row = _app_row(conn, app_id)
        bots = conn.execute(
            """SELECT id, title, model, backend_id, avatar, updated_at
               FROM conversations WHERE app_id = ? ORDER BY updated_at DESC""",
            (app_id,),
        ).fetchall()
    out = dict(row)
    out["bots"] = [dict(b) for b in bots]
    return out


@app.patch("/api/apps/{app_id}")
def api_update_app(app_id: int, data: AppUpdate):
    supplied = data.model_dump(exclude_unset=True)
    fields, values = [], []
    for col in ("name", "description", "link"):
        if col in supplied and supplied[col] is not None:
            val = supplied[col]
            if col == "name":
                val = val.strip()
                if not val:
                    raise HTTPException(400, "name cannot be empty")
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return {"ok": True}
    values.append(app_id)
    with db.get_conn() as conn:
        cur = conn.execute(
            f"UPDATE apps SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Application not found")
    return {"ok": True}


@app.delete("/api/apps/{app_id}")
def api_delete_app(app_id: int):
    """Delete an application. Its bots are UNLINKED (app_id → NULL), never deleted."""
    with db.get_conn() as conn:
        conn.execute("UPDATE conversations SET app_id = NULL WHERE app_id = ?", (app_id,))
        cur = conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Application not found")
    return {"ok": True}


@app.put("/api/apps/{app_id}/avatar")
def api_set_app_avatar(app_id: int, data: AvatarUpdate):
    """Set the application's logo (a base64 image data URL)."""
    url = (data.avatar or "").strip()
    if not url.startswith("data:image/"):
        raise HTTPException(400, "avatar must be a data:image/* URL")
    if len(url) > AVATAR_MAX_CHARS:
        raise HTTPException(413, "avatar image too large")
    with db.get_conn() as conn:
        cur = conn.execute("UPDATE apps SET avatar = ? WHERE id = ?", (url, app_id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Application not found")
    return {"ok": True}


@app.delete("/api/apps/{app_id}/avatar")
def api_clear_app_avatar(app_id: int):
    with db.get_conn() as conn:
        cur = conn.execute("UPDATE apps SET avatar = NULL WHERE id = ?", (app_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Application not found")
    return {"ok": True}


@app.post("/api/apps/{app_id}/bots", status_code=201)
def api_add_bot_to_app(app_id: int, data: AppBotAdd):
    """Move a bot into this application. One app per bot, so this reassigns it
    from any previous application."""
    with db.get_conn() as conn:
        _app_row(conn, app_id)
        cur = conn.execute(
            "UPDATE conversations SET app_id = ? WHERE id = ?",
            (app_id, data.conversation_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
    return {"ok": True}


@app.delete("/api/apps/{app_id}/bots/{conv_id}")
def api_remove_bot_from_app(app_id: int, conv_id: int):
    """Remove a bot from this application (back to the ungrouped Bots list)."""
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE conversations SET app_id = NULL WHERE id = ? AND app_id = ?",
            (conv_id, app_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Bot not in this application")
    return {"ok": True}


def _sdk_base_url(request: Request, override: str | None) -> str:
    """Base URL baked into a generated SDK: an explicit override, else the
    origin this request came in on (so the SDK points back at this server)."""
    if override:
        return override.rstrip("/")
    return str(request.base_url).rstrip("/")


def _app_sdk_files(app_id: int, base_url: str, lang: str = "ts"):
    if lang not in sdkgen.SDK_LANGS:
        raise HTTPException(
            400, f"unknown SDK language: {lang!r}. Valid: {', '.join(sdkgen.SDK_LANGS)}.")
    with db.get_conn() as conn:
        row = _app_row(conn, app_id)
        bots = conn.execute(
            "SELECT id, title, model FROM conversations WHERE app_id = ? ORDER BY id",
            (app_id,),
        ).fetchall()
    app_dict = dict(row)
    return app_dict, sdkgen.generate_sdk(lang, app_dict, [dict(b) for b in bots], base_url)


@app.get("/api/apps/{app_id}/sdk")
def api_app_sdk(app_id: int, request: Request, base_url: str | None = None, lang: str = "ts"):
    """Generated SDK files for this application (for preview).

    `lang` selects the language: `ts` (default, TypeScript), `js` (JavaScript),
    or `py` (Python). Defaults to `ts` so older clients keep working unchanged.
    """
    app_dict, files = _app_sdk_files(app_id, _sdk_base_url(request, base_url), lang)
    return {"app": {"id": app_dict["id"], "name": app_dict["name"]}, "lang": lang, "files": files}


@app.get("/api/apps/{app_id}/sdk.zip")
def api_app_sdk_zip(app_id: int, request: Request, base_url: str | None = None, lang: str = "ts"):
    """Download the generated SDK for this application as a .zip. See /sdk for `lang`."""
    app_dict, files = _app_sdk_files(app_id, _sdk_base_url(request, base_url), lang)
    slug = sdkgen.slugify(app_dict["name"])
    # Encode language in the filename so users can keep all three side-by-side
    # in a downloads folder without overwriting each other.
    filename = f"{slug}-sdk.zip" if lang == "ts" else f"{slug}-{lang}-sdk.zip"
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f["path"], f["content"])
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Per-bot knowledge base (RAG) ----------

class KnowledgeDocCreate(BaseModel):
    """Body for POST /api/conversations/{id}/knowledge.

    The frontend extracts text client-side (txt/md read directly, PDFs via the
    existing /api/extract-pdf endpoint) and posts the plain text here. Keeping
    this endpoint JSON-only (no multipart) keeps it simple.
    """
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(..., min_length=1, max_length=300)
    text: str = Field(..., min_length=1)


def _conv_exists(conv_id: int) -> dict:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")
    return db.row_to_dict(row)


def _resolve_embed_backend() -> dict:
    """Pick a backend to compute embeddings on.

    Embeddings are a LOCAL concern: `nomic-embed-text` lives on a local Ollama,
    not on a cloud chat relay. A bot can be pinned to a remote/relay backend for
    *chat* (e.g. Interdata) that doesn't serve the embedding model — so we do NOT
    use the bot's chat backend here. Resolution order:
      1. MINICLOSEDAI_EMBED_BACKEND_ID env override.
      2. The built-in local Ollama (is_builtin=1), if enabled.
      3. Any other enabled Ollama backend (lowest id first).
    Raises 503 if no Ollama-kind backend is available at all.
    """
    override = os.environ.get("MINICLOSEDAI_EMBED_BACKEND_ID")
    with db.get_conn() as conn:
        if override and override.strip().isdigit():
            row = conn.execute("SELECT * FROM backends WHERE id = ?", (int(override),)).fetchone()
            if row:
                return db.row_to_dict(row)
        row = conn.execute(
            "SELECT * FROM backends WHERE kind = 'ollama' AND enabled = 1 "
            "ORDER BY is_builtin DESC, id ASC LIMIT 1"
        ).fetchone()
    if not row:
        raise HTTPException(
            503,
            f"No local Ollama backend is available to compute embeddings. The "
            f"knowledge base needs an enabled Ollama endpoint with '{EMBED_MODEL}' "
            f"pulled (`ollama pull {EMBED_MODEL}`). Your bot's chat backend can "
            f"still be a cloud/relay endpoint — embeddings just run locally.",
        )
    return db.row_to_dict(row)


@app.post("/api/conversations/{conv_id}/knowledge")
async def api_add_knowledge(conv_id: int, doc: KnowledgeDocCreate):
    """Chunk + embed a document and store it in this bot's knowledge base."""
    _conv_exists(conv_id)
    backend = _resolve_embed_backend()

    chunks = knowledge.chunk_text(doc.text)
    if not chunks:
        raise HTTPException(400, "Document has no extractable text.")

    try:
        vecs = await llm.embed(backend, EMBED_MODEL, chunks)
    except (httpx.ConnectError, RuntimeError, ValueError) as e:
        raise HTTPException(
            502,
            f"Embedding failed with model '{EMBED_MODEL}' on backend "
            f"'{backend.get('name', '?')}': {e}. Pull it there with "
            f"`ollama pull {EMBED_MODEL}`, or set MINICLOSEDAI_EMBED_BACKEND_ID "
            f"to an Ollama endpoint that serves it.",
        )
    if len(vecs) != len(chunks):
        raise HTTPException(502, "Embedding backend returned the wrong number of vectors.")

    with db.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO kb_documents
               (conversation_id, filename, char_count, chunk_count, embed_model)
               VALUES (?, ?, ?, ?, ?)""",
            (conv_id, doc.filename, len(doc.text), len(chunks), EMBED_MODEL),
        )
        doc_id = cur.lastrowid
        for i, (text, vec) in enumerate(zip(chunks, vecs)):
            packed = knowledge.pack_vector(knowledge.normalize(vec))
            conn.execute(
                """INSERT INTO kb_chunks
                   (document_id, conversation_id, ordinal, text, embedding)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, conv_id, i, text, packed),
            )
        conn.commit()

    return {
        "id": doc_id,
        "filename": doc.filename,
        "char_count": len(doc.text),
        "chunk_count": len(chunks),
        "embed_model": EMBED_MODEL,
    }


@app.get("/api/conversations/{conv_id}/knowledge")
def api_list_knowledge(conv_id: int):
    """List the documents in this bot's knowledge base (no chunk text)."""
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT id, filename, char_count, chunk_count, embed_model, created_at
               FROM kb_documents WHERE conversation_id = ?
               ORDER BY created_at DESC, id DESC""",
            (conv_id,),
        ).fetchall()
    return {"documents": [dict(r) for r in rows]}


@app.delete("/api/conversations/{conv_id}/knowledge/{doc_id}")
def api_delete_knowledge(conv_id: int, doc_id: int):
    """Remove one document + its chunks from this bot's knowledge base."""
    with db.get_conn() as conn:
        conn.execute(
            "DELETE FROM kb_chunks WHERE document_id = ? AND conversation_id = ?",
            (doc_id, conv_id),
        )
        cur = conn.execute(
            "DELETE FROM kb_documents WHERE id = ? AND conversation_id = ?",
            (doc_id, conv_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Document not found")
    return {"ok": True}


async def _augment_messages_with_knowledge(
    conv_id: int, messages: list[dict], query_text: str, backend: dict
) -> None:
    """If this bot has a knowledge base, retrieve top-k chunks for the query and
    prepend them to the system message. Best-effort: any failure (embedding
    model not pulled, backend down) is swallowed so a knowledge hiccup never
    blocks a normal chat turn — the bot just answers without augmentation.

    `backend` is the bot's CHAT backend (unused for embedding): the query is
    embedded on the local embed backend so chunks + query use the same model,
    even when the bot chats through a cloud relay. See _resolve_embed_backend.
    """
    if not query_text or not query_text.strip():
        return
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT text, embedding, document_id FROM kb_chunks WHERE conversation_id = ?",
            (conv_id,),
        ).fetchall()
        if not rows:
            return
        docrows = conn.execute(
            "SELECT id, filename FROM kb_documents WHERE conversation_id = ?",
            (conv_id,),
        ).fetchall()
    names = {r["id"]: r["filename"] for r in docrows}
    try:
        embed_backend = _resolve_embed_backend()
        qvecs = await llm.embed(embed_backend, EMBED_MODEL, [query_text])
    except Exception:
        return
    if not qvecs or not qvecs[0]:
        return
    chunks = [
        {
            "text": r["text"],
            "embedding": knowledge.unpack_vector(r["embedding"]),
            "filename": names.get(r["document_id"], "document"),
        }
        for r in rows
    ]
    # Balanced retrieval so one huge/noisy book can't monopolize every slot and
    # bury a smaller book's relevant chunk. Single-doc bots behave like top_k.
    passages = knowledge.top_k_balanced(qvecs[0], chunks, k=KB_TOP_K)
    block = knowledge.build_context_block(passages)
    if block and messages and messages[0].get("role") == "system":
        messages[0]["content"] = block + "\n\n" + messages[0]["content"]


# ---------- MCP plugins (per-bot tool servers) ----------

class MCPServerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field("", max_length=80)
    url: str = Field(..., min_length=1, max_length=2000)
    enabled: bool = True


class MCPServersUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    servers: list[MCPServerSpec]


class MCPTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., min_length=1, max_length=2000)


@app.get("/api/conversations/{conv_id}/mcp")
def api_get_mcp(conv_id: int):
    """Return the bot's configured MCP servers."""
    conv = _conv_exists(conv_id)
    return {"servers": conv.get("mcp_servers", []) or []}


@app.put("/api/conversations/{conv_id}/mcp")
def api_set_mcp(conv_id: int, body: MCPServersUpdate):
    """Replace the bot's MCP server list."""
    _conv_exists(conv_id)
    servers = [s.model_dump() for s in body.servers]
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET mcp_servers = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(servers), conv_id),
        )
        conn.commit()
    return {"servers": servers}


@app.post("/api/conversations/{conv_id}/mcp/test")
async def api_test_mcp(conv_id: int, body: MCPTestRequest):
    """Connect to an MCP server URL and list its tools — used by the 'add
    server' UI to confirm a URL works before saving it."""
    _conv_exists(conv_id)
    try:
        tools = await mcp_host.list_tools(body.url)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "tools": [t["function"]["name"] for t in tools]}


def _enabled_mcp_servers(conv: dict) -> list[dict]:
    return [s for s in (conv.get("mcp_servers") or []) if s.get("enabled", True) and s.get("url")]


async def _run_mcp_tool_loop(model: str, messages: list[dict], eff: dict,
                             backend: dict, servers: list[dict]) -> str:
    """Run a bounded model→tools→model loop using the bot's MCP servers.

    Returns the final visible text. If no tools are reachable, falls back to a
    plain completion. Tool errors are fed back to the model as text so it can
    recover rather than crashing the turn.
    """
    tools, routing = await mcp_host.gather_tools(servers)
    params = dict(temperature=eff["temperature"], max_tokens=eff["max_tokens"],
                  top_p=eff["top_p"], top_k=eff["top_k"], think=eff["think"])
    if not tools:
        return await llm.chat(backend, model, messages, **params)

    convo = list(messages)
    for _ in range(MCP_MAX_TOOL_ITERS):
        resp = await llm.chat_with_tools(backend, model, convo, tools, **params)
        calls = resp.get("tool_calls") or []
        if not calls:
            return resp.get("content") or ""
        convo.append(resp["assistant_message"])
        for call in calls:
            route = routing.get(call["name"])
            if not route:
                result = f"(no MCP server provides a tool named '{call['name']}')"
            else:
                try:
                    result = await mcp_host.call_tool(
                        route["url"], route.get("headers"), call["name"], call["arguments"]
                    )
                except Exception as e:
                    result = f"(tool '{call['name']}' failed: {e})"
            convo.append(llm.tool_result_message(backend, call, result))
    # Exhausted the iteration budget — ask for a final answer without tools.
    final = await llm.chat(backend, model, convo, **params)
    return final or "(stopped: reached the maximum number of tool-call rounds)"


# ---------- Per-bot evaluation (scoring) ----------

class EvalCaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(..., min_length=1)
    expected: str = Field(..., min_length=1)


class EvalCasesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cases: list[EvalCaseSpec]


class EvalRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["exact", "contains", "judge"] = "exact"
    # For judge mode — which model grades. Supplied by the frontend from the
    # user's Prompt-Generator model choice. Ignored for exact/contains.
    judge_backend_id: int | None = None
    judge_model: str | None = None


@app.post("/api/conversations/{conv_id}/eval/cases")
def api_add_eval_cases(conv_id: int, body: EvalCasesCreate):
    """Bulk-add test cases to a bot's eval set."""
    _conv_exists(conv_id)
    with db.get_conn() as conn:
        for c in body.cases:
            conn.execute(
                "INSERT INTO eval_cases (conversation_id, input, expected) VALUES (?, ?, ?)",
                (conv_id, c.input, c.expected),
            )
        conn.commit()
    return {"added": len(body.cases)}


@app.get("/api/conversations/{conv_id}/eval/cases")
def api_list_eval_cases(conv_id: int):
    """List a bot's eval cases (newest first)."""
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT id, input, expected, created_at FROM eval_cases
               WHERE conversation_id = ? ORDER BY id ASC""",
            (conv_id,),
        ).fetchall()
    return {"cases": [dict(r) for r in rows]}


@app.delete("/api/conversations/{conv_id}/eval/cases/{case_id}")
def api_delete_eval_case(conv_id: int, case_id: int):
    with db.get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM eval_cases WHERE id = ? AND conversation_id = ?",
            (case_id, conv_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Eval case not found")
    return {"ok": True}


@app.delete("/api/conversations/{conv_id}/eval/cases")
def api_clear_eval_cases(conv_id: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM eval_cases WHERE conversation_id = ?", (conv_id,))
        conn.commit()
    return {"ok": True}


@app.post("/api/conversations/{conv_id}/eval/seed")
def api_seed_eval_cases(conv_id: int):
    """Seed eval cases from this bot's saved chat history — each user→assistant
    pair becomes a case (input=user turn, expected=assistant reply). Reuses the
    same pair extraction as the dataset CSV export."""
    conv = _conv_exists(conv_id)
    pairs = list(_iter_pairs(conv.get("messages", []) or []))
    added = 0
    with db.get_conn() as conn:
        for user_msg, assistant_msg in pairs:
            inp = _content_text_for_export(user_msg.get("display_text", user_msg.get("content", "")))
            exp = _content_text_for_export(assistant_msg.get("content", ""))
            if not inp.strip() or not exp.strip():
                continue
            conn.execute(
                "INSERT INTO eval_cases (conversation_id, input, expected) VALUES (?, ?, ?)",
                (conv_id, inp, exp),
            )
            added += 1
        conn.commit()
    return {"added": added}


@app.post("/api/conversations/{conv_id}/eval/run")
async def api_run_eval(conv_id: int, req: EvalRunRequest):
    """Run the bot over its eval set and score each case. Returns per-case
    results + overall accuracy. Scoring mode: exact | contains | judge."""
    _conv_exists(conv_id)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, input, expected FROM eval_cases WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,),
        ).fetchall()
    cases = [dict(r) for r in rows]
    if not cases:
        return {"mode": req.mode, "total": 0, "passed": 0, "accuracy": 0.0, "results": []}

    judge_backend = None
    if req.mode == "judge":
        if not req.judge_model:
            raise HTTPException(400, "judge mode requires judge_model (and judge_backend_id).")
        judge_backend = _load_backend(req.judge_backend_id)

    results = []
    passed = 0
    for c in cases:
        try:
            reply = await _run_conv_message(conv_id, c["input"])
        except (httpx.ConnectError, RuntimeError) as e:
            reply = f"(error: {e})"
        if req.mode == "judge":
            try:
                verdict = await llm.chat(
                    judge_backend, req.judge_model,
                    evals.build_judge_messages(c["input"], c["expected"], reply),
                    temperature=0.0, max_tokens=8, think=False,
                )
                ok = evals.parse_judge(verdict)
            except (httpx.ConnectError, RuntimeError):
                ok = False
        else:
            ok = evals.score(req.mode, reply, c["expected"])
        if ok:
            passed += 1
        results.append({
            "case_id": c["id"], "input": c["input"], "expected": c["expected"],
            "got": reply, "passed": ok,
        })

    total = len(cases)
    return {
        "mode": req.mode,
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4),
        "results": results,
    }


class MessageEditRequest(BaseModel):
    """Body for PATCH /api/conversations/{id}/messages/{index}.

    Only the message content is editable. Empty string is allowed — that's a
    user choice (e.g. deleting the content of a placeholder turn).
    """
    model_config = ConfigDict(extra="forbid")
    content: str


@app.patch("/api/conversations/{conv_id}/messages/{index}")
def api_edit_message(conv_id: int, index: int, data: MessageEditRequest):
    """Edit a single stored message in place.

    Designed for fine-tuning data curation: overwrite an unsatisfying
    assistant response with the ideal one. The first edit preserves the
    pristine original in `original_content` so you can still audit or export
    it as the "rejected" side of a DPO pair later. Subsequent edits update
    `content` only — `original_content` stays anchored to whatever the model
    first produced.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversation not found")

        messages = json.loads(row["messages"] or "[]")
        if index < 0 or index >= len(messages):
            raise HTTPException(
                404,
                f"Message index {index} out of range (conversation has {len(messages)} messages)",
            )

        msg = messages[index]
        if not msg.get("edited"):
            # First edit: pin the original so later edits can't overwrite it.
            msg["original_content"] = msg.get("content", "")
        msg["content"] = data.content
        msg["edited"] = True
        msg["edited_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        messages[index] = msg

        conn.execute(
            "UPDATE conversations SET messages = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(messages), conv_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    return db.row_to_dict(updated)


# ---------- Dataset-export helpers ----------
#
# Both export paths (CSV and ZIP) share these two utilities. The CSV path
# wants the user-visible text only (text-only training data); the ZIP path
# wants the full multimodal content array with images extracted to files.

_IMAGE_MIME_TO_EXT = {
    "image/png":  "png",
    "image/jpeg": "jpg",
    "image/jpg":  "jpg",
    "image/webp": "webp",
    "image/gif":  "gif",
    "image/bmp":  "bmp",
}


def _content_text_for_export(content) -> str:
    """Pull the text the user / model actually saw from a possibly-multimodal
    `content` field. String → returned as-is. List → text parts joined.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        p.get("text", "") or ""
        for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    )


def _safe_filename(title: str | None, conv_id: int) -> str:
    """Filesystem- and URL-safe filename derived from the conversation title."""
    raw = title or f"conv{conv_id}"
    out = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in raw)
    return out.strip("_") or f"conv{conv_id}"


def _iter_pairs(messages: list[dict]):
    """Yield (user_msg, assistant_msg) tuples in order. Orphan user messages
    with no reply (partial turns) are skipped — they aren't useful SFT data.
    """
    i = 0
    while i < len(messages) - 1:
        a, b = messages[i], messages[i + 1]
        if a.get("role") == "user" and b.get("role") == "assistant":
            yield a, b
            i += 2
        else:
            i += 1


@app.get("/api/conversations/{conv_id}/export.csv")
def api_export_conversation_csv(conv_id: int):
    """Download this conversation as a text-only fine-tuning CSV.

    Columns: `input` (user turn, text only) and `output` (assistant reply).
    For multimodal turns, the user-side text is the typed text — `display_text`
    if present (no `[Attached: ...]` preambles), else the joined text parts.
    Image data is **not** preserved; use the ZIP export for that.

    Orphan user messages with no reply yet are skipped — partial turns aren't
    useful SFT data. Edited content is exported as-is.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT title, messages FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")

    messages = json.loads(row["messages"] or "[]")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["input", "output"])
    for user_msg, assistant_msg in _iter_pairs(messages):
        # Prefer display_text (the user's typed text without prepended file
        # bodies). Falls back to the raw text-extracted content for legacy
        # rows that pre-date the display_text field.
        user_text = user_msg.get("display_text")
        if not user_text:
            user_text = _content_text_for_export(user_msg.get("content", ""))
        writer.writerow([
            user_text.strip(),
            _content_text_for_export(assistant_msg.get("content", "")).strip(),
        ])

    safe_title = _safe_filename(row["title"], conv_id)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.csv"',
        },
    )


@app.get("/api/conversations/{conv_id}/export.zip")
def api_export_conversation_zip(conv_id: int):
    """Download this conversation as a multimodal SFT bundle (JSONL + images).

    The ZIP layout::

        <title>.jsonl              one chat-turn pair per line, OpenAI shape
        images/<i>_user_<j>.<ext>  any base64 images attached to user turns

    Each JSONL line carries an OpenAI-compatible `messages` array — the same
    shape consumed by HuggingFace's `datasets.load_dataset`, OpenAI's
    fine-tuning API, axolotl, unsloth, and most modern training libraries::

        {"messages": [
          {"role": "user", "content": [
            {"type": "text", "text": "what's in this?"},
            {"type": "image_url", "image_url": {"url": "images/0_user_0.png"}}
          ]},
          {"role": "assistant", "content": "A red square."}
        ]}

    Text-only turns serialize with a string `content` (no array wrapper) for
    cleaner JSONL. Text- and PDF-attachment bodies are inlined into the user
    turn's text — that's what the model actually saw at training time, so
    that's what demonstration data should preserve. Skips orphan user
    messages with no reply.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT title, messages FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")

    messages = json.loads(row["messages"] or "[]")
    safe_title = _safe_filename(row["title"], conv_id)

    zip_buf = io.BytesIO()
    jsonl_lines: list[str] = []

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pair_idx, (user_msg, assistant_msg) in enumerate(_iter_pairs(messages)):
            # ----- User content: extract images, rewrite urls to relative paths -----
            user_content_in = user_msg.get("content", "")
            user_text_parts: list[str] = []
            user_image_parts: list[dict] = []
            img_idx = 0

            if isinstance(user_content_in, str):
                if user_content_in:
                    user_text_parts.append(user_content_in)
            elif isinstance(user_content_in, list):
                for p in user_content_in:
                    if not isinstance(p, dict):
                        continue
                    ptype = p.get("type")
                    if ptype == "text":
                        txt = p.get("text", "") or ""
                        if txt:
                            user_text_parts.append(txt)
                    elif ptype == "image_url":
                        url = ((p.get("image_url") or {}).get("url")) or ""
                        m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", url, re.DOTALL)
                        if not m:
                            # Already a relative path, or a non-data url — pass through.
                            user_image_parts.append(p)
                            continue
                        mime, b64 = m.group(1).lower(), m.group(2)
                        ext = _IMAGE_MIME_TO_EXT.get(mime, "bin")
                        try:
                            raw = base64.b64decode(b64)
                        except Exception:
                            continue
                        rel_path = f"images/{pair_idx}_user_{img_idx}.{ext}"
                        zf.writestr(rel_path, raw)
                        user_image_parts.append(
                            {"type": "image_url", "image_url": {"url": rel_path}}
                        )
                        img_idx += 1

            user_text_combined = "\n\n".join(s.strip() for s in user_text_parts if s.strip())

            # Build the user message in OpenAI shape. Text-only → string
            # content (cleaner JSONL); multimodal → typed-parts array.
            if user_image_parts:
                content_parts = []
                if user_text_combined:
                    content_parts.append({"type": "text", "text": user_text_combined})
                content_parts.extend(user_image_parts)
                user_out = {"role": "user", "content": content_parts}
            else:
                user_out = {"role": "user", "content": user_text_combined}

            # ----- Assistant: text only (collapsed if it ever came back as a list) -----
            assistant_out = {
                "role": "assistant",
                "content": _content_text_for_export(assistant_msg.get("content", "")).strip(),
            }

            jsonl_lines.append(json.dumps(
                {"messages": [user_out, assistant_out]},
                ensure_ascii=False,
            ))

        # Write the JSONL file last so it sits at the front of the directory listing.
        zf.writestr(f"{safe_title}.jsonl", "\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""))

    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.zip"',
        },
    )


@app.get("/api/conversations/{conv_id}/export.classify.zip")
def api_export_conversation_classification_zip(conv_id: int):
    """Download this conversation as an image-classification dataset.

    Use case: a vision-capable bot acting as a labeler. The system prompt
    holds the labeling instructions ("answer 'drunk' or 'sober'", "return
    JSON with bbox + class", etc.); each user turn uploads one or more
    images; each assistant turn returns the label for those images. This
    endpoint emits a flat CSV-of-(image, label) ready for `ImageFolder`-
    style loaders, sklearn pipelines, or a training script's `pandas.read_csv`.

    ZIP layout::

        <title>.csv               two columns: image,label
        images/<i>_user_<j>.<ext> one entry per image attached to a user turn

    Rules:

    - **Pairs without an image attachment are skipped.** Text-only pairs
      aren't classification examples.
    - **The user's typed text is ignored.** Only the image and the
      assistant's reply form a row. (The bot already saw the user text at
      label time; for the dataset, only `image → label` matters.)
    - **Multi-image turns produce one row per image, sharing the same
      label.** That's standard data-labeling behavior — when a labeler
      tags a batch as "all drunk," the dataset wants one row per image.
    - **Filename is `<sanitized-title>-classification.zip`** so it doesn't
      collide with the multimodal SFT ZIP (`<title>.zip`) — both can be
      downloaded for the same conversation without overwriting each other.

    The image filenames + paths match the multimodal SFT ZIP's, so the two
    archives can be unzipped into the same folder if you want both
    representations of the same data.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT title, messages FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")

    messages = json.loads(row["messages"] or "[]")
    safe_title = _safe_filename(row["title"], conv_id)

    zip_buf = io.BytesIO()
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["image", "label"])

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pair_idx, (user_msg, assistant_msg) in enumerate(_iter_pairs(messages)):
            user_content_in = user_msg.get("content", "")
            if not isinstance(user_content_in, list):
                continue  # text-only pair → not a classification example

            # The label is the assistant's text response, stripped of trailing
            # whitespace. Could be "true" / "false" / a category / a JSON blob —
            # we don't try to parse, that's the trainer's job.
            label = _content_text_for_export(assistant_msg.get("content", "")).strip()

            img_idx = 0
            for p in user_content_in:
                if not isinstance(p, dict) or p.get("type") != "image_url":
                    continue
                url = ((p.get("image_url") or {}).get("url")) or ""
                m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", url, re.DOTALL)
                if not m:
                    continue
                mime, b64 = m.group(1).lower(), m.group(2)
                ext = _IMAGE_MIME_TO_EXT.get(mime, "bin")
                try:
                    raw = base64.b64decode(b64)
                except Exception:
                    continue
                rel_path = f"images/{pair_idx}_user_{img_idx}.{ext}"
                zf.writestr(rel_path, raw)
                writer.writerow([rel_path, label])
                img_idx += 1

        # CSV last so it appears at the top of the listing.
        zf.writestr(f"{safe_title}.csv", csv_buf.getvalue())

    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}-classification.zip"',
        },
    )


# ---------- Chat (legacy generic endpoint — ChatRequest carries everything) ----------

def _build_messages(req: ChatRequest) -> list[dict]:
    msgs = [{"role": "system", "content": req.system_prompt}]
    msgs.extend(m.model_dump() for m in req.messages)
    return msgs


def _persist_turn(req: ChatRequest, assistant_text: str, backend: dict) -> None:
    """Append the latest user turn + assistant reply to the conversation."""
    if not req.conversation_id or not req.messages:
        return
    last_user = req.messages[-1]
    snapshot = {
        "model": req.model,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "think": req.think,
        "backend_id": backend["id"],
        "backend_name": backend["name"],
    }
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE id = ?", (req.conversation_id,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row["messages"] or "[]")
        existing.append({"role": last_user.role, "content": last_user.content, "params": snapshot})
        # Strip trailing whitespace from model output — it's almost always
        # junk padding the model appends, and it pollutes both the edit
        # textarea and the CSV export (bad training data).
        existing.append({"role": "assistant", "content": assistant_text.strip(), "params": snapshot})
        conn.execute(
            "UPDATE conversations SET messages = ?, model = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing), req.model, req.conversation_id),
        )
        conn.commit()


# ---------- Bot import/export ----------
#
# Portable, share-by-file bot configs. Format: a small JSON file with model
# name (string, not backend ID — backend IDs don't survive across instances),
# system prompt, sampling params, and optionally the conversation history.
# No API keys, no backend rows.

_BOT_EXPORT_FORMAT = "miniclosed-bot"
_BOT_EXPORT_FORMAT_VERSION = 1
_APP_EXPORT_FORMAT = "miniclosed-app"
_APP_EXPORT_FORMAT_VERSION = 1


class BotImportRequest(BaseModel):
    """POST /api/conversations/import body."""
    model_config = ConfigDict(extra="forbid")
    data: dict
    # When set, skip the auto-match probe and use this backend. The GUI sends
    # this on the second pass after the user picks from `available_backends`.
    backend_id: int | None = None


class AppImportRequest(BaseModel):
    """POST /api/apps/import body. Same shape as BotImportRequest — `backend_id`,
    if set, is applied to every bot in the imported app."""
    model_config = ConfigDict(extra="forbid")
    data: dict
    backend_id: int | None = None


def _build_bot_export(row, include_history: bool) -> dict:
    """The `bot`-shaped block that both the bot export and the app export emit.

    `row` is a sqlite Row with title, model, system_prompt, params, messages.
    Returns just the bot dict (no format envelope) — the caller wraps it.
    """
    return {
        "title": row["title"],
        "model": row["model"],
        "system_prompt": row["system_prompt"],
        "params": json.loads(row["params"] or "{}"),
        "sample_messages": json.loads(row["messages"] or "[]") if include_history else [],
    }


def _validate_bot_payload(bot: dict) -> tuple[str, str, str, dict, list]:
    """Validate a single bot block from an import file.

    Returns (title, model, system_prompt, params, sample_messages). Raises
    HTTPException(400) on malformed input. `sample_messages` may be absent
    in the source dict (defaults to []); if present but not a list we drop
    it and the caller can record a warning.
    """
    if not isinstance(bot, dict):
        raise HTTPException(400, "Each entry in 'bots' must be an object")
    title = (bot.get("title") or "Imported bot").strip() or "Imported bot"
    model = bot.get("model")
    system_prompt = bot.get("system_prompt") or "You are a helpful AI assistant."
    params = bot.get("params") or {}
    if not isinstance(model, str) or not model:
        raise HTTPException(400, "Missing 'bot.model' (string)")
    if not isinstance(params, dict):
        raise HTTPException(400, "'bot.params' must be an object")
    sample_messages = bot.get("sample_messages")
    if sample_messages is not None and not isinstance(sample_messages, list):
        sample_messages = None  # caller will record a warning
    return title, model, system_prompt, params, sample_messages or []


def _unique_title(title: str, taken: set[str]) -> str:
    """Suffix `(2)`, `(3)`, ... onto `title` until it's not in `taken`.
    Returns the resolved title AND mutates `taken` to include it — callers
    importing multiple bots in one transaction pass the same set across calls
    so titles created earlier in the loop don't collide with later ones."""
    out = title
    if out in taken:
        suffix = 2
        while f"{title} ({suffix})" in taken:
            suffix += 1
        out = f"{title} ({suffix})"
    taken.add(out)
    return out


def _insert_bot_row(
    title: str, model: str, system_prompt: str, params: dict,
    sample_messages: list, backend_id: int, app_id: int | None = None,
) -> int:
    """Insert a conversation row and return its new id. Shared by both
    `/api/conversations/import` and the per-bot loop in `/api/apps/import`."""
    with db.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO conversations (title, model, system_prompt, params, messages, backend_id, app_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, model, system_prompt, json.dumps(params),
             json.dumps(sample_messages), backend_id, app_id),
        )
        conn.commit()
        return cur.lastrowid


def _slugify_filename(s: str, fallback: str = "bot") -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in s).strip("-")
    return cleaned[:60] or fallback


async def _resolve_backend_for_model(model_name: str) -> tuple[int | None, list[dict], list[str]]:
    """Find an enabled backend that serves `model_name`.

    Returns (backend_id_or_none, candidate_backends_for_picker, warnings).
    `candidate_backends_for_picker` is the full enabled list (with their
    `models` arrays) so the GUI can render a "no auto-match — pick one" dialog
    without a second round-trip.
    """
    warnings: list[str] = []
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backends WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    backends = [db.row_to_dict(r) for r in rows]

    summary: list[dict] = []
    matched_id: int | None = None
    for b in backends:
        models: list[dict] = []
        try:
            if await llm.is_running(b):
                models = await llm.list_models(b)
        except Exception as e:
            warnings.append(f"backend '{b['name']}' probe failed: {e}")
        names = [m.get("name") or m.get("id") or "" for m in models]
        if matched_id is None and model_name in names:
            matched_id = b["id"]
        summary.append({
            "id": b["id"],
            "name": b["name"],
            "kind": b["kind"],
            "model_present": model_name in names,
            "model_count": len(names),
        })
    return matched_id, summary, warnings


@app.get("/api/conversations/{conv_id}/export")
def api_export_conversation_bot(conv_id: int, include_history: bool = False):
    """Export a saved bot as a portable JSON file.

    Carries config (title, model name, system prompt, params) plus optional
    conversation history. Strips backend_id and any DB ids — the importing
    instance resolves the backend itself by matching on model name.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT title, model, system_prompt, params, messages FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")

    bot_block = _build_bot_export(row, include_history)
    # Legacy on-disk shape: top-level `bot` and `sample_messages` siblings.
    # _build_bot_export folds sample_messages into the bot block for the
    # app export's per-bot entries; pop it back out here to keep the old
    # file layout unchanged for cross-version compatibility.
    sample_messages = bot_block.pop("sample_messages", [])
    export = {
        "format": _BOT_EXPORT_FORMAT,
        "format_version": _BOT_EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "bot": bot_block,
        "sample_messages": sample_messages,
    }
    fname = f"{_slugify_filename(row['title'])}.miniclosed-bot.json"
    return Response(
        content=json.dumps(export, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/conversations/import", status_code=201)
async def api_import_conversation_bot(req: BotImportRequest):
    """Import a bot from a previously-exported JSON file.

    Always creates a NEW conversation row — never overwrites. Backend
    resolution: caller-supplied `backend_id` wins; otherwise we scan enabled
    backends and pick the first one whose model list contains the requested
    model name. If neither path resolves, returns 409 with the candidate
    backend list so the GUI can prompt the user.
    """
    data = req.data
    if not isinstance(data, dict) or data.get("format") != _BOT_EXPORT_FORMAT:
        raise HTTPException(400, f"Not a {_BOT_EXPORT_FORMAT} file")
    fmt_ver = data.get("format_version")
    if not isinstance(fmt_ver, int) or fmt_ver > _BOT_EXPORT_FORMAT_VERSION:
        raise HTTPException(
            400,
            f"Unsupported format_version {fmt_ver!r}; this server understands up to {_BOT_EXPORT_FORMAT_VERSION}",
        )

    bot = data.get("bot")
    if not isinstance(bot, dict):
        raise HTTPException(400, "Missing 'bot' object")
    title, model, system_prompt, params, _ = _validate_bot_payload(bot)

    warnings: list[str] = []

    # 1. Resolve backend ----------------------------------------------------
    if req.backend_id is not None:
        try:
            _load_backend(req.backend_id)
        except HTTPException:
            raise HTTPException(400, f"backend_id {req.backend_id} not found")
        backend_id = req.backend_id
    else:
        matched_id, summary, probe_warnings = await _resolve_backend_for_model(model)
        warnings.extend(probe_warnings)
        if matched_id is None:
            return JSONResponse(
                status_code=409,
                content={
                    "needs_backend": True,
                    "model": model,
                    "available_backends": summary,
                    "warnings": warnings,
                    "detail": (
                        f"No enabled backend currently serves model '{model}'. "
                        "Pick a backend explicitly and retry with backend_id set."
                    ),
                },
            )
        backend_id = matched_id

    # 2. Avoid title collision (cosmetic — DB allows duplicates) ------------
    with db.get_conn() as conn:
        existing_titles = {
            r["title"] for r in conn.execute("SELECT title FROM conversations").fetchall()
        }
    title = _unique_title(title, existing_titles)

    # 3. Insert. The legacy bot file carries `sample_messages` at the top
    # level (sibling of `bot`); validate it separately from the bot block.
    sample_messages = data.get("sample_messages") or []
    if not isinstance(sample_messages, list):
        warnings.append("'sample_messages' was not a list — dropped")
        sample_messages = []
    new_id = _insert_bot_row(title, model, system_prompt, params,
                             sample_messages, backend_id)

    return {
        "id": new_id,
        "title": title,
        "matched_backend_id": backend_id,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Application export / import — same shape one level up: an app envelope
# wrapping N bot blocks. One backend is resolved for the whole app and
# applied to every bot, matching the user's chosen UX (single picker, not
# per-bot picker). The bot block format inside `bots[]` is exactly the
# `bot` object the per-bot export emits (minus the file-level envelope).
# ---------------------------------------------------------------------------


@app.get("/api/apps/{app_id}/export")
def api_export_app(app_id: int, include_history: bool = False):
    """Export an application (metadata + every bot in it) as portable JSON."""
    with db.get_conn() as conn:
        app_row = _app_row(conn, app_id)
        bot_rows = conn.execute(
            """SELECT title, model, system_prompt, params, messages
               FROM conversations WHERE app_id = ? ORDER BY id""",
            (app_id,),
        ).fetchall()

    export = {
        "format": _APP_EXPORT_FORMAT,
        "format_version": _APP_EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "application": {
            "name": app_row["name"],
            "description": app_row["description"] or "",
            "link": app_row["link"] or "",
            "avatar": app_row["avatar"],
        },
        "bots": [_build_bot_export(r, include_history) for r in bot_rows],
    }
    fname = f"{_slugify_filename(app_row['name'], fallback='app')}.miniclosed-app.json"
    return Response(
        content=json.dumps(export, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/apps/import", status_code=201)
async def api_import_app(req: AppImportRequest):
    """Import an application from a .miniclosed-app.json file.

    Always creates a NEW app + N new conversation rows. Backend resolution:
    caller-supplied `backend_id` wins; otherwise we look for a single enabled
    backend that advertises EVERY unique `model` mentioned in `bots[]`. If no
    such backend exists, return 409 with the candidate list so the GUI can
    prompt — same shape as the bot import 409, with `models` (plural) instead
    of `model`.
    """
    data = req.data
    if not isinstance(data, dict) or data.get("format") != _APP_EXPORT_FORMAT:
        raise HTTPException(400, f"Not a {_APP_EXPORT_FORMAT} file")
    fmt_ver = data.get("format_version")
    if not isinstance(fmt_ver, int) or fmt_ver > _APP_EXPORT_FORMAT_VERSION:
        raise HTTPException(
            400,
            f"Unsupported format_version {fmt_ver!r}; this server understands up to {_APP_EXPORT_FORMAT_VERSION}",
        )

    application = data.get("application")
    if not isinstance(application, dict):
        raise HTTPException(400, "Missing 'application' object")
    app_name = (application.get("name") or "").strip()
    if not app_name:
        raise HTTPException(400, "Missing 'application.name'")
    app_description = application.get("description") or ""
    app_link = application.get("link") or ""
    app_avatar = application.get("avatar")
    if app_avatar is not None and (
        not isinstance(app_avatar, str) or not app_avatar.startswith("data:image/")
    ):
        # Don't fail the import over a malformed avatar — just drop it.
        app_avatar = None

    bots = data.get("bots")
    if not isinstance(bots, list):
        raise HTTPException(400, "Missing 'bots' array")

    warnings: list[str] = []
    # Pre-validate every bot up front so a bad bot at index 7 doesn't half-
    # commit the app. Each tuple: (title, model, system_prompt, params,
    # sample_messages, sample_messages_was_invalid).
    parsed_bots: list[tuple[str, str, str, dict, list, bool]] = []
    for i, b in enumerate(bots):
        try:
            t, m, sp, p, sm = _validate_bot_payload(b)
        except HTTPException as e:
            raise HTTPException(400, f"bots[{i}]: {e.detail}")
        sm_invalid = b.get("sample_messages") is not None and not isinstance(
            b.get("sample_messages"), list
        )
        if sm_invalid:
            warnings.append(f"bots[{i}].sample_messages was not a list — dropped")
        parsed_bots.append((t, m, sp, p, sm, sm_invalid))

    # 1. Resolve backend — one for ALL bots ---------------------------------
    if req.backend_id is not None:
        try:
            _load_backend(req.backend_id)
        except HTTPException:
            raise HTTPException(400, f"backend_id {req.backend_id} not found")
        backend_id = req.backend_id
    else:
        backend_id = await _resolve_backend_for_app(parsed_bots, warnings)
        if isinstance(backend_id, JSONResponse):
            return backend_id  # 409 with the picker payload

    # 2. App-name uniqueness (suffix scheme) --------------------------------
    with db.get_conn() as conn:
        existing_app_names = {
            r["name"] for r in conn.execute("SELECT name FROM apps").fetchall()
        }
    app_name = _unique_title(app_name, existing_app_names)

    # 3. Insert app row -----------------------------------------------------
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO apps (name, description, link, avatar) VALUES (?, ?, ?, ?)",
            (app_name, app_description, app_link, app_avatar),
        )
        conn.commit()
        new_app_id = cur.lastrowid

    # 4. Insert each bot ----------------------------------------------------
    with db.get_conn() as conn:
        existing_titles = {
            r["title"] for r in conn.execute("SELECT title FROM conversations").fetchall()
        }
    bot_ids: list[int] = []
    for (title, model, system_prompt, params, sample_messages, _) in parsed_bots:
        title = _unique_title(title, existing_titles)
        new_id = _insert_bot_row(title, model, system_prompt, params,
                                 sample_messages, backend_id, app_id=new_app_id)
        bot_ids.append(new_id)

    return {
        "id": new_app_id,
        "name": app_name,
        "matched_backend_id": backend_id,
        "bot_ids": bot_ids,
        "warnings": warnings,
    }


async def _resolve_backend_for_app(
    parsed_bots: list[tuple], warnings: list[str]
) -> int | JSONResponse:
    """For app import: pick one backend whose model list covers EVERY unique
    `model` referenced by `parsed_bots`. Returns the backend id on success,
    or a 409 JSONResponse (with the candidate list) on failure."""
    unique_models = sorted({m for (_, m, *_rest) in parsed_bots})
    if not unique_models:
        raise HTTPException(400, "App has no bots to import")

    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backends WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    backends = [db.row_to_dict(r) for r in rows]

    summary: list[dict] = []
    matched_id: int | None = None
    for b in backends:
        models: list[dict] = []
        try:
            if await llm.is_running(b):
                models = await llm.list_models(b)
        except Exception as e:
            warnings.append(f"backend '{b['name']}' probe failed: {e}")
        names = [m.get("name") or m.get("id") or "" for m in models]
        present_count = sum(1 for m in unique_models if m in names)
        all_present = present_count == len(unique_models)
        if matched_id is None and all_present:
            matched_id = b["id"]
        summary.append({
            "id": b["id"],
            "name": b["name"],
            "kind": b["kind"],
            "model_present": all_present,
            "model_count": len(names),
            "matched_count": present_count,
            "needed_count": len(unique_models),
        })
    if matched_id is not None:
        return matched_id
    return JSONResponse(
        status_code=409,
        content={
            "needs_backend": True,
            "models": unique_models,
            "available_backends": summary,
            "warnings": warnings,
            "detail": (
                "No enabled backend serves every model in this application "
                f"({', '.join(unique_models)}). Pick a backend and every bot "
                "will run against it."
            ),
        },
    )


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    backend = _load_backend(req.backend_id)
    backend = await _maybe_override_to_relay(backend, req.model)
    messages = _build_messages(req)
    params = {"temperature": req.temperature, "max_tokens": req.max_tokens,
              "top_p": req.top_p, "top_k": req.top_k, "think": req.think}
    t0 = time.perf_counter()
    try:
        text = await llm.chat(
            backend, req.model, messages,
            temperature=req.temperature, max_tokens=req.max_tokens,
            top_p=req.top_p, top_k=req.top_k, think=req.think,
        )
    except (httpx.ConnectError, RuntimeError) as e:
        chat_logs.record_chat(
            endpoint="/api/chat", kind="sync", backend=backend, model=req.model,
            messages=messages, params=params, status="error", error=str(e),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        if isinstance(e, httpx.ConnectError):
            raise HTTPException(503, _backend_err(backend))
        raise HTTPException(502, str(e))
    chat_logs.record_chat(
        endpoint="/api/chat", kind="sync", backend=backend, model=req.model,
        messages=messages, params=params, response_text=text,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
    _persist_turn(req, text, backend)
    return {"response": text}


# ---------- Chat (per-conversation microservice endpoint) ----------

def _build_user_message(text: str | None, attachments: list[dict] | None) -> dict:
    """Combine the user's typed text + uploaded attachments into one user turn.

    The returned dict carries three pieces:

      - ``content``       — what the LLM sees: a content-array starting with a
                            single text part (extracted file bodies prepended,
                            then the user's typed text) followed by one
                            ``image_url`` part per attached image. If there
                            are no attachments at all, falls back to a plain
                            string ``content`` for legacy compatibility.
      - ``display_text``  — the user's typed text only, no extracted-file
                            preambles. Used by the UI to render the chat
                            bubble so the user doesn't see a wall of PDF
                            text in their own message.
      - ``attachments``   — lightweight metadata (name, kind, page_count,
                            char_count, truncated, mime). The actual base64
                            image data lives in ``content``; metadata avoids
                            duplicating it.
    """
    text = (text or "").strip()
    atts = list(attachments or [])
    if not atts:
        return {"role": "user", "content": text}

    text_chunks: list[str] = []
    image_parts: list[dict] = []
    meta: list[dict] = []
    for a in atts:
        kind = a.get("kind")
        name = a.get("name") or "attachment"
        if kind == "image":
            url = a.get("data_url")
            if url:
                image_parts.append({"type": "image_url", "image_url": {"url": url}})
            meta.append({"name": name, "kind": "image", "mime": a.get("mime")})
        elif kind in ("text", "pdf"):
            body = a.get("text") or ""
            if body.strip():
                text_chunks.append(f"[Attached: {name}]\n{body.rstrip()}")
            entry = {"name": name, "kind": kind}
            if a.get("page_count") is not None:
                entry["page_count"] = a["page_count"]
            if a.get("char_count") is not None:
                entry["char_count"] = a["char_count"]
            if a.get("truncated"):
                entry["truncated"] = True
            meta.append(entry)
    if text:
        text_chunks.append(text)
    combined = "\n\n".join(text_chunks)

    content_parts: list[dict] = []
    if combined:
        content_parts.append({"type": "text", "text": combined})
    content_parts.extend(image_parts)

    msg: dict = {"role": "user", "content": content_parts}
    if text:
        msg["display_text"] = text
    if meta:
        msg["attachments"] = meta
    return msg


def _resolve_conversation_chat(
    conv_id: int, req: ConversationChatRequest
) -> tuple[dict, list[dict], dict, dict]:
    """Load conv + its backend + build the ollama-messages list from the request.

    Returns (conv, ollama_messages, effective_params, backend).
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")
    conv = db.row_to_dict(row)

    if (req.message is None) == (req.messages is None):
        raise HTTPException(400, "Provide exactly one of 'message' (string) or 'messages' (array).")

    backend = _load_backend(conv.get("backend_id", 1))

    saved = conv.get("params", {}) or {}
    effective = {
        "model": conv["model"],
        "system_prompt": conv["system_prompt"],
        "temperature": saved.get("temperature", 0.7),
        "max_tokens": saved.get("max_tokens", 2048),
        "top_p": saved.get("top_p", 0.9),
        "top_k": saved.get("top_k", 40),
        "think": saved.get("think"),
        "max_thinking_tokens": saved.get("max_thinking_tokens"),
    }

    if req.message is not None:
        attachments_raw = (
            [a.model_dump() for a in req.attachments] if req.attachments else None
        )
        user_msgs = [_build_user_message(req.message, attachments_raw)]
    else:
        if req.attachments:
            raise HTTPException(
                400,
                "`attachments` is only valid with the single-`message` form. "
                "When using `messages=[…]`, embed multimodal content arrays in-line.",
            )
        user_msgs = [m.model_dump() for m in req.messages]

    # Default: pure-function semantic — model sees only (system + request msgs).
    # Opt-in: when `include_history=true` AND the request uses single-message
    # form, prepend the conversation's saved turns so conversational bots have
    # memory. Not applied when the caller already supplies `messages=[...]`,
    # since they're already in control of the history.
    system_prompt = effective["system_prompt"]
    if req.voice_mode:
        system_prompt = (
            (system_prompt or "").rstrip()
            + "\n\nYou are speaking aloud over a phone call. Reply in 1-2 short "
            "sentences, no markdown, no lists, no code blocks."
        )
    ollama_messages = [{"role": "system", "content": system_prompt}]
    if req.include_history and req.message is not None:
        for m in (conv.get("messages") or []):
            role = m.get("role")
            content = m.get("content", "")
            # `content` may be a string (legacy/text-only) or an OpenAI-style
            # content array (multimodal). Both pass through; llm.py handles
            # per-backend translation.
            has_payload = (
                bool(content) if isinstance(content, str) else bool(content)
            )
            if role in ("user", "assistant") and has_payload:
                ollama_messages.append({"role": role, "content": content})
    ollama_messages.extend(
        # Strip UI-only metadata (`display_text`, `attachments`) before
        # forwarding to the LLM — those are persistence-only fields.
        {k: v for k, v in m.items() if k in ("role", "content")}
        for m in user_msgs
    )

    return conv, ollama_messages, effective, backend


def _chat_snapshot(effective: dict, backend: dict) -> dict:
    params = {k: effective[k] for k in _PARAM_KEYS}
    return {**params, "model": effective["model"],
            "backend_id": backend["id"], "backend_name": backend["name"]}


def _user_entries(user_msgs: list[dict], snapshot: dict) -> list[dict]:
    out = []
    for m in user_msgs:
        entry = {"role": m["role"], "content": m["content"], "params": snapshot}
        # Preserve UI-only metadata so the bubble can be reconstructed on reload.
        if m.get("display_text") is not None:
            entry["display_text"] = m["display_text"]
        if m.get("attachments"):
            entry["attachments"] = m["attachments"]
        out.append(entry)
    return out


def _append_conv_messages(conv_id: int, entries: list[dict]) -> None:
    """Append message entries to a conversation's stored history (atomic)."""
    if not entries:
        return
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row["messages"] or "[]")
        existing.extend(entries)
        conn.execute(
            "UPDATE conversations SET messages = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing), conv_id),
        )
        conn.commit()


def _persist_conv_chat_turn(
    conv_id: int, user_msgs: list[dict], assistant_text: str, effective: dict, backend: dict
) -> None:
    """Append a user turn + the assistant reply atomically (non-streaming path)."""
    snap = _chat_snapshot(effective, backend)
    _append_conv_messages(
        conv_id,
        _user_entries(user_msgs, snap) + [{"role": "assistant", "content": assistant_text.strip(), "params": snap}],
    )


async def _run_conv_message(conv_id: int, message: str) -> str:
    """Run ONE message through a bot's full configured path (knowledge + MCP +
    relay), one-shot: no history, no persist, no chat-log entry. Used by the
    eval runner so a scored response is exactly what the bot would return in
    production. Mirrors the core sequence of api_conv_chat."""
    req = ConversationChatRequest(message=message, include_history=False, persist=False)
    conv, messages, eff, backend = _resolve_conversation_chat(conv_id, req)
    mcp_servers = _enabled_mcp_servers(conv)
    await _augment_messages_with_knowledge(conv_id, messages, message, backend)
    backend = await _maybe_override_to_relay(backend, eff["model"])
    if mcp_servers:
        return await _run_mcp_tool_loop(eff["model"], messages, eff, backend, mcp_servers)
    return await llm.chat(
        backend, eff["model"], messages,
        temperature=eff["temperature"], max_tokens=eff["max_tokens"],
        top_p=eff["top_p"], top_k=eff["top_k"], think=eff["think"],
    )


@app.post("/api/conversations/{conv_id}/chat")
async def api_conv_chat(conv_id: int, req: ConversationChatRequest):
    """Call the saved conversation as a configured function (non-streaming)."""
    conv, messages, eff, backend = _resolve_conversation_chat(conv_id, req)
    mcp_servers = _enabled_mcp_servers(conv) if req.message is not None else []
    if req.message is not None:
        await _augment_messages_with_knowledge(conv_id, messages, req.message, backend)
    backend = await _maybe_override_to_relay(backend, eff["model"])
    attachments = [a.name for a in (req.attachments or [])] if req.attachments else []
    endpoint = f"/api/conversations/{conv_id}/chat"
    t0 = time.perf_counter()
    try:
        if mcp_servers:
            text = await _run_mcp_tool_loop(eff["model"], messages, eff, backend, mcp_servers)
        else:
            text = await llm.chat(
                backend,
                eff["model"], messages,
                temperature=eff["temperature"], max_tokens=eff["max_tokens"],
                top_p=eff["top_p"], top_k=eff["top_k"],
                think=eff["think"],
            )
    except (httpx.ConnectError, RuntimeError) as e:
        chat_logs.record_chat(
            endpoint=endpoint, kind="sync", backend=backend, model=eff["model"],
            messages=messages, params=eff, attachments=attachments,
            status="error", error=str(e),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        if isinstance(e, httpx.ConnectError):
            raise HTTPException(503, _backend_err(backend))
        raise HTTPException(502, str(e))
    chat_logs.record_chat(
        endpoint=endpoint, kind="sync", backend=backend, model=eff["model"],
        messages=messages, params=eff, attachments=attachments,
        response_text=text,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )

    if req.persist:
        if req.message is not None:
            attachments_raw = (
                [a.model_dump() for a in req.attachments] if req.attachments else None
            )
            user_msgs = [_build_user_message(req.message, attachments_raw)]
        else:
            user_msgs = [m.model_dump() for m in req.messages]
        _persist_conv_chat_turn(conv_id, user_msgs, text, eff, backend)

    return {
        "response": text,
        "conversation_id": conv_id,
        "model": eff["model"],
        "backend_id": backend["id"],
        "persisted": req.persist,
    }


async def _run_generation(conv_id, model, messages, eff, backend, mcp_servers,
                          gen, snapshot, attachments, endpoint):
    """Generate the assistant reply in a background task, decoupled from any
    client SSE connection. Accumulates chunks into `gen` (clients stream from
    it), persists the assistant turn on completion, and marks status — so the
    reply lands in the DB even if the user refreshed/closed the tab."""
    t0 = time.perf_counter()
    max_think = eff.get("max_thinking_tokens")
    think_count = 0
    try:
        if mcp_servers:
            text = await _run_mcp_tool_loop(model, messages, eff, backend, mcp_servers)
            async with gen["cond"]:
                gen["chunks"].append(text)
                gen["cond"].notify_all()
        else:
            async for ev in llm.chat_stream(
                backend, model, messages,
                temperature=eff["temperature"], max_tokens=eff["max_tokens"],
                top_p=eff["top_p"], top_k=eff["top_k"], think=eff["think"],
            ):
                async with gen["cond"]:
                    if "content" in ev:
                        gen["chunks"].append(ev["content"])
                    elif "thinking" in ev:
                        think_count += 1
                        if max_think and think_count > max_think:
                            gen["truncated"] = True  # soft cap: stop surfacing reasoning
                        else:
                            gen["thinking"].append(ev["thinking"])
                    gen["cond"].notify_all()
        full = "".join(gen["chunks"])
        _append_conv_messages(conv_id, [{"role": "assistant", "content": full.strip(), "params": snapshot}])
        chat_logs.record_chat(
            endpoint=endpoint, kind="stream", backend=backend, model=model,
            messages=messages, params=eff, attachments=attachments,
            response_text=full, thinking_text="".join(gen["thinking"]) or None,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        async with gen["cond"]:
            gen["status"] = "done"
            gen["cond"].notify_all()
    except asyncio.CancelledError:
        # User pressed Stop. Persist whatever partial reply we have so it isn't
        # lost, mark the generation finished, and swallow the cancellation so
        # the task ends cleanly (it's a fire-and-forget background task).
        partial = "".join(gen["chunks"]).strip()
        if partial:
            _append_conv_messages(conv_id, [{"role": "assistant", "content": partial, "params": snapshot}])
        chat_logs.record_chat(
            endpoint=endpoint, kind="stream", backend=backend, model=model,
            messages=messages, params=eff, attachments=attachments,
            response_text=partial or None, status="error", error="stopped by user",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        async with gen["cond"]:
            gen["status"] = "done"
            gen["cond"].notify_all()
    except (httpx.ConnectError, Exception) as e:
        emsg = _backend_err(backend) if isinstance(e, httpx.ConnectError) else str(e)
        chat_logs.record_chat(
            endpoint=endpoint, kind="stream", backend=backend, model=model,
            messages=messages, params=eff, attachments=attachments,
            response_text="".join(gen["chunks"]) or None, status="error", error=str(e),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        async with gen["cond"]:
            gen["status"] = "error"
            gen["error"] = emsg
            gen["cond"].notify_all()
    finally:
        asyncio.create_task(_evict_generation(conv_id))


async def _evict_generation(conv_id):
    await asyncio.sleep(_GEN_EVICT_GRACE_S)
    g = _generations.get(conv_id)
    if g and g["status"] != "running":
        _generations.pop(conv_id, None)


async def _attach_generation_sse(conv_id):
    """SSE view into a (possibly already in-progress) generation: replays what's
    accumulated so far, then streams new chunks live. Safe to cancel on client
    disconnect — the underlying _run_generation task keeps running."""
    gen = _generations.get(conv_id)
    if not gen:
        # Nothing in flight (finished + evicted, or never started). The answer,
        # if any, is already persisted; client should just re-read the conv.
        yield f"data: {json.dumps({'end': True, 'truncated': False})}\n\n"
        return
    sent_c = sent_t = 0
    trunc_sent = False
    while True:
        async with gen["cond"]:
            while (len(gen["chunks"]) == sent_c and len(gen["thinking"]) == sent_t
                   and gen["status"] == "running" and (trunc_sent or not gen["truncated"])):
                await gen["cond"].wait()
            new_t = gen["thinking"][sent_t:]; sent_t = len(gen["thinking"])
            new_c = gen["chunks"][sent_c:]; sent_c = len(gen["chunks"])
            status, err, truncated = gen["status"], gen["error"], gen["truncated"]
        for t in new_t:
            yield f"data: {json.dumps({'thinking': t})}\n\n"
        if truncated and not trunc_sent:
            trunc_sent = True
            yield f"data: {json.dumps({'thinking_truncated': True})}\n\n"
        for c in new_c:
            yield f"data: {json.dumps({'chunk': c})}\n\n"
        if status != "running":
            if status == "error":
                yield f"data: {json.dumps({'error': err})}\n\n"
            yield f"data: {json.dumps({'end': True, 'truncated': truncated})}\n\n"
            return


@app.post("/api/conversations/{conv_id}/generation/cancel")
async def api_cancel_generation(conv_id: int):
    """Cancel an in-flight background generation (the Stop button). The task's
    CancelledError handler persists any partial reply and marks it done."""
    gen = _generations.get(conv_id)
    if gen and gen["status"] == "running" and gen.get("task"):
        gen["task"].cancel()
        return {"ok": True, "cancelled": True}
    return {"ok": True, "cancelled": False}


@app.get("/api/conversations/{conv_id}/generation/stream")
async def api_attach_generation(conv_id: int):
    """Re-attach (SSE) to an in-flight generation — used by the client to resume
    the streaming/waiting state after a page refresh."""
    return StreamingResponse(
        _attach_generation_sse(conv_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/conversations/{conv_id}/chat/stream")
async def api_conv_chat_stream(conv_id: int, req: ConversationChatRequest):
    """Call the saved conversation as a configured function (SSE streaming).

    Persisted single-message turns (the GUI chat) run a background generation
    that survives a client refresh; the SSE just views its buffer. Non-persist
    or messages=[] callers stream directly (no resilience needed)."""
    conv, messages, eff, backend = _resolve_conversation_chat(conv_id, req)
    mcp_servers = _enabled_mcp_servers(conv) if req.message is not None else []
    if req.message is not None:
        await _augment_messages_with_knowledge(conv_id, messages, req.message, backend)
    backend = await _maybe_override_to_relay(backend, eff["model"])
    attachments = [a.name for a in (req.attachments or [])] if req.attachments else []
    endpoint = f"/api/conversations/{conv_id}/chat/stream"

    # Resilient path: persist the user message NOW, then generate in a background
    # task. The reply survives refresh; this SSE just views the task buffer.
    if req.persist and req.message is not None:
        attachments_raw = [a.model_dump() for a in req.attachments] if req.attachments else None
        user_msgs = [_build_user_message(req.message, attachments_raw)]
        snapshot = _chat_snapshot(eff, backend)
        existing = _generations.get(conv_id)
        if not existing or existing["status"] != "running":
            _append_conv_messages(conv_id, _user_entries(user_msgs, snapshot))
            gen = _new_generation()
            _generations[conv_id] = gen
            gen["task"] = asyncio.create_task(_run_generation(
                conv_id, eff["model"], messages, eff, backend, mcp_servers,
                gen, snapshot, attachments, endpoint))
        return StreamingResponse(
            _attach_generation_sse(conv_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        collected: list[str] = []
        thinking_collected: list[str] = []
        think_count = 0
        max_think = eff.get("max_thinking_tokens")
        truncated = False
        t0 = time.perf_counter()
        # MCP tools require a request/response tool-calling loop, which can't be
        # streamed token-by-token. When a bot has plugins enabled we run the
        # loop, then emit the final answer as a single chunk so the SSE contract
        # (chunk… then end) the frontend expects still holds.
        if mcp_servers:
            try:
                text = await _run_mcp_tool_loop(eff["model"], messages, eff, backend, mcp_servers)
            except (httpx.ConnectError, Exception) as e:
                chat_logs.record_chat(
                    endpoint=endpoint, kind="stream", backend=backend, model=eff["model"],
                    messages=messages, params=eff, attachments=attachments,
                    status="error", error=str(e),
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                )
                msg = _backend_err(backend) if isinstance(e, httpx.ConnectError) else str(e)
                yield f"data: {json.dumps({'error': msg})}\n\n"
                return
            collected.append(text)
            yield f"data: {json.dumps({'chunk': text})}\n\n"
            chat_logs.record_chat(
                endpoint=endpoint, kind="stream", backend=backend, model=eff["model"],
                messages=messages, params=eff, attachments=attachments,
                response_text=text,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            if req.persist:
                attachments_raw = (
                    [a.model_dump() for a in req.attachments] if req.attachments else None
                )
                user_msgs = [_build_user_message(req.message, attachments_raw)]
                _persist_conv_chat_turn(conv_id, user_msgs, text, eff, backend)
            yield f"data: {json.dumps({'end': True, 'truncated': False})}\n\n"
            return
        try:
            async for ev in llm.chat_stream(
                backend,
                eff["model"], messages,
                temperature=eff["temperature"], max_tokens=eff["max_tokens"],
                top_p=eff["top_p"], top_k=eff["top_k"],
                think=eff["think"],
            ):
                if "content" in ev:
                    collected.append(ev["content"])
                    yield f"data: {json.dumps({'chunk': ev['content']})}\n\n"
                elif "thinking" in ev:
                    thinking_collected.append(ev["thinking"])
                    think_count += 1
                    if max_think and think_count > max_think:
                        # Soft cap: stop emitting *visible* reasoning to the UI
                        # and keep the connection open so the model can finish
                        # reasoning and produce the actual answer. The overall
                        # `max_tokens` still serves as the hard kill switch.
                        if not truncated:
                            truncated = True
                            yield f"data: {json.dumps({'thinking_truncated': True, 'reason': 'max_thinking_tokens', 'limit': max_think})}\n\n"
                        continue
                    yield f"data: {json.dumps({'thinking': ev['thinking']})}\n\n"
        except (httpx.ConnectError, Exception) as e:
            chat_logs.record_chat(
                endpoint=endpoint, kind="stream", backend=backend, model=eff["model"],
                messages=messages, params=eff, attachments=attachments,
                response_text="".join(collected) or None,
                thinking_text="".join(thinking_collected) or None,
                status="error", error=str(e),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            if isinstance(e, httpx.ConnectError):
                yield f"data: {json.dumps({'error': _backend_err(backend)})}\n\n"
            else:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        full_response = "".join(collected)
        chat_logs.record_chat(
            endpoint=endpoint, kind="stream", backend=backend, model=eff["model"],
            messages=messages, params=eff, attachments=attachments,
            response_text=full_response,
            thinking_text="".join(thinking_collected) or None,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # Persist whenever we actually produced a response. Truncated-thinking
        # is no longer a persistence-blocker because generation completed.
        if req.persist:
            if req.message is not None:
                attachments_raw = (
                    [a.model_dump() for a in req.attachments] if req.attachments else None
                )
                user_msgs = [_build_user_message(req.message, attachments_raw)]
            else:
                user_msgs = [m.model_dump() for m in req.messages]
            _persist_conv_chat_turn(conv_id, user_msgs, full_response, eff, backend)

        yield f"data: {json.dumps({'end': True, 'truncated': truncated})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =====================================================================
# Voice (per-conversation) — push-to-talk pipeline
# =====================================================================
#
# Three endpoints, all scoped to a conversation so each bot can have its own
# voice + language prefs (stored in conversations.voice_settings) and so the
# turn is persisted exactly like a normal chat turn:
#
#   POST /voice/transcribe — multipart audio → JSON {text, language}
#   POST /voice/speak      — JSON {text} → SSE audio chunks
#   POST /voice/turn       — multipart audio → SSE merging {transcript},
#                            {chunk} × N (assistant tokens), {audio_chunk_b64}
#                            × M, {end}; the user + assistant messages persist
#                            to the conv just like /chat/stream with persist=True.
#
# The voice backend is resolved per-conv via voice_settings.voice_backend_id,
# falling back to the first enabled kind='voice' row in `backends`. Users
# register that backend through Settings → Add endpoint (kind=Voice); there's
# no built-in or env-var seeding — the voice service is an independent box
# the user manages on their own (locally or on RunPod).

class VoiceSpeakRequest(BaseModel):
    """Body for POST /voice/speak."""
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str | None = None
    language: str | None = None
    speed: float | None = Field(None, ge=0.5, le=2.0)


class VoiceSayRequest(BaseModel):
    """Body for POST /voice/say. Caller already has the transcript (e.g. from
    the browser's SpeechRecognition API while the user was holding the mic) so
    we skip server-side Whisper entirely and go straight to LLM + TTS."""
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=8000)
    # Optional override of the bot's saved voice/language for this one turn.
    voice: str | None = None
    language: str | None = None


class CallTurnPersistRequest(BaseModel):
    """Body for POST /api/conversations/{id}/voice/persist-call-turn.

    Call mode uses persist=False on its /chat/stream POST for the latency
    win (skips the resilient-background-task path). This separate endpoint
    lets the voice service fire-and-forget the completed (user, assistant)
    pair into the conversation history AFTER the audio is delivered to the
    browser — same persistence shape as a normal /chat/stream turn, just
    decoupled from the LLM call's hot path."""
    model_config = ConfigDict(extra="forbid")
    user: str = Field(..., min_length=1, max_length=8000)
    assistant: str = Field(..., min_length=1, max_length=64000)


# ---------------------------------------------------------------------------
# Voice text-processing helpers — kept local to the voice section so the
# main chat path stays free of TTS-specific cleanup.
# ---------------------------------------------------------------------------
# Sentence terminator followed by whitespace + a likely next-sentence cue
# (uppercase letter / opening quote / paren / digit). Lookahead so we don't
# consume the next sentence's first character.
_VOICE_SPLIT_PAT = re.compile(r"[.!?][\"')\]]?(\s+)(?=[A-Z\"'(0-9])")
# Soft boundary: terminator + newline (paragraph end).
_VOICE_NEWLINE_PAT = re.compile(r"[.!?][\"')\]]?\n+")
# Abbreviations whose trailing dot must NOT be treated as a sentence boundary.
_VOICE_ABBREVIATIONS = frozenset({
    "mr.", "mrs.", "ms.", "dr.", "sr.", "jr.", "st.", "vs.", "etc.",
    "e.g.", "i.e.", "u.s.", "u.k.", "u.n.", "inc.", "ltd.", "co.", "no.",
    "fig.", "vol.", "ed.", "ch.", "pg.", "p.", "pp.", "approx.", "min.",
    "max.", "avg.", "incl.", "excl.", "rev.", "est.",
})
_VOICE_LAST_WORD_PAT = re.compile(r"\S+$")


def _next_voice_sentence(buf: str, *, min_len: int = 20, force_max: int = 240) -> tuple[str | None, str]:
    """Pop the next complete sentence off `buf`. Returns (sentence, remaining)."""
    if len(buf) >= force_max:
        # Hard cap so a runaway no-punctuation reply still flushes to TTS.
        for i in range(force_max, max(force_max - 60, 1), -1):
            if i < len(buf) and buf[i].isspace():
                return buf[:i].strip(), buf[i:].lstrip()
        return buf[:force_max].strip(), buf[force_max:]

    candidates: list[int] = []
    for m in _VOICE_NEWLINE_PAT.finditer(buf):
        candidates.append(m.end())
    for m in _VOICE_SPLIT_PAT.finditer(buf):
        # Skip if the word just before the terminator looks like an abbreviation.
        before = buf[:m.start() + 1]
        wmatch = _VOICE_LAST_WORD_PAT.search(before)
        if wmatch and wmatch.group(0).lower() in _VOICE_ABBREVIATIONS:
            continue
        candidates.append(m.end())
    if not candidates:
        return None, buf
    cut = min(candidates)
    sentence = buf[:cut].strip()
    if len(sentence) < min_len:
        return None, buf
    return sentence, buf[cut:].lstrip()


# Patterns for clean_for_tts — same set call.py uses, kept in sync manually.
_TTS_BOLD_ITALIC   = re.compile(r"\*{1,3}([^*]+?)\*{1,3}")
_TTS_HEADER        = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_TTS_BULLET        = re.compile(r"^\s*[-*•·]\s+", re.MULTILINE)
_TTS_LETTER_BULLET = re.compile(r"^\s*[A-Za-z]\)\s+", re.MULTILINE)
_TTS_DIGIT_BULLET  = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_TTS_BACKTICKS     = re.compile(r"`+")
_TTS_PIPES         = re.compile(r"\|")
_TTS_BRACKETS      = re.compile(r"[\[\]]")
_TTS_LINK_URL      = re.compile(r"\(https?://[^\s)]+\)")
_TTS_TILDE_HEAVY   = re.compile(r"~{1,3}([^~]+?)~{1,3}")
_TTS_ANGLE_TAGS    = re.compile(r"<[^>]+>")
_TTS_NON_ASCII     = re.compile(r"[^\x00-\x7F]+")
_TTS_MANY_BLANKS   = re.compile(r"\n{2,}")
_TTS_WS            = re.compile(r"\s+")


def _clean_for_tts(text: str) -> str:
    """Strip markdown / emojis / list bullets that the TTS would read literally.

    Mirrors `clean_for_tts` in miniclosedai-voice/call.py so the call path AND
    push-to-talk path produce identical, TTS-safe input.
    """
    if not text:
        return ""
    t = text
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = _TTS_BOLD_ITALIC.sub(r"\1", t)
    t = _TTS_TILDE_HEAVY.sub(r"\1", t)
    t = _TTS_HEADER.sub("", t)
    t = _TTS_BULLET.sub("", t)
    t = _TTS_LETTER_BULLET.sub("", t)
    t = _TTS_DIGIT_BULLET.sub("", t)
    t = _TTS_BACKTICKS.sub("", t)
    t = _TTS_LINK_URL.sub("", t)
    t = _TTS_BRACKETS.sub("", t)
    t = _TTS_PIPES.sub(" ", t)
    t = _TTS_ANGLE_TAGS.sub("", t)
    t = _TTS_NON_ASCII.sub("", t)
    t = _TTS_MANY_BLANKS.sub(" ", t)
    t = _TTS_WS.sub(" ", t)
    return t.strip()


async def _stream_llm_and_tts(
    *,
    llm_backend: dict, model: str, messages: list[dict], eff: dict,
    voice_backend: dict, voice_id: str, lang: str,
):
    """Stream LLM tokens AND TTS audio with FULL concurrency.

    Yields SSE-bound dict events:
        {"chunk": "<assistant token>"}                  × N — verbatim LLM tokens
        {"audio_chunk_b64": "...", "sample_rate": int}  × M — TTS audio per sentence
        {"_full_reply": "<complete reply text>"}              — terminal, for persistence

    Earlier serial version awaited voice.speak_stream inside the LLM read
    loop. While the audio chunks for sentence 1 were being yielded (~1 s of
    Chatterbox synthesis), the LLM SSE socket was suspended — tokens 6, 7, 8
    piled up in the network buffer, then drained as a burst, and you'd see
    "complete paragraph then all audio at once". This concurrent version
    splits the work into two tasks sharing one output queue, exactly the
    same pattern call.py uses:

      _llm_reader  ──reads SSE non-stop──►  text events to out_q
                                            sentence_q for the TTS worker
      _tts_worker  ──pops sentence──►  await voice.speak_stream  ──►  audio to out_q

    The LLM SSE socket is read continuously regardless of TTS state, so
    text events forward at LLM cadence. Audio chunks flow back the moment
    Chatterbox emits each one.
    """
    collected: list[str] = []
    buffer = ""
    out_q: asyncio.Queue = asyncio.Queue()
    sentence_q: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    async def _llm_reader():
        nonlocal buffer
        try:
            async for ev in llm.chat_stream(
                llm_backend, model, messages,
                temperature=eff["temperature"], max_tokens=eff["max_tokens"],
                top_p=eff["top_p"], top_k=eff["top_k"], think=eff["think"],
            ):
                if "content" not in ev:
                    continue
                piece = ev["content"]
                collected.append(piece)
                buffer += piece
                # Forward the text IMMEDIATELY — the bubble streams at the LLM's
                # actual token cadence regardless of what TTS is doing.
                await out_q.put({"chunk": piece})
                # Pump complete sentences onto sentence_q for the TTS worker.
                while True:
                    sentence, buffer = _next_voice_sentence(buffer)
                    if not sentence:
                        break
                    await sentence_q.put(sentence)
            # Trailing fragment that didn't end with a sentence terminator.
            tail = buffer.strip()
            if tail:
                await sentence_q.put(tail)
        except Exception as e:
            await out_q.put({"error": f"LLM stream: {e}"})
        finally:
            await sentence_q.put(None)  # signal end-of-sentences to tts worker

    async def _tts_worker():
        try:
            while True:
                sentence = await sentence_q.get()
                if sentence is None:
                    break
                cleaned = _clean_for_tts(sentence)
                if not cleaned:
                    continue
                try:
                    async for audio_ev in voice.speak_stream(
                        voice_backend, cleaned, voice_id, lang,
                    ):
                        if "chunk_b64" in audio_ev:
                            await out_q.put({
                                "audio_chunk_b64": audio_ev["chunk_b64"],
                                "sample_rate": audio_ev.get("sample_rate"),
                            })
                except Exception as e:
                    await out_q.put({"error": f"TTS: {e}"})
        finally:
            await out_q.put(SENTINEL)

    llm_task = asyncio.create_task(_llm_reader())
    tts_task = asyncio.create_task(_tts_worker())
    try:
        while True:
            ev = await out_q.get()
            if ev is SENTINEL:
                break
            yield ev
    finally:
        for t in (llm_task, tts_task):
            if not t.done():
                t.cancel()

    yield {"_full_reply": "".join(collected).strip()}


def _load_conv_for_voice(conv_id: int) -> dict:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")
    return db.row_to_dict(row)


def _resolve_voice_backend(conv: dict) -> dict:
    """Return the voice backend for this conv, or 404 if none is configured."""
    settings = conv.get("voice_settings") or {}
    explicit_id = settings.get("voice_backend_id")
    if explicit_id is not None:
        b = _load_backend(explicit_id)
        if b.get("kind") != "voice":
            raise HTTPException(
                400, f"Backend #{explicit_id} is not a voice backend (kind={b.get('kind')!r}).",
            )
        if not b.get("enabled"):
            raise HTTPException(400, f"Voice backend #{explicit_id} is disabled.")
        return b
    # Fallback: first enabled voice backend.
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backends WHERE kind = 'voice' AND enabled = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        raise HTTPException(
            404,
            "No voice backend configured. In Settings → LLM Endpoints, click "
            "'+ Add endpoint' and choose 'Voice (ASR + TTS)' with the URL of "
            "your running voice service (e.g. http://localhost:8090).",
        )
    return db.row_to_dict(row)


async def _resolve_voice_choice(
    conv: dict,
    backend: dict,
    override_voice: str | None = None,
    override_lang: str | None = None,
) -> tuple[str, str]:
    """(voice_id, language) — explicit override > conv voice_settings > first
    English voice from the backend > first available voice."""
    s = conv.get("voice_settings") or {}
    voice_id = override_voice or s.get("voice_id")
    language = override_lang or s.get("language")
    if voice_id and language:
        return voice_id, language
    try:
        cat = await voice.list_voices(backend)
    except Exception as e:
        raise HTTPException(502, f"Could not query voices catalog: {e}")
    if not isinstance(cat, dict):
        raise HTTPException(502, "Voice backend returned a malformed /voices catalog.")
    # English first, then any other language with voices.
    for lang in ("en", *sorted(k for k in cat.keys() if k != "en")):
        voices_list = cat.get(lang) or []
        if voices_list and isinstance(voices_list[0], dict):
            vid = voices_list[0].get("id")
            if vid:
                return vid, lang
    raise HTTPException(503, "Voice backend has no voices available.")


@app.get("/api/voices")
async def api_list_voices():
    """Flat catalog of every voice the registered voice backend can produce.

    Powers the chat-topbar voice picker (mirrors the LLM model picker but
    only TTS voices, so the two pickers stay strictly separate). Returns
    404 with a Settings hint when no voice backend is registered — the
    frontend hides the voice picker in that case.

    Response: {"voices": [{"id", "name", "language", "gender"?}, ...]}.
    Voices are flattened across all languages so the picker is a single
    flat dropdown (we don't ask the user to first pick a language then a
    voice — `id` + `language` together fully identify a voice).
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backends WHERE kind = 'voice' AND enabled = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        raise HTTPException(404, "No voice backend configured.")
    backend = db.row_to_dict(row)
    try:
        cat = await voice.list_voices(backend)
    except Exception as e:
        raise HTTPException(502, f"Could not query voices catalog: {e}")
    if not isinstance(cat, dict):
        raise HTTPException(502, "Voice backend returned a malformed /voices catalog.")
    out: list[dict] = []
    for lang in sorted(cat.keys()):
        voices_list = cat.get(lang) or []
        if not isinstance(voices_list, list):
            continue
        for v in voices_list:
            if not isinstance(v, dict):
                continue
            vid = v.get("id") or v.get("name")
            if not vid:
                continue
            out.append({
                "id": vid,
                "name": v.get("name") or vid,
                "language": lang,
                "gender": v.get("gender"),
            })
    return {"voices": out, "backend_id": backend["id"], "backend_name": backend["name"]}


@app.post("/api/conversations/{conv_id}/voice/transcribe")
async def api_conv_voice_transcribe(
    conv_id: int,
    audio: UploadFile = File(...),
    language: str | None = Form(None),
):
    """Proxy: audio in → text out. Uses the conv's voice backend."""
    conv = _load_conv_for_voice(conv_id)
    backend = _resolve_voice_backend(conv)
    audio_bytes = await audio.read()
    try:
        return await voice.transcribe(
            backend, audio_bytes,
            filename=audio.filename or "audio.wav",
            content_type=audio.content_type or "audio/wav",
            language=language,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Voice backend /transcribe failed: {e}")


@app.post("/api/conversations/{conv_id}/voice/speak")
async def api_conv_voice_speak(conv_id: int, req: VoiceSpeakRequest):
    """Proxy: text in → SSE audio chunks out. Uses the conv's voice + language
    (req fields override the saved voice_settings)."""
    conv = _load_conv_for_voice(conv_id)
    backend = _resolve_voice_backend(conv)
    voice_id, language = await _resolve_voice_choice(
        conv, backend, override_voice=req.voice, override_lang=req.language,
    )

    async def gen():
        try:
            async for ev in voice.speak_stream(
                backend, req.text, voice_id, language, speed=req.speed,
            ):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/conversations/{conv_id}/voice/turn")
async def api_conv_voice_turn(
    conv_id: int,
    audio: UploadFile = File(...),
    language: str | None = Form(None),
):
    """The push-to-talk turn: ASR → bot reply → TTS, merged into one SSE.

    Emits, in order:
      data: {transcript: "<text>", asr_language: "en"}
      data: {chunk: "<assistant token>"}           × N
      data: {audio_chunk_b64: "...", sample_rate: 22050}   × M
      data: {end: true}

    Persists the (user, assistant) pair to the conv exactly like
    `/chat/stream` with `persist=true`. Errors at any stage are surfaced as a
    `{error: "..."}` event before the `{end}`.
    """
    conv = _load_conv_for_voice(conv_id)
    voice_backend = _resolve_voice_backend(conv)
    audio_bytes = await audio.read()
    audio_name = audio.filename or "audio.wav"
    audio_ct = audio.content_type or "audio/wav"

    async def gen():
        # 1. ASR
        try:
            asr = await voice.transcribe(
                voice_backend, audio_bytes,
                filename=audio_name, content_type=audio_ct, language=language,
            )
        except Exception as e:
            yield f"data: {json.dumps({'error': f'ASR failed: {e}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return
        transcript = (asr.get("text") or "").strip()
        yield f"data: {json.dumps({'transcript': transcript, 'asr_language': asr.get('language')})}\n\n"
        if not transcript:
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        # 2. LLM — reuse the same path /chat/stream uses, so RAG + relay-route
        #    still work, and the messages list is identical. The client renders
        #    each {status} event as a "thinking" pill in the assistant bubble
        #    so the user knows what's happening between transcript and reply.
        try:
            chat_req = ConversationChatRequest(
                message=transcript, include_history=True, persist=False,
            )
            _, messages, eff, llm_backend = _resolve_conversation_chat(conv_id, chat_req)
            # Tell the UI we're hitting the knowledge base BEFORE we start —
            # the search itself can take 200ms-2s depending on chunk count +
            # embed-backend latency. Skip the event when there's no KB so the
            # status stays accurate.
            has_kb = False
            with db.get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM kb_chunks WHERE conversation_id = ? LIMIT 1",
                    (conv_id,),
                ).fetchone()
                has_kb = row is not None
            if has_kb:
                yield f"data: {json.dumps({'status': 'searching_knowledge'})}\n\n"
            await _augment_messages_with_knowledge(conv_id, messages, transcript, llm_backend)
            llm_backend = await _maybe_override_to_relay(llm_backend, eff["model"])
            # Setup done — LLM call about to start. First-token latency depends
            # on the model and whether it's warm; this status covers that gap.
            yield f"data: {json.dumps({'status': 'thinking'})}\n\n"
        except HTTPException as e:
            yield f"data: {json.dumps({'error': f'LLM setup: {e.detail}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        # 3. Resolve TTS voice up front so we can stream sentence-by-sentence.
        try:
            voice_id, lang = await _resolve_voice_choice(conv, voice_backend)
        except HTTPException as e:
            yield f"data: {json.dumps({'error': f'voice choice: {e.detail}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        # 4. Stream LLM tokens AND TTS audio interleaved — each completed
        #    sentence is cleaned and fed to the voice backend's /speak/stream
        #    immediately, so the first audio chunk lands while the model is
        #    still producing later sentences.
        full_reply = ""
        try:
            async for ev in _stream_llm_and_tts(
                llm_backend=llm_backend, model=eff["model"],
                messages=messages, eff=eff,
                voice_backend=voice_backend, voice_id=voice_id, lang=lang,
            ):
                if "_full_reply" in ev:
                    full_reply = ev["_full_reply"]
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'LLM/TTS stream: {e}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        # Persist the turn (best-effort — UI surfaces the audio playback even
        # if the DB write hits a transient error).
        try:
            user_msg = {"role": "user", "content": transcript}
            _persist_conv_chat_turn(conv_id, [user_msg], full_reply, eff, llm_backend)
        except Exception:
            pass

        yield f"data: {json.dumps({'end': True})}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/conversations/{conv_id}/voice/say")
async def api_conv_voice_say(conv_id: int, req: VoiceSayRequest):
    """Push-to-talk fast path: caller already has the transcript (from the
    browser's SpeechRecognition API). Skip server-side Whisper entirely; run
    LLM + TTS and return the merged SSE just like /voice/turn.

    Emits, in order:
      data: {transcript: "<echo>"}                    # client already has it,
                                                      # but echoing keeps the
                                                      # event shape identical
                                                      # to /voice/turn
      data: {status: "searching_knowledge" | "thinking"}
      data: {chunk: "<assistant token>"}              × N
      data: {audio_chunk_b64: "...", sample_rate: …}  × M
      data: {end: true}
    """
    conv = _load_conv_for_voice(conv_id)
    voice_backend = _resolve_voice_backend(conv)
    transcript = req.text.strip()
    if not transcript:
        raise HTTPException(400, "Empty text.")

    async def gen():
        # 1. Echo the transcript so the client SSE consumer can keep one
        #    code path for both /voice/turn (server ASR) and /voice/say
        #    (browser ASR).
        yield f"data: {json.dumps({'transcript': transcript, 'asr_source': 'browser'})}\n\n"

        # 2. LLM setup — same code path the normal chat /chat/stream uses, so
        #    RAG + relay-route + history all work identically.
        try:
            chat_req = ConversationChatRequest(
                message=transcript, include_history=True, persist=False,
            )
            _, messages, eff, llm_backend = _resolve_conversation_chat(conv_id, chat_req)
            has_kb = False
            with db.get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM kb_chunks WHERE conversation_id = ? LIMIT 1",
                    (conv_id,),
                ).fetchone()
                has_kb = row is not None
            if has_kb:
                yield f"data: {json.dumps({'status': 'searching_knowledge'})}\n\n"
            await _augment_messages_with_knowledge(conv_id, messages, transcript, llm_backend)
            llm_backend = await _maybe_override_to_relay(llm_backend, eff["model"])
            yield f"data: {json.dumps({'status': 'thinking'})}\n\n"
        except HTTPException as e:
            yield f"data: {json.dumps({'error': f'LLM setup: {e.detail}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        # 3. Resolve TTS voice up front so we can stream sentence-by-sentence.
        try:
            voice_id, lang = await _resolve_voice_choice(
                conv, voice_backend,
                override_voice=req.voice, override_lang=req.language,
            )
        except HTTPException as e:
            yield f"data: {json.dumps({'error': f'voice choice: {e.detail}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        # 4. Stream LLM tokens AND TTS audio interleaved. Each completed
        #    sentence is cleaned (strip markdown / emojis / bullets) and
        #    handed to the voice backend's /speak/stream as soon as it
        #    closes, so the first audio chunk lands while the LLM is still
        #    generating later sentences — same pattern as call.py.
        full_reply = ""
        try:
            async for ev in _stream_llm_and_tts(
                llm_backend=llm_backend, model=eff["model"],
                messages=messages, eff=eff,
                voice_backend=voice_backend, voice_id=voice_id, lang=lang,
            ):
                if "_full_reply" in ev:
                    full_reply = ev["_full_reply"]
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'LLM/TTS stream: {e}'})}\n\n"
            yield f"data: {json.dumps({'end': True})}\n\n"
            return

        try:
            user_msg = {"role": "user", "content": transcript}
            _persist_conv_chat_turn(conv_id, [user_msg], full_reply, eff, llm_backend)
        except Exception:
            pass

        yield f"data: {json.dumps({'end': True})}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/conversations/{conv_id}/voice/persist-call-turn")
async def api_conv_voice_persist_call_turn(conv_id: int, req: CallTurnPersistRequest):
    """Append a (user, assistant) pair from a completed call-mode turn.

    Call mode hits /chat/stream with persist=False so the LLM hot path stays
    fast. After the turn finishes streaming audio to the browser, the voice
    service fires-and-forgets a POST here to write the turn into the
    conversation's history — same shape as a normal /chat/stream persist,
    just decoupled from the response-time-critical loop.

    Returns 404 if the conversation doesn't exist, 200 on persist. Errors
    in persistence are swallowed by the caller (fire-and-forget) so a
    transient DB hiccup doesn't surface as a user-visible call failure.
    """
    conv = _load_conv_for_voice(conv_id)
    # Reuse the chat resolver to produce the same `eff` + `backend` snapshot
    # a normal turn would carry, so the persisted message has the same
    # `params` dict the GUI renders alongside text-chat history.
    chat_req = ConversationChatRequest(
        message=req.user, include_history=False, persist=False,
    )
    _, _, eff, llm_backend = _resolve_conversation_chat(conv_id, chat_req)
    user_msg = {"role": "user", "content": req.user.strip()}
    _persist_conv_chat_turn(conv_id, [user_msg], req.assistant.strip(), eff, llm_backend)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Call signaling proxy (HTTPS browser ↔ HTTP voice container)
# ---------------------------------------------------------------------------
# Browsers refuse cross-origin HTTP fetches from an HTTPS page (mixed content).
# These three endpoints proxy the small JSON / SSE signaling traffic through
# MiniClosedAI's own origin so the browser stays on HTTPS the whole way. The
# actual WebRTC audio (RTP/UDP) flows direct browser ↔ voice container after
# the SDP exchange — it never goes through this proxy and doesn't pay the
# bandwidth cost.

class CallConfigureRequest(BaseModel):
    """Body for /call/configure proxy. The browser only supplies voice prefs;
    conv_id and miniclosedai_url are filled in server-side so a tampered
    client can't make the voice container call an arbitrary URL."""
    model_config = ConfigDict(extra="forbid")
    voice: str | None = None
    language: str | None = None


class CallOfferRequest(BaseModel):
    """Body for /call/offer proxy — passes the SDP through unchanged."""
    model_config = ConfigDict(extra="allow")
    sdp: str | None = None
    type: str
    webrtc_id: str


def _self_url_for_voice(request: Request) -> str:
    """The base URL the voice container should use to call back into
    MiniClosedAI for /chat/stream. We trust the incoming `Host` header: from
    inside a Docker network the LAN IP works, and from a same-machine setup
    the localhost form does. Strip a trailing slash so concatenation is clean."""
    return str(request.base_url).rstrip("/")


@app.post("/api/conversations/{conv_id}/call/configure")
async def api_conv_call_configure(
    conv_id: int, req: CallConfigureRequest, request: Request,
):
    """Proxy POST /call/configure — same-origin so the browser can stay on HTTPS."""
    conv = _load_conv_for_voice(conv_id)
    backend = _resolve_voice_backend(conv)
    voice_id, language = await _resolve_voice_choice(
        conv, backend, override_voice=req.voice, override_lang=req.language,
    )
    payload = {
        "conv_id": conv_id,
        "miniclosedai_url": _self_url_for_voice(request),
        "voice": voice_id,
        "language": language,
    }
    # Pre-warm the bot's LLM in the background — first-turn latency in call
    # mode is dominated by the model load (Ollama's default keep_alive expires
    # in 5 min). Fire-and-forget, never blocks the call setup.
    asyncio.create_task(_warmup_conv_model(conv_id))
    try:
        return await voice.call_configure(backend, payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Voice backend /call/configure failed: {e}")


async def _warmup_conv_model(conv_id: int) -> None:
    """Force the bot's LLM into memory so the first call-mode turn isn't slow.

    Sends a 1-token prompt through the same chat path real turns use, so
    whichever backend the bot points at (Ollama, OpenAI-compat, relay) gets
    warmed correctly. Errors are swallowed — warmup is best-effort.
    """
    try:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT model, backend_id, params FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
        if not row:
            return
        backend = _load_backend(row["backend_id"] or 1)
        backend = await _maybe_override_to_relay(backend, row["model"])
        messages = [{"role": "user", "content": "."}]
        async for ev in llm.chat_stream(
            backend, row["model"], messages,
            temperature=0.0, max_tokens=1, top_p=1.0, top_k=1, think=False,
        ):
            # Bail after first event — the model is loaded once anything streams.
            break
    except Exception:
        pass


@app.post("/api/conversations/{conv_id}/call/offer")
async def api_conv_call_offer(conv_id: int, req: CallOfferRequest):
    """Proxy POST /webrtc/offer — returns the SDP answer JSON from FastRTC."""
    conv = _load_conv_for_voice(conv_id)
    backend = _resolve_voice_backend(conv)
    try:
        return await voice.call_offer(backend, req.model_dump(exclude_none=True))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Voice backend /webrtc/offer failed: {e}")


@app.get("/api/conversations/{conv_id}/call/events/{webrtc_id}")
async def api_conv_call_events(conv_id: int, webrtc_id: str):
    """Proxy GET /call/events/{id} — forwards the SSE stream to the browser."""
    conv = _load_conv_for_voice(conv_id)
    backend = _resolve_voice_backend(conv)

    async def gen():
        try:
            async for ev in voice.call_events(backend, webrtc_id):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest):
    backend = _load_backend(req.backend_id)
    backend = await _maybe_override_to_relay(backend, req.model)
    messages = _build_messages(req)
    params = {"temperature": req.temperature, "max_tokens": req.max_tokens,
              "top_p": req.top_p, "top_k": req.top_k, "think": req.think}

    async def event_stream():
        collected: list[str] = []
        thinking_collected: list[str] = []
        think_count = 0
        max_think = req.max_thinking_tokens
        truncated = False
        t0 = time.perf_counter()
        try:
            async for ev in llm.chat_stream(
                backend,
                req.model,
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                top_p=req.top_p,
                top_k=req.top_k,
                think=req.think,
            ):
                if "content" in ev:
                    collected.append(ev["content"])
                    yield f"data: {json.dumps({'chunk': ev['content']})}\n\n"
                elif "thinking" in ev:
                    thinking_collected.append(ev["thinking"])
                    think_count += 1
                    if max_think and think_count > max_think:
                        # Soft cap — truncate visible reasoning, keep the stream open.
                        if not truncated:
                            truncated = True
                            yield f"data: {json.dumps({'thinking_truncated': True, 'reason': 'max_thinking_tokens', 'limit': max_think})}\n\n"
                        continue
                    yield f"data: {json.dumps({'thinking': ev['thinking']})}\n\n"
        except (httpx.ConnectError, Exception) as e:
            chat_logs.record_chat(
                endpoint="/api/chat/stream", kind="stream", backend=backend, model=req.model,
                messages=messages, params=params,
                response_text="".join(collected) or None,
                thinking_text="".join(thinking_collected) or None,
                status="error", error=str(e),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            if isinstance(e, httpx.ConnectError):
                yield f"data: {json.dumps({'error': _backend_err(backend)})}\n\n"
            else:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        full_response = "".join(collected)
        chat_logs.record_chat(
            endpoint="/api/chat/stream", kind="stream", backend=backend, model=req.model,
            messages=messages, params=params,
            response_text=full_response,
            thinking_text="".join(thinking_collected) or None,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        _persist_turn(req, full_response, backend)
        yield f"data: {json.dumps({'end': True, 'truncated': truncated})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- OpenAI-compatible endpoint ----------
# External clients using the OpenAI SDK hit MiniClosedAI with the conversation
# ID in `model`. We resolve the bot's saved backend and call through it —
# so a conversation bound to LM Studio routes there, not to Ollama.

class OAIMessage(BaseModel):
    role: str
    content: str


class OAICompletionRequest(BaseModel):
    """Minimal OpenAI /v1/chat/completions request shape."""
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[OAIMessage]
    stream: bool = False


def _conv_id_from_openai_model(model_field: str) -> int:
    """Accept any of: "12", "conv-12", "bot-12", "miniclosed/12"."""
    raw = model_field.strip()
    for prefix in ("conv-", "bot-", "miniclosed/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(
            400,
            f"OpenAI-compat endpoint expects `model` to be a MiniClosedAI "
            f"conversation ID (e.g. \"12\" or \"conv-12\"); got {model_field!r}",
        )


def _load_conv_for_openai(conv_id: int) -> dict:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Conversation {conv_id} not found")
    return db.row_to_dict(row)


@app.post("/v1/chat/completions")
async def openai_chat_completions(req: OAICompletionRequest):
    conv_id = _conv_id_from_openai_model(req.model)
    conv = _load_conv_for_openai(conv_id)
    backend = _load_backend(conv.get("backend_id", 1))

    saved = conv.get("params", {}) or {}
    effective = {
        "model": conv["model"],
        "temperature": saved.get("temperature", 0.7),
        "max_tokens": saved.get("max_tokens", 2048),
        "top_p": saved.get("top_p", 0.9),
        "top_k": saved.get("top_k", 40),
        "think": saved.get("think"),
    }
    backend = await _maybe_override_to_relay(backend, effective["model"])

    # Bot's system prompt wins; drop caller-supplied system messages.
    ollama_messages = [{"role": "system", "content": conv["system_prompt"]}]
    ollama_messages.extend(
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.role != "system"
    )

    completion_id = f"chatcmpl-mca-{conv_id}-{int(time.time() * 1000)}"
    created = int(time.time())

    if req.stream:
        async def event_stream():
            sent_any = False
            collected: list[str] = []
            t0 = time.perf_counter()
            try:
                async for ev in llm.chat_stream(
                    backend,
                    effective["model"], ollama_messages,
                    temperature=effective["temperature"], max_tokens=effective["max_tokens"],
                    top_p=effective["top_p"], top_k=effective["top_k"],
                    think=effective["think"],
                ):
                    if "content" not in ev:
                        continue
                    collected.append(ev["content"])
                    delta = {"content": ev["content"]}
                    if not sent_any:
                        delta["role"] = "assistant"
                    sent_any = True
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": effective["model"],
                        "choices": [{
                            "index": 0,
                            "delta": delta,
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
            except (httpx.ConnectError, Exception) as e:
                chat_logs.record_chat(
                    endpoint="/v1/chat/completions", kind="stream",
                    backend=backend, model=effective["model"],
                    messages=ollama_messages, params=effective,
                    response_text="".join(collected) or None,
                    status="error", error=str(e),
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                )
                if isinstance(e, httpx.ConnectError):
                    err = {"error": {"message": _backend_err(backend),
                                     "type": "upstream_unavailable"}}
                else:
                    err = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(err)}\n\n"
                return

            chat_logs.record_chat(
                endpoint="/v1/chat/completions", kind="stream",
                backend=backend, model=effective["model"],
                messages=ollama_messages, params=effective,
                response_text="".join(collected),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

            final = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": effective["model"],
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming
    t0 = time.perf_counter()
    try:
        text = await llm.chat(
            backend,
            effective["model"], ollama_messages,
            temperature=effective["temperature"], max_tokens=effective["max_tokens"],
            top_p=effective["top_p"], top_k=effective["top_k"],
            think=effective["think"],
        )
    except (httpx.ConnectError, RuntimeError) as e:
        chat_logs.record_chat(
            endpoint="/v1/chat/completions", kind="sync",
            backend=backend, model=effective["model"],
            messages=ollama_messages, params=effective,
            status="error", error=str(e),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        if isinstance(e, httpx.ConnectError):
            raise HTTPException(503, _backend_err(backend))
        raise HTTPException(502, str(e))
    chat_logs.record_chat(
        endpoint="/v1/chat/completions", kind="sync",
        backend=backend, model=effective["model"],
        messages=ollama_messages, params=effective,
        response_text=text,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": effective["model"],
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.get("/v1/models")
async def openai_list_models():
    """OpenAI-compatible model listing — each MiniClosedAI conversation appears as a model."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, model, backend_id, created_at FROM conversations ORDER BY id"
        ).fetchall()
    return {
        "object": "list",
        "data": [
            {
                "id": str(r["id"]),
                "object": "model",
                "created": 0,
                "owned_by": "miniclosedai",
                "title": r["title"],
                "backend_model": r["model"],
                "backend_id": r["backend_id"],
            }
            for r in rows
        ],
    }


# ---------- Self-upgrade ----------
#
# Two endpoints power the GUI's "Update available" badge + click-to-upgrade
# flow. The actual work happens in `upgrade.sh` — these endpoints just
# expose the current state and spawn the script in a detached session.
#
#   GET  /api/upgrade/status   → version metadata + last-run progress (safe)
#   POST /api/upgrade/run      → loopback-only, fires the script (mutating)

_PROJECT_DIR = Path(__file__).parent
_UPGRADE_SCRIPT = _PROJECT_DIR / "upgrade.sh"
_UPGRADE_PROGRESS_PATH = Path("/tmp/miniclosedai-upgrade.json")
# Persistent "what did we last see on origin/main?" cache. Mirrors OpenClaw's
# `update-check.json`: lets the server cache the remote SHA across requests
# (so we don't hit GitHub's 60-req/hr anonymous limit on every poll), records
# `first_seen_at` for an "available since X" UI hint, and tracks
# `last_notified_sha` so the once-per-version server log fires exactly once
# per new release rather than every 10 minutes.
_UPGRADE_CHECK_STATE_PATH = Path("/tmp/miniclosedai-upgrade-check.json")
# How long to trust the cached remote SHA before re-querying GitHub. Matches
# the GUI's idle poll cadence — anything shorter would just re-do work the
# previous tick already did.
_UPGRADE_RECHECK_INTERVAL_S = 600


def _git_cmd(*args: str, timeout: float = 5.0) -> str:
    """Run a git subcommand in the project root and return stdout-stripped.
    Raises RuntimeError on non-zero exit so the status endpoint can degrade
    gracefully instead of 500-ing on a missing remote / offline network.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=_PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or '(no stderr)'}"
        )
    return result.stdout.strip()


def _read_upgrade_progress() -> dict | None:
    """Latest progress record written by upgrade.sh, or None if no run yet."""
    try:
        return json.loads(_UPGRADE_PROGRESS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _running_in_docker() -> bool:
    """Best-effort container detection across Linux/macOS/Windows hosts.

    `/.dockerenv` is the classic signal but doesn't exist on every runtime
    (notably some Docker Desktop + Compose setups on macOS, where the file
    is absent inside the container). We add two more signals so the GUI
    correctly classifies Docker installs and skips the in-place upgrade UI.
    """
    if Path("/.dockerenv").exists():
        return True
    try:
        cg = Path("/proc/1/cgroup").read_text()
        if "docker" in cg or "containerd" in cg or "kubepods" in cg:
            return True
    except OSError:
        pass
    if os.environ.get("MINICLOSEDAI_IN_DOCKER") == "1":
        return True
    return False


_DOCKER_UPGRADE_REASON = (
    "Docker installs upgrade with `git pull && docker compose up -d --build` "
    "from the host, not via this endpoint. (The image tags in this project are "
    "built from source, not published to a registry, so `docker compose pull` "
    "always fails with `pull access denied` — rebuild instead.)"
)

_GITHUB_API_MAIN = "https://api.github.com/repos/edantonio505/miniclosedai/commits/main"


def _github_main_sha(timeout: float = 4.0) -> str | None:
    """Fetch the current SHA of `main` on the canonical GitHub repo.

    Used by the Docker path of `api_upgrade_status` since containers don't
    ship a git client. Returns None on any failure (offline, 403/rate-limit,
    repo renamed) — caller degrades gracefully and still surfaces the docker
    rebuild message rather than claiming an update that can't be verified.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                _GITHUB_API_MAIN,
                headers={"Accept": "application/vnd.github+json"},
            )
        if resp.status_code != 200:
            return None
        return resp.json().get("sha")
    except Exception:
        return None


def _read_upgrade_check_state() -> dict:
    """Persistent state for the version-check loop. See `_record_update_state`.
    Missing / corrupted files yield an empty dict — the caller handles bootstrap.
    """
    try:
        return json.loads(_UPGRADE_CHECK_STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_upgrade_check_state(state: dict) -> None:
    """Persist state. Failures are swallowed — a corrupted FS shouldn't break
    the read-only `/api/upgrade/status` endpoint that callers rely on."""
    try:
        _UPGRADE_CHECK_STATE_PATH.write_text(json.dumps(state))
    except OSError:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_update_state(current_sha: str | None, latest_sha: str | None) -> dict:
    """Persist a (current, latest) observation and emit a once-per-version log.

    Returns the updated state dict so callers can surface `first_seen_at` in
    the API response. Three transitions matter:

    - **No update available** (latest is None or matches current):
      clear `last_remote_sha` / `first_seen_at` so a future regression to
      "behind" gets a fresh `first_seen_at` timestamp.

    - **New version detected** (latest != last_remote_sha):
      stamp `first_seen_at = now`. This is the "available since X" hint.

    - **First time we've seen this version** (latest != last_notified_sha):
      print a single line to the server log so operators tailing the log see
      the announcement once, not every 10 minutes. Mirrors OpenClaw's
      `lastNotifiedVersion` gating.

    Note: this function is the side-effect surface for state changes — both
    branches of `api_upgrade_status` (git + docker) call into it so they
    share the once-per-version semantics.
    """
    state = _read_upgrade_check_state()
    state["last_checked_at"] = _now_iso()

    if not current_sha or not latest_sha or latest_sha == current_sha:
        state.pop("last_remote_sha", None)
        state.pop("first_seen_at", None)
        _write_upgrade_check_state(state)
        return state

    if state.get("last_remote_sha") != latest_sha:
        state["last_remote_sha"] = latest_sha
        state["first_seen_at"] = _now_iso()

    if state.get("last_notified_sha") != latest_sha:
        # stderr so it shows up alongside uvicorn's request log without
        # depending on the logging module (rest of app.py uses neither).
        print(
            f"[miniclosedai] update available: {current_sha[:7]} → {latest_sha[:7]}",
            file=sys.stderr,
            flush=True,
        )
        state["last_notified_sha"] = latest_sha

    _write_upgrade_check_state(state)
    return state


def _cached_or_fetch_github_sha() -> str | None:
    """Cached-or-fetch wrapper around `_github_main_sha` for Docker mode.

    GitHub's anonymous REST API allows 60 requests / hour / IP. A single
    chatty client polling every minute would exhaust that in an hour; a busy
    LAN with several browsers open each polling every 10 minutes can also
    creep up. The cache window collapses N concurrent requests within a
    10-minute window into one network call.
    """
    state = _read_upgrade_check_state()
    last_at = state.get("last_checked_at")
    last_sha = state.get("last_remote_sha")
    if last_at and last_sha:
        try:
            cached_age = time.time() - datetime.fromisoformat(last_at).timestamp()
            if 0 <= cached_age < _UPGRADE_RECHECK_INTERVAL_S:
                return last_sha
        except Exception:
            pass
    return _github_main_sha()


def _upgrade_status_base() -> dict:
    """Shared scaffolding fields for the upgrade-status response. Every code
    path in `api_upgrade_status` builds on this to keep the response shape
    stable regardless of which branch was taken."""
    return {
        "current_sha": None,
        "current_short": None,
        "latest_sha": None,
        "latest_short": None,
        "behind": 0,
        "dirty": False,
        "latest_messages": [],
        "last_run": _read_upgrade_progress(),
        "first_seen_at": None,
    }


def _upgrade_status_unknown(base: dict) -> dict:
    """No `.git` directory — user installed from a tarball, or the working
    tree was nuked. In-place upgrade can't work; tell them to re-clone."""
    return {
        **base,
        "installed_via": "unknown",
        "can_upgrade": False,
        "reason": (
            "Not a git checkout. Re-clone from "
            "https://github.com/edantonio505/miniclosedai.git "
            "to enable in-place upgrades."
        ),
    }


def _upgrade_status_docker(base: dict) -> dict:
    """Containers don't ship `.git`, so we can't run git locally. Instead the
    build SHA is baked in via the `GIT_SHA` build arg (compose passes it) and
    we ask GitHub's REST API what `origin/main` currently is. If the two
    differ the badge fires; clicking it surfaces the docker-compose rebuild
    instructions (in-place upgrade still off)."""
    build_sha = (os.environ.get("MINICLOSEDAI_BUILD_SHA") or "").strip() or None

    if not build_sha or build_sha == "unknown":
        reason = (
            _DOCKER_UPGRADE_REASON
            + " (Build SHA not baked into this image — rebuild with "
            "`GIT_SHA=$(git rev-parse HEAD) docker compose up -d --build` "
            "to enable update notifications.)"
        )
        return {**base, "installed_via": "docker", "can_upgrade": False, "reason": reason}

    latest_sha = _cached_or_fetch_github_sha()
    if not latest_sha:
        # GitHub unreachable / rate-limited — degrade gracefully rather than
        # claim either presence or absence of an update we can't verify.
        return {
            **base,
            "current_sha": build_sha,
            "current_short": build_sha[:7],
            "installed_via": "docker",
            "can_upgrade": False,
            "reason": _DOCKER_UPGRADE_REASON,
        }

    state = _record_update_state(build_sha, latest_sha)
    behind = 0 if latest_sha == build_sha else 1   # binary — no graph in-container
    return {
        **base,
        "current_sha": build_sha,
        "current_short": build_sha[:7],
        "latest_sha": latest_sha,
        "latest_short": latest_sha[:7],
        "behind": behind,
        "installed_via": "docker",
        "can_upgrade": False,  # Docker upgrade is always rebuild-from-source
        "reason": _DOCKER_UPGRADE_REASON if behind else "Already on the latest commit.",
        "first_seen_at": state.get("first_seen_at") if behind else None,
    }


def _upgrade_status_git(base: dict) -> dict:
    """Git checkout — fetch origin/main (best-effort, offline tolerated) and
    compute behind-count via the local graph. Records a state-file entry so
    the once-per-version log fires here too, matching Docker mode."""
    try:
        _git_cmd("fetch", "--quiet", "--prune", "origin", "main", timeout=10.0)
    except Exception:
        pass  # offline / DNS failure → fall back to last-known origin/main

    try:
        current_sha = _git_cmd("rev-parse", "HEAD")
        current_short = _git_cmd("rev-parse", "--short", "HEAD")
        try:
            latest_sha = _git_cmd("rev-parse", "origin/main")
            latest_short = _git_cmd("rev-parse", "--short", "origin/main")
            behind = int(_git_cmd("rev-list", "--count", f"{current_sha}..{latest_sha}"))
        except Exception:
            latest_sha, latest_short, behind = current_sha, current_short, 0
        dirty = bool(_git_cmd("status", "--porcelain"))
        if behind > 0:
            log_out = _git_cmd("log", "--pretty=%s", "-50", f"{current_sha}..{latest_sha}")
            messages = [line for line in log_out.splitlines() if line.strip()]
        else:
            messages = []
    except Exception as e:
        return {**base, "installed_via": "git", "can_upgrade": False,
                "reason": f"git read failed: {e}"}

    state = _record_update_state(current_sha, latest_sha if behind > 0 else current_sha)

    can_upgrade = behind > 0 and not dirty and _UPGRADE_SCRIPT.exists()
    reason = None
    if behind == 0:
        reason = "Already on the latest commit."
    elif dirty:
        reason = (
            "Working tree has local changes. Commit, stash, or discard them "
            "before upgrading."
        )
    elif not _UPGRADE_SCRIPT.exists():
        reason = "upgrade.sh missing from the project root."

    return {
        **base,
        "current_sha": current_sha,
        "current_short": current_short,
        "latest_sha": latest_sha,
        "latest_short": latest_short,
        "behind": behind,
        "dirty": dirty,
        "latest_messages": messages,
        "installed_via": "git",
        "can_upgrade": can_upgrade,
        "reason": reason,
        "first_seen_at": state.get("first_seen_at") if behind > 0 else None,
    }


@app.get("/api/upgrade/status")
def api_upgrade_status():
    """Read-only version + update-availability probe.

    Three modes, dispatched by environment:
    - **Docker**: build SHA env + GitHub REST (cache-windowed)
    - **Unknown**: no `.git` directory present, in-place upgrade impossible
    - **Git**: standard `git fetch` + local graph for the behind-count

    All three converge on the same response shape and call into
    `_record_update_state` so the once-per-version log fires regardless of
    which mode the install is running in.
    """
    base = _upgrade_status_base()
    if _running_in_docker():
        return _upgrade_status_docker(base)
    if not (_PROJECT_DIR / ".git").exists():
        return _upgrade_status_unknown(base)
    return _upgrade_status_git(base)


@app.post("/api/upgrade/run")
def api_upgrade_run(request: Request):
    """Spawn upgrade.sh detached and return 202 immediately.

    Loopback-only on principle — even though the app has no auth, mutating
    "shell-exec from HTTP" surface should never be reachable from the LAN.
    The script writes progress to /tmp/miniclosedai-upgrade.json which the
    GUI polls via /api/upgrade/status.
    """
    # Docker pre-check fires before the loopback firewall so a Docker user
    # (whose container traffic enters as the bridge gateway IP, e.g.
    # 172.18.0.1) gets the actionable rebuild message instead of an
    # unexplained 403.
    if _running_in_docker():
        raise HTTPException(status_code=409, detail=_DOCKER_UPGRADE_REASON)

    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=403,
            detail=f"Upgrades only allowed from loopback (got client.host={client_host!r}).",
        )

    status = api_upgrade_status()
    if not status["can_upgrade"]:
        raise HTTPException(
            status_code=409,
            detail=status.get("reason") or "Upgrade not allowed in this state.",
        )

    if not _UPGRADE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="upgrade.sh missing")

    # Detach: new session means the script outlives this server process,
    # which is critical because the script's job is to *kill* this server.
    # stdin/out/err to DEVNULL so the script doesn't pin a closed pipe.
    subprocess.Popen(
        ["bash", str(_UPGRADE_SCRIPT)],
        cwd=str(_PROJECT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "MINICLOSEDAI_UPGRADE_VIA_GUI": "1"},
    )

    return {
        "started": True,
        "from_sha": status["current_short"],
        "to_sha": status["latest_short"],
    }


# ---------- Static / UI ----------

class _NoCacheStatics(StaticFiles):
    """StaticFiles subclass that disables browser caching.

    This is a local dev tool — the cost of refetching app.js / style.css
    every page load is zero, and silent stale-cache bugs are expensive
    (user spent time earlier hitting exactly that).
    """
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


app.mount("/static", _NoCacheStatics(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    resp = FileResponse(STATIC_DIR / "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8095, reload=False)
