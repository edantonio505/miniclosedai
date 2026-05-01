"""Backend-agnostic LLM client.

Speaks two protocols:
  - Ollama's native JSON-lines API (`POST /api/chat`, `GET /api/tags`).
  - OpenAI-compatible Chat Completions API (`POST /v1/chat/completions`,
    `GET /v1/models`) — works against LM Studio, vLLM, llama.cpp server, and
    anything else that implements the OpenAI wire format.

Public surface: every function takes a `backend` dict as the first arg.
A backend dict is the serialized row from the `backends` table, namely:

    {
      "id":       int,
      "name":     str,
      "kind":     "ollama" | "openai",
      "base_url": str,                 # no trailing slash
      "api_key":  str | None,
      "headers":  dict[str, str],      # optional extra request headers
      ...                              # other columns ignored
    }

All functions yield/return the same shape regardless of `backend["kind"]`,
so callers in app.py don't need kind-specific branches.
"""
import json
import os
from typing import AsyncIterator

import httpx

# Kept for backward compat + used by db.py's built-in seed.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Model-specific end-of-turn tokens that sometimes leak into streamed output.
# GGUF quantizations on LM Studio leak the same ones Ollama does, so we reuse
# the list across both backends.
_END_TOKENS = (
    "<|eot_id|>",
    "<｜end▁of▁sentence｜>",
    "<|im_end|>",
    "<|endoftext|>",
    "<|end|>",
)


def _clean(chunk: str) -> str:
    for tok in _END_TOKENS:
        chunk = chunk.replace(tok, "")
    return chunk


# ---------- Multimodal helpers ----------
#
# Internal storage uses the OpenAI content-array shape:
#   {"role": "user", "content": [
#     {"type": "text", "text": "what's in this?"},
#     {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
#   ]}
# Plain-string content is the legacy form and still works untouched.
#
# OpenAI-compat backends accept the array form natively. Ollama's native
# /api/chat needs a different shape: {content: "<text>", images: [base64,...]}
# where each entry is the raw base64 with NO `data:image/...;base64,` prefix.
# `_to_ollama_message` performs that translation.

def _is_multimodal_content(content) -> bool:
    return isinstance(content, list)


def _content_to_text_only(content) -> str:
    """Concatenate just the text parts of a content array (or pass through a string)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for p in content:
        if isinstance(p, dict) and p.get("type") == "text":
            parts.append(p.get("text", "") or "")
    return "\n".join(parts)


def _strip_data_url_prefix(url: str) -> str:
    """Turn `data:image/png;base64,<b64>` into `<b64>`. Pass through anything else."""
    if isinstance(url, str) and url.startswith("data:") and "," in url:
        return url.split(",", 1)[1]
    return url or ""


def _to_ollama_message(m: dict) -> dict:
    """Translate an OpenAI-style multimodal message into Ollama's native shape.

    String-content messages are returned unchanged. Content-array messages get
    their text parts joined into `content` and their image_url parts collected
    into a top-level `images: [base64, ...]` array.
    """
    content = m.get("content")
    if not _is_multimodal_content(content):
        return m  # string content — Ollama already accepts it
    text_parts: list[str] = []
    images: list[str] = []
    for p in content:
        if not isinstance(p, dict):
            continue
        ptype = p.get("type")
        if ptype == "text":
            text_parts.append(p.get("text", "") or "")
        elif ptype == "image_url":
            url = ((p.get("image_url") or {}).get("url")) or ""
            b64 = _strip_data_url_prefix(url)
            if b64:
                images.append(b64)
    out = {k: v for k, v in m.items() if k not in ("content",)}
    out["content"] = "\n".join(text_parts)
    if images:
        out["images"] = images
    return out


def _append_think_hint(messages: list[dict], hint: str) -> list[dict]:
    """Return a copy of `messages` with Qwen3's /think or /no_think hint appended.

    Qwen3's chat template scans the final user message (and the system message
    for /no_think) for the magic token and toggles reasoning accordingly. This
    is the client-side fallback for servers that don't honor
    `chat_template_kwargs.enable_thinking`.

    Handles both string-content messages and OpenAI-style content-array
    messages — for the latter we append the hint to the last text part (or
    add a new text part if the message is image-only).
    """
    if not messages:
        return messages
    out = [dict(m) for m in messages]
    # Append to the last user message; that's the spot Qwen3 looks first.
    for m in reversed(out):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, list):
                # Find the last text part (or append one) and tack the hint on.
                parts = [dict(p) if isinstance(p, dict) else p for p in content]
                text_idx = next(
                    (i for i in range(len(parts) - 1, -1, -1)
                     if isinstance(parts[i], dict) and parts[i].get("type") == "text"),
                    -1,
                )
                if text_idx >= 0:
                    txt = parts[text_idx].get("text", "") or ""
                    if hint not in txt:
                        parts[text_idx]["text"] = txt.rstrip() + "\n\n" + hint
                else:
                    parts.append({"type": "text", "text": hint})
                m["content"] = parts
            else:
                content = content or ""
                if hint not in content:
                    m["content"] = content.rstrip() + "\n\n" + hint
            return out
    # Fallback: no user message in the list — append to system.
    for m in out:
        if m.get("role") == "system":
            content = m.get("content", "") or ""
            if hint not in content:
                m["content"] = content.rstrip() + "\n\n" + hint
            return out
    return out


def _base_url(backend: dict) -> str:
    return (backend.get("base_url") or "").rstrip("/")


def _openai_headers(backend: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    # Merge any user-supplied headers first, then our defaults take precedence
    # for essentials (so nobody accidentally overwrites Content-Type).
    for k, v in (backend.get("headers") or {}).items():
        headers[k] = v
    headers["Content-Type"] = "application/json"
    if backend.get("api_key"):
        headers["Authorization"] = f"Bearer {backend['api_key']}"
    return headers


def _ollama_headers(backend: dict) -> dict:
    """Same shape as `_openai_headers`, but for the Ollama-native path.

    A bare local Ollama at localhost:11434 has no auth and `headers={}` is the
    norm. When users register a remote/relayed Ollama (e.g. a public IP gated
    by Bearer auth), this helper merges the backend's `api_key` (sent as
    Bearer) and `headers` dict so /api/tags, /api/chat, and /api/pull all
    carry the same credentials. Local-only setups are unaffected — without an
    api_key, no Authorization header is added.
    """
    headers = {"Content-Type": "application/json"}
    for k, v in (backend.get("headers") or {}).items():
        headers[k] = v
    headers["Content-Type"] = "application/json"
    if backend.get("api_key"):
        headers["Authorization"] = f"Bearer {backend['api_key']}"
    return headers


# =====================================================================
# Ollama implementation
# =====================================================================

async def _ollama_is_running(backend: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"{_base_url(backend)}/api/tags",
                headers=_ollama_headers(backend),
            )
            # 401/403 → server is alive, our auth was rejected. Still "running"
            # so the UI can surface a meaningful error rather than a generic
            # "backend offline" message.
            return r.status_code in (200, 401, 403)
    except Exception:
        return False


async def _ollama_list_models(backend: dict) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_base_url(backend)}/api/tags",
                headers=_ollama_headers(backend),
            )
            r.raise_for_status()
            return r.json().get("models", []) or []
    except Exception:
        return []


async def pull_ollama_model(backend: dict, name: str) -> AsyncIterator[dict]:
    """Stream Ollama's `/api/pull` progress events for a model name.

    Yields the raw JSON-line dicts: `{status, digest?, total?, completed?}`,
    and a final `{status: "success"}` when done. Caller is responsible for
    interpreting / persisting them. Raises if the backend isn't Ollama.
    """
    if backend.get("kind") != "ollama":
        raise ValueError("pull is only supported on Ollama backends")
    payload = {"name": name, "stream": True}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST", f"{_base_url(backend)}/api/pull",
            json=payload,
            headers=_ollama_headers(backend),
        ) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{backend.get('name', 'Ollama')} returned {r.status_code}: {body[:400]}"
                )
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("error"):
                    raise RuntimeError(str(data["error"]))
                yield data


async def _ollama_chat_stream(
    backend: dict,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    top_k: int,
    think: bool | str | None,
) -> AsyncIterator[dict]:
    # Translate any OpenAI-style content-array messages (multimodal) into
    # Ollama's native {content, images:[base64,...]} shape. String-content
    # messages pass through unchanged.
    messages = [_to_ollama_message(m) for m in messages]
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "top_p": top_p,
            "top_k": top_k,
        },
    }
    if think is not None:
        payload["think"] = think
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{_base_url(backend)}/api/chat",
            json=payload,
            headers=_ollama_headers(backend),
        ) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{backend.get('name', 'Ollama')} returned {r.status_code}: {body[:400]}"
                )
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = data.get("message", {})
                thinking = msg.get("thinking", "")
                content = msg.get("content", "")
                if thinking:
                    yield {"thinking": _clean(thinking)}
                if content:
                    yield {"content": _clean(content)}
                if data.get("done"):
                    return


# =====================================================================
# OpenAI-compatible implementation
# =====================================================================

async def _openai_is_running(backend: dict) -> bool:
    """Probe the OpenAI-compat server at {base_url}/models.

    Strict: only 2xx or 401/403 (auth failure — server exists, just rejecting
    us) count as "running". 404 or similar means the URL is wrong — surface
    that as unreachable so the user knows to check the path (often a missing
    `/v1` suffix).
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"{_base_url(backend)}/models", headers=_openai_headers(backend)
            )
            if r.status_code in (200, 401, 403):
                return True
            return False
    except Exception:
        return False


async def _openai_list_models(backend: dict) -> list[dict]:
    """Map OpenAI `/v1/models` into Ollama-ish `{name, size, details}` shape.

    Frontend's loadAggregatedModels() expects the same shape across backends,
    so Ollama-side doesn't need a branch.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_base_url(backend)}/models", headers=_openai_headers(backend)
            )
            r.raise_for_status()
            data = (r.json() or {}).get("data", []) or []
            return [
                {
                    "name": m.get("id", ""),
                    "size": 0,  # OpenAI-compat servers don't expose size
                    "details": {
                        "family": m.get("owned_by", "") or "",
                        "quantization_level": "",
                    },
                }
                for m in data
                if m.get("id")
            ]
    except Exception:
        return []


async def _openai_chat_stream(
    backend: dict,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
    top_k: int,           # noqa: ARG001 — not in OpenAI schema, intentionally dropped
    think: bool | str | None,
) -> AsyncIterator[dict]:
    """Translate an OpenAI-compat SSE stream into our {"content"}/{"thinking"} event dicts.

    Handles:
      * Keepalive / `[DONE]` / `data:` framing quirks.
      * Reasoning-token detection across vLLM / LM Studio variants
        (`delta.reasoning_content`, `delta.reasoning`, `delta.thinking`).
      * `think` → server-side reasoning control:
          - False / "off"    → chat_template_kwargs.enable_thinking = false
                               (Qwen3 family; LM Studio and vLLM pass it through)
          - True / "on"      → chat_template_kwargs.enable_thinking = true
          - "low"/"medium"/"high" → reasoning_effort (gpt-oss family)
        Backends that don't recognize these fields will typically ignore them;
        some strict servers may 4xx — tough call, but it's correct to forward.
      * `top_k` is dropped (not in OpenAI schema).
    """
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "top_p": top_p,
    }
    # max_tokens: some servers treat negative as unlimited; pass through as-is.
    if max_tokens and max_tokens > 0:
        payload["max_tokens"] = max_tokens

    # Reasoning control for OpenAI-compat servers. Three dialects are in use:
    #   chat_template_kwargs.enable_thinking → Qwen3 family on vLLM / LM Studio
    #                                          (the server-side switch)
    #   /no_think or /think in the prompt    → Qwen3 chat-template magic token
    #                                          (the client-side fallback — works
    #                                          regardless of server version)
    #   reasoning_effort                     → gpt-oss family
    #
    # We send BOTH Qwen3 signals when Thinking: Off, because some LM Studio
    # builds honor the server-side switch and some only honor the prompt
    # magic. Models that don't recognize either just ignore them.
    if think is True or think == "on":
        payload.setdefault("chat_template_kwargs", {})["enable_thinking"] = True
        messages = _append_think_hint(messages, "/think")
    elif think is False or think == "off":
        payload.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
        messages = _append_think_hint(messages, "/no_think")
    elif isinstance(think, str) and think in ("low", "medium", "high"):
        payload["reasoning_effort"] = think

    # Swap in the possibly-modified copy.
    payload["messages"] = messages

    headers = _openai_headers(backend)

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{_base_url(backend)}/chat/completions",
            json=payload,
            headers=headers,
        ) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{backend.get('name', 'OpenAI-compat backend')} returned {r.status_code}: {body[:400]}"
                )

            async for raw in r.aiter_lines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith(":"):  # SSE keepalive comment
                    continue
                if not line.startswith("data:"):
                    continue
                payload_str = line[5:].strip()
                if payload_str == "[DONE]":
                    return
                try:
                    data = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue

                # Inline error frame (some servers emit this instead of HTTP error).
                if "error" in data and not data.get("choices"):
                    err = data["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    raise RuntimeError(msg or "backend error")

                for choice in data.get("choices", []) or []:
                    delta = choice.get("delta") or {}
                    # Non-standard reasoning fields — check all three variants.
                    thinking = (
                        delta.get("reasoning_content")
                        or delta.get("reasoning")
                        or delta.get("thinking")
                        or ""
                    )
                    content = delta.get("content") or ""
                    if thinking:
                        yield {"thinking": _clean(thinking)}
                    if content:
                        yield {"content": _clean(content)}


# =====================================================================
# Dispatch
# =====================================================================

_IMPLS = {
    "ollama": {
        "is_running": _ollama_is_running,
        "list_models": _ollama_list_models,
        "chat_stream": _ollama_chat_stream,
    },
    "openai": {
        "is_running": _openai_is_running,
        "list_models": _openai_list_models,
        "chat_stream": _openai_chat_stream,
    },
}


def _impl(backend: dict) -> dict:
    kind = backend.get("kind")
    if kind not in _IMPLS:
        raise ValueError(f"Unknown backend kind: {kind!r}")
    return _IMPLS[kind]


# =====================================================================
# Public API (kind-agnostic; dispatches internally)
# =====================================================================

async def is_running(backend: dict) -> bool:
    """Return True if the backend responds to a lightweight probe."""
    return await _impl(backend)["is_running"](backend)


async def list_models(backend: dict) -> list[dict]:
    """Return models available on the backend.

    Always returns the Ollama-shaped list `[{name, size, details}]`, regardless
    of kind, so the frontend's grouped-dropdown builder has one format to parse.
    """
    return await _impl(backend)["list_models"](backend)


async def chat_stream(
    backend: dict,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    top_p: float = 0.9,
    top_k: int = 40,
    think: bool | str | None = None,
) -> AsyncIterator[dict]:
    """Stream assistant turns from the given backend.

    Yields event dicts, each with exactly one of:
      - {"content": str}  — visible assistant output
      - {"thinking": str} — reasoning tokens (qwen3/qwen3.5, deepseek-r1,
                             gpt-oss; or vLLM/LM-Studio reasoning variants)

    `think` controls Ollama reasoning-capable models. For OpenAI-compat
    backends it is silently ignored (no standardized field yet).
    """
    async for ev in _impl(backend)["chat_stream"](
        backend, model, messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        top_k=top_k,
        think=think,
    ):
        yield ev


async def chat(backend: dict, model: str, messages: list[dict], **params) -> str:
    """Non-streaming helper — concatenates visible content (drops thinking)."""
    parts: list[str] = []
    async for ev in chat_stream(backend, model, messages, **params):
        if "content" in ev:
            parts.append(ev["content"])
    return "".join(parts)
