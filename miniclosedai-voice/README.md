# miniclosedai-voice — open-source ASR + TTS in one container

Self-hosted speech for MiniClosedAI bots. A single FastAPI service in a Docker
image, exposing five endpoints that the main MiniClosedAI app wires up as a
backend (Settings → Add endpoint → **Voice (ASR + TTS)** → paste this URL).

The same image runs identically on your laptop (`docker run`) and on a RunPod
GPU pod. There's no compose-level coupling with MiniClosedAI — the two
containers find each other only through the URL you paste.

## What's inside

| Layer | Library | License | Notes |
|---|---|---|---|
| ASR | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | CTranslate2 Whisper. Multilingual. Auto-picks fp16 on GPU, int8 on CPU. |
| TTS | [Piper](https://github.com/rhasspy/piper) | MIT | ONNX runtime, ships **4 English + 4 Spanish** voices in v1. |
| HTTP | FastAPI + uvicorn | MIT | Single worker — GPU is serialized anyway. |

Voices in v1:

- English: Amy (US, F), Ryan (US, M), Alan (GB, M), Jenny (GB, F)
- Spanish: Dave (Spain, M), Sharvard (Spain, F), Claude (Mexico, F), Ald (Mexico, M)

More can be added by appending to `VOICE_CATALOG` in `tts.py` — Piper's
[voice gallery](https://rhasspy.github.io/piper-samples/) has 40+ EN and 10+ ES voices.

## Quick start

The fastest way — `./start.sh` handles everything (build, ufw rule, container, health poll, prints the URL to paste into MiniClosedAI):

```bash
cd miniclosedai-voice
./start.sh             # build (if needed) + start + wait for /health
./start.sh logs        # tail the logs
./start.sh status      # ports, container state, LAN URL
./start.sh down        # stop
./start.sh restart     # bounce
./start.sh health      # one-shot /health probe
```

If you'd rather drive Docker directly:

```bash
# Build
docker build -t miniclosedai-voice:latest .

# Run (CPU; works on any laptop)
docker run --rm -p 8090:8090 \
    -v voice_models:/root/.cache/huggingface \
    -v voice_pipers:/voices \
    miniclosedai-voice:latest

# Run (GPU; RunPod or any NVIDIA host)
docker run --rm --gpus all -p 8090:8090 \
    -e VOICE_ASR_MODEL=large-v3 -e VOICE_DEVICE=cuda \
    -v voice_models:/root/.cache/huggingface \
    -v voice_pipers:/voices \
    miniclosedai-voice:latest

# Or via compose (uses docker-compose.yml in this folder)
docker compose up -d --build
```

The two volumes (`voice_models` for the whisper cache, `voice_pipers` for the
Piper .onnx voices) make cold starts after the first ~instant. First start
downloads ~250 MB of voices and a whisper model.

## API

```text
GET  /health           — {ok, asr_model, tts_model, device, voices_loaded}
GET  /voices           — {"en": [{id,name,gender}, ...], "es": [...]}
POST /transcribe       — multipart audio (+optional language)  →  {text, language, segments}
POST /speak            — JSON {text, voice, language, speed?}  →  audio/wav
POST /speak/stream     — JSON {text, voice, language, speed?}  →  SSE chunk_b64 × N + done:true
```

OpenAPI lives at `http://localhost:8090/docs` once the container is up.

### Quick sanity checks

```bash
# /health (instant)
curl localhost:8090/health

# /voices catalog
curl localhost:8090/voices | python3 -m json.tool

# Transcribe a WAV
curl -F audio=@hello.wav localhost:8090/transcribe

# Speak English
curl -X POST localhost:8090/speak \
    -H 'Content-Type: application/json' \
    -d '{"text":"Hello from MiniClosedAI.","voice":"en_US-amy-medium","language":"en"}' \
    -o hello-en.wav

# Speak Spanish
curl -X POST localhost:8090/speak \
    -H 'Content-Type: application/json' \
    -d '{"text":"Hola desde MiniClosedAI.","voice":"es_MX-claude-high","language":"es"}' \
    -o hello-es.wav
```

## Configuration (env vars)

| Var | Default | Notes |
|---|---|---|
| `VOICE_ASR_MODEL` | `small` | `tiny` / `base` / `small` / `medium` / `large-v3`. CPU is happy up to `small`; GPU can run `large-v3`. |
| `VOICE_DEVICE` | `auto` | `auto` / `cuda` / `cpu`. `auto` picks CUDA when `torch.cuda.is_available()`. |
| `VOICE_VOICES_DIR` | `/voices` | Where Piper `.onnx` files cache. Mount a volume for persistence. |
| `VOICE_PORT` | `8090` | The port uvicorn binds. |
| `VOICE_API_KEY` | *(unset)* | If set, every request must carry `Authorization: Bearer <key>`. Leave unset for trusted LAN. |

## Plugging into MiniClosedAI

Once the container is up at `http://localhost:8090` (local) or
`https://<pod-id>-8090.proxy.runpod.net` (RunPod):

1. Open MiniClosedAI → **Settings → LLM Endpoints → + Add endpoint**.
2. Pick **Voice (ASR + TTS)**.
3. Paste the URL. Add the `VOICE_API_KEY` as the API key field if you set one.
4. Click **Test**. You'll see the voices catalog populate.
5. Open any bot → sidebar **Parameters** → pick a voice + language.
6. Hold the 🎤 button on the chat composer to talk to the bot.

(The push-to-talk UI ships in MiniClosedAI; this service only does ASR + TTS.)

## Roadmap

- Better-sounding TTS: swap Piper for XTTS-v2 or F5-TTS behind the same
  `/speak/stream` contract once a clean MIT-licensed option matures.
- Voice cloning: upload a 10-second reference WAV → cloned voice.
- Streaming ASR (partial transcripts during a long utterance).
- Per-language LoRA adapters on whisper for domain tuning (your other repo
  already has a recipe — port the `lora_adapters/` layout straight in).

## License

MIT (matches the rest of MiniClosedAI). The bundled voices keep their original
Piper licenses (also permissive; see the
[Piper voice list](https://huggingface.co/rhasspy/piper-voices)).
