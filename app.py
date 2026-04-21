"""MiniClosedAI — FastAPI app exposing a minimal Ollama playground."""
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

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
    """Body for POST /api/conversations/{id}/chat.

    The bot's config (model, system prompt, sampling params, thinking level) is
    locked to what the GUI saved. API callers only supply the conversation
    content — everything else is rejected.
    """
    model_config = ConfigDict(extra="forbid")

    message: str | None = None
    messages: list[Message] | None = None
    persist: bool = False  # save this turn to the conversation's display log


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

    # Config is locked to whatever the GUI saved. No per-request overrides.
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

    # Build the message list to send to Ollama.
    if req.message is not None:
        user_msgs = [{"role": "user", "content": req.message}]
    else:
        user_msgs = [m.model_dump() for m in req.messages]

    # Pure-function semantic: the model sees ONLY the saved system prompt
    # + saved params + the messages supplied in this request. Saved chat
    # history is never replayed — it exists only for the UI to render.
    # Callers that want multi-turn context must pass the full `messages`
    # array themselves.
    ollama_messages = [{"role": "system", "content": effective["system_prompt"]}]
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


# ---------- OpenAI-compatible endpoint ----------
# Lets any OpenAI SDK (Python `openai`, `@openai/openai`, etc.) talk to this
# app by setting base_url to http://<host>:8095/v1 and using the conversation
# ID as the `model` field. The bot's GUI-saved config (system prompt, model,
# sampling params) is the source of truth — any caller-supplied temperature,
# max_tokens, etc. are tolerated but ignored, matching the native endpoint.

class OAIMessage(BaseModel):
    role: str
    content: str


class OAICompletionRequest(BaseModel):
    """Minimal OpenAI /v1/chat/completions request shape.

    `extra="allow"` lets us tolerate fields we don't use (temperature, top_p,
    presence_penalty, logit_bias, response_format, …) without failing the
    request. Those fields are silently ignored — the bot config is locked.
    """
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[OAIMessage]
    stream: bool = False


def _conv_id_from_openai_model(model_field: str) -> int:
    """Accept the `model` field in any of: "12", "conv-12", "bot-12", "miniclosed/12"."""
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

    saved = conv.get("params", {}) or {}
    effective = {
        "model": conv["model"],
        "temperature": saved.get("temperature", 0.7),
        "max_tokens": saved.get("max_tokens", 2048),
        "top_p": saved.get("top_p", 0.9),
        "top_k": saved.get("top_k", 40),
        "think": saved.get("think"),
    }

    # Bot's system prompt wins. Drop any system messages the caller sent.
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
                    effective["model"], ollama_messages,
                    temperature=effective["temperature"], max_tokens=effective["max_tokens"],
                    top_p=effective["top_p"], top_k=effective["top_k"],
                    think=effective["think"],
                ):
                    if "content" not in ev:
                        continue
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": effective["model"],
                        "choices": [{
                            "index": 0,
                            "delta": {"content": ev["content"]} if not sent_any
                                     else {"content": ev["content"]},
                            "finish_reason": None,
                        }],
                    }
                    # First chunk conventionally also sets role:"assistant" in delta.
                    if not sent_any:
                        chunk["choices"][0]["delta"]["role"] = "assistant"
                    sent_any = True
                    yield f"data: {json.dumps(chunk)}\n\n"
            except httpx.ConnectError:
                err = {"error": {"message": "Cannot connect to Ollama at localhost:11434",
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
            effective["model"], ollama_messages,
            temperature=effective["temperature"], max_tokens=effective["max_tokens"],
            top_p=effective["top_p"], top_k=effective["top_k"],
            think=effective["think"],
        )
    except httpx.ConnectError:
        raise HTTPException(503, "Cannot connect to Ollama at localhost:11434")
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
            "SELECT id, title, model, created_at FROM conversations ORDER BY id"
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
