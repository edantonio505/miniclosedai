"""sdkgen.py — generate a per-application TypeScript SDK for a group of bots.

Each MiniClosedAI "application" (a named group of bots) can emit a tiny,
dependency-free TypeScript SDK: a port of `docs/examples/client/
miniclosedai_client.py`, but with the application's specific bots pre-wired as
named functions. Drop the folder into a TS project (e.g. LAILA) and call the
bots over the running MiniClosedAI HTTP API:

    import { triage, writer } from "./my-app-sdk";
    const intent = await triage("Order #4471 is late");      // one-shot expert
    const reply  = await writer(`Apologise about: ${intent}`);

`generate_ts_sdk(app, bots, base_url)` returns a list of {path, content} files.
The two routes in app.py turn that into a preview (JSON) or a .zip download.

Stdlib only — mirrors the rest of the project (no external deps).
"""
from __future__ import annotations

import re

# Keywords we must not emit as a bare identifier for a bot function/handle.
_RESERVED = {
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "export", "extends", "false",
    "finally", "for", "function", "if", "import", "in", "instanceof", "new",
    "null", "return", "super", "switch", "this", "throw", "true", "try",
    "typeof", "var", "void", "while", "with", "yield", "let", "static",
    "await", "async", "Bot", "DEFAULT_BASE_URL", "MiniClosedAIError",
}


def slugify(name: str, fallback: str = "app") -> str:
    """Folder-safe slug: lowercase, alphanumerics + single hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or fallback


def _camel(name: str) -> str:
    """A camelCase JS identifier derived from a (possibly messy) bot title."""
    parts = re.split(r"[^a-zA-Z0-9]+", name or "")
    parts = [p for p in parts if p]
    if not parts:
        return ""
    head, *tail = parts
    # An all-caps head (e.g. an acronym like "LAILA" or "API") reads better
    # fully lowercased ("laila", "api") than half-cased ("lAILA", "aPI").
    head_ident = head.lower() if head.isupper() else head[:1].lower() + head[1:]
    ident = head_ident + "".join(p[:1].upper() + p[1:] for p in tail)
    if ident and ident[0].isdigit():
        ident = "bot" + ident[0].upper() + ident[1:]
    return ident


def function_names(bots: list[dict]) -> dict[int, str]:
    """Map each bot id → a unique, valid JS identifier.

    Titles are NOT unique in MiniClosedAI, so collisions (and reserved words /
    empty titles) are disambiguated by appending the bot's id.
    """
    seen: set[str] = set()
    out: dict[int, str] = {}
    for b in bots:
        bid = int(b["id"])
        base = _camel(b.get("title") or "")
        if not base or base in _RESERVED:
            base = f"bot{bid}"
        name = base
        if name in seen:
            name = f"{base}_{bid}"
        seen.add(name)
        out[bid] = name
    return out


def _jsdoc(text: str) -> str:
    """Make a string safe to drop inside a /** ... */ JSDoc comment."""
    return (text or "").replace("*/", "* /").replace("\r", " ").replace("\n", " ")


def _line_comment(text: str) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ")


# --- client.ts -------------------------------------------------------------
# `__BASE_URL__` is replaced with the generating server's origin. Note the TS
# below is intentionally close, line-for-line, to miniclosedai_client.py.
_CLIENT_TS = '''\
/**
 * client.ts — a tiny, dependency-free TypeScript client for MiniClosedAI bots.
 *
 * Ported from docs/examples/client/miniclosedai_client.py. Uses the global
 * `fetch` (Node 18+ or any browser). Each saved MiniClosedAI bot is a callable
 * "expert"; this wraps the HTTP API so you can compose a fleet of them in your
 * own orchestration code.
 *
 * Point at your instance with the MINICLOSEDAI_BASE_URL env var (Node) or by
 * passing { baseUrl } per call / to a Bot constructor. MiniClosedAI must be
 * running and reachable for these calls to work.
 */

export class MiniClosedAIError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MiniClosedAIError";
  }
}

function envBaseUrl(): string | undefined {
  // Read process.env without requiring @types/node to be installed.
  const p = (globalThis as any).process;
  return p && p.env ? p.env.MINICLOSEDAI_BASE_URL : undefined;
}

export const DEFAULT_BASE_URL: string = envBaseUrl() || "__BASE_URL__";

export interface BotInfo {
  id: number;
  title: string;
  model: string;
  backend_id?: number;
  app_id?: number | null;
  updated_at?: string;
}

export interface AskOptions {
  /** Replay the bot's saved turns (conversational memory). Default true. */
  history?: boolean;
  /** Append this turn to the bot's saved history on the server. Default false. */
  persist?: boolean;
  /** Override the server base URL for this single call. */
  baseUrl?: string;
}

function trimSlash(u: string): string {
  return u.replace(/\\/+$/, "");
}

async function request<T = any>(method: string, url: string, payload?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: payload !== undefined ? JSON.stringify(payload) : undefined,
    });
  } catch (e) {
    throw new MiniClosedAIError(`Could not reach ${url}: ${String(e)}`);
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new MiniClosedAIError(`${method} ${url} -> HTTP ${res.status}: ${detail.slice(0, 300)}`);
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : {}) as T;
}

/** A handle to one saved MiniClosedAI conversation (a configured bot). */
export class Bot {
  readonly id: number;
  readonly baseUrl: string;

  constructor(id: number, baseUrl: string = DEFAULT_BASE_URL) {
    this.id = id;
    this.baseUrl = trimSlash(baseUrl);
  }

  toString(): string {
    return `<Bot #${this.id} @ ${this.baseUrl}>`;
  }

  /** Send a message; resolve to the assistant's reply text. */
  async ask(message: string, opts: AskOptions = {}): Promise<string> {
    const base = trimSlash(opts.baseUrl ?? this.baseUrl);
    const out = await request<{ response?: string }>(
      "POST",
      `${base}/api/conversations/${this.id}/chat`,
      { message, include_history: opts.history ?? true, persist: opts.persist ?? false },
    );
    return out.response ?? "";
  }

  /** Yield reply text chunks as they stream in (SSE). */
  async *stream(message: string, opts: AskOptions = {}): AsyncGenerator<string, void, unknown> {
    const base = trimSlash(opts.baseUrl ?? this.baseUrl);
    let res: Response;
    try {
      res = await fetch(`${base}/api/conversations/${this.id}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          include_history: opts.history ?? true,
          persist: opts.persist ?? false,
        }),
      });
    } catch (e) {
      throw new MiniClosedAIError(`Could not reach ${base}: ${String(e)}`);
    }
    if (!res.ok || !res.body) {
      const detail = await res.text().catch(() => "");
      throw new MiniClosedAIError(`stream -> HTTP ${res.status}: ${detail.slice(0, 300)}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\\n\\n");
      buf = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        let ev: any;
        try {
          ev = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        if (ev.error) throw new MiniClosedAIError(ev.error);
        if (typeof ev.chunk === "string") yield ev.chunk;
        if (ev.end) return;
      }
    }
  }

  /** Every saved bot on the server: [{ id, title, model, ... }, ...]. */
  static async list(baseUrl: string = DEFAULT_BASE_URL): Promise<BotInfo[]> {
    return request<BotInfo[]>("GET", `${trimSlash(baseUrl)}/api/conversations`);
  }

  /** First bot whose title contains `titleContains` (case-insensitive). */
  static async find(titleContains: string, baseUrl: string = DEFAULT_BASE_URL): Promise<Bot> {
    const needle = titleContains.toLowerCase();
    for (const c of await Bot.list(baseUrl)) {
      if ((c.title ?? "").toLowerCase().includes(needle)) return new Bot(c.id, baseUrl);
    }
    throw new MiniClosedAIError(`No bot whose title contains ${JSON.stringify(titleContains)}`);
  }
}
'''


def _bot_file_ts(bot: dict, fn: str) -> str:
    bid = int(bot["id"])
    title = bot.get("title") or f"Bot #{bid}"
    model = bot.get("model") or ""
    handle = f"{fn}Bot"
    return (
        'import { Bot, type AskOptions } from "../client.js";\n'
        "\n"
        f"/** {_jsdoc(title)} — bot #{bid}" + (f" (model: {_jsdoc(model)})" if model else "") + " */\n"
        f"export const {handle} = new Bot({bid});\n"
        "\n"
        f'/** Ask "{_jsdoc(title)}" (bot #{bid}). Pass {{ history: false }} for a one-shot call. */\n'
        f"export function {fn}(message: string, opts?: AskOptions): Promise<string> {{\n"
        f"  return {handle}.ask(message, opts);\n"
        "}\n"
    )


def _index_ts(app: dict, bots: list[dict], names: dict[int, str]) -> str:
    app_name = app.get("name") or "Application"
    app_const = _camel(app_name) or "app"
    if app_const in _RESERVED:
        app_const = "app"

    lines: list[str] = []
    lines.append(f"// MiniClosedAI SDK for application: {_line_comment(app_name)}")
    if app.get("link"):
        lines.append(f"// {_line_comment(app['link'])}")
    if app.get("description"):
        lines.append(f"// {_line_comment(app['description'])}")
    lines.append("//")
    lines.append("// Generated by MiniClosedAI. Requires a running MiniClosedAI server.")
    lines.append("")
    lines.append('export * from "./client.js";')
    lines.append("")
    for b in bots:
        fn = names[int(b["id"])]
        lines.append(f'export {{ {fn}, {fn}Bot }} from "./bots/{fn}.js";')
    lines.append("")
    if bots:
        for b in bots:
            fn = names[int(b["id"])]
            lines.append(f'import {{ {fn} }} from "./bots/{fn}.js";')
        lines.append("")
        lines.append(f"/** All bots in \"{_jsdoc(app_name)}\", keyed by function name. */")
        lines.append(f"export const {app_const} = {{")
        for b in bots:
            fn = names[int(b["id"])]
            lines.append(f"  {fn},")
        lines.append("};")
    else:
        lines.append("// (This application has no bots yet — add some in the MiniClosedAI GUI.)")
    lines.append("")
    return "\n".join(lines)


def _readme_md(app: dict, bots: list[dict], names: dict[int, str], slug: str, base_url: str) -> str:
    app_name = app.get("name") or "Application"
    row_list = []
    for b in bots:
        fn = names[int(b["id"])]
        safe_title = (b.get("title") or "").replace("|", r"\|")
        row_list.append(f"| `{fn}` | #{b['id']} | {safe_title} |")
    rows = "\n".join(row_list) or "| _(no bots yet)_ | | |"
    first_fn = names[int(bots[0]["id"])] if bots else "myBot"
    return f"""# {app_name} — MiniClosedAI SDK

A tiny, dependency-free TypeScript SDK for the bots in the **{app_name}** application.
Generated by MiniClosedAI. It talks to a **running** MiniClosedAI server over HTTP.

## Use it

Copy this `{slug}-sdk/` folder into your TypeScript project, then:

```ts
import {{ {first_fn} }} from "./{slug}-sdk";

const reply = await {first_fn}("Hello!");      // one round-trip to the bot
console.log(reply);
```

Each bot is exposed as a function (one-shot `ask`) and as a `Bot` handle
(`{first_fn}Bot`) for streaming or conversational use:

```ts
import {{ {first_fn}Bot }} from "./{slug}-sdk";

for await (const chunk of {first_fn}Bot.stream("Tell me a story", {{ history: true }})) {{
  process.stdout.write(chunk);
}}
```

## Configuration

The server base URL is baked in as `{base_url}`. Override it without editing code
via the `MINICLOSEDAI_BASE_URL` environment variable (Node), or per call:

```ts
await {first_fn}("Hi", {{ baseUrl: "http://localhost:8095" }});
```

Requires Node 18+ (global `fetch`) or a browser.

## Bots in this application

| Function | Bot ID | Title |
|----------|--------|-------|
{rows}
"""


def _package_json(app: dict, slug: str) -> str:
    name = app.get("name") or "Application"
    desc = (name + " — generated MiniClosedAI SDK").replace('"', "'")
    return (
        "{\n"
        f'  "name": "{slug}-sdk",\n'
        '  "version": "0.0.0",\n'
        '  "private": true,\n'
        '  "type": "module",\n'
        f'  "description": "{desc}"\n'
        "}\n"
    )


def generate_ts_sdk(app: dict, bots: list[dict], base_url: str) -> list[dict]:
    """Build the TypeScript SDK files for one application.

    Returns [{ "path": "<slug>-sdk/...", "content": "..." }, ...]. `path` values
    are root-relative (forward slashes) so the caller can preview them or zip
    them directly.
    """
    slug = slugify(app.get("name") or "app")
    root = f"{slug}-sdk"
    names = function_names(bots)

    files: list[dict] = []
    files.append({"path": f"{root}/client.ts", "content": _CLIENT_TS.replace("__BASE_URL__", base_url)})
    for b in bots:
        fn = names[int(b["id"])]
        files.append({"path": f"{root}/bots/{fn}.ts", "content": _bot_file_ts(b, fn)})
    files.append({"path": f"{root}/index.ts", "content": _index_ts(app, bots, names)})
    files.append({"path": f"{root}/README.md", "content": _readme_md(app, bots, names, slug, base_url)})
    files.append({"path": f"{root}/package.json", "content": _package_json(app, slug)})
    return files
