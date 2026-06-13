"""asr.py — faster-whisper wrapper for the MiniClosedAI voice service.

Two entrypoints:

  * `transcribe(audio_bytes, language=None)` — for any container the browser
    uploads (WebM/Opus, OGG/Opus, MP4, WAV, ...). Decodes via the `ffmpeg`
    subprocess (more forgiving than PyAV for MediaRecorder's fragmented
    WebM output), then runs faster-whisper on the resulting float32 PCM.
  * `transcribe_array(pcm, sample_rate, language=None)` — used by the FastRTC
    call handler, which already has the raw frames in memory. Resamples to
    16 kHz if needed and skips the ffmpeg detour entirely.

Model size is picked via the `VOICE_ASR_MODEL` env var (passed by server.py):

    tiny   — 39M params, instant on CPU, low accuracy
    base   — 74M params, fast on CPU, decent
    small  — 244M params, the v1 default (good balance on CPU)
    medium — 769M params, GPU-recommended
    large-v3 — 1.5B params, GPU strongly recommended
"""
from __future__ import annotations

import io
import subprocess
from typing import Any

import numpy as np
from faster_whisper import WhisperModel


def _ffmpeg_decode_to_pcm(audio_bytes: bytes, target_sr: int = 16000) -> np.ndarray:
    """Decode any ffmpeg-supported container to mono float32 PCM at target_sr.

    This is robust against the "no-duration WebM" blobs the browser's
    MediaRecorder produces, which PyAV's matroska demuxer refuses to parse
    (`invalid as first byte of an EBML number`). ffmpeg's libavformat is
    forgiving enough to demux them straight through.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",                   # any container, stdin
            "-f", "f32le",                    # raw 32-bit little-endian float
            "-ac", "1",                       # mono
            "-ar", str(target_sr),            # 16 kHz (Whisper's native rate)
            "pipe:1",
        ],
        input=audio_bytes, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace")[:400]
        raise RuntimeError(f"ffmpeg failed to decode the audio payload: {stderr}")
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _resolve_device_and_compute(device: str) -> tuple[str, str]:
    """Pick (device, compute_type). `device` may be 'auto' / 'cuda' / 'cpu'."""
    if device == "auto":
        try:
            import torch  # optional — only used for the CUDA probe
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    if device == "cuda":
        return "cuda", "float16"
    return "cpu", "int8"


class ASR:
    def __init__(self, model_name: str = "small", device: str = "auto") -> None:
        dev, compute = _resolve_device_and_compute(device)
        self.model_name = model_name
        self.device = dev
        self.compute_type = compute
        # Models are downloaded on first instantiation and cached under
        # $HF_HOME (defaults to /root/.cache/huggingface inside the container).
        self.model = WhisperModel(model_name, device=dev, compute_type=compute)

    def transcribe(self, audio: bytes, language: str | None = None) -> dict[str, Any]:
        """Decode (via ffmpeg) + transcribe `audio` from any audio container.

        Returns the same shape the MiniClosedAI side expects:
            {"text": "...", "language": "en", "segments": [{start,end,text}, ...]}
        """
        pcm = _ffmpeg_decode_to_pcm(audio, target_sr=16000)
        segments, info = self.model.transcribe(
            pcm,
            language=language,
            vad_filter=True,                       # cheap silero-vad pre-filter
            condition_on_previous_text=False,      # less hallucination for short clips
        )
        text_parts: list[str] = []
        seg_list: list[dict] = []
        for seg in segments:
            text_parts.append(seg.text)
            seg_list.append({"start": seg.start, "end": seg.end, "text": seg.text})
        return {
            "text": "".join(text_parts).strip(),
            "language": info.language,
            "segments": seg_list,
        }

    def transcribe_array(
        self,
        pcm,                       # np.ndarray, mono, int16 or float32
        sample_rate: int,
        language: str | None = None,
    ) -> str:
        """Transcribe raw PCM that's already in memory — no container/ffmpeg.

        Used by the FastRTC call handler: WebRTC frames arrive as a numpy
        array, already mono and already a known sample rate (usually 48 kHz or
        16 kHz). faster-whisper expects float32 at 16 kHz; this normalizes,
        resamples if necessary, and returns just the joined text.
        """
        import numpy as np
        # Cast to float32 in [-1, 1].
        if pcm.dtype == np.int16:
            audio = pcm.astype(np.float32) / 32768.0
        elif pcm.dtype == np.float32:
            audio = pcm
        else:
            audio = pcm.astype(np.float32)
            if audio.max() > 1.5 or audio.min() < -1.5:
                # Heuristic: looks integer-scaled, normalize.
                audio = audio / float(np.max(np.abs(audio)) or 1.0)
        # Force mono.
        if audio.ndim > 1:
            audio = audio.mean(axis=-1)
        # Resample to 16 kHz if needed (whisper's native rate). Linear interp
        # is good enough for ASR — quality difference vs. librosa-resample on
        # speech is below whisper's own noise floor.
        if sample_rate != 16000:
            ratio = 16000 / float(sample_rate)
            new_len = int(round(len(audio) * ratio))
            if new_len > 0:
                x_old = np.linspace(0, 1, num=len(audio), endpoint=False, dtype=np.float32)
                x_new = np.linspace(0, 1, num=new_len, endpoint=False, dtype=np.float32)
                audio = np.interp(x_new, x_old, audio).astype(np.float32)
        segments, _info = self.model.transcribe(
            audio,
            language=language,
            vad_filter=False,           # the call handler already did VAD
            condition_on_previous_text=False,
        )
        return "".join(s.text for s in segments).strip()
