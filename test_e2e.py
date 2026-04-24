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
    """
    dirty = False

    def _handler_class(self):
        captured = self.captured
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a, **kw): pass  # silent

            def do_GET(self):
                if self.path == "/api/tags":
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
                    captured.append({"path": self.path, "payload": payload})
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


# ==================================================================
# Main
# ==================================================================

def main() -> int:
    print(f"\nrunning {len(_TESTS)} tests against temp DB {_TMP_DB}\n")
    t0 = time.perf_counter()
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
