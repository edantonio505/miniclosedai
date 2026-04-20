"""Ollama client. Speaks HTTP directly to http://localhost:11434."""
import json
import os
from typing import AsyncIterator

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Model-specific end-of-turn tokens that sometimes leak into streamed output.
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


async def is_running() -> bool:
    """Return True if Ollama responds on its HTTP port."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def list_models() -> list[dict]:
    """Return models installed in the local Ollama daemon."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            return r.json().get("models", [])
    except Exception:
        return []


async def chat_stream(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    top_p: float = 0.9,
    top_k: int = 40,
    think: bool | str | None = None,
) -> AsyncIterator[dict]:
    """Yield events from Ollama's streaming chat endpoint.

    Each yielded dict has exactly one of:
      - {"content": str}  — visible assistant output
      - {"thinking": str} — reasoning tokens (qwen3.5, deepseek-r1, etc.)

    `think` controls reasoning-capable models:
      - None      → don't send the field (use model default)
      - True/False → enable/disable thinking
      - "low"/"medium"/"high" → effort levels (gpt-oss, etc.)
    Unsupported values are ignored by Ollama for models that don't support reasoning.
    """
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
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", errors="replace")
                raise RuntimeError(f"Ollama returned {r.status_code}: {body[:400]}")
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


async def chat(model: str, messages: list[dict], **params) -> str:
    """Non-streaming helper — concatenates only visible content (drops thinking)."""
    parts: list[str] = []
    async for ev in chat_stream(model, messages, **params):
        if "content" in ev:
            parts.append(ev["content"])
    return "".join(parts)
