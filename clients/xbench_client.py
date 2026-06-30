"""xbench_client — minimal Python client for MiniClosedAI's benchmark APIs.

Wraps the four routes that make the `xbench` methodology a thin script
instead of a full harness:

    POST /api/conversations/{id}/clone      — duplicate a bot per worker
    POST /api/backends/auto-register        — register a vLLM-served model
                                              by asking miniclosedai-llm
                                              where it lives (no copy-paste)
    POST /api/conversations                 — create a bot, with `params`
                                              accepted nested OR top-level
    POST /api/conversations/{id}/chat       — synchronous one-turn call;
                                              raises GenerationInFlight when
                                              the conversation is busy

The whole client is one class + a few helper exceptions. No retries, no
state, no async — keep things observable. Wrap with a thread pool or
asyncio.to_thread() for parallel work.

Usage (the canonical pattern):

    from xbench_client import XBenchClient

    mc = XBenchClient("https://192.168.0.110:8095", verify=False)

    # 1. Register a vLLM-served model as a backend in one POST.
    backend = mc.auto_register_backend(
        manager_url="http://localhost:8099",
        model_id="qwen3-vl-8b",
    )

    # 2. Create a base extractor bot once. Temperature can be nested.
    base = mc.create_conversation(
        title="extractor base",
        model=backend["served_model"],
        backend_id=backend["id"],
        system_prompt="Return pure JSON. No prose. ...",
        params={"temperature": 0.0},
    )

    # 3. Per parallel worker, clone the base — DELETE after.
    with mc.clone(base["id"], title="worker-0") as worker:
        reply = mc.chat(worker.id, message="...", persist=True)

Everything below relies on `httpx` (already a miniclosedai runtime
dependency).
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

import httpx


class XBenchError(Exception):
    """Base class for client-side raises against MiniClosedAI."""


class GenerationInFlight(XBenchError):
    """Raised when a /chat or /chat/stream call returns 409 because another
    generation is still running on the same conversation. The fix is almost
    always to clone the bot for the second caller — see XBenchClient.clone."""

    def __init__(self, conv_id: int, message: str):
        super().__init__(message)
        self.conv_id = conv_id


class ModelNotRunning(XBenchError):
    """Raised when auto_register_backend finds the model on the manager but
    its status is not 'running'. The detail message points at `mc start`."""


class ManagerUnreachable(XBenchError):
    """Raised when MiniClosedAI's auto-register endpoint couldn't reach the
    miniclosedai-llm manager at all (network error, manager not booted)."""


class _ClonedConversation:
    """Returned by XBenchClient.clone() so callers can `with` it for auto-
    cleanup. Holds the new conversation's id + the parent client."""

    def __init__(self, client: "XBenchClient", row: dict):
        self._client = client
        self.row = row
        self.id: int = row["id"]
        self.title: str = row["title"]
        self.from_id: int = row["from_id"]

    def __enter__(self) -> "_ClonedConversation":
        return self

    def __exit__(self, *exc) -> None:
        # Best-effort delete — never raise during teardown.
        try:
            self._client.delete_conversation(self.id)
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"<ClonedConversation id={self.id} title={self.title!r} from_id={self.from_id}>"


class XBenchClient:
    """Thin sync client. One per process — share across threads."""

    def __init__(
        self,
        base_url: str = "https://localhost:8095",
        *,
        verify: bool | str = True,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            verify=verify,
            timeout=timeout,
            headers=headers or {},
        )

    # ---- Backends -------------------------------------------------------

    def auto_register_backend(
        self,
        *,
        manager_url: str,
        model_id: str,
        name: str | None = None,
        prefer_docker_host: bool = False,
        api_key: str | None = None,
    ) -> dict:
        """Register a vLLM-served model as an `openai` backend.

        Returns the new backend row (with `served_model` echoed for use as
        the bot's `model` field). Raises `ManagerUnreachable` (502),
        `ModelNotRunning` (422), or `XBenchError` (other) on failure.
        """
        r = self._client.post("/api/backends/auto-register", json={
            "manager_url": manager_url,
            "model_id": model_id,
            "name": name,
            "prefer_docker_host": prefer_docker_host,
            "api_key": api_key,
        })
        if r.status_code == 502:
            raise ManagerUnreachable(_extract_detail(r))
        if r.status_code == 422:
            raise ModelNotRunning(_extract_detail(r))
        if r.status_code == 404:
            raise XBenchError(_extract_detail(r))
        r.raise_for_status()
        return r.json()

    # ---- Conversations --------------------------------------------------

    def create_conversation(
        self,
        *,
        model: str,
        backend_id: int,
        title: str = "xbench bot",
        system_prompt: str = "You are a helpful AI assistant.",
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Create a bot. Sampling params can be nested under `params={...}`
        OR passed top-level via kwargs — both forms are equivalent on the
        server (as of the params-merge fix). Conflicting values raise 400."""
        body: dict[str, Any] = {
            "model": model,
            "backend_id": backend_id,
            "title": title,
            "system_prompt": system_prompt,
        }
        if params:
            body["params"] = params
        body.update(kwargs)
        r = self._client.post("/api/conversations", json=body)
        r.raise_for_status()
        return r.json()

    def clone(
        self,
        conv_id: int,
        *,
        title: str | None = None,
        backend_id: int | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> _ClonedConversation:
        """Clone a bot for parallel work. Returns a context-manager that
        deletes the clone on `__exit__` — pair with `with mc.clone(...) as c:`
        so a crashing worker can't leak bots."""
        body: dict[str, Any] = {}
        if title is not None:         body["title"] = title
        if backend_id is not None:    body["backend_id"] = backend_id
        if model is not None:         body["model"] = model
        if system_prompt is not None: body["system_prompt"] = system_prompt
        if params:                     body["params"] = params
        r = self._client.post(f"/api/conversations/{conv_id}/clone", json=body)
        r.raise_for_status()
        return _ClonedConversation(self, r.json())

    def delete_conversation(self, conv_id: int) -> None:
        r = self._client.delete(f"/api/conversations/{conv_id}")
        r.raise_for_status()

    # ---- Inference ------------------------------------------------------

    def chat(
        self,
        conv_id: int,
        *,
        message: str | None = None,
        messages: list[dict] | None = None,
        persist: bool = False,
        attachments: list[dict] | None = None,
        include_history: bool = False,
    ) -> str:
        """One-shot chat. Returns the assistant text.

        Raises `GenerationInFlight` if another generation is already
        running on this conversation — that's a signal to use `clone()`
        for the parallel work the caller is doing.
        """
        body: dict[str, Any] = {"persist": persist, "include_history": include_history}
        if message is not None: body["message"] = message
        if messages is not None: body["messages"] = messages
        if attachments is not None: body["attachments"] = attachments
        r = self._client.post(f"/api/conversations/{conv_id}/chat", json=body)
        if r.status_code == 409:
            data = r.json().get("detail") or {}
            if isinstance(data, dict) and data.get("code") == "generation_in_flight":
                raise GenerationInFlight(conv_id, data.get("message") or "in flight")
        r.raise_for_status()
        return r.text  # the route returns plain JSON-encoded string

    # ---- Resource cleanup ----------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "XBenchClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _extract_detail(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail")
        if isinstance(d, dict):
            msg = d.get("message") or d.get("detail") or ""
            hint = d.get("hint")
            return f"{msg}{(' Hint: ' + hint) if hint else ''}".strip() or str(d)
        return str(d) if d else f"HTTP {r.status_code}"
    except Exception:
        return f"HTTP {r.status_code}: {r.text[:200]}"


@contextlib.contextmanager
def cloned_bots(
    mc: XBenchClient, base_id: int, n: int, **clone_kwargs: Any
) -> Iterator[list[_ClonedConversation]]:
    """Create N clones of a base bot for a benchmark fan-out, delete them all
    on exit (even on exception). Caller picks the parallelism — this just
    ensures cleanup."""
    clones: list[_ClonedConversation] = []
    try:
        for i in range(n):
            title = clone_kwargs.get("title", f"worker-{i}")
            kwargs = dict(clone_kwargs)
            kwargs["title"] = f"{title}-{i}" if "{i}" not in title else title.format(i=i)
            clones.append(mc.clone(base_id, **kwargs))
        yield clones
    finally:
        for c in clones:
            try:
                mc.delete_conversation(c.id)
            except Exception:
                pass
