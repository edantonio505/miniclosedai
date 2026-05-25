"""MCP (Model Context Protocol) host — lets a bot use remote MCP servers as tools.

MiniClosedAI acts as an MCP *client/host*: a bot is configured with a list of
remote MCP server URLs, and on a chat turn the model can call the tools those
servers expose. This makes "writing a plugin" mean "writing (or pointing at) an
MCP server" — no MiniClosedAI-specific plugin format, and instant access to the
existing MCP ecosystem.

Design choices for simplicity (v1):
  - Remote (Streamable HTTP) servers only — no spawning local stdio subprocesses
    (that's the bigger security surface; remote URLs are opt-in + allowlistable).
  - Stateless: we connect per operation (list tools / call a tool). MCP servers
    are built to handle this; it avoids long-lived session bookkeeping. Slower
    than a persistent session, fine for v1.

Public surface:
  - list_tools(url, headers)            -> list[ToolSpec]   (OpenAI tool schema)
  - call_tool(url, headers, name, args) -> str              (text result)
  - gather_tools(servers)               -> (tools, routing) across all servers
"""
from __future__ import annotations

import asyncio
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# Don't let a slow/hung MCP server stall a chat turn forever.
_CONNECT_TIMEOUT = 20.0


async def _with_session(url: str, headers: dict | None, fn):
    """Open a short-lived MCP session to `url`, run `fn(session)`, tear down."""
    async with streamablehttp_client(url, headers=headers or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _tool_to_openai_schema(tool: Any) -> dict:
    """Map an MCP Tool into the OpenAI/Ollama function-tool schema both
    backends understand."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "")[:1024],
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


async def list_tools(url: str, headers: dict | None = None) -> list[dict]:
    """Return the server's tools as OpenAI-style tool specs. Raises on failure."""
    async def _fn(session: ClientSession):
        result = await session.list_tools()
        return [_tool_to_openai_schema(t) for t in (result.tools or [])]

    return await asyncio.wait_for(_with_session(url, headers, _fn), timeout=_CONNECT_TIMEOUT)


async def call_tool(url: str, headers: dict | None, name: str, arguments: dict) -> str:
    """Invoke one tool and return its text content (concatenated text blocks)."""
    async def _fn(session: ClientSession):
        result = await session.call_tool(name, arguments or {})
        parts: list[str] = []
        for block in (result.content or []):
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        if not parts and getattr(result, "isError", False):
            return "(tool returned an error with no text)"
        return "\n".join(parts) if parts else "(tool returned no text content)"

    return await asyncio.wait_for(_with_session(url, headers, _fn), timeout=_CONNECT_TIMEOUT)


async def gather_tools(servers: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """Collect tools across all enabled servers.

    Returns:
      tools   — combined list of OpenAI tool specs to hand the model.
      routing — tool_name -> {"url", "headers"} so we know where to dispatch a
                call. On a name collision, the first server wins (and the dup is
                dropped) so the model never sees two tools with the same name.

    A server that fails to connect is skipped (best-effort) — one broken plugin
    shouldn't break the others or the chat turn.
    """
    tools: list[dict] = []
    routing: dict[str, dict] = {}
    for srv in servers:
        if not srv.get("enabled", True):
            continue
        url = srv.get("url")
        if not url:
            continue
        headers = srv.get("headers") or None
        try:
            specs = await list_tools(url, headers)
        except Exception:
            continue  # skip unreachable / broken server
        for spec in specs:
            name = spec["function"]["name"]
            if name in routing:
                continue  # first server wins on collision
            routing[name] = {"url": url, "headers": headers}
            tools.append(spec)
    return tools, routing
