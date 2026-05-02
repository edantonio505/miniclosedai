# MiniClosedAI

A tiny, 100%-local LLM playground. Chat with small Ollama models (1B–10B parameters), tweak sampling parameters live, and turn each saved chat into a callable API endpoint. **No cloud, no API keys, no costs.**

Built with **FastAPI** (3 Python deps), vanilla JS, and SQLite. Runs on a laptop.

<p align="center">
  <img src="miniclsedai1.png"
       alt="MiniClosedAI — a saved Pikachu bot responding to a message, with system prompt and parameters visible in the sidebar"
       width="820">
  <br><em>A saved bot. The sidebar is the full control panel; the chat is the live test.</em>
</p>

<p align="center">
  <img src="miniclosedai2.png"
       alt="Sentiment classifier bot: a reasoning model's 'Thoughts' block is expanded above the final one-word answer ('positive')"
       width="820">
  <br><em>Reasoning models stream their chain-of-thought into a collapsible block, separate from the final answer.</em>
</p>

<p align="center">
  <img src="miniclosedai3.png"
       alt="API Integration Code modal with three toggle groups — Language, Mode, Style — showing the JavaScript / Non-streaming / OpenAI-compat variant pointed at this instance"
       width="820">
  <br><em>Every saved chat is a microservice. Copy the snippet as cURL, Python, or JavaScript — native or OpenAI-SDK-compatible.</em>
</p>

<p align="center">
  <img src="miniclosedai4.png"
       alt="Support Ticket Router bot: the sidebar shows the JSON-extraction system prompt and deterministic sampling params; the chat shows a real inbound ticket on the right and the assistant's pretty-printed, syntax-highlighted JSON response next to it"
       width="820">
  <br><em>The Support Ticket Router recipe in action. A real inbound ticket (top right) goes in; structured, pretty-printed, syntax-highlighted JSON comes out — ready for a downstream CRM, Linear, or Slack webhook to consume. Recipes for this and a sister <a href="#7-inbound-lead-qualifier--full-walkthrough">Lead Qualifier</a> bot are documented as standalone walkthroughs.</em>
</p>

<p align="center">
  <img src="miniclosedai5.png"
       alt="Sentiment classifier chat with the header's download icon hovered, showing the tooltip 'Download this chat as CSV (input,output)' — saves the conversation as a two-column SFT dataset"
       width="820">
  <br><em>Every chat doubles as a fine-tuning dataset. The download icon in the header exports the conversation as a two-column <code>input,output</code> CSV — edited assistant responses become the ideal targets, ready for SFT. See <a href="#curating-fine-tuning-data">Curating fine-tuning data</a>.</em>
</p>

<p align="center">
  <img src="miniclosedai6.png"
       alt="MiniClosedAI Settings page with three registered LLM endpoints: Ollama (built-in) at localhost:11434 showing 23 reachable models, LM Studio at 192.168.0.110:1234/v1 with 7 models and an API key set, and Bonsai at localhost:8080/v1 with 1 model — each card has Edit and (for non-built-in) Delete buttons"
       width="820">
  <br><em>Settings → LLM Endpoints. Register as many backends as you want: the built-in Ollama, an LM Studio instance on your LAN, and PrismML's 1-bit Bonsai server all coexist. Each card shows its kind, base URL, API-key status, and a live reachability count. Models from every reachable endpoint merge into one grouped dropdown on the Dashboard, OpenWebUI-style. See <a href="#connecting-lm-studio-and-other-openai-compatible-endpoints">Connecting LM Studio and other endpoints</a> and <a href="#adding-bonsai-prismmls-1-bit-8b--step-by-step">Adding Bonsai</a>.</em>
</p>

<p align="center">
  <img src="miniclosedai7.png"
       alt="Doctor's Office Bot chat running on qwen3:8b. The sidebar shows the system prompt with the 'Required-fields gate (HARD RULE)' section visible. The chat shows the bot asking for patient details, the user's one-shot info-dump reply ('Ed Johnson, 1989-02-23, (347) 853-8734, new patient. Routine checkup, any available provider. Morning works best...'), and the bot's response — a natural confirmation sentence followed by a fenced create_appointment JSON block rendered as a code block in the chat, containing patient, visit, insurance, and confirmation sub-objects"
       width="820">
  <br><em>A conversational bot that emits structured actions. The <a href="#9-doctors-office-chatbot--full-walkthrough">Doctor's Office Bot</a> replies in natural language during info gathering, then emits a fenced <code>create_appointment</code> JSON block the moment every required field is present. Downstream apps strip the fence and dispatch to the real scheduler. Works with <code>qwen3:8b</code> on Ollama — full system prompt, worked examples, and the load-bearing few-shot section in <a href="./Doctors%20Office%20Bot.md"><code>Doctors Office Bot.md</code></a>.</em>
</p>

![stack](https://img.shields.io/badge/FastAPI-0.110+-009688) ![Ollama](https://img.shields.io/badge/Ollama-local-000000) ![license](https://img.shields.io/badge/license-MIT-blue)

> The defining idea: **each saved conversation is an addressable microservice.** You craft a system prompt + sampling params once in the UI, and that chat becomes a stable URL you can call from anything that speaks HTTP — including any OpenAI SDK.

---

## Table of contents

1. [What it is](#what-it-is)
2. [Requirements](#requirements)
3. [Install](#install) · [Docker quick start (with baked models)](#docker-quick-start-with-baked-models)
4. [Run](#run)
5. [Your first bot — 60 seconds](#your-first-bot--60-seconds)
6. [UI guide](#ui-guide)
7. [Connecting LM Studio and other OpenAI-compatible endpoints](#connecting-lm-studio-and-other-openai-compatible-endpoints)
8. [The microservice pattern](#the-microservice-pattern)
9. [API reference — native endpoints](#api-reference--native-endpoints)
10. [OpenAI-compatible endpoint](#openai-compatible-endpoint)
11. [Recipes — common bot patterns](#recipes--common-bot-patterns)
12. [Getting good responses from small models](#getting-good-responses-from-small-models)
13. [Curating fine-tuning data](#curating-fine-tuning-data)
14. [LAN access](#lan-access)
15. [Troubleshooting](#troubleshooting)
16. [Testing](#testing)
17. [Project layout](#project-layout)
18. [Security](#security)
19. [License](#license)

---

## What it is

MiniClosedAI is a single-user, single-process web app that wraps **local** LLMs into a playground UI. Its feature list is short on purpose:

- 🧠 **100% local inference** — no data leaves your machine.
- 🔌 **Multi-endpoint, OpenWebUI-style** — register Ollama plus any number of OpenAI-compatible servers (LM Studio, vLLM, [PrismML Bonsai (1-bit 8B)](https://github.com/PrismML-Eng/Bonsai-demo), raw `llama.cpp --server`, etc.). One grouped model dropdown lists everything; each saved chat picks one endpoint + model.
- 🎛️ **Live parameter sliders** — temperature, max tokens, top-p, top-k, thinking level, max thinking tokens. Every change auto-saves to the active conversation.
- 🔁 **Per-chat microservice endpoints** — each saved conversation is an addressable URL that replays your GUI-configured bot. Callers just send `{"message": "..."}`.
- 💭 **Reasoning-model aware** — `thinking` and `content` tokens from models like qwen3, deepseek-r1, and gpt-oss stream separately; "thoughts" appear in a collapsible block. `max_thinking_tokens` is a soft cap: visible reasoning is hidden but the model keeps running so the answer still arrives.
- 📎 **File attachments — images, PDFs, and text files** — paperclip in the composer (and clipboard paste) attaches files to a chat turn. Vision models (`llava`, `gemma4`, `qwen3.6`, `*-vision`, `*-vl`, etc.) see images natively over both Ollama's `/api/chat` and OpenAI's `chat/completions` formats. PDFs are extracted to text server-side with `pypdf` (50-page / 30 000-char caps), and `.txt` / `.md` / `.csv` / source-code files are read inline. Attached file bodies get prepended to the user's message; the bubble shows just the user's question + thumbnails / doc chips. Soft-warns when an image is attached to a model that doesn't pattern-match a vision model. **No extra setup** — `pypdf` ships in `requirements.txt`.
- ⏹ **Manual stop** — a Stop button in the composer aborts the stream cleanly.
- 🔁 **OpenAI-SDK-compatible server** — drop MiniClosedAI in place of `api.openai.com` with a one-line `base_url` change. Every bot appears as a "model" to the SDK; calls route to whichever backend that bot is pinned to.
- 🎨 **Polished UI** — left activity bar (Dashboard / Settings), Light / Dark / System theme, draggable splitters (sidebar width + system-prompt height), Gemini-style empty state, syntax-highlighted API-code modal with Streaming/Non-streaming and Native/OpenAI variants.
- 🗂️ **SQLite persistence** — one file, two tables (`backends`, `conversations`), JSON columns for messages. Delete to reset, copy to migrate.
- 🧪 **Fine-tuning data curation built-in** — edit any assistant response in place to turn it into the ideal output, then download the whole conversation as a two-column `input,output` CSV ready for SFT. The original pristine response is preserved under `original_content` for audit / DPO later.

**What it is not:** a production inference platform. No authentication, no rate limiting, no multi-user. Intended for localhost or a trusted LAN.

---

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or newer | `python3 --version` |
| At least one LLM backend | Ollama *or* LM Studio *or* any OpenAI-compatible server | Ollama is the built-in default. **Optional in lite mode** — see below. |
| Ollama | any recent release | Optional if you only use OpenAI-compat backends or run in [lite mode](#lite-install-no-local-ollama). Default URL `http://localhost:11434` |
| LM Studio | any recent release with the *Local Server* feature | Optional. Serves `/v1` at (typically) `http://host:1234/v1` |
| At least one model | pulled (Ollama) or loaded (LM Studio) | see [recommended models](#recommended-models-1b10b). In lite mode the model lives on the *remote* endpoint, not this machine. |
| RAM | ~2 GB for 1–3B models; 8+ GB for 7–9B | More for 20B+. **Lite mode needs only ~150 MB** — inference runs elsewhere. |
| Disk | ~1–10 GB per model | Plus 200 MB for the app itself. **Lite mode**: ~50 MB total — no model storage needed. |

Five Python dependencies — `fastapi`, `uvicorn`, `httpx`, `pypdf`, `python-multipart`. That's it. The same five whether you run heavy or lite.

**Lite mode** (no local Ollama) drops every requirement except Python + the five pip packages. See [Lite install](#lite-install-no-local-ollama) below.

---

## Install

Two methods (**Docker** or **bare-metal**), each with two modes — **heavy** (Ollama + baked models, ~10 GB image) or **lite** (no local Ollama; you point at any external Ollama / OpenAI-compatible endpoint via the Settings page, ~160 MB image, runs on any laptop). Pick whichever combination fits your hardware and use case:

| | Heavy (with built-in Ollama) | Lite (no Ollama, BYO endpoint) |
|---|---|---|
| **Docker** | [Docker quick start](#docker-quick-start-with-baked-models) — full stack, three baked models, GPU recommended. | [Docker — lite](#docker--lite-no-built-in-ollama) — single ~160 MB container, zero GPU. |
| **Bare-metal** | [Manual install](#1-ollama) — install Ollama + Python venv. | [Lite install](#lite-install-no-local-ollama) — `pip install -r requirements.txt` and you're done. |

Lite mode is the right pick when you have an inference server *somewhere else* — another machine on your LAN, a cloud Ollama relay, an LM Studio, vLLM, or any OpenAI-compatible URL — and you just want the playground UI on this machine.

### Docker quick start (with baked models)

One-command setup that boots MiniClosedAI **and** Ollama with three small-but-capable models (`llama3.2:3b`, `qwen2.5:3b`, `gemma2:2b` — about 5.5 GB of weights) already on disk inside the image. No `ollama pull` step. No host Ollama install. Works on any Linux with Docker + NVIDIA GPU; CPU-only fallback below.

#### Requirements

| | Version | Notes |
|---|---|---|
| Docker Engine | 20.10+ (Compose v2 bundled) | `docker --version`. Use `docker compose` (space), not `docker-compose` (hyphen, v1 — ignores healthcheck conditions). |
| NVIDIA drivers + `nvidia-container-toolkit` | current | Linux: `sudo apt install nvidia-container-toolkit && sudo systemctl restart docker`. Without it, `up` fails with *"could not select device driver nvidia with capabilities [[gpu]]"*. |
| Free disk | ~20 GB | Build-time working space on Docker's `data-root` — ~10.3 GB final Ollama image (base ships CUDA/ROCm libs) + model blobs + layer commit overhead. |

#### Bring it up

```bash
git clone <this repo> && cd miniclosedai
docker compose up -d --build
```

First build takes ~8–15 min (downloads three models from `registry.ollama.ai`). Subsequent `up -d` calls boot in ~30 s. When both services report `healthy` in `docker compose ps`, open <http://127.0.0.1:8095> — the model dropdown lists the three baked models under **Ollama (built-in)**.

#### CPU-only hosts

If you don't have (or don't want to use) an NVIDIA GPU:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

The override strips the GPU reservation. Inference on the 3B models will be noticeably slower; `gemma2:2b` stays usable in real time.

#### Adding or removing models after build

Models pulled at runtime persist in the `ollama_models` named volume across restarts and image rebuilds:

```bash
# Add one
docker compose exec ollama ollama pull phi3:mini

# Remove one
docker compose exec ollama ollama rm phi3:mini

# List everything
docker compose exec ollama ollama list
```

Refresh the MiniClosedAI page — the dropdown updates automatically (the app re-queries `/api/tags` on each page load).

#### What's persisted and what isn't

| Data | Where | Survives `down` | Survives `down -v` |
|---|---|---|---|
| Chat history, saved bot configs, backends table | `miniclosedai_db` volume → `/app/data/miniclosedai.db` | ✅ | ❌ |
| Runtime-pulled models | `ollama_models` volume → `/root/.ollama` | ✅ | ❌ |
| Baked models | Ollama image layer | ✅ (comes back on next build/up) | ✅ |

#### Security — loopback-only by default

The compose file binds MiniClosedAI to `127.0.0.1:8095:8095` — **accessible only from localhost**. MiniClosedAI has zero authentication. To expose the UI to your LAN (phones, other machines), change the port mapping to `"8095:8095"` and read the [LAN access](#lan-access) + [Security](#security) sections first.

#### Troubleshooting Docker

| Symptom | Fix |
|---|---|
| `could not select device driver "nvidia"` | `nvidia-container-toolkit` not installed. `sudo apt install nvidia-container-toolkit && sudo systemctl restart docker`. |
| Build fails with `ENOSPC` during `ollama pull` | Free disk space on Docker's `data-root` (`docker system df`, then `docker system prune`). Need ~15 GB headroom. |
| Stack up but UI shows empty model dropdown | `docker compose exec ollama ollama list` — confirms the models baked in. If list is empty, one of the build's `bake-models.sh` layers silently failed; `docker compose build --no-cache ollama` to rebuild. |
| `miniclosedai` can't reach `ollama` | Verify the env var: `docker compose exec miniclosedai env \| grep OLLAMA_URL` — must be `http://ollama:11434`. If it's `http://localhost:...`, the container isn't inheriting the compose env. |
| Switching GPUs ↔ CPU doesn't take effect | Docker caches a lot. `docker compose down && docker compose up -d --build` to force. |

### Docker — lite (no built-in Ollama)

Single-service compose file. Brings up **only** the MiniClosedAI web app (~160 MB image) — no Ollama container, no GPU passthrough, no `nvidia-container-toolkit` requirement, no model layers. The dashboard starts empty; you register your external endpoint(s) through the Settings page and the dropdown lights up.

```bash
git clone <this repo> && cd miniclosedai
docker compose -f docker-compose.lite.yml up -d --build
# → open http://127.0.0.1:8095
# → click ⚙️ Settings → Add endpoint
```

Build is ~30 seconds (one Python deps layer, no model pulls). The compose file sets `MINICLOSEDAI_NO_OLLAMA=1` in the container env so the built-in Ollama backend isn't seeded — the dashboard's empty state shows a "Welcome — let's add your first endpoint" CTA that flips to the Settings tab in one click.

| When to pick this | When to pick the heavy default |
|---|---|
| You have an Ollama (or OpenAI-compat server) on another machine, in a VPS, or behind a relay. | You want everything on one host. |
| Laptop with no GPU, or with limited disk. | Workstation or server with NVIDIA GPU + ≥20 GB free disk. |
| You don't want a 10 GB image to build/store. | You want zero external dependencies. |
| Your hardware can't run a 7–9B model locally. | Your hardware can. |

To switch back to the heavy default later, just bring the lite stack down and start the standard one — the SQLite DB lives in the same `miniclosedai_db` volume, so your conversations persist:

```bash
docker compose -f docker-compose.lite.yml down
docker compose up -d --build
```

The auto-disable on the built-in row is reversible — running the standard compose without `MINICLOSEDAI_NO_OLLAMA` won't re-flip the row's `enabled` flag automatically. If you've previously been in lite mode and the built-in row is disabled, re-enable it once via the Settings page (or set its `enabled = 1` in the DB).

To run without Docker — keep reading.

### 1. Ollama

**macOS**
```bash
brew install ollama
brew services start ollama
# or download Ollama.app from https://ollama.com/download
```

**Linux**
```bash
curl -fsSL https://ollama.com/install.sh | sh
# Systemd installs automatically. To verify:
systemctl status ollama
curl http://localhost:11434/api/tags    # → {"models":[]}
```

**Windows**

Download and run `OllamaSetup.exe` from <https://ollama.com/download>. It installs as a background service. Verify with PowerShell:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

### 2. A model (pick one to start)

```bash
ollama pull llama3.2:3b       # great default, ~2 GB
# or
ollama pull qwen3:8b          # reasoning-capable, ~5 GB
# or
ollama pull gemma2:2b         # very fast, ~1.6 GB
```

Full list of recommended models is below.

### 3. MiniClosedAI

```bash
cd miniclosedai
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Lite install (no local Ollama)

If you don't want to install Ollama on this machine — for example, you'll point at a remote Ollama, an LM Studio on your LAN, or any OpenAI-compatible endpoint — **skip steps 1 and 2 above and run just step 3**, then start the app with the `MINICLOSEDAI_NO_OLLAMA=1` env var:

```bash
git clone <this repo> && cd miniclosedai
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt       # 5 deps total, no system packages

MINICLOSEDAI_NO_OLLAMA=1 \
  python -m uvicorn app:app --host 0.0.0.0 --port 8095
```

(On Windows PowerShell: `$env:MINICLOSEDAI_NO_OLLAMA=1; python -m uvicorn app:app --host 0.0.0.0 --port 8095`)

Open <http://localhost:8095>. The dashboard's empty state shows **"Welcome — let's add your first endpoint"** with a button that takes you straight to **Settings → Add endpoint**. Fill in:

- **Name** — anything you like (e.g. *Home server Ollama*).
- **Kind** — `ollama` for native Ollama servers (recommended; supports `think: false` properly), `openai` for LM Studio / vLLM / llama.cpp / Bonsai / any OpenAI-compatible URL.
- **Base URL** — the full URL of your server. For native-Ollama use the host root (e.g. `https://my-server.example.com` — no `/v1` suffix). For OpenAI-compat include `/v1` (e.g. `http://192.168.1.50:1234/v1`).
- **API key** *(optional)* — sent as `Authorization: Bearer <key>` on every request. Use this if your endpoint is gated by a Bearer token.
- **Custom headers** *(optional)* — any extra headers your endpoint requires.

Save. The endpoint's models appear in the dashboard's model dropdown immediately. From there everything else (chat, attachments, API Code modal, fine-tuning data export) works exactly the same as the heavy install — only the inference happens elsewhere.

**What `MINICLOSEDAI_NO_OLLAMA=1` does:**

- On a fresh database, **the built-in Ollama backend isn't seeded**. The dashboard starts with zero endpoints registered.
- On an existing database that previously ran in heavy mode, **the built-in row is auto-disabled** at startup (its `enabled` flag is set to `0`) so it doesn't show as a permanently-broken endpoint in the dropdown.
- Without the env var, behavior is identical to the heavy default — no breaking changes for existing users.

Other env vars you may want for the lite setup:

| Var | Purpose |
|---|---|
| `MINICLOSEDAI_DB_PATH` | Override where the SQLite DB lives. Default: `./miniclosedai.db` next to `app.py`. |
| `OLLAMA_URL` | The default seeded URL for the built-in Ollama row when it *does* get seeded. Irrelevant in lite mode. |

---

## Run

```bash
python app.py
# or:
uvicorn app:app --host 127.0.0.1 --port 8095
```

Open **http://localhost:8095**.

---

## Your first bot — 60 seconds

1. Open the UI. In the header, **Model** dropdown should already list your pulled models. Pick one (e.g. `qwen3:8b`).
2. Click **+ New Chat**. Name it `Summarizer`.
3. In the **System Prompt** panel on the left, paste:
   ```
   You are a concise summarizer. Respond with one sentence that captures the core point. No preamble, no quoting. Under 20 words.
   ```
4. In **Parameters**: drop Temperature to `0.2`, set Thinking to `Off` (for qwen3-family models) so you get the summary immediately.
5. In the composer, paste any paragraph of text and hit Enter. Your bot responds.
6. Click **API Code** in the header. Copy the cURL snippet. You now have a deterministic, local summarization microservice you can call from anything:

```bash
curl -N -X POST http://localhost:8095/api/conversations/1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Long text to summarize..."}'
```

That's the whole loop: **configure → save → call**.

---

## UI guide

### Activity bar (left edge)

Vertical nav with two icons — clicking swaps the main content area without navigating:

- **Dashboard** (top, grid icon) — the chat + sidebar you use for authoring and running bots. This is where you land.
- **Settings** (bottom, gear icon) — register and manage LLM endpoints (see [Connecting LM Studio and other endpoints](#connecting-lm-studio-and-other-openai-compatible-endpoints)).

Your selection persists across reloads. Streaming chats keep playing when you flip to Settings and back — the DOM is never unmounted.

### Header (Dashboard)

| Control | Purpose |
|---|---|
| ◆ logo + title | Branding |
| Sidebar toggle (panel-left icon) | Collapse/expand the sidebar. Preference persists. |
| **Model** `<select>` | **Grouped by endpoint.** Each registered backend contributes an `<optgroup>` with its available models. Picking a model from a different group switches the bot's backend too. |
| **Conversation** `<select>` | Switch between saved bots. Shows title + backend model. |
| **+ New Chat** | Prompts for a name, then creates a fresh bot with default params (model + backend inherited from current selection). |
| **↺ Clear** | Wipes messages in the current conversation, keeps the config. |
| **🗑 Delete** | Removes the current conversation entirely. |
| **API Code** | Opens the snippet modal (see below). |
| **Theme toggle** | Cycles System → Light → Dark → System. Respects `prefers-color-scheme` while on System. |

### Sidebar

Two panels, separated by a **horizontal splitter** you can drag to resize:

**System Prompt** — the bot's role. Auto-saved to the active conversation.

**Parameters**:

| Control | Range | What it does |
|---|---|---|
| Temperature | 0.0–2.0 | Randomness. 0.0 = deterministic. 0.7 = default. >1.0 = creative. |
| Max Tokens | 64–32 000 | Upper cap on response length. |
| Top P | 0.0–1.0 | Nucleus sampling. Usually leave at 0.9. |
| Top K | 1–500 | Keeps the top-K tokens at each step. |
| Thinking | Default / Off / On / Low / Medium / High | Controls reasoning for models that support it (qwen3/qwen3.5, deepseek-r1, gpt-oss). "Off" suppresses thinking output; "High" maximizes reasoning effort. |
| Max thinking tokens | blank or N | Auto-stop after N thinking tokens. Protects against runaway reasoning. |

**Reset defaults** snaps everything back to stock values.

**Status** at the bottom reports the reachable / total endpoint count plus a combined model count (green dot = at least one endpoint reachable; amber = some down; red = none reachable).

Also: a **vertical splitter** between sidebar and chat lets you widen the sidebar. Both splitters persist to localStorage; double-click either to reset.

### Chat

- Streaming responses. Blinking cursor during generation.
- Markdown + syntax-highlighted code blocks.
- Reasoning models emit a collapsible `💭 Thinking` block; it auto-collapses when the actual response begins streaming.
- Each assistant message shows a params badge (model · T · max · top_p · top_k) for reproducibility.
- **Stop button** (square icon) replaces **Send** (paper-plane icon) while streaming — click to abort.
- **Attach button** (paperclip icon, left of Send) — see [File attachments](#file-attachments) below.
- **Edit pencil** (top-right of every assistant bubble) opens an in-place textarea so you can rewrite the response. Save commits the new text to storage and re-renders. `Esc` cancels, `Ctrl/⌘+Enter` saves. Disabled while a stream is in flight. The pristine original output is preserved the first time you edit (`original_content`); a small `edited` pill appears next to the params badge — click it to see the original.
- **Download CSV** (tray icon in the header, between Clear and Delete) exports the current conversation as a two-column `input,output` CSV — one row per user→assistant pair, edited content as-is, leading/trailing whitespace stripped, proper CSV escaping for commas/quotes/newlines. Orphan user messages with no reply are skipped.

### File attachments

Click the paperclip in the composer (or paste from the clipboard) to attach files to the next message. Three kinds are supported, all from a single picker:

| Kind | Extensions | How it reaches the model |
|---|---|---|
| **Images** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp` | Sent natively as multimodal input. Browser auto-downscales anything wider than 2048 px to JPEG quality 0.92 to keep base64 payloads sane. |
| **PDFs** | `.pdf` | Server extracts text with `pypdf` (caps: 50 pages, 30 000 chars per file, 10 MB raw upload). Extracted text is prepended to the user message as `[Attached: filename.pdf]\n<text>`. Image-only / scanned PDFs may come back empty — that's a `pypdf` limitation, not a bug. |
| **Plain text & source code** | `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.toml`, `.xml`, `.html`, `.css`, `.js`, `.ts`, `.tsx`, `.jsx`, `.py`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.h`, `.sh`, `.sql`, `.log`, etc. | Read as text in the browser, prepended like a PDF. |

**Per-file cap:** 10 MB raw. **Multiple files per message:** yes — mix images + PDFs + text freely.

**Wire-format translation** is handled automatically per backend kind. For Ollama-native (`/api/chat`), images go in the dedicated `images: [base64,...]` field and the prepended attachment text lives in `content`. For OpenAI-compatible (`/v1/chat/completions` — LM Studio, vLLM, llama.cpp, Bonsai, public-IP Ollama relays), images become `{type:"image_url", image_url:{url:"data:..."}}` parts and the attached text becomes a `{type:"text"}` part. The same uploaded file works against either backend kind without re-encoding.

**Vision-model detection** is heuristic — the soft-warn banner appears when an image is attached but the selected model name doesn't match `llava*`, `gemma4*`, `qwen3.6`, `*-vision`, `*-vl*`, `pixtral`, `moondream`, `minicpm-v`, or `llama3.2-vision`. The image is still sent — the warning just flags that the reply may ignore it.

**No extra setup.** `pypdf` and `python-multipart` are pinned in `requirements.txt`; `pip install -r requirements.txt` is still the full install.

### Empty state

Shows a greeting and four **suggestion chips** that pre-fill the composer. Handy for first-time use; disappears as soon as you send a message.

### API Code modal

Three independent toggles produce **12 snippet variants**:

- **Language**: cURL · Python · JavaScript
- **Mode**: Streaming · Non-streaming
- **Style**: Native · OpenAI-compat

Copy button works on both HTTPS/localhost (via `navigator.clipboard`) and plain-HTTP LAN (falls back to `document.execCommand("copy")`).

---

## Connecting LM Studio and other OpenAI-compatible endpoints

MiniClosedAI ships with **Ollama as a built-in endpoint** and lets you register any number of additional **OpenAI-compatible** servers alongside it: [LM Studio](https://lmstudio.ai), [vLLM](https://docs.vllm.ai), `llama.cpp`'s `server` binary, [Text Generation WebUI](https://github.com/oobabooga/text-generation-webui)'s OpenAI extension, or the real OpenAI API itself if you want.

Each saved conversation picks one endpoint + one model; the Dashboard's model dropdown groups everything into a single OpenWebUI-style `<optgroup>` picker so you can chat with a Qwen3.6 on LM Studio and a Llama3.2 on Ollama in separate tabs without swapping anything.

### Adding LM Studio — step by step

1. **In LM Studio**, open the *Developer* tab → turn on **Start Server** (port 1234 by default). Load at least one model from the chat sidebar so `/v1/models` has something to list.
2. *(Optional)* Decide whether to gate the endpoint with an API key. For localhost-only use, turn *Require API key* **off** — easier. For LAN use with a key, copy the token LM Studio shows you.
3. **In MiniClosedAI**, click the **Settings** icon (gear, bottom of the activity bar) → **+ Add endpoint**. Fill in:
   - **Name**: anything readable, e.g. `LM Studio`
   - **Kind**: *OpenAI-compatible*
   - **Base URL**: **`http://localhost:1234/v1`** (local) or `http://<lan-host>:1234/v1` (remote). **The `/v1` suffix is required** — without it, requests hit LM Studio's admin routes and return 0 models.
   - **API key**: paste the LM Studio token if you enabled auth, otherwise leave blank.
   - **Extra headers**: usually empty.
4. Click **Test connection** — should say *"✓ Reachable · N model(s)"*. If it says *"Reachable, but 0 models available"*, you're missing `/v1`.
5. **Save.** Return to the Dashboard. The model dropdown now has a second `<optgroup>` labeled with your endpoint name; its options are the models LM Studio has loaded.

### Adding Bonsai (PrismML's 1-bit 8B) — step by step

**[PrismML Bonsai-8B](https://github.com/PrismML-Eng/Bonsai-demo)** is an extreme-quantization experiment: a 1-bit 8-billion-parameter model that ships at ~1.15 GB on disk (about **14× smaller** than the fp16 version of the same base architecture) while staying within striking distance of full-precision baselines on factual / reasoning benchmarks. It runs via `llama.cpp`'s `llama-server`, which speaks the OpenAI-compatible API natively — so it slots in as another endpoint in MiniClosedAI with no translation layer.

**Useful links:**
- **Repo & demo scripts:** [github.com/PrismML-Eng/Bonsai-demo](https://github.com/PrismML-Eng/Bonsai-demo)
- **PrismML:** [prismml.com](https://prismml.com) — the team behind the model
- **Whitepaper:** `1-bit-bonsai-8b-whitepaper.pdf` (ships with the demo repo) — explains the quantization approach and benchmark methodology
- **llama.cpp** (runtime): [github.com/ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)

#### 1. Install and start the Bonsai server

```bash
# Clone PrismML's demo repo
git clone https://github.com/PrismML-Eng/Bonsai-demo.git
cd Bonsai-demo

# One-shot setup — builds llama.cpp and downloads the default GGUF model (Bonsai-8B)
./setup.sh

# Start the OpenAI-compatible server
./scripts/start_llama_server.sh
# Serves at http://localhost:8080 — health check at /health, API at /v1/chat/completions
```

Pick a different size by setting `BONSAI_MODEL` before the script: `8B` (default), `4B`, or `1.7B`.
```bash
BONSAI_MODEL=4B ./scripts/start_llama_server.sh
```

**aarch64 / ARM**: the shipped binaries are x86_64. Build from source with `./scripts/build_cuda_linux.sh` (Linux+NVIDIA) or `./scripts/build_mac.sh` (macOS+Metal) before the `start_llama_server` step.

#### 2. Register Bonsai as an endpoint in MiniClosedAI

Settings (gear icon, bottom of activity bar) → **+ Add endpoint**:

| Field | Value |
|---|---|
| **Name** | `Bonsai` (or anything readable) |
| **Kind** | **OpenAI-compatible** |
| **Base URL** | **`http://localhost:8080/v1`** — local. For LAN, substitute the host's IP. **Do not confuse `8080` (Bonsai) with `8095` (MiniClosedAI itself)** — see the pitfall below. The `/v1` suffix is required. |
| **API key** | *(leave blank — `llama.cpp --server` doesn't require auth by default)* |
| **Extra headers** | *(leave empty)* |

Click **Test connection** — should say *"✓ Reachable · 1 model(s)"* and list `Bonsai-8B.gguf` (or whichever size you loaded). Save.

#### 3. Chat with Bonsai

Back on the Dashboard, open the model dropdown → there's a `Bonsai` optgroup with `Bonsai-8B.gguf` inside it. Create a new chat, pick that model, write a prompt. Every subsequent turn routes automatically to `http://localhost:8080/v1/chat/completions` because the conversation is pinned to `(backend_id=<Bonsai>, model="Bonsai-8B.gguf")`.

The per-conv microservice pattern applies unchanged: `POST /api/conversations/{id}/chat` is your Bonsai bot's stable callable URL, and the API Code modal emits cURL / Python / JavaScript snippets that point at it.

**Ready-made Bonsai microservice recipe:** see **[`RAG Query Router.md`](./RAG%20Query%20Router.md)** for a complete system prompt, recommended settings, and Python integration code for a latency-critical query-classification bot that's purpose-built for Bonsai's speed profile. Covered in the Recipes section below as [#8 RAG query router](#8-rag-query-router-bonsai-paired--full-walkthrough).

#### Notes and gotchas specific to Bonsai

- **Thinking: Off (or Default).** `start_llama_server.sh` already boots with `--reasoning-budget 0 --reasoning-format none --chat-template-kwargs '{"enable_thinking": false}'` — thinking is disabled upstream. Leave MiniClosedAI's Thinking control on `Off` or `Default` to match. Flipping it to `On` just wastes tokens; the server still won't emit reasoning.
- **Context window.** Bonsai-8B is trained at 65,536 tokens; the start script uses llama.cpp's `-c 0` (auto-fit). For very long contexts your GPU VRAM will be the binding constraint, not MiniClosedAI.
- **Server-side sampling defaults** (set in `start_llama_server.sh`): `temp=0.5`, `top-p=0.85`, `top-k=20`, `min-p=0`. MiniClosedAI's per-conversation sliders override these on every request, so tune per-chat as usual.
- **Pitfall — wrong port = feedback loop.** If you accidentally set Bonsai's Base URL to `http://localhost:8095/v1` (MiniClosedAI's own port), the endpoint's `/v1/models` call loops back and returns *MiniClosedAI's saved conversations as "models"*. The model dropdown will show conversation IDs (e.g. `"30"`) under the Bonsai optgroup; picking one sends the chat through that conversation's bot instead of Bonsai, producing nonsensically on-topic responses (the Lead Qualifier's JSON, etc.). Fix: edit the endpoint, change the port to **`8080`**.
- **Stop the server** when you're done: `kill $(lsof -ti TCP:8080)` (or `Ctrl+C` in the terminal you started it in).

### Using it

- **Pick any external model** from the dropdown and chat normally. The bot saves the `(model, backend_id)` pair so the next time you open that conversation it routes to the correct endpoint automatically.
- **API Code modal** emits snippets that call MiniClosedAI's `/api/conversations/{id}/chat` or `/v1/chat/completions`. Your downstream code talks to MiniClosedAI; MiniClosedAI relays to whichever endpoint the bot is pinned to.
- **Mix freely.** One bot on Ollama, another on LM Studio (different host on your LAN), a third on Bonsai, a fourth on vLLM — all callable from the same URL base.

### Reasoning models on LM Studio / vLLM

The **Thinking** sidebar control translates as follows when a conversation is bound to an OpenAI-compatible endpoint:

| Thinking value | What gets sent |
|---|---|
| Off | `chat_template_kwargs: {enable_thinking: false}` + `/no_think` appended to the last user message |
| On | `chat_template_kwargs: {enable_thinking: true}` + `/think` appended to the last user message |
| Low / Medium / High | `reasoning_effort: <value>` (gpt-oss family) |

Whether the *server* honors these signals depends on the build. Newer vLLM and LM Studio versions respect `enable_thinking`; older ones don't. **If your model keeps reasoning after you set Thinking: Off, your LM Studio build is ignoring the flag** — MiniClosedAI has already sent it three different ways. The practical workaround is simple:

- **Use a reasoning model for reasoning tasks** with Thinking: On and no `max_thinking_tokens` cap — Qwen3.x, DeepSeek-R1, gpt-oss.
- **Use a non-reasoning model for strict-output tasks** (JSON extractors, classifiers, one-word answers) — Gemma 4, Mistral, Llama 3.x, qwen2.5 variants.

`max_thinking_tokens` is a **soft cap**: when exceeded, MiniClosedAI hides further reasoning from the UI but keeps the stream open so the model can finish and emit its actual answer. The banner reads *"✂ Thinking hidden after N tokens. Model still finishing its reasoning; the answer will follow."* The hard kill switch is **Max Tokens**.

### Managing endpoints

From the Settings page:

- **Test connection** (on each card or in the Add/Edit modal) probes the endpoint *through the MiniClosedAI server* — avoids browser CORS blocks on cross-origin calls to LM Studio.
- **Edit** lets you change the name, URL, API key, or custom headers. `kind` is immutable once saved.
- **Delete** removes a non-built-in endpoint. If any conversation is still bound to it, you get a 409 listing the conversations — rebind them first, then retry.
- **The built-in Ollama endpoint** can be renamed or have its URL changed (useful if Ollama runs on a different port or host), but can't be deleted.

---

## The microservice pattern

Each conversation in the database is a **self-contained, addressable bot**:

```
model   = "qwen3:8b"
system  = "You are a JSON extractor..."
params  = {temperature: 0.1, max_tokens: 2048, top_p: 0.9, top_k: 40,
           think: false, max_thinking_tokens: 200}
```

That bundle lives behind two URLs:

```
POST /api/conversations/{id}/chat         → non-streaming
POST /api/conversations/{id}/chat/stream  → SSE streaming
```

**The caller never sends config.** Only the content:

```json
{ "message": "Hello!" }
```

Or, for multi-turn calls:

```json
{ "messages": [
    { "role": "user",      "content": "My favorite color is blue." },
    { "role": "assistant", "content": "Got it." },
    { "role": "user",      "content": "What is it?" }
  ]
}
```

**Config is locked to what the GUI saved.** Attempts to override `temperature`, `model`, `system_prompt`, `top_p`, etc. in the request body get rejected with a clean 422 (`extra_forbidden`). If you want different behavior, change it in the GUI.

### Why it works

The flow GUI → server is the same flow cURL → server. When you hit **Send** in the UI, the frontend calls `POST /api/conversations/{id}/chat/stream` with `{"message": text, "persist": true}` — byte-identical to your cURL snippet except for `persist: true` (which is a *storage* flag; it saves the turn to the chat's display history without affecting the model's output).

The model sees only: `(saved system_prompt, saved params, request messages)`. Conversation history from the DB is **never** replayed into the model. The chat log in the UI is purely a display artifact.

**Implication**: GUI and API produce identical responses given the same message and bot. No ambiguity, no silent history leaks.

### Persistence semantics

```
persist: false  (default) → stateless call. Turn is not saved.
persist: true             → saves the user turn + assistant reply to the
                             chat's display history. The next UI refresh
                             will show it.
```

The GUI always sets `persist: true`. API callers default to false (each call is an independent function invocation).

---

## API reference — native endpoints

Base URL: `http://<host>:8095`. All endpoints return JSON unless noted. Interactive OpenAPI docs at `/docs`.

### Models (aggregated)

```
GET /api/models
```

Returns every enabled backend and the models it reports, plus a legacy flat shape for back-compat with anything still expecting Ollama-only output.

```json
{
  "backends": [
    {
      "id": 1,
      "name": "Ollama (built-in)",
      "kind": "ollama",
      "base_url": "http://localhost:11434",
      "enabled": true,
      "is_builtin": true,
      "running": true,
      "models": [
        { "name": "llama3.2:3b", "size": 2019393189,
          "details": { "parameter_size": "3.2B" } }
      ]
    },
    {
      "id": 2,
      "name": "LM Studio",
      "kind": "openai",
      "base_url": "http://localhost:1234/v1",
      "enabled": true,
      "is_builtin": false,
      "running": true,
      "models": [ { "name": "qwen/qwen3.6-35b-a3b", "size": 0, "details": {} } ]
    }
  ],
  "ollama_running": true,
  "models": [ /* legacy flat list from backend id=1 only */ ]
}
```

### Backends (endpoint lifecycle)

```
GET    /api/backends              → list all (api_key scrubbed to api_key_set bool)
POST   /api/backends              → create. Strip trailing /, normalize URL.
PATCH  /api/backends/{id}         → update (kind is immutable)
DELETE /api/backends/{id}         → 403 on is_builtin, 409 if bound to chats
GET    /api/backends/{id}/models  → list that backend's models only
GET    /api/backends/{id}/status  → is it reachable?
POST   /api/backends/test         → probe a draft config without saving
```

**Create body:**

```bash
curl -X POST http://localhost:8095/api/backends \
  -H "Content-Type: application/json" \
  -d '{
    "name": "LM Studio",
    "kind": "openai",
    "base_url": "http://localhost:1234/v1",
    "api_key": "optional-bearer-token",
    "headers": {"X-Custom": "optional"}
  }'
```

**Valid `kind` values:** `"ollama"` · `"openai"`. The OpenAI kind speaks the `/v1/chat/completions` wire format and works with any compliant server.

**Delete guardrails:**

- `DELETE /api/backends/1` (or any row with `is_builtin=1`) → **403 Forbidden**.
- `DELETE /api/backends/<id>` when one or more conversations still point at it → **409 Conflict** with a `bound_conversations` list. Rebind those conversations first (change their saved model to one on a different backend), then retry the delete.

**Test endpoint** (draft probe — server-side, bypasses browser CORS):

```bash
curl -X POST http://localhost:8095/api/backends/test \
  -H "Content-Type: application/json" \
  -d '{"name":"draft","kind":"openai","base_url":"http://localhost:1234/v1"}'
# → {"running": true, "models_count": 7, "message": "Reachable · 7 model(s)"}
```

### Conversations (bot lifecycle)

```
GET    /api/conversations                         → list all
POST   /api/conversations                         → create
GET    /api/conversations/{id}                    → get full conversation (config + messages)
PATCH  /api/conversations/{id}                    → update any subset of fields
DELETE /api/conversations/{id}                    → delete
POST   /api/conversations/{id}/clear              → wipe messages, keep config
PATCH  /api/conversations/{id}/messages/{index}   → edit a stored message in place
GET    /api/conversations/{id}/export.csv         → download this chat as an SFT CSV
```

**Create** — supply any subset of config fields. `backend_id` defaults to `1` (built-in Ollama); set it to pin the bot to an OpenAI-compatible endpoint you registered in Settings.

```bash
curl -X POST http://localhost:8095/api/conversations \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Info extractor",
    "model": "qwen3:8b",
    "backend_id": 1,
    "system_prompt": "Return pure JSON. No prose.",
    "temperature": 0.1,
    "max_tokens": 1200,
    "think": false
  }'
```

**Get** — returns config + full message history:

```json
{
  "id": 3,
  "title": "Info extractor",
  "model": "qwen3:8b",
  "backend_id": 1,
  "system_prompt": "...",
  "messages": [ {"role":"user","content":"...","params":{...}}, ... ],
  "params": {"temperature": 0.1, "max_tokens": 1200, "top_p": 0.9,
             "top_k": 40, "think": false, "max_thinking_tokens": null},
  "created_at": "2026-04-21 01:23:45",
  "updated_at": "2026-04-21 01:24:10"
}
```

**PATCH backend switch** — change which endpoint a bot runs on:

```bash
curl -X PATCH http://localhost:8095/api/conversations/3 \
  -H "Content-Type: application/json" \
  -d '{"backend_id": 2, "model": "qwen/qwen3.6-35b-a3b"}'
```

**PATCH** — send only the fields you want to change. Sampling params merge into the saved JSON; other saved params are preserved.

**PATCH `.../messages/{index}`** — edit a single stored message in place. Body accepts exactly `{"content": "new text"}` (empty string allowed; any extra field returns **422**). The first edit of a given message copies the existing text to `original_content` and stamps `edited: true` + `edited_at: <ISO-8601 UTC>`; subsequent edits update `content` only — the pristine original is preserved. Returns the full updated conversation. 404 if the conversation doesn't exist or `index` is out of range.

```bash
curl -X PATCH http://localhost:8095/api/conversations/3/messages/1 \
  -H "Content-Type: application/json" \
  -d '{"content": "The rewritten assistant answer that becomes the SFT target."}'
```

**GET `.../export.csv`** — download every user→assistant pair in this conversation as a two-column CSV. Columns are literally `input,output`. Rows use RFC-4180 quoting (commas, double quotes, and embedded newlines handled). Leading and trailing whitespace is stripped from both columns. Orphan user turns (no reply yet) are skipped. Response is `text/csv` with a `Content-Disposition: attachment; filename="<title>.csv"` header so the browser saves it directly. 404 if the conversation doesn't exist.

```bash
curl -o mybot.csv http://localhost:8095/api/conversations/3/export.csv
head -3 mybot.csv
# input,output
# "Subject: URGENT — payout broken…","{""intent"":""bug"",""urgency"":""p1"",…}"
```

### Chat

```
POST /api/conversations/{id}/chat          → non-streaming
POST /api/conversations/{id}/chat/stream   → SSE streaming
```

**Request body (only these fields accepted):**

| Field | Type | Default | Purpose |
|---|---|---|---|
| `message` | string | — | Single-turn content. Exactly one of `message` or `messages` must be set. |
| `messages` | array of `{role, content}` | — | Multi-turn content. `content` may be a string OR an OpenAI-style content array `[{type:"text", text:"…"}, {type:"image_url", image_url:{url:"data:image/png;base64,…"}}]` for multimodal turns. |
| `persist` | bool | `false` | Save the turn to the bot's display history. |
| `include_history` | bool | `false` | Single-message form only. Prepend the conversation's saved turns to the LLM context. |
| `attachments` | array | — | Single-message form only. List of `{name, kind, ...}` attachments. See **File attachments** below. |

Any other field — `model`, `system_prompt`, `temperature`, `max_tokens`, `top_p`, `top_k`, `think`, `max_thinking_tokens` — returns **422 Unprocessable Entity** with `extra_forbidden`. Config is locked to the GUI.

**File attachments** (single-message form, optional):

```json
{
  "message": "What's in this image?",
  "attachments": [
    {"name": "photo.png", "kind": "image", "mime": "image/png",
     "data_url": "data:image/png;base64,iVBORw0KGgo..."},
    {"name": "notes.pdf", "kind": "pdf",
     "text": "...extracted text...", "page_count": 12, "truncated": false},
    {"name": "todo.txt", "kind": "text", "text": "buy milk\nfeed the cat"}
  ]
}
```

The server combines `message` + each attachment into one multimodal user turn:
text/PDF bodies are prepended as `[Attached: <name>]\n<text>`, images become
`image_url` parts. The `kind` discriminator is one of `image | text | pdf`; for
images, supply `data_url` (a `data:image/...;base64,...` URL); for text/PDF,
supply the already-extracted `text`. Use `POST /api/extract-pdf` to convert a
raw PDF upload into the `text` field — see below.

**Non-streaming response:**

```json
{
  "response": "Hello!",
  "conversation_id": 3,
  "model": "qwen3:8b",
  "persisted": false
}
```

**Streaming response** — SSE frames:

| Frame | When |
|---|---|
| `data: {"chunk": "text"}` | Each content token |
| `data: {"thinking": "text"}` | Each reasoning token (qwen3/qwen3.5, deepseek-r1, gpt-oss) |
| `data: {"thinking_truncated": true, "reason": "max_thinking_tokens", "limit": N}` | Server auto-stopped at the thinking cap |
| `data: {"error": "…"}` | Upstream failure (Ollama down, etc.) |
| `data: {"end": true, "truncated": false}` | Final frame. `truncated` is `true` when auto-stop fired. |

**Minimal cURL:**

```bash
curl -N -X POST http://localhost:8095/api/conversations/3/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

### Sending file attachments

Multimodal turn — same streaming endpoint, same single-`message` form, plus an `attachments` array described in the request-body table above. The server combines `message` + each entry into one user turn (text/PDF bodies prepended as `[Attached: <name>]\n…`, images become `image_url` parts). All three snippets below use a vision-capable conversation (e.g. one pinned to `llava:7b`, `gemma4:31b`, or `qwen3.6:35b`). Replace the conversation ID and image path; everything else is verbatim.

**cURL** — inline base64-encodes a local image into a `data:` URL so the call is one paste:

```bash
# Chat #3. Config (model/prompt/params) is set in the GUI —
# this call only supplies the message + attachments.
B64=$(base64 -w0 ./photo.png)             # macOS: base64 -i ./photo.png | tr -d '\n'
curl -N -X POST http://localhost:8095/api/conversations/3/chat/stream \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What's in this image?\",
    \"attachments\": [{
      \"name\": \"photo.png\",
      \"kind\": \"image\",
      \"mime\": \"image/png\",
      \"data_url\": \"data:image/png;base64,$B64\"
    }]
  }"
```

**Python** — `httpx.stream` shape, mirrors the GUI's "API Code" modal output:

```python
import base64, httpx, json, mimetypes, pathlib

# Config (model/prompt/params) is set in the GUI — this call only supplies the message + attachments.
path = pathlib.Path("photo.png")
mime = mimetypes.guess_type(path)[0] or "image/png"
data_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"

URL = "http://localhost:8095/api/conversations/3/chat/stream"
payload = {
    "message": "What's in this image?",
    "attachments": [{
        "name": path.name,
        "kind": "image",
        "mime": mime,
        "data_url": data_url,
    }],
}
with httpx.stream("POST", URL, json=payload, timeout=None) as r:
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        data = json.loads(line[5:].strip())
        if "chunk" in data:
            print(data["chunk"], end="", flush=True)
        if data.get("end"):
            break
```

**JavaScript (Node 18+, native fetch):**

```js
import { readFile } from "node:fs/promises";

// Config (model/prompt/params) is set in the GUI — this call only supplies the message + attachments.
const buf = await readFile("./photo.png");
const dataUrl = `data:image/png;base64,${buf.toString("base64")}`;

const res = await fetch("http://localhost:8095/api/conversations/3/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    message: "What's in this image?",
    attachments: [{
      name: "photo.png",
      kind: "image",
      mime: "image/png",
      data_url: dataUrl,
    }],
  }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const parts = buffer.split("\n\n");
  buffer = parts.pop();
  for (const part of parts) {
    if (!part.startsWith("data:")) continue;
    const data = JSON.parse(part.slice(5).trim());
    if (data.chunk) process.stdout.write(data.chunk);
    if (data.end) process.exit(0);
  }
}
```

**Other file kinds.** Swap the entry shape — no base64 needed for plain text:

- **`.txt` / `.md` / `.csv` / source code** → `{"name": "todo.txt", "kind": "text", "text": "<file body as a string>"}`. Read the file as UTF-8 (Python: `path.read_text()`, JS: `fs.readFile(path, "utf-8")`) and drop the contents straight into `text`.
- **PDF** → first call `POST /api/extract-pdf` (curl example just below) and pass its returned fields through: `{"name": "doc.pdf", "kind": "pdf", "text": <returned text>, "page_count": <returned page_count>, "truncated": <returned truncated>}`.

Multiple attachments per message are allowed and may freely mix the three kinds — append more entries to the same `attachments` array.

### PDF text extraction

```
POST /api/extract-pdf      → multipart/form-data
```

**Request:** a single multipart field named `file`. Caps: 10 MB raw, 50 pages, 30 000 chars output.

**Response:**

```json
{
  "filename": "doc.pdf",
  "page_count": 12,
  "char_count": 4218,
  "truncated": false,
  "text": "--- Page 1 ---\n…\n\n--- Page 2 ---\n…"
}
```

`truncated` is `true` if either the page cap or the char cap was hit. Use the returned `text` (and the rest of the metadata) to populate an `attachments[]` entry on the next chat call. The frontend does this automatically — it's only an explicit endpoint for callers that want to handle PDFs without re-implementing extraction.

```bash
curl -X POST http://localhost:8095/api/extract-pdf \
  -F "file=@./report.pdf" | jq '.text' | head -c 200
```

### Legacy generic chat

```
POST /api/chat
POST /api/chat/stream
```

These require the full config in the request body (model, system_prompt, all sampling params). Kept for advanced cases; prefer the per-conversation endpoints for everything else.

---

## OpenAI-compatible endpoint

MiniClosedAI also serves an OpenAI-shape API so any OpenAI SDK works against it with a one-line base-URL change.

```
POST /v1/chat/completions         → OpenAI request/response shape
GET  /v1/models                   → each conversation listed as a model
```

### How the SDK maps to the bot

- **`model` field** = the conversation's ID. Accepts `"12"`, `"conv-12"`, `"bot-12"`, or `"miniclosed/12"` — all resolve to conversation 12.
- **`system` message** (if any in the caller's `messages`) is dropped — the bot's GUI-saved system prompt wins.
- **Sampling params** in the request (temperature, top_p, presence_penalty, …) are tolerated but ignored. Bot config is the source of truth.

### Python (OpenAI SDK + streaming)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8095/v1", api_key="not-required")

stream = client.chat.completions.create(
    model="3",                                    # conversation ID
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

### JavaScript (OpenAI SDK + streaming)

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8095/v1",
  apiKey: "not-required",
});

const stream = await client.chat.completions.create({
  model: "3",
  messages: [{ role: "user", content: "Hello!" }],
  stream: true,
});

for await (const chunk of stream) {
  const delta = chunk.choices[0]?.delta?.content;
  if (delta) process.stdout.write(delta);
}
```

### cURL (raw HTTP, non-streaming)

```bash
curl -X POST http://localhost:8095/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "3",
    "messages": [{"role":"user","content":"Hello!"}]
  }'
```

Response is standard OpenAI shape:

```json
{
  "id": "chatcmpl-mca-3-1776793724213",
  "object": "chat.completion",
  "created": 1776793724,
  "model": "qwen3:8b",
  "choices": [
    { "index": 0,
      "message": { "role": "assistant", "content": "Hello!" },
      "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

### Migration story

If your code already uses the OpenAI API:

```python
# Before: cloud
client = OpenAI(api_key="sk-...")
client.chat.completions.create(model="gpt-4", ...)

# After: local MiniClosedAI
client = OpenAI(base_url="http://localhost:8095/v1", api_key="x")
client.chat.completions.create(model="3", ...)     # your bot's chat id
```

Streaming, async clients, multi-turn messages — all work unchanged.

---

## Recipes — common bot patterns

### 1. JSON extractor

**System prompt:**
```
You are an information-extraction microservice.

Input: any raw text from the user.
Output: a single JSON object matching this schema. No prose, no fences.

{
  "summary":   "one sentence",
  "entities":  [ { "name": "...", "type": "person|org|place|product" } ],
  "dates":     ["YYYY-MM-DD", ...],
  "numbers":   [ { "value": 0, "unit": "USD", "context": "..." } ],
  "sources":   ["https://..."],
  "confidence": 0.0
}

Rules:
- Every key appears every call; use null or [] when empty.
- ISO-8601 dates. Never invent missing data. Deduplicate.
```

**Settings:** model `qwen3:8b` (or `qwen2.5:7b`), temperature `0.1`, Thinking `Off`, max_thinking_tokens `50`.

**Use it:**
```bash
curl -X POST http://localhost:8095/api/conversations/3/chat \
  -d '{"message": "Any email, article, or OCR dump here."}'
```

### 2. Sentiment classifier

**System prompt:**
```
Classify the sentiment of the user's text as exactly one of:
positive, negative, neutral, mixed.
Return ONLY that word. No punctuation, no explanation.
```

**Settings:** temperature `0.0`, max_tokens `10`, Thinking `Off`.

### 3. SQL generator

**System prompt:**
```
You are a PostgreSQL expert. Given a natural-language question and
this schema:

TABLE users (id INT, email TEXT, created_at TIMESTAMP)
TABLE orders (id INT, user_id INT, total NUMERIC, placed_at TIMESTAMP)

Respond with ONLY the SQL query. No explanation. No markdown fences.
```

**Settings:** temperature `0.0`, Thinking `High` (on qwen3 or gpt-oss), max_tokens `500`.

### 4. Persona (Pikachu!)

**System prompt:**
```
You are Pikachu. Respond to every message with exactly the word "Pikachu!" —
nothing more, nothing less.
```

**Settings:** qwen3:8b, temperature `0.0`, Thinking `Off`. (llava:7b won't follow this without few-shot examples — see [Getting good responses](#getting-good-responses-from-small-models).)

### 5. Code reviewer

**System prompt:**
```
You are a senior code reviewer. Given a diff or a code block, respond
with exactly three bullet points:
  • issue #1: one-line summary
  • issue #2: one-line summary
  • issue #3: one-line summary

If fewer than three real issues exist, repeat the highest-severity one.
No preamble, no praise, no code quoting.
```

**Settings:** qwen3:8b, temperature `0.3`, Thinking `Medium`, max_tokens `400`.

---

### 6. Support ticket router — [full walkthrough](./Support%20Ticket%20Router.md)

Takes an inbound support message, returns a JSON blob that classifies `intent`, picks a `team`, assigns `urgency` (p0–p3), extracts `key_entities` (product areas, order IDs, error codes, dates), scores `sentiment`, and suggests a reply tone. Includes a `needs_human_review` escape hatch for low-confidence cases.

**Output shape (abridged):**
```json
{
  "intent": "bug | billing | how_to | feature_request | account | complaint | spam | ...",
  "team":   "engineering | billing | support | sales | success | trust_safety | unknown",
  "urgency":"p0 | p1 | p2 | p3",
  "sentiment":"angry | frustrated | neutral | satisfied | delighted",
  "customer_blocked": true,
  "needs_human_review": false,
  "key_entities": { "product_areas":[], "order_ids":[], "emails":[], "error_codes":[], "dates":[] },
  "suggested_reply_tone":"empathetic | apologetic | informative | celebratory | cautious",
  "summary":"...",
  "confidence": 0.0
}
```

**Settings:** `qwen3:8b`, temperature `0.1`, Thinking `Off`, max_tokens `700`.

**Archetype:** classify → route → extract → flag-for-human. The canonical LLM-as-decision-service pattern. Drop-in replacement for the rules-plus-regex ticket-triage scripts every support team has written three times. Full system prompt, example I/O, integration code, and variant ideas in **[`Support Ticket Router.md`](./Support%20Ticket%20Router.md)**.

---

### 7. Inbound lead qualifier — [full walkthrough](./Inbound%20Lead%20Qualifier.md)

B2B sibling of the ticket router. Takes an inbound prospect message (form-fill, email, chat), returns a JSON blob with a numeric `fit_score` (0–100), `intent`, `role_signal`, company-size and industry guesses, budget + timeline signals, and a routing decision that maps to CRM stages (`book_demo`, `send_pricing`, `escalate_to_AE`, etc.).

**Output shape (abridged):**
```json
{
  "fit_score": 0,                          // integer 0-100, rounded to nearest 5
  "fit_label": "cold | lukewarm | warm | hot | evangelist",
  "intent": "pricing | demo_request | trial | comparison | rfp | partner | spam | ...",
  "role_signal": "decision_maker | influencer | end_user | gatekeeper | unknown",
  "company_size_guess": "solopreneur | smb | midmarket | enterprise | unknown",
  "budget_signal": "none | low | mid | high | unstated",
  "timeline_signal": "now | month | quarter | year | unclear",
  "competitor_mentioned": null,
  "use_case_summary":"...",
  "next_action":"book_demo | send_pricing | nurture_email | escalate_to_AE | ...",
  "assigned_rep_hint":"AE | SDR | CSM | automation | trash",
  "key_entities": { ... },
  "red_flags": [],
  "needs_human_review": false,
  "confidence": 0.0
}
```

**Settings:** `qwen3:8b`, temperature `0.1`, Thinking `Off`, max_tokens `900`.

**Archetype:** adds a numeric scoring dimension on top of the ticket-router pattern, plus a first-match routing table stated in plain English. Great proof that an 8B local model is enough to replace a spreadsheet-and-two-contractors lead-triage process. Full system prompt, example I/O, `match`/`case` routing code, and four more schema variants (applicant screener, investor inbound, beta applicant, partnership inbound) in **[`Inbound Lead Qualifier.md`](./Inbound%20Lead%20Qualifier.md)**.

---

### 8. RAG query router (Bonsai-paired) — [full walkthrough](./RAG%20Query%20Router.md)

A latency-critical pre-router for retrieval-augmented QA systems. Every inbound user question hits this bot first; it returns a JSON decision telling the orchestrator whether to hit the cache, fire a fast LLM-only reply, run light RAG, run deep RAG, or ask the user a clarifying question. Designed specifically to be paired with **[Bonsai-8B](#adding-bonsai-prismmls-1-bit-8b--step-by-step)** — the 1-bit model's ~200 ms inference makes this classifier free on the hot path of every user turn, which is the difference between a router being usable and being a bottleneck.

**Output shape (abridged):**
```json
{
  "question_type": "factual | multi_fact | comparative | procedural | conversational | hypothetical | ambiguous",
  "primary_topic": "...",
  "entities": ["..."],
  "requires_realtime": false,
  "min_facts_needed": 0,
  "routing_decision": "fast_cache | fast_llm_only | rag_light | rag_deep | ask_clarification",
  "clarifying_question": null,
  "estimated_tier": "trivial | easy | medium | hard",
  "pii_present": false,
  "confidence": 0.0
}
```

**Settings:** `Bonsai-8B.gguf` on the Bonsai endpoint, **temperature `0.0`** (pure greedy — same question always routes the same way), Thinking `Off`, max_tokens `400`. Works equally well with `llama3.2:3b` or `gemma2:2b` on Ollama if you don't want to run a separate llama.cpp server.

**Archetype:** *classify → decide → delegate*, not *classify → answer*. Differs from the ticket router / lead qualifier in that the output is an intermediate orchestration decision rather than an end-state record. Includes explicit handling for demonstrative pronouns ("how does this work?" → `ask_clarification` with a clarifying question) which is where small classifiers typically fail. Full system prompt, example I/O, Python `match/case` dispatcher, and five variant ideas (prompt-safety gatekeeper, agent-task decomposer, cache key canonicalizer, and more) in **[`RAG Query Router.md`](./RAG%20Query%20Router.md)**.

---

### 9. Doctor's office chatbot — [full walkthrough](./Doctors%20Office%20Bot.md)

A front-of-house chatbot for a primary-care practice. Answers FAQs from an explicit knowledge base in the system prompt, collects appointment-booking details across multiple turns, detects red-flag symptoms and redirects to 911, routes prescription-refill requests to a nurse callback, and offers a human-transfer path on request. **Different archetype from the three routers above:** conversational state + **dual-mode output** — plain text on info-gathering turns, plus a fenced JSON action block on the turn it's ready to execute (booking, emergency redirect, refill request, human handoff).

**Output — visible reply PLUS (on action turns) one of:**
```json
{"type": "create_appointment",       "patient": {...}, "visit": {...}, "insurance": {...}, "confirmation": {...}}
{"type": "urgent_redirect_911",      "trigger_signs": [...], "time_first_mentioned": null}
{"type": "request_prescription_refill", "patient": {...}, "medication": {...}}
{"type": "transfer_to_human",        "reason": "faq_out_of_scope | patient_requested | ...", "short_summary": "..."}
{"type": "request_callback",         "patient": {...}, "topic": "...", "preferred_window": "..."}
```

**Settings:** `qwen3:8b` on Ollama, temperature `0.3`, Thinking `Off`, max_tokens `600`. The MiniClosedAI UI sends `include_history: true` automatically so the model sees every prior turn. **Do not use Bonsai-8B (1-bit) for this bot** — verified live on this repo that 1-bit quantization drops the conditional JSON emission even with the few-shot-patched prompt. 1-bit is for single-mode classifiers (RAG Query Router, Ticket Router); mixed-mode needs full-precision 7–9B.

**Archetype:** *converse → gather → emit side effect*. Sits at the front door of a real website or patient portal. The bot is a chatbot for the user AND a microservice for your backend at the same time — dual-audience design. Includes hard guardrails (no medical advice, no policy invention, no prompt disclosure), a required-fields gate that prevents premature booking, and three load-bearing few-shot examples inside the system prompt (booking, red-flag, FAQ-out-of-scope) without which the JSON emission drops. Full system prompt, eight worked conversation examples (including an adversarial prompt-injection turn and an after-hours callback), Python session-state integration with regex-stripping of the fenced action block, and five domain variants (veterinary, dental, PT, mental-health, HVAC) in **[`Doctors Office Bot.md`](./Doctors%20Office%20Bot.md)**.

---

### 10. Restaurant reservations bot — [full walkthrough](./Restaurant%20Reservations%20Bot.md)

Same dual-mode archetype as the Doctor's Office Bot, applied to a sit-down restaurant's host stand. Answers FAQs from an explicit `RESTAURANT FACTS` block (hours, dress code, dietary, corkage, parking, cancellation policy), books / modifies / cancels reservations across multiple turns, hard-overrides any party of 9+ or private-event request to the events team, attaches a `kitchen_allergy_flag` to the reservation when the guest mentions celiac / anaphylaxis / "deathly allergic," and offers a human host transfer on request.

**Output — visible reply PLUS (on action turns) one of:**
```json
{"type": "create_reservation",   "guest": {...}, "reservation": {...}, "kitchen_allergy_flag": "...", "confirmation": {...}}
{"type": "modify_reservation",   "lookup": {...}, "changes": {...}}
{"type": "cancel_reservation",   "lookup": {...}, "reason": "..."}
{"type": "route_to_events_team", "guest": {...}, "request": {"kind": "large_party | wedding | ...", ...}}
{"type": "transfer_to_human",    "reason": "...", "short_summary": "..."}
```

**Settings:** `qwen3:8b` on Ollama, temperature `0.3`, Thinking `Off`, max_tokens `500`, `include_history: true`.

**Archetype:** drop-in twin of the Doctor's Office Bot for hospitality. Same `=== BEGIN/END FACTS ===` source-of-truth pattern, same dual-mode output, same required-fields gate — plus a hardened **pre-confirmation checklist** (closed-day check, in-service-hours check, party-size 1–8, seating-bookable check, all-fields-present check, **explicit affirmative trigger**, JSON-or-no-confirmation) and four negative-path few-shot examples (Examples D/E/F/G — closed Monday with dog indoors, Sunday post-close, bar counter not bookable, partial gather with no trigger). The hardening was added after live testing showed `qwen3:8b` would otherwise sometimes confirm prematurely on a follow-up answer like "no allergies" instead of waiting for an explicit yes. Edit the facts block to point at your restaurant. Walkthrough in **[`Restaurant Reservations Bot.md`](./Restaurant%20Reservations%20Bot.md)**.

---

### 11. Hotel reservations bot — [full walkthrough](./Hotel%20Reservations%20Bot.md)

Same dual-mode archetype, applied to a boutique hotel's reservations chat. Answers FAQs from an explicit `HOTEL FACTS` block (check-in/out, room types, rates, pet policy, parking, cancellation), books / modifies / cancels stays of any length, hard-overrides group blocks of 5+ rooms / weddings / conferences / buyouts / negotiated corporate rates to the sales team, and refuses to accept a credit-card number in chat — payment happens on the secure confirmation page after the inquiry is saved. (Stay length is intentionally NOT a routing trigger — a single guest booking 17 nights goes through the normal flow.)

**Output — visible reply PLUS (on action turns) one of:**
```json
{"type": "create_booking",      "guest": {...}, "stay": {...}, "add_ons": {...}, "confirmation": {...}}
{"type": "modify_booking",      "lookup": {...}, "changes": {...}}
{"type": "cancel_booking",      "lookup": {...}, "fee_acknowledged": true}
{"type": "route_to_sales_team", "guest": {...}, "request": {"kind": "group_block | wedding | ...", ...}}
{"type": "transfer_to_human",   "reason": "...", "short_summary": "..."}
{"type": "request_callback",    "guest": {...}, "topic": "...", "preferred_window": "..."}
```

**Settings:** `qwen3:8b` on Ollama, temperature `0.3`, Thinking `Off`, max_tokens `600`, `include_history: true`.

**Archetype:** same skeleton as the other conversational recipes, with one extra hard rule worth noting: **never accept card details in chat.** A real PMS hands payment off to a tokenized confirmation page — the bot's job is to capture the inquiry and refuse the card. The bot also runs a hardened **pre-confirmation checklist** (room-type-in-rate-card, occupancy-fits, pet/smoking, group-block routing, no-card-in-chat, all-fields-present, **explicit affirmative trigger**, JSON-or-no-confirmation) and ships with five negative-path few-shot examples (D/E/F/G/H — invalid room + over-occupancy, card refusal, group-block routing, long-stay-books-normally, partial gather with no trigger). Stay length is **not** a routing trigger — a single guest booking 17 nights books normally. Walkthrough in **[`Hotel Reservations Bot.md`](./Hotel%20Reservations%20Bot.md)**.

---

### 12. Dentist appointment bot — [full walkthrough](./Dentist%20Appointment%20Bot.md)

Closest sibling to the Doctor's Office Bot — primary-care archetype, dental-specific facts and red flags. Answers FAQs from an explicit `PRACTICE FACTS` block (services offered, services NOT offered → ortho/wisdom teeth/oral surgery referred out, insurance, sedation/nitrous availability), books / reschedules / cancels appointments, and routes emergencies on **two tiers**:

- **911** — airway involvement, severe facial swelling with fever, suspected jaw fracture, anaphylaxis. Same urgent-redirect pattern as the Doctor's Office Bot.
- **On-call dentist or in-hours emergency slot** — knocked-out tooth (avulsion, time-critical), severe toothache unresponsive to OTC, displaced tooth from trauma, abscess without systemic signs.

**Output — visible reply PLUS (on action turns) one of:**
```json
{"type": "create_appointment",        "patient": {...}, "visit": {...}, "insurance": {...}, "confirmation": {...}}
{"type": "route_to_emergency_slot",   "patient": {...}, "issue_summary": "...", "time_first_mentioned": null}
{"type": "route_to_on_call",          "issue_summary": "...", "guidance_given": "..."}
{"type": "urgent_redirect_911",       "trigger_signs": [...], "time_first_mentioned": null}
{"type": "reschedule_appointment",    "lookup": {...}, "changes": {...}}
{"type": "cancel_appointment",        "lookup": {...}, "reason": "..."}
{"type": "transfer_to_human",         "reason": "...", "short_summary": "..."}
{"type": "request_callback",          "patient": {...}, "topic": "...", "preferred_window": "..."}
```

**Settings:** `qwen3:8b` on Ollama, temperature `0.3`, Thinking `Off`, max_tokens `600`, `include_history: true`.

**Archetype:** same conversational dual-mode pattern as the Doctor's Office Bot, with the practical addition of an explicit "services NOT offered" line in the facts block — the bot proactively refers Invisalign, wisdom-tooth extraction, full-arch implants, and IV sedation out, instead of inventing a plausible-sounding answer. Also runs a hardened **pre-confirmation checklist** (provider-in-facts, all-fields-present including insurance, time-in-office-hours, **explicit affirmative trigger**, JSON-or-no-confirmation) and three negative-path few-shot examples (D/E/F — unknown provider + missing insurance, time before opening, partial gather with no trigger). Added after live testing showed the bot would otherwise hallucinate a "Dr. Kamata" provider name when asked, and confirm without an explicit yes. Walkthrough in **[`Dentist Appointment Bot.md`](./Dentist%20Appointment%20Bot.md)**.

---

## Getting good responses from small models

Small local models are *capable* but *literal*. A few rules of thumb:

1. **Pick the right model for the task.** Vision models (llava) are weak at text-only instruction-following. Reasoning-tuned models (qwen3/qwen3.5, deepseek-r1) need Thinking configured thoughtfully. For strict behavioral prompts, reach for `qwen3:8b`, `qwen2.5:7b`, `mistral:7b`, or `gemma2:9b`.

2. **Use low temperature for structured output.** JSON, SQL, classification — `0.0`–`0.2`. Creative writing — `0.8`–`1.2`.

3. **Turn Thinking OFF by default.** Reasoning models default to thinking, which burns tokens and delays the actual answer. For most bots you want immediate output; set Thinking to `Off`. For hard reasoning tasks, use `Low`/`Medium`/`High` with a reasonable `max_thinking_tokens` cap.

4. **Be explicit about the output format.** "Respond with ONLY X, no preamble, no explanation." Models obey these instructions more reliably than you'd think.

5. **Include examples when behavior is strict.** Especially for small models. Add a `User: ... / Assistant: ...` pair or two in the system prompt — it's few-shot priming in disguise and dramatically improves adherence.

6. **Raise Max Tokens when responses get truncated.** But keep it reasonable; huge caps slow first-token latency on cold models.

7. **Test with the actual API, not just the UI.** Because the GUI and API now take exactly the same path (stateless, same endpoint, same body shape), if the UI works your API call will too. If the API disappoints but the UI looked fine, it's probably because the UI chat had accidental few-shot priming from prior turns — the stateless API won't. Add the examples to the system prompt.

### Recommended models (1B–10B)

| Model | Size | Pull | Best for |
|---|---|---|---|
| `llama3.2:1b` | ~1.3 GB | `ollama pull llama3.2:1b` | Fastest, any hardware |
| `llama3.2:3b` | ~2.0 GB | `ollama pull llama3.2:3b` | Great general default |
| `qwen2.5:3b` | ~1.9 GB | `ollama pull qwen2.5:3b` | Strong for its size |
| `qwen2.5:7b` | ~4.7 GB | `ollama pull qwen2.5:7b` | Sharp reasoning |
| `phi3:mini` | ~2.3 GB | `ollama pull phi3:mini` | Microsoft, 3.8B |
| `gemma2:2b` | ~1.6 GB | `ollama pull gemma2:2b` | Google, very snappy |
| `gemma2:9b` | ~5.4 GB | `ollama pull gemma2:9b` | Best quality under 10 GB |
| `mistral:7b` | ~4.4 GB | `ollama pull mistral:7b` | Classic 7B workhorse |
| `deepseek-r1:1.5b` | ~1.1 GB | `ollama pull deepseek-r1:1.5b` | Tiny reasoner |
| `qwen3:8b` | ~5.2 GB | `ollama pull qwen3:8b` | Reasoning + strong instruction-following |
| `gpt-oss:20b` | ~14 GB | `ollama pull gpt-oss:20b` | Largest listed; supports `think` effort levels (low/medium/high) |
| `Bonsai-8B.gguf` *(1-bit)* | **~1.15 GB** | [Bonsai-demo](https://github.com/PrismML-Eng/Bonsai-demo) → `./setup.sh` → `./scripts/start_llama_server.sh` | **Fast microservice bot.** Extreme-quantization 1-bit 8B from PrismML, served via llama.cpp on `:8080`. Tiny footprint + high-throughput inference make it the natural pick for a per-conversation microservice you plan to hammer from production code. See [Adding Bonsai](#adding-bonsai-prismmls-1-bit-8b--step-by-step). |

The UI reads `ollama list` at startup and auto-populates the model dropdown for the built-in Ollama backend. Cloud proxies and embedding-only models are filtered out. Bonsai and any other OpenAI-compat endpoint you register in Settings add their own optgroups on top.

**Picking a model for an API-heavy microservice bot:** if the conversation is a callable endpoint that downstream code will hit a lot (ticket routing, JSON extraction, sentiment, lead scoring), prefer small + fast over large + smart. Bonsai-8B (1-bit, ~1.15 GB, GPU-accelerated on port 8080) and `llama3.2:3b` or `gemma2:2b` on Ollama are the three strongest low-latency candidates today. Save the bigger reasoning models for chats where a human actually waits for each turn.

---

## Curating fine-tuning data

Every chat in MiniClosedAI is both a playground and a dataset-in-progress. The workflow is deliberately the simplest one that works for small high-quality SFT datasets: **demonstration data collection** — keep the real user prompts, rewrite imperfect assistant responses into the ideal ones, export the pairs as CSV.

That's the whole loop. No separate rating UI. No thumbs-up/down table. No second sampling pass. The chat IS the dataset editor.

### Why demonstration data (not thumbs-up / preferences)

| Approach | What you collect | Training method | Data efficiency |
|---|---|---|---|
| **Demonstration** (edit to ideal) | `(prompt, ideal_response)` pairs | Supervised fine-tuning (SFT) | ~3× stronger per example on small (<5k pair) datasets |
| **Preferences** (thumbs-up vs thumbs-down) | `(prompt, chosen, rejected)` triples | DPO / RLHF | Needs more pairs; more infra |

If you have **<5,000 pairs**, demonstration data is the canonical choice — it trains a stronger policy per example and requires nothing beyond a text editor. Preference-based DPO is the right next step when your demonstration dataset stops improving the model, typically many thousands of pairs in. That's a conscious upgrade path, not the starting point.

### The three-click curation loop

1. **Run a normal chat.** Send the kinds of prompts you want the fine-tuned model to handle well. Use all the usual MiniClosedAI tools — sliders, system prompts, Thinking, different backends — to explore.

2. **Hover any assistant response → click the pencil (top-right).** An inline textarea appears with the raw response. Rewrite it into the "ideal" version. Save (or `Ctrl/⌘+Enter`). The bubble re-renders with the new content, a small `edited` pill appears, and the pristine output is preserved under `original_content` server-side.

3. **Click the download (tray) icon in the header.** You get `<chat-title>.csv` with `input,output` columns — one row per completed user→assistant pair, edited text as the `output`. Open it in any spreadsheet, load it into `pandas`, or stream it straight into a trainer.

Repeat 1–2 as many times as you want before step 3. You can also edit user messages? **No** — only assistant responses are editable. Your real prompts are the whole point of the dataset; you're training the model to handle the prompts you actually write.

### What's in the CSV

```
input,output
"What does MiniClosedAI do?","MiniClosedAI wraps local LLMs in a playground UI and turns every chat into a callable API endpoint."
"Summarize the support ticket below:\n\n<ticket text>","{""intent"":""bug"",""urgency"":""p1"",…}"
```

- Two columns, literally named `input` and `output`.
- One row per **complete** user→assistant pair. Orphan user messages with no reply are skipped.
- RFC-4180 escaping: values containing commas, double quotes, or newlines are wrapped in double quotes and internal `"` are doubled to `""`. Every standard CSV parser (pandas, Excel, `csv.reader`) round-trips cleanly.
- Leading/trailing whitespace stripped from both cells. Important for models like LM Studio's Qwen3.6 which emit a leading `\n\n` separator between their (hidden) reasoning and the answer — training on that pollutes the target and teaches the model to emit junk whitespace.
- The file is named after the conversation title; non-alphanumeric characters collapse to `_`.

### Full workflow example

```python
import pandas as pd

# Download one conversation's data via the API (or just click the UI icon):
import httpx
csv_text = httpx.get("http://localhost:8095/api/conversations/3/export.csv").text
df = pd.read_csv(pd.io.common.StringIO(csv_text))
print(df.head())
print(f"{len(df)} pairs ready for SFT")

# Combine several curated conversations into one training file:
frames = []
for conv_id in [3, 7, 11, 18]:
    t = httpx.get(f"http://localhost:8095/api/conversations/{conv_id}/export.csv").text
    frames.append(pd.read_csv(pd.io.common.StringIO(t)))
pd.concat(frames, ignore_index=True).to_csv("sft_dataset.csv", index=False)
```

Pair `sft_dataset.csv` with any SFT runner (`axolotl`, Hugging Face `trl`, Unsloth) using its generic `input/output` column mapping — or convert to `{"messages": [...]}` JSONL with a four-line script.

### Tips for good demonstration data

- **Edit decisively.** Don't nudge — rewrite the response to look exactly like the *final answer you want the fine-tuned model to produce*. Half-hearted edits make half-hearted datasets.
- **Keep the prompts realistic.** If you'd rephrase a user message so the model would do better, you're optimizing the dataset for a prompt the user won't actually write in prod. Edit only the `output` side for SFT purposes.
- **Cover your edges.** Include a deliberate mix of easy-in-distribution examples *and* the tricky ones that used to trip the model. A handful of well-curated adversarial examples often beats hundreds of unremarkable ones.
- **Cross-conversation variety.** Create a few distinct conversations — one per task archetype (ticket router, SQL gen, sentiment, JSON extractor) — then concat their CSVs. That's closer to a real training distribution than one enormous single chat.
- **Quality over quantity.** 200 excellent pairs often out-perform 2,000 mediocre ones, especially on 1B–9B base models.

### Audit trail / DPO upgrade path

Every edited message preserves its *first* stored version under `original_content` in the conversation's `messages` JSON. The CSV export intentionally uses the edited content, but the original is still there for later use:

- **Manual audit.** Click the small `edited` pill on any rewritten message in the UI to see the pristine version.
- **DPO dataset construction.** When you outgrow SFT, you already have `(prompt, chosen=edited_content, rejected=original_content)` triples sitting in your database. A short script over the `messages` JSON emits them as a DPO JSONL file without any new UI work.

That's the full curation story: start with demonstrations today; the preference-data upgrade is a data-transformation away, not a product rebuild.

---

## LAN access

To use MiniClosedAI from your phone, a tablet, or another machine on the same network:

```bash
uvicorn app:app --host 0.0.0.0 --port 8095
```

Then open `http://<host-machine-ip>:8095` from the other device. On Linux you might also need to open the port in the firewall:

```bash
sudo ufw allow 8095/tcp
```

**No authentication ships with the app.** Only do this on a trusted network. See [Security](#security).

Snippets generated by the **API Code** modal use `window.location.origin`, so LAN visitors get snippets with their real host in the URLs automatically.

**In Docker?** The compose file defaults to loopback-only (`127.0.0.1:8095:8095`). To expose on the LAN, edit `docker-compose.yml` and drop the `127.0.0.1:` prefix — same trust model as running `uvicorn --host 0.0.0.0` on the host. See [Docker quick start → Security](#docker-quick-start-with-baked-models).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar status says *"Ollama is not running"* | Start it: `ollama serve` (Linux, foreground) or launch the Ollama app (macOS/Windows). Confirm with `curl http://localhost:11434/api/tags`. |
| Dropdown says *"no local chat models installed"* | Run `ollama pull llama3.2:3b` (or any from the table). Refresh the page. Cloud proxies and embedding-only models are filtered out on purpose. |
| First message is slow | Ollama loads the model into memory on first use (5–30 s depending on size). Subsequent messages are fast. |
| Responses truncate mid-sentence | Raise **Max Tokens** in the sidebar. |
| Response is just an empty JSON skeleton / non-responsive | Your model is probably weak for the task (e.g. llava on strict text-only prompts). Switch to a stronger instruction-follower — `qwen3:8b`, `qwen2.5:7b`, `mistral:7b`. |
| Thinking-only models never finish | They exhausted tokens on reasoning. Set **Thinking** to `Off`, raise **Max Tokens**, or set **Max thinking tokens** to force an early exit. |
| Out-of-memory errors | Pick a smaller model (`llama3.2:1b`, `gemma2:2b`, `tinyllama`). |
| Port 8095 already in use | `uvicorn app:app --port 8096` |
| Clipboard Copy does nothing on a LAN page | `navigator.clipboard` only works over HTTPS or localhost. The app falls back to `document.execCommand("copy")` on plain-HTTP — but some mobile browsers block both. Manually select and copy with Ctrl+C as a last resort. |
| Can't access from phone on the same WiFi | Bind to `0.0.0.0` (not `127.0.0.1`) and allow the port in your firewall. See [LAN access](#lan-access). |
| Sidebar settings don't apply to API calls | The sidebar auto-saves with a 350 ms debounce. The save also flushes automatically when you open **API Code** or send a message. If a one-off call still seems stale, verify with `curl http://localhost:8095/api/conversations/<id>` and look at `model`, `system_prompt`, `params`. |
| GUI answer different from API answer for the same message | Usually means the UI response was accidentally influenced by prior chat history that happened to include examples. The stateless API never replays history. Add the examples to the system prompt. |
| Add-endpoint **Test connection** says *"Reachable, but 0 models available"* | The base URL is missing `/v1` (LM Studio, vLLM, OpenAI all serve the API under `/v1/*`). Edit the endpoint and change `http://host:1234` → `http://host:1234/v1`. |
| Add-endpoint Test says **"Failed to fetch"** | Fixed. Older frontend ran the probe directly from the browser and got CORS-blocked. Hard-refresh the page — the modern Test button goes through the MiniClosedAI server. |
| LM Studio returns *"Invalid LM Studio API token"* (401) | Either paste a fresh key into the endpoint's **Edit → API key** field, or turn off *Require API key* in LM Studio's Developer tab for localhost use. |
| Qwen3/DeepSeek-R1 on LM Studio keeps reasoning with **Thinking: Off** | Your LM Studio build is ignoring both `chat_template_kwargs.enable_thinking: false` and the `/no_think` magic token. Workaround: leave Thinking on (or pick a non-reasoning model like Gemma 4 / Llama 3.2 / Mistral for strict-output tasks). The soft-truncate fix still ensures the answer arrives even when reasoning runs. |
| Bonsai endpoint returns responses that look like *another* bot's output | You pointed the Bonsai endpoint at `http://localhost:8095/v1` (MiniClosedAI's own port) instead of `http://localhost:8080/v1` (the llama.cpp server). The endpoint's model list then comes from MiniClosedAI's `/v1/models` (your saved conversation IDs), so picking one routes the chat through an unrelated bot. Edit the endpoint, change the port to **`8080`**, then reopen the Bonsai chat and reselect `Bonsai-8B.gguf` from the dropdown. |
| *"✂ Thinking hidden after N tokens. Model still finishing its reasoning; the answer will follow."* | Informational, not an error. The model exceeded your `max_thinking_tokens` soft cap; further reasoning is hidden from the UI but the stream stays open so content can still arrive. Raise the cap (or clear it) to see full thoughts; raise **Max Tokens** if the whole response gets cut off before the answer. |
| Deleting an endpoint returns 409 with `bound_conversations` | Can't delete an endpoint any bot still uses. Either rebind each listed conversation to a different endpoint (change its model from the grouped dropdown) or delete those conversations first, then retry. |
| Docker: `could not select device driver "nvidia"` on `up` | `nvidia-container-toolkit` missing on the host. `sudo apt install nvidia-container-toolkit && sudo systemctl restart docker`. Alternatively use the CPU override: `docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build`. See [Docker quick start](#docker-quick-start-with-baked-models). |
| Docker: build fails with `ENOSPC` during `ollama pull` | Docker `data-root` out of space. Check with `docker system df`, free up with `docker system prune`. Need ~15 GB headroom for the three-model build. |
| Docker: stack is `healthy` but UI shows empty model dropdown | `docker compose exec ollama ollama list` — confirms baked models. If list is empty, a bake layer silently failed: `docker compose build --no-cache ollama` to rebuild; `/tmp/ollama-serve.log` inside the container has the pull log. |
| Docker: MiniClosedAI container can't reach Ollama | `docker compose exec miniclosedai env \| grep OLLAMA_URL` must show `http://ollama:11434`. If it shows `http://localhost:...`, the compose `environment:` stanza on the `miniclosedai` service isn't loaded — did you hand-edit and typo it? |
| Docker: switching GPU ↔ CPU override has no effect | Docker layer cache. `docker compose down && docker compose up -d --build` to force a fresh build. |

---

## Testing

MiniClosedAI ships a single-file end-to-end test suite. One command, no extra dependencies, doesn't touch your real database, and doesn't require Ollama or LM Studio to be running — upstream backends are faked in-process.

```bash
python test_e2e.py
```

Typical output: **28 tests, ~1.5 seconds, exits 0 on success** (1 on any failure, so it slots into CI or a pre-commit hook with no config).

### What it checks

The suite is designed so every time you add or change a feature, running it catches the regressions that cost an afternoon to debug:

- **Schema + migration** — additive `ALTER TABLE ADD COLUMN` is non-destructive, built-in Ollama is seeded at id=1, `init_db()` is idempotent.
- **Backends CRUD** — create, patch, delete with guardrails (403 for the built-in, 409 when conversations are still bound); `api_key` scrubbed from responses.
- **Probes** — `/api/backends/{id}/status`, `/models`, and the server-side `/api/backends/test` draft probe.
- **Aggregated `/api/models`** — new grouped shape plus back-compat legacy keys.
- **Conversations** — CRUD, clear, PATCH with `null` actually clearing a saved param (the "Reset defaults" fix), 400 on `backend_id: null`.
- **Config lock** — per-conv chat endpoint rejects `temperature`, `model`, `system_prompt` as extra fields (422).
- **Routing** — per-conv chat lands on the bot's specific backend for both Ollama and OpenAI-compat kinds; verified via captured fake-server payloads.
- **Streaming** — SSE frames carry `thinking` + `chunk` + terminal `end` events.
- **Soft-cap `max_thinking_tokens`** — content still arrives after the truncated-notice (guard against the old hard-kill behavior).
- **Thinking control translation** — Off → `chat_template_kwargs.enable_thinking=false` + `/no_think` in the user message; High → `reasoning_effort: "high"`.
- **OpenAI-compat endpoint** — `/v1/chat/completions` streams + non-streams correctly, routes per the bot's backend, rejects invalid `model` field with 400; `/v1/models` lists saved conversations.
- **Legacy endpoints** — `/api/chat` still works with explicit `backend_id`.
- **Static assets** — `/` serves the activity bar + page containers; `app.js` still contains critical symbols like `initActivityBar`, `loadBackends`, `prettifyJSONInMarkdown`, `_selectModelOption`, `flushPendingSave`.

### Deliberately out of scope

- **Browser UI behavior** — theme toggle, splitter drag, modal UX, pretty-print rendering, syntax highlighting. Would need Playwright or Selenium plus a real browser.
- **Real Ollama / LM Studio API drift** — the in-process fakes guarantee reproducibility but won't catch upstream schema changes. Worth a manual smoke-test against real servers once per release.
- **Load / concurrency** — single-threaded execution, no stress tests.

### How it's wired

- Uses FastAPI's built-in `TestClient` (ships with fastapi via starlette) — no real server port, nothing to kill between runs.
- Overrides `db.DB_PATH` to a `tempfile`-managed path before importing `app`, so your real `miniclosedai.db` is never touched. Temp DB is cleaned up on exit.
- Two in-process fake servers (`FakeOllama`, `FakeOpenAI`) thread-bound on random localhost ports. Each captures every request it receives so tests assert on *outgoing payloads*, not just responses — that's how we verify `/no_think` injection, `enable_thinking: false`, `reasoning_effort`, and model routing.
- A `@test("name")` decorator auto-registers runners into an ordered list. Add a function at the bottom of the file and it runs next time — no master list to maintain.

### Using it as a pre-commit hook

```bash
cat > .git/hooks/pre-commit <<'EOF'
#!/usr/bin/env bash
.venv/bin/python test_e2e.py || { echo "e2e failed, aborting commit"; exit 1; }
EOF
chmod +x .git/hooks/pre-commit
```

Now every commit runs the suite first and refuses to record if anything is red.

---

## Project layout

```
miniclosedai/
├── app.py                     # FastAPI routes (native + OpenAI-compat, multi-backend)
├── llm.py                     # Kind-dispatched client: Ollama + OpenAI-compat
├── db.py                      # SQLite schema + MINICLOSEDAI_DB_PATH env override
├── requirements.txt           # fastapi, uvicorn, httpx  (that's all)
├── static/
│   ├── index.html             # Single-page UI (activity bar + Dashboard + Settings)
│   ├── style.css              # Design system (light + dark)
│   └── app.js                 # Theme, splitters, chat, endpoint CRUD, grouped model dropdown
├── scripts/
│   └── bake-models.sh         # Docker: background-daemon Ollama pull with clean shutdown
├── Dockerfile                 # App image — python:3.12-slim, ~160 MB
├── Dockerfile.ollama          # Ollama image with 3 models baked in, ~10.3 GB
├── docker-compose.yml         # Two-service orchestration, GPU, healthchecks
├── docker-compose.cpu.yml     # Override for CPU-only hosts (`devices: !reset []`)
├── docker-compose.lite.yml    # Lite mode: single-service, no Ollama container, MINICLOSEDAI_NO_OLLAMA=1
├── .dockerignore              # Build-context exclusions
├── README.md                  # This document
├── DOCUMENTATION.md           # Extra architecture detail (covers Docker in depth)
├── INSTALL.md                 # Per-OS Ollama install detail
├── Support Ticket Router.md   # Standalone bot recipe
├── Inbound Lead Qualifier.md  # Standalone bot recipe
├── RAG Query Router.md        # Standalone bot recipe (Bonsai-paired)
├── Doctors Office Bot.md      # Standalone bot recipe (conversational, qwen3:8b)
├── Restaurant Reservations Bot.md  # Standalone bot recipe (conversational, qwen3:8b)
├── Hotel Reservations Bot.md       # Standalone bot recipe (conversational, qwen3:8b)
├── Dentist Appointment Bot.md      # Standalone bot recipe (conversational, qwen3:8b)
├── test_e2e.py                # Single-file end-to-end regression suite (39 tests)
└── miniclosedai.db            # SQLite file (gitignored; Docker: in named volume)
```

**Backend:** ~900 LoC Python total. **Frontend:** ~1700 LoC JS + ~850 CSS + ~240 HTML. **Docker scaffolding:** ~200 LoC across 6 files.

---

## Security

**MiniClosedAI ships with no authentication.** Anyone who can reach the HTTP port can:

- Read, create, update, or delete any conversation.
- Invoke any bot's endpoint (uses your local CPU/GPU, generates any output the bot is configured to).
- Write to the SQLite file.

This is intentional — the target deployment is local-only on `127.0.0.1`, or on a trusted LAN.

If you need to expose MiniClosedAI beyond that, put it behind:

- A reverse proxy (nginx, Caddy) with basic auth or OAuth2-Proxy.
- A VPN (Tailscale, WireGuard).
- A firewall allow-list.

The app does **not** speak HTTPS directly. `navigator.clipboard` requires HTTPS or `localhost`; the app falls back to `document.execCommand("copy")` over plain-HTTP.

---

## License

MIT. See headers in each source file.
