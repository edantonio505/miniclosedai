"""miniclosedai_client.py — a tiny, dependency-free client for MiniClosedAI bots.

Copy this ONE file into your project. No `pip install` needed — it's stdlib only
(urllib + json). Each saved MiniClosedAI bot is a callable "expert"; this wraps
the HTTP API so you can compose a fleet of them in your own orchestration code:

    from miniclosedai_client import Bot

    triage = Bot.find("triage")          # or Bot(12) by id (the </> "Copy bot ID" pill)
    writer = Bot.find("writer")          # or Bot(56)

    topic = triage.ask("My order #4471 is 2 weeks late!", history=False)
    reply = writer.ask(f"Draft a calm apology about: {topic}", history=False)
    print(reply)

This is the "multi-LLM management" pattern: MiniClosedAI hosts the bots (each with
its own model, knowledge base, and tools); your script is the orchestration layer
that wires them together. Point at your instance with the MINICLOSEDAI_BASE_URL
env var, or pass base_url=... explicitly.
"""
# Defer annotation evaluation — otherwise the `list` classmethod below shadows
# the builtin `list` in the class namespace and breaks `-> list[dict]` hints.
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = os.environ.get("MINICLOSEDAI_BASE_URL", "http://localhost:8095")


class MiniClosedAIError(RuntimeError):
    """Raised on a non-2xx response or an unreachable server."""


def _request(method: str, url: str, payload: dict | None = None, timeout: float = 300.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise MiniClosedAIError(f"{method} {url} -> HTTP {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        raise MiniClosedAIError(f"Could not reach {url}: {e.reason}")


class Bot:
    """A handle to one saved MiniClosedAI conversation (a configured bot)."""

    def __init__(self, conv_id: int, base_url: str = DEFAULT_BASE_URL):
        self.id = conv_id
        self.base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return f"<Bot #{self.id} @ {self.base_url}>"

    # ---- discovery -----------------------------------------------------
    @classmethod
    def list(cls, base_url: str = DEFAULT_BASE_URL) -> list[dict]:
        """Every saved bot: [{id, title, model, backend_id, updated_at}, ...]."""
        return _request("GET", f"{base_url.rstrip('/')}/api/conversations")

    @classmethod
    def find(cls, title_contains: str, base_url: str = DEFAULT_BASE_URL) -> "Bot":
        """Return the first bot whose title contains `title_contains` (case-insensitive)."""
        needle = title_contains.lower()
        for c in cls.list(base_url):
            if needle in (c.get("title") or "").lower():
                return cls(c["id"], base_url)
        raise MiniClosedAIError(f"No bot whose title contains {title_contains!r}")

    # ---- chat ----------------------------------------------------------
    def ask(self, message: str, history: bool = True, persist: bool = False) -> str:
        """Send a message; return the assistant's reply text.

        history=True replays the bot's saved turns (conversational memory).
        history=False = one-shot pure function (classifiers / routers / extractors).
        persist=True appends this turn to the bot's saved history.
        """
        out = _request(
            "POST",
            f"{self.base_url}/api/conversations/{self.id}/chat",
            {"message": message, "include_history": history, "persist": persist},
        )
        return out.get("response", "")

    def stream(self, message: str, history: bool = True, persist: bool = False):
        """Yield reply text chunks as they stream in (SSE)."""
        payload = json.dumps(
            {"message": message, "include_history": history, "persist": persist}
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/conversations/{self.id}/chat/stream",
            data=payload, method="POST", headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:  # SSE frames are newline-delimited
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if ev.get("error"):
                    raise MiniClosedAIError(ev["error"])
                if "chunk" in ev:
                    yield ev["chunk"]
                if ev.get("end"):
                    break

    # ---- knowledge base ------------------------------------------------
    def add_text(self, filename: str, text: str) -> dict:
        """Add a text document to this bot's knowledge base (chunked + embedded)."""
        return _request(
            "POST",
            f"{self.base_url}/api/conversations/{self.id}/knowledge",
            {"filename": filename, "text": text},
        )

    def add_file(self, path: str) -> dict:
        """Add a local .txt / .md (or any UTF-8 text) file to the knowledge base."""
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return self.add_text(os.path.basename(path), text)

    def knowledge(self) -> list[dict]:
        """List the documents in this bot's knowledge base."""
        return _request(
            "GET", f"{self.base_url}/api/conversations/{self.id}/knowledge"
        ).get("documents", [])
