"""call.py — FastRTC handler for the "call the bot" mode.

A long-running WebRTC peer connection with VAD-based turn detection. On each
detected pause we transcribe the buffered audio, POST it to MiniClosedAI's
existing chat-streaming endpoint, and feed the reply to Piper — **one
sentence at a time** so the user starts hearing audio while the rest of the
reply is still generating.

Pipeline per turn:

    audio (since the last pause)  →  faster-whisper ASR                →  text
                                                                          ↓
    text  →  POST /api/conversations/{id}/chat/stream  (to MiniClosedAI)
                                                                          ↓
    chunked reply  →  sentence splitter  →  Piper TTS (per sentence)   →  audio frames
                          (text events ride in parallel via DataChannel queue)

Side-channel events (each `AdditionalOutputs({...})`) the browser renders:
  {status: 'transcribing'|'thinking'|'speaking'|'listening'}  — pipeline stage
  {transcript: "..."}                                          — user's text
  {chunk: "..."}                                               — assistant token
  {end: true}                                                  — turn finished
  {error: "..."}                                               — pipeline failure

FastRTC's ReplyOnPause class already handles barge-in: when the user starts
speaking during a yielded TTS stream, the handler's generator is cancelled
and the next utterance starts a fresh turn.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx
import numpy as np
from fastrtc import AdditionalOutputs, ReplyOnPause


# -- Sentence splitter -----------------------------------------------------

# Common abbreviations whose trailing dot must NOT be treated as a sentence
# boundary. Lower-cased; the lookup also lower-cases the candidate.
_ABBREVIATIONS = frozenset({
    "mr.", "mrs.", "ms.", "dr.", "sr.", "jr.", "st.", "vs.", "etc.",
    "e.g.", "i.e.", "u.s.", "u.k.", "u.n.", "inc.", "ltd.", "co.", "no.",
    "fig.", "vol.", "ed.", "ch.", "pg.", "p.", "pp.", "approx.", "min.",
    "max.", "avg.", "incl.", "excl.", "rev.", "est.",
})

# Sentence terminator followed by whitespace + a likely next-sentence cue
# (uppercase letter / opening quote / paren / digit). Lookahead so we don't
# consume the next sentence's first character.
_SPLIT_PAT = re.compile(r"[.!?][\"')\]]?(\s+)(?=[A-Z\"'(0-9])")
# Soft boundary: terminator followed by a newline (LLM finished a paragraph).
_NEWLINE_PAT = re.compile(r"[.!?][\"')\]]?\n+")
# Trailing-word check to skip false positives like "Mr. Smith".
_LAST_WORD_PAT = re.compile(r"\S+$")


def _next_sentence(buf: str, *, min_len: int = 20, force_max: int = 240) -> tuple[str | None, str]:
    """Pop the next complete sentence off the front of `buf`.

    Returns `(sentence, remaining)` — sentence is `None` if no complete one
    yet (and `remaining` == `buf`). Skips false positives like "Mr. Smith" or
    "e.g." by checking the trailing word, and refuses to split anything
    shorter than `min_len` characters. As a failsafe, force-splits at the
    last comma / space if `buf` reaches `force_max` chars with no terminator.
    """
    for m in _SPLIT_PAT.finditer(buf):
        end = m.end() - len(m.group(1))
        candidate = buf[:end].rstrip()
        if len(candidate) < min_len:
            continue
        lw = _LAST_WORD_PAT.search(candidate)
        if lw and lw.group().lower() in _ABBREVIATIONS:
            continue
        return candidate, buf[end:].lstrip()

    nl = _NEWLINE_PAT.search(buf)
    if nl and len((c := buf[:nl.end()].rstrip())) >= min_len:
        return c, buf[nl.end():]

    if len(buf) >= force_max:
        head = buf[:force_max]
        comma_idx = head.rfind(", ")
        if comma_idx >= min_len:
            return head[:comma_idx + 1], buf[comma_idx + 1:].lstrip()
        space_idx = head.rfind(" ")
        if space_idx >= min_len:
            return head[:space_idx], buf[space_idx:].lstrip()

    return None, buf

log = logging.getLogger("voice.call")


class BotCallHandler:
    """Per-call state + the async generator FastRTC calls on each pause.

    `asr` and `tts` are the module-level singletons from server.py; we don't
    own them. `conv_id`, `miniclosedai_url`, `voice_id`, `language` are the
    per-call config the browser sends with the offer.
    """

    def __init__(
        self,
        asr,
        tts,
        conv_id: int,
        miniclosedai_url: str,
        voice_id: str,
        language: str,
    ) -> None:
        self.asr = asr
        self.tts = tts
        self.conv_id = conv_id
        self.miniclosedai_url = miniclosedai_url.rstrip("/")
        self.voice_id = voice_id
        self.language = language

    async def _synthesize(self, text: str):
        """Run Piper for one sentence in a worker thread; return all PCM chunks.

        Collecting per-sentence keeps the main async loop responsive while
        Piper churns; the chunks are then yielded back into the FastRTC media
        track in order. Sentences are short enough (<240 chars) that the
        thread call returns in ~150-400ms, which is well below the first-
        audio latency the user actually perceives.
        """
        def _run():
            out: list[tuple[bytes, int]] = []
            for pcm_chunk, sr in self.tts.synthesize_stream(
                text, self.voice_id, self.language,
            ):
                if pcm_chunk:
                    out.append((pcm_chunk, sr))
            return out
        return await asyncio.to_thread(_run)

    async def respond(self, audio):
        """Run one turn: ASR → chat (streamed) → sentence-by-sentence TTS.

        Each pipeline transition emits a `{status: ...}` event so the UI can
        show "transcribing / thinking / speaking / listening" feedback. TTS
        starts on the first complete sentence the LLM yields, so the user
        hears audio while later sentences are still being generated.
        """
        sample_rate, pcm = audio
        if hasattr(pcm, "flatten"):
            pcm = pcm.flatten()

        # 1. ASR
        yield AdditionalOutputs({"status": "transcribing"})
        try:
            text = await asyncio.to_thread(
                self.asr.transcribe_array, pcm, int(sample_rate), self.language or None,
            )
        except Exception as e:
            log.exception("asr failed")
            yield AdditionalOutputs({"error": f"asr: {e}", "status": "listening"})
            return
        text = (text or "").strip()
        if not text:
            yield AdditionalOutputs({"status": "listening"})
            return

        yield AdditionalOutputs({"transcript": text})
        log.info("conv=%s transcript=%r", self.conv_id, text)

        # 2. Stream chat reply; flush completed sentences to TTS as they form.
        yield AdditionalOutputs({"status": "thinking"})
        url = f"{self.miniclosedai_url}/api/conversations/{self.conv_id}/chat/stream"
        buffer = ""                          # accumulator for sentence detection
        spoke_anything = False               # whether any sentence has been synthesized
        full_reply: list[str] = []           # for logging / "the bot said X"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=10.0), verify=False,
            ) as client:
                async with client.stream(
                    "POST", url,
                    json={"message": text, "persist": True, "include_history": True, "voice_mode": True},
                    headers={"Accept": "text/event-stream"},
                ) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode(errors="replace")[:200]
                        msg = f"chat HTTP {resp.status_code}: {detail}"
                        log.warning("conv=%s %s", self.conv_id, msg)
                        yield AdditionalOutputs({"error": msg, "status": "listening"})
                        return
                    sse_buf = ""
                    chat_done = False
                    async for raw in resp.aiter_text():
                        sse_buf += raw
                        parts = sse_buf.split("\n\n")
                        sse_buf = parts.pop()
                        for part in parts:
                            line = part.strip()
                            if not line.startswith("data:"):
                                continue
                            try:
                                ev = json.loads(line[5:].strip())
                            except json.JSONDecodeError:
                                continue
                            if "error" in ev:
                                yield AdditionalOutputs({"error": ev["error"], "status": "listening"})
                                return
                            if "chunk" in ev:
                                piece = ev["chunk"]
                                full_reply.append(piece)
                                buffer += piece
                                # Forward the chunk for live text streaming.
                                yield AdditionalOutputs({"chunk": piece})
                                # Drain every complete sentence currently in
                                # the buffer; one chunk can finish multiple
                                # short sentences in a row.
                                while True:
                                    sentence, buffer = _next_sentence(buffer)
                                    if not sentence:
                                        break
                                    if not spoke_anything:
                                        yield AdditionalOutputs({"status": "speaking"})
                                        spoke_anything = True
                                    try:
                                        for pcm_chunk, out_sr in await self._synthesize(sentence):
                                            arr = np.frombuffer(pcm_chunk, dtype=np.int16)
                                            yield (out_sr, arr.reshape(1, -1))
                                    except Exception as e:
                                        log.exception("tts (mid-stream) failed: %r", e)
                                        # Don't bail the whole turn — surface the
                                        # error but keep streaming the remaining
                                        # sentences (or at least the text).
                                        yield AdditionalOutputs({"error": f"tts: {e}"})
                            if ev.get("end"):
                                chat_done = True
                                break
                        if chat_done:
                            break
        except Exception as e:
            log.exception("chat stream failed")
            yield AdditionalOutputs({"error": f"chat: {e}", "status": "listening"})
            return

        # 3. Flush trailing buffer — the last sentence often has no terminator
        #    + lookahead, so it stays in the buffer until the LLM stops.
        tail = buffer.strip()
        if tail:
            if not spoke_anything:
                yield AdditionalOutputs({"status": "speaking"})
                spoke_anything = True
            try:
                for pcm_chunk, out_sr in await self._synthesize(tail):
                    arr = np.frombuffer(pcm_chunk, dtype=np.int16)
                    yield (out_sr, arr.reshape(1, -1))
            except Exception as e:
                log.exception("tts (tail) failed: %r", e)
                yield AdditionalOutputs({"error": f"tts: {e}"})

        # 4. Done — tell the UI to finalize the bubble and reset to listening.
        yield AdditionalOutputs({"status": "listening"})
        yield AdditionalOutputs({"end": True})


def build_handler(asr, tts, conv_id, miniclosedai_url, voice_id, language) -> ReplyOnPause:
    """Construct a ReplyOnPause-wrapped instance for one call.

    FastRTC's ReplyOnPause does the VAD + buffering: it accumulates input
    audio frames, detects pauses via Silero VAD, and calls our `respond`
    generator with the buffered chunk. Barge-in support is built-in.
    """
    inst = BotCallHandler(asr, tts, conv_id, miniclosedai_url, voice_id, language)
    return ReplyOnPause(inst.respond)
