"""End-to-end test suite for MiniClosedAI.

Runs every route and feature against a temporary database + in-process fake
backends (no real Ollama or LM Studio needed). No pytest dependency — just:

    python test_e2e.py

Exits 0 on all-pass, 1 on any failure. Each test prints a ✓ or ✗ so a
regression points at the feature it broke.

What this suite covers
----------------------
* DB migration is additive + idempotent
* Backends CRUD: GET/POST/PATCH/DELETE /api/backends
* Guardrails: can't delete built-in (403); can't delete bound (409)
* Probe endpoints: /api/backends/{id}/status + /models + /test
* Aggregated /api/models shape
* Conversations CRUD + clear endpoint
* Legacy /api/chat and /api/chat/stream still work
* Per-conversation /chat and /chat/stream
* Config lock (extra="forbid") on ConversationChatRequest
* PATCH null = "clear saved param" (the fix we just shipped)
* max_thinking_tokens is a soft cap (stream not aborted)
* Thinking forwarding: enable_thinking + /no_think + reasoning_effort
* OpenAI-compat /v1/chat/completions routes per conversation's backend
* Pretty-print / syntax-highlight paths are frontend-only (not covered here)
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable


# ------------------------------------------------------------------
# Setup: point the app's DB at a throwaway path BEFORE importing app.
# ------------------------------------------------------------------

_TMP_DIR = Path(tempfile.mkdtemp(prefix="mca-e2e-"))
_TMP_DB = _TMP_DIR / "test.db"

import db as _db_mod  # noqa: E402
_db_mod.DB_PATH = _TMP_DB
_db_mod.init_db()     # fire schema + seed now, not lazily on first request

import app as app_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ------------------------------------------------------------------
# In-process fake backend servers
# ------------------------------------------------------------------

class _FakeServer:
    """Base class — threads a HTTPServer on a random localhost port."""

    def __init__(self) -> None:
        self.captured: list[dict] = []     # must exist before _handler_class runs
        self._httpd = HTTPServer(("127.0.0.1", 0), self._handler_class())
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self._httpd.shutdown()

    def _handler_class(self):
        raise NotImplementedError


class FakeOllama(_FakeServer):
    """Speaks enough of Ollama's API to satisfy MiniClosedAI's Ollama adapter.

    Set `instance.dirty = True` before a stream to emit leading + trailing
    whitespace in content chunks — used by the persist-strip test to prove
    the server cleans up model output before writing it to the DB.

    For pull tests, configure `pull_chunks` (list of JSON-line dicts) and
    `pull_per_chunk_delay` (seconds between emitted chunks) before each test.
    """
    dirty = False
    pull_chunks: list[dict] = []
    pull_per_chunk_delay: float = 0.0
    chat_per_chunk_delay: float = 0.0  # slow /api/chat streaming (cancel test); 0 = off

    def _handler_class(self):
        captured = self.captured
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a, **kw): pass  # silent

            def do_GET(self):
                if self.path == "/api/tags":
                    captured.append({"path": self.path,
                                     "headers": dict(self.headers)})
                    body = json.dumps({
                        "models": [
                            {"name": "ollama-a:3b", "size": 1_000_000,
                             "details": {"family": "llama", "families": ["llama"]}},
                            {"name": "ollama-b:7b", "size": 4_000_000,
                             "details": {"family": "qwen", "families": ["qwen"]}},
                        ]
                    }).encode()
                    self._reply(200, body, "application/json")
                    return
                self._reply(404, b"not found", "text/plain")

            def do_POST(self):
                if self.path == "/api/chat":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    captured.append({"path": self.path, "payload": payload,
                                     "headers": dict(self.headers)})
                    # Non-streaming (tool-calling) path: return a single JSON
                    # object. If tools are offered and we haven't yet seen a
                    # tool result, ask to call the 'echo' tool; otherwise give
                    # a final answer. This drives the MCP tool-loop test.
                    if payload.get("stream") is False:
                        msgs = payload.get("messages", [])
                        has_tool_result = any(m.get("role") == "tool" for m in msgs)
                        if payload.get("tools") and not has_tool_result:
                            msg = {"role": "assistant", "content": "",
                                   "tool_calls": [{"function": {"name": "echo",
                                                                "arguments": {"text": "hi"}}}]}
                        else:
                            msg = {"role": "assistant", "content": "final answer using tool"}
                        body = json.dumps({"message": msg, "done": True}).encode()
                        self._reply(200, body, "application/json")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    # Emit a mini NDJSON stream: one thinking chunk then content.
                    first = "\n\nHello " if outer.dirty else "Hello "
                    last = "!\n\n\n" if outer.dirty else "!"
                    frames = [
                        {"message": {"role": "assistant", "thinking": "Let me think..."}, "done": False},
                        {"message": {"role": "assistant", "content": first}, "done": False},
                        {"message": {"role": "assistant", "content": "world"}, "done": False},
                        {"message": {"role": "assistant", "content": last}, "done": True},
                    ]
                    try:
                        for f in frames:
                            if outer.chat_per_chunk_delay:
                                time.sleep(outer.chat_per_chunk_delay)
                            self.wfile.write((json.dumps(f) + "\n").encode())
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        # Client/background task cancelled mid-stream (cancel test).
                        pass
                    return
                if self.path == "/api/embed":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length)) if length else {}
                    captured.append({"path": self.path, "payload": payload})
                    inp = payload.get("input", [])
                    if isinstance(inp, str):
                        inp = [inp]
                    # Deterministic bag-of-keywords embedding so retrieval is
                    # testable: a text containing "alpha" lands near a query
                    # containing "alpha". Zero vector if no vocab words present.
                    vocab = ["alpha", "beta", "gamma", "delta",
                             "epsilon", "zeta", "eta", "theta"]
                    embs = [[float(t.lower().count(w)) for w in vocab] for t in inp]
                    body = json.dumps({"embeddings": embs}).encode()
                    self._reply(200, body, "application/json")
                    return
                if self.path == "/api/pull":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length)) if length else {}
                    captured.append({"path": self.path, "payload": payload})
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    try:
                        for c in list(outer.pull_chunks):
                            if outer.pull_per_chunk_delay:
                                time.sleep(outer.pull_per_chunk_delay)
                            self.wfile.write((json.dumps(c) + "\n").encode())
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        # Client cancelled mid-stream — expected in cancel tests.
                        pass
                    return
                self._reply(404, b"not found", "text/plain")

            def _reply(self, status, body, ct):
                self.send_response(status)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return H


class FakeOpenAI(_FakeServer):
    """Speaks enough of the OpenAI /v1 API: models + chat.completions SSE.

    Emits at least one frame with `reasoning_content` so the OpenAI path's
    reasoning-field translation is exercised end-to-end.
    """

    def _handler_class(self):
        captured = self.captured

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a, **kw): pass

            def do_GET(self):
                if self.path == "/v1/models":
                    body = json.dumps({
                        "data": [
                            {"id": "openai-a-4b", "owned_by": "fake"},
                            {"id": "openai-b-8b", "owned_by": "fake"},
                        ]
                    }).encode()
                    self._reply(200, body, "application/json")
                    return
                self._reply(404, b"not found", "text/plain")

            def do_POST(self):
                if self.path == "/v1/chat/completions":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    captured.append({"path": self.path, "payload": payload,
                                     "headers": dict(self.headers)})
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    # Stream: role init + 3 reasoning chunks + 3 content chunks + DONE
                    chunks = [
                        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]},
                        {"choices": [{"index": 0, "delta": {"reasoning_content": "Reason 1 "}}]},
                        {"choices": [{"index": 0, "delta": {"reasoning_content": "Reason 2 "}}]},
                        {"choices": [{"index": 0, "delta": {"reasoning_content": "Reason 3 "}}]},
                        {"choices": [{"index": 0, "delta": {"content": "Hello "}}]},
                        {"choices": [{"index": 0, "delta": {"content": "from "}}]},
                        {"choices": [{"index": 0, "delta": {"content": "OAI"}}]},
                    ]
                    for c in chunks:
                        self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
                        self.wfile.flush()
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    return
                self._reply(404, b"not found", "text/plain")

            def _reply(self, status, body, ct):
                self.send_response(status)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return H


class FakeVoice(_FakeServer):
    """Speaks the MiniClosedAI voice-backend contract (see voice.py).

    Just enough of the four endpoints (`/health`, `/voices`, `/transcribe`,
    `/speak/stream`) to satisfy the backend-status probe, the voices-list
    reshape, and the per-conversation voice/turn endpoint (task #46). No real
    ASR or TTS — `/transcribe` returns a canned string, `/speak/stream` yields
    one short base64'd chunk + `{done:true}`.

    Set `instance.fail = True` to make every route return 503 — used to test
    the unreachable-backend path without spinning up a separate dead server.
    """
    fail: bool = False

    def _handler_class(self):
        captured = self.captured
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a, **kw): pass

            def do_GET(self):
                if outer.fail:
                    self._reply(503, b"down", "text/plain"); return
                if self.path == "/health":
                    body = json.dumps({
                        "ok": True,
                        "asr_model": "fake-whisper-small",
                        "tts_model": "fake-melo-multilingual",
                        "device": "cpu",
                        "voices_loaded": True,
                    }).encode()
                    self._reply(200, body, "application/json"); return
                if self.path == "/voices":
                    body = json.dumps({
                        "en": [
                            {"id": "en_F_0", "name": "English Female",   "gender": "F"},
                            {"id": "en_M_0", "name": "English Male",     "gender": "M"},
                        ],
                        "es": [
                            {"id": "es_F_0", "name": "Spanish Female",   "gender": "F"},
                            {"id": "es_M_0", "name": "Spanish Male",     "gender": "M"},
                        ],
                    }).encode()
                    self._reply(200, body, "application/json"); return
                self._reply(404, b"not found", "text/plain")

            def do_POST(self):
                if outer.fail:
                    self._reply(503, b"down", "text/plain"); return
                if self.path == "/transcribe":
                    length = int(self.headers.get("Content-Length", "0"))
                    self.rfile.read(length)   # drain multipart, don't bother parsing
                    captured.append({"path": self.path, "len": length})
                    body = json.dumps({
                        "text": "hello world",
                        "language": "en",
                    }).encode()
                    self._reply(200, body, "application/json"); return
                if self.path == "/speak/stream":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length)) if length else {}
                    captured.append({"path": self.path, "payload": payload})
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    # One tiny base64 chunk + the terminal {done:true}.
                    frames = [
                        {"chunk_b64": "AAA=", "sample_rate": 22050},
                        {"done": True, "sample_rate": 22050},
                    ]
                    for f in frames:
                        self.wfile.write(f"data: {json.dumps(f)}\n\n".encode())
                        self.wfile.flush()
                    return
                self._reply(404, b"not found", "text/plain")

            def _reply(self, status, body, ct):
                self.send_response(status)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return H


# ------------------------------------------------------------------
# Test runner (tiny, stdlib only)
# ------------------------------------------------------------------

_RESULTS: list[tuple[str, bool, str]] = []
_TESTS: list[tuple[str, Callable]] = []   # (name, runner) in source order


def test(name: str):
    def deco(fn: Callable):
        def runner():
            t0 = time.perf_counter()
            try:
                fn()
            except _SkipTest as e:
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
        runner.__name__ = fn.__name__
        _TESTS.append((name, runner))
        return runner
    return deco


class _SkipTest(Exception):
    """Raised by a test to mark itself skipped (e.g. when a live service is
    unavailable). The test runner catches this separately from real failures."""


def skip(reason: str = "") -> None:
    """Inside a test body, abort and mark the test skipped with `reason`."""
    raise _SkipTest(reason)


# ------------------------------------------------------------------
# SSE helper — collect events from a streaming response body.
# ------------------------------------------------------------------

def sse_events(raw: bytes | str) -> list[dict]:
    """Parse `data: {json}\n\n` frames out of a streaming response body."""
    text = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
    out: list[dict] = []
    for block in text.split("\n\n"):
        line = block.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload in ("", "[DONE]"):
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return out


# ------------------------------------------------------------------
# Fixture wiring: single TestClient + two fakes reused across tests.
# ------------------------------------------------------------------

client = TestClient(app_mod.app)    # triggers lifespan → init_db against temp DB
fake_ollama = FakeOllama()
fake_openai = FakeOpenAI()
fake_voice = FakeVoice()


def _reseed_builtin_to_fake_ollama() -> None:
    """Redirect the built-in Ollama row to our fake server."""
    client.patch(f"/api/backends/1", json={"base_url": fake_ollama.base_url})


def _add_openai_backend() -> int:
    """Register the fake OpenAI-compat server as a new backend; return its id."""
    r = client.post("/api/backends", json={
        "name": "FakeOAI", "kind": "openai",
        "base_url": f"{fake_openai.base_url}/v1",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _add_voice_backend() -> int:
    """Register the fake voice service as a new backend; return its id."""
    r = client.post("/api/backends", json={
        "name": "FakeVoice", "kind": "voice",
        "base_url": fake_voice.base_url,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


# Probe for a real, running miniclosedai-voice Docker service. When present,
# the "voice integration:" tests below run end-to-end against it; when absent,
# they skip cleanly so CI / a fresh clone without the voice service still goes
# 100% green. Override with `MINICLOSEDAI_VOICE_URL=…` to point at a remote.
_VOICE_URL_PROBED: tuple[str, ...] | None = None  # cached after first call


def _probe_real_voice_service() -> str | None:
    """Return the URL of a reachable voice service (with kind='voice' contract),
    or None if no service responds. Caches the result for the suite lifetime."""
    global _VOICE_URL_PROBED
    if _VOICE_URL_PROBED is not None:
        return _VOICE_URL_PROBED[0] if _VOICE_URL_PROBED else None
    candidates = [
        os.environ.get("MINICLOSEDAI_VOICE_URL"),
        "http://127.0.0.1:8090",
        "http://localhost:8090",
    ]
    import urllib.request, urllib.error
    for url in candidates:
        if not url:
            continue
        url = url.rstrip("/")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as r:
                if r.status == 200:
                    body = json.loads(r.read().decode())
                    if body.get("ok") is True and body.get("tts_model"):
                        _VOICE_URL_PROBED = (url,)
                        return url
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            continue
    _VOICE_URL_PROBED = ()
    return None


# ==================================================================
# Tests
# ==================================================================

@test("migration: schema + built-in seed present")
def _():
    import sqlite3
    conn = sqlite3.connect(_TMP_DB)
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
    assert "backend_id" in cols, f"conversations.backend_id missing: {cols}"
    b = conn.execute("SELECT id, name, kind, is_builtin FROM backends WHERE id=1").fetchone()
    assert b and b["is_builtin"] == 1 and b["kind"] == "ollama"
    conn.close()


@test("migration: init_db is idempotent (safe to re-run)")
def _():
    # Calling init_db again on the same DB must not throw or duplicate rows.
    _db_mod.init_db()
    r = client.get("/api/backends")
    assert r.status_code == 200
    builtins = [b for b in r.json() if b["is_builtin"]]
    assert len(builtins) == 1, f"expected 1 built-in row, got {len(builtins)}"


@test("backends: list contains built-in, api_key is scrubbed")
def _():
    r = client.get("/api/backends")
    assert r.status_code == 200
    j = r.json()
    assert any(b["is_builtin"] for b in j)
    assert all("api_key" not in b for b in j), "api_key must never be returned"
    assert all("api_key_set" in b for b in j), "api_key_set flag missing"


@test("backends: create normalizes trailing slash on base_url")
def _():
    r = client.post("/api/backends", json={
        "name": "TrimSlashes", "kind": "openai",
        "base_url": "http://example.invalid/v1/",
    })
    assert r.status_code == 200
    assert r.json()["base_url"] == "http://example.invalid/v1"
    client.delete(f"/api/backends/{r.json()['id']}")


@test("backends: PATCH rejects immutable 'kind'")
def _():
    bid = _add_openai_backend()
    try:
        r = client.patch(f"/api/backends/{bid}", json={"kind": "ollama"})
        assert r.status_code == 422, r.text
    finally:
        client.delete(f"/api/backends/{bid}")


@test("backends: DELETE built-in is forbidden (403) without force")
def _():
    # Default policy: deleting the built-in needs explicit `?force=true`
    # (the GUI sets this after a stern two-step confirm). This guard
    # protects callers that hand-fire `DELETE /api/backends/1` from
    # accidentally wiping their primary Ollama row.
    r = client.delete("/api/backends/1")
    assert r.status_code == 403
    detail = r.json().get("detail")
    # Detail can be a dict or string depending on FastAPI version — handle both.
    if isinstance(detail, dict):
        assert detail.get("is_builtin") is True
        assert "force=true" in (detail.get("message") or "").lower()
    else:
        assert "built-in" in (detail or "").lower()


@test("backends: DELETE returns 409 when a conversation is bound")
def _():
    bid = _add_openai_backend()
    conv = client.post("/api/conversations", json={
        "title": "bound", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    try:
        r = client.delete(f"/api/backends/{bid}")
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["bound_conversations"], "expected list of bound convs"
        assert detail["bound_conversations"][0]["id"] == conv["id"]
    finally:
        client.delete(f"/api/conversations/{conv['id']}")
        client.delete(f"/api/backends/{bid}")


@test("backends: DELETE ?force=true cascades — backend + bound bots gone")
def _():
    # Settings → Delete should let users blow away a stale endpoint AND the
    # bots pinned to it in one shot, after a two-step confirm in the GUI.
    # The force flag is the server side of that escape hatch.
    bid = _add_openai_backend()
    conv1 = client.post("/api/conversations", json={
        "title": "stale-1", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    conv2 = client.post("/api/conversations", json={
        "title": "stale-2", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    # Sanity: force=true succeeds and reports the cascade count.
    r = client.delete(f"/api/backends/{bid}?force=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["deleted_conversations"] == 2, body
    # Backend gone — verified via the list endpoint since there's no
    # /api/backends/{id} GET (the path only takes DELETE/PATCH).
    listed = client.get("/api/backends").json()
    assert all(b["id"] != bid for b in listed), f"backend {bid} still present: {listed}"
    # Both conversations gone too.
    for c in (conv1, conv2):
        assert client.get(f"/api/conversations/{c['id']}").status_code == 404


@test("backends: DELETE ?force=true on built-in succeeds")
def _():
    # The user explicitly opted in via `?force=true` (or, in the GUI, the
    # extra-stern confirm dialog). We trust them — including for the
    # built-in row. The seed in db.init_db() only re-creates it when the
    # backends table is *fully empty*, so this deletion sticks across
    # restarts as long as at least one other backend exists.
    #
    # Re-add a fresh built-in row after the test so subsequent tests using
    # `_reseed_builtin_to_fake_ollama` (which patches id=1) don't 404.
    import db as db_mod
    bid_other = _add_openai_backend()
    try:
        r = client.delete("/api/backends/1?force=true")
        assert r.status_code == 200, r.text
        # Backend gone from the listing.
        listed = client.get("/api/backends").json()
        assert all(b["id"] != 1 for b in listed), listed
    finally:
        # Manually re-seed so later tests find the built-in at id=1.
        with db_mod.get_conn() as conn:
            conn.execute(
                """INSERT INTO backends (id, name, kind, base_url, is_builtin, enabled)
                   VALUES (1, 'Ollama (built-in)', 'ollama', 'http://localhost:11434', 1, 1)"""
            )
            conn.commit()
        client.delete(f"/api/backends/{bid_other}")


@test("backends: init_db re-seeds built-in only when backends table is empty")
def _():
    # The seed change in db.init_db() must NOT resurrect the built-in when
    # the user has any other backends. This is the "deletion sticks" guarantee.
    import db as db_mod
    # 1. Wipe everything, including the built-in.
    with db_mod.get_conn() as conn:
        conn.execute("DELETE FROM backends")
        conn.commit()
    # 2. Add a non-built-in backend, then run init_db. The built-in should
    #    NOT come back, because backend_count > 0.
    bid = _add_openai_backend()
    try:
        db_mod.init_db()
        listed = client.get("/api/backends").json()
        assert all(not b.get("is_builtin") for b in listed), listed
        assert any(b["id"] == bid for b in listed), listed
    finally:
        # 3. Wipe again; init_db on an empty table SHOULD re-seed the built-in.
        with db_mod.get_conn() as conn:
            conn.execute("DELETE FROM backends")
            conn.commit()
        db_mod.init_db()
        listed = client.get("/api/backends").json()
        assert any(b.get("is_builtin") for b in listed), \
            f"built-in didn't re-seed on empty table: {listed}"


@test("backends: DELETE ?force=true with no bound bots is a no-op cascade")
def _():
    # Force-delete a clean backend (no bots) — should still succeed and
    # report 0 deletions, not error or count a phantom bot.
    bid = _add_openai_backend()
    r = client.delete(f"/api/backends/{bid}?force=true")
    assert r.status_code == 200, r.text
    assert r.json()["deleted_conversations"] == 0


@test("backends: /status reports reachable for our fake")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.get("/api/backends/1/status")
    assert r.status_code == 200
    j = r.json()
    assert j["running"] is True
    assert j["kind"] == "ollama"


@test("backends: /models returns the fake Ollama model list")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.get("/api/backends/1/models")
    assert r.status_code == 200
    names = [m["name"] for m in r.json()["models"]]
    assert "ollama-a:3b" in names and "ollama-b:7b" in names


@test("backends: /test probes a draft config without saving")
def _():
    r = client.post("/api/backends/test", json={
        "name": "draft", "kind": "openai",
        "base_url": f"{fake_openai.base_url}/v1",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["running"] is True
    assert j["models_count"] == 2


@test("voice backend: kind=voice round-trips through create + list")
def _():
    bid = _add_voice_backend()
    try:
        # POST returned the row; list contains it with kind preserved + api_key scrubbed.
        all_backends = client.get("/api/backends").json()
        b = next(x for x in all_backends if x["id"] == bid)
        assert b["kind"] == "voice"
        assert b["base_url"] == fake_voice.base_url
        assert b["api_key_set"] is False
        assert b["enabled"] == 1
    finally:
        client.delete(f"/api/backends/{bid}")


@test("voice backend: /status reports reachable via /health (and unreachable on failure)")
def _():
    bid = _add_voice_backend()
    try:
        j = client.get(f"/api/backends/{bid}/status").json()
        assert j == {"running": True, "base_url": fake_voice.base_url,
                     "kind": "voice", "enabled": True}, j
        # Toggle the fake to 503 — /status now reports unreachable, no exception.
        fake_voice.fail = True
        try:
            j2 = client.get(f"/api/backends/{bid}/status").json()
            assert j2["running"] is False, j2
        finally:
            fake_voice.fail = False
    finally:
        client.delete(f"/api/backends/{bid}")


@test("voice backend: /models reshapes /voices into <lang>/<voice_id> entries")
def _():
    bid = _add_voice_backend()
    try:
        j = client.get(f"/api/backends/{bid}/models").json()
        assert j["running"] is True
        names = {m["name"] for m in j["models"]}
        # FakeVoice ships 2 English + 2 Spanish voices.
        assert {"en/en_F_0", "en/en_M_0", "es/es_F_0", "es/es_M_0"}.issubset(names), names
        # Details carry the language + voice_id so the dropdowns can group cleanly.
        m = next(m for m in j["models"] if m["name"] == "es/es_F_0")
        assert m["details"]["language"] == "es"
        assert m["details"]["voice_id"] == "es_F_0"
        assert m["details"]["display"] == "Spanish Female"
        assert m["details"]["family"] == "voice"
    finally:
        client.delete(f"/api/backends/{bid}")


@test("voice backend: /test draft probe reports reachable + voice count")
def _():
    r = client.post("/api/backends/test", json={
        "name": "voice-draft", "kind": "voice",
        "base_url": fake_voice.base_url,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["running"] is True
    # /models for voice returns the reshaped voices list; the count is the total
    # voices across all languages (2 EN + 2 ES = 4).
    assert j["models_count"] == 4, j


@test("voice endpoints: /voice/transcribe proxies through to the backend")
def _():
    vbid = _add_voice_backend()
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "voice-transcribe", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(
            f"/api/conversations/{c['id']}/voice/transcribe",
            files={"audio": ("hello.wav", b"\x00\x00\x00\x00", "audio/wav")},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["text"] == "hello world"
        assert j["language"] == "en"
        # Sanity: FakeVoice captured the request.
        assert any(p.get("path") == "/transcribe" for p in fake_voice.captured)
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{vbid}")


@test("voice endpoints: /voice/speak streams SSE chunks + uses defaults from /voices")
def _():
    vbid = _add_voice_backend()
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "voice-speak", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/voice/speak",
                           json={"text": "Hola"}) as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        # FakeVoice emits one chunk + one {done:true}.
        assert any("chunk_b64" in e for e in evts), evts
        assert any(e.get("done") for e in evts), evts
        # Defaulted to the first voice (en/en_F_0) since voice_settings is empty.
        speak_calls = [p["payload"] for p in fake_voice.captured if p.get("path") == "/speak/stream"]
        assert speak_calls, fake_voice.captured
        assert speak_calls[-1]["voice"] == "en_F_0"
        assert speak_calls[-1]["language"] == "en"
        assert speak_calls[-1]["text"] == "Hola"
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{vbid}")


@test("voice endpoints: /voice/turn chains ASR → chat → TTS into one SSE stream")
def _():
    vbid = _add_voice_backend()
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "voice-turn", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        fake_voice.captured.clear()
        with client.stream(
            "POST", f"/api/conversations/{c['id']}/voice/turn",
            files={"audio": ("greeting.wav", b"\x00\x00\x00\x00", "audio/wav")},
        ) as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        kinds = [next(iter(e.keys())) for e in evts if e]
        # Order: transcript first, then LLM chunks, then audio chunks, then end.
        assert "transcript" in kinds, kinds
        assert "chunk" in kinds, kinds          # FakeOllama emits the assistant text
        assert "audio_chunk_b64" in kinds, kinds
        assert any(e.get("end") for e in evts), evts
        # The transcript reached FakeOllama as the user message verbatim.
        ollama_call = next(
            p["payload"] for p in fake_ollama.captured if p["path"] == "/api/chat"
        )
        last_user = next(m for m in reversed(ollama_call["messages"]) if m["role"] == "user")
        assert last_user["content"] == "hello world"
        # And the turn was persisted on the conv.
        got = client.get(f"/api/conversations/{c['id']}").json()
        roles = [m["role"] for m in got["messages"]]
        assert roles == ["user", "assistant"], roles
        assert got["messages"][0]["content"] == "hello world"
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{vbid}")


@test("call mode: composer ships a #call-btn + app.js carries the WebRTC module")
def _():
    # The 📞 button is HTML markup; the JS module wires getUserMedia + RTCPeerConnection
    # + DataChannel handling. Both must be present in the served assets.
    html = client.get("/static/index.html").text
    assert 'id="call-btn"' in html, "call-btn missing from index.html"
    assert "Call the bot" in html, "call-btn aria-label / tooltip missing"
    js = client.get("/static/app.js").text
    assert "_refreshCallAffordance" in js, "call affordance gate missing"
    assert "_startCall" in js and "_endCall" in js, "call lifecycle helpers missing"
    assert "RTCPeerConnection" in js, "WebRTC peer connection setup missing"
    assert "EventSource" in js, "SSE consumer for transcript/chunk events missing"
    assert "initCallButton" in js, "initCallButton hook missing"


@test("voice endpoints: 404 when no voice backend is configured")
def _():
    # No voice backend in the DB. Endpoints must surface a clear 404 rather
    # than blowing up trying to call a phantom backend.
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "no-voice-backend", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(
            f"/api/conversations/{c['id']}/voice/transcribe",
            files={"audio": ("x.wav", b"\x00", "audio/wav")},
        )
        assert r.status_code == 404
        assert "Settings" in r.json()["detail"], r.json()
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("voice integration: /voice/speak streams real audio from the live voice service")
def _():
    # Live integration — runs only when miniclosedai-voice is reachable.
    # Validates that MiniClosedAI's /voice/speak proxy actually drives Piper
    # end-to-end (the FakeVoice tests only check the proxy contract).
    voice_url = _probe_real_voice_service()
    if not voice_url:
        skip("no voice service reachable (start miniclosedai-voice container)")
    bid = client.post("/api/backends", json={
        "name": "live-voice", "kind": "voice", "base_url": voice_url,
    }).json()["id"]
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "speak-live", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/voice/speak",
                           json={"text": "Hello from the integration suite.",
                                 "voice": "en_US-amy-medium", "language": "en"}) as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        chunks = [e for e in evts if "chunk_b64" in e]
        assert chunks, f"no audio chunks: {evts[:3]}"
        assert any(e.get("done") for e in evts), f"no terminal done event: {evts}"
        # Each chunk is base64-encoded int16 PCM at the sample_rate advertised.
        first = chunks[0]
        assert first.get("sample_rate", 0) > 0
        raw = base64.b64decode(first["chunk_b64"])
        assert len(raw) >= 320, f"first chunk too small ({len(raw)} bytes)"
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("voice integration: /voice/transcribe round-trips real TTS through real ASR")
def _():
    # Synthesize speech via /speak, hand the WAV back to /voice/transcribe,
    # and verify the round-trip recovers recognizable text. Skips when the
    # voice service isn't running.
    voice_url = _probe_real_voice_service()
    if not voice_url:
        skip("no voice service reachable (start miniclosedai-voice container)")
    import urllib.request
    # 1. Synthesize "this is a test" directly on the voice server.
    req = urllib.request.Request(
        f"{voice_url}/speak",
        data=json.dumps({"text": "This is a test of the voice integration.",
                         "voice": "en_US-amy-medium", "language": "en"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        wav = r.read()
    assert wav.startswith(b"RIFF"), f"expected WAV header, got {wav[:8]!r}"

    # 2. Register the live backend + a conv, then transcribe via MiniClosedAI's proxy.
    bid = client.post("/api/backends", json={
        "name": "live-voice", "kind": "voice", "base_url": voice_url,
    }).json()["id"]
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "transcribe-live", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(
            f"/api/conversations/{c['id']}/voice/transcribe",
            files={"audio": ("test.wav", wav, "audio/wav")},
        )
        assert r.status_code == 200, r.text
        out = r.json()
        text = (out.get("text") or "").lower()
        # Whisper-small isn't perfect — accept partial match of distinctive words.
        assert "test" in text or "voice" in text or "integration" in text, \
            f"no recognizable word in transcript: {text!r}"
        assert out.get("language"), out
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("voice backend: conversations.voice_settings column round-trips through GET")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "voice-prefs", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        got = client.get(f"/api/conversations/{c['id']}").json()
        # New conv has empty voice_settings — JSON-decoded by row_to_dict.
        assert "voice_settings" in got
        assert got["voice_settings"] == {}, got["voice_settings"]
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("/api/voices: 404 when no voice backend is registered")
def _():
    # No voice backend in default seed → endpoint refuses cleanly.
    r = client.get("/api/voices")
    assert r.status_code == 404, r.text


@test("voice picker affordance: visibility tracks /api/backends, not /api/voices catalog")
def _():
    # The frontend gate `_hasVoiceBackend()` reads `backendCache` (populated
    # by `/api/backends`), NOT the `/api/voices` catalog. This test pins the
    # contract on the server side so the frontend's affordance can rely on
    # it: `/api/backends` reports whether a voice backend is registered;
    # `/api/voices` reports the catalog (which may be empty / unreachable
    # even when the backend exists). Picker should appear/disappear based on
    # the former so it stays in sync with the mic + call buttons.
    # 1. No voice backend → /api/backends has none → picker HIDDEN.
    backends = client.get("/api/backends").json()
    assert not any(b.get("kind") == "voice" for b in backends), (
        f"unexpected voice backend in default fixture: {backends}"
    )
    # 2. Register a voice backend → /api/backends has one → picker VISIBLE
    #    (the frontend doesn't need to round-trip through /api/voices to know).
    vid = _add_voice_backend()
    try:
        backends = client.get("/api/backends").json()
        voice_rows = [b for b in backends if b.get("kind") == "voice" and b.get("enabled")]
        assert len(voice_rows) == 1, voice_rows
        # And /api/voices independently works when the backend is reachable —
        # this is what populates the picker contents (not its visibility).
        cat = client.get("/api/voices")
        assert cat.status_code == 200, cat.text
        assert cat.json()["backend_id"] == vid
    finally:
        client.delete(f"/api/backends/{vid}")
    # 3. After delete → /api/backends has none again → picker HIDDEN.
    backends = client.get("/api/backends").json()
    assert not any(b.get("kind") == "voice" for b in backends)


@test("/api/voices: flat list with id/name/language/gender from the voice backend")
def _():
    vid = _add_voice_backend()
    try:
        r = client.get("/api/voices")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["backend_id"] == vid
        voices = j["voices"]
        # FakeVoice ships 2 English + 2 Spanish.
        assert len(voices) == 4, voices
        # Every entry has the four expected keys.
        for v in voices:
            assert {"id", "name", "language"}.issubset(v.keys()), v
        langs = sorted({v["language"] for v in voices})
        assert langs == ["en", "es"], langs
        ids = sorted(v["id"] for v in voices)
        assert ids == ["en_F_0", "en_M_0", "es_F_0", "es_M_0"], ids
    finally:
        client.delete(f"/api/backends/{vid}")


@test("PATCH conversation: voice_settings persists round-trip")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "voice-pick", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        # Set
        r = client.patch(f"/api/conversations/{c['id']}", json={
            "voice_settings": {"voice_id": "en_F_0", "language": "en"},
        })
        assert r.status_code == 200, r.text
        got = client.get(f"/api/conversations/{c['id']}").json()
        assert got["voice_settings"] == {"voice_id": "en_F_0", "language": "en"}
        # Clear with empty dict
        r = client.patch(f"/api/conversations/{c['id']}", json={"voice_settings": {}})
        assert r.status_code == 200, r.text
        assert client.get(f"/api/conversations/{c['id']}").json()["voice_settings"] == {}
        # Reject non-object
        r = client.patch(f"/api/conversations/{c['id']}", json={"voice_settings": "nope"})
        assert r.status_code == 422 or r.status_code == 400, r.text
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("static: voice picker markup present + JS symbols")
def _():
    html = client.get("/").text
    # The voice picker sits to the left of the model picker in the topbar.
    assert 'id="voice-picker"' in html
    assert 'id="voice-select"' in html
    js = client.get("/static/app.js").text
    for sym in ("loadVoices", "_renderVoicePicker", "_setVoiceSelectFromConv", "_buildVoiceSettingsPatch",
                "_hasVoiceBackend", "_refreshVoicePickerAffordance"):
        assert sym in js, f"missing {sym} in served app.js"


@test("/api/models: aggregated shape + legacy back-compat keys")
def _():
    _reseed_builtin_to_fake_ollama()
    bid = _add_openai_backend()
    try:
        r = client.get("/api/models")
        assert r.status_code == 200
        j = r.json()
        assert "backends" in j, "aggregated shape missing"
        by_id = {b["id"]: b for b in j["backends"]}
        assert 1 in by_id and bid in by_id
        assert by_id[1]["running"] is True
        assert by_id[bid]["running"] is True
        assert j["ollama_running"] is True  # legacy flag preserved
        assert any(m["name"] == "ollama-a:3b" for m in j["models"])
    finally:
        client.delete(f"/api/backends/{bid}")


@test("/api/models: voice backends are NOT listed — TTS voices stay out of the LLM picker")
def _():
    _reseed_builtin_to_fake_ollama()
    vid = _add_voice_backend()
    try:
        r = client.get("/api/models")
        assert r.status_code == 200
        j = r.json()
        kinds = [b["kind"] for b in j["backends"]]
        assert "voice" not in kinds, (
            f"voice backend leaked into /api/models — kinds: {kinds}. "
            "TTS voices would pollute the LLM model dropdown in the chat topbar."
        )
        # The voice backend itself still exists via /api/backends — only the
        # LLM-picker endpoint excludes it.
        all_backends = client.get("/api/backends").json()
        assert any(b["id"] == vid and b["kind"] == "voice" for b in all_backends)
    finally:
        client.delete(f"/api/backends/{vid}")


@test("conversations: CRUD roundtrip + backend_id persists")
def _():
    bid = _add_openai_backend()
    try:
        c = client.post("/api/conversations", json={
            "title": "roundtrip", "model": "openai-a-4b",
            "backend_id": bid, "temperature": 0.3, "think": False,
        }).json()
        cid = c["id"]
        assert c["backend_id"] == bid
        assert c["params"]["think"] is False
        assert c["params"]["temperature"] == 0.3

        # PATCH
        r = client.patch(f"/api/conversations/{cid}", json={"title": "renamed"})
        assert r.status_code == 200

        got = client.get(f"/api/conversations/{cid}").json()
        assert got["title"] == "renamed"
        assert got["backend_id"] == bid

        # Clear (keeps config)
        client.post(f"/api/conversations/{cid}/clear")
        assert client.get(f"/api/conversations/{cid}").json()["messages"] == []
    finally:
        client.delete(f"/api/conversations/{cid}")
        client.delete(f"/api/backends/{bid}")


@test("conversations: PATCH null clears a saved param (the recent fix)")
def _():
    bid = _add_openai_backend()
    try:
        c = client.post("/api/conversations", json={
            "title": "clears", "model": "openai-a-4b", "backend_id": bid,
            "max_thinking_tokens": 80, "think": False,
        }).json()
        cid = c["id"]
        assert c["params"]["max_thinking_tokens"] == 80
        assert c["params"]["think"] is False

        # PATCH with explicit nulls → keys should be REMOVED.
        r = client.patch(f"/api/conversations/{cid}",
                         json={"max_thinking_tokens": None, "think": None})
        assert r.status_code == 200

        got = client.get(f"/api/conversations/{cid}").json()
        assert "max_thinking_tokens" not in got["params"], \
            f"max_thinking_tokens still present: {got['params']}"
        assert "think" not in got["params"], \
            f"think still present: {got['params']}"
    finally:
        client.delete(f"/api/conversations/{cid}")
        client.delete(f"/api/backends/{bid}")


@test("conversations: PATCH with backend_id=null is rejected (400)")
def _():
    c = client.post("/api/conversations", json={
        "title": "nobid", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.patch(f"/api/conversations/{c['id']}", json={"backend_id": None})
        assert r.status_code == 400
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("avatar: new bot has none; PUT sets it; list + GET expose it; DELETE clears")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "avatar", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    cid = c["id"]
    # 1x1 transparent PNG data URL — a valid `data:image/*` payload.
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0"
           "lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
    try:
        # New bot: avatar is null.
        assert client.get(f"/api/conversations/{cid}").json()["avatar"] is None
        assert next(b for b in client.get("/api/conversations").json()
                    if b["id"] == cid)["avatar"] is None

        # Set it.
        r = client.put(f"/api/conversations/{cid}/avatar", json={"avatar": png})
        assert r.status_code == 200, r.text
        assert client.get(f"/api/conversations/{cid}").json()["avatar"] == png
        # The list endpoint must include it so cards render without N extra fetches.
        assert next(b for b in client.get("/api/conversations").json()
                    if b["id"] == cid)["avatar"] == png

        # Clear it.
        assert client.delete(f"/api/conversations/{cid}/avatar").status_code == 200
        assert client.get(f"/api/conversations/{cid}").json()["avatar"] is None
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("avatar: rejects non-image data URLs (400) and oversize images (413)")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "avatar-bad", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    cid = c["id"]
    try:
        # Not a data:image/* URL.
        assert client.put(f"/api/conversations/{cid}/avatar",
                          json={"avatar": "https://example.com/x.png"}).status_code == 400
        assert client.put(f"/api/conversations/{cid}/avatar",
                          json={"avatar": "data:text/plain;base64,aGVsbG8="}).status_code == 400
        # Over the size cap.
        huge = "data:image/png;base64," + ("A" * 1_600_000)
        assert client.put(f"/api/conversations/{cid}/avatar",
                          json={"avatar": huge}).status_code == 413
        # None of the rejects should have stuck.
        assert client.get(f"/api/conversations/{cid}").json()["avatar"] is None
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("avatar: set/clear on a missing conversation → 404")
def _():
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    assert client.put("/api/conversations/99999999/avatar",
                      json={"avatar": png}).status_code == 404
    assert client.delete("/api/conversations/99999999/avatar").status_code == 404


@test("per-conv /chat: config lock rejects extra fields (422)")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "locked", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        for bad in ({"message": "hi", "temperature": 0.1},
                    {"message": "hi", "model": "override"},
                    {"message": "hi", "system_prompt": "nope"}):
            r = client.post(f"/api/conversations/{c['id']}/chat", json=bad)
            assert r.status_code == 422, f"should reject {bad}, got {r.status_code}"
            assert "extra" in r.text.lower()
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("per-conv /chat: routes to bot's backend (Ollama)")
def _():
    _reseed_builtin_to_fake_ollama()
    fake_ollama.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "olla-chat", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat",
                        json={"message": "hi"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["response"] == "Hello world!"
        assert j["backend_id"] == 1
        # Fake Ollama should have seen exactly one call.
        assert len(fake_ollama.captured) >= 1
        assert fake_ollama.captured[-1]["payload"]["model"] == "ollama-a:3b"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("per-conv /chat: routes to bot's backend (OpenAI-compat)")
def _():
    bid = _add_openai_backend()
    fake_openai.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "oai-chat", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat",
                        json={"message": "hi"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert "Hello from OAI" in j["response"]
        assert j["backend_id"] == bid
        sent = fake_openai.captured[-1]["payload"]
        assert sent["model"] == "openai-a-4b"
        assert sent["stream"] is True
        assert "top_k" not in sent, "top_k must be dropped for OpenAI schema"
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("per-conv /chat/stream: SSE frames include thinking + content + end")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "sse", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi"}) as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        kinds = [next(iter(e.keys())) for e in evts]
        assert "thinking" in kinds
        assert "chunk" in kinds
        assert any(e.get("end") for e in evts)
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("max_thinking_tokens: soft cap — content still arrives after truncation")
def _():
    bid = _add_openai_backend()  # fake OAI emits 3 reasoning frames
    c = client.post("/api/conversations", json={
        "title": "cap", "model": "openai-a-4b",
        "backend_id": bid, "max_thinking_tokens": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi"}) as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        # Must see a truncated notice
        assert any(e.get("thinking_truncated") for e in evts)
        # Must STILL see content chunks (soft cap keeps stream open)
        chunks = [e["chunk"] for e in evts if "chunk" in e]
        assert chunks, "content chunks missing — cap hard-killed the stream (regression!)"
        assert "".join(chunks).startswith("Hello"), \
            f"unexpected content after truncate: {chunks}"
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("refresh-resilience: background generation persists user + assistant turn")
def _():
    # The persisted GUI path runs generation in a background task; the turn must
    # land in the DB so it survives a refresh. Drain the SSE, then confirm both
    # messages are persisted and the in-flight flag has cleared.
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "resilience", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi", "persist": True}) as r:
            body = b"".join(r.iter_bytes())
        assert any(e.get("end") for e in sse_events(body))
        got = client.get(f"/api/conversations/{c['id']}").json()
        roles = [m["role"] for m in got["messages"]]
        assert roles == ["user", "assistant"], roles
        assert got["messages"][-1]["content"] == "Hello world!", got["messages"][-1]
        assert got["generating"] is False
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("refresh-resilience: GET generation/stream re-attaches and replays the reply")
def _():
    # After a refresh the client re-attaches via the resume endpoint. While the
    # finished generation is still in its eviction grace window, the endpoint
    # replays the buffered chunks and a terminal end frame.
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "resume", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi", "persist": True}) as r:
            b"".join(r.iter_bytes())
        with client.stream("GET", f"/api/conversations/{c['id']}/generation/stream") as r2:
            body2 = b"".join(r2.iter_bytes())
        evts = sse_events(body2)
        assert any(e.get("end") for e in evts)
        chunks = "".join(e["chunk"] for e in evts if "chunk" in e)
        assert "Hello" in chunks, chunks
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("refresh-resilience: resume endpoint with no in-flight generation → just end")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "no-gen", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("GET", f"/api/conversations/{c['id']}/generation/stream") as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        assert any(e.get("end") for e in evts)
        assert not any("chunk" in e for e in evts), evts
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("refresh-resilience: generating flag defaults False; cancel is a no-op when idle")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "idle", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        assert client.get(f"/api/conversations/{c['id']}").json()["generating"] is False
        res = client.post(f"/api/conversations/{c['id']}/generation/cancel").json()
        assert res == {"ok": True, "cancelled": False}, res
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("refresh-resilience: failed background generation persists only the user turn")
def _():
    # Generation runs in the background; if the backend is unreachable the task
    # records an error and persists NO assistant message — but the user's turn
    # (saved up-front) must remain so a refresh still shows what was asked.
    bid = client.post("/api/backends", json={
        "name": "DeadOllama", "kind": "ollama",
        "base_url": "http://127.0.0.1:59999",  # nothing listening → ConnectError
    }).json()["id"]
    c = client.post("/api/conversations", json={
        "title": "deadbackend", "model": "ghost:1b", "backend_id": bid,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi", "persist": True}) as r:
            body = b"".join(r.iter_bytes())
        evts = sse_events(body)
        assert any("error" in e for e in evts), evts
        assert any(e.get("end") for e in evts)
        got = client.get(f"/api/conversations/{c['id']}").json()
        assert [m["role"] for m in got["messages"]] == ["user"], got["messages"]
        assert got["generating"] is False
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("refresh-resilience: cancelling a running generation marks it done + truncates the reply")
def _():
    # Stop must truly cancel the server-side task, not just disconnect the view.
    # TestClient buffers streaming responses (hiding the mid-flight state), so we
    # drive the background generator directly to control timing: a slow fake
    # keeps it running, we cancel, then assert it stops before producing the full
    # reply and is marked finished (so a reloading client's resume won't hang).
    import asyncio
    _reseed_builtin_to_fake_ollama()
    fake_ollama.chat_per_chunk_delay = 0.2  # frames at 0.2/0.4/0.6/0.8s
    c = client.post("/api/conversations", json={
        "title": "cancel", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    cid = c["id"]
    backend = app_mod._load_backend(1)
    eff = {"model": "ollama-a:3b", "temperature": 0.7, "max_tokens": 512,
           "top_p": 0.9, "top_k": 40, "think": False, "max_thinking_tokens": None}
    snap = app_mod._chat_snapshot(eff, backend)
    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": "hi"}]

    async def scenario():
        gen = app_mod._new_generation()
        app_mod._generations[cid] = gen
        gen["task"] = asyncio.create_task(app_mod._run_generation(
            cid, "ollama-a:3b", messages, eff, backend, [], gen, snap, [], "/test"))
        await asyncio.sleep(0.3)             # one frame in — definitely running
        running = gen["status"]
        gen["task"].cancel()
        await asyncio.sleep(0.4)             # let the CancelledError handler finish
        return running, gen["status"]

    try:
        running, after = asyncio.run(scenario())
        assert running == "running", running
        assert after == "done", after       # cancelled gens are marked finished
        got = client.get(f"/api/conversations/{cid}").json()
        # The trailing content frame ("world", at 0.6s) was never reached, so the
        # full reply must not have been persisted — generation was truncated.
        assert all("world" not in (m.get("content") or "")
                   for m in got["messages"]), got["messages"]
        assert got["generating"] is False
    finally:
        fake_ollama.chat_per_chunk_delay = 0.0
        app_mod._generations.pop(cid, None)
        client.delete(f"/api/conversations/{cid}")


@test("refresh-resilience: a non-persist stream starts no background generation")
def _():
    # The direct (one-shot API) path must not engage the resilience machinery:
    # nothing persisted, no in-flight flag, no cancellable generation.
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "direct", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi"}) as r:  # no persist flag
            body = b"".join(r.iter_bytes())
        assert any(e.get("end") for e in sse_events(body))
        got = client.get(f"/api/conversations/{c['id']}").json()
        assert got["messages"] == [], got["messages"]
        assert got["generating"] is False
        assert client.post(
            f"/api/conversations/{c['id']}/generation/cancel").json()["cancelled"] is False
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("thinking control: Off injects enable_thinking=false + /no_think")
def _():
    bid = _add_openai_backend()
    fake_openai.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "nothink", "model": "openai-a-4b",
        "backend_id": bid, "think": False,
    }).json()
    try:
        client.post(f"/api/conversations/{c['id']}/chat", json={"message": "hi"})
        sent = fake_openai.captured[-1]["payload"]
        assert sent.get("chat_template_kwargs", {}).get("enable_thinking") is False, sent
        # Last user message should contain /no_think
        last_user = next(m for m in reversed(sent["messages"]) if m["role"] == "user")
        assert "/no_think" in last_user["content"], last_user
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("thinking control: Low/Medium/High → reasoning_effort")
def _():
    bid = _add_openai_backend()
    fake_openai.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "effort", "model": "openai-a-4b",
        "backend_id": bid, "think": "high",
    }).json()
    try:
        client.post(f"/api/conversations/{c['id']}/chat", json={"message": "hi"})
        sent = fake_openai.captured[-1]["payload"]
        assert sent.get("reasoning_effort") == "high", sent
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("/v1/chat/completions: non-streaming routes through bot's backend")
def _():
    bid = _add_openai_backend()
    fake_openai.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "v1-nonstream", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    try:
        r = client.post("/v1/chat/completions", json={
            "model": str(c["id"]),
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        assert r.status_code == 200
        j = r.json()
        assert j["object"] == "chat.completion"
        assert "Hello from OAI" in j["choices"][0]["message"]["content"]
        assert fake_openai.captured, "OpenAI backend wasn't called"
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("/v1/chat/completions: streaming emits OpenAI-shape SSE (+ [DONE])")
def _():
    bid = _add_openai_backend()
    c = client.post("/api/conversations", json={
        "title": "v1-stream", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    try:
        with client.stream("POST", "/v1/chat/completions", json={
            "model": str(c["id"]),
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }) as r:
            body = b"".join(r.iter_bytes())
        assert b"data: [DONE]" in body
        text_body = body.decode()
        # At least one chunk with chat.completion.chunk + a delta.content
        assert "chat.completion.chunk" in text_body
        assert "delta" in text_body
        assert "Hello " in text_body
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("/v1/chat/completions: invalid `model` returns 400")
def _():
    r = client.post("/v1/chat/completions", json={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 400
    assert "conversation ID" in r.json()["detail"]


@test("/v1/models: lists saved conversations")
def _():
    bid = _add_openai_backend()
    c = client.post("/api/conversations", json={
        "title": "v1models", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    try:
        r = client.get("/v1/models")
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["data"]]
        assert str(c["id"]) in ids
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("legacy /api/chat: still works with explicit backend_id")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.post("/api/chat", json={
        "model": "ollama-a:3b",
        "messages": [{"role": "user", "content": "hi"}],
        "backend_id": 1,
    })
    assert r.status_code == 200
    assert r.json()["response"] == "Hello world!"


@test("static: / serves index.html with activity bar + pages")
def _():
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    # The Bots list is now the landing surface — the Dashboard nav icon was
    # removed and the chat page is reached by drilling into a bot.
    assert 'data-page="bots"' in body
    assert 'class="activity-bar"' in body
    assert 'class="page page-dashboard"' in body
    assert 'class="page page-bots"' in body
    assert 'class="page page-settings"' in body
    assert 'id="breadcrumb-back"' in body
    # API Code modal grew a "Bot #N" copy pill in the header.
    assert 'id="copy-bot-id"' in body
    assert 'id="modal-bot-id"' in body
    # Bots page has its own filter input + list container.
    assert 'id="bots-filter"' in body
    assert 'id="bots-list"' in body
    # Sidebar Knowledge (RAG) + Extensions (MCP) panels.
    assert 'id="kb-list"' in body
    assert 'id="kb-add-btn"' in body
    assert 'id="mcp-list"' in body
    assert 'id="mcp-url-input"' in body
    # Shared hidden file input for per-card "add knowledge".
    assert 'id="bots-kb-file"' in body
    # Manage Knowledge + Manage Extensions modals.
    assert 'id="kb-modal-backdrop"' in body
    assert 'id="kb-modal-list"' in body
    assert 'id="mcp-modal-backdrop"' in body
    assert 'id="mcp-modal-list"' in body
    # Evals panel + modal.
    assert 'id="evals-manage-btn"' in body
    assert 'id="eval-modal-backdrop"' in body
    assert 'id="eval-run-btn"' in body
    # Searchable model picker (native <select> kept as hidden backing state).
    assert 'id="model-picker-btn"' in body
    assert 'id="model-picker-search"' in body
    assert 'id="model-select"' in body
    # Apps page header + toolbar wiring: import button, file input, the
    # list/grid view toggle (mirrors the Bots page's toggle one-for-one).
    assert 'id="apps-list"' in body
    assert 'id="apps-import-btn"' in body
    assert 'id="apps-import-file"' in body
    assert 'id="apps-view-list"' in body
    assert 'id="apps-view-grid"' in body
    # The global tooltip element — a single fixed-positioned <body> child
    # that every [data-tooltip] hover hijacks. Without this, tooltips fall
    # back to per-trigger pseudo-elements that get clipped by ancestor
    # `overflow: hidden`. Guard the architectural decision in CI.
    assert 'id="global-tooltip"' in body
    # Backend-picker modal is shared between bot and app import flows.
    assert 'id="import-modal-backdrop"' in body


@test("static: app.js is served and contains recent helpers")
def _():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    needles = [
        # Pre-existing helpers
        "initActivityBar", "loadBackends", "prettifyJSONInMarkdown",
        "_selectModelOption", "flushPendingSave",
        "openInlineEditor", "_appendEditButton",
        # Bots-page + nav drill-in
        "renderBotsPage", "renderBreadcrumb", "applyActivePage",
        "_BOTS_AREA", "onBotsPageEntered", "initBotsUI",
        # Unread / streaming indicator state machine
        "_streaming", "_unread",
        "_refreshUnreadUI", "_onStreamStart", "_onStreamEnd", "_markConvViewed",
        # Row actions on bot cards + scoped API code modal
        "deleteConvById", "openApiCodeForConv", "_modalConvId",
        # Knowledge (RAG) + Extensions (MCP) panels
        "loadKnowledge", "addKnowledgeFiles", "initKnowledgeUI",
        "loadMcp", "addMcpServer", "initMcpUI",
        # Per-card quick-add actions
        "_uploadKnowledgeToConv", "_addMcpToConv",
        "_botCardFlash", "_triggerKbUpload",
        # Manage Knowledge + Manage Extensions modals
        "openKnowledgeModal", "_loadKbModal", "initKnowledgeModalUI",
        "openMcpModal", "_loadMcpModal", "initMcpModalUI",
        # Evals
        "loadEvals", "openEvalModal", "runEvals", "autoImproveLoop",
        "initEvalsUI", "initEvalModalUI",
        # Searchable model picker
        "initModelPicker", "_rebuildModelPicker", "_syncModelPickerLabel",
        # Application export / import — mirrors the bot pattern at the apps level.
        "_handleAppImportFile", "_runAppImport", "_downloadApp",
        "initAppsImportUI",
        # Apps page grid/list view toggle (parallels the bots toggle).
        "_APPS_VIEW_KEY", "_applyAppsView", "_setAppsView",
        # Global tooltip system — one fixed-positioned element on <body>
        # that escapes every stacking context / overflow clip.
        "initGlobalTooltip", "_showGlobalTooltip", "_hideGlobalTooltip",
    ]
    for needle in needles:
        assert needle in r.text, f"missing {needle} in served app.js"


def _seed_conv_with_turn(title: str) -> int:
    """Create a conversation and stream a single turn into it so message[0]/[1]
    exist. Uses the fake Ollama backend so we don't depend on real upstreams.
    """
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": title, "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    # Stream one turn with persist=true so messages[0] (user) and messages[1]
    # (assistant) get written to the conv.
    with client.stream(
        "POST", f"/api/conversations/{c['id']}/chat/stream",
        json={"message": "hi", "persist": True},
    ) as r:
        for _ in r.iter_bytes():
            pass
    return c["id"]


def _new_fake_conv(title: str) -> int:
    """Create an empty conv on the fake Ollama backend (no turns)."""
    _reseed_builtin_to_fake_ollama()
    return client.post("/api/conversations", json={
        "title": title, "model": "ollama-a:3b", "backend_id": 1,
    }).json()["id"]


@test("knowledge: add a document → chunks + embeds, returns summary")
def _():
    cid = _new_fake_conv("kb-add")
    r = client.post(
        f"/api/conversations/{cid}/knowledge",
        json={"filename": "book.txt", "text": "The alpha protocol governs alpha sequences."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "book.txt"
    assert body["chunk_count"] >= 1
    assert body["char_count"] > 0
    assert body["embed_model"]  # whatever EMBED_MODEL resolved to


@test("knowledge: list returns added docs; delete removes them")
def _():
    cid = _new_fake_conv("kb-list-del")
    d = client.post(
        f"/api/conversations/{cid}/knowledge",
        json={"filename": "beta.md", "text": "beta beta facts about beta."},
    ).json()
    listed = client.get(f"/api/conversations/{cid}/knowledge").json()["documents"]
    assert any(x["id"] == d["id"] and x["filename"] == "beta.md" for x in listed)

    r = client.delete(f"/api/conversations/{cid}/knowledge/{d['id']}")
    assert r.status_code == 200, r.text
    after = client.get(f"/api/conversations/{cid}/knowledge").json()["documents"]
    assert all(x["id"] != d["id"] for x in after)
    # Deleting a missing doc 404s.
    assert client.delete(f"/api/conversations/{cid}/knowledge/{d['id']}").status_code == 404


@test("knowledge: whitespace-only text rejected (400)")
def _():
    cid = _new_fake_conv("kb-empty")
    r = client.post(
        f"/api/conversations/{cid}/knowledge",
        json={"filename": "blank.txt", "text": "   \n  "},
    )
    assert r.status_code == 400, r.text


@test("knowledge: retrieval injects the relevant excerpt into the system prompt")
def _():
    cid = _new_fake_conv("kb-retrieve")
    client.post(
        f"/api/conversations/{cid}/knowledge",
        json={"filename": "gamma.txt",
              "text": "The gamma ray burst was recorded near gamma sector seven."},
    )
    fake_ollama.captured.clear()
    # A query sharing the 'gamma' keyword should pull that chunk into context.
    r = client.post(
        f"/api/conversations/{cid}/chat",
        json={"message": "tell me about the gamma reading"},
    )
    assert r.status_code == 200, r.text
    chat_calls = [c for c in fake_ollama.captured if c["path"] == "/api/chat"]
    assert chat_calls, "no chat call captured"
    sys_msg = chat_calls[-1]["payload"]["messages"][0]
    assert sys_msg["role"] == "system"
    assert "Knowledge base excerpts" in sys_msg["content"]
    assert "gamma sector seven" in sys_msg["content"]


@test("knowledge: a bot on a non-Ollama backend still embeds via local Ollama")
def _():
    # Reproduces the relay bug: a bot pinned to an OpenAI-compat / cloud backend
    # that doesn't serve the embed model must still embed locally (built-in Ollama).
    _reseed_builtin_to_fake_ollama()        # built-in id=1 = fake Ollama (has /api/embed)
    bid = _add_openai_backend()             # fake OpenAI-compat (no /api/embed)
    cid = client.post("/api/conversations", json={
        "title": "kb-relay", "model": "openai-a-4b", "backend_id": bid}).json()["id"]
    r = client.post(f"/api/conversations/{cid}/knowledge",
                    json={"filename": "n.txt", "text": "alpha alpha facts about alpha."})
    assert r.status_code == 200, r.text     # embeds on built-in Ollama, not the OpenAI bot backend
    assert r.json()["chunk_count"] >= 1


@test("knowledge: deleting a conversation cascades to its knowledge base")
def _():
    cid = _new_fake_conv("kb-cascade")
    client.post(
        f"/api/conversations/{cid}/knowledge",
        json={"filename": "delta.txt", "text": "delta delta delta."},
    )
    assert client.get(f"/api/conversations/{cid}/knowledge").json()["documents"]
    client.delete(f"/api/conversations/{cid}")
    # KB rows are keyed by conversation_id; cascade should leave none.
    assert client.get(f"/api/conversations/{cid}/knowledge").json()["documents"] == []


@test("mcp: server config GET default empty, PUT then GET roundtrips")
def _():
    cid = _new_fake_conv("mcp-cfg")
    assert client.get(f"/api/conversations/{cid}/mcp").json()["servers"] == []
    servers = [{"name": "GH", "url": "http://localhost:9999/mcp", "enabled": True}]
    r = client.put(f"/api/conversations/{cid}/mcp", json={"servers": servers})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/conversations/{cid}/mcp").json()["servers"]
    assert got[0]["url"] == "http://localhost:9999/mcp"
    assert got[0]["enabled"] is True


@test("mcp: /test against an unreachable server returns ok:false")
def _():
    cid = _new_fake_conv("mcp-test")
    r = client.post(f"/api/conversations/{cid}/mcp/test", json={"url": "http://127.0.0.1:1/mcp"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False


@test("mcp: tool-call loop executes a tool then returns a final answer")
def _():
    import mcp_host as mh
    cid = _new_fake_conv("mcp-loop")
    client.put(
        f"/api/conversations/{cid}/mcp",
        json={"servers": [{"name": "t", "url": "http://x/mcp", "enabled": True}]},
    )

    async def fake_gather(servers):
        spec = {"type": "function", "function": {
            "name": "echo", "description": "echo", "parameters": {"type": "object"}}}
        return ([spec], {"echo": {"url": "http://x/mcp", "headers": None}})

    async def fake_call(url, headers, name, args):
        return "ECHOED:" + str(args)

    orig_g, orig_c = mh.gather_tools, mh.call_tool
    mh.gather_tools = fake_gather
    mh.call_tool = fake_call
    try:
        r = client.post(f"/api/conversations/{cid}/chat", json={"message": "use the tool"})
        assert r.status_code == 200, r.text
        assert "final answer" in r.json()["response"].lower()
    finally:
        mh.gather_tools, mh.call_tool = orig_g, orig_c


@test("mcp: no servers configured → normal chat, tool loop not triggered")
def _():
    cid = _new_fake_conv("mcp-none")
    # No MCP servers → streaming path with the usual Hello world fake stream.
    with client.stream("POST", f"/api/conversations/{cid}/chat/stream",
                       json={"message": "hi"}) as r:
        body = b"".join(r.iter_bytes())
    evs = sse_events(body)
    chunks = "".join(e.get("chunk", "") for e in evs)
    assert "Hello" in chunks


@test("eval: case CRUD — add (bulk), list, delete, clear")
def _():
    cid = _new_fake_conv("eval-crud")
    assert client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"] == []
    r = client.post(f"/api/conversations/{cid}/eval/cases", json={"cases": [
        {"input": "a", "expected": "1"}, {"input": "b", "expected": "2"}]})
    assert r.status_code == 200 and r.json()["added"] == 2, r.text
    cases = client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"]
    assert len(cases) == 2 and cases[0]["input"] == "a"
    assert client.delete(f"/api/conversations/{cid}/eval/cases/{cases[0]['id']}").status_code == 200
    assert len(client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"]) == 1
    client.delete(f"/api/conversations/{cid}/eval/cases")
    assert client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"] == []


@test("eval: seed from chat history creates input/expected pairs")
def _():
    cid = _seed_conv_with_turn("eval-seed")  # streams one user→assistant turn
    r = client.post(f"/api/conversations/{cid}/eval/seed")
    assert r.status_code == 200 and r.json()["added"] >= 1, r.text
    cases = client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"]
    assert cases and cases[0]["input"] == "hi"
    assert "Hello world" in cases[0]["expected"]


@test("eval run: exact mode scores reply vs expected")
def _():
    cid = _new_fake_conv("eval-exact")  # fake bot always replies "Hello world!"
    client.post(f"/api/conversations/{cid}/eval/cases", json={"cases": [
        {"input": "x", "expected": "Hello world!"},    # passes (normalized match)
        {"input": "y", "expected": "totally wrong"}]})  # fails
    r = client.post(f"/api/conversations/{cid}/eval/run", json={"mode": "exact"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2 and body["passed"] == 1 and body["accuracy"] == 0.5
    by_input = {x["input"]: x for x in body["results"]}
    assert by_input["x"]["passed"] is True and by_input["y"]["passed"] is False


@test("eval run: contains mode passes on substring match")
def _():
    cid = _new_fake_conv("eval-contains")
    client.post(f"/api/conversations/{cid}/eval/cases", json={"cases": [
        {"input": "x", "expected": "world"}]})   # 'world' ⊂ 'Hello world!'
    body = client.post(f"/api/conversations/{cid}/eval/run", json={"mode": "contains"}).json()
    assert body["passed"] == 1 and body["accuracy"] == 1.0


@test("eval run: judge mode scores via the grader LLM")
def _():
    import llm as _llm
    cid = _new_fake_conv("eval-judge")
    client.post(f"/api/conversations/{cid}/eval/cases", json={"cases": [
        {"input": "x", "expected": "anything goes"}]})
    real_chat = _llm.chat

    async def fake_chat(backend, model, messages, **kw):
        # The grader call carries the judge system prompt; return YES for it,
        # delegate real bot calls to the actual fake-backed path.
        sys = messages[0].get("content", "") if messages else ""
        if "grading assistant" in sys:
            return "YES"
        return await real_chat(backend, model, messages, **kw)

    _llm.chat = fake_chat
    try:
        body = client.post(f"/api/conversations/{cid}/eval/run", json={
            "mode": "judge", "judge_backend_id": 1, "judge_model": "ollama-a:3b"}).json()
        assert body["passed"] == 1 and body["accuracy"] == 1.0, body
    finally:
        _llm.chat = real_chat


@test("eval run: judge mode without judge_model is rejected (400)")
def _():
    cid = _new_fake_conv("eval-judge-bad")
    client.post(f"/api/conversations/{cid}/eval/cases", json={"cases": [{"input": "x", "expected": "y"}]})
    r = client.post(f"/api/conversations/{cid}/eval/run", json={"mode": "judge"})
    assert r.status_code == 400, r.text


@test("eval: deleting a conversation cascades to its eval cases")
def _():
    cid = _new_fake_conv("eval-cascade")
    client.post(f"/api/conversations/{cid}/eval/cases", json={"cases": [{"input": "a", "expected": "b"}]})
    assert client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"]
    client.delete(f"/api/conversations/{cid}")
    assert client.get(f"/api/conversations/{cid}/eval/cases").json()["cases"] == []


@test("clear: wipes messages but keeps config; 404 on missing conv")
def _():
    cid = _seed_conv_with_turn("clear-test")
    assert len(client.get(f"/api/conversations/{cid}").json()["messages"]) >= 2
    r = client.post(f"/api/conversations/{cid}/clear")
    assert r.status_code == 200, r.text
    after = client.get(f"/api/conversations/{cid}").json()
    assert after["messages"] == []          # messages wiped
    assert after["model"] == "ollama-a:3b"  # config kept
    assert client.post("/api/conversations/999999/clear").status_code == 404


@test("legacy /api/chat/stream: streams content via explicit backend")
def _():
    _reseed_builtin_to_fake_ollama()
    with client.stream("POST", "/api/chat/stream", json={
        "model": "ollama-a:3b",
        "messages": [{"role": "user", "content": "hi"}],
        "backend_id": 1,
    }) as r:
        body = b"".join(r.iter_bytes())
    evs = sse_events(body)
    assert "Hello" in "".join(e.get("chunk", "") for e in evs)
    assert any(e.get("end") for e in evs)


@test("mcp: streaming endpoint runs the tool loop and emits the final answer")
def _():
    import mcp_host as mh
    cid = _new_fake_conv("mcp-stream")
    client.put(f"/api/conversations/{cid}/mcp",
               json={"servers": [{"name": "t", "url": "http://x/mcp", "enabled": True}]})

    async def fake_gather(servers):
        spec = {"type": "function", "function": {
            "name": "echo", "description": "echo", "parameters": {"type": "object"}}}
        return ([spec], {"echo": {"url": "http://x/mcp", "headers": None}})

    async def fake_call(url, headers, name, args):
        return "tool ran"

    og, oc = mh.gather_tools, mh.call_tool
    mh.gather_tools, mh.call_tool = fake_gather, fake_call
    try:
        with client.stream("POST", f"/api/conversations/{cid}/chat/stream",
                           json={"message": "use the tool"}) as r:
            body = b"".join(r.iter_bytes())
        evs = sse_events(body)
        assert "final answer" in "".join(e.get("chunk", "") for e in evs).lower()
        assert any(e.get("end") for e in evs)
    finally:
        mh.gather_tools, mh.call_tool = og, oc


@test("knowledge: messages=[] form skips retrieval (single-message only)")
def _():
    cid = _new_fake_conv("kb-messages-form")
    client.post(f"/api/conversations/{cid}/knowledge",
                json={"filename": "g.txt", "text": "gamma gamma gamma facts"})
    fake_ollama.captured.clear()
    r = client.post(f"/api/conversations/{cid}/chat",
                    json={"messages": [{"role": "user", "content": "about gamma"}]})
    assert r.status_code == 200, r.text
    chat_calls = [c for c in fake_ollama.captured if c["path"] == "/api/chat"]
    sys_msg = chat_calls[-1]["payload"]["messages"][0]
    assert "Knowledge base excerpts" not in sys_msg["content"]


@test("mcp_host.gather_tools: dedups tool names (first wins) + skips unreachable/disabled")
def _():
    import asyncio
    import mcp_host as mh

    async def fake_list(url, headers=None):
        if url == "http://a/mcp":
            return [{"type": "function", "function": {"name": "shared", "description": "", "parameters": {}}},
                    {"type": "function", "function": {"name": "only_a", "description": "", "parameters": {}}}]
        if url == "http://b/mcp":
            return [{"type": "function", "function": {"name": "shared", "description": "", "parameters": {}}}]
        raise RuntimeError("unreachable")

    orig = mh.list_tools
    mh.list_tools = fake_list
    try:
        servers = [
            {"url": "http://a/mcp", "enabled": True},
            {"url": "http://b/mcp", "enabled": True},     # 'shared' collides → dropped
            {"url": "http://dead/mcp", "enabled": True},  # raises → skipped
            {"url": "http://a/mcp", "enabled": False},    # disabled → skipped
        ]
        tools, routing = asyncio.run(mh.gather_tools(servers))
        names = [t["function"]["name"] for t in tools]
        assert names == ["shared", "only_a"], names
        assert routing["shared"]["url"] == "http://a/mcp"  # first server wins
    finally:
        mh.list_tools = orig


@test("knowledge.py units: chunk_text overlap/empty, top_k ranking, context block")
def _():
    import knowledge as kn
    assert kn.chunk_text("") == []
    assert kn.chunk_text("short") == ["short"]
    cs = kn.chunk_text("word " * 600, size=200, overlap=40)
    assert len(cs) > 1
    chunks = [{"embedding": kn.normalize([1.0, 0.0]), "text": "A", "filename": "a.txt"},
              {"embedding": kn.normalize([0.0, 1.0]), "text": "B", "filename": "b.txt"}]
    top = kn.top_k([0.9, 0.1], chunks, k=1)
    assert top[0]["text"] == "A" and top[0]["score"] > 0.5
    block = kn.build_context_block(top)
    assert "Knowledge base excerpts" in block and "[source: a.txt]" in block
    # top_k_balanced: a big book whose chunks all outscore a small book must NOT
    # fill every slot — the small book's relevant chunk has to surface.
    big = [{"embedding": kn.normalize([1.0, 0.01 * i]), "text": f"big{i}", "filename": "BIG.pdf"}
           for i in range(10)]
    small = [{"embedding": kn.normalize([0.9, 0.2]), "text": "small-hit", "filename": "small.pdf"}]
    bal = kn.top_k_balanced([1.0, 0.0], big + small, k=5)
    assert any(c["filename"] == "small.pdf" for c in bal), [c["filename"] for c in bal]
    assert all(c["filename"] == "BIG.pdf" for c in kn.top_k([1.0, 0.0], big + small, k=5))  # plain buries it


@test("llm.tool_result_message: per-kind shape (ollama vs openai)")
def _():
    import llm as _llm
    call = {"id": "call_1", "name": "echo", "arguments": {}}
    assert _llm.tool_result_message({"kind": "ollama"}, call, "R") == \
        {"role": "tool", "content": "R", "tool_name": "echo"}
    assert _llm.tool_result_message({"kind": "openai"}, call, "R") == \
        {"role": "tool", "tool_call_id": "call_1", "content": "R"}


@test("edit-message: PATCH happy path — content updated, original preserved, edited_at set")
def _():
    cid = _seed_conv_with_turn("edit-happy")
    try:
        # Index 1 is the assistant turn. Verify seed worked.
        before = client.get(f"/api/conversations/{cid}").json()
        assert len(before["messages"]) >= 2, f"seed produced {len(before['messages'])} msgs"
        assert before["messages"][1]["role"] == "assistant"
        pristine = before["messages"][1]["content"]

        r = client.patch(
            f"/api/conversations/{cid}/messages/1",
            json={"content": "an ideal, human-written response"},
        )
        assert r.status_code == 200, r.text
        after = r.json()
        msg = after["messages"][1]
        assert msg["content"] == "an ideal, human-written response"
        assert msg.get("edited") is True
        assert msg.get("original_content") == pristine
        assert "edited_at" in msg and msg["edited_at"]
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("edit-message: second edit preserves the ORIGINAL original_content (not interim)")
def _():
    cid = _seed_conv_with_turn("edit-twice")
    try:
        pristine = client.get(f"/api/conversations/{cid}").json()["messages"][1]["content"]
        client.patch(f"/api/conversations/{cid}/messages/1", json={"content": "v1"})
        client.patch(f"/api/conversations/{cid}/messages/1", json={"content": "v2-final"})
        msg = client.get(f"/api/conversations/{cid}").json()["messages"][1]
        assert msg["content"] == "v2-final"
        # Anchor must still be the pristine model output, NOT "v1".
        assert msg["original_content"] == pristine, (
            f"original drifted — expected {pristine!r}, got {msg['original_content']!r}"
        )
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("edit-message: out-of-range index and missing conv_id both return 404")
def _():
    cid = _seed_conv_with_turn("edit-404")
    try:
        r = client.patch(
            f"/api/conversations/{cid}/messages/999",
            json={"content": "nope"},
        )
        assert r.status_code == 404, r.text

        r = client.patch(
            "/api/conversations/999999/messages/0",
            json={"content": "nope"},
        )
        assert r.status_code == 404, r.text
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("edit-message: rejects extra fields (extra='forbid')")
def _():
    cid = _seed_conv_with_turn("edit-extra")
    try:
        r = client.patch(
            f"/api/conversations/{cid}/messages/1",
            json={"content": "x", "role": "system"},
        )
        assert r.status_code == 422, r.text
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export CSV: input/output columns, one row per user→assistant pair")
def _():
    cid = _seed_conv_with_turn("csv-export")
    try:
        # Overwrite assistant reply with a value containing CSV-hostile chars
        # so we also verify escaping.
        tricky = 'line1, with comma\n"line2" with quotes'
        client.patch(
            f"/api/conversations/{cid}/messages/1", json={"content": tricky}
        )
        r = client.get(f"/api/conversations/{cid}/export.csv")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv"), r.headers
        assert "attachment" in r.headers.get("content-disposition", ""), r.headers

        import csv as _csv, io as _io
        rows = list(_csv.reader(_io.StringIO(r.text)))
        assert rows[0] == ["input", "output"], rows[0]
        assert len(rows) == 2, f"expected header + 1 pair, got {rows}"
        assert rows[1][0] == "hi"
        assert rows[1][1] == tricky
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export CSV: 404 on missing conversation")
def _():
    r = client.get("/api/conversations/999999/export.csv")
    assert r.status_code == 404, r.text


@test("persist strip: model output with leading+trailing whitespace lands clean in DB")
def _():
    """Qwen3 / LM Studio emit a leading \\n\\n between (hidden) thinking and the
    answer, and often trailing \\n\\n at completion. The persist path must
    .strip() both ends — otherwise the edit textarea shows junk empty lines
    and the CSV export carries them into the SFT target.
    """
    _reseed_builtin_to_fake_ollama()
    fake_ollama.dirty = True
    try:
        c = client.post("/api/conversations", json={
            "title": "persist-strip", "model": "ollama-a:3b", "backend_id": 1,
        }).json()
        with client.stream(
            "POST", f"/api/conversations/{c['id']}/chat/stream",
            json={"message": "hi", "persist": True},
        ) as r:
            for _ in r.iter_bytes():
                pass

        stored = client.get(f"/api/conversations/{c['id']}").json()
        assert len(stored["messages"]) >= 2
        content = stored["messages"][1]["content"]
        # FakeOllama's dirty frames produce "\n\nHello world!\n\n\n".
        # After rstrip/strip on persist it must be exactly "Hello world!".
        assert content == "Hello world!", f"unstripped content: {content!r}"
        client.delete(f"/api/conversations/{c['id']}")
    finally:
        fake_ollama.dirty = False


@test("export CSV: strips leading/trailing whitespace on already-stored messages")
def _():
    """Belt-and-suspenders: legacy conversations may have been stored before
    the persist-strip fix. The export endpoint must still emit clean cells.
    """
    cid = _seed_conv_with_turn("csv-strip")
    try:
        # Round-trip a dirty payload via PATCH (which intentionally does NOT
        # strip — it preserves whatever the user typed). Then verify export
        # strips it on the way out.
        dirty = "  \n\nRewritten answer.\n\n  "
        client.patch(f"/api/conversations/{cid}/messages/1", json={"content": dirty})

        r = client.get(f"/api/conversations/{cid}/export.csv")
        assert r.status_code == 200, r.text
        import csv as _csv, io as _io
        rows = list(_csv.reader(_io.StringIO(r.text)))
        assert rows[0] == ["input", "output"]
        assert rows[1][1] == "Rewritten answer.", f"unstripped output cell: {rows[1][1]!r}"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export CSV: multimodal turn — uses display_text, drops images, doesn't crash")
def _():
    """Pre-fix bug: `.strip()` on a list-content user message would TypeError.
    Now: text-only CSV export prefers display_text, falls back to text parts.
    """
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "csv-mm", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "what's in this?",
            "persist": True,
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r.status_code == 200, r.text
        r = client.get(f"/api/conversations/{c['id']}/export.csv")
        assert r.status_code == 200, r.text
        import csv as _csv, io as _io
        rows = list(_csv.reader(_io.StringIO(r.text)))
        assert rows[0] == ["input", "output"]
        # Should be exactly the user's typed text — no `[Attached: ...]` preamble,
        # no base64 data leak.
        assert rows[1][0] == "what's in this?", f"unexpected input cell: {rows[1][0]!r}"
        assert "data:image" not in rows[1][0]
        assert rows[1][1], "assistant cell empty"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


# ---- ZIP export (multimodal SFT bundle) ----

import zipfile as _zipfile  # noqa: E402

@test("export ZIP: text-only conversation produces clean JSONL, no images/")
def _():
    cid = _seed_conv_with_turn("zip-textonly")
    try:
        r = client.get(f"/api/conversations/{cid}/export.zip")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert any(n.endswith(".jsonl") for n in names), f"no JSONL in ZIP: {names}"
        assert not any(n.startswith("images/") for n in names), \
            f"text-only export shouldn't have images/: {names}"
        jsonl_name = next(n for n in names if n.endswith(".jsonl"))
        lines = zf.read(jsonl_name).decode().splitlines()
        assert len(lines) == 1, f"expected 1 pair, got {len(lines)}"
        rec = json.loads(lines[0])
        msgs = rec["messages"]
        assert msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
        # Text-only → string content (cleaner JSONL).
        assert isinstance(msgs[0]["content"], str)
        assert isinstance(msgs[1]["content"], str)
        assert msgs[1]["content"] == "Hello world!", f"assistant: {msgs[1]['content']!r}"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export ZIP: image attachment → relative path in JSONL + actual bytes in images/")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "zip-image", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "describe",
            "persist": True,
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r.status_code == 200, r.text
        r = client.get(f"/api/conversations/{c['id']}/export.zip")
        assert r.status_code == 200, r.text
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        # Exactly one image expected at the canonical path.
        img_paths = [n for n in names if n.startswith("images/")]
        assert img_paths == ["images/0_user_0.png"], f"image paths: {img_paths}"
        # Image bytes match what we sent in (PNG signature).
        img_bytes = zf.read("images/0_user_0.png")
        assert img_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "image bytes don't have PNG signature"
        assert base64.b64encode(img_bytes).decode() == _TINY_PNG_BASE64, \
            "image bytes don't match the original base64"
        # JSONL references the relative path, NOT a data: URL.
        jsonl_name = next(n for n in names if n.endswith(".jsonl"))
        rec = json.loads(zf.read(jsonl_name).decode().splitlines()[0])
        user_content = rec["messages"][0]["content"]
        assert isinstance(user_content, list), f"multimodal user content not array: {user_content}"
        types = [p["type"] for p in user_content]
        assert types == ["text", "image_url"], f"types: {types}"
        url = user_content[1]["image_url"]["url"]
        assert url == "images/0_user_0.png", f"url not rewritten to relative path: {url}"
        # User's typed text only (no `[Attached: ...]` preamble — image-only attachments
        # don't produce that header on the way in either).
        assert user_content[0]["text"] == "describe", f"text part: {user_content[0]['text']!r}"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("export ZIP: PDF/text attachment body is inlined into the JSON text part")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "zip-pdf", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "What's the password?",
            "persist": True,
            "attachments": [{
                "name": "secret.pdf", "kind": "pdf",
                "text": "TOP_SECRET=BLUEFOX42", "page_count": 1,
                "char_count": 19, "truncated": False,
            }],
        })
        assert r.status_code == 200, r.text
        r = client.get(f"/api/conversations/{c['id']}/export.zip")
        assert r.status_code == 200, r.text
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        # No images/ entries — PDF is text-only.
        assert not any(n.startswith("images/") for n in names), names
        jsonl_name = next(n for n in names if n.endswith(".jsonl"))
        rec = json.loads(zf.read(jsonl_name).decode().splitlines()[0])
        # Text-only → user content is a string. The PDF body lives inline so
        # the trainer sees what the model actually saw at training time.
        user_content = rec["messages"][0]["content"]
        assert isinstance(user_content, str), f"expected string, got {type(user_content)}"
        assert "[Attached: secret.pdf]" in user_content
        assert "TOP_SECRET=BLUEFOX42" in user_content
        assert "What's the password?" in user_content
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("export ZIP: filename uses sanitized conversation title")
def _():
    cid = _seed_conv_with_turn("zip / filename:dirty?title")
    try:
        r = client.get(f"/api/conversations/{cid}/export.zip")
        assert r.status_code == 200, r.text
        cd = r.headers.get("content-disposition", "")
        # Original title had spaces and punctuation — must be flattened.
        assert "filename=" in cd
        # Extract just the filename portion.
        m = re.search(r'filename="([^"]+)"', cd)
        assert m, f"no filename in Content-Disposition: {cd}"
        fname = m.group(1)
        for ch in (" ", "/", ":", "?"):
            assert ch not in fname, f"unsafe char {ch!r} in filename: {fname!r}"
        assert fname.endswith(".zip")
        # JSONL inside should have the same stem.
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        stem = fname[:-4]
        assert f"{stem}.jsonl" in zf.namelist(), f"JSONL doesn't match zip stem: {zf.namelist()}"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export ZIP: 404 on missing conversation")
def _():
    r = client.get("/api/conversations/999999/export.zip")
    assert r.status_code == 404, r.text


# We need `re` and `base64` for the zip tests (the tests reference _TINY_PNG_BASE64
# defined further down in the multimodal section, so the import order is fine).
import re  # noqa: E402, F811
import base64  # noqa: E402, F811


# ---- Image-classification export (third format: image,label CSV in a ZIP) ----

@test("export classification: one image → one (image, label) CSV row + matching file")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "classify-one", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        # User attaches one image with some typed text. Fake assistant replies "Hello world!".
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "is this a drunk person?",
            "persist": True,
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r.status_code == 200, r.text

        r = client.get(f"/api/conversations/{c['id']}/export.classify.zip")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert "images/0_user_0.png" in names, f"image file missing: {names}"
        csv_name = next(n for n in names if n.endswith(".csv"))
        import csv as _csv, io as _io
        rows = list(_csv.reader(_io.StringIO(zf.read(csv_name).decode())))
        assert rows[0] == ["image", "label"]
        assert len(rows) == 2, f"expected 1 data row, got {len(rows) - 1}"
        assert rows[1][0] == "images/0_user_0.png", f"image path mismatch: {rows[1][0]!r}"
        assert rows[1][1] == "Hello world!", f"label: {rows[1][1]!r}"
        # Bytes for the image actually match what was sent.
        assert base64.b64encode(zf.read("images/0_user_0.png")).decode() == _TINY_PNG_BASE64
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("export classification: typed text is ignored — never appears in the CSV")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "classify-no-text", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        TYPED = "DROP TABLE users;-- THIS TEXT MUST NOT LEAK"
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": TYPED,
            "persist": True,
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r.status_code == 200, r.text

        r = client.get(f"/api/conversations/{c['id']}/export.classify.zip")
        assert r.status_code == 200, r.text
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        csv_text = zf.read(next(n for n in zf.namelist() if n.endswith(".csv"))).decode()
        assert TYPED not in csv_text, f"typed text leaked into classification CSV: {csv_text!r}"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("export classification: text-only pairs are skipped (no CSV rows, no images/)")
def _():
    cid = _seed_conv_with_turn("classify-textonly")
    try:
        # _seed_conv_with_turn produces one user→assistant text-only pair.
        r = client.get(f"/api/conversations/{cid}/export.classify.zip")
        assert r.status_code == 200, r.text
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert not any(n.startswith("images/") for n in names), \
            f"text-only conv produced images/ entries: {names}"
        csv_text = zf.read(next(n for n in names if n.endswith(".csv"))).decode()
        # Header only — no data rows.
        assert csv_text.strip() == "image,label", f"unexpected CSV body: {csv_text!r}"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export classification: filename uses <title>-classification.zip")
def _():
    cid = _seed_conv_with_turn("classify name")
    try:
        r = client.get(f"/api/conversations/{cid}/export.classify.zip")
        assert r.status_code == 200, r.text
        cd = r.headers.get("content-disposition", "")
        m = re.search(r'filename="([^"]+)"', cd)
        assert m, f"no filename in CD: {cd}"
        fname = m.group(1)
        assert fname.endswith("-classification.zip"), f"unexpected filename: {fname}"
        # Doesn't collide with the SFT ZIP name.
        assert fname != "classify_name.zip"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("export classification: multi-image turn → one row per image, shared label")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "classify-multi", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        # Three images attached to one user turn — one labeling action covers all three.
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "label these",
            "persist": True,
            "attachments": [
                {"name": f"a{i}.png", "kind": "image", "mime": "image/png",
                 "data_url": _TINY_PNG_DATA_URL} for i in range(3)
            ],
        })
        assert r.status_code == 200, r.text

        r = client.get(f"/api/conversations/{c['id']}/export.classify.zip")
        assert r.status_code == 200, r.text
        zf = _zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        # All three images present at predictable paths.
        for j in range(3):
            assert f"images/0_user_{j}.png" in names, f"image {j} missing: {names}"
        csv_text = zf.read(next(n for n in names if n.endswith(".csv"))).decode()
        import csv as _csv, io as _io
        rows = list(_csv.reader(_io.StringIO(csv_text)))
        assert rows[0] == ["image", "label"]
        assert len(rows) == 4, f"expected 3 data rows for 3 images, got {len(rows) - 1}"
        # All three rows share the same assistant-supplied label.
        labels = {r[1] for r in rows[1:]}
        assert labels == {"Hello world!"}, f"multi-image rows didn't share label: {labels}"
        # Each row points at a distinct image path.
        paths = [r[0] for r in rows[1:]]
        assert paths == [
            "images/0_user_0.png", "images/0_user_1.png", "images/0_user_2.png"
        ], f"image paths not in pair-order: {paths}"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("export classification: 404 on missing conversation")
def _():
    r = client.get("/api/conversations/999999/export.classify.zip")
    assert r.status_code == 404, r.text


# ---- Self-upgrade endpoints ----

@test("upgrade status: returns shape with current/latest SHAs + can_upgrade flag")
def _():
    # The repo we're testing against IS a git repo (the project's own checkout),
    # so we can hit the real endpoint and assert on its structural shape.
    r = client.get("/api/upgrade/status")
    assert r.status_code == 200, r.text
    j = r.json()
    # Shape: every documented key is present, regardless of state.
    for key in ("installed_via", "can_upgrade", "current_sha", "current_short",
                "latest_sha", "latest_short", "behind", "dirty",
                "latest_messages", "last_run"):
        assert key in j, f"missing key in /api/upgrade/status: {key}"
    assert j["installed_via"] in ("git", "docker", "unknown")
    assert isinstance(j["behind"], int) and j["behind"] >= 0
    assert isinstance(j["dirty"], bool)
    assert isinstance(j["latest_messages"], list)
    # can_upgrade is conjunction: behind > 0 AND not dirty AND git install.
    if j["installed_via"] == "git" and j["behind"] > 0 and not j["dirty"]:
        # Could be False if upgrade.sh is missing — but we ship it, so:
        assert j["can_upgrade"] is True, f"expected can_upgrade with behind>0 + clean: {j}"
    else:
        assert j["can_upgrade"] is False, f"can_upgrade should be False here: {j}"


@test("upgrade run: refuses non-loopback client (security check)")
def _():
    # FastAPI's TestClient sets request.client.host to "testclient" by default,
    # which is NOT in the loopback allowlist — so the POST must bounce with
    # 403 BEFORE any shell exec or even the can_upgrade check happens. This
    # is the security guarantee: an HTTP caller from outside loopback cannot
    # trigger the script under any circumstance.
    r = client.post("/api/upgrade/run")
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert "loopback" in r.json().get("detail", "").lower()


def _clear_upgrade_state_file() -> None:
    """Wipe the persistent upgrade-check state so each test starts cold.
    Tests that exercise the once-per-version notification need a clean slate
    or the prior test's `last_notified_sha` would suppress this one's log."""
    import app as app_mod
    try:
        app_mod._UPGRADE_CHECK_STATE_PATH.unlink()
    except FileNotFoundError:
        pass


@test("upgrade state: once-per-version log fires exactly once per new SHA")
def _():
    # Two consecutive status calls with the same (current, latest) pair
    # should print the "update available" line exactly once. Mirrors
    # OpenClaw's `lastNotifiedVersion` semantics.
    import io, os, sys
    from contextlib import redirect_stderr
    from unittest.mock import patch
    _clear_upgrade_state_file()
    fake_main = "f" * 40
    fake_build = "0" * 40
    captured = io.StringIO()
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": fake_build,
    }), patch("app._github_main_sha", return_value=fake_main), redirect_stderr(captured):
        from app import api_upgrade_status
        api_upgrade_status()
        api_upgrade_status()
        api_upgrade_status()
    log = captured.getvalue()
    occurrences = log.count("update available:")
    assert occurrences == 1, f"expected exactly 1 notify line, got {occurrences}: {log!r}"


@test("upgrade state: new version after a known one re-fires the notify log")
def _():
    # Once we *do* see a different remote SHA, the log should fire again
    # (so users actually learn about each release, not just the first).
    import io, os
    from contextlib import redirect_stderr
    from unittest.mock import patch
    _clear_upgrade_state_file()
    fake_build = "0" * 40
    sha_v1 = "1" * 40
    sha_v2 = "2" * 40
    captured = io.StringIO()
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": fake_build,
    }), redirect_stderr(captured):
        from app import api_upgrade_status
        with patch("app._github_main_sha", return_value=sha_v1):
            api_upgrade_status()
            api_upgrade_status()
        # Force the cache to expire, otherwise the cached SHA wins and
        # our fresh patch never gets called.
        import json as _json, app as _app
        st = _json.loads(_app._UPGRADE_CHECK_STATE_PATH.read_text())
        st["last_checked_at"] = "1970-01-01T00:00:00+00:00"
        _app._UPGRADE_CHECK_STATE_PATH.write_text(_json.dumps(st))
        with patch("app._github_main_sha", return_value=sha_v2):
            api_upgrade_status()
    log = captured.getvalue()
    assert log.count("update available:") == 2, log


@test("upgrade state: first_seen_at is preserved across repeat calls for the same version")
def _():
    import os
    from unittest.mock import patch
    _clear_upgrade_state_file()
    fake_main = "f" * 40
    fake_build = "0" * 40
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": fake_build,
    }), patch("app._github_main_sha", return_value=fake_main):
        from app import api_upgrade_status
        first = api_upgrade_status()["first_seen_at"]
        second = api_upgrade_status()["first_seen_at"]
    assert first is not None and first == second, (first, second)


@test("upgrade state: first_seen_at clears once the install catches up to the remote")
def _():
    # If the user upgrades and later polls report behind=0, we should clear
    # the seen-since marker so a future regression starts fresh.
    import os
    from unittest.mock import patch
    _clear_upgrade_state_file()
    sha = "a" * 40
    fake_build = "0" * 40
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": fake_build,
    }), patch("app._github_main_sha", return_value=sha):
        from app import api_upgrade_status
        first = api_upgrade_status()
        assert first["first_seen_at"] is not None
    # Simulate the install catching up: build SHA now matches the remote.
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": sha,
    }), patch("app._github_main_sha", return_value=sha):
        caught_up = api_upgrade_status()
    assert caught_up["behind"] == 0
    assert caught_up["first_seen_at"] is None


@test("upgrade status: Docker install reports behind>0 when build SHA != GitHub main")
def _():
    # Regression for "Docker users never see the upgrade badge". When running
    # in a container we can't run git, so we bake the build SHA into env at
    # image-build time and consult GitHub's REST API for origin/main. With a
    # mismatch we expect installed_via=docker, behind>=1, and the actionable
    # rebuild reason. The test mocks _github_main_sha so we don't depend on
    # network or hit GitHub's rate limit.
    import os
    from unittest.mock import patch
    _clear_upgrade_state_file()
    fake_main = "f" * 40
    fake_build = "0" * 40
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": fake_build,
    }), patch("app._github_main_sha", return_value=fake_main):
        from app import api_upgrade_status
        j = api_upgrade_status()
    assert j["installed_via"] == "docker", j
    assert j["current_sha"] == fake_build, j
    assert j["latest_sha"] == fake_main, j
    assert j["behind"] == 1, j
    assert j["can_upgrade"] is False, j
    assert "docker compose" in (j["reason"] or "").lower(), j


@test("upgrade status: Docker install reports behind=0 when build SHA == GitHub main")
def _():
    # The "no update" half of the prior test — same SHA both sides → no badge.
    import os
    from unittest.mock import patch
    _clear_upgrade_state_file()
    sha = "a" * 40
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": sha,
    }), patch("app._github_main_sha", return_value=sha):
        from app import api_upgrade_status
        j = api_upgrade_status()
    assert j["installed_via"] == "docker", j
    assert j["behind"] == 0, j
    assert "already on the latest" in (j["reason"] or "").lower(), j


@test("upgrade status: Docker install with unknown build SHA degrades gracefully")
def _():
    # Image rebuilt without the GIT_SHA build arg — we can't compare anything,
    # so we shouldn't claim an update. Reason text steers the user toward
    # rebuilding with the build arg set.
    import os
    from unittest.mock import patch
    _clear_upgrade_state_file()
    with patch.dict(os.environ, {
        "MINICLOSEDAI_IN_DOCKER": "1",
        "MINICLOSEDAI_BUILD_SHA": "unknown",
    }), patch("app._github_main_sha", return_value="f" * 40):
        from app import api_upgrade_status
        j = api_upgrade_status()
    assert j["installed_via"] == "docker", j
    assert j["behind"] == 0, j
    assert j["can_upgrade"] is False, j
    assert "build sha not baked" in (j["reason"] or "").lower(), j


@test("upgrade run: Docker install returns helpful 409 before loopback 403")
def _():
    # Regression for the Mac+Docker bug: when the app runs inside a container,
    # the client_host appears as the bridge gateway IP (e.g. 172.18.0.1), so
    # the loopback firewall would fire 403 first and hide the actionable
    # rebuild instructions. The Docker pre-check must run BEFORE the loopback
    # check and return 409 with the rebuild command (NOT `docker compose pull`,
    # which fails for this project — image tags are built locally).
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, {"MINICLOSEDAI_IN_DOCKER": "1"}):
        r = client.post("/api/upgrade/run")
    assert r.status_code == 409, f"expected 409 (Docker), got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "").lower()
    assert "git pull" in detail, f"missing git pull hint: {detail}"
    assert "--build" in detail, f"missing --build hint: {detail}"


@test("upgrade run: requires can_upgrade=True even from loopback")
def _():
    # We can't easily fake `request.client.host = "127.0.0.1"` from inside
    # TestClient without patching ASGI internals. Instead, exercise the
    # mid-tier guard directly: call api_upgrade_status() in-process and
    # assert that the can_upgrade conjunction matches the documented rules.
    # (The full POST path is exercised manually + by the security test above.)
    from app import api_upgrade_status
    j = api_upgrade_status()
    expected_ok = (
        j["installed_via"] == "git"
        and j["behind"] > 0
        and not j["dirty"]
        and j.get("reason") in (None, "")
    )
    if expected_ok:
        assert j["can_upgrade"] is True, j
    else:
        assert j["can_upgrade"] is False, j
        # And there's always a human-readable reason explaining why not.
        assert j.get("reason"), f"can_upgrade=False but no reason: {j}"


@test("per-conv /chat: include_history=true replays saved turns to the model")
def _():
    """Without this, conversational bots (FAQ chat, Doctors Office Bot) forget
    every prior turn — catastrophic UX. The flag is opt-in so one-shot
    classifier bots keep their pure-function semantics by default.
    """
    cid = _seed_conv_with_turn("history-replay")
    try:
        fake_ollama.captured.clear()

        # Send a follow-up with include_history=true.
        r = client.post(
            f"/api/conversations/{cid}/chat",
            json={"message": "do you remember what I said?", "include_history": True},
        )
        assert r.status_code == 200, r.text

        # Inspect what got sent to the upstream LLM.
        assert len(fake_ollama.captured) == 1
        sent = fake_ollama.captured[0]["payload"]["messages"]
        # Expect: [system, user(prev), assistant(prev), user(now)] — four messages.
        roles = [m["role"] for m in sent]
        assert roles == ["system", "user", "assistant", "user"], f"unexpected roles: {roles}"
        assert sent[1]["content"] == "hi", f"prior user turn not replayed: {sent[1]}"
        assert sent[3]["content"] == "do you remember what I said?"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("per-conv /chat: include_history defaults to false (microservice contract)")
def _():
    """Regression guard — flipping the default would silently break every
    classifier bot already deployed against this endpoint.
    """
    cid = _seed_conv_with_turn("no-history-default")
    try:
        fake_ollama.captured.clear()
        r = client.post(
            f"/api/conversations/{cid}/chat",
            json={"message": "fresh call with no history flag"},
        )
        assert r.status_code == 200, r.text
        sent = fake_ollama.captured[0]["payload"]["messages"]
        roles = [m["role"] for m in sent]
        # Just [system, user(now)] — no replay.
        assert roles == ["system", "user"], f"history leaked in without flag: {roles}"
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("static: no-cache headers on /static/* so stale JS can't bite users")
def _():
    """We hit a real time-sink debugging the edit-message feature when Chrome
    kept serving cached app.js. _NoCacheStatics sets strict no-cache headers;
    this is the regression guard.
    """
    r = client.get("/static/app.js")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "").lower()
    assert "no-cache" in cc, f"missing no-cache: {cc!r}"
    assert "no-store" in cc, f"missing no-store: {cc!r}"

    # Also check the app shell at /
    r2 = client.get("/")
    cc2 = r2.headers.get("cache-control", "").lower()
    assert "no-cache" in cc2, f"index.html cache-control: {cc2!r}"


# ------------------------------------------------------------------
# Pull (Ollama model download) tests
# ------------------------------------------------------------------

def _reset_pull_fake():
    fake_ollama.pull_chunks = [
        {"status": "pulling manifest"},
        {"status": "downloading sha:a", "total": 100, "completed": 50},
        {"status": "downloading sha:a", "total": 100, "completed": 100},
        {"status": "success"},
    ]
    fake_ollama.pull_per_chunk_delay = 0.0


def _wait_pull(key, predicate, timeout=5.0):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = client.get("/api/pulls").json()
        for p in last["pulls"]:
            if p["key"] == key and predicate(p):
                return p
        time.sleep(0.03)
    raise TimeoutError(f"pull {key} predicate timed out after {timeout}s; last={last}")


@test("pull: streams progress and lands as done with status=success")
def _():
    _reseed_builtin_to_fake_ollama()
    _reset_pull_fake()
    name = "test-happy:1"
    r = client.post("/api/backends/1/pull", json={"name": name})
    assert r.status_code == 200, r.text
    state = r.json()
    key = state["key"]
    assert key == f"1:{name}"
    assert state["done"] is False, state

    p = _wait_pull(key, lambda p: p["done"])
    assert p["error"] is None, p
    assert p["status"] == "success", p
    assert p["total"] == 100, p
    assert p["completed"] == 100, p

    # Cleanup so subsequent tests start clean.
    client.delete(f"/api/backends/1/pulls/{name}")


@test("pull: Ollama-side error lands in state.error with status=error")
def _():
    _reseed_builtin_to_fake_ollama()
    fake_ollama.pull_chunks = [
        {"status": "pulling manifest"},
        {"error": "manifest not found"},
    ]
    fake_ollama.pull_per_chunk_delay = 0.0
    name = "test-error:1"
    r = client.post("/api/backends/1/pull", json={"name": name})
    assert r.status_code == 200, r.text
    key = r.json()["key"]

    p = _wait_pull(key, lambda p: p["done"])
    assert p["status"] == "error", p
    assert p["error"] and "manifest not found" in p["error"], p

    client.delete(f"/api/backends/1/pulls/{name}")


@test("pull: duplicate pull while in-flight returns 409")
def _():
    _reseed_builtin_to_fake_ollama()
    _reset_pull_fake()
    fake_ollama.pull_per_chunk_delay = 0.5  # stretch the pull so it stays in-flight
    name = "test-dup:1"
    r1 = client.post("/api/backends/1/pull", json={"name": name})
    assert r1.status_code == 200, r1.text

    r2 = client.post("/api/backends/1/pull", json={"name": name})
    assert r2.status_code == 409, r2.text

    # Cancel + reset for next tests.
    client.delete(f"/api/backends/1/pulls/{name}")
    _reset_pull_fake()


@test("pull: rejected on non-Ollama backend (400)")
def _():
    bid = _add_openai_backend()
    try:
        r = client.post(f"/api/backends/{bid}/pull", json={"name": "anything"})
        assert r.status_code == 400, r.text
    finally:
        client.delete(f"/api/backends/{bid}")


@test("pull: cancel removes the in-flight pull from the registry")
def _():
    _reseed_builtin_to_fake_ollama()
    _reset_pull_fake()
    fake_ollama.pull_per_chunk_delay = 0.5
    name = "test-cancel:1"
    r = client.post("/api/backends/1/pull", json={"name": name})
    assert r.status_code == 200, r.text
    key = r.json()["key"]

    # Confirm it's actually registered + in-flight before cancelling.
    _wait_pull(key, lambda p: not p["done"])

    rc = client.delete(f"/api/backends/1/pulls/{name}")
    assert rc.status_code == 200, rc.text

    pulls = client.get("/api/pulls").json()["pulls"]
    assert not any(p["key"] == key for p in pulls), f"pull still listed after cancel: {pulls}"

    _reset_pull_fake()


@test("pull: missing name field is rejected (422)")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.post("/api/backends/1/pull", json={})
    assert r.status_code == 422, r.text


# ==================================================================
# File attachments — /api/extract-pdf + multimodal chat round-trips
# ==================================================================
#
# The frontend reads images and plain-text files in the browser, but PDFs
# need server-side extraction. These tests exercise both paths plus the
# wire-format translation in llm.py — Ollama gets {content, images:[base64]},
# OpenAI-compat gets the OpenAI content-array shape passed through.

# Hand-built minimal one-page PDF — small enough to inline, real enough that
# pypdf extracts the text. Saves a build dependency on reportlab.
_TEST_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
    b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
    b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources <</Font <</F1 4 0 R>>>> /Contents 5 0 R>> endobj\n"
    b"4 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
    b"5 0 obj <</Length 48>> stream\n"
    b"BT /F1 14 Tf 100 700 Td (TEST_PDF_MARKER) Tj ET\n"
    b"endstream endobj\n"
    b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000111 00000 n \n0000000214 00000 n \n"
    b"0000000278 00000 n \n"
    b"trailer <</Size 6 /Root 1 0 R>>\n"
    b"startxref\n374\n%%EOF\n"
)

# 1×1 transparent PNG, base64. Plenty for a smoke test without dragging in PIL.
_TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "nGP4//8/AwAI/AL+XJ/PtQAAAABJRU5ErkJggg=="
)
_TINY_PNG_BASE64 = _TINY_PNG_DATA_URL.split(",", 1)[1]


@test("extract-pdf: happy path — text + page_count + char_count returned")
def _():
    r = client.post(
        "/api/extract-pdf",
        files={"file": ("hello.pdf", _TEST_PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["filename"] == "hello.pdf"
    assert j["page_count"] == 1
    assert j["truncated"] is False
    assert "TEST_PDF_MARKER" in j["text"], f"marker missing: {j['text']!r}"
    assert j["char_count"] == len(j["text"])


@test("extract-pdf: oversize upload is rejected (413)")
def _():
    # 11 MB of zero bytes — past the 10 MB chat-attachment cap.
    big = b"\x00" * (11 * 1024 * 1024)
    r = client.post(
        "/api/extract-pdf",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"].lower()


@test("extract-pdf: full=1 raises the byte cap (knowledge-base path)")
def _():
    # Same 11 MB that the default path rejects — full=1 must NOT 413 it (it's
    # under the book-friendly cap). The zero bytes aren't a valid PDF, so it
    # gets a 400 parse error instead — proving the size gate was lifted, not hit.
    big = b"\x00" * (11 * 1024 * 1024)
    r = client.post(
        "/api/extract-pdf?full=1",
        files={"file": ("book.pdf", big, "application/pdf")},
    )
    assert r.status_code != 413, r.text
    assert r.status_code == 400, r.text


@test("extract-pdf: malformed bytes return 400")
def _():
    r = client.post(
        "/api/extract-pdf",
        files={"file": ("not-a-pdf.pdf", b"this is plain text, not a PDF",
                        "application/pdf")},
    )
    assert r.status_code == 400, r.text


@test("attachments: image → Ollama content + images:[base64] (no data: prefix)")
def _():
    _reseed_builtin_to_fake_ollama()
    fake_ollama.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "img-ollama", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "What's in this image?",
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r.status_code == 200, r.text
        sent = fake_ollama.captured[-1]["payload"]
        # Find the user turn the server forwarded.
        user_msgs = [m for m in sent["messages"] if m.get("role") == "user"]
        assert user_msgs, "no user message in payload"
        last_user = user_msgs[-1]
        # Translation: text in `content`, base64 (no data: prefix) in `images`.
        assert isinstance(last_user["content"], str), \
            f"Ollama path must collapse content to string, got {type(last_user['content'])}"
        assert "What's in this image?" in last_user["content"]
        assert last_user.get("images") == [_TINY_PNG_BASE64], \
            f"images list mismatch: {last_user.get('images')}"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("attachments: text file body is prepended to user content")
def _():
    _reseed_builtin_to_fake_ollama()
    fake_ollama.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "txt-ollama", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "Summarize.",
            "attachments": [{
                "name": "shopping.txt", "kind": "text",
                "text": "milk\neggs\nbread",
            }],
        })
        assert r.status_code == 200, r.text
        sent = fake_ollama.captured[-1]["payload"]
        last_user = [m for m in sent["messages"] if m.get("role") == "user"][-1]
        assert "[Attached: shopping.txt]" in last_user["content"]
        assert "milk\neggs\nbread" in last_user["content"]
        assert "Summarize." in last_user["content"]
        # Text-only attachment must NOT produce an `images` key.
        assert "images" not in last_user
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("attachments: PDF text uses [Attached: name] header, no images key")
def _():
    _reseed_builtin_to_fake_ollama()
    fake_ollama.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "pdf-ollama", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "What's in the doc?",
            "attachments": [{
                "name": "secret.pdf", "kind": "pdf",
                "text": "TOP_SECRET_TOKEN_42", "page_count": 1,
                "char_count": 18, "truncated": False,
            }],
        })
        assert r.status_code == 200, r.text
        last_user = [m for m in fake_ollama.captured[-1]["payload"]["messages"]
                     if m.get("role") == "user"][-1]
        assert "[Attached: secret.pdf]" in last_user["content"]
        assert "TOP_SECRET_TOKEN_42" in last_user["content"]
        assert "images" not in last_user
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("attachments: image to OpenAI-compat sends content-array unchanged")
def _():
    bid = _add_openai_backend()
    fake_openai.captured.clear()
    c = client.post("/api/conversations", json={
        "title": "img-oai", "model": "openai-a-4b", "backend_id": bid,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "What's in this image?",
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r.status_code == 200, r.text
        sent = fake_openai.captured[-1]["payload"]
        last_user = [m for m in sent["messages"] if m.get("role") == "user"][-1]
        # OpenAI shape: content is a list of typed parts, NOT a top-level images key.
        assert isinstance(last_user["content"], list), \
            f"OpenAI path must keep content array; got {type(last_user['content'])}"
        types = [p.get("type") for p in last_user["content"]]
        assert "text" in types and "image_url" in types, f"types: {types}"
        # Image part keeps the full data: URL (server forwards as-is to OpenAI).
        img_part = next(p for p in last_user["content"] if p.get("type") == "image_url")
        assert img_part["image_url"]["url"] == _TINY_PNG_DATA_URL
        # No top-level images field on the OpenAI path.
        assert "images" not in last_user
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        client.delete(f"/api/backends/{bid}")


@test("attachments: persistence preserves display_text + attachments metadata")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "persist-mm", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "describe",
            "persist": True,
            "attachments": [
                {"name": "tiny.png", "kind": "image", "mime": "image/png",
                 "data_url": _TINY_PNG_DATA_URL},
                {"name": "notes.txt", "kind": "text", "text": "hi"},
            ],
        })
        assert r.status_code == 200, r.text
        full = client.get(f"/api/conversations/{c['id']}").json()
        msgs = full["messages"]
        user_msg = next(m for m in msgs if m.get("role") == "user")
        # The stored content is the OpenAI-style content array (image data lives there).
        assert isinstance(user_msg["content"], list), \
            f"persisted content not a list: {type(user_msg['content'])}"
        types = [p.get("type") for p in user_msg["content"]]
        assert "text" in types and "image_url" in types
        # display_text is the user's typed text only — no [Attached: …] preamble.
        assert user_msg.get("display_text") == "describe", \
            f"display_text: {user_msg.get('display_text')!r}"
        kinds = [a.get("kind") for a in user_msg.get("attachments") or []]
        assert kinds == ["image", "text"], f"attachments meta kinds: {kinds}"
        # Image attachment metadata does NOT duplicate the base64 (lives in content).
        img_meta = user_msg["attachments"][0]
        assert "data_url" not in img_meta and "url" not in img_meta
        assert img_meta.get("mime") == "image/png"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("attachments: rejected on messages=[…] form (single-message form only)")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "mm-reject", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        r = client.post(f"/api/conversations/{c['id']}/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "attachments": [{"name": "x.txt", "kind": "text", "text": "hi"}],
        })
        assert r.status_code == 400, r.text
        assert "single-`message` form" in r.json()["detail"]
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("attachments: include_history replays a stored multimodal turn correctly")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "mm-history", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        # Turn 1: store a multimodal user turn (image + text) with persist=true.
        r1 = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "describe",
            "persist": True,
            "attachments": [{
                "name": "tiny.png", "kind": "image", "mime": "image/png",
                "data_url": _TINY_PNG_DATA_URL,
            }],
        })
        assert r1.status_code == 200, r1.text

        # Turn 2: include_history=true should replay turn 1 correctly.
        fake_ollama.captured.clear()
        r2 = client.post(f"/api/conversations/{c['id']}/chat", json={
            "message": "again",
            "include_history": True,
        })
        assert r2.status_code == 200, r2.text
        sent = fake_ollama.captured[-1]["payload"]
        # The replayed turn 1 user message should arrive translated for Ollama:
        # `images: [base64]` and a string content. (Persisted shape was a content
        # array; llm.py's _to_ollama_message must collapse it on the way out.)
        user_msgs = [m for m in sent["messages"] if m.get("role") == "user"]
        assert len(user_msgs) == 2, f"expected 2 user turns, got {len(user_msgs)}"
        replayed = user_msgs[0]   # the older one is turn 1
        assert isinstance(replayed["content"], str), \
            f"replayed content not collapsed for Ollama: {type(replayed['content'])}"
        assert replayed.get("images") == [_TINY_PNG_BASE64], \
            "replayed image base64 missing or mismatched"
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("ollama auth: api_key sent as Bearer on /api/tags + /api/chat")
def _():
    # Register a SECOND ollama-kind backend pointing at the same fake server,
    # but with an api_key set. Our fake captures Authorization on both routes.
    r = client.post("/api/backends", json={
        "name": "auth-ollama", "kind": "ollama",
        "base_url": fake_ollama.base_url,
        "api_key": "sekrit-token-xyz",
    })
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    fake_ollama.captured.clear()
    try:
        # Hits /api/tags (list_models)
        r2 = client.get(f"/api/backends/{bid}/models")
        assert r2.status_code == 200, r2.text
        tags_calls = [c for c in fake_ollama.captured if c["path"] == "/api/tags"]
        assert tags_calls, "no /api/tags hit captured"
        assert tags_calls[-1]["headers"].get("Authorization") == "Bearer sekrit-token-xyz", \
            f"expected Bearer header on /api/tags; got headers {tags_calls[-1]['headers']}"

        # Hits /api/chat
        c = client.post("/api/conversations", json={
            "title": "auth-chat", "model": "ollama-a:3b", "backend_id": bid,
        }).json()
        try:
            r3 = client.post(f"/api/conversations/{c['id']}/chat",
                             json={"message": "hi"})
            assert r3.status_code == 200, r3.text
            chat_calls = [c for c in fake_ollama.captured if c["path"] == "/api/chat"]
            assert chat_calls, "no /api/chat hit captured"
            assert chat_calls[-1]["headers"].get("Authorization") == "Bearer sekrit-token-xyz", \
                f"expected Bearer header on /api/chat; got headers {chat_calls[-1]['headers']}"
        finally:
            client.delete(f"/api/conversations/{c['id']}")
    finally:
        client.delete(f"/api/backends/{bid}")


@test("ollama auth: no api_key → no Authorization header (back-compat)")
def _():
    # Built-in backend has no api_key — must NOT send Authorization.
    _reseed_builtin_to_fake_ollama()
    fake_ollama.captured.clear()
    r = client.get("/api/backends/1/models")
    assert r.status_code == 200, r.text
    tags_calls = [c for c in fake_ollama.captured if c["path"] == "/api/tags"]
    assert tags_calls, "no /api/tags call captured"
    auth_hdr = tags_calls[-1]["headers"].get("Authorization")
    assert auth_hdr is None, f"unauthenticated backend leaked Authorization: {auth_hdr}"


# ==================================================================
# Lite mode — MINICLOSEDAI_NO_OLLAMA env var
# ==================================================================
#
# Each test uses an isolated temp DB so the main test client's DB stays
# intact. Pattern: swap _db_mod.DB_PATH → temp file, set/clear the env
# var, run init_db(), inspect, restore.

import contextlib  # noqa: E402

@contextlib.contextmanager
def _isolated_db(no_ollama_env: str | None):
    """Run init_db() against a throwaway DB with the env var configured.

    Yields the temporary DB path so tests can inspect its contents directly
    (via sqlite3) — this avoids tripping the main TestClient, which is bound
    to the suite-wide DB.
    """
    tmp = Path(tempfile.mkdtemp(prefix="mca-lite-"))
    tmp_db = tmp / "lite.db"
    saved_path = _db_mod.DB_PATH
    saved_env = os.environ.get("MINICLOSEDAI_NO_OLLAMA")
    try:
        _db_mod.DB_PATH = tmp_db
        if no_ollama_env is None:
            os.environ.pop("MINICLOSEDAI_NO_OLLAMA", None)
        else:
            os.environ["MINICLOSEDAI_NO_OLLAMA"] = no_ollama_env
        yield tmp_db
    finally:
        _db_mod.DB_PATH = saved_path
        if saved_env is None:
            os.environ.pop("MINICLOSEDAI_NO_OLLAMA", None)
        else:
            os.environ["MINICLOSEDAI_NO_OLLAMA"] = saved_env
        try:
            tmp_db.unlink(missing_ok=True)
            tmp.rmdir()
        except Exception:
            pass


@test("lite mode: env var truthy values are recognized")
def _():
    # The exact value strings the docs promise: 1, true, yes, on
    # (case-insensitive). Anything else (incl. unset, empty, 0, false)
    # must read as heavy mode.
    truthy = ["1", "true", "yes", "on", "TRUE", "Yes", " 1 "]
    falsey = [None, "", "0", "false", "no", "off", "tru"]
    saved = os.environ.get("MINICLOSEDAI_NO_OLLAMA")
    try:
        for v in truthy:
            os.environ["MINICLOSEDAI_NO_OLLAMA"] = v
            assert _db_mod._no_ollama_mode() is True, f"truthy value {v!r} not recognized"
        for v in falsey:
            if v is None:
                os.environ.pop("MINICLOSEDAI_NO_OLLAMA", None)
            else:
                os.environ["MINICLOSEDAI_NO_OLLAMA"] = v
            assert _db_mod._no_ollama_mode() is False, f"falsey value {v!r} read as truthy"
    finally:
        if saved is None:
            os.environ.pop("MINICLOSEDAI_NO_OLLAMA", None)
        else:
            os.environ["MINICLOSEDAI_NO_OLLAMA"] = saved


@test("lite mode: fresh DB → built-in Ollama row is NOT seeded")
def _():
    import sqlite3
    with _isolated_db("1") as tmp_db:
        _db_mod.init_db()
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, name, kind, is_builtin, enabled FROM backends").fetchall()
        conn.close()
    assert len(rows) == 0, \
        f"lite mode seeded {len(rows)} backends; expected zero. Rows: {[dict(r) for r in rows]}"


@test("lite mode: heavy → lite migration auto-disables existing built-in row")
def _():
    import sqlite3
    with _isolated_db(None) as tmp_db:
        # Phase 1: heavy init seeds the row enabled=1.
        _db_mod.init_db()
        conn = sqlite3.connect(tmp_db); conn.row_factory = sqlite3.Row
        before = conn.execute(
            "SELECT id, is_builtin, enabled FROM backends WHERE is_builtin = 1"
        ).fetchone()
        conn.close()
        assert before is not None, "heavy init didn't seed the built-in row"
        assert before["enabled"] == 1, f"built-in row started disabled: {dict(before)}"

        # Phase 2: flip env var on, re-run init_db (simulates upgrade-to-lite restart).
        os.environ["MINICLOSEDAI_NO_OLLAMA"] = "1"
        _db_mod.init_db()
        conn = sqlite3.connect(tmp_db); conn.row_factory = sqlite3.Row
        after = conn.execute(
            "SELECT id, is_builtin, enabled FROM backends WHERE is_builtin = 1"
        ).fetchone()
        conn.close()

    assert after is not None, "lite mode deleted the row instead of disabling it"
    assert after["id"] == before["id"], "row id changed (lite shouldn't move FK targets)"
    assert after["enabled"] == 0, f"lite mode failed to flip enabled=0: {dict(after)}"


@test("lite mode: re-running init_db in lite is idempotent (still empty / still disabled)")
def _():
    import sqlite3
    with _isolated_db("1") as tmp_db:
        _db_mod.init_db()
        _db_mod.init_db()   # second call must not seed retroactively
        _db_mod.init_db()
        conn = sqlite3.connect(tmp_db)
        n = conn.execute("SELECT COUNT(*) FROM backends").fetchone()[0]
        conn.close()
    assert n == 0, f"idempotent re-init in lite mode added rows: {n}"


@test("lite mode: heavy default still works (env var unset → row seeded)")
def _():
    import sqlite3
    with _isolated_db(None) as tmp_db:
        _db_mod.init_db()
        conn = sqlite3.connect(tmp_db); conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, name, kind, is_builtin, enabled FROM backends WHERE is_builtin = 1"
        ).fetchone()
        conn.close()
    assert row is not None, "heavy mode failed to seed the built-in row"
    assert row["enabled"] == 1 and row["kind"] == "ollama" and row["is_builtin"] == 1, \
        f"heavy seed shape unexpected: {dict(row)}"


# ---- Bot import/export ----

@test("bot export: returns miniclosed-bot json with config, no backend_id leakage")
def _():
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "Doctor's Office Bot",
        "model": "ollama-a:3b",
        "system_prompt": "You greet patients and book visits.",
        "temperature": 0.4, "top_p": 0.85, "max_tokens": 1024,
        "backend_id": 1,
    }).json()
    try:
        r = client.get(f"/api/conversations/{c['id']}/export")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/json"), r.headers
        assert ".miniclosed-bot.json" in r.headers.get("content-disposition", ""), r.headers
        j = r.json()
        assert j["format"] == "miniclosed-bot"
        assert j["format_version"] == 1
        assert j["bot"]["title"] == "Doctor's Office Bot"
        assert j["bot"]["model"] == "ollama-a:3b"
        assert j["bot"]["system_prompt"].startswith("You greet")
        assert j["bot"]["params"]["temperature"] == 0.4
        # Critical: no backend_id, no DB ids — those are per-instance.
        assert "backend_id" not in j["bot"]
        assert "id" not in j["bot"]
        # Default include_history=false leaves messages empty even if present.
        assert j["sample_messages"] == []
    finally:
        client.delete(f"/api/conversations/{c['id']}")


@test("bot export: include_history=true carries the message history")
def _():
    cid = _seed_conv_with_turn("export-history")
    try:
        r = client.get(f"/api/conversations/{cid}/export?include_history=true")
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j["sample_messages"], list)
        assert len(j["sample_messages"]) >= 2, f"expected at least the seeded turn, got {j['sample_messages']}"
        roles = [m.get("role") for m in j["sample_messages"]]
        assert "user" in roles and "assistant" in roles
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("bot export: 404 on missing conversation")
def _():
    r = client.get("/api/conversations/9999999/export")
    assert r.status_code == 404, r.text


@test("bot import: round-trip — export then import creates a new conv on a matching backend")
def _():
    _reseed_builtin_to_fake_ollama()
    src = client.post("/api/conversations", json={
        "title": "Roundtrip Bot",
        "model": "ollama-a:3b",
        "system_prompt": "Be terse.",
        "temperature": 0.3,
        "backend_id": 1,
    }).json()
    try:
        export = client.get(f"/api/conversations/{src['id']}/export").json()
        r = client.post("/api/conversations/import", json={"data": export})
        assert r.status_code == 201, r.text
        body = r.json()
        new_id = body["id"]
        try:
            assert body["matched_backend_id"] == 1, body
            # Title collides with the source — server appends a suffix.
            assert body["title"].startswith("Roundtrip Bot"), body
            assert body["title"] != "Roundtrip Bot", "title collision should have been bumped"
            # Conversation row matches the export contents.
            new = client.get(f"/api/conversations/{new_id}").json()
            assert new["model"] == "ollama-a:3b"
            assert new["system_prompt"] == "Be terse."
            assert new["params"]["temperature"] == 0.3
            assert new["backend_id"] == 1
        finally:
            client.delete(f"/api/conversations/{new_id}")
    finally:
        client.delete(f"/api/conversations/{src['id']}")


@test("bot import: 409 needs_backend when no enabled backend serves the model")
def _():
    _reseed_builtin_to_fake_ollama()
    export = {
        "format": "miniclosed-bot",
        "format_version": 1,
        "bot": {
            "title": "Unmatched Bot",
            "model": "no-such-model:99b",
            "system_prompt": "Hi.",
            "params": {"temperature": 0.5},
        },
        "sample_messages": [],
    }
    r = client.post("/api/conversations/import", json={"data": export})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("needs_backend") is True, body
    assert body.get("model") == "no-such-model:99b"
    assert isinstance(body.get("available_backends"), list)
    # Built-in Ollama backend should appear in the candidate list (even if it
    # doesn't have the model).
    assert any(b["id"] == 1 for b in body["available_backends"]), body
    assert all(b["model_present"] is False for b in body["available_backends"]), body


@test("bot import: explicit backend_id bypasses model auto-match")
def _():
    _reseed_builtin_to_fake_ollama()
    export = {
        "format": "miniclosed-bot",
        "format_version": 1,
        "bot": {
            "title": "Forced Bot",
            "model": "no-such-model:99b",  # would 409 without backend_id
            "system_prompt": "Forced.",
            "params": {},
        },
    }
    r = client.post("/api/conversations/import", json={"data": export, "backend_id": 1})
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    try:
        new = client.get(f"/api/conversations/{new_id}").json()
        assert new["backend_id"] == 1
        assert new["model"] == "no-such-model:99b"
    finally:
        client.delete(f"/api/conversations/{new_id}")


@test("bot import: malformed payload rejected with 400")
def _():
    # Missing format
    r = client.post("/api/conversations/import", json={"data": {"bot": {}}})
    assert r.status_code == 400, r.text
    # Wrong format string
    r = client.post("/api/conversations/import",
                    json={"data": {"format": "something-else", "format_version": 1, "bot": {}}})
    assert r.status_code == 400, r.text
    # Missing bot.model
    r = client.post("/api/conversations/import", json={"data": {
        "format": "miniclosed-bot", "format_version": 1, "bot": {"title": "x"}
    }})
    assert r.status_code == 400, r.text
    # Future format_version
    r = client.post("/api/conversations/import", json={"data": {
        "format": "miniclosed-bot", "format_version": 99, "bot": {"model": "m"}
    }})
    assert r.status_code == 400, r.text


# ---- App import/export ----

@test("app export: returns miniclosed-app json with metadata + each bot block")
def _():
    _reseed_builtin_to_fake_ollama()
    b1 = client.post("/api/conversations", json={
        "title": "App Bot Alpha", "model": "ollama-a:3b",
        "system_prompt": "alpha system", "temperature": 0.4, "backend_id": 1,
    }).json()["id"]
    b2 = client.post("/api/conversations", json={
        "title": "App Bot Beta", "model": "ollama-a:3b",
        "system_prompt": "beta system", "temperature": 0.7, "backend_id": 1,
    }).json()["id"]
    aid = client.post("/api/apps", json={
        "name": "Exportable App", "description": "for the test", "link": "https://e.example",
    }).json()["id"]
    try:
        assert client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b1}).status_code == 201
        assert client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b2}).status_code == 201

        r = client.get(f"/api/apps/{aid}/export")
        assert r.status_code == 200, r.text
        assert ".miniclosed-app.json" in r.headers.get("content-disposition", ""), r.headers
        j = r.json()
        assert j["format"] == "miniclosed-app"
        assert j["format_version"] == 1
        assert j["application"]["name"] == "Exportable App"
        assert j["application"]["description"] == "for the test"
        assert j["application"]["link"] == "https://e.example"
        # Bots come through as a list of bot blocks (same shape as bot export's `bot`).
        assert isinstance(j["bots"], list) and len(j["bots"]) == 2
        titles = sorted(b["title"] for b in j["bots"])
        assert titles == ["App Bot Alpha", "App Bot Beta"], titles
        for b in j["bots"]:
            assert "backend_id" not in b, "backend_id must not leak — it's per-instance"
            assert "id" not in b, "DB id must not leak"
            assert isinstance(b["params"], dict)
            assert b["sample_messages"] == []  # include_history defaults to false
    finally:
        client.delete(f"/api/apps/{aid}")
        client.delete(f"/api/conversations/{b1}")
        client.delete(f"/api/conversations/{b2}")


@test("app export: include_history=true carries each bot's messages")
def _():
    _reseed_builtin_to_fake_ollama()
    cid = _seed_conv_with_turn("app-export-history")
    aid = client.post("/api/apps", json={"name": "History App"}).json()["id"]
    try:
        assert client.post(f"/api/apps/{aid}/bots", json={"conversation_id": cid}).status_code == 201
        r = client.get(f"/api/apps/{aid}/export?include_history=true")
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["bots"]) == 1
        msgs = j["bots"][0]["sample_messages"]
        assert isinstance(msgs, list) and len(msgs) >= 2, msgs
        roles = [m.get("role") for m in msgs]
        assert "user" in roles and "assistant" in roles, roles
    finally:
        client.delete(f"/api/apps/{aid}")
        client.delete(f"/api/conversations/{cid}")


@test("app import: round-trip — export then import recreates app + bots with one backend")
def _():
    _reseed_builtin_to_fake_ollama()
    b1 = client.post("/api/conversations", json={
        "title": "RT App Bot 1", "model": "ollama-a:3b",
        "system_prompt": "one", "temperature": 0.3, "backend_id": 1,
    }).json()["id"]
    b2 = client.post("/api/conversations", json={
        "title": "RT App Bot 2", "model": "ollama-a:3b",
        "system_prompt": "two", "temperature": 0.9, "backend_id": 1,
    }).json()["id"]
    aid = client.post("/api/apps", json={"name": "Roundtrip App"}).json()["id"]
    new_app_id = None
    new_bot_ids: list[int] = []
    try:
        client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b1})
        client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b2})
        export = client.get(f"/api/apps/{aid}/export").json()

        r = client.post("/api/apps/import", json={"data": export})
        assert r.status_code == 201, r.text
        body = r.json()
        new_app_id = body["id"]
        new_bot_ids = list(body["bot_ids"])
        assert body["matched_backend_id"] == 1, body
        # App name collides with source -> suffix appended.
        assert body["name"].startswith("Roundtrip App") and body["name"] != "Roundtrip App", body
        # Detail page returns both bots, bound to the new app.
        detail = client.get(f"/api/apps/{new_app_id}").json()
        assert len(detail["bots"]) == 2
        assert {b["title"].split(" (")[0] for b in detail["bots"]} == {"RT App Bot 1", "RT App Bot 2"}
        for b in detail["bots"]:
            assert b["backend_id"] == 1
        # Each bot also appears in the global conversation list with the new app_id.
        convs = {c["id"]: c["app_id"] for c in client.get("/api/conversations").json()}
        for nb in new_bot_ids:
            assert convs[nb] == new_app_id, (nb, convs.get(nb))
    finally:
        for nb in new_bot_ids:
            client.delete(f"/api/conversations/{nb}")
        if new_app_id is not None:
            client.delete(f"/api/apps/{new_app_id}")
        client.delete(f"/api/apps/{aid}")
        client.delete(f"/api/conversations/{b1}")
        client.delete(f"/api/conversations/{b2}")


@test("app import: 409 needs_backend when no enabled backend covers every model")
def _():
    _reseed_builtin_to_fake_ollama()
    export = {
        "format": "miniclosed-app",
        "format_version": 1,
        "application": {"name": "Unmatched App"},
        "bots": [
            {"title": "X", "model": "no-such-model:99b", "system_prompt": "x", "params": {}},
            {"title": "Y", "model": "also-missing:1b", "system_prompt": "y", "params": {}},
        ],
    }
    r = client.post("/api/apps/import", json={"data": export})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("needs_backend") is True
    assert set(body.get("models", [])) == {"no-such-model:99b", "also-missing:1b"}, body
    # Built-in backend appears in candidates but doesn't have either model.
    assert any(b["id"] == 1 for b in body["available_backends"])
    assert all(not b["model_present"] for b in body["available_backends"]), body


@test("app import: explicit backend_id bypasses auto-match and is applied to every bot")
def _():
    _reseed_builtin_to_fake_ollama()
    export = {
        "format": "miniclosed-app",
        "format_version": 1,
        "application": {"name": "Forced App"},
        "bots": [
            {"title": "F1", "model": "no-such-model:99b", "system_prompt": "f1", "params": {}},
            {"title": "F2", "model": "also-missing:1b", "system_prompt": "f2", "params": {}},
        ],
    }
    r = client.post("/api/apps/import", json={"data": export, "backend_id": 1})
    assert r.status_code == 201, r.text
    body = r.json()
    new_app_id = body["id"]
    new_bot_ids = list(body["bot_ids"])
    try:
        assert body["matched_backend_id"] == 1
        for nb in new_bot_ids:
            row = client.get(f"/api/conversations/{nb}").json()
            assert row["backend_id"] == 1, row
    finally:
        for nb in new_bot_ids:
            client.delete(f"/api/conversations/{nb}")
        client.delete(f"/api/apps/{new_app_id}")


@test("app import: title-collision suffix applied per bot and to the app name")
def _():
    _reseed_builtin_to_fake_ollama()
    # Pre-seed a conv whose title will clash with one of the imported bots.
    existing = client.post("/api/conversations", json={
        "title": "Collider Bot", "model": "ollama-a:3b", "backend_id": 1,
    }).json()["id"]
    existing_app = client.post("/api/apps", json={"name": "Collider App"}).json()["id"]
    export = {
        "format": "miniclosed-app",
        "format_version": 1,
        "application": {"name": "Collider App"},
        "bots": [
            {"title": "Collider Bot", "model": "ollama-a:3b", "system_prompt": "s", "params": {}},
            {"title": "Other Bot", "model": "ollama-a:3b", "system_prompt": "s", "params": {}},
        ],
    }
    r = client.post("/api/apps/import", json={"data": export})
    assert r.status_code == 201, r.text
    body = r.json()
    new_app_id = body["id"]
    new_bot_ids = list(body["bot_ids"])
    try:
        assert body["name"] != "Collider App", body
        assert body["name"].startswith("Collider App"), body
        new_titles = {
            client.get(f"/api/conversations/{nb}").json()["title"]
            for nb in new_bot_ids
        }
        # The "Collider Bot" title clashed with the seeded conv -> suffix.
        assert "Collider Bot" not in new_titles, new_titles
        assert any(t.startswith("Collider Bot") for t in new_titles), new_titles
    finally:
        for nb in new_bot_ids:
            client.delete(f"/api/conversations/{nb}")
        client.delete(f"/api/apps/{new_app_id}")
        client.delete(f"/api/apps/{existing_app}")
        client.delete(f"/api/conversations/{existing}")


@test("app import: malformed payload rejected with 400")
def _():
    # Wrong format string
    r = client.post("/api/apps/import",
                    json={"data": {"format": "miniclosed-bot", "format_version": 1, "application": {"name": "x"}, "bots": []}})
    assert r.status_code == 400, r.text
    # Missing application
    r = client.post("/api/apps/import",
                    json={"data": {"format": "miniclosed-app", "format_version": 1, "bots": []}})
    assert r.status_code == 400, r.text
    # Empty application.name
    r = client.post("/api/apps/import",
                    json={"data": {"format": "miniclosed-app", "format_version": 1,
                                   "application": {"name": "  "}, "bots": []}})
    assert r.status_code == 400, r.text
    # Missing bots array
    r = client.post("/api/apps/import",
                    json={"data": {"format": "miniclosed-app", "format_version": 1,
                                   "application": {"name": "ok"}}})
    assert r.status_code == 400, r.text
    # Bad bot inside list (no model)
    r = client.post("/api/apps/import",
                    json={"data": {"format": "miniclosed-app", "format_version": 1,
                                   "application": {"name": "ok"},
                                   "bots": [{"title": "missing-model"}]}})
    assert r.status_code == 400, r.text
    # Future format_version
    r = client.post("/api/apps/import",
                    json={"data": {"format": "miniclosed-app", "format_version": 99,
                                   "application": {"name": "ok"}, "bots": []}})
    assert r.status_code == 400, r.text


# ---- LLM request/response log buffer ----

@test("logs: chat calls are recorded with status, latency, response preview")
def _():
    import logs as chat_logs
    _reseed_builtin_to_fake_ollama()
    chat_logs.clear()
    c = client.post("/api/conversations", json={
        "title": "logged", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        # Drive one non-streaming call so a log entry lands.
        r = client.post(f"/api/conversations/{c['id']}/chat", json={"message": "ping"})
        assert r.status_code == 200, r.text
        items = client.get("/api/logs").json()["logs"]
        assert items, "expected at least one log entry"
        e = items[0]
        assert e["status"] == "ok", e
        assert e["kind"] == "sync", e
        assert e["model"] == "ollama-a:3b"
        assert e["endpoint"].endswith(f"/conversations/{c['id']}/chat"), e
        assert isinstance(e["latency_ms"], int) and e["latency_ms"] >= 0
        assert e["response"]["char_count"] > 0, e
        # Last user message is included in the summary.
        roles = [m["role"] for m in e["messages"]]
        assert "user" in roles, e
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        chat_logs.clear()


@test("logs: streaming endpoint records full accumulated response after stream ends")
def _():
    import logs as chat_logs
    _reseed_builtin_to_fake_ollama()
    chat_logs.clear()
    c = client.post("/api/conversations", json={
        "title": "streamlog", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        with client.stream("POST", f"/api/conversations/{c['id']}/chat/stream",
                           json={"message": "hi"}) as r:
            for _ in r.iter_bytes():
                pass
        items = client.get("/api/logs").json()["logs"]
        assert items, "expected at least one log entry"
        e = items[0]
        assert e["kind"] == "stream", e
        assert e["status"] == "ok", e
        # Streamed response was aggregated and persisted to the log.
        assert e["response"]["char_count"] > 0, e
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        chat_logs.clear()


@test("logs: since_id query param returns only newer entries")
def _():
    import logs as chat_logs
    _reseed_builtin_to_fake_ollama()
    chat_logs.clear()
    c = client.post("/api/conversations", json={
        "title": "since-test", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        client.post(f"/api/conversations/{c['id']}/chat", json={"message": "one"})
        first = client.get("/api/logs").json()["logs"]
        assert len(first) >= 1
        cutoff = first[0]["id"]
        # Same-id check should return empty.
        again = client.get(f"/api/logs?since_id={cutoff}").json()["logs"]
        assert again == [], f"expected empty list, got {again}"
        # New call should appear.
        client.post(f"/api/conversations/{c['id']}/chat", json={"message": "two"})
        after = client.get(f"/api/logs?since_id={cutoff}").json()["logs"]
        assert len(after) == 1, after
        assert after[0]["id"] > cutoff
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        chat_logs.clear()


@test("logs: DELETE /api/logs empties the buffer")
def _():
    import logs as chat_logs
    _reseed_builtin_to_fake_ollama()
    c = client.post("/api/conversations", json={
        "title": "clear-test", "model": "ollama-a:3b", "backend_id": 1,
    }).json()
    try:
        client.post(f"/api/conversations/{c['id']}/chat", json={"message": "x"})
        assert client.get("/api/logs").json()["logs"], "expected entries before clear"
        r = client.delete("/api/logs")
        assert r.status_code == 200 and r.json().get("ok") is True
        assert client.get("/api/logs").json()["logs"] == []
    finally:
        client.delete(f"/api/conversations/{c['id']}")
        chat_logs.clear()


@test("logs: long responses are truncated with the truncated flag set")
def _():
    # Hand-construct an entry so we don't have to coerce a fake to emit 2000+ chars.
    import logs as chat_logs
    chat_logs.clear()
    long_text = "x" * 5000
    chat_logs.record_chat(
        endpoint="/api/test", kind="sync",
        backend={"id": 1, "name": "fake", "kind": "ollama"},
        model="m", messages=[{"role": "user", "content": "hi"}],
        params={"temperature": 0.5},
        response_text=long_text, latency_ms=10,
    )
    items = client.get("/api/logs").json()["logs"]
    assert items
    e = items[0]
    assert e["response"]["truncated"] is True
    assert e["response"]["char_count"] == 5000
    assert len(e["response"]["preview"]) < len(long_text)
    chat_logs.clear()


@test("logs: base64 image payloads are stripped from the export blob")
def _():
    # Regression: retaining raw data:image;base64 URLs in the export-only
    # `_full` blob ballooned memory into GBs and stalled /api/logs/export on
    # image-heavy servers. record_chat must strip them to a compact marker
    # while keeping text and non-base64 URLs intact.
    import logs as chat_logs
    chat_logs.clear()
    big_b64 = "A" * 400_000  # ~300 KB decoded
    chat_logs.record_chat(
        endpoint="/api/test", kind="sync",
        backend={"id": 1, "name": "fake", "kind": "openai"},
        model="m",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + big_b64}},
                {"type": "image_url", "image_url": {"url": "images/0_user_0.png"}},
            ],
        }],
        params={}, response_text="a cat", latency_ms=5,
    )
    # The export endpoint surfaces the full request messages.
    r = client.get("/api/logs/export")
    assert r.status_code == 200, r.status_code
    body = r.text
    # The 400 KB base64 blob must be gone; the marker + text + path must remain.
    assert big_b64 not in body, "base64 payload leaked into export"
    assert "image/png" in body and "omitted" in body, "expected image marker"
    assert "what is this?" in body, "text content dropped"
    assert "images/0_user_0.png" in body, "non-base64 url should be preserved"
    # And the whole export must stay small (was multi-hundred-KB before).
    assert len(body) < 5_000, f"export unexpectedly large: {len(body)} bytes"
    chat_logs.clear()


# ---- Relay auto-route override ----

def _reset_relay_cache():
    """Reset the in-process relay-model cache so tests don't bleed into each other."""
    import app as app_mod
    app_mod._relay_model_cache["backend_id"] = None
    app_mod._relay_model_cache["models"] = set()
    app_mod._relay_model_cache["last_fetched"] = 0.0


@test("relay override: no relay registered → original backend wins")
def _():
    # Sanity: with no `app.interdataresearch` backend, the override is a no-op.
    import asyncio, app as app_mod
    _reset_relay_cache()
    original = {"id": 1, "name": "local", "kind": "ollama", "base_url": "http://localhost:11434"}
    result = asyncio.run(app_mod._maybe_override_to_relay(original, "any-model"))
    assert result is original, "expected pass-through when no relay registered"


@test("relay override: model on relay → route to relay")
def _():
    import asyncio, app as app_mod
    from unittest.mock import patch
    _reset_relay_cache()
    # Register a relay backend ad-hoc.
    bid = client.post("/api/backends", json={
        "name": "test-relay", "kind": "ollama",
        "base_url": "https://app.interdataresearch.example.com",
    }).json()["id"]
    try:
        async def fake_list(_backend):
            return [{"name": "claimed-by-relay:1b"}, {"name": "another:7b"}]
        with patch("app.llm.list_models", side_effect=fake_list):
            original = {"id": 1, "name": "local", "kind": "ollama", "base_url": "http://localhost:11434"}
            result = asyncio.run(app_mod._maybe_override_to_relay(original, "claimed-by-relay:1b"))
        assert result["id"] == bid, f"expected override to relay id={bid}, got {result}"
        assert "interdataresearch" in result["base_url"]
    finally:
        # Cleanup: force-delete the test relay (no convs bound, so no cascade needed).
        client.delete(f"/api/backends/{bid}?force=true")
        _reset_relay_cache()


@test("relay override: model NOT on relay → original backend wins")
def _():
    import asyncio, app as app_mod
    from unittest.mock import patch
    _reset_relay_cache()
    bid = client.post("/api/backends", json={
        "name": "test-relay-2", "kind": "ollama",
        "base_url": "https://app.interdataresearch.example.com",
    }).json()["id"]
    try:
        async def fake_list(_backend):
            return [{"name": "only-this:1b"}]
        with patch("app.llm.list_models", side_effect=fake_list):
            original = {"id": 1, "name": "local", "kind": "ollama", "base_url": "http://localhost:11434"}
            result = asyncio.run(app_mod._maybe_override_to_relay(original, "nope:7b"))
        assert result is original, "expected pass-through when relay doesn't serve the model"
    finally:
        client.delete(f"/api/backends/{bid}?force=true")
        _reset_relay_cache()


@test("relay override: probe failure → original backend wins (no silent route to dead relay)")
def _():
    # If the relay's /api/tags is unreachable, the override must NOT silently
    # redirect — the chat would fail. Fall back to whatever the conversation
    # was originally pinned to.
    import asyncio, app as app_mod
    from unittest.mock import patch
    _reset_relay_cache()
    bid = client.post("/api/backends", json={
        "name": "test-relay-3", "kind": "ollama",
        "base_url": "https://app.interdataresearch.example.com",
    }).json()["id"]
    try:
        async def boom(_backend):
            raise ConnectionError("relay is down")
        with patch("app.llm.list_models", side_effect=boom):
            original = {"id": 1, "name": "local", "kind": "ollama", "base_url": "http://localhost:11434"}
            result = asyncio.run(app_mod._maybe_override_to_relay(original, "any-model"))
        assert result is original, "expected pass-through on probe failure"
    finally:
        client.delete(f"/api/backends/{bid}?force=true")
        _reset_relay_cache()


@test("relay override: MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE=1 disables the override")
def _():
    # Emergency stop for when the relay is degraded and the user wants
    # chats to follow conv.backend_id strictly. Test confirms the override
    # never probes when the env var is set.
    import asyncio, os, app as app_mod
    from unittest.mock import patch
    _reset_relay_cache()
    bid = client.post("/api/backends", json={
        "name": "test-relay-disable", "kind": "ollama",
        "base_url": "https://app.interdataresearch.example.com",
    }).json()["id"]
    try:
        call_count = {"n": 0}
        async def fake_list(_backend):
            call_count["n"] += 1
            return [{"name": "would-have-redirected:1b"}]
        with patch.dict(os.environ, {"MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE": "1"}), \
             patch("app.llm.list_models", side_effect=fake_list):
            original = {"id": 1, "name": "local", "kind": "ollama", "base_url": "http://localhost:11434"}
            result = asyncio.run(app_mod._maybe_override_to_relay(original, "would-have-redirected:1b"))
        assert result is original, "env-var disable should keep original backend"
        assert call_count["n"] == 0, "env-var disable should skip the probe entirely"
    finally:
        client.delete(f"/api/backends/{bid}?force=true")
        _reset_relay_cache()


@test("relay override: probe failure is cached — second call skips re-probe")
def _():
    # Without this caching, every chat during a relay outage would eat the
    # 5-second probe timeout. The fix: failure caches an empty model set
    # for the same TTL as success, so re-probes happen at most once per
    # TTL window even when the relay stays down.
    import asyncio, app as app_mod
    from unittest.mock import patch
    _reset_relay_cache()
    bid = client.post("/api/backends", json={
        "name": "test-relay-5", "kind": "ollama",
        "base_url": "https://app.interdataresearch.example.com",
    }).json()["id"]
    try:
        call_count = {"n": 0}
        async def boom(_backend):
            call_count["n"] += 1
            raise ConnectionError("timeout")
        with patch("app.llm.list_models", side_effect=boom):
            original = {"id": 1, "name": "local", "kind": "ollama", "base_url": "http://localhost:11434"}
            # First call → probes, fails, caches empty set.
            r1 = asyncio.run(app_mod._maybe_override_to_relay(original, "any-model"))
            # Second call → cache is fresh (even though empty), should NOT re-probe.
            r2 = asyncio.run(app_mod._maybe_override_to_relay(original, "any-model"))
            r3 = asyncio.run(app_mod._maybe_override_to_relay(original, "different-model"))
        assert r1 is original and r2 is original and r3 is original
        assert call_count["n"] == 1, f"expected exactly 1 probe (cached failure), got {call_count['n']}"
    finally:
        client.delete(f"/api/backends/{bid}?force=true")
        _reset_relay_cache()


@test("relay override: already on relay → no-op (skip the probe)")
def _():
    # Hot-path optimization: if the caller is ALREADY targeting the relay,
    # don't bother probing — return immediately.
    import asyncio, app as app_mod
    from unittest.mock import patch
    _reset_relay_cache()
    bid = client.post("/api/backends", json={
        "name": "test-relay-4", "kind": "ollama",
        "base_url": "https://app.interdataresearch.example.com",
    }).json()["id"]
    try:
        called = {"n": 0}
        async def counting_list(_backend):
            called["n"] += 1
            return [{"name": "any:1b"}]
        with patch("app.llm.list_models", side_effect=counting_list):
            relay_backend = {"id": bid, "name": "test-relay-4", "kind": "ollama",
                             "base_url": "https://app.interdataresearch.example.com"}
            result = asyncio.run(app_mod._maybe_override_to_relay(relay_backend, "any:1b"))
        assert result is relay_backend, "should return input unchanged"
        assert called["n"] == 0, "should not have probed when already on the relay"
    finally:
        client.delete(f"/api/backends/{bid}?force=true")
        _reset_relay_cache()


# ==================================================================
# Applications (groups of bots) + per-app TypeScript SDK
# ==================================================================

@test("apps: migration adds apps table + conversations.app_id")
def _():
    import sqlite3
    conn = sqlite3.connect(_TMP_DB)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "apps" in tables, tables
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)")}
        assert "app_id" in cols, cols
    finally:
        conn.close()


@test("apps: CRUD + bot_count; delete unlinks bots (keeps them)")
def _():
    bid = _add_openai_backend()
    b1 = client.post("/api/conversations", json={"title": "App Bot 1", "model": "openai-a-4b", "backend_id": bid}).json()["id"]
    b2 = client.post("/api/conversations", json={"title": "App Bot 2", "model": "openai-a-4b", "backend_id": bid}).json()["id"]
    r = client.post("/api/apps", json={"name": "Test App", "link": "https://x.example", "description": "d"})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["name"] == "Test App"
    assert client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b1}).status_code == 201
    assert client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b2}).status_code == 201
    row = next(a for a in client.get("/api/apps").json() if a["id"] == aid)
    assert row["bot_count"] == 2, row
    detail = client.get(f"/api/apps/{aid}").json()
    assert {x["title"] for x in detail["bots"]} == {"App Bot 1", "App Bot 2"}
    assert client.patch(f"/api/apps/{aid}", json={"name": "Renamed"}).status_code == 200
    assert client.get(f"/api/apps/{aid}").json()["name"] == "Renamed"
    # conversation list exposes app_id
    convs = {c["id"]: c["app_id"] for c in client.get("/api/conversations").json()}
    assert convs[b1] == aid, convs
    # delete app -> bots survive, ungrouped
    assert client.delete(f"/api/apps/{aid}").status_code == 200
    convs = {c["id"]: c["app_id"] for c in client.get("/api/conversations").json()}
    assert convs[b1] is None and convs[b2] is None, convs
    assert client.get(f"/api/conversations/{b1}").status_code == 200
    client.delete(f"/api/conversations/{b1}")
    client.delete(f"/api/conversations/{b2}")


@test("apps: one app per bot — adding to a second app moves it")
def _():
    bid = _add_openai_backend()
    b = client.post("/api/conversations", json={"title": "Mover", "model": "openai-a-4b", "backend_id": bid}).json()["id"]
    a1 = client.post("/api/apps", json={"name": "A1"}).json()["id"]
    a2 = client.post("/api/apps", json={"name": "A2"}).json()["id"]
    client.post(f"/api/apps/{a1}/bots", json={"conversation_id": b})
    assert len(client.get(f"/api/apps/{a1}").json()["bots"]) == 1
    client.post(f"/api/apps/{a2}/bots", json={"conversation_id": b})  # moves out of a1
    assert len(client.get(f"/api/apps/{a1}").json()["bots"]) == 0
    assert len(client.get(f"/api/apps/{a2}").json()["bots"]) == 1
    assert client.delete(f"/api/apps/{a2}/bots/{b}").status_code == 200
    assert len(client.get(f"/api/apps/{a2}").json()["bots"]) == 0
    # removing a bot not in the app -> 404
    assert client.delete(f"/api/apps/{a1}/bots/{b}").status_code == 404
    client.delete(f"/api/apps/{a1}")
    client.delete(f"/api/apps/{a2}")
    client.delete(f"/api/conversations/{b}")


@test("apps: SDK preview + zip expose bots as deduped functions")
def _():
    bid = _add_openai_backend()
    b1 = client.post("/api/conversations", json={"title": "Intake Reviewer", "model": "openai-a-4b", "backend_id": bid}).json()["id"]
    b2 = client.post("/api/conversations", json={"title": "Intake Reviewer", "model": "openai-a-4b", "backend_id": bid}).json()["id"]
    aid = client.post("/api/apps", json={"name": "SDK App"}).json()["id"]
    client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b1})
    client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b2})
    sdk = client.get(f"/api/apps/{aid}/sdk").json()
    paths = [f["path"] for f in sdk["files"]]
    assert any(p.endswith("client.ts") for p in paths), paths
    assert any(p.endswith("index.ts") for p in paths), paths
    bot_files = sorted(p for p in paths if "/bots/" in p)
    assert len(bot_files) == 2 and bot_files[0] != bot_files[1], bot_files  # dup titles deduped
    blob = "\n".join(f["content"] for f in sdk["files"])
    assert "intakeReviewer" in blob
    assert f"new Bot({b1})" in blob and f"new Bot({b2})" in blob, blob
    z = client.get(f"/api/apps/{aid}/sdk.zip")
    assert z.status_code == 200 and z.headers["content-type"].startswith("application/zip")
    assert "sdk-app-sdk.zip" in z.headers.get("content-disposition", "")
    import zipfile as _zip, io as _io
    names = _zip.ZipFile(_io.BytesIO(z.content)).namelist()
    assert any(n.endswith("index.ts") for n in names), names
    client.delete(f"/api/apps/{aid}")
    client.delete(f"/api/conversations/{b1}")
    client.delete(f"/api/conversations/{b2}")


@test("apps: SDK lang=js produces a JavaScript package + zip filename suffix")
def _():
    bid = _add_openai_backend()
    b = client.post("/api/conversations", json={
        "title": "Intake Reviewer", "model": "openai-a-4b", "backend_id": bid,
    }).json()["id"]
    aid = client.post("/api/apps", json={"name": "JS App"}).json()["id"]
    client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b})
    sdk = client.get(f"/api/apps/{aid}/sdk?lang=js").json()
    assert sdk["lang"] == "js"
    paths = [f["path"] for f in sdk["files"]]
    assert any(p.endswith("client.js") for p in paths), paths
    assert any(p.endswith("index.js") for p in paths), paths
    assert not any(p.endswith(".ts") for p in paths), paths  # no TS leakage
    blob = "\n".join(f["content"] for f in sdk["files"])
    assert "intakeReviewer" in blob          # camelCase function (same as TS)
    assert ": string" not in blob            # type annotations stripped
    z = client.get(f"/api/apps/{aid}/sdk.zip?lang=js")
    assert z.status_code == 200
    assert "js-app-js-sdk.zip" in z.headers.get("content-disposition", "")
    client.delete(f"/api/apps/{aid}")
    client.delete(f"/api/conversations/{b}")


@test("apps: SDK lang=py produces an importable Python package")
def _():
    bid = _add_openai_backend()
    b = client.post("/api/conversations", json={
        "title": "Intake Reviewer", "model": "openai-a-4b", "backend_id": bid,
    }).json()["id"]
    aid = client.post("/api/apps", json={"name": "Py App"}).json()["id"]
    client.post(f"/api/apps/{aid}/bots", json={"conversation_id": b})
    sdk = client.get(f"/api/apps/{aid}/sdk?lang=py").json()
    assert sdk["lang"] == "py"
    paths = [f["path"] for f in sdk["files"]]
    # Python package uses underscores in the folder so it's directly importable.
    assert all(p.startswith("py_app_sdk/") for p in paths), paths
    assert "py_app_sdk/__init__.py" in paths
    assert "py_app_sdk/client.py" in paths
    bot_files = [p for p in paths if p.startswith("py_app_sdk/bots/") and p.endswith(".py")
                 and not p.endswith("__init__.py")]
    assert len(bot_files) == 1, bot_files
    # Snake-case Python function name derived from the title.
    blob = "\n".join(f["content"] for f in sdk["files"])
    assert "def intake_reviewer(" in blob, blob
    assert f"Bot({b})" in blob, blob
    # All generated files must parse as Python.
    import ast as _ast
    for f in sdk["files"]:
        if f["path"].endswith(".py"):
            _ast.parse(f["content"], filename=f["path"])
    z = client.get(f"/api/apps/{aid}/sdk.zip?lang=py")
    assert z.status_code == 200
    assert "py-app-py-sdk.zip" in z.headers.get("content-disposition", "")
    client.delete(f"/api/apps/{aid}")
    client.delete(f"/api/conversations/{b}")


@test("apps: SDK lang validation — unknown value rejected, default stays ts")
def _():
    aid = client.post("/api/apps", json={"name": "Lang App"}).json()["id"]
    # No lang → default TypeScript (backwards-compat for existing clients).
    assert client.get(f"/api/apps/{aid}/sdk").json()["lang"] == "ts"
    # Unknown lang → 400.
    assert client.get(f"/api/apps/{aid}/sdk?lang=ruby").status_code == 400
    # Default zip keeps the old filename (no language suffix) for ts.
    z = client.get(f"/api/apps/{aid}/sdk.zip")
    assert "lang-app-sdk.zip" in z.headers.get("content-disposition", "")
    client.delete(f"/api/apps/{aid}")


@test("apps: 404s for missing app / bot")
def _():
    assert client.get("/api/apps/999999").status_code == 404
    assert client.patch("/api/apps/999999", json={"name": "x"}).status_code == 404
    assert client.delete("/api/apps/999999").status_code == 404
    assert client.get("/api/apps/999999/sdk").status_code == 404
    aid = client.post("/api/apps", json={"name": "E"}).json()["id"]
    assert client.post(f"/api/apps/{aid}/bots", json={"conversation_id": 999999}).status_code == 404
    client.delete(f"/api/apps/{aid}")


# ==================================================================
# xbench-methodology endpoints — clone, in-flight 409, nested params,
# auto-register against a fake miniclosedai-llm manager.
# ==================================================================

@test("clone: POST /api/conversations/{id}/clone copies config with empty messages")
def _():
    _reseed_builtin_to_fake_ollama()
    src = client.post("/api/conversations", json={
        "title": "extractor", "model": "ollama-a:3b",
        "system_prompt": "Return pure JSON.", "temperature": 0.2,
    }).json()
    try:
        r = client.post(f"/api/conversations/{src['id']}/clone", json={})
        assert r.status_code == 201, r.text
        new = r.json()
        try:
            assert new["from_id"] == src["id"]
            assert new["title"].startswith("extractor")
            got = client.get(f"/api/conversations/{new['id']}").json()
            assert got["model"] == "ollama-a:3b"
            assert got["system_prompt"] == "Return pure JSON."
            assert got["params"]["temperature"] == 0.2
            assert got["messages"] == []
        finally:
            client.delete(f"/api/conversations/{new['id']}")
    finally:
        client.delete(f"/api/conversations/{src['id']}")


@test("clone: body overrides apply (title + nested params merge)")
def _():
    _reseed_builtin_to_fake_ollama()
    src = client.post("/api/conversations", json={
        "title": "src", "model": "ollama-a:3b", "temperature": 0.7,
    }).json()
    try:
        r = client.post(f"/api/conversations/{src['id']}/clone", json={
            "title": "worker-0",
            "params": {"temperature": 0.0, "max_tokens": 999},
        })
        assert r.status_code == 201, r.text
        new_id = r.json()["id"]
        try:
            assert r.json()["title"] == "worker-0"
            got = client.get(f"/api/conversations/{new_id}").json()
            assert got["params"]["temperature"] == 0.0
            assert got["params"]["max_tokens"] == 999
        finally:
            client.delete(f"/api/conversations/{new_id}")
    finally:
        client.delete(f"/api/conversations/{src['id']}")


@test("clone: title-collision adds a numeric suffix")
def _():
    _reseed_builtin_to_fake_ollama()
    src = client.post("/api/conversations", json={
        "title": "dup", "model": "ollama-a:3b",
    }).json()
    a = client.post(f"/api/conversations/{src['id']}/clone", json={"title": "dup"}).json()
    b = client.post(f"/api/conversations/{src['id']}/clone", json={"title": "dup"}).json()
    try:
        assert a["title"] != b["title"], f"both clones got {a['title']!r}"
        assert "dup" in a["title"] and "dup" in b["title"]
    finally:
        client.delete(f"/api/conversations/{a['id']}")
        client.delete(f"/api/conversations/{b['id']}")
        client.delete(f"/api/conversations/{src['id']}")


@test("clone: 404 when source conv does not exist")
def _():
    r = client.post("/api/conversations/99999/clone", json={})
    assert r.status_code == 404, r.text


@test("conversations: accept nested params.temperature on create")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.post("/api/conversations", json={
        "model": "ollama-a:3b", "backend_id": 1,
        "params": {"temperature": 0.0, "top_p": 0.5},
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    try:
        got = client.get(f"/api/conversations/{cid}").json()
        assert got["params"]["temperature"] == 0.0
        assert got["params"]["top_p"] == 0.5
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("conversations: nested + top-level temperature CONFLICT → 400")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.post("/api/conversations", json={
        "model": "ollama-a:3b", "backend_id": 1,
        "temperature": 0.5, "params": {"temperature": 0.0},
    })
    assert r.status_code == 400, r.text
    assert "temperature" in r.text.lower()


@test("conversations: nested + top-level agreeing → 200 (idempotent)")
def _():
    _reseed_builtin_to_fake_ollama()
    r = client.post("/api/conversations", json={
        "model": "ollama-a:3b", "backend_id": 1,
        "temperature": 0.0, "params": {"temperature": 0.0},
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    try:
        assert client.get(f"/api/conversations/{cid}").json()["params"]["temperature"] == 0.0
    finally:
        client.delete(f"/api/conversations/{cid}")


@test("conversations: PATCH accepts nested params.temperature")
def _():
    _reseed_builtin_to_fake_ollama()
    cid = client.post("/api/conversations", json={"model": "ollama-a:3b"}).json()["id"]
    try:
        r = client.patch(f"/api/conversations/{cid}", json={"params": {"temperature": 0.0}})
        assert r.status_code == 200, r.text
        assert client.get(f"/api/conversations/{cid}").json()["params"]["temperature"] == 0.0
    finally:
        client.delete(f"/api/conversations/{cid}")


# ----- Auto-register against a fake miniclosedai-llm manager -----

class FakeManager(_FakeServer):
    """Speaks just enough of miniclosedai-llm's /api/models for the
    auto-register endpoint to find a served model."""

    def _handler_class(self):
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a, **kw): pass
            def do_GET(self):
                if self.path == "/api/models":
                    body = json.dumps([
                        {
                            "id": "qwen3-vl-8b",
                            "served_name": "qwen3-vl-8b",
                            "hf_id": "Qwen/Qwen3-VL-8B-Instruct",
                            "status": "running",
                            "base_url": "http://localhost:8001/v1",
                            "alt_base_url": "http://host.docker.internal:8001/v1",
                        },
                        {
                            "id": "stopped-model",
                            "served_name": "stopped-model",
                            "hf_id": "Foo/Bar",
                            "status": "stopped",
                            "base_url": "http://localhost:8002/v1",
                            "alt_base_url": "http://host.docker.internal:8002/v1",
                        },
                    ]).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404); self.end_headers()
        return H


fake_manager = FakeManager()


@test("auto-register: GET /api/models → INSERT openai backend with base_url")
def _():
    r = client.post("/api/backends/auto-register", json={
        "manager_url": fake_manager.base_url,
        "model_id": "qwen3-vl-8b",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    bid = body["id"]
    try:
        assert body["kind"] == "openai"
        assert body["base_url"] == "http://localhost:8001/v1"
        assert body["served_model"] == "qwen3-vl-8b"
        # Backend actually inserted in the DB.
        all_backends = client.get("/api/backends").json()
        assert any(b["id"] == bid for b in all_backends)
    finally:
        client.delete(f"/api/backends/{bid}")


@test("auto-register: prefer_docker_host=true picks alt_base_url")
def _():
    r = client.post("/api/backends/auto-register", json={
        "manager_url": fake_manager.base_url,
        "model_id": "qwen3-vl-8b",
        "prefer_docker_host": True,
    })
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    try:
        assert r.json()["base_url"] == "http://host.docker.internal:8001/v1"
    finally:
        client.delete(f"/api/backends/{bid}")


@test("auto-register: unknown model_id → 404 with available list")
def _():
    r = client.post("/api/backends/auto-register", json={
        "manager_url": fake_manager.base_url,
        "model_id": "no-such-model",
    })
    assert r.status_code == 404, r.text
    body = r.json()
    assert "available" in body["detail"]
    assert "qwen3-vl-8b" in body["detail"]["available"]


@test("auto-register: model exists but is stopped → 422")
def _():
    r = client.post("/api/backends/auto-register", json={
        "manager_url": fake_manager.base_url,
        "model_id": "stopped-model",
    })
    assert r.status_code == 422, r.text
    assert "not running" in r.text.lower() or "mc start" in r.text.lower()


@test("auto-register: unreachable manager → 502")
def _():
    r = client.post("/api/backends/auto-register", json={
        "manager_url": "http://127.0.0.1:1",   # nothing listening
        "model_id": "anything",
    })
    assert r.status_code == 502, r.text


# ----- In-flight 409 guard -----

@test("in-flight 409: second persist+message chat on same conv is rejected")
def _():
    """Manually park a 'running' generation in _generations[cid], then verify
    both /chat and /chat/stream reject new persist+message turns with 409.

    We park the marker directly (same trick the cancel-test uses, test_e2e.py
    around line 1493) rather than racing a real HTTP stream — TestClient
    consumes streams synchronously, which doesn't reliably leave the bg task
    in 'running' state long enough for sibling requests to observe it."""
    _reseed_builtin_to_fake_ollama()
    cid = client.post("/api/conversations", json={
        "model": "ollama-a:3b", "backend_id": 1, "temperature": 0.0,
    }).json()["id"]
    try:
        # Park a "running" generation marker on this conv.
        gen = app_mod._new_generation()
        app_mod._generations[cid] = gen

        # Streaming sibling → 409.
        r = client.post(f"/api/conversations/{cid}/chat/stream",
                        json={"message": "second", "persist": True})
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["detail"]["code"] == "generation_in_flight"
        assert "clone" in body["detail"]["message"].lower()

        # Non-streaming sibling → 409 too.
        r = client.post(f"/api/conversations/{cid}/chat",
                        json={"message": "second", "persist": True})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "generation_in_flight"

        # And reattach: true bypasses the guard (so the GUI's refresh-path
        # behaviour from API callers can also reconnect).
        gen["status"] = "running"   # ensure still parked
        r = client.post(f"/api/conversations/{cid}/chat",
                        json={"message": "second", "persist": True, "reattach": True})
        # The non-streaming /chat with reattach=true is allowed through; it
        # falls into the regular code path (which will fail downstream but
        # NOT with 409 — that's the only thing we're asserting).
        assert r.status_code != 409, r.text
    finally:
        app_mod._generations.pop(cid, None)
        client.delete(f"/api/conversations/{cid}")


@test("in-flight 409: non-persist or messages= form is NOT 409'd")
def _():
    """The 409 only applies to the persist + single-message path (where the
    background-resume race lives). One-shot non-persist callers run through
    the regular code path and never touch _generations."""
    _reseed_builtin_to_fake_ollama()
    cid = client.post("/api/conversations", json={
        "model": "ollama-a:3b", "backend_id": 1, "temperature": 0.0,
    }).json()["id"]
    try:
        gen = app_mod._new_generation()
        app_mod._generations[cid] = gen

        # persist=False → not guarded.
        r = client.post(f"/api/conversations/{cid}/chat",
                        json={"message": "fire and forget", "persist": False})
        assert r.status_code != 409, r.text
    finally:
        app_mod._generations.pop(cid, None)
        client.delete(f"/api/conversations/{cid}")


# ==================================================================
# Main
# ==================================================================

def main() -> int:
    print(f"\nrunning {len(_TESTS)} tests against temp DB {_TMP_DB}\n")
    t0 = time.perf_counter()
    # Enter the TestClient as a context manager so the underlying anyio portal
    # / asyncio loop persists across requests. Required for pull tests, which
    # rely on asyncio.create_task-spawned tasks surviving past the request that
    # started them — without this they get cancelled immediately.
    with client:
        for _, fn in _TESTS:
            fn()

    total = time.perf_counter() - t0
    passed  = sum(1 for _, ok, _ in _RESULTS if ok is True)
    skipped = sum(1 for _, ok, _ in _RESULTS if ok == "skip")
    failed  = len(_RESULTS) - passed - skipped
    print(f"\n{'='*48}")
    skip_str = f" · {skipped} skipped" if skipped else ""
    print(f"{passed}/{len(_RESULTS)} passed · {failed} failed{skip_str} · {total:.2f}s")
    print('='*48)
    if failed:
        print("\nFailures:")
        for name, ok, msg in _RESULTS:
            if ok is False:
                print(f"  ✗ {name}  → {msg}")
    if skipped:
        print("\nSkipped:")
        for name, ok, msg in _RESULTS:
            if ok == "skip":
                print(f"  ⊘ {name}  → {msg}")

    # Cleanup
    fake_ollama.stop()
    fake_openai.stop()
    try:
        os.unlink(_TMP_DB)
        os.rmdir(_TMP_DIR)
    except Exception:
        pass

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
