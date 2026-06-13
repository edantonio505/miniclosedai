"""server.py — MiniClosedAI voice service.

A small FastAPI app that wraps **faster-whisper** (ASR) + **Piper** (TTS)
behind the six-endpoint contract MiniClosedAI's voice client expects:

    GET  /health         — {ok, asr_model, tts_model, device, voices_loaded}
    GET  /voices         — {"en": [{id,name,gender}, ...], "es": [...]}
    POST /transcribe     — multipart audio → {text, language, segments}
    POST /speak          — JSON → audio/wav body (one-shot)
    POST /speak/stream   — JSON → SSE {chunk_b64, sample_rate} × N, then {done:true}
    POST /call/configure — JSON → set per-call config (conv_id, miniclosedai_url, …)
    POST /webrtc/offer   — SDP offer (mounted by FastRTC) → SDP answer; live duplex audio

The same image runs locally (`docker run`) or on a remote GPU pod (RunPod).
The user wires it into MiniClosedAI through Settings → Add endpoint with the
service's URL; no compose-level coupling, no shared filesystem.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
from pathlib import Path

# WebRTC debugging — surface ICE state changes, peer connection lifecycle,
# and the handler's transcript / chunk events. Without this, fastrtc's
# default uvicorn config swallows every log below WARNING, so a stuck call
# looks identical to a working one from the outside.
logging.basicConfig(level=logging.INFO)
for name in ("aiortc", "aioice", "fastrtc", "voice.call"):
    logging.getLogger(name).setLevel(logging.DEBUG)

import numpy as np
import soundfile as sf
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from asr import ASR
from tts import TTS, VOICE_CATALOG
from call import BotCallHandler

# ---------------------------------------------------------------------------
# Config (env vars)
# ---------------------------------------------------------------------------
ASR_MODEL = os.environ.get("VOICE_ASR_MODEL", "small")
TTS_VOICES_DIR = Path(os.environ.get("VOICE_VOICES_DIR", "/voices"))
DEVICE = os.environ.get("VOICE_DEVICE", "auto")
API_KEY = os.environ.get("VOICE_API_KEY", "").strip()
PORT = int(os.environ.get("VOICE_PORT", "8090"))

# ---------------------------------------------------------------------------
# Lazy model loading
# ---------------------------------------------------------------------------
# The whisper model is ~500MB on disk; loading it adds a few seconds to the
# first request. We defer that work past container start so /health returns
# fast and Docker's healthcheck succeeds before models finish loading.
_asr: ASR | None = None
_tts: TTS | None = None
_load_lock = asyncio.Lock()


async def _get_asr() -> ASR:
    global _asr
    if _asr is None:
        async with _load_lock:
            if _asr is None:
                _asr = await asyncio.to_thread(ASR, ASR_MODEL, DEVICE)
    return _asr


async def _get_tts() -> TTS:
    global _tts
    if _tts is None:
        async with _load_lock:
            if _tts is None:
                _tts = TTS(voices_dir=TTS_VOICES_DIR, use_cuda=(DEVICE == "cuda"))
    return _tts


# ---------------------------------------------------------------------------
# Auth — optional Bearer token
# ---------------------------------------------------------------------------
def _require_auth(authorization: str | None = Header(None)) -> None:
    """If `VOICE_API_KEY` is set in the env, require a matching Bearer token."""
    if not API_KEY:
        return
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(401, "Invalid or missing Authorization header.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="MiniClosedAI Voice", docs_url="/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str
    language: str
    speed: float | None = Field(None, ge=0.5, le=2.0)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Cheap reachability probe. Doesn't touch models — safe to hit pre-warm."""
    return {
        "ok": True,
        "asr_model": ASR_MODEL,
        "tts_model": "piper",
        "device": DEVICE,
        "voices_loaded": _tts is not None,
    }


@app.get("/voices")
def voices(_=Depends(_require_auth)):
    """The static catalog — same shape MiniClosedAI's voice.py reshapes for
    the per-bot Voice + Language dropdowns."""
    return VOICE_CATALOG


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    _=Depends(_require_auth),
):
    """Multipart audio → JSON transcript. `language` is an optional hint;
    omit for auto-detect (faster-whisper's CLD is reasonable)."""
    asr = await _get_asr()
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio payload.")
    # Whisper is CPU/GPU-bound; offload to a worker thread so the event
    # loop stays responsive to /health probes during a long clip.
    return await asyncio.to_thread(asr.transcribe, data, language)


@app.post("/speak")
async def speak(req: SpeakRequest, _=Depends(_require_auth)):
    """One-shot synth — returns a single audio/wav body. Use /speak/stream for
    chunked playback over SSE."""
    tts = await _get_tts()
    chunks: list[bytes] = []
    sample_rate: int | None = None
    for chunk, sr in tts.synthesize_stream(req.text, req.voice, req.language, req.speed):
        chunks.append(chunk)
        sample_rate = sr
    pcm = b"".join(chunks)
    if not pcm or sample_rate is None:
        raise HTTPException(500, "TTS produced no audio.")
    audio_np = np.frombuffer(pcm, dtype=np.int16)
    buf = io.BytesIO()
    sf.write(buf, audio_np, sample_rate, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")


# ---------------------------------------------------------------------------
# Call mode — long-running duplex WebRTC via FastRTC
# ---------------------------------------------------------------------------
# The browser drives a real conversation:
#   1. POST /call/configure with {conv_id, miniclosedai_url, voice, language}
#   2. POST /webrtc/offer (mounted by FastRTC) with the SDP offer → SDP answer
#   3. Audio flows directly browser ↔ this service. After each detected pause,
#      our handler transcribes, calls MiniClosedAI's /chat/stream for the bot
#      reply, synthesizes via Piper, and yields audio back.
#   4. Transcript + reply tokens ride a WebRTC DataChannel as JSON events.
#
# v1 limit: ONE active call per voice service instance. Multi-concurrent
# requires scoping `_call_config` per WebRTC session id — punted to v3.

_call_config: dict = {
    "conv_id": None,
    "miniclosedai_url": "",
    "voice_id": "",
    "language": "en",
}

# Default voice per language — Piper voice ids from tts.py's VOICE_CATALOG.
_DEFAULT_VOICES = {"en": "en_US-amy-medium", "es": "es_MX-claude-high"}


def _default_voice(lang: str) -> str:
    return _DEFAULT_VOICES.get(lang, "en_US-amy-medium")


class CallConfigure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conv_id: int
    miniclosedai_url: str = Field(..., min_length=1)
    voice: str | None = None
    language: str | None = None


@app.post("/call/configure")
def call_configure(req: CallConfigure, _=Depends(_require_auth)):
    """Set the per-call config the WebRTC handler will read on each turn.

    Must be called immediately before POSTing the SDP offer. Returns the
    resolved config so the browser knows which voice/language defaulted in.
    """
    lang = (req.language or "en").lower()
    voice = req.voice or _default_voice(lang)
    _call_config["conv_id"] = req.conv_id
    _call_config["miniclosedai_url"] = req.miniclosedai_url
    _call_config["voice_id"] = voice
    _call_config["language"] = lang
    return {"ok": True, "conv_id": req.conv_id, "voice": voice, "language": lang}


@app.get("/call/events/{webrtc_id}")
async def call_events(webrtc_id: str):
    """SSE stream of AdditionalOutputs the handler yields during the call.

    FastRTC's Stream pushes `AdditionalOutputs(...)` into an internal queue
    keyed by `webrtc_id` — they are NOT delivered over the WebRTC DataChannel
    automatically. This endpoint forwards them as `data: {...}\\n\\n` frames so
    the browser can render `{transcript}` / `{chunk}` / `{end}` / `{error}`
    events in real time, alongside the audio track flowing over WebRTC.
    """
    stream = _ensure_stream()

    async def gen():
        try:
            async for outputs in stream.output_stream(webrtc_id):
                # AdditionalOutputs.args is a tuple of whatever the handler
                # passed to AdditionalOutputs(...) — usually one dict each.
                for arg in (getattr(outputs, "args", None) or ()):
                    if isinstance(arg, dict):
                        yield f"data: {json.dumps(arg)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _call_handler(audio):
    """The single global handler FastRTC drives on each VAD pause.

    Reads per-call config from `_call_config` (set by /call/configure). Builds
    a fresh BotCallHandler for each turn so per-call state stays local; the
    asr/tts singletons are reused, no extra model load.
    """
    if _call_config["conv_id"] is None or not _call_config["miniclosedai_url"]:
        return
    asr = await _get_asr()
    tts = await _get_tts()
    inst = BotCallHandler(
        asr, tts,
        _call_config["conv_id"],
        _call_config["miniclosedai_url"],
        _call_config["voice_id"],
        _call_config["language"],
    )
    async for ev in inst.respond(audio):
        yield ev


# Mount the FastRTC Stream at startup. Lazy so the import of fastrtc (which
# pulls aiortc + libsrtp) doesn't slow down /health's first response.
_stream = None


def _ensure_stream():
    global _stream
    if _stream is not None:
        return _stream
    from fastrtc import ReplyOnPause, Stream
    from fastrtc.reply_on_pause import AlgoOptions
    from fastrtc.pause_detection.silero import SileroVadOptions

    # The browser's mic delivers very-low-amplitude audio (peak ~5% of int16
    # full scale). Apply gain so VAD + Whisper see normal speech levels. 4x
    # brings peak~1500 → ~6000 without slamming the ceiling — 8x clipped at
    # 32767, which made Whisper hallucinate ("RRRR" / repeated phrases).
    _GAIN = 4

    def _amplify(pcm):
        if pcm is None or not hasattr(pcm, "astype"):
            return pcm
        amp = pcm.astype(np.int32) * _GAIN
        np.clip(amp, -32768, 32767, out=amp)
        return amp.astype(np.int16)

    async def _amplified_call_handler(audio):
        sr, pcm = audio
        async for ev in _call_handler((sr, _amplify(pcm))):
            yield ev

    # Monkey-patch ReplyOnPause.receive so VAD also sees amplified audio (the
    # handler-side gain alone wouldn't help: VAD runs first and decides whether
    # to invoke the handler at all).
    _orig_receive = ReplyOnPause.receive
    def _gained_receive(self, frame):
        sr, pcm = frame
        return _orig_receive(self, (sr, _amplify(pcm)))
    ReplyOnPause.receive = _gained_receive

    _stream = Stream(
        handler=ReplyOnPause(
            _amplified_call_handler,
            # Silero defaults to 2000ms of silence before declaring end-of-turn,
            # which is most of the perceived "took a really long time" lag. With
            # amplified audio (above), 300ms is reliable for conversational
            # turn-taking. min_speech_duration_ms=100 catches short "yes"/"no".
            model_options=SileroVadOptions(
                min_silence_duration_ms=300,
                min_speech_duration_ms=100,
                speech_pad_ms=200,
            ),
            # AlgoOptions stays mostly default — chunk size 0.5s leaves enough
            # silero a 250ms-min window. speech_threshold=0.05 is permissive
            # so a quiet trailing word still counts as still-speaking.
            algo_options=AlgoOptions(
                audio_chunk_duration=0.5,
                started_talking_threshold=0.15,
                speech_threshold=0.05,
            ),
        ),
        modality="audio",
        mode="send-receive",
    )
    _stream.mount(app)
    return _stream


@app.on_event("startup")
async def _mount_call_stream():
    try:
        _ensure_stream()
    except Exception:
        # Don't kill the whole service if fastrtc fails to import — /transcribe
        # and /speak still work. The /call/configure endpoint will surface the
        # error if someone tries to use call mode.
        import traceback
        traceback.print_exc()


@app.on_event("startup")
async def _prewarm_models():
    # Whisper-small is ~500MB; loading it on the first VAD pause makes turn 1
    # of a call mode session feel sluggish vs every subsequent turn. Pull both
    # ASR and TTS into memory at startup so the first utterance is fast.
    # Fire-and-forget — startup completes immediately; /health stays cheap.
    async def _warm():
        try:
            await _get_asr()
            await _get_tts()
        except Exception:
            import traceback
            traceback.print_exc()
    asyncio.create_task(_warm())


@app.post("/speak/stream")
async def speak_stream(req: SpeakRequest, _=Depends(_require_auth)):
    """SSE chunked synth — each frame is `{chunk_b64, sample_rate}` (int16 PCM
    base64-encoded), then a terminal `{done: true}`. MiniClosedAI's push-to-talk
    UI decodes the chunks straight into Web Audio for seamless playback."""
    tts = await _get_tts()

    async def gen():
        try:
            for chunk, sr in tts.synthesize_stream(req.text, req.voice, req.language, req.speed):
                event = {
                    "chunk_b64": base64.b64encode(chunk).decode("ascii"),
                    "sample_rate": sr,
                }
                yield f"data: {json.dumps(event)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, log_level="info")
