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

# Every httpx.AsyncClient below is built with `verify=False`. A voice backend
# is, by design, a user-registered LAN endpoint — usually the sibling
# miniclosedai-voice service over a self-signed dev cert (start.sh generates
# one in .devcerts/ on first run). The browser's getUserMedia API forces the
# voice service onto HTTPS, but its dev cert isn't in the system trust store,
# so a default httpx call would fail with SSL: CERTIFICATE_VERIFY_FAILED.
# `verify=False` is the correct default here — the user already told us this
# URL is trusted by registering it in Settings.

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
    async with httpx.AsyncClient(verify=False, timeout=_PROBE_TIMEOUT) as client:
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
    async with httpx.AsyncClient(verify=False, timeout=_PROBE_TIMEOUT) as client:
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
    async with httpx.AsyncClient(verify=False, timeout=_TURN_TIMEOUT) as client:
        r = await client.post(url, files=files, data=data, headers=_headers(backend))
        r.raise_for_status()
        return r.json()


# ---------- Call mode signaling proxy ---------------------------------------
#
# Browser ↔ MiniClosedAI is HTTPS (so the mic API is available); but the voice
# container runs on plain HTTP. Browsers block cross-origin HTTPS→HTTP fetches
# (mixed content), so MiniClosedAI proxies the three signaling endpoints so
# the browser only talks to one origin.
#
# The actual WebRTC audio (RTP/UDP) does NOT go through this proxy — once the
# SDP exchange + ICE happens, the browser and the voice container have each
# other's ICE candidates and the media flows direct peer-to-peer. So only the
# small JSON/SSE traffic is proxied.


async def call_configure(backend: dict, payload: dict) -> dict:
    """POST /call/configure on the voice backend; return the JSON response."""
    url = f"{_base_url(backend)}/call/configure"
    async with httpx.AsyncClient(verify=False, timeout=_PROBE_TIMEOUT) as client:
        r = await client.post(url, json=payload, headers=_headers(backend))
        r.raise_for_status()
        return r.json()


async def call_offer(backend: dict, payload: dict) -> dict:
    """POST /webrtc/offer (FastRTC's signaling endpoint) and return the SDP
    answer JSON. The actual media stream is negotiated via ICE candidates
    inside this SDP — once exchanged, audio flows direct browser↔voice, NOT
    through MiniClosedAI."""
    url = f"{_base_url(backend)}/webrtc/offer"
    async with httpx.AsyncClient(verify=False, timeout=_PROBE_TIMEOUT) as client:
        r = await client.post(url, json=payload, headers=_headers(backend))
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"voice /webrtc/offer -> HTTP {r.status_code}: "
                f"{r.text[:200]}",
                request=r.request, response=r,
            )
        return r.json()


async def push_turn(backend: dict, turn_id: str, lines) -> None:
    """Relay-mode egress: stream the LLM reply to the voice service.

    `lines` is an async iterator of newline-terminated JSON byte strings
    ({"chunk": ...} × N then {"end": true}, or {"error": ...}); they're sent
    incrementally over ONE chunked POST to /call/turn/{turn_id}, so the voice
    server's TTS starts on the first sentence while later tokens are still
    being generated. Raises httpx errors on failure (404 = turn expired)."""
    url = f"{_base_url(backend)}/call/turn/{turn_id}"
    async with httpx.AsyncClient(
        verify=False, timeout=httpx.Timeout(300.0, connect=10.0),
    ) as client:
        r = await client.post(
            url, content=lines,
            headers={**_headers(backend), "Content-Type": "application/x-ndjson"},
        )
        r.raise_for_status()


async def call_events(backend: dict, webrtc_id: str) -> AsyncIterator[dict]:
    """Stream the voice service's /call/events/{webrtc_id} SSE. Yields each
    parsed event dict (the per-stage status / transcript / chunk / end / error
    messages the call handler emits via AdditionalOutputs)."""
    url = f"{_base_url(backend)}/call/events/{webrtc_id}"
    async with httpx.AsyncClient(verify=False, timeout=_TURN_TIMEOUT) as client:
        async with client.stream(
            "GET", url,
            headers={**_headers(backend), "Accept": "text/event-stream"},
        ) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode(errors="replace")[:300]
                raise httpx.HTTPStatusError(
                    f"voice /call/events -> HTTP {resp.status_code}: {detail}",
                    request=resp.request, response=resp,
                )
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                parts = buf.split("\n\n")
                buf = parts.pop()
                for part in parts:
                    line = part.strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        yield json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue


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
    async with httpx.AsyncClient(verify=False, timeout=_TURN_TIMEOUT) as client:
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
