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
                    for f in frames:
                        self.wfile.write((json.dumps(f) + "\n").encode())
                        self.wfile.flush()
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


@test("backends: DELETE built-in is forbidden (403)")
def _():
    r = client.delete("/api/backends/1")
    assert r.status_code == 403


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
    assert 'data-page="dashboard"' in body
    assert 'class="activity-bar"' in body
    assert 'class="page page-dashboard"' in body
    assert 'class="page page-settings"' in body


@test("static: app.js is served and contains recent helpers")
def _():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    for needle in ("initActivityBar", "loadBackends", "prettifyJSONInMarkdown",
                   "_selectModelOption", "flushPendingSave",
                   "openInlineEditor", "_appendEditButton"):
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
    # 11 MB of zero bytes — past the 10 MB cap.
    big = b"\x00" * (11 * 1024 * 1024)
    r = client.post(
        "/api/extract-pdf",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"].lower()


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
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = len(_RESULTS) - passed
    print(f"\n{'='*48}")
    print(f"{passed}/{len(_RESULTS)} passed · {failed} failed · {total:.2f}s")
    print('='*48)
    if failed:
        print("\nFailures:")
        for name, ok, msg in _RESULTS:
            if not ok:
                print(f"  ✗ {name}  → {msg}")

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
