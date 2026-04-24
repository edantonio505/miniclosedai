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

# Poll up to 180s. The Ollama daemon's first startup on a fresh
# /root/.ollama generates an SSH host key (~30s on some hosts) before the
# HTTP port binds. Observed ~60s cold-start during smoke-testing; 180s is
# a generous upper bound so this never false-negatives.
#
# We use `ollama list` as the probe rather than curl/wget — the base
# ollama/ollama image doesn't include any HTTP client binaries, but the
# `ollama` CLI itself talks to /api/tags internally. Exit 0 = daemon up
# and answering; non-zero = daemon not ready yet.
echo "[bake] waiting for ollama HTTP API to come up..."
for i in $(seq 1 180); do
  if /bin/ollama list > /dev/null 2>&1; then
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
if ! /bin/ollama list > /dev/null 2>&1; then
  echo "FATAL: ollama HTTP API never responded after 180s" >&2
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

# Sanity: confirm the model manifest is actually present. We run this
# WHILE the daemon is still alive — `ollama list` goes through /api/tags,
# which requires the HTTP server to be running. If the check fails the
# model was persisted partially and the layer should fail.
echo "[bake] verifying $MODEL is present on disk..."
if ! /bin/ollama list 2>/dev/null | grep -q "^${MODEL%%:*}"; then
  echo "FATAL: $MODEL missing from 'ollama list' after pull" >&2
  /bin/ollama list 2>&1 >&2 || true
  kill -KILL "$SERVE_PID" 2>/dev/null || true
  exit 1
fi

# Clean shutdown — SIGTERM, wait up to 10s, then SIGKILL as fallback.
# `wait` after `kill` is load-bearing: without it the background process
# may still be flushing writes when the layer gets committed, producing
# truncated blobs and silently-broken baked models.
echo "[bake] stopping ollama serve cleanly..."
kill -TERM "$SERVE_PID" 2>/dev/null || true
for i in $(seq 1 10); do
  if ! kill -0 "$SERVE_PID" 2>/dev/null; then break; fi
  sleep 1
done
kill -KILL "$SERVE_PID" 2>/dev/null || true
wait "$SERVE_PID" 2>/dev/null || true

echo "[bake] done — $MODEL baked into this layer"
