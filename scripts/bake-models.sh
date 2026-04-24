#!/usr/bin/env bash
#
# Bakes a single Ollama model into an image layer at build time.
#
# Called from Dockerfile.ollama as `bake-models.sh <model-tag>`. Runs ONE
# model at a time so each model becomes its own image layer — swapping the
# shortlist doesn't invalidate unrelated layers.
#
# The tricky part is `ollama serve`: it's a foreground process. We background
# it, poll /api/tags until the HTTP API answers, pull the model with retries,
# then cleanly SIGTERM + wait before the RUN exits. A half-shut daemon can
# commit truncated blobs and silently break the baked model.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: bake-models.sh <model-tag>" >&2
  exit 2
fi
MODEL="$1"

echo "[bake] starting ollama serve in background for $MODEL"
/bin/ollama serve > /tmp/ollama-serve.log 2>&1 &
SERVE_PID=$!

# Poll /api/tags up to 60s. Cold-start on shared hosts has been observed up
# to 12s; 60s is a comfortable upper bound.
echo "[bake] waiting for ollama HTTP API to come up..."
for i in $(seq 1 60); do
  if curl -sSf http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
    echo "[bake] ollama API ready after ${i}s"
    break
  fi
  if ! kill -0 "$SERVE_PID" 2>/dev/null; then
    echo "FATAL: ollama serve died before HTTP API came up" >&2
    cat /tmp/ollama-serve.log >&2 || true
    exit 1
  fi
  sleep 1
done

# Final check that the API is actually responsive.
if ! curl -sSf http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
  echo "FATAL: ollama HTTP API never responded after 60s" >&2
  cat /tmp/ollama-serve.log >&2 || true
  exit 1
fi

# Pull with up to 3 retries at 3s backoff. registry.ollama.ai occasionally
# 500s on hot CDN edges; persistent failure usually means bad model tag.
echo "[bake] pulling $MODEL (max 3 attempts)"
n=0
until [ "$n" -ge 3 ]; do
  if /bin/ollama pull "$MODEL"; then
    echo "[bake] pulled $MODEL"
    break
  fi
  n=$((n + 1))
  echo "[bake] pull $MODEL failed, retry $n/3" >&2
  sleep 3
done
if [ "$n" -ge 3 ]; then
  echo "FATAL: could not pull $MODEL after 3 attempts" >&2
  cat /tmp/ollama-serve.log >&2 || true
  kill -KILL "$SERVE_PID" 2>/dev/null || true
  exit 1
fi

# Clean shutdown — SIGTERM, wait up to 10s, then SIGKILL as fallback.
# `wait` after `kill` is load-bearing: without it the background process
# may still be flushing writes when the layer gets committed.
echo "[bake] stopping ollama serve cleanly..."
kill -TERM "$SERVE_PID" 2>/dev/null || true
for i in $(seq 1 10); do
  if ! kill -0 "$SERVE_PID" 2>/dev/null; then break; fi
  sleep 1
done
kill -KILL "$SERVE_PID" 2>/dev/null || true
wait "$SERVE_PID" 2>/dev/null || true

# Sanity: confirm the model manifest is actually on disk. `ollama list`
# walks the manifest tree; the grep matches the family prefix (before ':').
# If this fails the model was persisted partially — fail the layer so the
# bug is caught at build time, not at first chat.
echo "[bake] verifying $MODEL is present on disk..."
if ! /bin/ollama list 2>/dev/null | grep -q "^${MODEL%%:*}"; then
  echo "FATAL: $MODEL missing from 'ollama list' after pull" >&2
  /bin/ollama list 2>&1 >&2 || true
  exit 1
fi

echo "[bake] done — $MODEL baked into this layer"
