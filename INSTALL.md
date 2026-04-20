# Installing Ollama (and MiniClosedAI)

MiniClosedAI runs LLMs locally through **[Ollama](https://ollama.com)**. Install Ollama once, pull a model, and you're done — no API keys, no cloud.

---

## 1. Install Ollama

### macOS

**Option A — App:** download `Ollama.dmg` from <https://ollama.com/download> and drag it to Applications. Launching the app starts the local server automatically.

**Option B — Homebrew:**

```bash
brew install ollama
brew services start ollama
```

Verify:

```bash
curl http://localhost:11434/api/tags
# → {"models":[]} means Ollama is running
```

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

This installs the `ollama` binary and a systemd service that starts on boot. To confirm it's running:

```bash
systemctl status ollama          # or: ollama serve (to run in foreground)
curl http://localhost:11434/api/tags
```

If the daemon isn't running under systemd, start it in a terminal:

```bash
ollama serve
```

### Windows

1. Download **OllamaSetup.exe** from <https://ollama.com/download>.
2. Run the installer. Ollama installs as a background service and starts automatically.
3. Open PowerShell and verify:

   ```powershell
   Invoke-RestMethod http://localhost:11434/api/tags
   ```

---

## 2. Pull at Least One Model

MiniClosedAI targets small models (1B–10B parameters). **Start with one of these:**

```bash
# Tiny & fast (great for laptops without a GPU)
ollama pull llama3.2:1b
ollama pull gemma2:2b
ollama pull tinyllama

# Balanced default
ollama pull llama3.2:3b
ollama pull qwen2.5:3b
ollama pull phi3:mini

# Higher quality (needs ~8 GB RAM / a decent GPU)
ollama pull qwen2.5:7b
ollama pull mistral:7b
ollama pull gemma2:9b

# Reasoning-tuned
ollama pull deepseek-r1:1.5b
ollama pull deepseek-r1:7b
```

List what you've got:

```bash
ollama list
```

Quick smoke test from the CLI:

```bash
ollama run llama3.2:3b "Say hi in five words."
```

---

## 3. Install MiniClosedAI

Requires **Python 3.10+**.

```bash
cd /path/to/miniclosedai

# (Recommended) isolate deps
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# Three deps total: fastapi, uvicorn, httpx
pip install -r requirements.txt
```

---

## 4. Run

```bash
python app.py
# or:
uvicorn app:app --host 127.0.0.1 --port 8095
```

Open **<http://localhost:8095>**.

The model dropdown in the header lists every model from your local `ollama list`. Pick one and start chatting. Parameters on the left update per-request, and the **Get API Code** button generates cURL / Python / JavaScript snippets that talk to your running server.

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| "Ollama is not running" in sidebar | Start it: `ollama serve` (Linux) or open the Ollama app (macOS/Windows). Confirm with `curl http://localhost:11434/api/tags`. |
| Model dropdown says "(no models installed)" | Run `ollama pull llama3.2:3b` (or any model). Refresh the page. |
| Responses stall / time out | Model is probably loading into memory for the first time. Give it 10–30 seconds. Subsequent messages are instant. |
| Out of memory errors | Switch to a smaller model (`llama3.2:1b`, `gemma2:2b`, `tinyllama`). |
| Port 8095 already in use | `uvicorn app:app --port 8096` |
| Ollama is on a different machine | Set `OLLAMA_URL=http://host:11434` before starting MiniClosedAI. |

---

## 6. Uninstall

```bash
# Remove pulled models (frees disk)
ollama rm llama3.2:3b qwen2.5:3b   # etc.

# macOS: drag Ollama.app to trash, or `brew uninstall ollama`
# Linux: sudo systemctl stop ollama && sudo rm /usr/local/bin/ollama
# Windows: uninstall via "Add or remove programs"
```

That's it. Everything runs locally, no data leaves your machine.
