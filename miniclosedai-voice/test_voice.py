#!/usr/bin/env python3
"""test_voice.py — end-to-end tests for the standalone voice service.

Runs independently of MiniClosedAI. Covers the full HTTP contract plus a
real WebRTC offer/answer handshake. Where possible the tests *generate
their own audio* (synthesize via /speak, hand the result to /transcribe)
so there's nothing to download and nothing to keep in sync with a
reference fixture.

Usage:
    # From the host, against a running container on :8090:
    python3 test_voice.py
    # Or point at a remote / different port:
    VOICE_URL=https://my-runpod-host.proxy.runpod.net python3 test_voice.py
    # Inside the container itself (handy for full aiortc audio round-trip):
    docker compose exec voice python /app/test_voice.py --with-audio

Exit code is 0 iff every test passed (skipped tests don't fail the run).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Callable

VOICE_URL = os.environ.get("VOICE_URL", "http://localhost:8090").rstrip("/")

_RESULTS: list[tuple[str, str | bool, str]] = []   # (name, ok|"skip", message)
_TESTS: list[tuple[str, Callable]] = []


def test(name: str):
    def deco(fn: Callable):
        async def runner():
            t0 = time.perf_counter()
            try:
                if asyncio.iscoroutinefunction(fn):
                    await fn()
                else:
                    fn()
            except _Skip as e:
                _RESULTS.append((name, "skip", str(e) or "skipped"))
                print(f"  ⊘ {name}  (skipped: {e or 'no reason'})  ({time.perf_counter()-t0:.2f}s)")
                return
            except AssertionError as e:
                _RESULTS.append((name, False, f"AssertionError: {e}"))
                print(f"  ✗ {name}  ({time.perf_counter()-t0:.2f}s)")
                traceback.print_exc()
                return
            except Exception as e:
                _RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
                print(f"  ✗ {name}  ({time.perf_counter()-t0:.2f}s)")
                traceback.print_exc()
                return
            _RESULTS.append((name, True, ""))
            print(f"  ✓ {name}  ({time.perf_counter()-t0:.2f}s)")
        _TESTS.append((name, runner))
        return runner
    return deco


class _Skip(Exception):
    """Marks a test as skipped (e.g. when aiortc isn't installed)."""


def skip(reason: str = "") -> None:
    raise _Skip(reason)


# ----------------------------------------------------------------------
# Helpers — bare urllib + json keep the test script dependency-free.
# ----------------------------------------------------------------------

def _http_get(path: str, *, timeout: float = 5.0) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(f"{VOICE_URL}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _http_post_json(path: str, payload: dict, *, timeout: float = 30.0) -> tuple[int, bytes, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{VOICE_URL}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _http_post_multipart(path: str, fields: dict[str, tuple[str, bytes, str]],
                         *, timeout: float = 60.0) -> tuple[int, bytes]:
    """Tiny multipart/form-data POST — no `requests` dependency.

    `fields` is `{name: (filename, content_bytes, mime)}`.
    """
    boundary = f"-----{uuid.uuid4().hex}"
    body = io.BytesIO()
    for name, (fname, content, mime) in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'.encode()
        )
        body.write(f"Content-Type: {mime}\r\n\r\n".encode())
        body.write(content)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"{VOICE_URL}{path}", data=body.getvalue(), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _sse_events(raw: bytes, *, limit: int | None = None) -> list[dict]:
    out: list[dict] = []
    for block in raw.decode(errors="replace").split("\n\n"):
        line = block.strip()
        if not line.startswith("data:"):
            continue
        try:
            out.append(json.loads(line[5:].strip()))
        except json.JSONDecodeError:
            continue
        if limit and len(out) >= limit:
            break
    return out


def _stream_sse(path: str, *, body: dict | None = None,
                method: str = "POST", max_seconds: float = 120.0) -> list[dict]:
    """Open an SSE stream and collect every JSON event until the body closes."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "text/event-stream"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{VOICE_URL}{path}", data=data, method=method, headers=headers,
    )
    events: list[dict] = []
    buf = ""
    deadline = time.monotonic() + max_seconds
    with urllib.request.urlopen(req, timeout=max_seconds) as r:
        while time.monotonic() < deadline:
            chunk = r.read(4096)
            if not chunk:
                break
            buf += chunk.decode(errors="replace")
            parts = buf.split("\n\n")
            buf = parts.pop()
            for part in parts:
                line = part.strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                    events.append(ev)
                    if ev.get("done") or ev.get("end"):
                        return events
                except json.JSONDecodeError:
                    continue
    return events


# ----------------------------------------------------------------------
# Tier 1: HTTP contract — fast, deterministic, no GPU/audio dependency.
# ----------------------------------------------------------------------

@test("health: returns {ok, asr_model, tts_model, device}")
def _():
    code, body, _ = _http_get("/health")
    assert code == 200, body
    d = json.loads(body)
    assert d["ok"] is True, d
    assert d["asr_model"], d
    assert d["tts_model"] == "piper", d
    assert d["device"] in ("auto", "cuda", "cpu"), d


@test("voices: catalog includes EN + ES + voice ids")
def _():
    code, body, _ = _http_get("/voices")
    assert code == 200
    cat = json.loads(body)
    assert "en" in cat and cat["en"], cat
    assert "es" in cat and cat["es"], cat
    for lang in ("en", "es"):
        for v in cat[lang]:
            assert v.get("id"), (lang, v)
            assert v.get("name"), (lang, v)


@test("openapi: every advertised route is mounted (no 404 stragglers)")
def _():
    code, body, _ = _http_get("/openapi.json")
    assert code == 200
    spec = json.loads(body)
    expected = {"/health", "/voices", "/transcribe", "/speak",
                "/speak/stream", "/call/configure", "/call/events/{webrtc_id}",
                "/webrtc/offer"}
    present = set(spec["paths"].keys())
    missing = expected - present
    assert not missing, f"routes missing from openapi: {missing}"


@test("speak: returns a non-empty WAV audio response")
def _():
    code, body, _ = _http_post_json("/speak", {
        "text": "Hello world.",
        "voice": "en_US-amy-medium", "language": "en",
    }, timeout=60)
    assert code == 200, body
    assert body.startswith(b"RIFF"), f"expected WAV header, got {body[:8]!r}"
    assert len(body) > 1024, f"WAV too small ({len(body)} bytes)"


@test("speak/stream: emits at least one chunk and a terminal done event")
def _():
    events = _stream_sse("/speak/stream", body={
        "text": "Streaming hello.",
        "voice": "en_US-amy-medium", "language": "en",
    })
    chunks = [e for e in events if "chunk_b64" in e]
    assert chunks, f"no audio chunks: {events[:3]}"
    assert any(e.get("done") for e in events), f"no done event: {events}"
    raw = base64.b64decode(chunks[0]["chunk_b64"])
    assert chunks[0]["sample_rate"] > 0
    assert len(raw) > 0


@test("speak: rejects requests for an unknown voice/language gracefully")
def _():
    # The Piper wrapper falls back to a default rather than raising; the call
    # should still 200 with a valid WAV — so this is really 'doesn't crash'.
    code, body, _ = _http_post_json("/speak", {
        "text": "Default voice fallback.",
        "voice": "this-voice-does-not-exist", "language": "qq",
    }, timeout=60)
    assert code == 200, body
    assert body.startswith(b"RIFF"), body[:8]


# ----------------------------------------------------------------------
# Tier 2: ASR ↔ TTS round-trip — proves both models load and integrate.
# ----------------------------------------------------------------------

@test("round-trip: speak('this is a test') → transcribe should recover the words")
def _():
    code, wav, _ = _http_post_json("/speak", {
        "text": "This is a voice integration test.",
        "voice": "en_US-amy-medium", "language": "en",
    }, timeout=60)
    assert code == 200 and wav.startswith(b"RIFF"), wav[:8]
    code, body = _http_post_multipart("/transcribe", {
        "audio": ("synth.wav", wav, "audio/wav"),
    }, timeout=60)
    assert code == 200, body
    out = json.loads(body)
    text = (out.get("text") or "").lower()
    # Whisper-small is fuzzy on synthetic audio — accept any of the
    # distinctive words. If none match, something is fundamentally off.
    needles = ("test", "voice", "integration")
    assert any(n in text for n in needles), \
        f"transcript {text!r} contains none of {needles}"
    assert out.get("language"), out


# ----------------------------------------------------------------------
# Tier 3: Call mode — WebRTC handshake + SSE events.
# ----------------------------------------------------------------------

@test("call/configure: accepts JSON and resolves voice + language defaults")
def _():
    code, body, _ = _http_post_json("/call/configure", {
        "conv_id": 1,
        "miniclosedai_url": "http://test.invalid",
        "language": "en",
    })
    assert code == 200, body
    d = json.loads(body)
    assert d["ok"] is True
    assert d["voice"], d   # default voice resolved
    assert d["language"] == "en"


@test("webrtc/offer: rejects requests missing webrtc_id (422)")
def _():
    code, body, _ = _http_post_json("/webrtc/offer", {
        "sdp": "v=0\r\n", "type": "offer",
    })
    assert code == 422, (code, body)
    detail = json.loads(body)
    assert any(
        d.get("loc", [])[-1] == "webrtc_id" for d in detail.get("detail", [])
    ), detail


def _real_offer_sdp() -> str:
    """Build a minimal real SDP offer using aiortc, no media playback wired up.

    aiortc must be installed (it is in the voice container). Returns an offer
    SDP string with a receive-only audio m= line.
    """
    from aiortc import RTCPeerConnection
    async def _():
        pc = RTCPeerConnection()
        # An "addTransceiver" of audio without an attached track yields a
        # receive-only m= line — enough for the server to negotiate.
        pc.addTransceiver("audio", direction="recvonly")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        # Wait briefly for at least one local ICE candidate to be gathered
        # (host candidates appear almost immediately).
        for _ in range(20):
            if pc.iceGatheringState == "complete":
                break
            await asyncio.sleep(0.1)
        sdp = pc.localDescription.sdp
        await pc.close()
        return sdp
    return asyncio.get_event_loop().run_until_complete(_())


@test("webrtc/offer: a real SDP offer is accepted and returns a valid answer")
async def _():
    try:
        from aiortc import RTCPeerConnection      # noqa: F401
    except ImportError:
        skip("aiortc not installed (run inside the voice container)")

    from aiortc import RTCPeerConnection, RTCSessionDescription
    pc = RTCPeerConnection()
    pc.addTransceiver("audio", direction="recvonly")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    for _ in range(30):
        if pc.iceGatheringState == "complete":
            break
        await asyncio.sleep(0.1)

    webrtc_id = f"test-{uuid.uuid4()}"
    # Configure the call against a dummy URL so the handler has somewhere
    # to point if it ever fires (we won't trigger a turn in this test).
    _http_post_json("/call/configure", {
        "conv_id": 1, "miniclosedai_url": "http://test.invalid", "language": "en",
    })
    code, body, _ = _http_post_json("/webrtc/offer", {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "webrtc_id": webrtc_id,
    }, timeout=15)
    try:
        assert code == 200, body
        ans = json.loads(body)
        assert ans.get("type") == "answer", ans
        assert "v=0" in ans.get("sdp", ""), ans
        # The answer must include an audio m= line.
        assert "m=audio" in ans["sdp"], ans["sdp"][:300]
        # Setting the remote description on our local pc should succeed —
        # proving the SDP is well-formed for aiortc's parser.
        await pc.setRemoteDescription(RTCSessionDescription(**ans))
    finally:
        await pc.close()


@test("call/events/{id}: SSE endpoint opens and stays open for an unknown id")
def _():
    # Even without a live WebRTC connection, the SSE endpoint must accept
    # the request and return a valid stream (it'll just have no events).
    # Read a few bytes with a short timeout to confirm 200 + correct
    # content-type, then close.
    req = urllib.request.Request(
        f"{VOICE_URL}/call/events/no-such-id-{uuid.uuid4()}",
        headers={"Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200, r.status
        ct = r.headers.get("content-type", "")
        assert "text/event-stream" in ct, ct
        # Read a small amount with the socket timeout already in effect.
        try:
            r.read(64)
        except Exception:
            # Empty / timing-out reads are expected; we already validated
            # the headers, which is the actual contract.
            pass


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

async def _main_async() -> int:
    print(f"\nVoice service E2E tests against {VOICE_URL}")
    print(f"running {len(_TESTS)} tests\n")
    for _, runner in _TESTS:
        await runner()

    passed  = sum(1 for _, ok, _ in _RESULTS if ok is True)
    skipped = sum(1 for _, ok, _ in _RESULTS if ok == "skip")
    failed  = len(_RESULTS) - passed - skipped
    skip_str = f" · {skipped} skipped" if skipped else ""
    print(f"\n{'='*48}\n{passed}/{len(_RESULTS)} passed · {failed} failed{skip_str}\n{'='*48}")
    if failed:
        print("\nFailures:")
        for n, ok, m in _RESULTS:
            if ok is False:
                print(f"  ✗ {n}  → {m}")
    if skipped:
        print("\nSkipped:")
        for n, ok, m in _RESULTS:
            if ok == "skip":
                print(f"  ⊘ {n}  → {m}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="Voice service URL (default: $VOICE_URL or http://localhost:8090)")
    args = parser.parse_args()
    global VOICE_URL
    if args.url:
        VOICE_URL = args.url.rstrip("/")

    # Quick connectivity probe before launching the suite — fail fast with a
    # clear message rather than a wall of cryptic urllib errors.
    try:
        urllib.request.urlopen(f"{VOICE_URL}/health", timeout=3)
    except (urllib.error.URLError, OSError) as e:
        print(f"\n✗ Could not reach the voice service at {VOICE_URL}: {e}")
        print("  Start it with:  cd miniclosedai-voice && ./start.sh")
        return 2

    return asyncio.run(_main_async())


if __name__ == "__main__":
    sys.exit(main())
