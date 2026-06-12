"""voice.py — HTTP client for a MiniClosedAI **voice backend** (kind='voice').

A voice backend is any FastAPI service exposing this small contract:

    GET  /health                         — {ok, asr_model, tts_model, device, voices_loaded}
    GET  /voices                         — {"en": [{id,name,gender}, ...], "es": [...]}
    POST /transcribe  (multipart audio)  — {text, language, segments?}
    POST /speak/stream (JSON)            — SSE: {chunk_b64, sample_rate} × N, then {done:true}

The reference implementation is the `miniclosedai-voice/` Docker image (a
single FastAPI app wrapping faster-whisper + MeloTTS). The *same* image works
locally (`docker run`) or on a remote GPU pod (RunPod); the only thing that
changes is the URL the user pastes into Settings → Add endpoint.

Stylistically this mirrors `llm.py` — small httpx-backed async helpers.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

# Short timeout for status / probe calls; long timeout for streaming TTS so a
# generous reply doesn't kill the connection mid-utterance.
_PROBE_TIMEOUT = httpx.Timeout(8.0, connect=5.0)
_TURN_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


def _base_url(backend: dict) -> str:
    return (backend.get("base_url") or "").rstrip("/")


def _headers(backend: dict) -> dict:
    """Apply optional Bearer auth + any custom headers the user set in Settings.

    The voice service ships with no auth by default; users who expose it to
    the public internet can set `VOICE_API_KEY` on the container, then store
    that token as the backend's `api_key` here.
    """
    h: dict = {}
    extra = backend.get("headers") or {}
    if isinstance(extra, dict):
        h.update(extra)
    key = backend.get("api_key")
    if key:
        h.setdefault("Authorization", f"Bearer {key}")
    return h


# ---------- Probe / discovery ----------------------------------------------

async def health(backend: dict) -> dict:
    """Return the /health payload. Raises httpx errors on network/HTTP failures."""
    url = f"{_base_url(backend)}/health"
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
        r = await client.get(url, headers=_headers(backend))
        r.raise_for_status()
        return r.json()


async def is_running(backend: dict) -> bool:
    """A voice service is 'running' iff /health returns {ok: true}.

    Mirrors `llm.is_running()` so the existing per-backend status pill code in
    app.py can dispatch by `kind` without caring which client it's talking to.
    """
    try:
        d = await health(backend)
        return bool(d.get("ok"))
    except Exception:
        return False


async def list_voices(backend: dict) -> dict:
    """Return /voices: {"en": [{id,name,gender}, ...], "es": [...], ...}.

    Returned to the /api/backends/{id}/models endpoint so the existing per-
    backend dropdowns and the new Voice/Language pickers can populate from one
    place.
    """
    url = f"{_base_url(backend)}/voices"
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
        r = await client.get(url, headers=_headers(backend))
        r.raise_for_status()
        return r.json()


# ---------- The two real operations ----------------------------------------

async def transcribe(
    backend: dict,
    audio: bytes,
    filename: str = "audio.wav",
    content_type: str = "audio/wav",
    language: str | None = None,
) -> dict:
    """POST /transcribe — returns {text, language, segments?}."""
    url = f"{_base_url(backend)}/transcribe"
    files = {"audio": (filename, audio, content_type)}
    data = {"language": language} if language else None
    async with httpx.AsyncClient(timeout=_TURN_TIMEOUT) as client:
        r = await client.post(url, files=files, data=data, headers=_headers(backend))
        r.raise_for_status()
        return r.json()


async def speak_stream(
    backend: dict,
    text: str,
    voice: str,
    language: str,
    speed: float | None = None,
) -> AsyncIterator[dict]:
    """POST /speak/stream — yield each SSE event as a dict, including the
    terminal `{done: true}`. Re-raises on a non-2xx response or an explicit
    `{error: ...}` frame, so the caller can surface a clean error to the UI.
    """
    url = f"{_base_url(backend)}/speak/stream"
    payload: dict = {"text": text, "voice": voice, "language": language}
    if speed is not None:
        payload["speed"] = speed
    async with httpx.AsyncClient(timeout=_TURN_TIMEOUT) as client:
        async with client.stream(
            "POST", url, json=payload,
            headers={**_headers(backend), "Accept": "text/event-stream"},
        ) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode(errors="replace")[:300]
                raise httpx.HTTPStatusError(
                    f"voice /speak/stream -> HTTP {resp.status_code}: {detail}",
                    request=resp.request, response=resp,
                )
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                # SSE frames are separated by a blank line.
                parts = buf.split("\n\n")
                buf = parts.pop()
                for part in parts:
                    line = part.strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if "error" in ev:
                        raise RuntimeError(f"voice /speak/stream error: {ev['error']}")
                    yield ev
                    if ev.get("done"):
                        return
