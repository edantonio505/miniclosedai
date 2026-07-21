#!/usr/bin/env python3
"""mcai — terminal client for MiniClosedAI.

Everything the web dashboard does, from the shell: manage backends, create and
edit bots, chat with a saved bot, upload knowledge, wire up MCP extensions, run
evals, group bots into apps + generate their SDK, tail logs, import/export bots,
run HuggingFace models on the miniclosedai-llm manager (`llm` group), and manage
TTS voices on any connected miniclosedai-voice service (`voice` group). It's a
thin HTTP client over the same `/api` endpoints the GUI uses (the `llm`/`voice`
groups go through the same-origin `/api/llm/*` and `/api/voicestudio/*` proxies
the Models and Voice Studio tabs use), so the CLI and browser stay in live sync.

Dependency-free: standard library only (argparse + urllib + json + ssl) — runs
under any python3, no venv required. Talks to the server at $MINICLOSEDAI_URL
(default https://localhost:$MINICLOSEDAI_PORT, 8095). MiniClosedAI serves a
self-signed dev cert, so TLS verification is OFF by default for localhost; set
MINICLOSEDAI_VERIFY=1 to enforce it. Sends Authorization: Bearer
$MINICLOSEDAI_API_KEY when that env var is set (no auth is required locally).

Run `mcai <command> -h` for per-command help. Common commands:
    mcai status | models | bots ls | backend ls
    mcai bots create --title "FAQ" --backend 1 --model llama3.1 --system "..."
    mcai send <bot> "your prompt"          mcai chat <bot>
    mcai url <bot>                         mcai logs
    mcai kb add <bot> notes.md             mcai eval run <bot> --mode contains
    mcai apps sdk <app> --lang ts --out ./sdk
    mcai llm ls | run <hf_id> --wait | test <id> "prompt" | register <id>
    mcai voice ls | speak "hi" --out hi.wav | clone sample.wav --name X
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXIT_OK, EXIT_ERR, EXIT_UNREACHABLE = 0, 1, 2


# --------------------------------------------------------------------- config
def _load_dotenv() -> dict:
    env = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_DOTENV = _load_dotenv()


def cfg(name: str, default: str = "") -> str:
    return os.environ.get(name) or _DOTENV.get(name) or default


def base_url() -> str:
    url = cfg("MINICLOSEDAI_URL")
    if url:
        return url.rstrip("/")
    return f"https://localhost:{cfg('MINICLOSEDAI_PORT', '8095')}"


def _ssl_ctx():
    """MiniClosedAI's dev server uses a self-signed cert; skip verification for
    localhost/dev unless MINICLOSEDAI_VERIFY=1 is set."""
    if cfg("MINICLOSEDAI_VERIFY") in ("1", "true", "yes"):
        return None  # urllib uses the default verifying context
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _headers(extra: dict | None = None) -> dict:
    h = {"Accept": "application/json"}
    key = cfg("MINICLOSEDAI_API_KEY")
    if key:
        h["Authorization"] = f"Bearer {key}"
    if extra:
        h.update(extra)
    return h


# --------------------------------------------------------------------- ANSI
_TTY = sys.stdout.isatty()


def c(text, color):
    if not _TTY:
        return text
    codes = {"dim": "2", "red": "31", "green": "32", "yellow": "33",
             "blue": "34", "cyan": "36", "bold": "1", "magenta": "35"}
    return f"\033[{codes[color]}m{text}\033[0m"


# --------------------------------------------------------------------- HTTP
class ApiError(Exception):
    def __init__(self, status, detail):
        self.status = status
        self.detail = detail
        msg = detail.get("message") if isinstance(detail, dict) else detail
        super().__init__(msg if isinstance(msg, str) else json.dumps(msg))


class Unreachable(Exception):
    pass


def _request(method, path, *, data=None, headers=None, timeout=60):
    url = path if path.startswith("http") else base_url() + path
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=_headers(headers))
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except (ValueError, AttributeError):
            detail = body
        raise ApiError(e.code, detail)
    except (urllib.error.URLError, ConnectionError, socket.timeout, OSError) as e:
        raise Unreachable(str(e))


def api_get(path, timeout=30):
    with _request("GET", path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def api_post(path, obj=None, timeout=300):
    data = json.dumps(obj or {}).encode()
    with _request("POST", path, data=data,
                  headers={"Content-Type": "application/json"}, timeout=timeout) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def api_patch(path, obj=None, timeout=60):
    data = json.dumps(obj or {}).encode()
    with _request("PATCH", path, data=data,
                  headers={"Content-Type": "application/json"}, timeout=timeout) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def api_delete(path, timeout=60):
    with _request("DELETE", path, timeout=timeout) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def download(path, timeout=120) -> bytes:
    with _request("GET", path, timeout=timeout) as r:
        return r.read()


def api_multipart(path, files, timeout=300):
    """POST a multipart/form-data body. `files` maps field → (filename, bytes, ctype)."""
    boundary = "----mcai" + str(int(time.time() * 1000))
    parts = []
    for k, (fn, content, ctype) in files.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    with _request("POST", path, data=body,
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                  timeout=timeout) as r:
        return json.loads(r.read().decode())


# --------------------------------------------------------------------- helpers
def die(msg, code=EXIT_ERR):
    print(c("error:", "red") + " " + msg, file=sys.stderr)
    sys.exit(code)


def require_daemon():
    """Friendly check that the server is up; exits 2 if not."""
    try:
        return api_get("/api/backends", timeout=8)
    except Unreachable:
        die(f"MiniClosedAI not running at {base_url()} — start it:  ./dev.sh up",
            EXIT_UNREACHABLE)
    except ApiError as e:
        if e.status in (401, 403):
            die("unauthorized — set MINICLOSEDAI_API_KEY to match the server.", EXIT_UNREACHABLE)
        raise


def resolve_bot(key: str) -> int:
    """Resolve a bot reference to a conversation id. Accepts an exact id or a
    forgiving title substring."""
    convs = api_get("/api/conversations")
    if str(key).isdigit() and any(str(b["id"]) == str(key) for b in convs):
        return int(key)
    matches = [b for b in convs if key.lower() in (b.get("title") or "").lower()]
    if len(matches) == 1:
        return int(matches[0]["id"])
    if not convs:
        die("no bots yet — create one:  mcai bots create --title ... --model ... --backend 1")
    if not matches:
        die(f"'{key}' didn't match any bot. List them:  mcai bots ls")
    die(f"'{key}' matched {len(matches)} bots: "
        + ", ".join(f"{b['id']}:{b['title']}" for b in matches))


def resolve_app(key: str) -> int:
    apps = api_get("/api/apps")
    if str(key).isdigit() and any(str(a["id"]) == str(key) for a in apps):
        return int(key)
    matches = [a for a in apps if key.lower() in (a.get("name") or "").lower()]
    if len(matches) == 1:
        return int(matches[0]["id"])
    if not matches:
        die(f"'{key}' didn't match any app. List them:  mcai apps ls")
    die(f"'{key}' matched {len(matches)} apps: "
        + ", ".join(f"{a['id']}:{a['name']}" for a in matches))


def resolve_voice_backend(key: str | None) -> dict:
    """Resolve --backend to an enabled kind='voice' backend row.

    Unlike vc (always exactly one target service), mcai may have several
    registered voice backends (local + remote). `key` is an id or a forgiving
    name substring; omitted → the first enabled one, with a printed note of
    which was picked so the choice is never silently ambiguous."""
    backends = [b for b in api_get("/api/backends") if b.get("kind") == "voice" and b.get("enabled")]
    if not backends:
        die("no voice backends registered — add one in Settings, or:\n"
            "  mcai backend add --name X --kind voice --url https://host:8090")
    if key is None:
        b = backends[0]
        if len(backends) > 1:
            print(c(f"(using voice backend {b['id']}:{b['name']} — pass --backend to choose another)", "dim"),
                  file=sys.stderr)
        return b
    if str(key).isdigit() and any(str(b["id"]) == str(key) for b in backends):
        return next(b for b in backends if str(b["id"]) == str(key))
    matches = [b for b in backends if key.lower() in (b.get("name") or "").lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        die(f"'{key}' didn't match any voice backend. Candidates: "
            + ", ".join(f"{b['id']}:{b['name']}" for b in backends))
    die(f"'{key}' matched {len(matches)} voice backends: "
        + ", ".join(f"{b['id']}:{b['name']}" for b in matches))


def _llm_resolve_id(key: str) -> str:
    """Forgiving model-id match against the LLM manager: exact → prefix →
    hf_id substring (mirrors `mc`'s resolve_id)."""
    models = api_get("/api/llm/models")["models"]
    ids = [m["id"] for m in models]
    if key in ids:
        return key
    pref = [i for i in ids if i.startswith(key)]
    if len(pref) == 1:
        return pref[0]
    byhf = [m["id"] for m in models if key.lower() in m["hf_id"].lower()]
    if len(byhf) == 1:
        return byhf[0]
    if not models:
        die("no models yet — run one first:  mcai llm run <hf_id>")
    cands = pref or byhf or ids
    die(f"'{key}' didn't match one model. Candidates: {', '.join(cands)}")


def _voice_resolve_id(backend: dict, key: str) -> str:
    """Forgiving voice-id match within one backend's catalog: exact → prefix
    → name substring (mirrors `vc`'s resolve_voice)."""
    cat = api_get(f"/api/voicestudio/{backend['id']}/voices")
    voices = [{"lang": lang, **v} for lang, items in cat.items() for v in items]
    ids = [v["id"] for v in voices]
    if key in ids:
        return key
    pref = sorted({i for i in ids if i.startswith(key)})
    if len(pref) == 1:
        return pref[0]
    byname = sorted({v["id"] for v in voices if key.lower() in v.get("name", "").lower()})
    if len(byname) == 1:
        return byname[0]
    if not voices:
        die(f"no voices on backend {backend['id']}:{backend['name']} — clone one:  "
            f"mcai voice clone <audio> --name NAME --backend {backend['id']}")
    cands = pref or byname or sorted(set(ids))
    die(f"'{key}' didn't match one voice. Candidates: {', '.join(cands)}")


def _table(rows, headers):
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(c(line, "bold"))
    for r in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(r)))


def _kv_list(pairs: list[str] | None) -> dict:
    """Parse repeated `k=v` flags into a dict."""
    out = {}
    for item in pairs or []:
        if "=" not in item:
            die(f"expected key=value, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


_NUM_PARAMS = {"temperature": float, "top_p": float, "top_k": int,
               "max_tokens": int, "max_thinking_tokens": int}


def _parse_params(pairs: list[str] | None) -> dict:
    """Parse --param k=v sampling params, coercing known numeric keys."""
    raw = _kv_list(pairs)
    out = {}
    for k, v in raw.items():
        if k in _NUM_PARAMS:
            try:
                out[k] = _NUM_PARAMS[k](v)
            except ValueError:
                die(f"param {k} must be {_NUM_PARAMS[k].__name__}, got {v!r}")
        elif k == "think":
            out[k] = True if v == "true" else False if v == "false" else v
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------- status / models
def cmd_status(args):
    backends = require_daemon()
    print(f"{c('server', 'dim')}   {c(base_url(), 'cyan')}  {c('online ✓', 'green')}")
    rows = []
    for b in backends:
        if not b.get("enabled"):
            state = c("disabled", "dim")
        else:
            try:
                st = api_get(f"/api/backends/{b['id']}/status", timeout=8)
                state = c("online", "green") if st.get("running") else c("offline", "yellow")
            except ApiError:
                state = c("?", "yellow")
        rows.append([b["id"], b["name"], b["kind"], state, b["base_url"]])
    _table(rows, ["ID", "NAME", "KIND", "STATUS", "BASE_URL"])


def cmd_models(args):
    require_daemon()
    data = api_get("/api/models")
    if args.json:
        print(json.dumps(data, indent=2)); return
    rows = []
    for b in data.get("backends", []):
        for m in b.get("models", []):
            rows.append([b["name"], m.get("name", "?")])
    if not rows:
        print(c("no models available — is a backend online?  mcai status", "dim")); return
    _table(rows, ["BACKEND", "MODEL"])


# --------------------------------------------------------------------- backends
def cmd_backend_ls(args):
    require_daemon()
    backends = api_get("/api/backends")
    if args.json:
        print(json.dumps(backends, indent=2)); return
    rows = [[b["id"], b["name"], b["kind"],
             "yes" if b.get("enabled") else "no",
             "key" if b.get("api_key_set") else "-", b["base_url"]]
            for b in backends]
    _table(rows, ["ID", "NAME", "KIND", "ENABLED", "AUTH", "BASE_URL"])


def cmd_backend_add(args):
    require_daemon()
    body = {"name": args.name, "kind": args.kind, "base_url": args.url,
            "enabled": not args.disabled}
    if args.api_key:
        body["api_key"] = args.api_key
    if args.header:
        body["headers"] = _kv_list(args.header)
    b = api_post("/api/backends", body)
    print(f"added backend {c(str(b['id']), 'bold')}  {b['name']} ({b['kind']}) → {b['base_url']}")


def cmd_backend_edit(args):
    require_daemon()
    body = {}
    if args.name is not None: body["name"] = args.name
    if args.url is not None: body["base_url"] = args.url
    if args.api_key is not None: body["api_key"] = args.api_key
    if args.header: body["headers"] = _kv_list(args.header)
    if args.enable: body["enabled"] = True
    if args.disable: body["enabled"] = False
    if not body:
        die("nothing to change — pass --name/--url/--api-key/--enable/--disable/--header")
    b = api_patch(f"/api/backends/{args.id}", body)
    print(f"updated backend {b['id']}  {b['name']} ({'enabled' if b.get('enabled') else 'disabled'})")


def cmd_backend_rm(args):
    require_daemon()
    path = f"/api/backends/{args.id}" + ("?force=true" if args.force else "")
    try:
        api_delete(path)
    except ApiError as e:
        die(f"{e}\n  (built-in backends or those with bound bots need --force)")
    print(f"removed backend {args.id}")


def cmd_backend_test(args):
    require_daemon()
    body = {"name": args.name or "draft", "kind": args.kind, "base_url": args.url}
    if args.api_key:
        body["api_key"] = args.api_key
    if args.header:
        body["headers"] = _kv_list(args.header)
    r = api_post("/api/backends/test", body)
    ok = r.get("running")
    label = c("reachable ✓", "green") if ok else c("unreachable ✗", "red")
    print(f"{label}  {r.get('message', '')}")
    if not ok:
        sys.exit(EXIT_ERR)


def cmd_backend_status(args):
    require_daemon()
    st = api_get(f"/api/backends/{args.id}/status")
    if args.json:
        print(json.dumps(st, indent=2)); return
    state = c("online", "green") if st.get("running") else c("offline", "yellow")
    print(f"backend {args.id}: {state}  ({st.get('kind')} @ {st.get('base_url')})")


def cmd_backend_models(args):
    require_daemon()
    r = api_get(f"/api/backends/{args.id}/models")
    if args.json:
        print(json.dumps(r, indent=2)); return
    if not r.get("running"):
        print(c("backend offline or disabled", "yellow")); return
    for m in r.get("models", []):
        print(m.get("name", "?"))


def cmd_backend_pull(args):
    require_daemon()
    st = api_post(f"/api/backends/{args.id}/pull", {"name": args.model})
    print(f"pull started: {st.get('name')} on backend {args.id}  ({st.get('status')})")
    print(c("  watch progress:  mcai backend pulls", "dim"))


def cmd_backend_pulls(args):
    require_daemon()
    data = api_get("/api/pulls")
    pulls = data.get("pulls", [])
    if args.json:
        print(json.dumps(data, indent=2)); return
    if not pulls:
        print(c("no pulls", "dim")); return
    rows = []
    for p in pulls:
        total, done = p.get("total") or 0, p.get("completed") or 0
        pct = f"{(done/total*100):.0f}%" if total else "-"
        rows.append([p.get("backend_id"), p.get("name"), p.get("status"), pct])
    _table(rows, ["BACKEND", "MODEL", "STATUS", "PROGRESS"])


def cmd_backend_unpull(args):
    require_daemon()
    api_delete(f"/api/backends/{args.id}/pulls/{args.model}")
    print(f"deleted model {args.model} from backend {args.id}")


def cmd_backend_autoregister(args):
    require_daemon()
    body = {"manager_url": args.manager_url, "model_id": args.model_id}
    if args.name: body["name"] = args.name
    if args.prefer_docker_host: body["prefer_docker_host"] = True
    if args.api_key: body["api_key"] = args.api_key
    try:
        b = api_post("/api/backends/auto-register", body)
    except ApiError as e:
        die(str(e))
    print(f"registered backend {c(str(b['id']), 'bold')}  {b['name']} → {b['base_url']}")
    print(c(f"  use it as a bot model:  {b.get('served_model')}", "dim"))


# --------------------------------------------------------------------- bots
def cmd_bots_ls(args):
    require_daemon()
    convs = api_get("/api/conversations")
    if args.app:
        app_id = resolve_app(args.app)
        convs = [b for b in convs if b.get("app_id") == app_id]
    if args.json:
        print(json.dumps(convs, indent=2)); return
    if not convs:
        print(c("no bots yet — mcai bots create ...", "dim")); return
    rows = [[b["id"], (b.get("title") or "")[:32], b.get("model", ""),
             b.get("backend_id"), b.get("app_id") if b.get("app_id") else "-"]
            for b in convs]
    _table(rows, ["ID", "TITLE", "MODEL", "BACKEND", "APP"])


def cmd_bots_show(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    conv = api_get(f"/api/conversations/{bot_id}")
    if args.json:
        print(json.dumps(conv, indent=2)); return
    print(f"{c('#'+str(conv['id'])+'  '+conv.get('title',''), 'bold')}")
    print(f"{c('model', 'dim')}      {conv.get('model')}   (backend {conv.get('backend_id')})")
    print(f"{c('params', 'dim')}     {json.dumps(conv.get('params') or {})}")
    msgs = conv.get("messages") or []
    print(f"{c('messages', 'dim')}   {len(msgs)} turn(s)")
    sp = (conv.get("system_prompt") or "").strip()
    print(f"{c('system', 'dim')}\n{sp}")


def cmd_bots_create(args):
    require_daemon()
    body = {"title": args.title, "model": args.model, "backend_id": args.backend}
    if args.system_file:
        body["system_prompt"] = Path(args.system_file).read_text()
    elif args.system:
        body["system_prompt"] = args.system
    params = _parse_params(args.param)
    if params:
        body["params"] = params
    b = api_post("/api/conversations", body)
    print(f"created bot {c(str(b['id']), 'bold')}  {b.get('title')}  ({b.get('model')})")
    print(c(f"  chat:  mcai chat {b['id']}    call URL:  mcai url {b['id']}", "dim"))


def cmd_bots_edit(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    body = {}
    if args.title is not None: body["title"] = args.title
    if args.model is not None: body["model"] = args.model
    if args.backend is not None: body["backend_id"] = args.backend
    if args.system_file:
        body["system_prompt"] = Path(args.system_file).read_text()
    elif args.system is not None:
        body["system_prompt"] = args.system
    params = _parse_params(args.param)
    if params:
        body["params"] = params
    if not body:
        die("nothing to change — pass --title/--model/--backend/--system/--param")
    api_patch(f"/api/conversations/{bot_id}", body)
    print(f"updated bot {bot_id}")


def cmd_bots_clone(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    body = {}
    if args.title: body["title"] = args.title
    if args.backend is not None: body["backend_id"] = args.backend
    if args.model: body["model"] = args.model
    params = _parse_params(args.param)
    if params:
        body["params"] = params
    r = api_post(f"/api/conversations/{bot_id}/clone", body)
    print(f"cloned {bot_id} → {c(str(r['id']), 'bold')}  {r.get('title')}")


def cmd_bots_clear(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    api_post(f"/api/conversations/{bot_id}/clear")
    print(f"cleared message history for bot {bot_id}")


def cmd_bots_rm(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    api_delete(f"/api/conversations/{bot_id}")
    print(f"deleted bot {bot_id}")


_EXPORT_KINDS = {
    "config": ("export", "miniclosed-bot.json"),
    "csv": ("export.csv", "csv"),
    "dataset-zip": ("export.zip", "zip"),
    "classify-zip": ("export.classify.zip", "zip"),
}


def cmd_bots_export(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    suffix, ext = _EXPORT_KINDS[args.kind]
    q = "?include_history=true" if (args.kind == "config" and args.with_history) else ""
    blob = download(f"/api/conversations/{bot_id}/{suffix}{q}")
    out = args.out or f"bot-{bot_id}.{ext}"
    Path(out).write_bytes(blob)
    print(f"wrote {c(out, 'cyan')}  ({len(blob)} bytes)")


def cmd_bots_import(args):
    require_daemon()
    data = json.loads(Path(args.file).read_text())
    body = {"data": data}
    if args.backend is not None:
        body["backend_id"] = args.backend
    try:
        r = api_post("/api/conversations/import", body)
    except ApiError as e:
        if e.status == 409:
            d = e.detail if isinstance(e.detail, dict) else {}
            avail = d.get("available_backends") or []
            hint = ", ".join(f"{b.get('id')}:{b.get('name')}" for b in avail) if avail else "mcai backend ls"
            die(f"no backend serves model {d.get('model','?')!r}. "
                f"Retry with --backend <id>. Candidates: {hint}")
        die(str(e))
    print(f"imported bot {c(str(r['id']), 'bold')}  {r.get('title')}  "
          f"(backend {r.get('matched_backend_id')})")


# --------------------------------------------------------------------- chat
def _sse_chat(bot_id, message, show_thinking, timeout=600):
    """Stream a turn via /chat/stream, printing chunks live. Returns the reply."""
    payload = {"message": message, "persist": True, "include_history": True}
    try:
        resp = _request("POST", f"/api/conversations/{bot_id}/chat/stream",
                        data=json.dumps(payload).encode(),
                        headers={"Content-Type": "application/json"}, timeout=timeout)
    except Unreachable as e:
        die(str(e), EXIT_UNREACHABLE)
    acc = ""
    try:
        for raw in resp:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except ValueError:
                continue
            if "chunk" in d:
                acc += d["chunk"]
                sys.stdout.write(d["chunk"]); sys.stdout.flush()
            elif "thinking" in d and show_thinking:
                sys.stdout.write(c(d["thinking"], "dim")); sys.stdout.flush()
            elif "error" in d:
                print(c(f"\n[error: {d['error']}]", "red"))
            elif d.get("end"):
                break
    finally:
        resp.close()
    return acc


def cmd_chat(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    conv = api_get(f"/api/conversations/{bot_id}")
    print(c(f"chatting with #{bot_id} {conv.get('title','')} ({conv.get('model')}). "
            "/reset clears history, /exit quits.", "dim"))
    while True:
        try:
            prompt = input(c("you> ", "cyan"))
        except (EOFError, KeyboardInterrupt):
            print(); break
        prompt = prompt.strip()
        if not prompt:
            continue
        if prompt in ("/exit", "/quit", "/q"):
            break
        if prompt == "/reset":
            api_post(f"/api/conversations/{bot_id}/clear")
            print(c("(history cleared)", "dim")); continue
        sys.stdout.write(c("bot> ", "green")); sys.stdout.flush()
        try:
            _sse_chat(bot_id, prompt, args.show_thinking)
        except KeyboardInterrupt:
            print(c("\n[interrupted]", "yellow")); continue
        print()


def cmd_send(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    ephemeral = args.ephemeral
    body = {"message": args.prompt,
            "persist": not ephemeral,
            "include_history": not ephemeral}
    try:
        r = api_post(f"/api/conversations/{bot_id}/chat", body)
    except ApiError as e:
        die(str(e))
    if args.json:
        print(json.dumps(r, indent=2)); return
    print(r.get("response", "").strip())


# --------------------------------------------------------------------- url / snippets
def cmd_url(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    conv = api_get(f"/api/conversations/{bot_id}")
    bu = base_url()
    native = f"{bu}/api/conversations/{bot_id}/chat"
    oai = f"{bu}/v1/chat/completions"
    print(c(f"# Bot #{bot_id} — {conv.get('title','')} ({conv.get('model')})", "bold"))
    print(f"\n{c('Native endpoint', 'dim')}\n  POST {c(native, 'cyan')}")
    print(f"\n{c('OpenAI-compatible', 'dim')}\n  POST {c(oai, 'cyan')}   (model = \"{bot_id}\")")
    print(c("\n# curl (native)", "dim"))
    print(f"""curl -sk {native} \\
  -H 'Content-Type: application/json' \\
  -d '{{"message": "hello", "include_history": true}}'""")
    print(c("\n# curl (OpenAI-compatible)", "dim"))
    print(f"""curl -sk {oai} \\
  -H 'Content-Type: application/json' \\
  -d '{{"model": "{bot_id}", "messages": [{{"role":"user","content":"hello"}}]}}'""")
    print(c("\n# python (openai SDK)", "dim"))
    print(f"""from openai import OpenAI
client = OpenAI(base_url="{bu}/v1", api_key="x")
r = client.chat.completions.create(
    model="{bot_id}", messages=[{{"role": "user", "content": "hello"}}])
print(r.choices[0].message.content)""")


# --------------------------------------------------------------------- knowledge
def _extract_text(path: Path) -> str:
    """Read a file to plain text. PDFs go through the server's extractor; other
    types are read directly (matches the GUI, which extracts client-side)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        r = api_multipart("/api/extract-pdf?full=true",
                          {"file": (path.name, path.read_bytes(), "application/pdf")})
        return r.get("text", "")
    return path.read_text(errors="replace")


def cmd_kb_ls(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    docs = api_get(f"/api/conversations/{bot_id}/knowledge").get("documents", [])
    if args.json:
        print(json.dumps(docs, indent=2)); return
    if not docs:
        print(c("no documents — mcai kb add <bot> <file>", "dim")); return
    rows = [[d["id"], d["filename"], d.get("chunk_count"), d.get("char_count"),
             d.get("embed_model")] for d in docs]
    _table(rows, ["ID", "FILENAME", "CHUNKS", "CHARS", "EMBED_MODEL"])


def cmd_kb_add(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    p = Path(args.file)
    if not p.exists():
        die(f"file not found: {args.file}")
    text = _extract_text(p)
    if not text.strip():
        die("no extractable text in file")
    try:
        r = api_post(f"/api/conversations/{bot_id}/knowledge",
                     {"filename": p.name, "text": text})
    except ApiError as e:
        die(str(e))
    print(f"added {c(r['filename'], 'bold')}  ({r['chunk_count']} chunks, "
          f"{r['char_count']} chars, embed={r['embed_model']})")


def cmd_kb_rm(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    api_delete(f"/api/conversations/{bot_id}/knowledge/{args.doc_id}")
    print(f"removed document {args.doc_id} from bot {bot_id}")


# --------------------------------------------------------------------- mcp
def api_put(path, obj):
    data = json.dumps(obj).encode()
    with _request("PUT", path, data=data,
                  headers={"Content-Type": "application/json"}) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def _get_mcp_servers(bot_id) -> list:
    return api_get(f"/api/conversations/{bot_id}/mcp").get("servers", []) or []


def _put_mcp_servers(bot_id, servers):
    return api_put(f"/api/conversations/{bot_id}/mcp", {"servers": servers})


def cmd_mcp_ls(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    servers = _get_mcp_servers(bot_id)
    if args.json:
        print(json.dumps(servers, indent=2)); return
    if not servers:
        print(c("no MCP servers — mcai mcp add <bot> --url ...", "dim")); return
    rows = [[s.get("name") or "-", "on" if s.get("enabled", True) else "off", s.get("url")]
            for s in servers]
    _table(rows, ["NAME", "ENABLED", "URL"])


def cmd_mcp_add(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    servers = [s for s in _get_mcp_servers(bot_id) if s.get("url") != args.url]  # replace same url
    servers.append({"name": args.name or "", "url": args.url, "enabled": True})
    _put_mcp_servers(bot_id, servers)
    print(f"added MCP server {args.url} to bot {bot_id}")


def cmd_mcp_rm(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    servers = [s for s in _get_mcp_servers(bot_id) if s.get("url") != args.url]
    _put_mcp_servers(bot_id, servers)
    print(f"removed MCP server {args.url} from bot {bot_id}")


def cmd_mcp_toggle(args, enabled):
    require_daemon()
    bot_id = resolve_bot(args.id)
    servers = _get_mcp_servers(bot_id)
    found = False
    for s in servers:
        if s.get("url") == args.url:
            s["enabled"] = enabled; found = True
    if not found:
        die(f"no MCP server with url {args.url} on bot {bot_id}")
    _put_mcp_servers(bot_id, servers)
    print(f"{'enabled' if enabled else 'disabled'} {args.url} on bot {bot_id}")


def cmd_mcp_test(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    r = api_post(f"/api/conversations/{bot_id}/mcp/test", {"url": args.url})
    if r.get("ok"):
        tools = r.get("tools") or []
        print(c(f"reachable ✓  {len(tools)} tool(s): ", "green") + ", ".join(
            t.get("name", "?") if isinstance(t, dict) else str(t) for t in tools))
    else:
        die(r.get("error") or r.get("message") or "MCP server test failed")


# --------------------------------------------------------------------- evals
def cmd_eval_ls(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    cases = api_get(f"/api/conversations/{bot_id}/eval/cases").get("cases", [])
    if args.json:
        print(json.dumps(cases, indent=2)); return
    if not cases:
        print(c("no eval cases — mcai eval add <bot> --input ... --expected ...", "dim")); return
    rows = [[ca["id"], (ca["input"] or "")[:40], (ca["expected"] or "")[:40]] for ca in cases]
    _table(rows, ["ID", "INPUT", "EXPECTED"])


def cmd_eval_add(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    cases = []
    if args.file:
        text = Path(args.file).read_text()
        if args.file.endswith(".json"):
            loaded = json.loads(text)
            cases = loaded.get("cases", loaded) if isinstance(loaded, dict) else loaded
        else:  # CSV: input,expected
            import csv
            import io as _io
            reader = csv.reader(_io.StringIO(text))
            rows = list(reader)
            start = 1 if rows and rows[0][:2] == ["input", "expected"] else 0
            cases = [{"input": r[0], "expected": r[1]} for r in rows[start:] if len(r) >= 2]
    else:
        if args.input is None or args.expected is None:
            die("pass --input and --expected (or --file cases.csv/json)")
        cases = [{"input": args.input, "expected": args.expected}]
    r = api_post(f"/api/conversations/{bot_id}/eval/cases", {"cases": cases})
    print(f"added {r.get('added')} case(s) to bot {bot_id}")


def cmd_eval_rm(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    api_delete(f"/api/conversations/{bot_id}/eval/cases/{args.case_id}")
    print(f"removed case {args.case_id}")


def cmd_eval_clear(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    api_delete(f"/api/conversations/{bot_id}/eval/cases")
    print(f"cleared all eval cases for bot {bot_id}")


def cmd_eval_seed(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    r = api_post(f"/api/conversations/{bot_id}/eval/seed")
    print(f"seeded {r.get('added')} case(s) from chat history")


def cmd_eval_run(args):
    require_daemon()
    bot_id = resolve_bot(args.id)
    body = {"mode": args.mode}
    if args.mode == "judge":
        if not args.judge_model:
            die("judge mode needs --judge-model (and optionally --judge-backend)")
        body["judge_model"] = args.judge_model
        if args.judge_backend is not None:
            body["judge_backend_id"] = args.judge_backend
    r = api_post(f"/api/conversations/{bot_id}/eval/run", body, timeout=1800)
    if args.json:
        print(json.dumps(r, indent=2)); return
    total, passed = r.get("total", 0), r.get("passed", 0)
    if total == 0:
        print(c("no eval cases to run", "yellow")); return
    for res in r.get("results", []):
        mark = c("PASS", "green") if res["passed"] else c("FAIL", "red")
        print(f"{mark}  in={res['input'][:50]!r}  got={res['got'][:50]!r}")
    acc = r.get("accuracy", 0) * 100
    color = "green" if acc >= 80 else "yellow" if acc >= 50 else "red"
    print(c(f"\n{passed}/{total} passed · {acc:.1f}% ({args.mode})", color))


# --------------------------------------------------------------------- apps
def cmd_apps_ls(args):
    require_daemon()
    apps = api_get("/api/apps")
    if args.json:
        print(json.dumps(apps, indent=2)); return
    if not apps:
        print(c("no apps — mcai apps create --name ...", "dim")); return
    rows = [[a["id"], a["name"], a.get("bot_count", 0), (a.get("description") or "")[:40]]
            for a in apps]
    _table(rows, ["ID", "NAME", "BOTS", "DESCRIPTION"])


def cmd_apps_show(args):
    require_daemon()
    app_id = resolve_app(args.id)
    a = api_get(f"/api/apps/{app_id}")
    if args.json:
        print(json.dumps(a, indent=2)); return
    print(c(f"#{a['id']}  {a['name']}", "bold"))
    if a.get("description"):
        print(a["description"])
    bots = a.get("bots", [])
    rows = [[b["id"], b.get("title"), b.get("model")] for b in bots]
    if rows:
        _table(rows, ["BOT", "TITLE", "MODEL"])
    else:
        print(c("(no bots in this app)", "dim"))


def cmd_apps_create(args):
    require_daemon()
    body = {"name": args.name}
    if args.description: body["description"] = args.description
    if args.link: body["link"] = args.link
    a = api_post("/api/apps", body)
    print(f"created app {c(str(a['id']), 'bold')}  {a['name']}")


def cmd_apps_edit(args):
    require_daemon()
    app_id = resolve_app(args.id)
    body = {}
    if args.name is not None: body["name"] = args.name
    if args.description is not None: body["description"] = args.description
    if args.link is not None: body["link"] = args.link
    if not body:
        die("nothing to change — pass --name/--description/--link")
    api_patch(f"/api/apps/{app_id}", body)
    print(f"updated app {app_id}")


def cmd_apps_rm(args):
    require_daemon()
    app_id = resolve_app(args.id)
    api_delete(f"/api/apps/{app_id}")
    print(f"deleted app {app_id}  (its bots are unlinked, not deleted)")


def cmd_apps_addbot(args):
    require_daemon()
    app_id = resolve_app(args.app)
    bot_id = resolve_bot(args.bot)
    api_post(f"/api/apps/{app_id}/bots", {"conversation_id": bot_id})
    print(f"added bot {bot_id} to app {app_id}")


def cmd_apps_rmbot(args):
    require_daemon()
    app_id = resolve_app(args.app)
    bot_id = resolve_bot(args.bot)
    api_delete(f"/api/apps/{app_id}/bots/{bot_id}")
    print(f"removed bot {bot_id} from app {app_id}")


def cmd_apps_sdk(args):
    require_daemon()
    app_id = resolve_app(args.id)
    if args.zip:
        blob = download(f"/api/apps/{app_id}/sdk.zip?lang={args.lang}")
        out = args.out or f"app-{app_id}-{args.lang}-sdk.zip"
        Path(out).write_bytes(blob)
        print(f"wrote {c(out, 'cyan')}  ({len(blob)} bytes)")
        return
    r = api_get(f"/api/apps/{app_id}/sdk?lang={args.lang}")
    files = r.get("files", [])
    if not args.out:
        for f in files:
            print(c(f"# === {f['path']} ===", "bold"))
            print(f["content"])
        return
    outdir = Path(args.out)
    for f in files:
        dest = outdir / f["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f["content"])
    print(f"wrote {len(files)} file(s) to {c(str(outdir), 'cyan')}")


# --------------------------------------------------------------------- logs
def cmd_logs(args):
    require_daemon()
    if args.sub == "clear":
        api_delete("/api/logs")
        print("cleared logs"); return
    if args.sub == "export":
        blob = download("/api/logs/export")
        out = args.out or "miniclosedai-logs.csv"
        Path(out).write_bytes(blob)
        print(f"wrote {c(out, 'cyan')}  ({len(blob)} bytes)"); return
    data = api_get("/api/logs")
    items = data.get("logs", []) if isinstance(data, dict) else data
    if args.json:
        print(json.dumps(data, indent=2)); return
    if not items:
        print(c("no log entries", "dim")); return
    rows = []
    for e in items[: args.limit]:
        status = e.get("status") or "ok"
        sc = "green" if status == "ok" else "red"
        resp = e.get("response")
        if isinstance(resp, dict):
            raw = resp.get("preview") or resp.get("text") or ""
        else:
            raw = resp or e.get("error") or ""
        preview = (raw if isinstance(raw, str) else json.dumps(raw)).replace("\n", " ")
        rows.append([c(status, sc), e.get("model", "?"),
                     f"{e.get('latency_ms','?')}ms", preview[:50]])
    _table(rows, ["STATUS", "MODEL", "LATENCY", "RESPONSE"])


# --------------------------------------------------------------------- llm (miniclosedai-llm, via /api/llm/* proxy)
# Port of miniclosedai-llm's own `mc` CLI, retargeted at the same-origin
# /api/llm/* proxy (app.py) instead of dialing the manager's :8099 directly —
# so it works identically whether the CLI is run on this box or against a
# remote miniclosedai (which is why the group is named `llm`, not `models`:
# mcai already has a top-level `models` command — the aggregated model list
# across registered backends — which this is not).

_LLM_STATUS_COLOR = {"ready": "green", "error": "red", "stopped": "dim",
                     "pulling": "yellow", "downloading": "yellow", "loading": "yellow"}


def cmd_llm_info(args):
    require_daemon()
    try:
        h = api_get("/api/llm/health")
    except ApiError as e:
        die(str(e))
    eng = h.get("engine")
    print(f"{c('engine', 'dim')}     {eng}  ({'GPU ok' if h.get('gpu_ok') else c('no GPU', 'yellow')})")
    if h.get("dashboard_url"):
        print(f"{c('dashboard', 'dim')}  {h.get('dashboard_url')}")
    if h.get("hf_home"):
        print(f"{c('hf_home', 'dim')}    {h.get('hf_home')}")
    gg = c("ready", "green") if h.get("llamacpp_ok") else c("run ./setup_llamacpp.sh", "yellow")
    print(f"{c('gguf', 'dim')}       llama.cpp (ternary/GGUF): {gg}")
    if h.get("no_engine"):
        print(c("  no launch engine available — install Docker or `pip install vllm`", "red"))
    try:
        g = api_get("/api/llm/gpu")
        for gpu in g.get("gpus", []):
            mem = "unified memory" if gpu["mem_total_mb"] is None else f"{gpu['mem_used_mb']}/{gpu['mem_total_mb']} MB"
            print(f"{c('gpu', 'dim')}        GPU{gpu['index']} {gpu['name']} — {mem} ({gpu['util_pct']}%)")
        if g.get("error"):
            print(f"{c('gpu', 'dim')}        {c(g['error'], 'yellow')}")
    except ApiError:
        pass


def cmd_llm_gpu(args):
    require_daemon()
    g = api_get("/api/llm/gpu")
    if args.json:
        print(json.dumps(g, indent=2)); return
    if not g.get("gpus"):
        print(c("no GPU: " + (g.get("error") or "not detected"), "yellow")); return
    for gpu in g["gpus"]:
        mem = "unified" if gpu["mem_total_mb"] is None else f"{gpu['mem_used_mb']}/{gpu['mem_total_mb']} MB"
        print(f"GPU{gpu['index']}  {gpu['name']}  {mem}  util {gpu['util_pct']}%")


def cmd_llm_ls(args):
    require_daemon()
    models = api_get("/api/llm/models")["models"]
    if args.json:
        print(json.dumps(models, indent=2)); return
    if not models:
        print(c("no models — run one:  mcai llm run <hf_id>", "dim")); return
    rows = []
    for m in sorted(models, key=lambda x: (x["source"] != "custom", x["id"])):
        st = c(m["status"], _LLM_STATUS_COLOR.get(m["status"], "dim"))
        kind = "gguf" if m.get("fmt") == "gguf" else ("vision" if m.get("multimodal") else "text")
        rows.append([m["id"], st, f":{m['port']}", kind, m["hf_id"]])
    _table(rows, ["NAME", "STATUS", "PORT", "KIND", "HF_ID"])


def cmd_llm_analyze(args):
    require_daemon()
    a = api_post("/api/llm/analyze", {"hf_id": args.hf_id})
    if args.json:
        print(json.dumps(a, indent=2)); return
    if not a.get("exists"):
        die(a.get("error", "not found"))
    typ = "vision+text" if a["multimodal"] else "text"
    print(f"{c(a['hf_id'], 'bold')}  ({typ})")
    if a.get("fmt") == "gguf":
        print(f"  format     GGUF → llama.cpp" + (f"  ·  {a['gguf_file']}" if a.get("gguf_file") else ""))
    if a.get("params"):
        print(f"  params     {a['params']/1e9:.1f} B" + (f" · {a['dtype']}" if a.get('dtype') else ""))
    if a.get("size_gb") is not None:
        print(f"  weights    ~{a['size_gb']} GB")
    if a.get("need_gb") is not None:
        print(f"  needs      ~{a['need_gb']} GB")
    print(f"  available  {a['available_gb']} GB / {a['total_gb']} GB total")
    if a.get("gated"):
        print("  gated      " + ("yes (HF_TOKEN set)" if a["hf_token_present"]
                                  else c("yes — set HF_TOKEN on the manager", "yellow")))
    verdict = c("fits ✓", "green") if a.get("fits") else c("may not fit ⚠", "yellow")
    print(f"  verdict    {verdict}")


def _llm_run_params(args) -> dict:
    p = {}
    if args.max_len is not None: p["max_model_len"] = args.max_len
    if args.gpu_mem is not None: p["gpu_memory_util"] = args.gpu_mem
    if args.tp is not None: p["tensor_parallel"] = args.tp
    if args.max_images is not None: p["max_images"] = args.max_images
    if args.quant: p["quantization"] = args.quant
    if args.trust_remote_code: p["trust_remote_code"] = True
    if getattr(args, "gguf_file", None): p["gguf_file"] = args.gguf_file
    return p


def cmd_llm_run(args):
    require_daemon()
    body = {"hf_id": args.hf_id, "run": True, "force": args.force}
    if args.name: body["served_name"] = args.name
    if args.port: body["port"] = args.port
    p = _llm_run_params(args)
    if p: body["params"] = p
    try:
        m = api_post("/api/llm/models", body)
    except ApiError as e:
        if e.status == 409:
            msg = e.detail.get("message") if isinstance(e.detail, dict) else e.detail
            die(f"{msg}\n  re-run with --force to launch anyway.")
        die(str(e))
    print(f"launching {c(m['served_name'], 'bold')} on :{m['port']}  "
          f"({'vision' if m.get('multimodal') else 'text'}, {m.get('size_gb', '?')} GB)")
    if not args.wait:
        print(c(f"  watch:  mcai llm logs {m['id']} -f", "dim"))
        return
    _llm_wait_ready(m["id"], args.timeout)


def _llm_wait_ready(mid, timeout):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        st = api_get(f"/api/llm/models/{mid}/status")
        s = st["status"]
        if s != last:
            print(f"  [{int(time.time()-start):4d}s] {c(s, _LLM_STATUS_COLOR.get(s, 'dim'))}")
            last = s
        if st.get("ready"):
            print(c(f"ready — try:  mcai llm test {mid} \"hello\"", "green"))
            return
        if s == "error":
            die("failed to start:\n" + (st.get("detail") or "")[-800:])
        time.sleep(3)
    die(f"timed out after {timeout}s (last: {last})")


def cmd_llm_start(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    try:
        m = api_post(f"/api/llm/models/{mid}/start")
    except ApiError as e:
        die(str(e))
    print(f"starting {c(mid, 'bold')} on :{m['port']}")
    if args.wait:
        _llm_wait_ready(mid, args.timeout)
    else:
        print(c(f"  watch:  mcai llm logs {mid} -f", "dim"))


def cmd_llm_stop(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    api_post(f"/api/llm/models/{mid}/stop")
    print(f"stopped {mid}")


def cmd_llm_rm(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    api_delete(f"/api/llm/models/{mid}")
    print(f"removed {mid}  (weights kept; free them with: mcai llm free <hf_id>)")


def cmd_llm_status(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    st = api_get(f"/api/llm/models/{mid}/status")
    if args.json:
        print(json.dumps(st, indent=2)); return
    print(f"{mid}: {c(st['status'], _LLM_STATUS_COLOR.get(st['status'], 'dim'))}"
          + (f"  ({st['detail']})" if st.get("detail") else ""))


def cmd_llm_logs(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    # SSE stream through the proxy — same raw-line-reader `mc` uses, since the
    # proxy re-yields the manager's chunks untouched (framing survives intact).
    read_timeout = None if args.follow else 5.0
    deadline = None if args.follow else time.time() + 6.0
    try:
        resp = _request("GET", f"/api/llm/models/{mid}/logs", timeout=read_timeout)
    except Unreachable as e:
        die(str(e), EXIT_UNREACHABLE)
    try:
        for raw in resp:
            if deadline and time.time() > deadline:
                break
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except ValueError:
                continue
            if "line" in d:
                print(d["line"])
            elif d.get("eof"):
                break
    except (socket.timeout, TimeoutError):
        pass
    except KeyboardInterrupt:
        pass
    finally:
        resp.close()


def cmd_llm_test(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    fields = {"prompt": args.prompt, "max_tokens": str(args.max_tokens)}
    files = {}
    if args.image:
        p = Path(args.image)
        if not p.exists():
            die(f"image not found: {args.image}")
        files["image"] = (p.name, p.read_bytes(), "image/png")
    try:
        r = _llm_multipart(f"/api/llm/models/{mid}/test", fields, files)
    except ApiError as e:
        die(str(e))
    print(r.get("answer", "").strip())
    u = r.get("usage") or {}
    print(c(f"\n[{r.get('latency_ms')} ms"
            + (f" · {u.get('total_tokens')} tok" if u.get('total_tokens') else "") + "]", "dim"))


def _llm_multipart(path, fields, files, timeout=300):
    """Like `api_multipart`, but also carries text fields (mcai's own
    `api_multipart` is files-only — the manager's /test endpoint takes both)."""
    boundary = "----mcai" + str(int(time.time() * 1000))
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, content, ctype) in files.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    with _request("POST", path, data=body,
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                  timeout=timeout) as r:
        return json.loads(r.read().decode())


def cmd_llm_url(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    m = next(x for x in api_get("/api/llm/models")["models"] if x["id"] == mid)
    print(f"Kind:     openai")
    print(f"Base URL: {c(m['base_url'], 'cyan')}")
    if m.get("alt_base_url"):
        print(c(f"(same-host Docker miniclosedai? use {m['alt_base_url']})", "dim"))
    print(c(f"register it here:  mcai llm register {mid}", "dim"))


def cmd_llm_register(args):
    require_daemon()
    mid = _llm_resolve_id(args.id)
    try:
        info = api_get("/api/llm-info")
    except ApiError as e:
        die(str(e))
    if not info.get("reachable"):
        die(f"model manager at {info.get('manager_url')} is not reachable")
    body = {"manager_url": info["manager_url"], "model_id": mid}
    if args.name: body["name"] = args.name
    if args.prefer_docker_host: body["prefer_docker_host"] = True
    try:
        b = api_post("/api/backends/auto-register", body)
    except ApiError as e:
        die(str(e))
    print(f"registered backend {c(str(b['id']), 'bold')}  {b['name']} → {b['base_url']}")
    print(c(f"  use it as a bot's model:  {b.get('served_model')}", "dim"))


def cmd_llm_cache(args):
    require_daemon()
    if args.sub == "rm":
        api_post("/api/llm/cache/delete", {"hf_id": args.hf_id})
        print(f"freed {args.hf_id} from cache"); return
    d = api_get("/api/llm/cache")
    if args.json:
        print(json.dumps(d, indent=2)); return
    models = d.get("models", [])
    if not models:
        print(c("no downloaded LLMs in the cache yet.", "dim")); return
    rows = [[m["hf_id"], f"{m['size_gb']} GB", "vision" if m["multimodal"] else "text"]
            for m in sorted(models, key=lambda x: -x["size_gb"])]
    _table(rows, ["HF_ID", "SIZE", "KIND"])
    print(c(f"\n{len(models)} models · {d.get('total_gb')} GB", "dim"))
    print(c("run one (loads from disk, no re-download):  mcai llm run <hf_id>", "dim"))


def cmd_llm_free(args):
    require_daemon()
    try:
        api_post("/api/llm/cache/delete", {"hf_id": args.hf_id})
    except ApiError as e:
        die(str(e))
    print(f"freed {args.hf_id} from cache")


# --------------------------------------------------------------------- voice (miniclosedai-voice, via /api/voicestudio/{backend}/* proxy)
# Port of miniclosedai-voice's own `vc` CLI. Unlike `vc` (always exactly one
# target service), mcai may have several registered voice backends — every
# command takes an optional --backend (id or name substring); omitted picks
# the first enabled one (see resolve_voice_backend).

def _voice_get(backend, path, timeout=30):
    with _request("GET", f"/api/voicestudio/{backend['id']}/{path}", timeout=timeout) as r:
        return json.loads(r.read().decode())


def _voice_post_json(backend, path, obj, timeout=120):
    data = json.dumps(obj).encode()
    with _request("POST", f"/api/voicestudio/{backend['id']}/{path}", data=data,
                  headers={"Content-Type": "application/json"}, timeout=timeout) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def _voice_post_binary(backend, path, obj, timeout=300) -> bytes:
    data = json.dumps(obj).encode()
    with _request("POST", f"/api/voicestudio/{backend['id']}/{path}", data=data,
                  headers={"Content-Type": "application/json"}, timeout=timeout) as r:
        return r.read()


def _voice_post_sse(backend, path, obj, timeout=300):
    data = json.dumps(obj).encode()
    with _request("POST", f"/api/voicestudio/{backend['id']}/{path}", data=data,
                  headers={"Content-Type": "application/json",
                           "Accept": "text/event-stream"}, timeout=timeout) as r:
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            try:
                yield json.loads(payload)
            except ValueError:
                continue


def _voice_multipart(backend, path, fields, files, timeout=300):
    boundary = "----mcai" + str(int(time.time() * 1000))
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, content, ctype) in files.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    with _request("POST", f"/api/voicestudio/{backend['id']}/{path}", data=body,
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                  timeout=timeout) as r:
        out = r.read().decode()
        return json.loads(out) if out else None


_AUDIO_CTYPES = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".mp4": "audio/mp4", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".flac": "audio/flac", ".webm": "audio/webm",
}


def _audio_ctype(p: Path) -> str:
    return _AUDIO_CTYPES.get(p.suffix.lower(), "application/octet-stream")


def _voice_play(path: str):
    """Play a WAV through the first available system player. A no-op (with a
    hint) when none is installed — never an error, so headless use is fine."""
    for tool, argv in (("ffplay", [path]), ("paplay", [path]),
                       ("aplay", [path]), ("afplay", [path])):
        exe = shutil.which(tool)
        if not exe:
            continue
        args = [exe]
        if tool == "ffplay":
            args += ["-nodisp", "-autoexit", "-loglevel", "quiet"]
        args += argv
        try:
            subprocess.run(args, check=False)
        except Exception as e:
            print(c(f"(playback via {tool} failed: {e})", "dim"))
        return
    print(c("(no audio player found — install ffmpeg/alsa to use --play)", "dim"))


def cmd_voice_status(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    try:
        h = _voice_get(b, "health")
    except ApiError as e:
        die(str(e))
    count = 0
    try:
        cat = _voice_get(b, "voices")
        count = len({v["id"] for items in cat.values() for v in items})
    except ApiError:
        pass
    if args.json:
        print(json.dumps({"backend": {"id": b["id"], "name": b["name"]}, "health": h, "voice_count": count}, indent=2))
        return
    ok = h.get("ok")
    print(f"{c('backend', 'dim')}    {b['id']}:{b['name']}  {c(b['base_url'], 'cyan')}")
    print(f"{c('status', 'dim')}     {c('ready', 'green') if ok else c('degraded', 'yellow')}")
    print(f"{c('asr', 'dim')}        {h.get('asr_model')}")
    print(f"{c('tts', 'dim')}        {h.get('tts_model')}")
    print(f"{c('device', 'dim')}     {h.get('device')}  (voices_loaded={h.get('voices_loaded')})")
    print(f"{c('voices', 'dim')}     {count}")


def cmd_voice_url(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    try:
        info = _voice_get(b, "api/connect-info")
    except ApiError as e:
        die(str(e))
    print(f"Kind:     {info.get('kind', 'voice')}")
    print(f"Base URL: {c(info['base_url'], 'cyan')}")
    if info.get("alt_base_url"):
        print(c(f"(same-host Docker miniclosedai? use {info['alt_base_url']})", "dim"))
    if info.get("auth_required"):
        print(c("(auth on for this voice service — set its API key in Settings)", "dim"))


def cmd_voice_ls(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    cat = _voice_get(b, "voices")
    if args.json:
        print(json.dumps(cat, indent=2)); return
    rows = []
    for lang in sorted(cat):
        for v in cat[lang]:
            rows.append([lang, v["id"], v.get("name", ""), v.get("gender", "") or ""])
    if not rows:
        print(c("no voices yet — clone one:  mcai voice clone <audio> --name NAME", "dim")); return
    _table(rows, ["LANG", "ID", "NAME", "GENDER"])


def cmd_voice_clone(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    p = Path(args.audio)
    if not p.exists():
        die(f"file not found: {args.audio}")
    ctype = "audio/wav" if p.suffix.lower() == ".wav" else _audio_ctype(p)
    if not ctype.startswith("audio/wav"):
        print(c(f"note: the service accepts WAV for cloning; sending {p.name} "
                f"as {ctype} may be rejected (convert with ffmpeg first).", "yellow"))
    try:
        out = _voice_multipart(b, "voices", {"name": args.name, "language": args.language},
                               {"audio": (p.name, p.read_bytes(), ctype)})
    except ApiError as e:
        die(str(e))
    print(f"cloned {c(out['voice_id'], 'bold')}  "
          f"({out.get('language')}, {out.get('duration_sec')}s @ {out.get('sample_rate')}Hz)")
    print(c(f"try it:  mcai voice speak \"hello\" --voice {out['voice_id']} "
            f"--language {out.get('language', 'en')} --backend {b['id']}", "dim"))


def cmd_voice_rm(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    vid = _voice_resolve_id(b, args.voice_id)
    try:
        with _request("DELETE", f"/api/voicestudio/{b['id']}/voices/{vid}") as r:
            r.read()
    except ApiError as e:
        die(str(e))
    print(f"removed {c(vid, 'bold')} from {b['id']}:{b['name']}")


def cmd_voice_speak(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    voice = _voice_resolve_id(b, args.voice) if args.voice != "default" else "default"
    out = Path(args.out)
    payload = {"text": args.text, "voice": voice, "language": args.language}
    if args.speed is not None:
        payload["speed"] = args.speed

    if args.stream:
        pcm = bytearray()
        sample_rate = None
        try:
            for ev in _voice_post_sse(b, "speak/stream", payload):
                if ev.get("error"):
                    die(f"speak failed: {ev['error']}")
                if "chunk_b64" in ev:
                    pcm += base64.b64decode(ev["chunk_b64"])
                    sample_rate = ev.get("sample_rate", sample_rate)
                if ev.get("done"):
                    break
        except ApiError as e:
            die(str(e))
        if not pcm or not sample_rate:
            die("stream produced no audio.")
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # int16
            w.setframerate(int(sample_rate))
            w.writeframes(bytes(pcm))
    else:
        try:
            wav = _voice_post_binary(b, "speak", payload)
        except ApiError as e:
            die(str(e))
        if not wav:
            die("speak produced no audio.")
        out.write_bytes(wav)

    print(str(out))
    if args.play:
        _voice_play(str(out))


def cmd_voice_transcribe(args):
    require_daemon()
    b = resolve_voice_backend(args.backend)
    p = Path(args.audio)
    if not p.exists():
        die(f"file not found: {args.audio}")
    fields = {"language": args.language} if args.language else {}
    try:
        res = _voice_multipart(b, "transcribe", fields, {"audio": (p.name, p.read_bytes(), _audio_ctype(p))})
    except ApiError as e:
        die(str(e))
    if args.json:
        print(json.dumps(res, indent=2)); return
    print((res.get("text") or "").strip())


# --------------------------------------------------------------------- parser
def build_parser():
    p = argparse.ArgumentParser(
        prog="mcai", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    # status / models
    sub.add_parser("status", help="server + backend health").set_defaults(fn=cmd_status)
    s = sub.add_parser("models", help="all models across backends")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_models)

    # backend group
    be = sub.add_parser("backend", help="manage LLM/voice endpoints").add_subparsers(dest="sub")
    s = be.add_parser("ls", help="list backends"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_backend_ls)
    s = be.add_parser("add", help="register a backend")
    s.add_argument("--name", required=True); s.add_argument("--kind", required=True, choices=["ollama", "openai", "voice"])
    s.add_argument("--url", required=True); s.add_argument("--api-key", dest="api_key")
    s.add_argument("--header", action="append", help="k=v (repeatable)"); s.add_argument("--disabled", action="store_true")
    s.set_defaults(fn=cmd_backend_add)
    s = be.add_parser("edit", help="update a backend"); s.add_argument("id", type=int)
    s.add_argument("--name"); s.add_argument("--url"); s.add_argument("--api-key", dest="api_key")
    s.add_argument("--header", action="append"); s.add_argument("--enable", action="store_true"); s.add_argument("--disable", action="store_true")
    s.set_defaults(fn=cmd_backend_edit)
    s = be.add_parser("rm", help="delete a backend"); s.add_argument("id", type=int); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_backend_rm)
    s = be.add_parser("test", help="probe a draft backend config")
    s.add_argument("--name"); s.add_argument("--kind", required=True, choices=["ollama", "openai", "voice"])
    s.add_argument("--url", required=True); s.add_argument("--api-key", dest="api_key"); s.add_argument("--header", action="append")
    s.set_defaults(fn=cmd_backend_test)
    s = be.add_parser("status", help="health of one backend"); s.add_argument("id", type=int); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_backend_status)
    s = be.add_parser("models", help="models on one backend"); s.add_argument("id", type=int); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_backend_models)
    s = be.add_parser("pull", help="pull a model (Ollama)"); s.add_argument("id", type=int); s.add_argument("model"); s.set_defaults(fn=cmd_backend_pull)
    s = be.add_parser("pulls", help="list pull jobs"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_backend_pulls)
    s = be.add_parser("unpull", help="delete a pulled model"); s.add_argument("id", type=int); s.add_argument("model"); s.set_defaults(fn=cmd_backend_unpull)
    s = be.add_parser("auto-register", help="register a vLLM model from a miniclosedai-llm manager")
    s.add_argument("model_id"); s.add_argument("--manager-url", default="http://localhost:8099")
    s.add_argument("--name"); s.add_argument("--prefer-docker-host", action="store_true"); s.add_argument("--api-key", dest="api_key")
    s.set_defaults(fn=cmd_backend_autoregister)

    # bots group
    bo = sub.add_parser("bots", help="manage saved bots (conversations)").add_subparsers(dest="sub")
    s = bo.add_parser("ls", help="list bots"); s.add_argument("--app"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_bots_ls)
    s = bo.add_parser("show", help="show one bot"); s.add_argument("id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_bots_show)
    s = bo.add_parser("create", help="create a bot")
    s.add_argument("--title", default="New Chat"); s.add_argument("--model", required=True)
    s.add_argument("--backend", type=int, default=1); s.add_argument("--system"); s.add_argument("--system-file", dest="system_file")
    s.add_argument("--param", action="append", help="k=v sampling param (repeatable)"); s.set_defaults(fn=cmd_bots_create)
    s = bo.add_parser("edit", help="edit a bot"); s.add_argument("id")
    s.add_argument("--title"); s.add_argument("--model"); s.add_argument("--backend", type=int)
    s.add_argument("--system"); s.add_argument("--system-file", dest="system_file"); s.add_argument("--param", action="append")
    s.set_defaults(fn=cmd_bots_edit)
    s = bo.add_parser("clone", help="clone a bot"); s.add_argument("id")
    s.add_argument("--title"); s.add_argument("--backend", type=int); s.add_argument("--model"); s.add_argument("--param", action="append")
    s.set_defaults(fn=cmd_bots_clone)
    s = bo.add_parser("clear", help="clear a bot's history"); s.add_argument("id"); s.set_defaults(fn=cmd_bots_clear)
    s = bo.add_parser("rm", help="delete a bot"); s.add_argument("id"); s.set_defaults(fn=cmd_bots_rm)
    s = bo.add_parser("export", help="export a bot"); s.add_argument("id")
    s.add_argument("--kind", choices=list(_EXPORT_KINDS), default="config")
    s.add_argument("--with-history", action="store_true"); s.add_argument("--out"); s.set_defaults(fn=cmd_bots_export)
    s = bo.add_parser("import", help="import a bot from a .miniclosed-bot.json file")
    s.add_argument("file"); s.add_argument("--backend", type=int); s.set_defaults(fn=cmd_bots_import)

    # chat / send / url
    s = sub.add_parser("chat", help="interactive chat with a bot (REPL)")
    s.add_argument("id"); s.add_argument("--show-thinking", action="store_true", dest="show_thinking"); s.set_defaults(fn=cmd_chat)
    s = sub.add_parser("send", help="one-shot message to a bot")
    s.add_argument("id"); s.add_argument("prompt")
    s.add_argument("--ephemeral", action="store_true", help="don't save the turn / ignore history")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_send)
    s = sub.add_parser("url", help="callable endpoint + code snippets for a bot"); s.add_argument("id"); s.set_defaults(fn=cmd_url)

    # kb group
    kb = sub.add_parser("kb", help="per-bot knowledge base (RAG)").add_subparsers(dest="sub")
    s = kb.add_parser("ls", help="list documents"); s.add_argument("id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_kb_ls)
    s = kb.add_parser("add", help="upload a document"); s.add_argument("id"); s.add_argument("file"); s.set_defaults(fn=cmd_kb_add)
    s = kb.add_parser("rm", help="remove a document"); s.add_argument("id"); s.add_argument("doc_id", type=int); s.set_defaults(fn=cmd_kb_rm)

    # mcp group
    mc = sub.add_parser("mcp", help="per-bot MCP extensions").add_subparsers(dest="sub")
    s = mc.add_parser("ls", help="list MCP servers"); s.add_argument("id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_mcp_ls)
    s = mc.add_parser("add", help="add an MCP server"); s.add_argument("id"); s.add_argument("--url", required=True); s.add_argument("--name"); s.set_defaults(fn=cmd_mcp_add)
    s = mc.add_parser("rm", help="remove an MCP server"); s.add_argument("id"); s.add_argument("--url", required=True); s.set_defaults(fn=cmd_mcp_rm)
    s = mc.add_parser("enable", help="enable an MCP server"); s.add_argument("id"); s.add_argument("--url", required=True); s.set_defaults(fn=lambda a: cmd_mcp_toggle(a, True))
    s = mc.add_parser("disable", help="disable an MCP server"); s.add_argument("id"); s.add_argument("--url", required=True); s.set_defaults(fn=lambda a: cmd_mcp_toggle(a, False))
    s = mc.add_parser("test", help="test an MCP server"); s.add_argument("id"); s.add_argument("--url", required=True); s.set_defaults(fn=cmd_mcp_test)

    # eval group
    ev = sub.add_parser("eval", help="per-bot evaluations").add_subparsers(dest="sub")
    s = ev.add_parser("ls", help="list cases"); s.add_argument("id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_eval_ls)
    s = ev.add_parser("add", help="add case(s)"); s.add_argument("id"); s.add_argument("--input"); s.add_argument("--expected"); s.add_argument("--file", help="cases.csv or .json"); s.set_defaults(fn=cmd_eval_add)
    s = ev.add_parser("rm", help="remove a case"); s.add_argument("id"); s.add_argument("case_id", type=int); s.set_defaults(fn=cmd_eval_rm)
    s = ev.add_parser("clear", help="clear all cases"); s.add_argument("id"); s.set_defaults(fn=cmd_eval_clear)
    s = ev.add_parser("seed", help="seed cases from chat history"); s.add_argument("id"); s.set_defaults(fn=cmd_eval_seed)
    s = ev.add_parser("run", help="run evals"); s.add_argument("id")
    s.add_argument("--mode", choices=["exact", "contains", "judge"], default="exact")
    s.add_argument("--judge-model", dest="judge_model"); s.add_argument("--judge-backend", dest="judge_backend", type=int)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_eval_run)

    # apps group
    ap = sub.add_parser("apps", help="group bots into applications + SDKs").add_subparsers(dest="sub")
    s = ap.add_parser("ls", help="list apps"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_apps_ls)
    s = ap.add_parser("show", help="show one app"); s.add_argument("id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_apps_show)
    s = ap.add_parser("create", help="create an app"); s.add_argument("--name", required=True); s.add_argument("--description"); s.add_argument("--link"); s.set_defaults(fn=cmd_apps_create)
    s = ap.add_parser("edit", help="edit an app"); s.add_argument("id"); s.add_argument("--name"); s.add_argument("--description"); s.add_argument("--link"); s.set_defaults(fn=cmd_apps_edit)
    s = ap.add_parser("rm", help="delete an app"); s.add_argument("id"); s.set_defaults(fn=cmd_apps_rm)
    s = ap.add_parser("add-bot", help="add a bot to an app"); s.add_argument("app"); s.add_argument("bot"); s.set_defaults(fn=cmd_apps_addbot)
    s = ap.add_parser("rm-bot", help="remove a bot from an app"); s.add_argument("app"); s.add_argument("bot"); s.set_defaults(fn=cmd_apps_rmbot)
    s = ap.add_parser("sdk", help="generate an app's SDK"); s.add_argument("id")
    s.add_argument("--lang", choices=["ts", "js", "py"], default="ts"); s.add_argument("--out"); s.add_argument("--zip", action="store_true")
    s.set_defaults(fn=cmd_apps_sdk)

    # llm group — run HuggingFace models on the miniclosedai-llm manager
    # (via /api/llm/*; port of the manager's own `mc` CLI)
    lm = sub.add_parser("llm", help="run HuggingFace LLMs via the model manager").add_subparsers(dest="sub")
    lm.add_parser("info", help="engine + GPU + dashboard status").set_defaults(fn=cmd_llm_info)
    s = lm.add_parser("gpu", help="GPU readout"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_llm_gpu)
    for name in ("ls", "list"):
        s = lm.add_parser(name, help="list models"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_llm_ls)
    s = lm.add_parser("analyze", help="inspect a HF model before downloading")
    s.add_argument("hf_id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_llm_analyze)
    s = lm.add_parser("run", help="download + run a model")
    s.add_argument("hf_id")
    s.add_argument("--name", help="served model name (default: slug of repo)")
    s.add_argument("--port", type=int)
    s.add_argument("--quant", help="fp8 | awq | gptq")
    s.add_argument("--max-len", type=int, dest="max_len")
    s.add_argument("--gpu-mem", type=float, dest="gpu_mem")
    s.add_argument("--tp", type=int, help="tensor parallel size (#GPUs)")
    s.add_argument("--max-images", type=int, dest="max_images")
    s.add_argument("--trust-remote-code", action="store_true")
    s.add_argument("--gguf-file", dest="gguf_file", help="for a multi-file GGUF repo, pick the file")
    s.add_argument("--force", action="store_true", help="launch even if it may not fit")
    s.add_argument("--wait", action="store_true", help="poll until ready")
    s.add_argument("--timeout", type=int, default=1200)
    s.set_defaults(fn=cmd_llm_run)
    s = lm.add_parser("start", help="(re)start an existing stopped model by id")
    s.add_argument("id"); s.add_argument("--wait", action="store_true")
    s.add_argument("--timeout", type=int, default=1200); s.set_defaults(fn=cmd_llm_start)
    s = lm.add_parser("stop", help="stop a running model"); s.add_argument("id"); s.set_defaults(fn=cmd_llm_stop)
    s = lm.add_parser("rm", help="remove a model (keeps weights)"); s.add_argument("id"); s.set_defaults(fn=cmd_llm_rm)
    s = lm.add_parser("status", help="status of one model"); s.add_argument("id"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_llm_status)
    s = lm.add_parser("logs", help="stream a model's logs"); s.add_argument("id")
    s.add_argument("-f", "--follow", action="store_true", help="follow (Ctrl-C to stop)"); s.set_defaults(fn=cmd_llm_logs)
    s = lm.add_parser("test", help="one-shot chat test")
    s.add_argument("id"); s.add_argument("prompt", nargs="?", default="Say hello in one short sentence.")
    s.add_argument("--image"); s.add_argument("--max-tokens", type=int, default=300, dest="max_tokens")
    s.set_defaults(fn=cmd_llm_test)
    s = lm.add_parser("url", help="base_url for this model"); s.add_argument("id"); s.set_defaults(fn=cmd_llm_url)
    s = lm.add_parser("register", help="register a ready model as a MiniClosedAI backend (one click, like the GUI)")
    s.add_argument("id"); s.add_argument("--name"); s.add_argument("--prefer-docker-host", action="store_true")
    s.set_defaults(fn=cmd_llm_register)
    for name in ("cache", "downloaded"):
        s = lm.add_parser(name, help="list / manage already-downloaded models")
        s.add_argument("sub", nargs="?", choices=["rm"], help="rm <hf_id> to delete weights")
        s.add_argument("hf_id", nargs="?")
        s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_llm_cache)
    s = lm.add_parser("free", help="delete a cached model's weights"); s.add_argument("hf_id"); s.set_defaults(fn=cmd_llm_free)

    # voice group — manage TTS voices on any connected miniclosedai-voice
    # service (via /api/voicestudio/{backend}/*; port of vc, extended with
    # --backend since mcai may have more than one registered voice service)
    vo = sub.add_parser("voice", help="manage TTS voices (Voice Studio)").add_subparsers(dest="sub")
    for name in ("status", "info"):
        s = vo.add_parser(name, help="service health + voice count"); s.add_argument("--backend"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_voice_status)
    s = vo.add_parser("url", help="base URL for this voice service"); s.add_argument("--backend"); s.set_defaults(fn=cmd_voice_url)
    for name in ("voices", "ls"):
        s = vo.add_parser(name, help="list available voices"); s.add_argument("--backend"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_voice_ls)
    s = vo.add_parser("clone", help="clone a voice from a WAV sample")
    s.add_argument("audio", help="path to a WAV clip (0.5-35 s)")
    s.add_argument("--name", required=True, help="display name shown in the dropdown")
    s.add_argument("--language", default="en", help="en | es (default: en)")
    s.add_argument("--backend"); s.set_defaults(fn=cmd_voice_clone)
    s = vo.add_parser("rm", help="remove a cloned voice"); s.add_argument("voice_id"); s.add_argument("--backend"); s.set_defaults(fn=cmd_voice_rm)
    s = vo.add_parser("speak", help="synthesize text to a WAV file")
    s.add_argument("text")
    s.add_argument("--voice", default="default", help="voice id (default: default)")
    s.add_argument("--language", default="en", help="en | es (default: en)")
    s.add_argument("--speed", type=float, help="0.5-2.0 speed multiplier")
    s.add_argument("--out", default="speech.wav", help="output WAV path (default: speech.wav)")
    s.add_argument("--play", action="store_true", help="play after saving (needs ffplay/aplay)")
    s.add_argument("--stream", action="store_true", help="use the streaming endpoint")
    s.add_argument("--backend"); s.set_defaults(fn=cmd_voice_speak)
    s = vo.add_parser("transcribe", help="transcribe an audio file to text")
    s.add_argument("audio", help="path to an audio file")
    s.add_argument("--language", help="language hint, e.g. en (default: auto-detect)")
    s.add_argument("--json", action="store_true"); s.add_argument("--backend")
    s.set_defaults(fn=cmd_voice_transcribe)

    # logs
    s = sub.add_parser("logs", help="recent LLM request/response logs")
    s.add_argument("sub", nargs="?", choices=["clear", "export"], help="clear | export")
    s.add_argument("--out"); s.add_argument("--limit", type=int, default=30); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_logs)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        # A group was given with no subcommand (e.g. `mcai bots`): show help.
        parser.parse_args((argv or sys.argv[1:])[:1] + ["-h"]) if getattr(args, "cmd", None) else parser.print_help()
        return EXIT_OK
    try:
        args.fn(args)
        return EXIT_OK
    except Unreachable:
        die(f"MiniClosedAI not running at {base_url()} — start it:  ./dev.sh up", EXIT_UNREACHABLE)
    except ApiError as e:
        die(str(e))
    except BrokenPipeError:
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
