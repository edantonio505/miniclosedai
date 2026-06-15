"""In-memory request/response log buffer for the LLM activity viewer.

Mirrors LM Studio's "Server logs" panel — every chat call records one entry
(request metadata + first chunks of response). A fixed-size deque (500 entries)
keeps memory bounded; old entries fall off automatically. Reset on server
restart by design: this is a debugging surface, not an audit log.

Single public function `record_chat(...)` collects the data. `get_all()` and
`clear()` back the `GET /api/logs` and `DELETE /api/logs` endpoints. All access
serialized by a single `threading.Lock` since FastAPI may dispatch handlers
from worker threads on sync routes.
"""
from __future__ import annotations

import itertools
from collections import deque
from datetime import datetime, timezone
from threading import Lock

_MAX_ENTRIES = 200            # smaller now that each entry stores full content
_RESPONSE_PREVIEW_CHARS = 2000
_THINKING_PREVIEW_CHARS = 1000
_PER_MESSAGE_PREVIEW = 500
_MESSAGES_TAIL = 3   # only the last N turns get included in the preview list view
# Full-content cap to avoid blowing memory on a runaway response. Plenty for
# normal chats; truncations are flagged on the entry so the export shows it.
_FULL_RESPONSE_CAP = 200_000

_buffer: deque[dict] = deque(maxlen=_MAX_ENTRIES)
_lock = Lock()
_counter = itertools.count(1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str | None, limit: int) -> tuple[str, bool]:
    if not text:
        return "", False
    if len(text) <= limit:
        return text, False
    return text[:limit] + "…", True


def _summarize_messages(messages: list[dict]) -> list[dict]:
    """Compact preview of the LLM-bound message list.

    Only the last `_MESSAGES_TAIL` turns are kept; each is reduced to
    `{role, content_preview}` where content is either:

    - **Plain string**: truncated to `_PER_MESSAGE_PREVIEW` chars.
    - **Content array (multimodal)**: text parts joined and truncated,
      plus a `[+N image(s)]` suffix when image parts are present so the
      log shows attachment volume without bloating with base64 payloads.
    """
    out: list[dict] = []
    for m in messages[-_MESSAGES_TAIL:]:
        content = m.get("content")
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
            image_count = sum(1 for p in content if p.get("type") == "image_url")
            preview = " ".join(text_parts)[:_PER_MESSAGE_PREVIEW]
            if image_count:
                preview = f"{preview}  [+{image_count} image(s)]"
        else:
            preview = (content or "")[:_PER_MESSAGE_PREVIEW]
        out.append({"role": m.get("role"), "content_preview": preview})
    return out


def record_chat(
    *,
    endpoint: str,
    kind: str,                       # "sync" | "stream"
    backend: dict,
    model: str,
    messages: list[dict],
    params: dict,
    response_text: str | None = None,
    thinking_text: str | None = None,
    status: str = "ok",              # "ok" | "error"
    error: str | None = None,
    latency_ms: int | None = None,
    attachments: list[str] | None = None,
) -> None:
    """Append a single chat record.

    Safe to call from any thread or async context — internal access is
    serialized. Callers should invoke this exactly once per LLM call (on
    success after the response is fully consumed, or in an exception handler
    on failure). The function never raises.
    """
    try:
        resp_preview, resp_truncated = _truncate(response_text, _RESPONSE_PREVIEW_CHARS)
        think_preview, think_truncated = _truncate(thinking_text, _THINKING_PREVIEW_CHARS)
        # Full content for the Export button — capped only by _FULL_RESPONSE_CAP.
        # The list view still uses the truncated `messages` / `response.preview`
        # fields so polling /api/logs stays cheap.
        full_resp = (response_text or "")[:_FULL_RESPONSE_CAP]
        full_think = (thinking_text or "")[:_FULL_RESPONSE_CAP] if thinking_text else None
        entry = {
            "id": next(_counter),
            "ts": _now_iso(),
            "endpoint": endpoint,
            "kind": kind,
            "backend_id": backend.get("id") if backend else None,
            "backend_name": backend.get("name") if backend else None,
            "backend_kind": backend.get("kind") if backend else None,
            "model": model,
            "params": params or {},
            "messages": _summarize_messages(messages or []),
            "attachments": attachments or [],
            "response": {
                "preview": resp_preview,
                "truncated": resp_truncated,
                "char_count": len(response_text or ""),
            },
            "thinking": ({
                "preview": think_preview,
                "truncated": think_truncated,
                "char_count": len(thinking_text or ""),
            }) if thinking_text else None,
            "status": status,
            "error": error,
            "latency_ms": latency_ms,
            # Full payload for export. Not surfaced by /api/logs (the polling
            # list endpoint) to keep that response small.
            "_full": {
                "messages": messages or [],
                "response_text": full_resp,
                "thinking_text": full_think,
            },
        }
        with _lock:
            _buffer.append(entry)
    except Exception:
        # Logging itself must never break a request. Swallow silently so a
        # malformed payload here (unexpected type, etc.) doesn't 500 the chat.
        pass


def get_all() -> list[dict]:
    """Newest-first snapshot for the polling list view. Strips the heavy
    `_full` payload to keep the response small — use `get_all_full()` for the
    export endpoint instead."""
    with _lock:
        return [{k: v for k, v in e.items() if k != "_full"} for e in reversed(_buffer)]


def get_all_full() -> list[dict]:
    """Newest-first snapshot with the full request messages + full response
    text inlined. Used by `GET /api/logs/export`."""
    with _lock:
        return [
            {**{k: v for k, v in e.items() if k != "_full"},
             "request_messages": e.get("_full", {}).get("messages", []),
             "response_text": e.get("_full", {}).get("response_text", ""),
             "thinking_text": e.get("_full", {}).get("thinking_text"),
             }
            for e in reversed(_buffer)
        ]


def clear() -> None:
    with _lock:
        _buffer.clear()
