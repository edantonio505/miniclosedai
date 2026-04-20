# MiniClosedAI

A tiny, 100%-local LLM playground. Chat with small Ollama models (1B–10B parameters), tweak sampling parameters live, and turn each saved chat into a callable API endpoint. **No cloud, no API keys, no accounts.**

Built with **FastAPI** (3 Python deps), vanilla JS, and SQLite. Runs on your laptop.

![stack](https://img.shields.io/badge/FastAPI-0.110+-009688) ![Ollama](https://img.shields.io/badge/Ollama-local-000000) ![license](https://img.shields.io/badge/license-MIT-blue)

---

## Highlights

- 🧠 **Local-only inference** via Ollama — no data leaves your machine.
- 🎛️ **Live parameter sliders** — temperature, max tokens, top-p, top-k, thinking level, max thinking tokens.
- 🔁 **Per-chat microservice endpoints** — each conversation is an addressable URL (`/api/conversations/{id}/chat/stream`) with its own saved config. Call it with just `{"message": "..."}`.
- ⏹ **Manual + automatic stop** — abort generation with one click, or auto-cap runaway reasoning with `max_thinking_tokens`.
- 💭 **Reasoning-model aware** — displays "thinking" tokens separately (qwen3/qwen3.5, deepseek-r1, gpt-oss).
- 🎚️ **Resizable splitters** — drag both the sidebar width and the System Prompt height; preferences persist.
- 📝 **Markdown + code highlighting** in responses (marked.js).
- 🗂️ **Conversation history** auto-saved to SQLite; clear, delete, and switch via the header dropdown.
- 🔧 **Auto-generated API snippets** — copy working cURL, Python, or JavaScript for any saved chat.

---

## Requirements

- **Python 3.10+**
- **[Ollama](https://ollama.com)** running locally on `http://localhost:11434` (default).
- At least **one model pulled** (see the list below).
- ~2 GB of RAM free for the smallest models; 8+ GB for the 7B class.

---

## Quick start

```bash
# 1. Install Ollama (macOS shown; see INSTALL.md for Linux/Windows)
brew install ollama && brew services start ollama

# 2. Pull a small model
ollama pull llama3.2:3b

# 3. Install MiniClosedAI
cd miniclosedai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. Run
python app.py
# → open http://localhost:8095
```

More detail (including Linux and Windows install, firewall tips, LAN access, troubleshooting) in **[INSTALL.md](./INSTALL.md)**.

For architecture, full API reference, and how the per-chat microservice pattern works, see **[DOCUMENTATION.md](./DOCUMENTATION.md)**.

---

## Recommended models (1B–10B)

MiniClosedAI is designed for **small, fast models** that run on a laptop CPU or a modest GPU:

| Model | Size | Pull | Notes |
|---|---|---|---|
| `llama3.2:1b` | ~1.3 GB | `ollama pull llama3.2:1b` | Fastest, runs on any machine |
| `llama3.2:3b` | ~2.0 GB | `ollama pull llama3.2:3b` | Great default |
| `qwen2.5:3b` | ~1.9 GB | `ollama pull qwen2.5:3b` | Strong for its size |
| `qwen2.5:7b` | ~4.7 GB | `ollama pull qwen2.5:7b` | Sharper reasoning |
| `phi3:mini` | ~2.3 GB | `ollama pull phi3:mini` | Microsoft, 3.8B |
| `gemma2:2b` | ~1.6 GB | `ollama pull gemma2:2b` | Google, snappy |
| `gemma2:9b` | ~5.4 GB | `ollama pull gemma2:9b` | Best quality in this range |
| `mistral:7b` | ~4.4 GB | `ollama pull mistral:7b` | Classic 7B |
| `deepseek-r1:1.5b` | ~1.1 GB | `ollama pull deepseek-r1:1.5b` | Reasoning, tiny |
| `qwen3:8b` | ~5.2 GB | `ollama pull qwen3:8b` | Reasoning-capable |
| `gpt-oss:20b` | ~14 GB | `ollama pull gpt-oss:20b` | Supports `think` effort levels |

The UI reads `ollama list` at startup and auto-populates the model dropdown. Cloud and embedding-only models are filtered out.

---

## Running on your LAN

To access MiniClosedAI from another device on your network:

```bash
uvicorn app:app --host 0.0.0.0 --port 8095
```

Then open `http://<your-machine-ip>:8095` from the other device. There is **no authentication** — only do this on a trusted network. See [DOCUMENTATION.md](./DOCUMENTATION.md#security) for details.

---

## What can I do with it?

MiniClosedAI shines as a **local microservice factory**: each chat you save becomes a callable API endpoint with its own model, system prompt, and sampling params. Build a bot once in the UI, then hit it from your own apps with a one-line JSON body.

Example: a deterministic information-extraction service.

```bash
# 1. In the UI, create a chat with:
#    model = qwen2.5:7b, temperature = 0.1, think = off
#    system prompt = "You are a JSON extractor; return {summary, facts[], entities[]} ..."

# 2. Call it from anywhere:
curl -X POST http://localhost:8095/api/conversations/3/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "paste any article/email/notes here"}'

# → returns structured JSON, no prose
```

Full walkthrough in [DOCUMENTATION.md → Per-chat microservice pattern](./DOCUMENTATION.md#per-chat-microservice-pattern).

---

## Project layout

```
miniclosedai/
├── app.py                # FastAPI routes
├── llm.py                # Ollama HTTP client (streaming, reasoning-aware)
├── db.py                 # SQLite schema + helpers
├── requirements.txt      # fastapi, uvicorn, httpx
├── static/
│   ├── index.html        # UI
│   ├── style.css
│   └── app.js
├── README.md             # this file
├── DOCUMENTATION.md      # architecture + full API reference
├── INSTALL.md            # per-OS Ollama install guide
└── CLAUDE.md             # notes for AI coding assistants
```

---

## License

MIT.
