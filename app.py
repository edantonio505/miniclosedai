"""MiniClosedAI — FastAPI app exposing a minimal Ollama playground."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import llm

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="MiniClosedAI", version="0.1.0", lifespan=lifespan)


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


class ConversationChatRequest(BaseModel):
    """Body for POST /api/conversations/{id}/chat — each chat acts like a saved API function."""
    message: str | None = None
    messages: list[Message] | None = None
    # Optional overrides of the saved conversation config:
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=32000)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    top_k: int | None = Field(None, ge=1, le=500)
    think: ThinkValue = None
    max_thinking_tokens: int | None = Field(None, ge=1, le=100000)
    persist: bool = False  # append this turn to the saved conversation history


# ---------- Models (Ollama) ----------

@app.get("/api/models")
async def api_models():
    running = await llm.is_running()
    models = await llm.list_models() if running else []
    return {"ollama_running": running, "models": models}


# ---------- Conversations ----------

@app.get("/api/conversations")
def api_list_conversations():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, model, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


_PARAM_KEYS = ("temperature", "max_tokens", "top_p", "top_k", "think", "max_thinking_tokens")


@app.post("/api/conversations")
def api_create_conversation(data: ConversationCreate):
    params = {k: getattr(data, k) for k in _PARAM_KEYS}
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (title, model, system_prompt, params) VALUES (?, ?, ?, ?)",
            (data.title, data.model, data.system_prompt, json.dumps(params)),
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
    supplied = data.model_dump(exclude_none=True)
    fields, values = [], []
    # Plain columns:
    for col in ("title", "model", "system_prompt"):
        if col in supplied:
            fields.append(f"{col} = ?")
            values.append(supplied[col])
    # Param overrides: merge into the params JSON column.
    param_updates = {k: supplied[k] for k in _PARAM_KEYS if k in supplied}
    with db.get_conn() as conn:
        if param_updates:
            row = conn.execute(
                "SELECT params FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Conversation not found")
            merged = json.loads(row["params"] or "{}")
            merged.update(param_updates)
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
    """Wipe messages for this conversation, keep its config (model, system prompt, params)."""
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE conversations SET messages = '[]', updated_at = datetime('now') WHERE id = ?",
            (conv_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
    return {"ok": True}


# ---------- Chat ----------

def _build_messages(req: ChatRequest) -> list[dict]:
    msgs = [{"role": "system", "content": req.system_prompt}]
    msgs.extend(m.model_dump() for m in req.messages)
    return msgs


def _persist_turn(req: ChatRequest, assistant_text: str) -> None:
    """Append the latest user turn + assistant reply (with param snapshot) to the conversation."""
    if not req.conversation_id or not req.messages:
        return
    last_user = req.messages[-1]
    params = {
        "model": req.model,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "think": req.think,
    }
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE id = ?", (req.conversation_id,)
        ).fetchone()
        if not row:
            return
        existing = json.loads(row["messages"] or "[]")
        existing.append({"role": last_user.role, "content": last_user.content, "params": params})
        existing.append({"role": "assistant", "content": assistant_text, "params": params})
        conn.execute(
            "UPDATE conversations SET messages = ?, model = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing), req.model, req.conversation_id),
        )
        conn.commit()


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    try:
        text = await llm.chat(
            req.model,
            _build_messages(req),
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            top_p=req.top_p,
            top_k=req.top_k,
            think=req.think,
        )
    except httpx.ConnectError:
        raise HTTPException(503, "Cannot connect to Ollama at localhost:11434")
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    _persist_turn(req, text)
    return {"response": text}


def _resolve_conversation_chat(conv_id: int, req: ConversationChatRequest) -> tuple[dict, list[dict], dict]:
    """Load the conversation, merge request overrides with saved config, build the messages list.

    Returns (conv_row_dict, ollama_messages, effective_params).
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

    # Resolve effective config: request overrides win, else conversation saved values, else defaults.
    saved = conv.get("params", {}) or {}
    effective = {
        "model": req.model or conv["model"],
        "system_prompt": req.system_prompt if req.system_prompt is not None else conv["system_prompt"],
        "temperature": req.temperature if req.temperature is not None else saved.get("temperature", 0.7),
        "max_tokens": req.max_tokens if req.max_tokens is not None else saved.get("max_tokens", 2048),
        "top_p": req.top_p if req.top_p is not None else saved.get("top_p", 0.9),
        "top_k": req.top_k if req.top_k is not None else saved.get("top_k", 40),
        "think": req.think if req.think is not None else saved.get("think"),
        "max_thinking_tokens": req.max_thinking_tokens if req.max_thinking_tokens is not None else saved.get("max_thinking_tokens"),
    }

    # Build the message list to send to Ollama.
    if req.message is not None:
        user_msgs = [{"role": "user", "content": req.message}]
    else:
        user_msgs = [m.model_dump() for m in req.messages]

    ollama_messages = [{"role": "system", "content": effective["system_prompt"]}]
    # If persisting, include prior conversation history for context.
    if req.persist:
        for m in conv.get("messages", []):
            if m.get("role") in ("user", "assistant"):
                ollama_messages.append({"role": m["role"], "content": m["content"]})
    ollama_messages.extend(user_msgs)

    return conv, ollama_messages, effective


def _persist_conv_chat_turn(conv_id: int, user_msgs: list[dict], assistant_text: str, effective: dict) -> None:
    params = {k: effective[k] for k in _PARAM_KEYS}
    snapshot = {**params, "model": effective["model"]}
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
    conv, messages, eff = _resolve_conversation_chat(conv_id, req)
    try:
        text = await llm.chat(
            eff["model"], messages,
            temperature=eff["temperature"], max_tokens=eff["max_tokens"],
            top_p=eff["top_p"], top_k=eff["top_k"],
            think=eff["think"],
        )
    except httpx.ConnectError:
        raise HTTPException(503, "Cannot connect to Ollama at localhost:11434")
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    if req.persist:
        user_msgs = [{"role": "user", "content": req.message}] if req.message is not None else [m.model_dump() for m in req.messages]
        _persist_conv_chat_turn(conv_id, user_msgs, text, eff)

    return {
        "response": text,
        "conversation_id": conv_id,
        "model": eff["model"],
        "persisted": req.persist,
    }


@app.post("/api/conversations/{conv_id}/chat/stream")
async def api_conv_chat_stream(conv_id: int, req: ConversationChatRequest):
    """Call the saved conversation as a configured function (SSE streaming)."""
    conv, messages, eff = _resolve_conversation_chat(conv_id, req)

    async def event_stream():
        collected: list[str] = []
        think_count = 0
        max_think = eff.get("max_thinking_tokens")
        truncated = False
        try:
            async for ev in llm.chat_stream(
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
                        truncated = True
                        yield f"data: {json.dumps({'thinking_truncated': True, 'reason': 'max_thinking_tokens', 'limit': max_think})}\n\n"
                        break  # closes Ollama stream → stops generation
                    yield f"data: {json.dumps({'thinking': ev['thinking']})}\n\n"
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'Cannot connect to Ollama at localhost:11434. Is `ollama serve` running?'})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        if req.persist and not truncated:
            user_msgs = [{"role": "user", "content": req.message}] if req.message is not None else [m.model_dump() for m in req.messages]
            _persist_conv_chat_turn(conv_id, user_msgs, "".join(collected), eff)

        yield f"data: {json.dumps({'end': True, 'truncated': truncated})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest):
    messages = _build_messages(req)

    async def event_stream():
        collected: list[str] = []
        think_count = 0
        max_think = req.max_thinking_tokens
        truncated = False
        try:
            async for ev in llm.chat_stream(
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
                        truncated = True
                        yield f"data: {json.dumps({'thinking_truncated': True, 'reason': 'max_thinking_tokens', 'limit': max_think})}\n\n"
                        break
                    yield f"data: {json.dumps({'thinking': ev['thinking']})}\n\n"
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'Cannot connect to Ollama at localhost:11434. Is `ollama serve` running?'})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        if not truncated:
            _persist_turn(req, "".join(collected))
        yield f"data: {json.dumps({'end': True, 'truncated': truncated})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Static / UI ----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8095, reload=False)
