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

/** Optional bearer for MiniClosedAI installs with authentication enabled
 *  (Settings → Security). Unset = requests are sent without auth, which the
 *  server allows in grace mode (they show up as "connections needing
 *  attention" for the instance owner). */
export let API_KEY: string | undefined;
export function setApiKey(key: string | undefined): void { API_KEY = key; }

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["Authorization"] = `Bearer ${API_KEY}`;
  return h;
}

async function request<T = any>(method: string, url: string, payload?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: authHeaders(),
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
        headers: authHeaders(),
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


# =====================================================================
# JavaScript SDK — same shape as the TS one (per-bot files, an index
# barrel, a README, a package.json) but with the type annotations
# stripped so the folder runs in plain Node 18+ / any modern browser.
# =====================================================================

_CLIENT_JS = '''\
/**
 * client.js — a tiny, dependency-free JavaScript client for MiniClosedAI bots.
 *
 * Ported from docs/examples/client/miniclosedai_client.py. Uses the global
 * `fetch` (Node 18+ or any browser). Each saved MiniClosedAI bot is a callable
 * "expert"; this wraps the HTTP API so you can compose a fleet of them in your
 * own orchestration code.
 *
 * Point at your instance with the MINICLOSEDAI_BASE_URL env var (Node) or by
 * passing { baseUrl } per call / to a Bot constructor.
 */

export class MiniClosedAIError extends Error {
  constructor(message) {
    super(message);
    this.name = "MiniClosedAIError";
  }
}

function envBaseUrl() {
  const p = globalThis.process;
  return p && p.env ? p.env.MINICLOSEDAI_BASE_URL : undefined;
}

export const DEFAULT_BASE_URL = envBaseUrl() || "__BASE_URL__";

function trimSlash(u) {
  return u.replace(/\\/+$/, "");
}

/** Optional bearer for MiniClosedAI installs with authentication enabled
 *  (Settings → Security). Unset = grace mode on the server side. */
export let API_KEY = process?.env?.MINICLOSEDAI_API_KEY || undefined;
export function setApiKey(key) { API_KEY = key; }

function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (API_KEY) h["Authorization"] = `Bearer ${API_KEY}`;
  return h;
}

async function request(method, url, payload) {
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: authHeaders(),
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
  return text ? JSON.parse(text) : {};
}

/** A handle to one saved MiniClosedAI conversation (a configured bot). */
export class Bot {
  constructor(id, baseUrl = DEFAULT_BASE_URL) {
    this.id = id;
    this.baseUrl = trimSlash(baseUrl);
  }

  toString() {
    return `<Bot #${this.id} @ ${this.baseUrl}>`;
  }

  /** Send a message; resolve to the assistant's reply text. */
  async ask(message, opts = {}) {
    const base = trimSlash(opts.baseUrl ?? this.baseUrl);
    const out = await request(
      "POST",
      `${base}/api/conversations/${this.id}/chat`,
      { message, include_history: opts.history ?? true, persist: opts.persist ?? false },
    );
    return out.response ?? "";
  }

  /** Yield reply text chunks as they stream in (SSE). */
  async *stream(message, opts = {}) {
    const base = trimSlash(opts.baseUrl ?? this.baseUrl);
    let res;
    try {
      res = await fetch(`${base}/api/conversations/${this.id}/chat/stream`, {
        method: "POST",
        headers: authHeaders(),
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
        let ev;
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

  /** Every saved bot on the server. */
  static async list(baseUrl = DEFAULT_BASE_URL) {
    return request("GET", `${trimSlash(baseUrl)}/api/conversations`);
  }

  /** First bot whose title contains `titleContains` (case-insensitive). */
  static async find(titleContains, baseUrl = DEFAULT_BASE_URL) {
    const needle = titleContains.toLowerCase();
    for (const c of await Bot.list(baseUrl)) {
      if ((c.title ?? "").toLowerCase().includes(needle)) return new Bot(c.id, baseUrl);
    }
    throw new MiniClosedAIError(`No bot whose title contains ${JSON.stringify(titleContains)}`);
  }
}
'''


def _bot_file_js(bot: dict, fn: str) -> str:
    bid = int(bot["id"])
    title = bot.get("title") or f"Bot #{bid}"
    model = bot.get("model") or ""
    handle = f"{fn}Bot"
    return (
        'import { Bot } from "../client.js";\n'
        "\n"
        f"/** {_jsdoc(title)} — bot #{bid}" + (f" (model: {_jsdoc(model)})" if model else "") + " */\n"
        f"export const {handle} = new Bot({bid});\n"
        "\n"
        f'/** Ask "{_jsdoc(title)}" (bot #{bid}). Pass {{ history: false }} for a one-shot call. */\n'
        f"export function {fn}(message, opts) {{\n"
        f"  return {handle}.ask(message, opts);\n"
        "}\n"
    )


def _index_js(app: dict, bots: list[dict], names: dict[int, str]) -> str:
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
        lines.append(f'/** All bots in "{_jsdoc(app_name)}", keyed by function name. */')
        lines.append(f"export const {app_const} = {{")
        for b in bots:
            fn = names[int(b["id"])]
            lines.append(f"  {fn},")
        lines.append("};")
    else:
        lines.append("// (This application has no bots yet — add some in the MiniClosedAI GUI.)")
    lines.append("")
    return "\n".join(lines)


def _readme_md_js(app: dict, bots: list[dict], names: dict[int, str], slug: str, base_url: str) -> str:
    app_name = app.get("name") or "Application"
    row_list = []
    for b in bots:
        fn = names[int(b["id"])]
        safe_title = (b.get("title") or "").replace("|", r"\|")
        row_list.append(f"| `{fn}` | #{b['id']} | {safe_title} |")
    rows = "\n".join(row_list) or "| _(no bots yet)_ | | |"
    first_fn = names[int(bots[0]["id"])] if bots else "myBot"
    return f"""# {app_name} — MiniClosedAI SDK (JavaScript)

A tiny, dependency-free ES-module JavaScript SDK for the bots in the **{app_name}** application.
Generated by MiniClosedAI. It talks to a **running** MiniClosedAI server over HTTP.

## Use it

Copy this `{slug}-sdk/` folder into your project, then:

```js
import {{ {first_fn} }} from "./{slug}-sdk/index.js";

const reply = await {first_fn}("Hello!");
console.log(reply);
```

Streaming:

```js
import {{ {first_fn}Bot }} from "./{slug}-sdk/index.js";

for await (const chunk of {first_fn}Bot.stream("Tell me a story", {{ history: true }})) {{
  process.stdout.write(chunk);
}}
```

## Configuration

The server base URL is baked in as `{base_url}`. Override it without editing code
via the `MINICLOSEDAI_BASE_URL` environment variable (Node), or per call:

```js
await {first_fn}("Hi", {{ baseUrl: "http://localhost:8095" }});
```

Requires Node 18+ (global `fetch`) or a modern browser.

## Bots in this application

| Function | Bot ID | Title |
|----------|--------|-------|
{rows}
"""


def _package_json_js(app: dict, slug: str) -> str:
    name = app.get("name") or "Application"
    desc = (name + " — generated MiniClosedAI SDK (JS)").replace('"', "'")
    return (
        "{\n"
        f'  "name": "{slug}-sdk",\n'
        '  "version": "0.0.0",\n'
        '  "private": true,\n'
        '  "type": "module",\n'
        f'  "description": "{desc}",\n'
        '  "main": "index.js"\n'
        "}\n"
    )


def generate_js_sdk(app: dict, bots: list[dict], base_url: str) -> list[dict]:
    """Build the JavaScript (ESM) SDK files for one application. Same shape as
    the TS SDK; types stripped so it runs in plain Node 18+ / browser."""
    slug = slugify(app.get("name") or "app")
    root = f"{slug}-sdk"
    names = function_names(bots)

    files: list[dict] = []
    files.append({"path": f"{root}/client.js", "content": _CLIENT_JS.replace("__BASE_URL__", base_url)})
    for b in bots:
        fn = names[int(b["id"])]
        files.append({"path": f"{root}/bots/{fn}.js", "content": _bot_file_js(b, fn)})
    files.append({"path": f"{root}/index.js", "content": _index_js(app, bots, names)})
    files.append({"path": f"{root}/README.md", "content": _readme_md_js(app, bots, names, slug, base_url)})
    files.append({"path": f"{root}/package.json", "content": _package_json_js(app, slug)})
    return files


# =====================================================================
# Python SDK — a stdlib-only package mirroring the TS shape. Folder
# uses underscores (Python packages can't have hyphens), and function
# names are snake_case (Python convention).
# =====================================================================

_PY_RESERVED = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
    "Bot", "DEFAULT_BASE_URL", "MiniClosedAIError",
}


def _snake(name: str) -> str:
    """A snake_case Python identifier derived from a (possibly messy) bot title."""
    parts = re.split(r"[^a-zA-Z0-9]+", name or "")
    parts = [p for p in parts if p]
    if not parts:
        return ""
    out: list[str] = []
    for p in parts:
        # CamelCase → snake: split on lower→Upper boundaries inside each part.
        for seg in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", p):
            if seg:
                out.append(seg.lower())
    ident = "_".join(out)
    if ident and ident[0].isdigit():
        ident = "bot_" + ident
    return ident


def function_names_python(bots: list[dict]) -> dict[int, str]:
    """Map each bot id → a unique, valid snake_case Python identifier."""
    seen: set[str] = set()
    out: dict[int, str] = {}
    for b in bots:
        bid = int(b["id"])
        base = _snake(b.get("title") or "")
        if not base or base in _PY_RESERVED:
            base = f"bot_{bid}"
        name = base
        if name in seen:
            name = f"{base}_{bid}"
        seen.add(name)
        out[bid] = name
    return out


def py_slug(name: str, fallback: str = "app") -> str:
    """Python-package-safe slug: lowercase, alphanumerics + single underscores."""
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    if s and s[0].isdigit():
        s = "_" + s
    return s or fallback


_CLIENT_PY = '''\
"""client.py — a tiny, dependency-free client for MiniClosedAI bots.

Ported from docs/examples/client/miniclosedai_client.py. Stdlib only
(urllib + json). Each saved MiniClosedAI bot is a callable "expert"; this
wraps the HTTP API so you can compose a fleet of them in your own
orchestration code.

Point at your instance with the MINICLOSEDAI_BASE_URL env var, or pass
base_url=... explicitly. The default below was baked in at generation time.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = os.environ.get("MINICLOSEDAI_BASE_URL", "__BASE_URL__")


class MiniClosedAIError(RuntimeError):
    """Raised on a non-2xx response or an unreachable server."""


# Optional bearer for MiniClosedAI installs with authentication enabled
# (Settings -> Security). Falls back to the MINICLOSEDAI_API_KEY env var.
# Unset = requests go without auth; the server allows them in grace mode.
API_KEY = os.environ.get("MINICLOSEDAI_API_KEY") or None


def set_api_key(key):
    global API_KEY
    API_KEY = key


def _headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def _request(method, url, payload=None, timeout=300.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers=_headers()
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

    def __init__(self, conv_id, base_url=DEFAULT_BASE_URL):
        self.id = conv_id
        self.base_url = base_url.rstrip("/")

    def __repr__(self):
        return f"<Bot #{self.id} @ {self.base_url}>"

    @classmethod
    def list(cls, base_url=DEFAULT_BASE_URL):
        """Every saved bot on the server."""
        return _request("GET", f"{base_url.rstrip('/')}/api/conversations")

    @classmethod
    def find(cls, title_contains, base_url=DEFAULT_BASE_URL):
        """Return the first bot whose title contains `title_contains` (case-insensitive)."""
        needle = title_contains.lower()
        for c in cls.list(base_url):
            if needle in (c.get("title") or "").lower():
                return cls(c["id"], base_url)
        raise MiniClosedAIError(f"No bot whose title contains {title_contains!r}")

    def ask(self, message, history=True, persist=False):
        """Send a message; return the assistant's reply text."""
        out = _request(
            "POST",
            f"{self.base_url}/api/conversations/{self.id}/chat",
            {"message": message, "include_history": history, "persist": persist},
        )
        return out.get("response", "")

    def stream(self, message, history=True, persist=False):
        """Yield reply text chunks as they stream in (SSE)."""
        payload = json.dumps(
            {"message": message, "include_history": history, "persist": persist}
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/conversations/{self.id}/chat/stream",
            data=payload, method="POST", headers=_headers(),
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:
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
'''


def _bot_file_py(bot: dict, fn: str) -> str:
    bid = int(bot["id"])
    title = bot.get("title") or f"Bot #{bid}"
    model = bot.get("model") or ""
    docs_title = title.replace('"""', "'''")
    docs_model = (model or "").replace('"""', "'''")
    return (
        f'"""{docs_title} — bot #{bid}' + (f" (model: {docs_model})" if model else "") + '"""\n'
        "from ..client import Bot\n"
        "\n"
        f"{fn}_bot = Bot({bid})\n"
        "\n"
        "\n"
        f"def {fn}(message, history=True, persist=False):\n"
        f'    """Ask "{docs_title}" (bot #{bid}). Pass history=False for a one-shot call."""\n'
        f"    return {fn}_bot.ask(message, history=history, persist=persist)\n"
    )


def _init_py(app: dict, bots: list[dict], names: dict[int, str]) -> str:
    app_name = app.get("name") or "Application"
    bag = py_slug(app_name, "app")
    if bag in _PY_RESERVED:
        bag = "app"
    safe_name = app_name.replace('"""', "'''")
    head = [f'"""MiniClosedAI SDK for application: {safe_name}']
    if app.get("link"):
        head.append("")
        head.append(app["link"].replace('"""', "'''"))
    if app.get("description"):
        head.append("")
        head.append(app["description"].replace('"""', "'''"))
    head.append("")
    head.append("Generated by MiniClosedAI. Requires a running MiniClosedAI server.")
    head.append('"""')

    body: list[str] = []
    body.append("from .client import Bot, MiniClosedAIError, DEFAULT_BASE_URL")
    body.append("")
    for b in bots:
        fn = names[int(b["id"])]
        body.append(f"from .bots.{fn} import {fn}, {fn}_bot")
    body.append("")
    if bots:
        body.append(f"# All bots in {safe_name!r}, keyed by function name.")
        body.append(f"{bag} = {{")
        for b in bots:
            fn = names[int(b["id"])]
            body.append(f'    "{fn}": {fn},')
        body.append("}")
    else:
        body.append("# (This application has no bots yet — add some in the MiniClosedAI GUI.)")
    body.append("")
    return "\n".join(head + [""] + body)


def _readme_md_py(app: dict, bots: list[dict], names: dict[int, str], slug_py: str, base_url: str) -> str:
    app_name = app.get("name") or "Application"
    row_list = []
    for b in bots:
        fn = names[int(b["id"])]
        safe_title = (b.get("title") or "").replace("|", r"\|")
        row_list.append(f"| `{fn}` | #{b['id']} | {safe_title} |")
    rows = "\n".join(row_list) or "| _(no bots yet)_ | | |"
    first_fn = names[int(bots[0]["id"])] if bots else "my_bot"
    return f"""# {app_name} — MiniClosedAI SDK (Python)

A tiny, dependency-free Python SDK for the bots in the **{app_name}** application.
Stdlib only (urllib + json). Generated by MiniClosedAI. Talks to a **running**
MiniClosedAI server over HTTP.

## Use it

Place the `{slug_py}_sdk/` package inside your Python project (or anywhere on
`sys.path`), then:

```python
from {slug_py}_sdk import {first_fn}

reply = {first_fn}("Hello!")
print(reply)
```

Streaming:

```python
from {slug_py}_sdk import {first_fn}_bot

for chunk in {first_fn}_bot.stream("Tell me a story", history=True):
    print(chunk, end="", flush=True)
```

## Configuration

The server base URL is baked in as `{base_url}`. Override it without editing
code via the `MINICLOSEDAI_BASE_URL` env var, or pass `base_url=...` when
constructing a fresh `Bot(id)`.

## Bots in this application

| Function | Bot ID | Title |
|----------|--------|-------|
{rows}
"""


def generate_python_sdk(app: dict, bots: list[dict], base_url: str) -> list[dict]:
    """Build the Python SDK files for one application — a stdlib-only package.

    The folder is `<py_slug>_sdk/` (underscores) so it's directly importable.
    Function names are snake_case via `function_names_python`.
    """
    slug_py = py_slug(app.get("name") or "app")
    root = f"{slug_py}_sdk"
    names = function_names_python(bots)

    files: list[dict] = []
    files.append({"path": f"{root}/client.py", "content": _CLIENT_PY.replace("__BASE_URL__", base_url)})
    files.append({"path": f"{root}/__init__.py", "content": _init_py(app, bots, names)})
    files.append({"path": f"{root}/bots/__init__.py",
                  "content": '"""Per-bot modules — re-exported from the parent package."""\n'})
    for b in bots:
        fn = names[int(b["id"])]
        files.append({"path": f"{root}/bots/{fn}.py", "content": _bot_file_py(b, fn)})
    files.append({"path": f"{root}/README.md", "content": _readme_md_py(app, bots, names, slug_py, base_url)})
    return files


# =====================================================================
# Dispatch
# =====================================================================

SDK_LANGS = ("ts", "js", "py")


def generate_sdk(lang: str, app: dict, bots: list[dict], base_url: str) -> list[dict]:
    """Dispatch to the per-language SDK generator. `lang` ∈ SDK_LANGS."""
    if lang == "ts":
        return generate_ts_sdk(app, bots, base_url)
    if lang == "js":
        return generate_js_sdk(app, bots, base_url)
    if lang == "py":
        return generate_python_sdk(app, bots, base_url)
    raise ValueError(f"unknown SDK language: {lang!r}")
