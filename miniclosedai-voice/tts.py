"""tts.py — Piper TTS wrapper for the MiniClosedAI voice service.

Piper ships dozens of small ONNX voices per language. v1 ships **4 English +
4 Spanish voices** that auto-download from Hugging Face on first use and cache
to `VOICE_VOICES_DIR` (mounted as a Docker volume so cold-start happens once).

The wrapper exposes:
    voices()           — the static catalog (the `/voices` payload)
    synthesize_stream  — generator yielding (pcm16_chunk, sample_rate)

We swap the wrapper out later for XTTS-v2 / F5-TTS / etc. behind the same
two-method surface; the HTTP contract in server.py never changes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator
from urllib.request import urlretrieve

from piper import PiperVoice


# Static catalog: the voices this v1 ships. Each id matches Piper's HF layout
# (`<lang_region>-<name>-<quality>`); the wrapper auto-downloads on first use.
# `gender` is the speaker's natural gender (best-guess from voice card).
VOICE_CATALOG: dict[str, list[dict]] = {
    "en": [
        {"id": "en_US-amy-medium",          "name": "Amy (US)",      "gender": "F"},
        {"id": "en_US-ryan-medium",         "name": "Ryan (US)",     "gender": "M"},
        {"id": "en_GB-alan-medium",         "name": "Alan (GB)",     "gender": "M"},
        {"id": "en_GB-jenny_dioco-medium",  "name": "Jenny (GB)",    "gender": "F"},
    ],
    "es": [
        {"id": "es_ES-davefx-medium",       "name": "Dave (Spain)",    "gender": "M"},
        {"id": "es_ES-sharvard-medium",     "name": "Sharvard (Spain)","gender": "F"},
        {"id": "es_MX-claude-high",         "name": "Claude (Mexico)", "gender": "F"},
        {"id": "es_MX-ald-medium",          "name": "Ald (Mexico)",    "gender": "M"},
    ],
}

_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _voice_url_path(voice_id: str) -> str:
    """Build the path under rhasspy/piper-voices for a given voice id.

    Layout on HF: `<lang>/<lang_region>/<name>/<quality>/<voice_id>.onnx`
    e.g. `en/en_US/amy/medium/en_US-amy-medium.onnx`.
    """
    parts = voice_id.split("-")
    if len(parts) < 3:
        raise ValueError(f"Unrecognized Piper voice id: {voice_id!r}")
    lang_region, name, quality = parts[0], parts[1], parts[2]
    lang = lang_region.split("_")[0]
    return f"{lang}/{lang_region}/{name}/{quality}"


class TTS:
    def __init__(self, voices_dir: Path, use_cuda: bool = False) -> None:
        self.voices_dir = Path(voices_dir)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.use_cuda = use_cuda
        self._cache: dict[str, PiperVoice] = {}

    # ---- discovery ----------------------------------------------------

    @staticmethod
    def voices() -> dict[str, list[dict]]:
        return VOICE_CATALOG

    @staticmethod
    def _resolve(voice_id: str, language: str | None) -> str:
        """Return a known catalog voice id (defaults if the request is loose)."""
        # Exact match.
        for entries in VOICE_CATALOG.values():
            for e in entries:
                if e["id"] == voice_id:
                    return voice_id
        # Fall back to the first voice for the requested language.
        if language and VOICE_CATALOG.get(language):
            return VOICE_CATALOG[language][0]["id"]
        # Otherwise default to the first English voice.
        return VOICE_CATALOG["en"][0]["id"]

    # ---- loading ------------------------------------------------------

    def _ensure_downloaded(self, voice_id: str) -> Path:
        """Make sure the .onnx + .onnx.json files are on disk; return the .onnx."""
        rel = _voice_url_path(voice_id)
        for ext in ("onnx", "onnx.json"):
            dest = self.voices_dir / f"{voice_id}.{ext}"
            if dest.exists():
                continue
            url = f"{_HF_BASE}/{rel}/{voice_id}.{ext}"
            print(f"[voice] downloading {voice_id}.{ext} from {url}", flush=True)
            urlretrieve(url, dest)
        return self.voices_dir / f"{voice_id}.onnx"

    def _load(self, voice_id: str) -> PiperVoice:
        if voice_id in self._cache:
            return self._cache[voice_id]
        onnx_path = self._ensure_downloaded(voice_id)
        v = PiperVoice.load(str(onnx_path), use_cuda=self.use_cuda)
        self._cache[voice_id] = v
        return v

    # ---- synthesis ----------------------------------------------------

    def synthesize_stream(
        self,
        text: str,
        voice_id: str,
        language: str | None = None,
        speed: float | None = None,
    ) -> Iterator[tuple[bytes, int]]:
        """Yield (pcm16_chunk_bytes, sample_rate) tuples as audio is generated.

        Piper's `synthesize_stream_raw` emits little-endian int16 PCM at the
        voice's own sample rate (typically 22.05 kHz for medium-quality voices).
        Speed is applied per-call via `length_scale` (`speed > 1` = faster).
        """
        resolved = self._resolve(voice_id, language)
        voice = self._load(resolved)
        sr = voice.config.sample_rate
        kwargs = {}
        if speed and abs(speed - 1.0) > 1e-3:
            # Piper exposes length_scale, which is the inverse: <1 = faster.
            kwargs["length_scale"] = 1.0 / speed
        for chunk in voice.synthesize_stream_raw(text, **kwargs):
            yield chunk, sr
