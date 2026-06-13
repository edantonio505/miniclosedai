# syntax=docker/dockerfile:1
#
# MiniClosedAI voice service — open-source ASR + TTS in one container.
#
# Build:
#   docker build -t miniclosedai-voice:latest .
#
# Run (local laptop, CPU only):
#   docker run --rm -p 8090:8090 \
#     -v voice_models:/root/.cache/huggingface \
#     -v voice_pipers:/voices \
#     miniclosedai-voice:latest
#
# Run (GPU pod — RunPod or anywhere with NVIDIA Container Toolkit):
#   docker run --rm --gpus all -p 8090:8090 \
#     -e VOICE_ASR_MODEL=large-v3 -e VOICE_DEVICE=cuda \
#     -v voice_models:/root/.cache/huggingface \
#     -v voice_pipers:/voices \
#     miniclosedai-voice:latest
#
# The image is GPU-capable but CPU-safe — faster-whisper auto-detects CUDA
# via torch.cuda.is_available(), and Piper falls back to ONNX-CPU when
# `VOICE_DEVICE=cuda` isn't requested. The image is the same in both cases;
# only the run-time env vars + the `--gpus all` flag change.

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# Python 3.11 + ffmpeg (soundfile / faster-whisper need it for non-WAV input).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

WORKDIR /app

# Cache the dep layer separately so model/code edits don't bust the wheel build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY asr.py tts.py call.py server.py test_client.py ./

# Volumes:
#   /root/.cache/huggingface — faster-whisper model cache
#   /voices                  — Piper .onnx voice files (auto-downloaded on first use)
RUN mkdir -p /voices /root/.cache/huggingface

ENV VOICE_PORT=8090 \
    VOICE_VOICES_DIR=/voices \
    VOICE_ASR_MODEL=small \
    VOICE_DEVICE=auto

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8090/health || exit 1

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
