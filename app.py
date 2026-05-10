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
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import pypdf

import db
import llm

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


class BackendCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    kind: Literal["ollama", "openai"]
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

    Default behavior: refuses with 409 when any conversation is still pinned
    to this backend, returning the bound list so the GUI can offer to rebind
    them. When `force=true`, also deletes those conversations as a cascade —
    used by the GUI's "delete the bots too" two-step confirm. Built-in
    backends are still 403 regardless of `force`.
    """
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, is_builtin FROM backends WHERE id = ?", (backend_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Backend {backend_id} not found")
        if row["is_builtin"]:
            raise HTTPException(403, "The built-in backend can't be deleted.")

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
        return {"running": True, "models_count": 0, "message": f"Reachable but /models failed: {e}"}
    count = len(models)
    if count == 0:
        return {
            "running": True,
            "models_count": 0,
            "message": f"Reachable, but 0 models available. (If this is LM Studio, is a model loaded? Also confirm the URL ends with '/v1'.)",
        }
    return {"running": True, "models_count": count, "message": f"Reachable · {count} model(s)"}


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

PDF_MAX_BYTES = 10 * 1024 * 1024     # 10 MB raw upload cap
PDF_MAX_PAGES = 50                   # only the first 50 pages are scanned
PDF_MAX_CHARS = 30_000               # output truncated past this many chars


@app.post("/api/extract-pdf")
async def api_extract_pdf(file: UploadFile = File(...)):
    """Extract plain text from an uploaded PDF.

    Returns ``{filename, page_count, char_count, truncated, text}``. ``truncated``
    is true if either the page cap or the character cap was hit; the caller
    can surface that to the user. Image-only / scanned PDFs come back with
    short or empty ``text`` — that's a pypdf limitation, not a bug here.
    """
    raw = await file.read()
    if len(raw) > PDF_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large ({len(raw) / 1024 / 1024:.1f} MB > {PDF_MAX_BYTES // 1024 // 1024} MB cap)",
        )
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")

    total_pages = len(reader.pages)
    pages_scanned = min(total_pages, PDF_MAX_PAGES)
    chunks: list[str] = []
    chars = 0
    truncated = total_pages > PDF_MAX_PAGES
    for i in range(pages_scanned):
        try:
            page_text = reader.pages[i].extract_text() or ""
        except Exception:
            page_text = ""
        # Header lets the model see page boundaries when scanning multi-page docs.
        chunks.append(f"--- Page {i + 1} ---\n{page_text.strip()}")
        chars += len(page_text)
        if chars >= PDF_MAX_CHARS:
            truncated = True
            break

    text = "\n\n".join(chunks)
    if len(text) > PDF_MAX_CHARS:
        text = text[:PDF_MAX_CHARS]
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

    Returns one entry per backend with its model list. Disabled backends are
    included with `running=False` + empty models so the UI can still show them
    greyed out. Preserves `ollama_running` for older front-end code until the
    frontend is updated.
    """
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM backends ORDER BY id").fetchall()
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
            "SELECT id, title, model, backend_id, updated_at FROM conversations ORDER BY updated_at DESC"
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
    return db.row_to_dict(row)


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


@app.delete("/api/conversations/{conv_id}")
def api_delete_conversation(conv_id: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
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


class BotImportRequest(BaseModel):
    """POST /api/conversations/import body."""
    model_config = ConfigDict(extra="forbid")
    data: dict
    # When set, skip the auto-match probe and use this backend. The GUI sends
    # this on the second pass after the user picks from `available_backends`.
    backend_id: int | None = None


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

    params = json.loads(row["params"] or "{}")
    bot_payload = {
        "title": row["title"],
        "model": row["model"],
        "system_prompt": row["system_prompt"],
        "params": params,
    }
    export = {
        "format": _BOT_EXPORT_FORMAT,
        "format_version": _BOT_EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "bot": bot_payload,
        "sample_messages": json.loads(row["messages"] or "[]") if include_history else [],
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
    title = (bot.get("title") or "Imported bot").strip() or "Imported bot"
    model = bot.get("model")
    system_prompt = bot.get("system_prompt") or "You are a helpful AI assistant."
    params = bot.get("params") or {}
    if not isinstance(model, str) or not model:
        raise HTTPException(400, "Missing 'bot.model' (string)")
    if not isinstance(params, dict):
        raise HTTPException(400, "'bot.params' must be an object")

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
    if title in existing_titles:
        suffix = 2
        while f"{title} ({suffix})" in existing_titles:
            suffix += 1
        title = f"{title} ({suffix})"

    # 3. Insert -------------------------------------------------------------
    sample_messages = data.get("sample_messages") or []
    if not isinstance(sample_messages, list):
        warnings.append("'sample_messages' was not a list — dropped")
        sample_messages = []
    with db.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO conversations (title, model, system_prompt, params, messages, backend_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, model, system_prompt, json.dumps(params), json.dumps(sample_messages), backend_id),
        )
        conn.commit()
        new_id = cur.lastrowid

    return {
        "id": new_id,
        "title": title,
        "matched_backend_id": backend_id,
        "warnings": warnings,
    }


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    backend = _load_backend(req.backend_id)
    try:
        text = await llm.chat(
            backend,
            req.model,
            _build_messages(req),
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            top_p=req.top_p,
            top_k=req.top_k,
            think=req.think,
        )
    except httpx.ConnectError:
        raise HTTPException(503, _backend_err(backend))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
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
    ollama_messages = [{"role": "system", "content": effective["system_prompt"]}]
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


def _persist_conv_chat_turn(
    conv_id: int, user_msgs: list[dict], assistant_text: str, effective: dict, backend: dict
) -> None:
    params = {k: effective[k] for k in _PARAM_KEYS}
    snapshot = {
        **params,
        "model": effective["model"],
        "backend_id": backend["id"],
        "backend_name": backend["name"],
    }
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row["messages"] or "[]")
        for m in user_msgs:
            entry = {"role": m["role"], "content": m["content"], "params": snapshot}
            # Preserve UI-only metadata so the bubble can be reconstructed on
            # reload. `display_text` is the user's typed text without the
            # "[Attached: …]" file-body prefixes; `attachments` is per-file
            # metadata used for rendering chips.
            if m.get("display_text") is not None:
                entry["display_text"] = m["display_text"]
            if m.get("attachments"):
                entry["attachments"] = m["attachments"]
            existing.append(entry)
        existing.append({"role": "assistant", "content": assistant_text.strip(), "params": snapshot})
        conn.execute(
            "UPDATE conversations SET messages = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing), conv_id),
        )
        conn.commit()


@app.post("/api/conversations/{conv_id}/chat")
async def api_conv_chat(conv_id: int, req: ConversationChatRequest):
    """Call the saved conversation as a configured function (non-streaming)."""
    conv, messages, eff, backend = _resolve_conversation_chat(conv_id, req)
    try:
        text = await llm.chat(
            backend,
            eff["model"], messages,
            temperature=eff["temperature"], max_tokens=eff["max_tokens"],
            top_p=eff["top_p"], top_k=eff["top_k"],
            think=eff["think"],
        )
    except httpx.ConnectError:
        raise HTTPException(503, _backend_err(backend))
    except RuntimeError as e:
        raise HTTPException(502, str(e))

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


@app.post("/api/conversations/{conv_id}/chat/stream")
async def api_conv_chat_stream(conv_id: int, req: ConversationChatRequest):
    """Call the saved conversation as a configured function (SSE streaming)."""
    conv, messages, eff, backend = _resolve_conversation_chat(conv_id, req)

    async def event_stream():
        collected: list[str] = []
        think_count = 0
        max_think = eff.get("max_thinking_tokens")
        truncated = False
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
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': _backend_err(backend)})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

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
            _persist_conv_chat_turn(conv_id, user_msgs, "".join(collected), eff, backend)

        yield f"data: {json.dumps({'end': True, 'truncated': truncated})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest):
    backend = _load_backend(req.backend_id)
    messages = _build_messages(req)

    async def event_stream():
        collected: list[str] = []
        think_count = 0
        max_think = req.max_thinking_tokens
        truncated = False
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
                    think_count += 1
                    if max_think and think_count > max_think:
                        # Soft cap — truncate visible reasoning, keep the stream open.
                        if not truncated:
                            truncated = True
                            yield f"data: {json.dumps({'thinking_truncated': True, 'reason': 'max_thinking_tokens', 'limit': max_think})}\n\n"
                        continue
                    yield f"data: {json.dumps({'thinking': ev['thinking']})}\n\n"
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': _backend_err(backend)})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        _persist_turn(req, "".join(collected), backend)
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
            except httpx.ConnectError:
                err = {"error": {"message": _backend_err(backend),
                                 "type": "upstream_unavailable"}}
                yield f"data: {json.dumps(err)}\n\n"
                return
            except Exception as e:
                err = {"error": {"message": str(e), "type": "server_error"}}
                yield f"data: {json.dumps(err)}\n\n"
                return

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
    try:
        text = await llm.chat(
            backend,
            effective["model"], ollama_messages,
            temperature=effective["temperature"], max_tokens=effective["max_tokens"],
            top_p=effective["top_p"], top_k=effective["top_k"],
            think=effective["think"],
        )
    except httpx.ConnectError:
        raise HTTPException(503, _backend_err(backend))
    except RuntimeError as e:
        raise HTTPException(502, str(e))

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
