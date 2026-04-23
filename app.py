"""MiniClosedAI — FastAPI app exposing a multi-backend local LLM playground.

Each saved conversation (bot) is pinned to a single backend via
`conversations.backend_id`. Backends can be Ollama or any OpenAI-compatible
server (LM Studio, vLLM, llama.cpp's `server`, etc.). All backend handling
lives in llm.py — this module is HTTP routing + persistence.
"""
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import db
import llm

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="MiniClosedAI", version="0.2.0", lifespan=lifespan)


# ---------- Schemas ----------

class Message(BaseModel):
    role: str
    content: str


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
def api_delete_backend(backend_id: int):
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
        if bound:
            raise HTTPException(
                409,
                {
                    "message": f"Backend {backend_id} is still bound to "
                               f"{len(bound)} conversation(s). Rebind them first.",
                    "bound_conversations": [
                        {"id": r["id"], "title": r["title"]} for r in bound
                    ],
                },
            )

        conn.execute("DELETE FROM backends WHERE id = ?", (backend_id,))
        conn.commit()
    return {"ok": True}


@app.post("/api/backends/test")
async def api_backend_test(data: BackendCreate):
    """Probe a draft (unsaved) backend config. Used by the Settings modal's
    Test-connection button, so the browser doesn't have to make a cross-origin
    call that CORS would block.
    """
    probe = {
        "id": 0,
        "name": data.name or "draft",
        "kind": data.kind,
        "base_url": _normalize_base_url(data.base_url),
        "api_key": data.api_key,
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
        existing.append({"role": "assistant", "content": assistant_text, "params": snapshot})
        conn.execute(
            "UPDATE conversations SET messages = ?, model = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing), req.model, req.conversation_id),
        )
        conn.commit()


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
        user_msgs = [{"role": "user", "content": req.message}]
    else:
        user_msgs = [m.model_dump() for m in req.messages]

    # Pure-function semantic — model sees only (system + request msgs). Saved
    # chat history is never replayed; it exists only for the UI to render.
    ollama_messages = [{"role": "system", "content": effective["system_prompt"]}]
    ollama_messages.extend(user_msgs)

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
            existing.append({"role": m["role"], "content": m["content"], "params": snapshot})
        existing.append({"role": "assistant", "content": assistant_text, "params": snapshot})
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
        user_msgs = [{"role": "user", "content": req.message}] if req.message is not None else [m.model_dump() for m in req.messages]
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
            user_msgs = [{"role": "user", "content": req.message}] if req.message is not None else [m.model_dump() for m in req.messages]
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


# ---------- Static / UI ----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8095, reload=False)
