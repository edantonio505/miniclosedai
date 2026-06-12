# MiniClosedAI — Documentation

> ⚠ **This file predates the multi-endpoint (OpenWebUI-style) feature.** The
> README now covers install, the activity bar, the Settings page, LM Studio
> and any-OpenAI-compatible endpoint setup, the grouped model dropdown, and
> the full API surface (including `/api/backends` CRUD) at parity with the
> current app. Treat **[README.md](./README.md)** as the canonical reference.
> What remains here is a deeper architectural narrative for anyone who wants
> to read around the code — not a contract.

Full reference for architecture, features, API, and usage patterns.

For install + quick start, see **[README.md](./README.md)**.
For per-OS Ollama install details, see **[INSTALL.md](./INSTALL.md)**.
For LM Studio / OpenAI-compat endpoint setup, see
**[README § Connecting LM Studio and other OpenAI-compatible endpoints](./README.md#connecting-lm-studio-and-other-openai-compatible-endpoints)**.
For the extreme-quantization 1-bit Bonsai integration (`llama.cpp` server on port 8080), see
**[README § Adding Bonsai (PrismML's 1-bit 8B) — step by step](./README.md#adding-bonsai-prismmls-1-bit-8b--step-by-step)**.

---

## Table of contents

1. [Requirements](#requirements)
2. [Architecture overview](#architecture-overview)
3. [Running](#running)
4. [Docker deployment](#docker-deployment)
5. [UI features](#ui-features)
6. [Voice — push-to-talk (Dockerized ASR + TTS service)](#voice-push-to-talk-via-a-separate-dockerized-asr--tts-service)
7. [Apps + per-app SDK generation (TypeScript / JavaScript / Python)](#apps-groups-of-bots-and-per-app-sdk-generation)
8. [Knowledge base (RAG)](#knowledge-base-rag)
7. [Extensibility — MCP plugins](#extensibility--mcp-plugins)
8. [Evaluation & auto-improve](#evaluation--auto-improve-scoring)
9. [Worked example — connecting Bonsai (1-bit 8B)](#worked-example--connecting-bonsai-1-bit-8b)
10. [Per-chat microservice pattern](#per-chat-microservice-pattern)
11. [API reference](#api-reference)
12. [Thinking / reasoning control](#thinking--reasoning-control)
13. [Stopping generation](#stopping-generation)
14. [Fine-tuning data export](#fine-tuning-data-export)
15. [Worked example — automated image labeling](#worked-example--automated-image-labeling)
16. [Worked example — chatbot frontends (Python CLI + HTML widget)](#worked-example--chatbot-frontends-python-cli--html-widget)
17. [Client SDK — composing bots from your code](#client-sdk--composing-bots-from-your-code)
18. [Bot import / export](#bot-import--export)
19. [Self-upgrade](#self-upgrade)
20. [Prompt generator](#prompt-generator)
21. [Activity logs](#activity-logs)
22. [Database](#database)
23. [Configuration](#configuration)
24. [File layout](#file-layout)
25. [Security](#security)
26. [Troubleshooting](#troubleshooting)
27. [Testing](#testing)

---

## Requirements

Five supported deployment paths. The quickest is the **one-line installer** ([Path Z](#path-z--one-line-installer-installsh) — pipe a curl into bash) which automates Path D. The other four are two methods (Docker / bare-metal) crossed with two modes (heavy / lite); pick by hardware + use case.

| | Heavy (with built-in Ollama) | Lite (no Ollama, BYO endpoint) |
|---|---|---|
| **Docker** | [Path A](#path-a--docker-recommended-zero-manual-ollama-install) — compose stack, three baked models, ~10.3 GB image, GPU recommended. | [Path C](#path-c--docker-lite-no-built-in-ollama) — single ~160 MB container, zero GPU, no model layers. |
| **Bare-metal** | [Path B](#path-b--manual-python-venv--host-ollama) — Python venv + host Ollama. | [Path D](#path-d--manual-lite-no-local-ollama) — Python venv only. `MINICLOSEDAI_NO_OLLAMA=1` env var skips the built-in Ollama backend; you register an external endpoint via the Settings page. **Or use [Path Z](#path-z--one-line-installer-installsh) — `curl … | bash` — which does this for you.** |

Lite mode (paths C, D, and Z) is the right pick when inference happens on a *different* machine — a remote Ollama relay, an LM Studio on your LAN, vLLM on a GPU box, etc. The local install is just the FastAPI app + SQLite + static frontend.

### Path Z — One-line installer (`install.sh`)

The fastest non-Docker route. Effectively a wrapper around Path D — clones the repo, sets up a Python venv, installs deps, optionally starts uvicorn detached.

```bash
curl -fsSL https://raw.githubusercontent.com/edantonio505/miniclosedai/main/install.sh | bash
```

Behaviorally identical to running the manual lite steps by hand, with the same end state: a `~/miniclosedai` checkout + `.venv` + a uvicorn process bound to `0.0.0.0:8095`. Re-running the same command pulls and reinstalls in place (idempotent). The script's source lives at the repo root for inspection before piping it to bash.

Environment overrides (read by the script):

| Env var | Default | Effect |
|---|---|---|
| `MINICLOSEDAI_DIR` | `$HOME/miniclosedai` | Target checkout path. Existing dirs that aren't git checkouts cause an early refusal; existing checkouts get `git pull`-ed instead. |
| `MINICLOSEDAI_PORT` | `8095` | Bind port for auto-started uvicorn. |
| `MINICLOSEDAI_START` | `1` | `0` skips the auto-start (script just prints the run command). |
| `MINICLOSEDAI_BRANCH` | `main` | Useful for testing PRs / feature branches. |
| `MINICLOSEDAI_REPO` | canonical URL | Fork support. |

Prereq checks (`git`, `python3 ≥ 3.10`) run before any side-effects. On port conflict the script `pkill`s any existing `uvicorn app:app --port $PORT` before starting the new one — re-running the installer is the supported way to apply updates *without* the in-place upgrade machinery (which requires the server to already be answering on `/api/upgrade/run`).

### Path A — Docker (recommended, zero manual Ollama install)

| Requirement | Version |
|---|---|
| Docker Engine | 20.10+ with Compose v2 bundled |
| `nvidia-container-toolkit` | current, for NVIDIA GPU passthrough (Linux: `sudo apt install nvidia-container-toolkit`) — optional, CPU override exists |
| Free disk | ~20 GB build-time space on Docker's `data-root`; final Ollama image ~10.3 GB (base `ollama/ollama` includes CUDA/ROCm libs) + app image ~160 MB |
| RAM / VRAM | ~6 GB VRAM comfortably holds all three baked models simultaneously; 2 GB swaps work with `OLLAMA_KEEP_ALIVE` tuning |

See [Docker deployment](#docker-deployment) for the full walkthrough. All three of the smallest-and-most-effective Ollama models are baked into the image (`llama3.2:3b`, `qwen2.5:3b`, `gemma2:2b`) — no manual `ollama pull`.

### Path B — Manual (Python venv + host Ollama)

| Requirement | Version |
|---|---|
| Python | 3.10 or newer |
| Ollama | any recent version ([ollama.com](https://ollama.com)), running on `http://localhost:11434` |
| At least one pulled model | See [README.md](./README.md#recommended-models-1b10b) |
| RAM | ~2 GB free for 1–3B models; 8+ GB for 7–9B |

Python dependencies (five total, in `requirements.txt`):

```
fastapi>=0.110
uvicorn>=0.27
httpx>=0.27
python-multipart>=0.0.9   # multipart/form-data parsing for /api/extract-pdf
pypdf>=4.0                # server-side PDF text extraction for chat attachments
```

`pypdf` and `python-multipart` are pinned so file-attachment support (images, PDFs, text files in the chat composer) works out of the box — `pip install -r requirements.txt` is the full setup; users do not need to install anything else by hand.

### Path C — Docker lite (no built-in Ollama)

Single-service compose file. Brings up only the MiniClosedAI web app — no Ollama container, no GPU passthrough, no model layers.

| Requirement | Version |
|---|---|
| Docker Engine | 20.10+ with Compose v2 bundled |
| Free disk | ~250 MB total (image is ~160 MB; the rest is the SQLite volume) |
| RAM | ~150 MB |
| GPU / VRAM | none — inference happens on the external endpoint you'll register |

Bring it up:

```bash
docker compose -f docker-compose.lite.yml up -d --build
# → http://127.0.0.1:8095
# → ⚙️ Settings → Add endpoint
```

The compose file (`/home/edgar/Desktop/miniclosedai/docker-compose.lite.yml`) sets `MINICLOSEDAI_NO_OLLAMA=1` in the container env. See [Lite mode internals](#lite-mode-internals-mini-closed-ai_no_ollama) below for what that env var does.

### Path D — Manual lite (no local Ollama)

Drops every system requirement except Python and the five pip packages.

| Requirement | Version |
|---|---|
| Python | 3.10 or newer |
| pip packages | the same five as Path B (`fastapi`, `uvicorn`, `httpx`, `python-multipart`, `pypdf`) |
| RAM | ~150 MB |
| At least one **external** LLM endpoint | reachable at runtime; configured via the Settings page after first boot |

Setup:

```bash
git clone https://github.com/edantonio505/miniclosedai.git && cd miniclosedai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
MINICLOSEDAI_NO_OLLAMA=1 python -m uvicorn app:app --host 0.0.0.0 --port 8095
```

Open the UI, click **⚙️ Settings → Add endpoint**, paste your endpoint URL + (optional) Bearer token, save. Done.

### Lite mode internals (`MINICLOSEDAI_NO_OLLAMA`)

When `MINICLOSEDAI_NO_OLLAMA` is set to `1` / `true` / `yes` / `on` (case-insensitive), `db.init_db()` behaves differently in two ways:

1. **On a fresh database** — the `INSERT OR IGNORE` that normally seeds the `Ollama (built-in)` row at id=1 is skipped. The backends table starts empty; the dashboard model dropdown shows a "Welcome — let's add your first endpoint" CTA that flips to the Settings tab.
2. **On an existing database** — any pre-existing built-in Ollama row (`is_builtin = 1 AND kind = 'ollama'`) gets `enabled = 0` set on it at startup. The row stays in place (it's the FK target for any `conversation.backend_id = 1`), but it's hidden from the dashboard dropdown and the model-aggregation endpoint, and probes don't run against it.

The flag is honored by `db._no_ollama_mode()` in [`/home/edgar/Desktop/miniclosedai/db.py`](./db.py). All four deployment paths share the same SQLite schema, so flipping between heavy and lite is just a matter of toggling the env var (no migrations to run, no DB to drop) — though re-enabling the built-in row after a lite-mode auto-disable currently requires a one-time manual step (Settings page, or `UPDATE backends SET enabled = 1 WHERE is_builtin = 1`).

---

## Architecture overview

### Manual install (Python venv + host Ollama)

```
 ┌─────────────────┐   HTTP/SSE    ┌──────────────────┐   HTTP   ┌────────────┐
 │  Browser (vJS)  │ ───────────▶  │  FastAPI (app.py) │ ───────▶ │   Ollama   │
 │  index.html     │               │  llm.py, db.py    │          │ :11434     │
 │  app.js         │               │  SQLite on disk   │          │            │
 └─────────────────┘               └──────────────────┘          └────────────┘
```

- **Frontend**: single-page vanilla JS (no build step, no framework). Uses `marked.js` via CDN for Markdown.
- **Backend**: FastAPI app with three routes groups — `models`, `conversations`, `chat`. Streaming via Server-Sent Events.
- **LLM client**: thin `httpx` wrapper over Ollama's `/api/chat` endpoint. Handles both regular `content` and `thinking` token streams.
- **Persistence**: a single SQLite file (`miniclosedai.db`) with one table (`conversations`). Each conversation stores its saved config (model, system prompt, sampling params) plus the full message history as a JSON blob.

The app serves its own static UI at `/`. API docs are auto-generated by FastAPI at `/docs`.

### Docker deployment (compose, two services)

```
 ┌─────────────────┐   HTTP/SSE    ┌──────────────────────┐  internal   ┌────────────────────────┐
 │  Browser (vJS)  │ ───────────▶  │   miniclosedai       │   compose   │   ollama               │
 │  :8095 host     │               │   FastAPI + uvicorn  │ ──────────▶ │   ollama/ollama:0.5.x  │
 │  (loopback)     │               │   python:3.12-slim   │   net       │   + 3 models baked in  │
 └─────────────────┘               │   ~160 MB            │  http://    │   ~10.3 GB image        │
                                   │                      │  ollama:    │   :11434 (internal)    │
                                   └──────────────────────┘  11434      └────────────────────────┘
                                         │                                       │
                                    miniclosedai_db                         ollama_models
                                    (named volume)                          (named volume)
```

- **Two images, two services.** MiniClosedAI (FastAPI app, ~160 MB) and Ollama (extended base + three models baked in as layers, ~10.3 GB) run in separate containers on a shared compose network.
- **Ollama is not published to host.** MiniClosedAI reaches it only on the internal `miniclosedai_net` via `http://ollama:11434` (env var `OLLAMA_URL`, which the app already honors — no code change for endpoint switching).
- **MiniClosedAI is loopback-only by default.** `ports: ["127.0.0.1:8095:8095"]` — LAN exposure is a conscious one-character opt-in (see Security below).
- **Named volumes persist state.** `miniclosedai_db` holds the SQLite database (`/app/data/miniclosedai.db` inside the container, reached via the `MINICLOSEDAI_DB_PATH` env override). `ollama_models` holds any models pulled at runtime (baked models live in image layers and are union-mounted under it on first `up`).
- **Healthchecks gate startup.** `depends_on: ollama: condition: service_healthy` means MiniClosedAI doesn't start until Ollama's `/api/tags` answers — the UI never shows an empty model dropdown on cold boot.
- **GPU by default, CPU by override.** `docker-compose.yml` declares an NVIDIA device reservation. `docker-compose.cpu.yml` uses `devices: !reset []` (Compose v2.24+) to strip it for CPU-only hosts.

---

## Running

From the project root with deps installed:

```bash
python app.py                               # bound to 127.0.0.1:8095
# or
uvicorn app:app --host 127.0.0.1 --port 8095
```

### LAN / network access

```bash
uvicorn app:app --host 0.0.0.0 --port 8095
```

Then point other devices at `http://<host-ip>:8095`. The app has **no auth**; see [Security](#security).

### Alternative port

```bash
uvicorn app:app --port 8096
```

### Alternative Ollama location

```bash
OLLAMA_URL=http://192.168.1.42:11434 python app.py
```

---

## Docker deployment

The repo ships a production-shaped Docker setup: two images orchestrated by Compose, three Ollama models baked into the Ollama image at build time so a fresh `docker compose up` needs zero network dependency at runtime. All the files live at the project root.

### Files involved

| File | Role |
|---|---|
| **`Dockerfile`** | MiniClosedAI app image. `python:3.12-slim` + the three `requirements.txt` deps + app code + static assets. Non-root `app` user. CMD: `uvicorn app:app --host 0.0.0.0 --port 8095`. Final size ~160 MB. |
| **`Dockerfile.ollama`** | Extends `ollama/ollama:0.5.13`. Bakes each baked model in its own `RUN` layer via `scripts/bake-models.sh`. Total image ~10.3 GB. |
| **`scripts/bake-models.sh`** | The background-daemon trick — `ollama serve &` in foreground-only base image, poll `/api/tags` up to 60 s (not a blind `sleep`), `ollama pull` with 3 retries, clean SIGTERM + `wait` before the `RUN` exits, and sanity-check via `ollama list` so a silently-failed pull fails the layer. One script per model per layer. |
| **`docker-compose.yml`** | Two services (`miniclosedai`, `ollama`). Internal compose network. Two named volumes (`miniclosedai_db`, `ollama_models`). NVIDIA GPU device reservation. Healthchecks on both services. `depends_on: ollama: condition: service_healthy`. Loopback-only host port bind. |
| **`docker-compose.cpu.yml`** | Override that strips the GPU reservation via `devices: !reset []` (Compose v2.24+). Use with `-f docker-compose.yml -f docker-compose.cpu.yml`. |
| **`docker-compose.lite.yml`** | Single-service compose — only the MiniClosedAI app, no Ollama container, no GPU, no model layers. Sets `MINICLOSEDAI_NO_OLLAMA=1` in the container env. Run with `docker compose -f docker-compose.lite.yml up -d --build`. ~30 s build, ~160 MB image, runs on any laptop. |
| **`.dockerignore`** | Defense-in-depth — excludes `.venv/`, `.git/`, `__pycache__/`, `test_e2e.py`, `miniclosedai.db`, docs, screenshots, scratch notes, editor files, and the Docker files themselves from the build context. |

### Baked models

The defaults match the README's [Recommended models table](./README.md#recommended-models-1b10b) pick-list for "smallest + most popular + most effective":

| Model | Size on disk | Role in the UI |
|---|---|---|
| `llama3.2:3b` | ~2.0 GB | General-purpose workhorse. Supports `think=true`. |
| `qwen2.5:3b` | ~1.9 GB | Structured-output / JSON specialist. Supports `/think` + `/no_think` magic tokens. |
| `gemma2:2b` | ~1.6 GB | Snap-fast classifier (~30 % faster first-token). No thinking mode — best for high-volume microservice bots. |

Total model payload ~5.5 GB; three distinct behavioral profiles (not three variants of the same thing) so the UI dropdown is actually useful. Edit the three `RUN /usr/local/bin/bake-models.sh <model>` lines in `Dockerfile.ollama` to swap; each model is its own layer so swapping one doesn't invalidate the others. See the alternative shortlists in `README.md`.

### Commands

```bash
# First build (8–15 min, pulls 5.5 GB of models from registry.ollama.ai)
docker compose up -d --build

# CPU-only hosts (or hosts without nvidia-container-toolkit)
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build

# Watch progress
docker compose ps
docker compose logs -f

# Add a model at runtime (persists in ollama_models volume)
docker compose exec ollama ollama pull phi3:mini

# Remove a model
docker compose exec ollama ollama rm phi3:mini

# List everything
docker compose exec ollama ollama list

# Tear down but keep data
docker compose down

# Nuke data (deletes both named volumes — chats and models)
docker compose down -v
```

### Env vars the containers read

| Variable | Where | Effect |
|---|---|---|
| `OLLAMA_URL` | MiniClosedAI container; set to `http://ollama:11434` in compose | Used by `db.py:23` to seed the built-in backend row and by `llm.py:32` as the default client target. Already supported by the codebase — Dockerization required no code change here. |
| `MINICLOSEDAI_DB_PATH` | MiniClosedAI container; set to `/app/data/miniclosedai.db` in compose | The one-line override added to `db.py:21` so the SQLite file can live in the `miniclosedai_db` named volume without mounting over the app code tree. Unset in local dev = original path behavior. |
| `OLLAMA_KEEP_ALIVE` | Ollama container; set to `5m` in compose | Keeps models resident in VRAM between requests so switching among the three baked models doesn't trigger unload/reload churn. Useful on <8 GB GPUs. |

### Persistence matrix

| Data | Lives at | Survives `down` | Survives `down -v` | Rebuilt on new image |
|---|---|---|---|---|
| Chat history, saved bot configs, backends table | `miniclosedai_db:/app/data/miniclosedai.db` | ✅ | ❌ | ✅ |
| Runtime-pulled models | `ollama_models:/root/.ollama` | ✅ | ❌ | ✅ (survives, but new baked models also land here on first `up`) |
| Baked models | Ollama image layer | ✅ (return on next `up`) | ✅ (in the image) | ❌ (fresh layer — same models, same blob hashes → Docker layer cache re-uses them) |

### Traps designed out

- **`app.py`'s `__main__` block binds 127.0.0.1.** Using `CMD ["python", "app.py"]` in the Dockerfile would silently produce a container whose internal healthcheck passes but is unreachable from the published port. The Dockerfile uses `uvicorn --host 0.0.0.0` explicitly.
- **Hard-coded DB path.** Without the `MINICLOSEDAI_DB_PATH` env override, the only way to persist the SQLite file was to mount a volume over `/app` (shadowing the code) or bind-mount a single `.db` file (fragile, pre-existing file required). The one-line env override sidesteps both.
- **`ollama serve` is a foreground process.** The base `ollama/ollama` image has no systemd; a build-time pull requires backgrounding the daemon, polling `/api/tags` (not blind `sleep`), pulling, then clean-killing + `wait`-ing so layer commit doesn't freeze a half-flushed blob. Handled in `scripts/bake-models.sh` with explicit retries, sanity-check, and error propagation.
- **Compose list-merge gotcha.** Earlier draft used `reservations: {}` to strip the GPU block; Compose deep-merges maps, so the `devices` list leaked through. Final CPU override uses `devices: !reset []` (Compose v2.24+) which replaces rather than merges.
- **Base-image drift.** `ollama/ollama:0.5.13` and `python:3.12-slim` are pinned. Unpinned `:latest` would silently trigger full re-bakes on unrelated rebuilds.

### Security defaults

MiniClosedAI has no authentication. The compose file binds host port `127.0.0.1:8095:8095` — **localhost-only by default**. To expose to the LAN (phones, other machines):

```yaml
ports:
  - "8095:8095"       # remove the "127.0.0.1:" prefix, then read Security below
```

See [Security](#security) and the README's [LAN access](./README.md#lan-access) section before doing that. Same trust model as running `python app.py` on your laptop — don't expose to networks you don't control.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `could not select device driver "nvidia"` on `up` | `nvidia-container-toolkit` missing. `sudo apt install nvidia-container-toolkit && sudo systemctl restart docker`. Or use the CPU override. |
| `ENOSPC` during a bake layer | Docker `data-root` out of space. `docker system df` / `docker system prune`. Need ~15 GB headroom for the three-model build. |
| `docker compose ps` shows ollama `healthy` but UI's model dropdown is empty | `docker compose exec ollama ollama list` — confirms baked models. If the list is empty, a bake layer silently succeeded without pulling. `docker compose build --no-cache ollama` to rebuild; check `/tmp/ollama-serve.log` inside the container. |
| MiniClosedAI can't reach Ollama | `docker compose exec miniclosedai env \| grep OLLAMA_URL` must show `http://ollama:11434`. If it shows `http://localhost:...`, env isn't inheriting from compose — check `environment:` stanza on the `miniclosedai` service. |
| `SQLITE_IOERR_LOCK` errors in the app logs | Someone replaced the named volume with a bind mount on Docker Desktop (osxfs/gRPC-FUSE). Switch back to named volumes — SQLite locking is broken on bind mounts in those filesystems. |
| Switching GPU ↔ CPU override takes no effect | Docker layer cache. `docker compose down && docker compose up -d --build` to force a fresh build. |

---

## UI features

### Navigation (list → detail)

The UI is a **list/detail** pattern, not flat tabs. The activity bar has three icons — **Bots** (home, message-square), **Logs** (terminal), **Settings** (gear). The "Dashboard" page still exists internally (it's the chat surface) but has no nav button; you reach it by drilling into a bot from the list.

<p align="center">
  <img src="docs/images/bots_page_listview.png" alt="Bots page — list view" width="800"><br><em>Bots page — list view</em>
</p>
<p align="center">
  <img src="docs/images/bots_page_avatars.png" alt="Bots page — grid view with per-bot circle avatars" width="800"><br><em>Bots page — grid view with per-bot circle avatars (bot-glyph fallback on a per-id color; click to upload an image)</em>
</p>

- **Per-bot avatar** — a circle (`.bot-card-avatar`, a focusable `<button>`) to the left of the name in both views. Stored as a base64 data URL in a nullable `avatar` column on `conversations` (additive migration in `db.py`), returned by both the list and single-conversation GETs. Set via `PUT /api/conversations/{id}/avatar` (validates a `data:image/*` prefix, ~1 MB cap) and cleared via `DELETE …/avatar` — neither bumps `updated_at`. Client side: `_renderAvatarInto(el, c)` paints either an `<img>` or, as fallback, an inline bot SVG (`_BOT_AVATAR_SVG`) on a stable hue derived from the bot id (`--avatar-hue`, `.is-fallback`); clicking the circle runs `_pickAvatarFor` → `_makeAvatarDataUrl` (center-crops to a square and downscales to a 128px JPEG via canvas) → PUT → cache update + re-render. The same avatar is mirrored into the **chat sidebar's System Prompt header** (`#sys-prompt-avatar`, `renderSysPromptAvatar`), which is also click-to-change; the avatar's hover `transform` makes a local stacking context, so it carries `z-index` on `:hover`/`:focus-visible` to keep its tooltip above the heading.
- **Bots page** — searchable cards; click to enter that chat. Slide-in animation. The toolbar (filter input + bot count + a **list ↔ grid view toggle**, persisted to `localStorage` key `miniclosedai:botsView`) is `position: sticky; top: 0; z-index: 10` with `background: var(--bg)` so it pins to the top of the scrolling `.page-bots` container while cards scroll underneath. Grid view is `.bots-list.grid-view` (responsive auto-fill tiles); list is the default vertical stack. `⌘K` / `Ctrl+K` from anywhere (or `/` outside a text field) jumps here and focuses the filter.
- **Bot card row actions** — appear on `:hover` / `:focus-within` only, in `.bot-card-actions` (an absolutely-positioned strip on the right edge with a gradient mask fade): `</>` API code, **📚 Manage knowledge**, **🧩 Manage extensions**, and 🗑 Delete. All call `e.stopPropagation()` and carry the card's `data-conv-id`.
  - **📚 → Manage Knowledge modal** (`openKnowledgeModal`): lists the bot's documents (filename · chunk count · size · date) with per-doc delete, plus **+ Add document** which routes the shared hidden file input (`#bots-kb-file`) via `_triggerKbUpload({convId, onStatus, onDone})` → `_uploadKnowledgeToConv`.
  - **🧩 → Manage Extensions modal** (`openMcpModal`): lists the bot's MCP servers with a per-server **enable toggle** + remove (each mutation PUTs the full list via `_saveMcpModal`), plus an add-by-URL row → `_addMcpToConv`.
  - Both modals reuse the same endpoints as the sidebar panels; if the edited bot is the one currently open, the matching sidebar panel (`loadKnowledge` / `loadMcp`) refreshes so the two surfaces stay in sync. The card itself gets `z-index: 5` on hover so the actions and their tooltips can paint over the next card's border (`.bot-card-actions` uses `transform`, which creates a local stacking context, so the tooltip's `z-index: 9999` only competes within that subtree). Delete is wired to `deleteConvById(id, { title })`, which prunes the id from `_streaming` / `_unread` so stale dots don't linger, then falls back to opening the next-most-recent bot (or the Bots empty state if none remain). API code is wired to `openApiCodeForConv(id)` (see below) which scopes the modal to that id without disturbing `state.conversationId`.
- **Topbar `<` back button** — leftmost element of the chat topbar; returns to the Bots list with a reverse slide. `Esc` is the keyboard equivalent (skipped when a modal is open).
- **Pulse dot** on the Bots icon AND on individual bot cards — driven by two sets:
  - `_streaming` — convs whose chat stream is currently in flight.
  - `_unread` — convs whose stream finished while the user wasn't watching.
  
  Dot is lit whenever either set has an id the user isn't currently viewing. Marking a conv as viewed (= landing on the Dashboard with that conv loaded, OR explicitly opening it from the list) drops it from `_unread`. See `_refreshUnreadUI` / `_onStreamStart` / `_onStreamEnd` / `_markConvViewed` in `static/app.js`.

### Chat topbar (when a bot is open)

- **`<` back button** (leftmost) — `applyActivePage("bots")`. Also bound to `Esc`.
- **Model** `<select>` — lists every model from every reachable backend, grouped by `<optgroup>`. Switching updates the active conversation's saved model (auto-saved).
- **Bot name pill** — read-only label after the model select; mirrors the currently-open bot's title. Updated by `renderBreadcrumb()`.
- **+ New chat** (plus icon) — creates a fresh conversation with the current model, system prompt, and params.
- **Import bot** (upload-cloud) — loads a `.miniclosed-bot.json`.
- **🧹 Clear** — wipes messages in the current conversation (keeps config).
- **Download** (tray) — popover with 5 export formats (CSV / multimodal ZIP / classification ZIP / bot-config JSON / bot-config-with-history JSON).
- **🗑 Delete** — deletes the current conversation. If it was the last bot, the UI auto-returns to the Bots list.
- **`</>` API Code** (icon-only) — opens the snippet modal with cURL / Python / JavaScript variants. The modal header carries a **`Bot #N` copy pill** that copies just the raw conversation id (helpful when your microservice config only needs the id, not the full URL or snippet). The pill flashes "Copied!" in accent color for 1.2s on success. When the modal is opened from a bot card's row `</>` action via `openApiCodeForConv(id)`, the module-level `_modalConvId` overrides `state.conversationId` for snippet rendering and the pill — without mutating `state`. `closeModal()` clears `_modalConvId` so the next topbar open reverts to live conversation state.

### Sidebar

- **System Prompt** — editable textarea; auto-saves per conversation. A **✨ Generate prompt / Improve prompt** affordance sits above it (see [Prompt generator](#prompt-generator) below).
- **Parameters** — sliders and inputs for:
  - **Temperature** (0.0–2.0)
  - **Max tokens** (64–32 000) — cap on the response length.
  - **Top P** (0.0–1.0), **Top K** (1–500)
  - **Thinking** — Default / Off / On / Low / Medium / High. See [Thinking control](#thinking--reasoning-control).
  - **Max thinking tokens** — optional hard cap; once exceeded the server stops generation and marks the response as truncated.
- **Reset defaults** — restores built-in defaults for the current conversation.
- **Status** — Ollama connection state and model count.

### Chat

- Streaming responses with a blinking cursor.
- Markdown and code-block rendering.
- Thinking tokens (for reasoning models) appear in a collapsible `💭 Thinking` block that auto-collapses when normal output starts.
- Per-message badge shows the exact model + params used for reproducibility.
- **⏹ Stop** button during streaming — aborts generation immediately (see [Stopping generation](#stopping-generation)).
- **Edit pencil** on every assistant message (top-right) opens an in-place textarea for rewriting the response. `Save` persists (first edit pins the pristine output under `original_content`), `Cancel` or `Esc` discards. Disabled while a stream is active. See [Fine-tuning data export](#fine-tuning-data-export).
- **Download CSV** in the header exports the current chat as a two-column `input,output` SFT dataset. See [Fine-tuning data export](#fine-tuning-data-export).

### Splitters

Two draggable dividers persist to `localStorage`:

- **Vertical splitter** (between sidebar and chat) — drag to resize sidebar width. Double-click to reset to 300 px.
- **Horizontal splitter** (between System Prompt and Parameters) — drag to resize the System Prompt panel height. Double-click to reset to 220 px.

The sidebar's scrollbar is hidden across all browsers; scrolling still works via wheel / trackpad / keyboard.

### Logs page

Vertical-nav button (terminal icon, between Bots and Settings in the activity bar) opens the LLM activity viewer. Implementation detail in [Activity logs](#activity-logs) below; from a user's perspective it's a per-call row showing status / endpoint / model / latency / timestamp, click-to-expand for params + messages + response. The toolbar (filter input + entry count) is `position: sticky` at top of the scrolling container — same treatment as the Bots page — so the filter stays visible while rows scroll under it. Polling auto-pauses when the page isn't visible.

<p align="center">
  <img src="docs/images/logs_page.png" alt="Logs page — per-call request/response viewer" width="800"><br><em>Logs page</em>
</p>

---

## Voice (push-to-talk via a separate Dockerized ASR + TTS service)

A self-hosted voice surface for any bot: hold the 🎤 on the chat composer, talk, release; the transcript appears as the user turn, the assistant reply streams in **and speaks back**, all in one round trip. The audio plumbing is intentionally split between **two containers** so MiniClosedAI doesn't carry GPU-heavy model dependencies and so the voice service is interchangeable between local (CPU) and remote (RunPod GPU) without touching MiniClosedAI's code.

### Architecture

```
Browser                       MiniClosedAI                 Voice Docker             Ollama / LLM
─────────                     ─────────────                 ────────────             ────────────
🎤 hold
  ↓ MediaRecorder (WebM/Opus)
  ↓ POST multipart
  ───────────────────────►   /api/conversations/{id}/voice/turn
                               │  (1) /transcribe ─────►    faster-whisper → text
                               │  (2) chat path ──────────────────────────────►   bot reply (streamed)
                               │  (3) /speak/stream ───►    Piper → SSE PCM chunks
                               ◄──────────────────────────
  ◄── SSE: {transcript}, {chunk} × N, {audio_chunk_b64} × M, {end} ──
  Web Audio playback queue
```

### Voice service — `miniclosedai-voice/`

A standalone FastAPI app (one folder, one Docker image). MIT-licensed open-source stack:

| Layer | Library | Notes |
|---|---|---|
| ASR | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | CTranslate2 Whisper. Multilingual. fp16 on GPU, int8 on CPU. `VOICE_ASR_MODEL` picks `tiny`/`base`/`small`/`medium`/`large-v3`. |
| TTS | [Piper](https://github.com/rhasspy/piper) | ONNX runtime. v1 ships 4 EN + 4 ES voices; auto-downloads from `rhasspy/piper-voices` on Hugging Face on first use. |
| HTTP | FastAPI + uvicorn | Single worker (GPU is serialized). CORS open. Optional `VOICE_API_KEY` Bearer auth. |

The five-endpoint contract (`miniclosedai-voice/server.py`):

```
GET  /health         — {ok, asr_model, tts_model, device, voices_loaded}
GET  /voices         — {"en": [{id,name,gender}, ...], "es": [...]}
POST /transcribe     — multipart audio (+optional language) → {text, language, segments}
POST /speak          — JSON {text, voice, language, speed?} → audio/wav body
POST /speak/stream   — same body → SSE: {chunk_b64, sample_rate} × N, then {done:true}
```

### MiniClosedAI side

**Backend integration** (`db.py`, `app.py`, `voice.py`):

- The `backends.kind` CHECK now accepts `'voice'` (idempotent recreate-table migration in `db.py:_migrate_backends_kind_to_include_voice`). All existing backend lifecycle endpoints (`/api/backends`, `/status`, `/test`, `/models`) dispatch to voice via a new branch in `llm._IMPLS["voice"]`; `/models` returns the voices catalog reshaped to the Ollama-style `[{name, size, details}]` list the frontend already parses.
- `voice.py` (new module) provides the four async httpx wrappers — `health`, `list_voices`, `transcribe`, `speak_stream` — same style as `llm._ollama_*` / `llm._openai_*`.
- New per-conversation endpoints (`app.py`):
  - `POST /api/conversations/{id}/voice/transcribe` — multipart audio → JSON transcript.
  - `POST /api/conversations/{id}/voice/speak` — JSON `{text}` → SSE audio chunks.
  - `POST /api/conversations/{id}/voice/turn` — multipart audio → one merged SSE: ASR transcript, chat reply (text), TTS audio. Reuses `_resolve_conversation_chat`, `_augment_messages_with_knowledge`, `_maybe_override_to_relay`, and `_persist_conv_chat_turn` so RAG, relay-routing, and conversation persistence all behave identically to a normal `/chat/stream` turn.
- Per-conversation `voice_settings` JSON column (`{voice_backend_id?, voice_id?, language?, autoplay?}`) — the resolver picks the explicit backend id, else the first enabled voice backend; the voice/language resolve from `voice_settings` else the backend's first English voice.

**Frontend** (`static/app.js`, `index.html`, `style.css`):

- `<option value="voice">Voice (ASR + TTS)</option>` joins the `#backend-kind` dropdown; the URL hint mentions the voice URL.
- `#mic-btn` on the composer is hidden by default; `_refreshMicAffordance()` unhides it when `backendCache` contains any enabled `kind='voice'` backend.
- Press-and-hold or click-toggle: `_startRecording()` → `navigator.mediaDevices.getUserMedia({audio:true})` + `MediaRecorder`; on release `_stopRecordingAndSend()` posts the blob to `/voice/turn`.
- `_consumeVoiceTurn()` reads the merged SSE: `transcript` renders a user bubble + opens an assistant bubble, `chunk` streams text into it, `audio_chunk_b64` decodes (atob → Int16 → Float32) and `_enqueueAudioChunk()` schedules it on a sliding `AudioContext.currentTime` cursor for gapless playback.
- CSS pulse animation on `#mic-btn.recording`; `.busy` while the turn is in flight.

### Deploying the voice service

The image is identical between local and RunPod; only the URL you paste into Settings differs.

```bash
# Local CPU (default)
docker run --rm -p 8090:8090 \
    -v voice_models:/root/.cache/huggingface -v voice_pipers:/voices \
    miniclosedai-voice:latest

# GPU
docker run --rm --gpus all -p 8090:8090 \
    -e VOICE_ASR_MODEL=large-v3 -e VOICE_DEVICE=cuda \
    -v voice_models:/root/.cache/huggingface -v voice_pipers:/voices \
    miniclosedai-voice:latest
```

Then in MiniClosedAI: **Settings → LLM Endpoints → + Add endpoint** → kind `Voice (ASR + TTS)` → paste URL → **Test** → Save.

### Testing

`test_e2e.py` ships a `FakeVoice` (mirrors `FakeOllama` / `FakeOpenAI`) serving canned `/health`, `/voices`, `/transcribe`, and `/speak/stream`. Nine voice-related tests cover: `kind='voice'` CRUD round-trip; `/status` reachable/unreachable; `/models` reshape into `<lang>/<voice_id>` entries; `/test` draft probe; `voice_settings` column round-trip; `/voice/transcribe` proxy; `/voice/speak` SSE + default-voice resolution; `/voice/turn` full ASR→Ollama→TTS chain with persistence; 404 when no voice backend is configured. Run via `.venv/bin/python test_e2e.py`.

---

## Apps (groups of bots) and per-app SDK generation

A second top-level surface beside Bots: an **application** is a named group of bots (e.g. *"GA Probate"*) that can also emit a ready-to-use client SDK in TypeScript, JavaScript, or Python with each member bot wired in as a named function.

### Data model

A single **`apps`** table (`db.py:111-119`): `id`, `name`, `description`, `link`, `avatar` (data URL), `created_at`, `updated_at`. Bots belong to an app via a `conversations.app_id` column (additive migration in `init_db`), with `idx_conversations_app` for the per-app lookup. Assignment is one-to-many — a bot is in zero or one apps. Removing a bot from an app sets `app_id = NULL`; deleting the app does the same to its bots (the bots are not deleted).

### Endpoints (`app.py:1033-1209`)

CRUD on apps:
- `GET  /api/apps` — list apps with `bot_count`.
- `POST /api/apps` — create (`AppCreate`: name, description, link).
- `GET  /api/apps/{id}` — single app + its bots.
- `PATCH /api/apps/{id}` — update name / description / link.
- `DELETE /api/apps/{id}` — delete app; bots' `app_id` is set to NULL.
- `PUT/DELETE /api/apps/{id}/avatar` — same shape as the per-bot avatar endpoints.

Bot assignment:
- `POST /api/apps/{id}/bots` body `{conversation_id}` — assign a bot (reassigns from any previous app).
- `DELETE /api/apps/{id}/bots/{conv_id}` — clear `app_id` (404 if the bot wasn't in this app).

SDK generation:
- `GET /api/apps/{id}/sdk?lang=ts|js|py` — JSON preview: `{app, lang, files: [{path, content}]}`. `lang` defaults to `ts` (backwards-compat); unknown lang → 400.
- `GET /api/apps/{id}/sdk.zip?lang=…` — download as a zip. Filename keeps `<slug>-sdk.zip` for `ts` (no breakage); `js` / `py` use `<slug>-<lang>-sdk.zip` so all three can coexist in a downloads folder.

### `sdkgen.py` — the generator

Stdlib-only, with three parallel emitters dispatched by `generate_sdk(lang, app, bots, base_url)` (`SDK_LANGS = ("ts", "js", "py")`):

- **`generate_ts_sdk`** — typed TypeScript; per-bot `bots/<fn>.ts`, `client.ts`, `index.ts` barrel, `package.json`, `README.md`. Imports use the explicit `.js` extension (NodeNext/bundler-style).
- **`generate_js_sdk`** — same shape with types stripped; ESM `.js`. Runs in Node 18+ (native `fetch`) and modern browsers.
- **`generate_python_sdk`** — a stdlib-only Python package. Folder is `<py_slug>_sdk/` (underscores, so it's directly importable). Lays out `client.py`, `__init__.py` (re-exports + a `<bag>` dict of all bots), and `bots/<fn>.py` per bot. Snake-case function names via `function_names_python` (camelCase `function_names` is reused for TS/JS).

Identifiers are deduplicated on collision by appending the bot id, and reserved words are rejected (per-language `_RESERVED` / `_PY_RESERVED` sets). The server URL is baked into `client.{ts,js,py}` via a `__BASE_URL__` placeholder substituted at generation time.

### UI (`static/index.html`, `static/app.js`, `static/style.css`)

- **Apps page** (`body[data-page="apps"]`, `renderAppsPage`): grid of app cards (`_appsState.cache`) with filter, "New application" button, and a per-card **Generate SDK** action.
- **App detail** (`body[data-page="app-detail"]`, `renderAppDetail`): back-to-Apps button, the app's bot grid, plus a top-level Generate-SDK button. `_appsState.current` holds the open app.
- **SDK modal** (`#sdk-modal-backdrop`, `openSdkModal`): three-language tab strip (`.sdk-lang-tab[data-lang="ts|js|py"]`); each tab refetches `/sdk?lang=…` via `_loadSdkFiles()` and re-renders the file tree + preview. Download button targets `/sdk.zip?lang=…`. State carries `{ files, active, appId, appName, lang }`.
- **Context-aware back** (`enterChat()` / `exitChatToReturn()` in `app.js`): the chat view remembers which surface launched it (`state.chatReturnTo`), so back from a bot opened *inside* an app returns to that app's detail view — not the global Bots page. On Esc the same restore runs.

### Drop-in usage caveats

The generated SDKs are thin HTTP clients: they need a **reachable MiniClosedAI server**. The base URL is baked at generation time but overridable via `MINICLOSEDAI_BASE_URL` (Node `process.env` for JS/TS, `os.environ` for Python) or per-call `baseUrl` / `base_url`. Bot ids are pinned in the generated files — recreate a bot and you'll need to regenerate. The API ships with `allow_origins=["*"]` (in `app.py`) and no auth, so put a reverse proxy + auth in front before exposing port `8095` to the public internet.

---

## Knowledge base (RAG)

Each bot can have its own library of documents ("books") that it answers from. The design is deliberately zero-install: **SQLite is the vector store and Ollama supplies the embeddings** — there is no external vector database.

**Data model** (`db.py`): two tables, both keyed to `conversation_id` (logical FK, cleaned up in the conversation-delete handler):
- `kb_documents(id, conversation_id, filename, char_count, chunk_count, embed_model, created_at)`
- `kb_chunks(id, document_id, conversation_id, ordinal, text, embedding BLOB)` — the embedding is a packed little-endian float32 BLOB, L2-normalized at store time.

**Module** `knowledge.py` (stdlib only): `chunk_text` (≈1000-char windows, 150 overlap, prefers whitespace breaks), `pack_vector` / `unpack_vector` (struct), `normalize`, `dot`, `top_k` (brute-force cosine = dot over normalized vectors), `build_context_block`.

**Embeddings** `llm.embed(backend, model, texts)` — kind-agnostic: Ollama `POST /api/embed`, OpenAI-compat `POST /v1/embeddings`. Embeddings are a **local** concern: `_resolve_embed_backend()` routes them to the built-in/local Ollama (prefers `is_builtin`; override with `MINICLOSEDAI_EMBED_BACKEND_ID`), **not** the bot's chat backend. So a bot pinned to a cloud relay — which serves chat models but not `nomic-embed-text` — still embeds locally instead of 403-ing. The embedding model (`MINICLOSEDAI_EMBED_MODEL`, default `nomic-embed-text`) must be pulled on that local backend. Ingestion and retrieval use the **same** resolver, so chunks + queries are always embedded by the same model.

**Endpoints:**
- `POST /api/conversations/{id}/knowledge` — body `{filename, text}`. Chunks → embeds → stores. The frontend extracts text first (txt/md read in-browser, PDFs via `/api/extract-pdf?full=1` — book-friendly caps of 200 MB / 5000 pages / 5M chars vs. the 10 MB chat-attachment caps; see [Configuration](#configuration)), keeping this endpoint JSON-only. Embedding failure → 502 with a "pull the embedding model" hint.
- `GET /api/conversations/{id}/knowledge` — list documents (no chunk text).
- `DELETE /api/conversations/{id}/knowledge/{doc_id}` — drop a document + its chunks.

**Retrieval** happens in `_augment_messages_with_knowledge`, called from both conv-chat handlers. It embeds the query on the **local embed backend** (same resolver as ingestion, so chunks + query share one model even when the bot chats through a relay). Only the single-`message` form is augmented (same rule as `include_history`). It runs balanced retrieval (`top_k_balanced`, default `MINICLOSEDAI_KB_TOP_K=8`) over this bot's chunks — capping each document to ~`ceil(k/num_docs)` slots so one huge/noisy book can't monopolize the context — and prepends a `## Knowledge base excerpts` block to the system message. **Best-effort**: any failure (model not pulled, backend down) is swallowed so a knowledge hiccup never blocks a normal chat turn.

---

## Extensibility — MCP plugins

MiniClosedAI is a **host/client** for the [Model Context Protocol](https://modelcontextprotocol.io). A bot is configured with remote MCP server URLs; on a chat turn the model can call those servers' tools. "Writing a plugin" means writing (or pointing at) an MCP server — there's no MiniClosedAI-specific plugin format, and you inherit the existing MCP ecosystem.

**Config** lives in a `conversations.mcp_servers` JSON column (additive migration) — a list of `{name, url, enabled}`. Endpoints:
- `GET /api/conversations/{id}/mcp` — current servers.
- `PUT /api/conversations/{id}/mcp` — replace the list.
- `POST /api/conversations/{id}/mcp/test` — connect to a URL and return its tool names (used by the "Add" UI to validate before saving).

**Module** `mcp_host.py` (uses the official `mcp` SDK, Streamable HTTP transport): `list_tools(url)`, `call_tool(url, headers, name, args)`, and `gather_tools(servers)` which merges tools across enabled servers into OpenAI tool specs + a `name → server` routing map (first server wins on a name collision; unreachable servers are skipped). **Remote-only, stateless** (connect per operation) for v1 simplicity — no local stdio subprocesses.

**Tool-calling** `llm.chat_with_tools(...)` is a non-streaming call (Ollama `/api/chat` and OpenAI `/v1/chat/completions`, both `stream:false`, with `tools`) returning a normalized `{assistant_message, tool_calls:[{id,name,arguments}], content}`. `llm.tool_result_message(...)` builds the per-kind `role:"tool"` turn.

**The loop** `_run_mcp_tool_loop` runs `model → (execute tool calls via MCP) → model → …` up to `MINICLOSEDAI_MCP_MAX_ITERS` (default 6) rounds, then returns the final text. Tool errors are fed back to the model as text so it can recover. Wired into both conv-chat handlers when the bot has enabled servers + the single-`message` form. Because tool calling is request/response (not streamable), the **streaming** endpoint runs the loop and emits the final answer as a single SSE chunk + `end`, preserving the frontend's contract.

**Requirements / caveats:** needs a tool-calling-capable model (qwen3, llama3.x, mistral; not 1-bit Bonsai-class). Connecting to a remote MCP server runs code on that server — opt-in, per-bot, remote-first by design.

### Writing a plugin (example server)

The easiest way to write a plugin is **FastMCP**, bundled with the `mcp` SDK (already in `requirements.txt`). A runnable example ships at [`docs/examples/mcp_server/server.py`](./docs/examples/mcp_server/server.py):

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-tools", host="127.0.0.1", port=8765)

@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b

if __name__ == "__main__":
    mcp.run(transport="streamable-http")   # MUST be streamable-http
```

Run it (`python docs/examples/mcp_server/server.py`), then add `http://localhost:8765/mcp` in a bot's **Extensions** panel. The function's type hints + docstring *are* the tool schema — no separate spec. The mount path is always `/mcp`; the transport must be `streamable-http` (stdio servers aren't reachable by the host's `streamablehttp_client`).

**Verified live:** with this example server + a `qwen3:8b` bot, MiniClosedAI lists the three tools, and asking "what's the weather in Reykjavik?" triggers a real `CallToolRequest` and the bot answers using the tool's returned value — confirming the full host → model → tool → model loop.

---

## Evaluation & auto-improve (scoring)

Bots are often fixed-response (classifiers / routers / extractors). The eval system lets you measure a bot's accuracy against a set of test cases and then auto-tune its system prompt against the failures — turning blind prompt-editing into a measure → improve → re-measure loop.

**Data model** (`db.py`): one table, mirroring the knowledge pattern.
- `eval_cases(id, conversation_id, input, expected, created_at)` — keyed to the bot by `conversation_id` (logical FK). Cleaned up in the conversation-delete handler (alongside the kb tables). Scores are computed on demand, never stored.

**Scoring module** `evals.py` (stdlib): `normalize()` (trim + lowercase + collapse whitespace), `score_exact` / `score_contains`, and the LLM-judge helpers `build_judge_messages(input, expected, reply)` + `parse_judge(text)` (YES/NO).

**Endpoints** (app.py):
- `POST /api/conversations/{id}/eval/cases` — bulk add `{cases:[{input,expected}]}`.
- `GET /api/conversations/{id}/eval/cases` — list.
- `DELETE .../eval/cases/{case_id}` and `DELETE .../eval/cases` — remove one / clear all.
- `POST .../eval/seed` — turn the bot's saved chat history into cases (reuses `_iter_pairs` / `_content_text_for_export`, the same pair extraction as the CSV export).
- `POST .../eval/run` — body `{mode, judge_backend_id?, judge_model?}`. For each case, runs the bot via **`_run_conv_message`** (a one-shot, no-history, no-log helper extracted from `api_conv_chat`, so scoring exercises the bot's *real* path — knowledge + MCP + relay all apply), then scores by `mode`:
  - `exact` — normalized equality (default; best for fixed-response bots).
  - `contains` — normalized expected is a substring of the reply.
  - `judge` — calls `llm.chat(judge_backend, judge_model, build_judge_messages(...))` and parses YES/NO. The grader model is supplied by the frontend from the user's Prompt-Generator choice; a 400 is returned if `judge_model` is missing.
  - Returns `{mode, total, passed, accuracy, results:[{case_id, input, expected, got, passed}]}`.

**Frontend** mirrors the Knowledge/Extensions surfaces — a sidebar **Evals** panel (case count + "Manage evals") and an **Evals modal** (`eval-modal-backdrop`) with: add-case row, **Seed from history** + **Upload CSV** + **Clear all**, the case list, a scoring-mode selector + **Run** (per-case pass/fail + accuracy %), and the **Auto-improve** controls (target %, max iters, Start). A 📊 bot-card action opens the modal too. Functions: `loadEvals`, `openEvalModal`, `_loadEvalModal`, `runEvals`, `autoImproveLoop`, `initEvalsUI`, `initEvalModalUI`.

**Auto-improve loop** (`autoImproveLoop`, client-side, in the modal):
```
for i in range(maxIters):
    res = await runEvals(mode)                  // POST /eval/run (scores server-side)
    record {accuracy, prompt: systemPromptTextarea.value}; track best
    if res.accuracy >= target: break
    summary = failing cases → "INPUT / EXPECTED / GOT" lines
    await _runPromptGeneration(summary)         // reuses the existing Improve-prompt flow → streams a new prompt into #system-prompt
    await flushPendingSave()                     // persist so the next run scores the new prompt
restore the best-scoring prompt + persist; show the score history
```
The loop is **orchestrated client-side** specifically so the improve meta-prompt stays single-sourced in the existing prompt-generator code (`_runPromptGeneration` / `_PROMPT_IMPROVE_META_PROMPT`) rather than being duplicated server-side. Judge mode + auto-improve require a Prompt-Generator model (Settings → Prompt Generator).

**Verified live** with `qwen3:8b`: a sentiment classifier scored 100% (exact) on a clean 4-case set, dropped to 80% when a deliberately-wrong expected was added, and judge mode graded the same set; deleting the bot cascaded its eval cases away.

---

## Worked example — connecting Bonsai (1-bit 8B)

This section walks through registering **[PrismML's Bonsai-8B](https://github.com/PrismML-Eng/Bonsai-demo)** — a 1-bit quantized 8-billion-parameter model that runs at ~1.15 GB on disk — as an endpoint. It's a good end-to-end illustration of how the multi-backend architecture handles anything that exposes the OpenAI-compat `/v1` surface.

### Why Bonsai

Bonsai is an extreme-quantization experiment from [PrismML](https://prismml.com). A full-precision 8B LLM weighs ~16 GB; aggressive 4-bit quantization brings that to ~5 GB. Bonsai quantizes to true **1-bit** weights (~1.15 GB), and the PrismML whitepaper reports ~70.5% average on standard benchmarks — within striking distance of full-precision baselines. The model is served through the standard `llama.cpp --server` binary, which exposes the OpenAI-compat REST shape natively. From MiniClosedAI's point of view, it's just another OpenAI-kind endpoint.

**Why it's a strong default for microservice bots.** MiniClosedAI's core idea is that each saved conversation is a callable API endpoint — you write a system prompt once, then pound it with programmatic requests from downstream code. That workload profile (many short, structured completions; latency matters more than nuance) is almost the opposite of an interactive chat session. Bonsai's tiny weight footprint plus GPU-offloaded llama.cpp inference means first-token latency and sustained throughput are both substantially better than a dense 7B/8B on Ollama, while factual capability stays high enough for classification, JSON extraction, routing, and sentiment work. Pair it with a strict `temperature ≤ 0.2` + "respond with only X" system prompt and you have a production-grade microservice bot on a laptop. See the [Recommended models table in README](./README.md#recommended-models-1b10b) for the side-by-side comparison against Ollama models.

**Where Bonsai is NOT a good fit.** 1-bit quantization weakens conditional multi-rule instruction-following. For bots whose output format has *branches* — natural prose on some turns, natural prose PLUS a fenced JSON action block on others — Bonsai matches the tone of the in-prompt examples but tends to drop the structural JSON emission. Verified live on the [Doctor's Office Bot](./docs/recipes/Doctors%20Office%20Bot.md): with an identical few-shot-patched prompt, `qwen3:8b` emits the `create_appointment` / `urgent_redirect_911` / `transfer_to_human` actions reliably; Bonsai skips them and claims to have "scheduled" an appointment without the JSON — which means no event fires downstream, a dangerous silent failure mode.

**Rule of thumb:** count the branches in your output format. Always-JSON or always-prose → Bonsai is the fast pick. Prose-sometimes-with-JSON → full-precision 7-9B. MiniClosedAI's multi-backend design exists precisely so you can use both in the same app — Bonsai for the RAG Query Router, `qwen3:8b` for the Doctor's Office Bot, both callable from the same `/api/conversations/{id}/chat` URL base.

**Reference links:**
- Demo scripts + pre-built GGUF models: [github.com/PrismML-Eng/Bonsai-demo](https://github.com/PrismML-Eng/Bonsai-demo)
- PrismML (team): [prismml.com](https://prismml.com)
- Whitepaper: `1-bit-bonsai-8b-whitepaper.pdf` in the demo repo
- Runtime: [llama.cpp](https://github.com/ggerganov/llama.cpp)

### Install + boot the Bonsai server

```bash
git clone https://github.com/PrismML-Eng/Bonsai-demo.git
cd Bonsai-demo
./setup.sh                             # builds llama.cpp + downloads Bonsai-8B.gguf

./scripts/start_llama_server.sh        # serves at http://localhost:8080
# Model-size switch:
BONSAI_MODEL=4B ./scripts/start_llama_server.sh
# Valid values: 8B (default), 4B, 1.7B
```

The server's canonical endpoints once running:

| Path | Purpose |
|---|---|
| `GET  http://localhost:8080/health` | Readiness probe — MiniClosedAI's **Test connection** calls this equivalent path. |
| `GET  http://localhost:8080/v1/models` | Lists the loaded model(s). Only one at a time. |
| `POST http://localhost:8080/v1/chat/completions` | OpenAI-compatible chat. Streaming + non-streaming both supported. |

`start_llama_server.sh` boots llama.cpp with these pre-set flags (source-of-truth is the script itself):

```
-ngl 99                               # offload everything to GPU
-c 0                                  # auto-fit context (Bonsai-8B trained at 65536)
--temp 0.5 --top-p 0.85 --top-k 20 --min-p 0
--reasoning-budget 0
--reasoning-format none
--chat-template-kwargs '{"enable_thinking": false}'
```

The `--reasoning-*` flags matter because Bonsai uses a Qwen3-family chat template — without them the server would try to emit `<think>` blocks even though Bonsai itself is distilled to a non-reasoning regime.

### Register the endpoint

In MiniClosedAI → **Settings** (gear icon, bottom of activity bar) → **+ Add endpoint**:

```
Name:     Bonsai
Kind:     OpenAI-compatible
Base URL: http://localhost:8080/v1         ← not 8095; see pitfall below
API key:  (blank — llama.cpp doesn't auth by default)
Headers:  (blank)
```

Click **Test connection** → expect *"✓ Reachable · 1 model(s)"*, listing `Bonsai-8B.gguf`. Save.

Internally MiniClosedAI persists the backend in the `backends` SQLite table with `kind='openai'` and `base_url='http://localhost:8080/v1'`. The client dispatcher in `llm.py` picks the OpenAI code path for this backend on every request, so streaming, non-streaming, reasoning-field mapping, error translation, and the `Cache-Control: no-cache` / `X-Accel-Buffering: no` proxy headers all apply uniformly.

### Chatting with Bonsai

Back on the Dashboard:

1. The model dropdown has a new `Bonsai` optgroup; its option is `Bonsai-8B.gguf`.
2. Create a new chat (➕ icon) → pick `Bonsai-8B.gguf` → name it → the conversation persists with `(backend_id=<Bonsai's id>, model="Bonsai-8B.gguf")`.
3. Every subsequent turn routes to `http://localhost:8080/v1/chat/completions` because that pair is locked server-side.

The microservice pattern applies unchanged: `POST /api/conversations/{id}/chat` is now a stable Bonsai-backed endpoint, and the API Code modal emits cURL / Python / JavaScript snippets that call it. The downstream caller never knows the bot is 1-bit — MiniClosedAI's `extra="forbid"` guard rails on `ConversationChatRequest` make the bot's config immutable from the caller's side.

**Concrete recipe designed for Bonsai's speed profile:** **[`RAG Query Router.md`](./docs/recipes/RAG%20Query%20Router.md)** — a latency-critical query classifier that runs in front of a retrieval-augmented QA pipeline. Every inbound user question hits the router first (~200 ms on Bonsai), which decides whether to hit a cache, fire a fast LLM-only reply, run light or deep RAG, or ask a clarifying question. Temperature `0.0` for pure greedy decoding; reproducible. Includes full system prompt with few-shot examples, Python `match/case` dispatcher, worked input/output, and five variant archetypes.

### Bonsai-specific gotchas

- **Thinking control.** Leave MiniClosedAI's Thinking slider on `Default` or `Off`. The server booted with `enable_thinking=false` and `--reasoning-budget 0`, so any reasoning signal MiniClosedAI sends is ignored. Setting Thinking to `On` costs tokens but produces no useful `<think>` content.
- **Sampling.** The server's defaults (temp `0.5`, top-p `0.85`, top-k `20`) are per-session seeds; the per-conversation sliders override them on every `/v1/chat/completions` call. Tune as usual.
- **Only one model loaded at a time.** `llama.cpp --server` can serve exactly one GGUF. If you want multiple Bonsai sizes side by side, register each one as a separate endpoint on a different port (`start_llama_server.sh` uses `PORT=8080` hardcoded — patch it or pass `--port 8081` to llama-server directly) and add each to MiniClosedAI's Settings.
- **aarch64 / ARM.** The pre-built `llama-server` binary is x86_64. Build from source first: `./scripts/build_cuda_linux.sh` (Linux + NVIDIA) or `./scripts/build_mac.sh` (macOS + Metal).
- **Shutdown.** `kill $(lsof -ti TCP:8080)`.

### Pitfall: loopback via the wrong port

If the Base URL is set to `http://localhost:8095/v1` instead of `8080/v1`, the endpoint ends up pointing at **MiniClosedAI itself**. MiniClosedAI's own `/v1/models` implementation returns **saved conversation IDs as model names** (so the OpenAI SDK can address each bot as a "model"), which means:

- The Bonsai optgroup in the model dropdown will be populated with numeric strings (`"30"`, `"31"`, …) — each one is actually the ID of a pre-existing conversation, not a real Bonsai model.
- Picking one and sending a message creates an infinite-looking routing loop: MiniClosedAI → (misconfigured Bonsai endpoint) → `http://localhost:8095/v1/chat/completions` → MiniClosedAI receives the request → routes to the conversation with that ID → Ollama answers with *that* bot's system prompt and model.
- Concretely, the user reported sending "Hello" to a fresh Bonsai chat and receiving a Lead Qualifier JSON back — because the stale "model" was `"30"`, the Inbound Lead Qualifier's conversation ID.

**Fix:** edit the Bonsai endpoint, change the port to `8080`, Test connection (should now list one real model file), Save, reopen the Bonsai chat, and reselect `Bonsai-8B.gguf` from the dropdown. Clear the bad turn with the broom icon before asking again.

### How this slots into the architecture

Nothing in MiniClosedAI's core is Bonsai-specific. The integration reuses:

- `backends` table (append-only row, no schema change)
- OpenAI client in `llm.py` (same code path as LM Studio, vLLM, or real OpenAI)
- Conversation persistence, edit-message endpoint, CSV export, fine-tuning curation flow — all identical
- `/v1/chat/completions` and `/v1/models` on MiniClosedAI's side, so OpenAI-SDK callers against MiniClosedAI never know Bonsai is downstream

That's the point of the OpenWebUI-style multi-endpoint design: adding a new backend is a data change, not a code change.

---

## Per-chat microservice pattern

Each conversation is a **self-contained, addressable configuration**. Once saved, it has a stable URL:

```
POST /api/conversations/{id}/chat         # non-streaming, JSON response
POST /api/conversations/{id}/chat/stream  # SSE streaming
```

The caller sends only the message (everything else is stored server-side):

```bash
curl -X POST http://localhost:8095/api/conversations/3/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

Response:

```json
{
  "response": "Hello! How can I help?",
  "conversation_id": 3,
  "model": "llama3.2:3b",
  "persisted": false
}
```

### Override any field per call

```json
{
  "message": "Draft a one-sentence summary.",
  "temperature": 0.2,
  "max_tokens": 50,
  "think": "low",
  "system_prompt": "You summarize concisely.",
  "persist": true
}
```

- `persist: true` appends this turn to the saved conversation history (useful for multi-turn clients).
- `persist: false` (default) = stateless call, no DB write, each call fully independent.
- `include_history: true` — **only valid with the single-`message` form.** Tells the server to prepend the conversation's saved turns to the LLM context before calling the model. Defaults to `false` so classifier / router bots keep pure-function semantics (every call independent). Set it to `true` for conversational bots (FAQ chat, [Doctor's Office Bot](./docs/recipes/Doctors%20Office%20Bot.md), support agents) that need memory across turns. The MiniClosedAI browser UI sets it to `true` automatically on every Send. Callers who use the multi-turn `messages=[...]` form own the history themselves and should leave this flag false.

### Multi-turn payload

Instead of a single `message` string, send a full `messages` array:

```json
{
  "messages": [
    {"role": "user", "content": "What's the capital of France?"},
    {"role": "assistant", "content": "Paris."},
    {"role": "user", "content": "And its population?"}
  ]
}
```

### Why this is useful

- **One system prompt = one microservice.** Craft a focused prompt (JSON extractor, sentiment classifier, resume parser), save it as a chat, and call it from anywhere with a 1-line payload.
- **No redeploys.** Change the prompt in the UI, and the next call uses the new behavior.
- **Multiple specialized endpoints.** Create as many chats as you want — each is independent.
- **Deterministic.** Set temperature low, think off, and you've got a reproducible API.

### Production-grade recipes

Seven full, copy-paste walkthroughs live alongside this doc. Each is a standalone `.md` file with the exact system prompt, recommended sampling settings, worked input/output examples, Python + cURL + OpenAI-SDK integration code, and variant ideas:

| Recipe | File | Workload profile | Best backend |
|---|---|---|---|
| **Support Ticket Router** | [`Support Ticket Router.md`](./docs/recipes/Support%20Ticket%20Router.md) | Classify inbound support messages → Zendesk/Linear routing. One-shot JSON per ticket. | `qwen3:8b` on Ollama (Bonsai also works) |
| **Inbound Lead Qualifier** | [`Inbound Lead Qualifier.md`](./docs/recipes/Inbound%20Lead%20Qualifier.md) | Score B2B prospects (fit_score 0–100, intent, role, budget/timeline signals) → CRM routing. | `qwen3:8b` on Ollama (Bonsai also works) |
| **RAG Query Router** | [`RAG Query Router.md`](./docs/recipes/RAG%20Query%20Router.md) | Latency-critical pre-router for retrieval-augmented QA. Classifies every user query; decides cache/fast-LLM/light-RAG/deep-RAG/ask-clarification. | **Bonsai-8B** on llama.cpp (port 8080) — ~200 ms per call; see [Worked example — connecting Bonsai](#worked-example--connecting-bonsai-1-bit-8b). |
| **Doctor's Office Bot** | [`Doctors Office Bot.md`](./docs/recipes/Doctors%20Office%20Bot.md) | Conversational front-of-house chatbot for a primary-care practice. FAQs + multi-turn appointment booking + red-flag symptom → 911 redirect + refill routing. Emits fenced JSON action blocks on action-triggering turns only. | `qwen3:8b` on Ollama. **Not Bonsai** — mixed-mode output (prose + conditional JSON) exceeds 1-bit instruction-following reliability; verified live. |
| **Restaurant Reservations Bot** | [`Restaurant Reservations Bot.md`](./docs/recipes/Restaurant%20Reservations%20Bot.md) | Conversational host-stand chatbot for a sit-down restaurant. FAQs + multi-turn reservation booking/modify/cancel + large-party (9+) → events team override + allergy flags for the kitchen. Same dual-mode output as Doctor's Office Bot, with hardened pre-confirmation checklist + explicit-affirmative-trigger rule + four negative-path few-shots. | `qwen3:8b` on Ollama. Same not-Bonsai rationale as Doctor's Office Bot. |
| **Hotel Reservations Bot** | [`Hotel Reservations Bot.md`](./docs/recipes/Hotel%20Reservations%20Bot.md) | Conversational reservations chatbot for a boutique hotel. FAQs + multi-turn booking/modify/cancel of any length + group-block (5+ rooms) → sales-team override + hard-refuse on card numbers in chat. Dual-mode output, hardened pre-confirmation checklist + explicit-affirmative-trigger rule + five negative-path few-shots (incl. a long-stay-books-normally example). Stay length is **not** a routing trigger. | `qwen3:8b` on Ollama. |
| **Dentist Appointment Bot** | [`Dentist Appointment Bot.md`](./docs/recipes/Dentist%20Appointment%20Bot.md) | Conversational front-of-house chatbot for a general-dentistry practice. FAQs + multi-turn booking/reschedule/cancel + two-tier emergency routing (911 for airway/spreading-infection signs vs. on-call dentist for time-critical dental emergencies). Dual-mode output, hardened pre-confirmation checklist + explicit-affirmative-trigger rule + three negative-path few-shots. | `qwen3:8b` on Ollama. |

All seven share the same archetype — *small structured decision (or action), driven by a focused system prompt, called as an HTTP microservice* — but differ in where they sit in the pipeline:

- **End-state record** (Ticket Router, Lead Qualifier) — one-shot classification per call, same JSON schema every time.
- **Intermediate orchestration decision** (RAG Query Router) — one-shot decision about where to route an incoming request; every output is JSON.
- **Conversational agent with side-effecting actions** (Doctor's Office, Restaurant Reservations, Hotel Reservations, Dentist Appointment) — multi-turn state, dual-mode output, fenced JSON action block on a subset of turns. The four conversational recipes share a deliberately identical skeleton: a `=== BEGIN/END FACTS ===` block as the only source of truth for FAQs, hard-override branches (911 / events team / sales team / on-call), action-emission gates, and load-bearing few-shot examples at the bottom of the system prompt covering both the **happy path** (one example per action that fires) and the **negative path** (one example per common refusal — invalid provider/room/seating, time outside hours, missing required field). The Restaurant, Hotel, and Dentist recipes also include an explicit **pre-confirmation checklist** the model runs silently before any `create_*` action, with two failure modes worth calling out specifically:

  - **Hallucinated facts.** Without explicit "must match the facts block" rules, `qwen3:8b` at T=0.3 will accept a made-up provider name ("Dr. Kamata") or invented room type ("Presidential Suite") and confirm a booking against it. The checklist's first item in each recipe is a literal name/value match against the facts block.
  - **Premature confirmation.** Without an **explicit affirmative trigger** rule (`yes` / `I confirm` / `book it` / `go ahead` / `lock it in` / `sounds good` / `do it` / `that works`), the model treats answers to its own follow-up questions ("no allergies", "no special requests", "no need for accessibility") as green lights and emits "you're set" prose without the JSON action block — a silent failure where downstream systems see no event to dispatch. The trigger rule + a "partial gather, no trigger" few-shot example fix this on all three patched recipes.

  The Doctor's Office Bot pre-dates the hardening and uses the older three-example (booking / red-flag / FAQ-out-of-scope) form. Pick whichever recipe is closest to your domain and edit the facts block.

Study all seven before authoring a new one; the similarities show you which patterns are reusable and the differences show you which knobs actually matter for your workload. **Rule of thumb for picking a model:** if output is always JSON (single-mode), Bonsai 1-bit is often the best pick for latency. If output is prose sometimes and JSON sometimes (multi-mode), use a full-precision 7–9B.

---

## API reference

All routes return JSON unless otherwise noted. Interactive docs at `http://localhost:8095/docs`.

### `GET /api/models`

Lists Ollama models available locally.

```json
{
  "ollama_running": true,
  "models": [
    {"name": "llama3.2:3b", "size": 2019393189, "details": {"parameter_size": "3.2B", "...": "..."}}
  ]
}
```

### Backends

```
GET    /api/backends                              → list all (api_key scrubbed to api_key_set bool)
POST   /api/backends                              → create. Strip trailing /, normalize URL.
PATCH  /api/backends/{id}                         → update (kind is immutable)
DELETE /api/backends/{id}                         → 403 on is_builtin, 409 if bound to chats
DELETE /api/backends/{id}?force=true              → cascade-delete: removes backend + every bound bot in one tx
GET    /api/backends/{id}/models                  → list that backend's models only
GET    /api/backends/{id}/status                  → reachability probe (running, kind, model count)
POST   /api/backends/test                         → probe a draft config without saving
POST   /api/backends/{id}/pull                    → start a streaming model pull on Ollama backends
GET    /api/pulls                                 → poll progress for all in-flight pulls
DELETE /api/backends/{id}/pulls/{name:path}       → cancel an in-flight pull
```

**Delete semantics**:

- The built-in row (`is_builtin=1`, default `id=1`) is undeletable — 403 fires *before* the bound-bots check, regardless of `?force=true`. This protects lite-mode users from ending up with zero Ollama rows by accident.
- Default delete refuses (409) when any conversation has `backend_id = <this id>`. The body's `detail.bound_conversations` lists `[{id, title}, …]` so the GUI can offer to rebind those bots.
- `?force=true` skips the 409 and runs `DELETE FROM conversations WHERE backend_id = ?` in the same transaction as the backend delete. Response includes `deleted_conversations: <count>` so callers can confirm what was wiped. Used by the Settings GUI's two-step cascade-confirm dialog.

**Why the GUI gates with two confirms**: the data being wiped (whole bots, full message history, attachments) is high-value. The first dialog names the bots and recommends rebinding instead; the second dialog gates the actual destructive call. Single-click confirm would be a too-easy regret-trigger for what's effectively `DROP TABLE … CASCADE`.

### Conversations

```
GET    /api/conversations                         → list all
POST   /api/conversations                         → create
GET    /api/conversations/{id}                    → get full conversation (including messages)
PATCH  /api/conversations/{id}                    → update any subset of fields
DELETE /api/conversations/{id}                    → delete
POST   /api/conversations/{id}/clear              → wipe messages, keep config
PATCH  /api/conversations/{id}/messages/{index}   → edit one stored message in place
GET    /api/conversations/{id}/export.csv             → text-only SFT CSV (input,output)
GET    /api/conversations/{id}/export.zip             → multimodal SFT bundle (JSONL + images)
GET    /api/conversations/{id}/export.classify.zip    → image-classification dataset (image,label CSV + images/)
GET    /api/conversations/{id}/export                 → portable bot config (.miniclosed-bot.json)
POST   /api/conversations/import                      → import a .miniclosed-bot.json file
```

**Create body**:

```json
{
  "title": "Info extractor",
  "model": "qwen2.5:7b",
  "system_prompt": "You extract structured JSON.",
  "temperature": 0.1,
  "max_tokens": 1024,
  "top_p": 0.9,
  "top_k": 40,
  "think": "off",
  "max_thinking_tokens": 200
}
```

**Get response**:

```json
{
  "id": 3,
  "title": "Info extractor",
  "model": "qwen2.5:7b",
  "system_prompt": "...",
  "messages": [ {"role": "user", "content": "...", "params": {...}}, ... ],
  "params": {"temperature": 0.1, "max_tokens": 1024, "top_p": 0.9, "top_k": 40, "think": false, "max_thinking_tokens": 200},
  "created_at": "2026-04-14 01:23:45",
  "updated_at": "2026-04-14 01:24:10"
}
```

**PATCH**: supply any subset of the same fields. Param fields merge into the saved JSON (other saved params are preserved).

**Edit a single message** — `PATCH /api/conversations/{id}/messages/{index}`. Body: `{"content": "<new text>"}`; any extra key returns **422**. The first edit of a message copies the existing content to `original_content` and stamps `edited: true` + an ISO-8601 `edited_at`. Subsequent edits only update `content`; `original_content` remains pinned to the pristine model output. Returns the full updated conversation. 404 when the conversation is missing or `index` is out of range.

**Export as CSV** — `GET /api/conversations/{id}/export.csv`. Returns `text/csv` with a `Content-Disposition: attachment` header so the browser saves it directly. Columns are `input,output`; one row per complete user→assistant pair; RFC-4180 quoted; leading/trailing whitespace stripped from both columns; orphan user messages (no reply yet) are skipped. Full details in [Fine-tuning data export](#fine-tuning-data-export).

### Chat

```
POST /api/conversations/{id}/chat          → non-streaming; response as JSON
POST /api/conversations/{id}/chat/stream   → SSE streaming
POST /api/chat                             → (legacy) non-streaming, no conversation_id required
POST /api/chat/stream                      → (legacy) streaming, no conversation_id required
```

The per-conversation variants use the saved config as defaults. The legacy ones require the full config in the request body.

Optional fields on the per-conversation variants: `include_history: bool` (single-`message` form only — replays saved turns into context) and `attachments: [{name, kind, ...}]` (single-`message` form only — see [File attachments](#file-attachments-images-pdfs-text-files) for the full spec). The `messages=[…]` form must include any multimodal content arrays in-line itself.

### File extraction

```
POST /api/extract-pdf       → multipart/form-data, field name `file`
```

Server-side wrapper around `pypdf` for PDF text extraction. Caps: 10 MB raw, 50 pages, 30 000 chars output. Returns `{filename, page_count, char_count, truncated, text}`. The frontend uses this transparently when a `.pdf` is dropped in the paperclip picker; external callers can use it directly to populate the `text` field of a `pdf`-kind attachment before chatting.

### Activity logs

```
GET    /api/logs                    → newest-first list of chat-call records
GET    /api/logs?since_id=N         → only entries with id > N
GET    /api/logs?limit=M            → cap to M entries
DELETE /api/logs                    → wipe the buffer
```

Read-only listing of recent chat calls — backs the GUI's [Logs page](#logs-page) and the [Activity logs](#activity-logs) architecture section. Entry shape and buffer semantics documented there.

### SSE event format

Every streamed frame is of the form `data: <json>\n\n`:

| Event | Shape |
|---|---|
| content chunk | `{"chunk": "text"}` |
| thinking chunk (reasoning models) | `{"thinking": "text"}` |
| auto-stop notice | `{"thinking_truncated": true, "reason": "max_thinking_tokens", "limit": 200}` |
| server error | `{"error": "message"}` |
| terminator | `{"end": true, "truncated": false}` |

Client-side consumption sample (JavaScript):

```js
const res = await fetch(url, { method: "POST", body: JSON.stringify({message: "hi"}) });
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buf = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const parts = buf.split("\n\n");
  buf = parts.pop();
  for (const part of parts) {
    if (!part.startsWith("data:")) continue;
    const evt = JSON.parse(part.slice(5).trim());
    if (evt.chunk) process.stdout.write(evt.chunk);
    if (evt.end) return;
  }
}
```

---

## Thinking / reasoning control

Newer reasoning-tuned models (qwen3 / qwen3.5 families, deepseek-r1, gpt-oss, glm-4.7-flash, etc.) produce internal reasoning tokens before answering. MiniClosedAI exposes this as the **`think`** field.

| Value | Ollama payload | Effect |
|---|---|---|
| (unset / `null`) | `think` omitted | Model default (qwen3.5 always thinks; llava/llama3.2 never do) |
| `false` | `"think": false` | Suppress thinking output |
| `true` | `"think": true` | Enable thinking |
| `"low"` | `"think": "low"` | Low reasoning effort (gpt-oss family) |
| `"medium"` | `"think": "medium"` | Medium effort |
| `"high"` | `"think": "high"` | High effort |

Saved per conversation; overridable per call. Models that don't support the field ignore it.

In the UI, "thinking" tokens stream into a separate collapsible block so you can see the reasoning without it polluting the final answer.

---

## File attachments (images, PDFs, text files)

### Supported types

The composer's paperclip button (and clipboard paste) accepts one mixed file picker covering three categories:

| Category | File types | Where the bytes go |
|---|---|---|
| **Images** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp` | Base64-encoded in the browser. Auto-downscaled to 2048 px longest edge (JPEG quality 0.92) when larger. Sent to the model as native multimodal input. |
| **PDFs** | `.pdf` | Uploaded to `POST /api/extract-pdf`; server runs `pypdf` to extract plain text. Caps: 10 MB raw, 50 pages, 30 000 chars. Output is prepended to the user's message. |
| **Plain text & source code** | `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.toml`, `.xml`, `.html`, `.css`, `.js`, `.ts`, `.tsx`, `.jsx`, `.py`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.h`, `.sh`, `.sql`, `.log`, plus anything whose MIME starts with `text/` | Read in the browser via `FileReader.readAsText`, prepended to the user's message. |

Per-file cap is 10 MB raw; multiple attachments per message are allowed and may freely mix the three kinds. Sending images while the selected model isn't pattern-recognized as vision-capable triggers a soft-warn banner — the request still goes through, the warning just flags that the reply may ignore the image.

### Wire-format translation

Internal storage uses the OpenAI content-array shape:

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "[Attached: notes.pdf]\n<extracted body>\n\nWhat does this say?"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ],
  "display_text": "What does this say?",
  "attachments": [
    {"name": "notes.pdf", "kind": "pdf", "page_count": 12, "char_count": 4218},
    {"name": "diagram.png", "kind": "image", "mime": "image/png"}
  ]
}
```

Outbound translation per backend kind happens inside `llm.py`:

| Backend kind | Endpoint | Translation |
|---|---|---|
| `ollama` | `POST /api/chat` | Each multimodal message is rewritten by `_to_ollama_message`: text parts get joined into `content`, every `image_url` part has its `data:` prefix stripped and the raw base64 collected into a top-level `images: [...]` array. String-content messages pass through unchanged. |
| `openai` | `POST /v1/chat/completions` | Content arrays are forwarded as-is — LM Studio, vLLM, and Ollama's own `/v1` shim all accept the OpenAI multimodal shape. |

`display_text` and `attachments` are UI-only metadata: stripped from outbound LLM requests by `_resolve_conversation_chat`, then re-attached on persistence so reloading a conversation reconstructs the original chat-bubble layout.

For copy-paste curl / Python / JavaScript callers, see [README — Sending file attachments](./README.md#sending-file-attachments).

### Vision-model heuristic

Neither Ollama's `/api/tags` nor OpenAI's `/v1/models` exposes a clean "is multimodal" flag. The frontend matches model names against this regex set to decide whether to soft-warn on image attachments:

```
/^llava/i, /-vision/i, /vl[:-]/i, /qwen.*vl/i, /qwen3\.6/i,
/^gemma4/i, /llama3\.2-vision/i, /minicpm-?v/i, /pixtral/i, /moondream/i
```

Edit `VISION_MODEL_PATTERNS` in `static/app.js` to extend it. The check is purely cosmetic — the request payload is identical either way.

### Auth on remote/relayed Ollama backends

Both backend kinds now thread `api_key` (sent as `Authorization: Bearer …`) and any custom `headers` dict through every HTTP call, including `/api/tags`, `/api/chat`, and `/api/pull`. This lets you register a public-IP Ollama (e.g. an authenticating relay sitting in front of `localhost:11434`) as `kind=ollama` and still hit the native `/api/chat` endpoint — which is the only one that honors `"think": false` properly for Qwen3-family models.

The canonical real-world example of this pattern is [Interdata Lab](https://interdataresearch.ai), which runs Ollama deployments on cloud GPUs and exposes them at `https://app.interdataresearch.ai` with per-account API keys. Same wire format as a localhost Ollama, just a Bearer token added to every request via `_ollama_headers()`. See [Worked example — connecting Interdata Lab](#worked-example--connecting-interdata-lab-cloud-gpu) below for the registration walkthrough; the auto-route override and pull denylist (next subsection) both special-case `app.interdataresearch*` because of this integration.

### Model pulls and the relay denylist

```
POST /api/backends/{backend_id}/pull         → start a streaming pull
GET  /api/pulls                              → poll progress for all in-flight pulls
```

Body for the start call: `{"name": "qwen3:30b"}`. The server proxies to the backend's `/api/pull` and streams JSONL progress events the GUI surfaces as a per-layer progress row.

The Settings UI gates the **Download** form by hostname — calling pull on a relay-style provider that forwards `/api/chat` but rejects `/api/pull` would 403 on every keystroke. The denylist is a substring match against `URL.hostname.toLowerCase()`:

```js
// static/app.js
const _OLLAMA_PULL_DENY_HOST_FRAGMENTS = ["app.interdataresearch"];
```

Default policy: **allow pull on every Ollama endpoint the user has registered**. Adding the endpoint implies the user administers it (or has permission to write models to it). Append fragments to the array if you discover another known relay where pulls fail. The HTTP endpoint itself doesn't enforce this — it's purely a UI affordance; CLI / programmatic callers can still try the pull, and they'll get the relay's actual error response back.

### Worked example — connecting Interdata Lab (cloud GPU)

[Interdata Lab](https://interdataresearch.ai) is a cloud Ollama deployment with API-key auth, hosted at `app.interdataresearch.ai`. It's the canonical "remote `kind=ollama` backend with bearer auth" that the previous two subsections describe, and the example most users will encounter — the auto-route override (`_maybe_override_to_relay` in [`app.py`](./app.py)) and the pull denylist ([`static/app.js`](./static/app.js)) both single it out by hostname fragment.

#### What you're plugging into

| Field | Value | Why |
|---|---|---|
| **Kind** | `ollama` | Service speaks the native Ollama `/api/chat` JSONL stream, not OpenAI-compatible `/v1/chat/completions`. Same dispatcher (`_impl(backend)["chat_stream"]` in `llm.py`) as a localhost Ollama. |
| **Base URL** | `https://app.interdataresearch.ai` | Substring match on `app.interdataresearch` triggers both the auto-route override and the pull denylist (both TLD-agnostic). |
| **API key** | per-account, from the service's "API Keys" page | Sent as `Authorization: Bearer <key>` by `_ollama_headers(backend)`. Stored in the `backends.api_key` SQLite column, scrubbed from `GET /api/backends` responses. |
| **Headers** | `{}` (default) | Add custom ones via the Settings modal if your deployment needs them — threaded through the same way as the Bearer header. |

No new code path. The same six chat call sites (`llm.chat`, `llm.chat_stream`) that talk to a local Ollama talk to Interdata Lab with no branching.

#### Setup procedure

The user-facing 5-step walkthrough lives in [README — Adding Interdata Lab](./README.md#adding-interdata-lab-cloud-gpu--step-by-step) (with video). From an architectural angle the procedure boils down to: create an API key in the service's dashboard, paste it plus the base URL into MCAi's Settings → + Add endpoint modal, kind=ollama, Test connection. The Test button's call path is `POST /api/backends/test` → `llm.is_running(backend)` → `GET <base_url>/api/tags` with the bearer header. A 200 with a non-empty `models` array means everything's working.

#### Integration with the relay auto-route

Once Interdata Lab is registered and enabled, `_maybe_override_to_relay()` (in `app.py`, called by every chat endpoint after backend resolution) does the following on each chat call:

1. Look up the conversation's pinned backend the usual way.
2. If a registered backend's `base_url` matches `_RELAY_HOST_FRAGMENTS = ("app.interdataresearch",)` and that backend's `list_models` includes the conversation's model name, override the resolved backend to the relay.
3. Cache the relay's model list for `_RELAY_MODEL_CACHE_TTL_S = 60` so the probe doesn't fire on every chat call.

Operational effect: a conversation pinned to local Ollama whose model name (e.g. `qwen3.6:35b`, `gemma4:31b`) also exists on Interdata Lab will route through Interdata Lab automatically — without editing the conversation's `backend_id`. The MCAi Logs page reports the actual backend used (`backend_name: interdatalab`); the relay's own request log (if it keeps one) sees the same call.

To disable the override per-process, set `MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE=1` in the environment and restart. The override falls back to the conversation's pinned backend whenever the relay is unreachable, so a brief relay outage doesn't break local chats — it transparently silos them locally for the duration.

#### Free during alpha

Interdata Lab is in design-partner mode at the time of writing — free for early users in exchange for feedback. See [interdataresearch.ai](https://interdataresearch.ai). If you'd rather run your own cloud Ollama, the same procedure works — only the host fragment in `_RELAY_HOST_FRAGMENTS` needs to change (or you can leave the override off and just chat against your remote endpoint like any other backend).

### Dependencies

`pypdf` and `python-multipart` are pinned in `requirements.txt`. A standard `pip install -r requirements.txt` is the full setup; users cloning the repo do not need any extra commands to enable file attachments. Image and text-file handling is browser-side and adds no runtime dependencies.

---

## Stopping generation

Two complementary mechanisms:

### 1. Manual stop (UI)

The **⏹ Stop** button replaces Send while a response is streaming. Clicking it:

1. Aborts the fetch via `AbortController` on the client.
2. FastAPI detects the disconnect, which closes the `httpx` stream to Ollama.
3. Ollama stops generating within a few tokens.
4. The partial response is **not** persisted to the conversation history.
5. A `⏹ Stopped by user.` notice appears in the assistant bubble.

### 2. Automatic stop (`max_thinking_tokens`)

Set `Max thinking tokens` in the sidebar (or pass `max_thinking_tokens` in the JSON body). When the server's counter of emitted thinking tokens exceeds the limit:

1. The server emits a `data: {"thinking_truncated": true, "reason": "max_thinking_tokens", "limit": N}` SSE event.
2. The generator closes, which closes the upstream Ollama stream.
3. The server sends `data: {"end": true, "truncated": true}`.
4. The turn is **not** persisted (prevents broken-reasoning pollution of context).

Can be overridden per call:

```bash
curl ... -d '{"message":"hi","max_thinking_tokens":50}'
```

---

## Fine-tuning data export

Every chat doubles as a curation surface for supervised fine-tuning (SFT). The workflow uses demonstration data: keep the real user prompts, rewrite imperfect assistant responses into the ideal output, export the pairs as CSV.

### Surfaces

| UI control | What it does |
|---|---|
| ✏️ Pencil (top-right of each assistant bubble) | Inline editor. Textarea prefilled with the raw response (whitespace-trimmed for display). `Save` commits; `Cancel` / `Esc` aborts; `Ctrl/⌘+Enter` saves. Disabled while a stream is active. |
| ⬇ Download icon (header, between Clear and Delete) | Click opens a popover with three formats: **Text CSV** (`<chat_title>.csv` — two columns, image attachments dropped), **JSONL + images (ZIP)** (`<chat_title>.zip` — OpenAI-shaped JSONL records + base64-decoded images), and **Image classification (ZIP)** (`<chat_title>-classification.zip` — flat `image,label` CSV + images, for data-labeling workflows where the assistant labels each uploaded image). |

Edits to user messages are intentionally not supported — the value of the dataset is in the **real prompts** you'd actually send in production. Only assistant outputs are rewriteable.

### Storage model

No schema migration was needed. The conversation's `messages` column is a JSON array of `{role, content, params}` dicts; the edit endpoint just adds three optional fields to each message it touches:

| Field | Type | Populated when |
|---|---|---|
| `edited` | bool | First `PATCH .../messages/{i}`. Stays `true`. |
| `edited_at` | string (ISO-8601 UTC) | Overwritten on every edit. |
| `original_content` | string | Set on the **first** edit only — pinned to the pristine model output; not overwritten by subsequent edits. |

The second edit of a message updates `content` and `edited_at` but leaves `original_content` alone. That matters: it keeps the audit trail (and any future DPO pipeline) anchored to what the model *originally* produced, not the last intermediate revision.

### CSV shape and escaping

```
input,output
"Hello!","Hi there — how can I help?"
"What's ERR_INT_8822?","ERR_INT_8822 is a payout-processor timeout. Typical causes are…"
```

- Columns are literally `input` and `output`.
- Rows are emitted in conversation order, one per adjacent user→assistant pair. If two user messages appear in a row (rare, e.g. after a mid-stream abort), only the second forms a pair with the next assistant reply; the orphan is skipped.
- Escaping is RFC-4180 via Python's stdlib `csv.writer`:
  - Fields containing `,`, `"`, `\r`, or `\n` are wrapped in double quotes.
  - Literal `"` inside a value becomes `""`.
- Leading / trailing whitespace is `strip()`'d on both columns. Important because LM Studio + Qwen3-family models emit a leading `\n\n` separator between their (hidden) thinking block and the answer — training on it teaches the fine-tuned model to emit junk whitespace too.
- Content-Disposition header sets a sanitized filename derived from the conversation title (non-alphanumeric characters → `_`).

### Programmatic access

```python
import httpx, pandas as pd

# Single conversation
csv = httpx.get("http://localhost:8095/api/conversations/3/export.csv").text
df = pd.read_csv(pd.io.common.StringIO(csv))

# Many conversations → one dataset
ids = [3, 7, 11, 18]
frames = [pd.read_csv(pd.io.common.StringIO(
    httpx.get(f"http://localhost:8095/api/conversations/{i}/export.csv").text
)) for i in ids]
pd.concat(frames, ignore_index=True).to_csv("sft.csv", index=False)
```

### ZIP shape (multimodal, JSONL + images)

```
<title>.zip
├── <title>.jsonl                  # one user→assistant pair per line, OpenAI shape
└── images/
    ├── 0_user_0.png               # pair 0, user turn, image 0
    ├── 0_user_1.jpg               # pair 0, user turn, image 1
    └── 2_user_0.png               # pair 2, user turn, image 0
```

JSONL line format (uses the OpenAI fine-tuning shape that HuggingFace `datasets`, axolotl, unsloth, and OpenAI's API all consume natively):

```json
{"messages": [
  {"role": "user", "content": [
    {"type": "text", "text": "what's in this?"},
    {"type": "image_url", "image_url": {"url": "images/0_user_0.png"}}
  ]},
  {"role": "assistant", "content": "A red square."}
]}
```

Implementation notes (from `api_export_conversation_zip` in `app.py`):

- **Pair extraction is shared with the CSV path** (`_iter_pairs(messages)` walks adjacent user→assistant pairs and skips orphans).
- **Text-only turns serialize with a string `content`**, not a single-element typed-parts array. Cleaner JSONL, no `[{"type":"text","text":"..."}]` wrapper for the common case.
- **Image extraction**: each `{"type":"image_url","image_url":{"url":"data:image/...;base64,..."}}` part is parsed via regex; the base64 is decoded and written as a real file at `images/<pair-idx>_user_<img-idx>.<ext>`. The `.url` field in the JSONL is rewritten to that relative path. Mime → extension map covers PNG / JPEG / WebP / GIF / BMP; unknown mimes fall back to `.bin`.
- **PDF and text attachment bodies are inlined** into the user turn's text part (not split into separate files). Demonstration data should preserve what the model actually saw at training time, and the model saw the merged `[Attached: filename]\n<body>\n\n<question>` text.
- **`images/` folder is omitted** from the archive entirely if no image attachments existed in the conversation.
- **No external dependencies**. Stdlib `zipfile` builds the archive into a `BytesIO` buffer; the buffer is returned as `application/zip` with `Content-Disposition: attachment; filename="<title>.zip"`. No temp directory, no streaming complexity — small enough datasets that loading the whole thing in memory is fine.

```python
# Programmatic access — same shape as the CSV section but for the ZIP path.
import httpx, zipfile, io, json

zip_bytes = httpx.get("http://localhost:8095/api/conversations/3/export.zip").content
zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
jsonl_name = next(n for n in zf.namelist() if n.endswith(".jsonl"))
records = [json.loads(line) for line in zf.read(jsonl_name).decode().splitlines()]
print(f"{len(records)} pairs; {sum(1 for n in zf.namelist() if n.startswith('images/'))} images")

# Or — feed straight to HuggingFace `datasets` after extracting:
zf.extractall("./mybot")
from datasets import Dataset
ds = Dataset.from_json("./mybot/mybot.jsonl")
```

### Image-classification ZIP shape (data-labeling workflow)

A third export format optimized for *image classification / data labeling* — distinct from the multimodal SFT JSONL above. Use case: the system prompt holds your labeling instructions (`"Answer 'drunk' or 'sober'"`, `"Return JSON with bbox + class"`, etc.); each user turn uploads an image; each assistant reply is the label. The resulting dataset is a flat `(image, label)` table.

```
<title>-classification.zip
├── <title>.csv               # two columns: image, label
└── images/
    ├── 0_user_0.png          # one entry per image attached to a user turn
    └── 1_user_0.jpg
```

The CSV body looks like:

```
image,label
images/0_user_0.png,drunk
images/0_user_1.png,drunk
images/1_user_0.jpg,sober
```

Implementation notes (from `api_export_conversation_classification_zip` in `app.py`):

- **Pair-walking is shared with the other exporters** (`_iter_pairs`).
- **Pairs without an image attachment are skipped entirely.** A text-only chat exports a CSV with the header row only — no spurious empty pairs.
- **The user's typed text is dropped.** Two reasons: (a) the model already saw it at label time, (b) a classification dataset's `image → label` mapping shouldn't be polluted with text inputs that won't exist at inference time. (Use the multimodal SFT ZIP if you need the text preserved.)
- **Multi-image turns produce one CSV row per image, all sharing the same label** — natural behavior for a labeler tagging a batch in one go. Image filenames use the same `<pair-idx>_user_<img-idx>.<ext>` scheme as the multimodal SFT ZIP, so both archives can be unzipped into the same folder if you want both representations of the same data.
- **Filename ends `<title>-classification.zip`** (vs the SFT ZIP's `<title>.zip`) — both can be downloaded for the same conversation without overwriting each other.
- **No external dependencies.** Stdlib `zipfile` + `csv` + `base64` + `re`.

```python
# Pandas / sklearn / torchvision / HuggingFace ImageFolder all consume this directly.
import httpx, zipfile, io, pandas as pd

zip_bytes = httpx.get("http://localhost:8095/api/conversations/3/export.classify.zip").content
zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
zf.extractall("./labels")
df = pd.read_csv(next(p for p in pathlib.Path("./labels").glob("*.csv")))
print(df["label"].value_counts())
```

### From SFT to DPO

The `original_content` field means the database already contains preference triples whenever you've edited a message: `(prompt, chosen=edited content, rejected=original_content)`. A short script reading the raw `messages` JSON produces a DPO JSONL file with no UI changes required. This is the intended upgrade path when your demonstration dataset stops improving the model (typically many thousands of pairs in).

---

## Worked example — automated image labeling

<p align="center">
  <a href="https://youtu.be/yKNebbDbWJE">
    <img src="https://img.youtube.com/vi/yKNebbDbWJE/hqdefault.jpg"
         alt="Sped-up demo of LLM-assisted image labeling"
         width="640">
  </a>
  <br><em>Sped-up walkthrough — click to watch on YouTube.</em>
</p>

A complete, runnable example of the per-chat-microservice pattern applied to LLM-assisted dataset labeling. Source: [`docs/examples/hotdog_nothotdog/`](./docs/examples/hotdog_nothotdog/) (script + 100-image dataset + the CSV they produce).

### What the script does

[`label_images.py`](./docs/examples/hotdog_nothotdog/label_images.py) is 73 lines. For every image in `IMAGES_DIR` it:

1. Reads the file, base64-encodes, builds a `data:<mime>;base64,...` URL.
2. POSTs `/api/conversations/{id}/chat` with the multimodal payload:
   ```json
   {
     "message": "What is in this image?",
     "attachments": [{
       "name": "<filename>",
       "kind": "image",
       "mime": "image/jpeg",
       "data_url": "data:image/jpeg;base64,..."
     }]
   }
   ```
3. Reads the model's `response` field — a single short label (`Hotdog` / `not hotdog` in the example, because that's what the bot's *system prompt* — set once in the GUI — instructs).
4. Appends `(input=images/<filename>, output=<label>)` to a `pandas.DataFrame` and writes the whole frame to `labels.csv` *after every image*. The CSV is the source of truth at every step; a crash, kill, or power cut loses at most the one in-flight call.

That's the entire labeler: no auth, no batching framework, no queue, no streaming. It depends on `requests` + `pandas` and nothing else.

### Why it's small

The labeling logic itself — "what makes this output a label rather than a paragraph?" — lives entirely in the saved conversation's `system_prompt` column. The HTTP call doesn't carry any classifier-defining context; the server reads the bot config from SQLite and injects it into every chat call. Consequences:

- **The same script labels anything.** Change the bot's system prompt in the GUI (or use the **✨ Generate prompt** button to author it from a one-sentence description) and the same `label_images.py` produces fundamentally different output — multi-label tags, JSON with confidence, bounding boxes, free-text captions. Zero code change to the labeler.
- **Per-conversation overrides are impossible from this caller.** The endpoint **ignores** caller-supplied `model` / `temperature` / `system_prompt` fields on the per-conversation `/chat` route — that's the [microservice config lock](#per-chat-microservice-pattern). The labeler can't accidentally degrade output by passing wrong sampling params. This is by design.
- **Reproducibility.** Two months later, re-running the same conversation against the same images produces the same labels, because the model + system prompt + params are pinned in the DB. To version the labeling task itself: [export the bot config](#bot-import--export) to a `.miniclosed-bot.json` and check it into git.

### Pre-conditions on the bot

Just two:

| Required | Why |
|---|---|
| The picked model is **vision-capable** | otherwise the `image_url` content part is silently dropped by Ollama / OpenAI-compat servers. MiniClosedAI's [vision-model heuristic](#vision-model-heuristic) shows a soft-warn banner in the GUI; programmatic callers don't see it but the model just returns text-only guesses. |
| The system prompt **constrains output to a known label set** | "Reply with only `Hotdog` or `not hotdog`" — without this the bot answers in prose ("This appears to be a delicious hot dog with mustard…") and post-processing has to extract the label every time. Prompt-engineer the constraint once, in the GUI; the script doesn't normalize anything. |

### Crash safety / resumability

The script writes the entire `pandas.DataFrame` to CSV every loop iteration (`df.to_csv(OUTPUT_CSV, index=False)`). On crash:

- The CSV reflects every successfully-labeled image up to the failure.
- To resume: read the existing CSV, filter `image_files` to skip already-labeled filenames, run again. The example doesn't ship this filter (intentionally — it'd add 10 lines and the user might want a re-label semantics instead), but it's a 3-line addition.

A more aggressive design (one this example deliberately doesn't take): SQLite-backed checkpoint, per-row retry budget, exponential backoff on transient HTTP failures. None of that is needed for the typical case — local Ollama doesn't have transient failures, and 100% throughput on 100k images is not the goal.

### Scale notes

- **Sequential by default.** ~1 request/sec on a 7B vision model, GPU-bound. 100 images in 1–2 minutes; 10k in 3–4 hours. Run it overnight.
- **Parallelize via `xargs -P N`** or split `image_files` into N shards across N processes — each MiniClosedAI endpoint serves concurrent requests independently. Ollama / LM Studio / vLLM each handle concurrent inference differently; vLLM batches efficiently, Ollama queues.
- **Network locality matters.** The example POSTs to `192.168.0.110:8095` — a LAN-local MiniClosedAI. Public-internet round-trip latency dominates per-call cost at scale; co-locate the labeler with the server.

### When *not* to use this

- **High-volume production labeling at >1k req/sec sustained** — at that point, talk directly to the model server (skip MiniClosedAI's HTTP layer) or use a batch API like vLLM's `/v1/chat/completions` with concurrency tuned at the model layer.
- **Cases where you want streaming labels** — this example uses the non-streaming `/chat` endpoint because each label is short. For long structured outputs (full paragraphs, large JSON), use `/chat/stream` and consume the SSE chunks like the [README's streaming snippet](./README.md#chat).

### What to clone from this

The [`docs/examples/hotdog_nothotdog/`](./docs/examples/hotdog_nothotdog/) folder is meant to be copied wholesale: rename, swap the images, swap the system prompt in the GUI, swap the URL + conversation ID in the script. The structure (a single Python file + an `images/` folder + a `labels.csv` output) is the template. Future examples added under `docs/examples/` should follow the same shape so users can recognize the pattern by filename.

---

## Worked example — chatbot frontends (Python CLI + HTML widget)

### Video walkthrough — Hotel Reservation Bot, end to end

▶️ **[YouTube: build + embed a Hotel Reservation Bot](https://youtu.be/LiQeIAeSVA4)** — the full create-to-chat loop in one take. Every file referenced is in this repo; this is the step-by-step the video follows:

1. **New bot.** MiniClosedAI → **+ New bot** → paste the system prompt from [`docs/recipes/Hotel Reservations Bot.md`](./docs/recipes/Hotel%20Reservations%20Bot.md) → apply the recipe's recommended settings (`qwen3:8b`, T `0.3`, max tokens `600`, `include_history: true`).
2. **Verify in the GUI.** Send the recipe's "Example 0" one-shot booking. Correct behavior = a prose reply followed by a fenced `create_booking` JSON block (the dual-mode output pattern).
3. **Copy the bot ID.** Chat topbar → **`</>`** ("Get API integration code") → **Copy bot ID** pill in the modal header (one click; no manual typing).
4. **Repoint the widget.** Edit [`docs/examples/web_chatbot/index.html`](./docs/examples/web_chatbot/index.html) → set `const CONV_ID = <id>` → save. `MCAI_BASE_URL` auto-derives from the page host (with a `file://` fallback), so no other edit is needed for same-host serving.
5. **Serve + chat.** `cd docs/examples/web_chatbot && python3 -m http.server 9000` → open the page → chat with the bot you just built.

The rest of this section is the implementation detail behind the two templates.

---

Two reference implementations of "consume a conversational MCAi bot as an end-user surface". Both back-end on the same `/api/conversations/{id}/chat/stream` endpoint (the HTML) or `/v1/chat/completions` (the Python script via the OpenAI SDK) and demonstrate the same five-stage lifecycle:

1. **Stream** the bot's reply token-by-token.
2. **Suppress** any fenced code block (the recipe's action JSON) from the user-visible surface.
3. **Signal** the moment a fence opens (transition from "bot writing prose" to "bot writing JSON").
4. **Render** a structured summary of the parsed action.
5. **End** the conversation cleanly so the user can't keep typing after action capture.

Source folders:

- [`docs/examples/hotel_chatbot/chat.py`](./docs/examples/hotel_chatbot/chat.py) — terminal CLI, 250 LOC, `openai` SDK.
- [`docs/examples/web_chatbot/index.html`](./docs/examples/web_chatbot/index.html) — self-contained HTML page, 560 LOC including styles, zero dependencies.

### Architecture, identical in both languages

```
                         ┌──────────────┐
   user types in input ──►  "Thinking…" │ ← indicator while waiting for token 1
                         └──────┬───────┘
                                │ POST /chat/stream (or /v1/chat/completions)
                                ▼
                       ┌─────────────────┐
   stream of chunks ←──┤  MCAi server    │
                       │  + relay route  │
                       └─────────────────┘
                                │
                                ▼ each chunk:
                       ┌──────────────────────┐
                       │  FenceSuppressor     │
                       │  ── inside fence? ───┼──── yes ──► drop (suppress JSON)
                       │  └─ first ``` seen ──┼──── fire `on_fence_open` ──┐
                       └──────────────────────┘                           │
                                │                                         ▼
                                ▼ outside fence content              ┌─────────────────────────┐
                       ┌──────────────────┐                          │ "Extracting information…"│
                       │   chat bubble    │                          └─────────────────────────┘
                       │   or terminal    │
                       └──────────────────┘
                                │
                                ▼ stream ends
                       ┌──────────────────────────────┐
                       │  extractAction() → JSON dict │
                       └──────────────┬───────────────┘
                                      ▼
                       ┌──────────────────────────────────┐
                       │  renderAction() → labeled table  │
                       │  composer disabled                │
                       └──────────────────────────────────┘
```

### The `FenceSuppressor` class — present in both files

Both implementations share the same algorithm, line for line:

- Maintain a small lookbehind buffer (2 chars when outside a fence, 3 when inside).
- When outside a fence: emit everything except the trailing 2 chars (in case they're the start of `` ``` `` arriving across chunk boundaries).
- When `` ``` `` is found: skip it + any language tag + the trailing newline, transition into "inside fence" mode, fire the `on_fence_open` callback **exactly once** per instance (one-shot — even if the bot emits multiple action blocks in a single reply, the indicator only appears once).
- When inside a fence: drop everything until the next `` ``` ``, then transition back out.
- The callback site is wrapped in try/except so a faulty callback doesn't break the streamer.

Python: [`FenceSuppressingStreamer`](./docs/examples/hotel_chatbot/chat.py). JS: `class FenceSuppressor` at the top of the `<script>` block in the HTML.

### Why the Python uses OpenAI SDK and the HTML uses native MCAi

| | Python | HTML |
|---|---|---|
| Endpoint | `POST /v1/chat/completions` | `POST /api/conversations/{id}/chat/stream` |
| SSE shape | OpenAI `chat.completion.chunk` (`choices[0].delta.content`) | MCAi-native (`{"chunk": "..."}` / `{"end": true}`) |
| Library | `openai` (1 dep) | none (`fetch` + `ReadableStream`) |
| Why | The official SDK is the most-installed LLM library on PyPI; using it here makes the script a portable template that works against api.openai.com with one URL change. | Hand-rolling SSE parsing in 30 lines is cheaper than including a 50 KB SDK; native MCAi's shape is simpler to parse client-side; CORS works out of the box. |

### Generic action renderer — used by both

The recipe bots emit different action shapes (`create_booking`, `create_appointment`, `create_reservation`, etc.). Both renderers walk the parsed dict generically:

- Convert `snake_case` keys to `Title Case` labels.
- Skip `null` / `""` / `[]` / `{}` values (recipe placeholders for unfilled fields).
- Render booleans as `yes` / `no`.
- Group nested objects under a section header indented one level.

Python: `render_action()`. JS: `renderAction()`. Output is structurally identical (a `<dl>` in HTML, a labeled key/value table in the CLI).

### Adapting to a different recipe

Neither file references "hotel" or `create_booking` in the chat-handling code path — the fence-detection and action-extraction look for **any** fenced JSON block. To repoint at another recipe:

1. Change the conversation id (`MCAI_CONV_ID` env var for Python; `CONV_ID` constant in HTML).
2. Edit the system prompt of that conversation in MCAi's GUI to define what gets collected and what action emits.

Nothing else changes. The Doctor's `create_appointment`, the Restaurant's `create_reservation`, a custom bot of yours emitting `{"type": "place_order", ...}` — all render the same way and trigger the same lifecycle.

### Deployment surfaces — HTML widget

The HTML's CORS-friendliness (MCAi ships `allow_origins=["*"]`) plus its auto-derived `MCAI_BASE_URL` makes it work in five useful contexts:

| Deployment | Setup | Notes |
|---|---|---|
| **Local file** (`file://`) | Just open `index.html` | The page falls back to `http://localhost:8095` for `MCAi_BASE_URL` since `window.location.hostname` is empty under `file://`. Fastest test / demo. |
| **Same-origin** — served by MCAi itself | `cp docs/examples/web_chatbot/index.html static/web_chatbot/`, visit `http://<host>:8095/static/web_chatbot/index.html` | One port. No CORS preflight. Easiest internal deployment. |
| **Different port on same host** — simulates a separate web app | `cd docs/examples/web_chatbot && python3 -m http.server 9000 --bind 0.0.0.0`, visit `http://<host>:9000/index.html` | Two ports, two processes, exact mimic of a third-party site embedding the chatbot. The page derives `http://<host>:8095` for MCAi from `window.location.hostname`; the browser does a CORS preflight that MCAi accepts because of `allow_origins=["*"]`. |
| **Different host entirely** — your marketing site fetches the widget | Replace `MCAI_BASE_URL` constant with an explicit URL: `"https://chat.example.com"` | MCAi must be network-reachable from every visitor's browser. Usually means putting MCAi behind a reverse proxy with TLS + auth. |
| **Public-internet** — chatbot served, MCAi reachable | **Don't, without auth in front.** MCAi has zero auth by default. | Anyone reaching `/api/*` can read, modify, or delete your bots. Always front MCAi with nginx + bearer-token auth (or OAuth proxy) before exposing publicly. |

### MCAi-URL auto-detection — how the HTML decides where to call

```js
const MCAI_BASE_URL =
  window.location.protocol === "file:"
    ? "http://localhost:8095"
    : `${window.location.protocol}//${window.location.hostname}:8095`;
```

| Page loaded from… | `window.location.hostname` | Result |
|---|---|---|
| `file:///path/to/index.html` | `""` (empty) | `http://localhost:8095` (the explicit fallback) |
| `http://localhost:8095/static/web_chatbot/index.html` | `localhost` | `http://localhost:8095` |
| `http://192.168.0.110:8095/static/...` | `192.168.0.110` | `http://192.168.0.110:8095` |
| `http://192.168.0.110:9000/index.html` (separate static server) | `192.168.0.110` | `http://192.168.0.110:8095` — same host, MCAi's port |
| `https://my-site.com/chat/` | `my-site.com` | `https://my-site.com:8095` — likely **wrong**; hardcode `MCAI_BASE_URL` for production |

The default is right for "host both pieces on the same LAN box, possibly on different ports." For any other topology, edit the constant directly.

### Scroll behavior during fence suppression

A subtle UX bug to keep an eye on if you fork this widget: while the bot streams a suppressed fenced block, `addBubble`-then-grow doesn't add visible content, but new DOM elements (like the "Extracting information…" indicator) *do* land below the bubble. If you naively call `bubble.scrollIntoView({block:"end"})` on every chunk, those still-arriving chunks scroll the viewport back UP to the bubble — burying the indicator off-screen.

The widget uses a single `scrollToBottom()` primitive that pins to `messages.scrollHeight` on every DOM-changing event, instead of scrolling individual elements into view. Whatever's at the bottom of the container — bubble, indicator, or extracted-card — stays visible.

### Per-session memory model

Conversation history is owned entirely by the client (a `const history = []` array in the JS module) and shipped on every chat request as the `messages: [...]` field:

```js
body: JSON.stringify({ messages: history })
```

The widget deliberately does **not** use `include_history: true` (which would replay the bot's persisted messages from the SQLite row) or `persist: true` (which would write back). Consequences:

- **Page refresh = brand-new visitor.** JS state resets; the bot has no idea who came before. Perfect for kiosk-style retesting.
- **The bot's saved DB row stays pristine.** Only its config (system prompt, model, sampling params) is read; the `messages` column is never touched.
- **Multiple browser tabs share nothing.** Each tab has its own JS `history`. Two visitors testing simultaneously can't interfere with each other.

If you want cross-session persistence (e.g. a logged-in user resuming yesterday's chat), build a server-side conversation-per-user mapping and pass the right `messages: [...]` from your backend; don't lean on MCAi's `persist: true` mechanism unless you want the dashboard's view of the bot polluted with end-user transcripts.

### Markdown rendering in bot bubbles

Bot replies typically contain `**bold**`, numbered lists, and inline `` `code` ``. The widget includes a ~25-line `renderMarkdown(text)` function with deliberately minimal grammar — just the patterns the recipes actually emit:

| Grammar | Output element |
|---|---|
| `**…**` | `<strong>` |
| `*…*` (not inside word boundary) | `<em>` |
| `` `…` `` | `<code>` |
| Lines starting `N. ` | `<ol><li>` |
| Lines starting `- ` or `* ` | `<ul><li>` |
| Everything else | text node |

**Security model.** Every character is HTML-escaped first (`&`/`<`/`>` → `&amp;`/`&lt;`/`&gt;`) *before* any markdown pattern matches the escaped text. The function's output can only contain the six element types above — no `<script>`, no event handlers, no `<iframe>`. LLM output is treated as untrusted; the escape-then-transform order guarantees nothing the model can emit (intentionally or by manipulation) reaches the DOM as executable HTML.

**Streaming-friendliness.** `FenceSuppressor` accumulates visible text in `this.visible` (a string) and re-renders the entire bubble via `target.innerHTML = renderMarkdown(this.visible)` on every chunk. Incomplete patterns at the buffer tail (e.g. `**fo` waiting for `o**`) render as literal characters until the closing marker arrives, then snap into the formatted element on the next chunk — no flicker, no partial DOM updates, no separate "streaming-aware" parser needed. Re-parsing is cheap (linear in bubble length, typically <2 KB).

**User bubbles stay plain.** `addBubble("user", text)` uses `textContent`, not `innerHTML`. If a user types `**hi**` they see literal asterisks — preventing surprise formatting on visitor input.

**When to swap for a real parser.** This renderer is intentionally limited to what the recipes use. If you need headers, tables, links, fenced code blocks (the action JSON is *suppressed*, not displayed), or any other CommonMark feature, drop in [marked](https://marked.js.org/) for parsing and [DOMPurify](https://github.com/cure53/DOMPurify) for sanitization — both single-file CDN drops. Replace `renderMarkdown(s)` with `DOMPurify.sanitize(marked.parse(s))`. Trade-off: ~30 KB of vendor JS added; harder to audit than the ~25 lines in the widget today.

### Out of scope

- **Authentication.** Neither example includes auth headers. MCAi is local-first; if you front it with a reverse proxy that requires a bearer token, add an `Authorization` header to both clients (~1 line each).
- **Multi-turn persistence beyond the script's lifetime.** Both clients keep history in-memory only. Reload the page (or rerun the script) and you start with a fresh `history`. To carry context across sessions, set `persist: true` in the Python call (and use `/api/conversations/{id}/chat` rather than the OpenAI-compat endpoint) or maintain history client-side and resend it on every request.
- **Production hardening.** No retry-on-network-failure, no abort-controller for streaming, no rate-limiting. Add these in your production fork — the templates are deliberately readable above optimized.

---

## Client SDK — composing bots from your code

The CLI and HTML examples are *end-user surfaces* for a single bot. For **orchestration** — one process that calls several bots, has them feed each other, or embeds each bot as a function inside an internal app — there's a zero-dependency single-file client at [`docs/examples/client/miniclosedai_client.py`](./docs/examples/client/miniclosedai_client.py) (stdlib only; copy, no `pip install`).

```python
from miniclosedai_client import Bot
triage, writer = Bot.find("triage"), Bot.find("writer")
intent = triage.ask(user_msg, history=False)
reply  = writer.ask(f"Reply addressing: {intent}", history=False)
```

The `Bot` class is a thin wrapper over the per-conversation endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `Bot(id)` / `Bot.find(title)` / `Bot.list()` | `GET /api/conversations` | address / discover bots |
| `Bot.create(...)` / `Bot.get_or_create(...)` | `POST /api/conversations` | create a bot from code (get_or_create is idempotent by exact title) |
| `.ask(msg, history=, persist=)` | `POST /api/conversations/{id}/chat` | reply text (sets `include_history`, `persist`) |
| `.stream(msg)` | `POST .../chat/stream` | generator of SSE `chunk`s |
| `.add_text()` / `.add_file()` / `.knowledge()` | `…/knowledge` | manage the bot's RAG library |
| `.delete()` | `DELETE /api/conversations/{id}` | remove the bot (+ its knowledge base) |

Base URL comes from `MINICLOSEDAI_BASE_URL` (default `http://localhost:8095`). Errors raise `MiniClosedAIError`. Two runnable examples: [`example.py`](./docs/examples/client/example.py) (a two-bot pipeline) and [`router_example.py`](./docs/examples/client/router_example.py) — a self-bootstrapping router that creates a router + three specialist bots, classifies a support message, and dispatches to the matching expert (verified live; `--cleanup` removes the demo bots).

This is the intended **multi-LLM management** shape: MiniClosedAI is the registry/host (each bot = a configured expert with its own model, knowledge, tools); the orchestration logic lives in *your* code, not inside MCAi. (Implementation note: the client uses `from __future__ import annotations` because the `Bot.list` classmethod shadows the builtin `list` in the class namespace, which would otherwise break the `-> list[dict]` hints.) For OpenAI-SDK ergonomics you can alternatively use the official `openai` package against `…:8095/v1` with `model="conv-<id>"`; the bespoke client exists for the native-only features (`include_history`, `persist`, knowledge upload).

### Router walkthrough — classify-then-dispatch over a bot fleet

[`router_example.py`](./docs/examples/client/router_example.py) is the canonical multi-LLM example: one router bot classifies an inbound message, and the orchestration code dispatches to the matching specialist. It's self-contained — it bootstraps its own bots, so it runs against any instance with a tool-capable chat model.

1. **Bootstrap (idempotent).** `Bot.get_or_create(title, MODEL, system_prompt, **params)` creates a router + three specialists keyed by exact title, so re-runs don't duplicate. The router prompt forces a single-word reply (`billing` / `technical` / `sales`) at `temperature=0.0` for determinism; specialists run at `0.3`.
2. **Dispatch (the whole orchestration):**
   ```python
   label  = router.ask(message, history=False).strip().lower().split()[0]
   expert = LABEL_TO_TITLE_MAP[label] (fallback: technical)
   reply  = expert.ask(message, history=False)
   ```
   `history=False` on every call = pure-function semantics (each request independent; no shared history). `.split()[0]` defensively takes the first token in case a model adds stray words around the label.
3. **Verified live** against `qwen3:8b`: "charged twice" → `billing`, "crashes on PDF upload" → `technical`, "annual discount?" → `sales`, each answered by the correct specialist.
4. **Cleanup:** `--cleanup` enumerates `Bot.list()`, matches the demo titles, and calls `Bot.delete()` on each.

Design point: the specialists are independent server-side experts — give any of them a different model, a RAG knowledge base, or MCP tools and the orchestration code is unchanged. The engine stays in the user's script; MCAi only hosts the bots. This is deliberately *not* a workflow runtime baked into MCAi (which would compete with LangGraph/CrewAI and bloat the core) — the classify-then-dispatch logic is ~10 lines of plain Python the user owns.

---

## Bot import / export

A separate channel from fine-tuning data export. The CSV / ZIP exports above are for **training data**; this section is for **moving a bot's configuration between instances**. Different file, different consumer, different security stance.

### Why a dedicated format

A bot in MiniClosedAI is a row in the `conversations` table — title, model name, system prompt, sampling params, optional message history. The natural "share this bot" question is: "I built this in dev, can I run the same thing on the production box / on a teammate's laptop?" Two non-options that we explicitly rejected:

1. **`sqlite3 .dump | sqlite3`** — drags every other bot, every backend row (with its API keys), and is fragile across DB version drift.
2. **`POST /api/conversations` with the right body** — works, but the caller has to translate between the source instance's `backend_id` and the target's, and there's no portable file to email/Slack/git.

So: a small JSON file the user can move around, plus an importer that does the backend resolution.

### Endpoints

```
GET  /api/conversations/{id}/export?include_history=false
       → 200 application/json
       → Content-Disposition: attachment; filename="<title-slug>.miniclosed-bot.json"

POST /api/conversations/import
       → 201 (auto-matched a backend)
       → 409 (no enabled backend serves the model — payload includes a picker list)
       → 400 (malformed file or unknown format_version)
```

### File schema (`format_version: 1`)

```json
{
  "format": "miniclosed-bot",
  "format_version": 1,
  "exported_at": "2026-05-05T18:30:00+00:00",
  "bot": {
    "title": "Doctor's Office Bot",
    "model": "qwen3:8b",
    "system_prompt": "You are the receptionist at...",
    "params": {
      "temperature": 0.4,
      "max_tokens": 2048,
      "top_p": 0.9,
      "top_k": 40,
      "think": false,
      "max_thinking_tokens": null
    }
  },
  "sample_messages": []
}
```

Key shape rules:

- **`format`** is always the literal string `"miniclosed-bot"`. Importer rejects anything else with **400**.
- **`format_version`** is an integer. The current server understands version `1`. A future server bumping to `2` must keep accepting `1` (back-compat); a v1 server given a v2 file rejects with **400** rather than silently dropping unknown fields.
- **`bot.model`** is a *string*, not a backend ID. Backend IDs are per-instance and meaningless across machines. The importer uses this string to find a matching backend.
- **`bot.params`** mirrors the in-DB `params` JSON column — same keys as the [Conversations create body](#conversations). Unknown keys are accepted and persisted (forward-compat with future param additions).
- **`sample_messages`** is `[]` by default. When `?include_history=true` was passed on export, it's the exact `messages` JSON column verbatim — including any `attachments` arrays with base64-inlined images.
- **What's deliberately absent**: `backend_id`, API keys, backend rows, DB ids, `created_at`, `updated_at`. The file is safe to share over Slack / email / git.

### Import resolution flow

```
                    ┌─────────────────────┐
POST /import  ───►  │ Validate format +   │
                    │ format_version ≤ 1  │
                    └────────┬────────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
         backend_id given?         backend_id missing
                │                         │
                ▼                         ▼
       Use it (validate          Scan enabled backends,
        it exists, 400            list each one's models,
        otherwise)                pick first one whose
                │                  model list contains
                │                  bot.model (auto-match)
                │                         │
                │                  match? ┴── no ──► 409 needs_backend
                │                  yes
                └─────────┬───────────────┘
                          ▼
              Insert NEW conversation row
              (title bumped if it collides)
                          ▼
                  201 { id, title,
                        matched_backend_id,
                        warnings: [...] }
```

Five concrete behaviors worth knowing:

1. **Always inserts a new row**. Never overwrites. There's no `?replace_id=` parameter on purpose — collisions across instances would be ambiguous.
2. **Title collision → suffix**. If a bot named "Doctor's Office Bot" already exists, the import becomes "Doctor's Office Bot (2)" (then `(3)`, etc.).
3. **Auto-match is the default; explicit override is the escape hatch**. POST `{"data": ..., "backend_id": 5}` skips the model probe entirely and trusts the caller. The 201 returns whichever `backend_id` was actually used as `matched_backend_id`.
4. **`needs_backend` is not a failure, it's a question**. The 409 body includes `available_backends: [{id, name, kind, model_present, model_count}, ...]` — the GUI uses this to render a picker. You retry the same POST with `backend_id` set.
5. **Probe failures are warnings, not errors**. If a backend's `is_running` check times out or `/api/tags` 500s, the import doesn't blow up — that backend is treated as having no models, and a `"backend '...' probe failed: ..."` line lands in the 201's `warnings` array.

### Worked round-trip

```bash
# On instance A:
curl -o doctor.miniclosed-bot.json \
  http://localhost:8095/api/conversations/3/export
# → 12 KB JSON

# Email/Slack/git the file to instance B (different machine, different DB).

# On instance B — happy path (auto-match):
curl -X POST http://localhost:8095/api/conversations/import \
  -H "Content-Type: application/json" \
  -d "{\"data\": $(cat doctor.miniclosed-bot.json)}"
# → 201 { "id": 14, "title": "Doctor's Office Bot",
#         "matched_backend_id": 1, "warnings": [] }

# On instance B — picker path (no enabled backend has qwen3:8b):
curl -X POST http://localhost:8095/api/conversations/import \
  -H "Content-Type: application/json" \
  -d "{\"data\": $(cat doctor.miniclosed-bot.json)}"
# → 409 { "needs_backend": true, "model": "qwen3:8b",
#         "available_backends": [
#           {"id": 1, "name": "Built-in Ollama", "kind": "ollama",
#            "model_present": false, "model_count": 3},
#           {"id": 4, "name": "LM Studio", "kind": "openai",
#            "model_present": false, "model_count": 12}
#         ],
#         "detail": "No enabled backend currently serves model..." }

# Retry with explicit backend_id:
curl -X POST http://localhost:8095/api/conversations/import \
  -H "Content-Type: application/json" \
  -d "{\"data\": $(cat doctor.miniclosed-bot.json), \"backend_id\": 4}"
# → 201 { "id": 15, ... "matched_backend_id": 4 }
```

### GUI counterparts

- **Export**: top-bar download icon → popover menu → **Bot config (JSON)** or **Bot config + history (JSON)**.
- **Import**: top-bar upload-cloud icon (next to "+ New Chat") → file picker → success switches to the new bot, 409 opens the picker modal with radio buttons over `available_backends`.

### Security stance

The format is intentionally minimal so a bot file can be shared without leaking secrets:

- No API keys (those live in the `backends` table, never in conversations).
- No backend rows or `base_url`s — the importing instance uses its *own* registered backends.
- No DB ids — the importer assigns fresh ones.
- No upstream credentials of any kind.

If you need to *also* share an endpoint (e.g. a hosted Bonsai relay you want a teammate to use), that's a separate manual step on their side: ⚙️ Settings → Add endpoint. We could add a portable-endpoint format later, but it would need an explicit "include the API key?" toggle and clear warnings.

---

## Self-upgrade

Two surfaces for pulling the latest from GitHub: a CLI script (`upgrade.sh`) and a GUI button. The button is just a thin trigger over the script — the script is the source of truth, runs identically either way.

### Architecture

```
[Browser]               [Server (uvicorn)]            [upgrade.sh]
   │                          │                              │
   ├─ click Update ──────▶    │                              │
   │                          ├─ Popen([./upgrade.sh],       │
   │  ◀── 202 ───────────     │     start_new_session=True)──▶ (own process group)
   │                          │                              │
   ├─ poll /status (1.5 s) ──▶│                              ├ git pull
   │                          │   ◀── kill (SIGTERM) ────────┤
   │                          ✗ (server dead)                ├ pip install
   ├─ poll /status ────▶ ✗ (conn refused)                    │
   ├─ poll /status ────▶ ✗ (conn refused)                    ├ nohup uvicorn ──▶ ✓ new server up
   ├─ poll /status ────────────────────────────────────────────────▶ 200, current_sha = new_sha
   │                                                                │
   ├─ location.href = pathname + "?_ts=" + Date.now()  (cache-busted reload)
```

The script becomes its own process group via `setsid` (Python: `subprocess.Popen(start_new_session=True)`) so the SIGTERM that kills the old uvicorn doesn't kill the script that's mid-pull. The new uvicorn is spawned via `nohup … &; disown` so it survives the script exiting.

### Endpoints

| Route | Purpose | Safety |
|---|---|---|
| `GET  /api/upgrade/status` | Returns `{installed_via, current_sha, current_short, latest_sha, latest_short, behind, dirty, latest_messages, can_upgrade, reason, last_run, first_seen_at}`. Read-only. **Three modes:** `git` (best-effort `git fetch` + local graph), `docker` (build SHA env + GitHub REST API, cache-windowed at 10 min), `unknown` (no `.git`, in-place upgrade impossible). See [Update detection state](#update-detection-state) below for the persistent state file and once-per-version logging. | Always exposed. |
| `POST /api/upgrade/run` | Spawns `upgrade.sh` detached. Returns 202 immediately with `{started, from_sha, to_sha}`. | **Loopback-only** — refuses with 403 if `request.client.host` isn't in `{127.0.0.1, ::1, localhost}`. Refuses with 409 if `can_upgrade=false`. |

### Script states

The script writes `/tmp/miniclosedai-upgrade.json` at every phase so the GUI can show meaningful progress without re-running git. Possible values for the `state` field:

| State | Meaning |
|---|---|
| `pulling` | git fetch + ff-only pull in progress |
| `installing` | `pip install -qr requirements.txt` |
| `restarting` | killing old uvicorn + spawning new one |
| `verifying` | polling `/api/upgrade/status` on the new server |
| `done` | new server answered within the 15 s window — success |
| `failed` | something broke; auto-rollback ran; install is back on `from_sha` |

### Auto-rollback

The script's last act before declaring success is to verify the new server actually answers `/api/upgrade/status`. If it doesn't within 15 seconds (30 polls × 0.5 s):

1. Kill the new uvicorn process.
2. `git reset --hard $PREV_SHA`.
3. Reinstall the previous deps.
4. Re-spawn uvicorn with the old code.
5. Write `state: "failed"` with the error so the GUI can surface it.

Logs of the failed attempt land in `/tmp/miniclosedai-upgrade.log` for postmortem.

### Why loopback-only

Even on a single-user playground, exposing "shell-exec via HTTP" to anything other than the local machine is a non-trivial blast-radius if the bind address ever changes (e.g. someone runs `--host 0.0.0.0` to share the GUI with their phone on the LAN — perfectly reasonable for chat, dangerous for upgrade). The 403 guard makes the policy explicit at the framework boundary instead of relying on bind config.

The status endpoint is always exposed because reading version metadata is harmless and the GUI's "behind by N" badge needs to work over the LAN.

### When the script is run directly vs from the GUI

The script checks `MINICLOSEDAI_UPGRADE_VIA_GUI`: when set (the FastAPI `Popen` call sets it), it sleeps 1 s before doing anything heavy so the server has time to flush the 202 response before the script kills it. When run from a terminal (env var unset), it skips the sleep — there's no parent HTTP request to flush.

### Update detection state

Pattern lifted from OpenClaw's `update-check.json`. The status endpoint persists what it learned across requests so we can:

1. **Cache the GitHub API call.** Anonymous `api.github.com` is rate-limited to 60 requests / hour / IP. A LAN with several browser tabs each polling every 10 minutes can creep up; the cache window collapses repeats into one network call.
2. **Stamp `first_seen_at`** the first time a given new remote SHA is observed. The modal surfaces this as "Available since X" so a release that's been sitting unupgraded for days is obvious.
3. **Log the announcement once.** When a brand-new SHA is seen, the server prints `[miniclosedai] update available: <current> → <latest>` to stderr exactly once per new version — not every poll. Mirrors OpenClaw's `lastNotifiedVersion` gating.

State file: `/tmp/miniclosedai-upgrade-check.json`

```json
{
  "last_checked_at":   "2026-05-10T14:30:00+00:00",
  "last_remote_sha":   "abc123...",
  "first_seen_at":     "2026-05-10T14:30:00+00:00",
  "last_notified_sha": "abc123..."
}
```

Lifecycle:

| Transition | What happens |
|---|---|
| `current == latest` (no update) | `last_remote_sha` and `first_seen_at` cleared. `last_notified_sha` retained so we don't re-announce a now-applied version if it ever comes back. |
| `current != latest`, never seen | `last_remote_sha = latest`, `first_seen_at = now`. Log fires. `last_notified_sha = latest`. |
| Same `latest` re-observed | Nothing changes. `first_seen_at` stays put (so the UI hint stays consistent). No log line. |
| New `latest` (different from `last_remote_sha`) | `last_remote_sha`, `first_seen_at` re-stamped. Log fires again. `last_notified_sha` updated. |
| Cache window (`last_checked_at` < 10 min ago) | Docker mode skips the GitHub API call and reuses `last_remote_sha`. Git mode still does its local `git fetch` (cheap, no rate limit). |

The state file is only written by `_record_update_state` in `app.py`; the upgrade script doesn't touch it. Failures to read or write are swallowed — a corrupted/missing file just means the next call rebuilds the state from scratch, never breaks `/api/upgrade/status` itself.

### Why not a server-side ticker?

OpenClaw runs a `setTimeout` loop server-side (a "gateway update check") so it detects releases even with no client connected. MiniClosedAI doesn't need this: the GUI polls `/api/upgrade/status` every 10 minutes while a tab is open, and a closed tab means there's no UI to notify anyway. Adding a server ticker would duplicate work the client poll already does. The `first_seen_at` stamp + once-per-version log are the two pieces from OpenClaw worth keeping; the ticker isn't.

---

## Prompt generator

A small client-side affordance above the System Prompt textarea that turns a free-text description into a complete system prompt — and, when a prompt already exists, rewrites it using the running conversation as evidence. Pure GUI feature: no new server endpoints, no DB changes, all logic in `static/app.js`.

### Two modes, one button

The same toggle button switches label based on whether the system-prompt textarea has any content:

| State | Label | Meta-prompt sent | User payload |
|---|---|---|---|
| Empty textarea | **✨ Generate prompt** | `_PROMPT_GEN_META_PROMPT` (write a fresh system prompt) | `<description>` |
| Non-empty textarea | **✨ Improve prompt** | `_PROMPT_IMPROVE_META_PROMPT` (rewrite preserving what works) | Three labeled sections: `=== CURRENT SYSTEM PROMPT ===` + `=== CONVERSATION TRANSCRIPT ===` + `=== IMPROVEMENT REQUEST ===` |

The mode is decided live on every input event (`_promptGenMode()` in `static/app.js`), so the label flips in real time as the user types or clears the prompt. Programmatic value sets (loading a conversation, "Reset defaults") explicitly call `_updatePromptGenAffordance()` since assigning `.value` doesn't fire `input`.

### Wire format

The button reuses `POST /api/chat/stream` — the same legacy endpoint the dashboard uses for non-saved-conversation inference. No new backend code:

```
POST /api/chat/stream
Content-Type: application/json

{
  "backend_id": <selected backend id>,
  "model":      "<selected model name>",
  "system_prompt": "<meta-prompt for the chosen mode>",
  "messages": [{"role": "user", "content": "<description or 3-section payload>"}],
  "max_tokens": 4000,
  "temperature": 0.5,
  "think": false
}
```

The response is consumed as standard SSE; each `chunk` event is appended to the System Prompt textarea live. After the stream ends the final value is right-trimmed (models often append a stray newline) and an `input` event is dispatched to the textarea so the existing `saveSettings()` + `scheduleSaveToConversation()` listeners persist the new prompt.

### Conversation transcript (improve mode only)

The transcript section is built from `state.messages` — the in-memory messages of the active conversation:

- **Last 30 turns only**, to stay well under any backend's context window even on long chats.
- **`_userVisibleText(m)`** is reused to extract the typed text from multimodal turns; PDF/image content is *not* inlined.
- **Empty turns dropped**, **`role: "system"`** turns dropped (only `user` / `assistant` appear).
- If `state.messages` is empty, the section reads `(no conversation has been run against this prompt yet)` so the model knows it can't lean on evidence.

### Model picker (Settings → Prompt Generator)

The section appears in **⚙️ Settings** when at least one enabled, reachable backend has at least one model. The dropdown is grouped by `<optgroup>` per backend (mirrors the dashboard's main model picker). Option values are encoded `<backend_id>::<model_name>` so the change handler recovers both halves and persists them as a JSON-encoded `{backend_id, model}` blob in `localStorage` under the key `miniclosedai:promptGenChoice`.

Resolution order on every refresh (called once at init + every 60 s):

1. Saved `(backend_id, model)` exact pair → use it if the backend is still enabled+running and still serves that model.
2. Saved model name → use any backend that currently advertises it (handles backend re-registration where the id changed).
3. No match → first model on the first enabled+running backend.

The 60-second poll is what makes the affordance auto-appear/disappear when a backend's reachability flips. The same `/api/models` payload that powers the dashboard's model dropdown is reused — no new endpoint.

### Failure handling

The streaming loop wraps the whole flow in `try/catch`. Any error (network, backend down, malformed SSE frame, model returns `error` event) restores **the original prompt in Improve mode** so a streaming hiccup never destroys the user's existing system prompt. The status line flips red with `"Improvement failed: <reason>"` (or `Generation failed: …`); the textarea is re-enabled and re-focused.

### What this is NOT

- **Not a server-side endpoint**. No `/api/prompt-gen` or similar; the LLM call is just `/api/chat/stream` with a custom system prompt + user message.
- **Not persisted to the conversation history.** The generated prompt lands in the System Prompt field (and is auto-saved there), but the meta-prompt + the user's description are *not* stored anywhere; only the resulting system prompt is.
- **Not a separate model abstraction.** Whatever backends/models the user has registered for normal chat are the same ones offered here; the choice is per-browser (localStorage), not per-conversation.

---

## Activity logs

LM-Studio-style request/response viewer surfaced via the **Logs** nav button and the `/api/logs` endpoint. Every chat call across every endpoint records one entry; the GUI polls it on a 2-second tick.

### Architecture

```
Chat endpoints ──► chat_logs.record_chat(...) ──► deque(maxlen=500)
                                                          │
                                                          ▼
                              GET /api/logs   ──►  newest-first JSON list
                              DELETE /api/logs ─►  wipes the deque
```

A single in-process `collections.deque(maxlen=500)` in [`logs.py`](./logs.py) holds the most-recent entries. Thread-safe via one `threading.Lock` since FastAPI may dispatch sync handlers from worker threads. Lifetime is process-bound — restart wipes it. The buffer is intentionally **not** persisted to SQLite or any file: this is a debugging surface, not an audit log; persistence would push memory-grade IO patterns onto disk and conflict with the "drop entries when full" semantic the `maxlen` deque provides for free.

### Instrumented endpoints

All five chat-call paths emit a log entry exactly once per call (success or error):

| Endpoint | Kind | Instrumentation site |
|---|---|---|
| `POST /api/chat` | `sync` | After `llm.chat` returns (or in the `except`). |
| `POST /api/chat/stream` | `stream` | At end-of-stream (with the accumulated `collected` text), or in the `except` mid-stream. |
| `POST /api/conversations/{id}/chat` | `sync` | Same shape as `/api/chat`, plus the `attachments` filename list. |
| `POST /api/conversations/{id}/chat/stream` | `stream` | At end-of-stream with both `collected` content and `thinking_collected`. |
| `POST /v1/chat/completions` | `sync` / `stream` | Both branches recorded; the stream variant accumulates content into a local `collected` list so the log gets the full output, not just metadata. |

The `latency_ms` field measures from the function entry point to the moment the LLM call completes (or errors). For stream endpoints that's the time-to-last-token, not time-to-first-token — chosen because a partial stream that fails mid-flight should still show how far the model got.

### Truncation and size discipline

```python
_RESPONSE_PREVIEW_CHARS = 2000   # per response
_THINKING_PREVIEW_CHARS = 1000   # per thinking trace
_PER_MESSAGE_PREVIEW   = 500     # per message
_MESSAGES_TAIL         = 3       # only the last N messages survive into the entry
```

Each truncation point also records the original length so the UI can show *"first 2000 chars of a 17,432-char response."* Multimodal `content` arrays are flattened to text parts joined with spaces plus a `[+N image(s)]` suffix — base64 image bytes are **never** stored in the log buffer, both for memory and for usefulness (a 30 KB log entry full of base64 is unreadable).

### Polling protocol

The GUI uses `since_id` for cheap incremental polling:

```
First tick:        GET /api/logs                    → all entries
Subsequent ticks:  GET /api/logs?since_id=<max>     → only new entries
```

`since_id` filtering happens server-side after the buffer snapshot, so the client always sees a consistent view (no race where an entry could appear in two consecutive `since_id` responses). When the polling resumes after a Pause or after returning from another nav tab, the next tick fetches everything newer than the highest id the client has cached — at most 500 entries on a wraparound, typically a handful.

### What it deliberately doesn't do

- **No persistence.** Server restart = empty buffer. Use the uvicorn stdout / `journalctl` if you need a true audit trail.
- **No authentication on the read.** Same security model as the rest of the app — local-only / trusted-LAN by default. Don't expose `/api/logs` to a hostile network; the previews can contain user input.
- **No filtering by backend or endpoint server-side.** The GUI does in-memory substring search across the buffer it already has. At 500 entries this is cheap; if the buffer ever grows server-side filtering becomes worthwhile.
- **No webhook / SSE push.** Polling is simpler and the latency cost (2 seconds) doesn't matter for a debugging view. SSE would also require keeping connections open per tab; the polling approach gracefully handles tab close, page navigate, and laptop sleep.

---

## Database

Single SQLite file `miniclosedai.db`, auto-created at startup. One table:

```sql
CREATE TABLE conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL DEFAULT 'New Chat',
    model         TEXT    NOT NULL,
    system_prompt TEXT    NOT NULL DEFAULT 'You are a helpful AI assistant.',
    messages      TEXT    NOT NULL DEFAULT '[]',   -- JSON array of {role, content, params}
    params        TEXT    NOT NULL DEFAULT '{}',   -- JSON: {temperature, max_tokens, top_p, top_k, think, max_thinking_tokens}
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

Inspect from the CLI:

```bash
sqlite3 miniclosedai.db '.schema'
sqlite3 miniclosedai.db 'SELECT id, title, model, length(messages) FROM conversations;'
```

Delete the file to fully reset. Copy it to migrate state to another machine.

---

## Configuration

Environment variables the app reads:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Default URL for the built-in Ollama backend. Used by `db.py:23` (seed) and `llm.py:32` (client default). In Docker compose, set to `http://ollama:11434` so MiniClosedAI reaches the sibling Ollama service over the internal network. |
| `MINICLOSEDAI_DB_PATH` | `<repo>/miniclosedai.db` | Override the SQLite file location. Set to `/app/data/miniclosedai.db` in the Docker container so the `miniclosedai_db` named volume can persist state without mounting over the app code tree. Unset in local dev = original path, no behavior change. |
| `MINICLOSEDAI_NO_OLLAMA` | unset | "Lite" mode — don't seed the built-in Ollama backend (and auto-disable an existing one). For installs that only use external/cloud endpoints. Accepts `1`/`true`/`yes`/`on`. See [Lite mode](#docker-deployment). |
| `MINICLOSEDAI_DISABLE_RELAY_AUTO_ROUTE` | unset | Set to `1` to disable the auto-route that sends a chat to a matching relay (e.g. Interdata) when the relay serves the bot's model. Keeps every bot strictly on its pinned backend. |
| `MINICLOSEDAI_EMBED_MODEL` | `nomic-embed-text` | Embedding model for the knowledge base (RAG). Must be pulled on an Ollama backend. |
| `MINICLOSEDAI_EMBED_BACKEND_ID` | unset | Force a specific backend id for embeddings. By default embeddings resolve to the built-in/local Ollama (see [Knowledge base](#knowledge-base-rag)), so a bot chatting on a cloud relay still embeds locally. |
| `MINICLOSEDAI_KB_TOP_K` | `8` | How many retrieved knowledge chunks are injected into the prompt per turn (balanced across the bot's documents). |
| `MINICLOSEDAI_MCP_MAX_ITERS` | `6` | Safety cap on MCP tool-call rounds per turn (model→tools→model…). |
| `MINICLOSEDAI_PDF_MAX_MB` / `_PAGES` / `_CHARS` | `10` / `50` / `30000` | Caps for the **chat-attachment** PDF path (a PDF stuffed into one chat turn). |
| `MINICLOSEDAI_PDF_FULL_MAX_MB` / `_PAGES` / `_CHARS` | `200` / `5000` / `5000000` | Book-friendly caps for the **knowledge-base** PDF path (`/api/extract-pdf?full=1`) — the text is chunked + embedded, so length isn't a context concern. |

The listen port is set in `app.py` (`port=8095`) or via the uvicorn `--port` flag. In Docker, port mapping lives in `docker-compose.yml` (`ports: ["127.0.0.1:8095:8095"]`).

Ollama-side env vars (set on the `ollama` service in compose):

| Variable | Default (in compose) | Purpose |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `5m` | Keep models resident in VRAM between requests so switching among the three baked models doesn't unload/reload. Tune down if you want to free VRAM for other workloads between requests. |

---

## File layout

```
miniclosedai/
├── app.py                     # FastAPI routes (models, conversations, chat, SSE)
├── llm.py                     # Client: Ollama + OpenAI-compat, think support
├── db.py                      # SQLite schema + helpers (MINICLOSEDAI_DB_PATH override)
├── logs.py                    # In-memory ring buffer for the Logs page (chat req/resp records)
├── requirements.txt           # fastapi, uvicorn, httpx, pypdf, python-multipart
├── upgrade.sh                 # in-place upgrade with auto-rollback (CLI + GUI button trigger)
├── test_e2e.py                # 39-test single-file suite, no pytest
├── static/
│   ├── index.html             # Single-page UI
│   ├── style.css              # Dark-mode, responsive, no-cache headers served
│   └── app.js                 # All frontend logic
├── scripts/
│   └── bake-models.sh         # Build-time Ollama daemon + pull + clean-kill
├── Dockerfile                 # App image — python:3.12-slim, ~160 MB
├── Dockerfile.ollama          # Ollama image with 3 models baked in, ~10.3 GB
├── docker-compose.yml         # Two services, GPU reservation, healthchecks, volumes
├── docker-compose.cpu.yml     # Override: strip GPU via `devices: !reset []`
├── docker-compose.lite.yml    # Single-service: app only, MINICLOSEDAI_NO_OLLAMA=1, no GPU/models
├── .dockerignore              # Build-context exclusions
├── README.md                  # Quick start + recipes
├── DOCUMENTATION.md           # This file
├── INSTALL.md                 # Per-OS Ollama install guide
├── Support Ticket Router.md   # Recipe
├── Inbound Lead Qualifier.md  # Recipe
├── RAG Query Router.md        # Recipe (Bonsai-paired)
├── Doctors Office Bot.md      # Recipe (conversational, qwen3:8b)
├── Restaurant Reservations Bot.md  # Recipe (conversational, qwen3:8b)
├── Hotel Reservations Bot.md       # Recipe (conversational, qwen3:8b)
├── Dentist Appointment Bot.md      # Recipe (conversational, qwen3:8b)
├── CLAUDE.md                  # Notes for AI coding assistants
└── miniclosedai.db            # (runtime-generated, gitignored; Docker: in named volume)
```

Backend total: ~400 LoC Python. Frontend total: ~650 LoC JS + ~350 LoC CSS + ~130 LoC HTML.

---

## Security

**MiniClosedAI has no authentication or authorization.** Anyone who can reach the HTTP port can:

- Read, create, update, or delete any conversation.
- Send chat requests that consume CPU/GPU.

This is intentional — the intended deployment is local-only on `127.0.0.1`, or on a trusted LAN.

If you bind to `0.0.0.0` and expose over a network, only do so on a **trusted network**. For anything beyond that, put the app behind:

- A reverse proxy (nginx / Caddy) with basic auth or OAuth2-Proxy.
- A VPN (Tailscale, WireGuard).
- A firewall allowlist.

The app does not ship with HTTPS. `navigator.clipboard` requires HTTPS or `localhost` — the "Copy" button in the API modal falls back to `document.execCommand("copy")` over plain-HTTP LAN, which works on all current browsers.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says *"Ollama is not running"* | Start the daemon: `ollama serve` (Linux) or launch the Ollama app (macOS/Windows). Verify with `curl http://localhost:11434/api/tags`. |
| Dropdown shows *"no local chat models installed"* | `ollama pull llama3.2:3b` (or any other model). Refresh. Cloud and embedding-only models are filtered out by design. |
| First message is slow | Ollama loads the model into memory on first use (5–30 s). Subsequent messages are fast. |
| Responses truncate mid-sentence | Raise **Max tokens** in the sidebar. |
| Thinking-only models never produce visible output | Set **Thinking** to **Off**, raise **Max tokens**, or set a generous **Max thinking tokens** so the model finishes reasoning before the cap. |
| Out-of-memory errors | Pick a smaller model (`llama3.2:1b`, `gemma2:2b`, `tinyllama`). |
| Port 8095 already in use | `uvicorn app:app --port 8096` |
| Clipboard "Copy" button does nothing on LAN | Expected pre-fix; current code falls back to legacy copy automatically. If it still fails, select the code manually and Ctrl+C. |
| Can't access from phone on same WiFi | Bind to `0.0.0.0`: `uvicorn app:app --host 0.0.0.0 --port 8095`. Also allow the port in your host firewall (`sudo ufw allow 8095/tcp`). |
| Browser devtools floods with `ERR_CONNECTION_REFUSED` on `/api/pulls`, `/api/models`, `/api/logs` | Browser can't reach the FastAPI server. **Most common cause:** browser running on a different machine than the server, but URL bar still says `localhost:8095` (which means *the browser's* machine, not the server's). Switch to `http://<server-lan-ip>:8095`. **Confirm:** from the *server's* shell, `curl http://127.0.0.1:8095/api/logs` should return JSON — if it does, the server is healthy and the problem is networking/URL; if it doesn't, the uvicorn process isn't running. |
| Logs page renders empty even though chats are happening | Open devtools Network tab and watch the `/api/logs` request. A 200 with `{"logs": []}` means the page is fine — there's just no activity in *this* server's buffer (e.g. you're sending chats to a different host, or the server was restarted recently and lost the buffer). A failed request means a connection problem — see the row above. |

---

## Development notes

- **No build step.** Edit `static/*` and refresh the browser (hard-refresh to bust cache).
- **Hot reload**: `uvicorn app:app --reload`.
- **Interactive API docs**: `http://localhost:8095/docs` (Swagger UI) and `/redoc`.
- **Add a new param**: update the `ChatRequest` / `ConversationChatRequest` / `ConversationCreate` / `ConversationUpdate` pydantic models, extend `_PARAM_KEYS`, thread through `_resolve_conversation_chat()` and the `llm.chat_stream()` call sites, and add the input to `static/index.html` + `static/app.js`.

---

## Testing

Full end-to-end coverage lives in **`test_e2e.py`** at the repo root. Run:

```bash
python test_e2e.py
```

28 tests, ~1.5 seconds, no external dependencies (no pytest), no real Ollama or LM Studio required — upstream backends are simulated in-process via two tiny `http.server` instances. The test DB is a tempfile; your real `miniclosedai.db` is never touched. Exits 0 on all-pass, 1 on any failure.

For the full coverage matrix and hook-setup instructions, see **[README → Testing](./README.md#testing)**.

---

## License

MIT.
