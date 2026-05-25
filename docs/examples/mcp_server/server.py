"""Minimal MCP server you can plug into a MiniClosedAI bot.

This is the easiest way to write a "plugin" for MiniClosedAI: define plain
Python functions, decorate them with @mcp.tool(), and serve over Streamable
HTTP. The function's type hints + docstring become the tool schema the model
sees — so a clear one-line docstring per tool is all the "spec" you need.

Run it:

    pip install mcp            # already in MiniClosedAI's requirements.txt
    python docs/examples/mcp_server/server.py

It serves at  http://localhost:8765/mcp  (the path is always /mcp).

Then in MiniClosedAI: open a bot → sidebar "Extensions" panel → paste
`http://localhost:8765/mcp` → Add. The bot can now call these tools mid-chat
(needs a tool-calling-capable model — qwen3, llama3.x, mistral, …).

NOTE: transport MUST be "streamable-http" — MiniClosedAI's MCP host connects
over Streamable HTTP, not stdio. Port 8765 is used to avoid the common 8000.
"""
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("miniclosedai-demo-tools", host="127.0.0.1", port=8765)


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


@mcp.tool()
def current_utc_time() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@mcp.tool()
def weather(city: str) -> str:
    """Get the current weather for a city. (Demo: returns a canned value.)"""
    return f"It is 21°C and sunny in {city}."


if __name__ == "__main__":
    # Streamable HTTP transport — this is the one MiniClosedAI speaks.
    mcp.run(transport="streamable-http")
