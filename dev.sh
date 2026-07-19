#!/usr/bin/env bash
#
# dev.sh — one-command bring-up for the full MiniClosedAI + voice service.
#
# Usage:
#   ./dev.sh              # default: ensure both servers are up + healthy
#   ./dev.sh up           # same as default
#   ./dev.sh down         # stop both
#   ./dev.sh restart      # down then up
#   ./dev.sh status       # health probe both
#   ./dev.sh test         # run the call-quality harness
#   ./dev.sh logs voice   # tail voice container logs
#   ./dev.sh logs app     # tail MiniClosedAI uvicorn logs
#
# Servers:
#   MiniClosedAI  → https://0.0.0.0:8095  (uvicorn + self-signed TLS)
#   Voice service → http://0.0.0.0:8090   (docker container)
#
# Voice backend ("audio" / kind=voice / http://192.168.0.110:8090) is already
# in the SQLite db from the first GUI registration — nothing to set up there.
#
set -euo pipefail
cd "$(dirname "$0")"

PORT_APP=8095
PORT_VOICE=8090
APP_LOG=/tmp/miniclosedai.log
CERT=.devcerts/dev-cert.pem
KEY=.devcerts/dev-key.pem

# Voice server lives in its own repo, alongside this one by default. Override
# with MINICLOSEDAI_VOICE_DIR for non-default checkouts (e.g., on RunPod).
VOICE_DIR="${MINICLOSEDAI_VOICE_DIR:-$(cd "$(dirname "$0")" && cd .. && pwd)/miniclosedai-voice}"

# LLM model manager (miniclosedai-llm) — sibling repo, same convention. On a
# CUDA-capable box, `up` brings all THREE systems online: voice (ASR+TTS),
# the LLM manager, and MiniClosedAI itself. The manager's own dev.sh
# auto-detects the launch engine (docker vs native vllm) and the GPU.
LLM_DIR="${MINICLOSEDAI_LLM_DIR:-$(cd "$(dirname "$0")" && cd .. && pwd)/miniclosedai-llm}"
PORT_LLM=8099
LLM_LOG=/tmp/miniclosedai-llm.log

llm_pid()    { pgrep -f "uvicorn app:app.*${PORT_LLM}" | head -1; }
llm_alive()  { [[ -n "$(llm_pid)" ]]; }
llm_health() { curl -fsS --max-time 2 "http://localhost:${PORT_LLM}/api/health" >/dev/null 2>&1; }

# CUDA gate: the voice service (ASR+TTS) and the LLM model server are GPU
# workloads — on a box without working CUDA they'd either crawl (CPU TTS) or
# fail to load models. `up` starts them ONLY when nvidia-smi answers; the
# Models / Voice Studio tabs degrade to their friendly "not running" state.
# Override with MINICLOSEDAI_FORCE_GPU_SERVICES=1 (e.g. CPU-only debugging).
cuda_available() {
  [[ "${MINICLOSEDAI_FORCE_GPU_SERVICES:-}" == "1" ]] && return 0
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1
}

c_blue=$'\e[1;34m'; c_green=$'\e[1;32m'; c_red=$'\e[1;31m'; c_yellow=$'\e[1;33m'; c_dim=$'\e[2m'; c_off=$'\e[0m'
step() { printf "\n%s▶ %s%s\n" "$c_blue"   "$1" "$c_off"; }
ok()   { printf   "%s✓ %s%s\n" "$c_green"  "$1" "$c_off"; }
warn() { printf   "%s! %s%s\n" "$c_yellow" "$1" "$c_off"; }
die()  { printf   "%s✗ %s%s\n" "$c_red"    "$1" "$c_off" >&2; exit 1; }

app_pid()    { pgrep -f "uvicorn app:app.*${PORT_APP}" | head -1; }
app_alive()  { [[ -n "$(app_pid)" ]]; }
app_health() { curl -fsSk --max-time 2 "https://localhost:${PORT_APP}/" >/dev/null 2>&1; }

# Voice service state probes — work for BOTH the bare-metal HTTPS path
# (preferred on this box; the sibling repo's ./dev.sh runs it via start.sh)
# AND the legacy Docker path (kept as fallback). We always check HTTPS first
# since that's the new default — bare-metal start.sh auto-generates a
# self-signed cert covering localhost + the LAN IP.
voice_pid()          { pgrep -f "uvicorn server:app.*${PORT_VOICE}" | head -1; }
voice_proc_alive()   { [[ -n "$(voice_pid)" ]]; }
voice_docker_alive() { docker compose -f "$VOICE_DIR/docker-compose.yml" ps --status=running --quiet voice 2>/dev/null | grep -q .; }
voice_running()      { voice_proc_alive || voice_docker_alive; }
voice_health() {
  curl -fsSk --max-time 2 "https://localhost:${PORT_VOICE}/health" >/dev/null 2>&1 ||
  curl -fsS  --max-time 2 "http://localhost:${PORT_VOICE}/health"  >/dev/null 2>&1
}
voice_health_body() {
  # Echo the /health JSON so the "ready" line can show what loaded. Tries
  # HTTPS first, falls back to HTTP.
  curl -fsSk --max-time 2 "https://localhost:${PORT_VOICE}/health" 2>/dev/null ||
  curl -fsS  --max-time 2 "http://localhost:${PORT_VOICE}/health"  2>/dev/null
}

ensure_cert() {
  [[ -f "$CERT" && -f "$KEY" ]] && return
  step "Generating self-signed dev cert at .devcerts/"
  mkdir -p .devcerts
  openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
    -keyout "$KEY" -out "$CERT" \
    -subj "/CN=miniclosedai-dev" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)" \
    >/dev/null 2>&1 || die "openssl failed"
  ok "Cert generated"
}

start_app() {
  if app_alive; then
    ok "MiniClosedAI already running (pid $(app_pid))"
    return
  fi
  ensure_cert
  step "Starting MiniClosedAI on https://0.0.0.0:${PORT_APP}"
  nohup .venv/bin/python -m uvicorn app:app \
    --host 0.0.0.0 --port "$PORT_APP" \
    --ssl-certfile "$CERT" --ssl-keyfile "$KEY" \
    > "$APP_LOG" 2>&1 &
  disown
  # wait up to 15s for /
  for _ in $(seq 1 30); do
    if app_health; then
      ok "MiniClosedAI ready (pid $(app_pid))   ${c_dim}https://localhost:${PORT_APP}/  → log: $APP_LOG${c_off}"
      return
    fi
    sleep 0.5
  done
  warn "MiniClosedAI didn't respond in 15s. Last 30 lines of $APP_LOG:"
  tail -30 "$APP_LOG"
  die "MiniClosedAI bring-up failed"
}

start_voice() {
  # Fast path: already up and healthy.
  if voice_running && voice_health; then
    ok "Voice service already running   ${c_dim}$(voice_health_body)${c_off}"
    return
  fi

  # If a Docker container is up but bare-metal sibling exists, the container
  # is silently squatting on port 8090 — the bare-metal start.sh will then
  # fail with EADDRINUSE. Take the container down first so bare-metal can
  # claim the port. (This is the failure mode we hit repeatedly: an old
  # Docker session held the port even after `docker compose down voice`
  # because restart=unless-stopped kept respawning it.)
  if voice_docker_alive && [[ -x "$VOICE_DIR/dev.sh" ]]; then
    step "Stopping stale Docker voice container so bare-metal can bind :$PORT_VOICE"
    ( cd "$VOICE_DIR" && docker compose down voice ) > /dev/null 2>&1
    sleep 1
  fi

  # Preferred path: bare-metal HTTPS via the sibling repo's dev.sh.
  # This is the proven-working path on the Blackwell GB10 host (Docker hits
  # CUDA sm_121 JIT issues that bare-metal's warmed-up venv avoids).
  if [[ -x "$VOICE_DIR/dev.sh" ]]; then
    step "Starting voice service (bare-metal HTTPS via $VOICE_DIR/dev.sh up)"
    ( cd "$VOICE_DIR" && ./dev.sh up > /dev/null 2>&1 ) || true
    # /health may take ~20s on first launch (model warmup).
    for _ in $(seq 1 60); do
      if voice_health; then
        ok "Voice service ready   ${c_dim}$(voice_health_body)${c_off}"
        return
      fi
      sleep 1
    done
    warn "Voice didn't respond in 60s. Last 30 lines of /tmp/voice.log:"
    tail -30 /tmp/voice.log 2>/dev/null || warn "(no log file)"
    die "Voice bring-up failed"
  fi

  # Fallback path: legacy Docker compose (kept for environments where
  # bare-metal setup isn't done — most non-Blackwell boxes work fine here).
  step "Starting voice service (docker compose — sibling dev.sh not found)"
  ( cd "$VOICE_DIR" && docker compose up -d --build voice > /dev/null )
  for _ in $(seq 1 60); do
    if voice_health; then
      ok "Voice service ready   ${c_dim}$(voice_health_body)${c_off}"
      return
    fi
    sleep 1
  done
  warn "Voice didn't respond in 60s. Last 30 log lines:"
  ( cd "$VOICE_DIR" && docker compose logs --tail 30 voice )
  die "Voice bring-up failed"
}

stop_app() {
  if app_alive; then
    step "Stopping MiniClosedAI (pid $(app_pid))"
    kill "$(app_pid)" 2>/dev/null || true
    for _ in $(seq 1 10); do
      app_alive || { ok "MiniClosedAI stopped"; return; }
      sleep 0.3
    done
    warn "Force-killing"
    kill -9 "$(app_pid)" 2>/dev/null || true
  else
    ok "MiniClosedAI not running"
  fi
}

stop_voice() {
  # Stop whichever path is currently up. Bare-metal first (most common
  # nowadays), then any leftover Docker container.
  local stopped=0
  if voice_proc_alive && [[ -x "$VOICE_DIR/dev.sh" ]]; then
    step "Stopping bare-metal voice service"
    ( cd "$VOICE_DIR" && ./dev.sh down > /dev/null 2>&1 ) || true
    stopped=1
  fi
  if voice_docker_alive; then
    step "Stopping voice service container"
    ( cd "$VOICE_DIR" && docker compose stop voice ) > /dev/null 2>&1 || true
    stopped=1
  fi
  if [[ $stopped -eq 0 ]]; then
    ok "Voice service not running"
  else
    ok "Voice service stopped"
  fi
}

cmd_voice_purge() {
  # Explicit teardown — stop bare-metal AND remove the Docker container so
  # the next start rebuilds cleanly. Use after a Dockerfile or venv change.
  step "Tearing down all voice service paths"
  ( cd "$VOICE_DIR" && ./dev.sh down > /dev/null 2>&1 ) || true
  ( cd "$VOICE_DIR" && docker compose down ) > /dev/null 2>&1 || true
  ok "Voice service removed"
}

start_llm() {
  if llm_alive && llm_health; then
    ok "LLM manager already running (pid $(llm_pid))   ${c_dim}http://localhost:${PORT_LLM}/${c_off}"
    return
  fi
  if [[ ! -x "$LLM_DIR/dev.sh" ]]; then
    warn "miniclosedai-llm not found at $LLM_DIR — Models tab will show 'not running' (set MINICLOSEDAI_LLM_DIR)"
    return
  fi
  step "Starting LLM manager (miniclosedai-llm on :${PORT_LLM})"
  ( cd "$LLM_DIR" && nohup ./dev.sh > "$LLM_LOG" 2>&1 & disown ) || true
  for _ in $(seq 1 30); do
    if llm_health; then
      ok "LLM manager ready (pid $(llm_pid))   ${c_dim}http://localhost:${PORT_LLM}/  → log: $LLM_LOG${c_off}"
      return
    fi
    sleep 1
  done
  warn "LLM manager didn't respond in 30s. Last 15 lines of $LLM_LOG:"
  tail -15 "$LLM_LOG" 2>/dev/null || true
  warn "Continuing without it — the Models tab will show 'not running'."
}

stop_llm() {
  if llm_alive; then
    step "Stopping LLM manager (pid $(llm_pid))"
    kill "$(llm_pid)" 2>/dev/null || true
    ok "LLM manager stopped"
  else
    ok "LLM manager not running"
  fi
}

# By design `down` leaves the voice container AND the LLM manager running so
# models stay warm across MiniClosedAI restarts. Use `voice-purge` /
# `llm-stop` to actually stop them.
cmd_up() {
  if cuda_available; then
    start_voice
    start_llm
  else
    warn "No working CUDA on this machine (nvidia-smi absent/failing) — skipping the"
    warn "voice service and LLM model server. MiniClosedAI still runs; register remote"
    warn "endpoints in Settings, or set MINICLOSEDAI_FORCE_GPU_SERVICES=1 to override."
  fi
  start_app
}
cmd_down()    { stop_app; ok "Voice service + LLM manager left running (use '$0 voice-purge' / '$0 llm-stop')"; }
cmd_restart() { cmd_down; cmd_up; }

cmd_status() {
  step "MiniClosedAI"
  if app_alive; then
    if app_health; then
      ok  "pid $(app_pid)  https://localhost:${PORT_APP}/  ✓"
    else
      warn "pid $(app_pid)  but / is not responding"
    fi
  else
    warn "not running"
  fi
  step "Voice service"
  if voice_running; then
    if voice_health; then
      # Show scheme + body so it's obvious whether bare-metal HTTPS or
      # Docker HTTP is active.
      local scheme=""
      curl -fsSk --max-time 2 "https://localhost:${PORT_VOICE}/health" >/dev/null 2>&1 && scheme="https" || scheme="http"
      ok "${scheme}://localhost:${PORT_VOICE}/   $(voice_health_body)"
    else
      warn "running but /health not responding"
    fi
  else
    warn "not running"
  fi
  step "LLM manager (miniclosedai-llm)"
  if llm_alive; then
    if llm_health; then
      ok "pid $(llm_pid)  http://localhost:${PORT_LLM}/  ✓"
    else
      warn "pid $(llm_pid)  but /api/health is not responding"
    fi
  else
    warn "not running"
  fi
  step "Registered voice backends in DB"
  .venv/bin/python -c "
import sqlite3
db = sqlite3.connect('miniclosedai.db')
db.row_factory = sqlite3.Row
rows = list(db.execute(\"SELECT id, name, base_url, enabled FROM backends WHERE kind='voice' ORDER BY id\"))
for r in rows:
    print(f'  id={r[\"id\"]}  enabled={r[\"enabled\"]}  {r[\"name\"]:<20}  {r[\"base_url\"]}')
if not rows:
    print('  (none — register via Settings → Add endpoint → Kind: Voice)')
" 2>/dev/null
}

cmd_test() {
  app_health   || die "MiniClosedAI not healthy — run $0 up first"
  voice_health || die "Voice service not healthy — run $0 up first"
  step "Running call-quality test (conv 94)"
  .venv/bin/python tools/test_call.py --conv-id 94 "${@:1}"
}

cmd_logs() {
  case "${1:-app}" in
    app)   tail -f "$APP_LOG" ;;
    voice) ( cd "$VOICE_DIR" && docker compose logs -f voice ) ;;
    llm)   tail -f "$LLM_LOG" ;;
    *)     die "logs target must be 'app', 'voice', or 'llm'" ;;
  esac
}

case "${1:-up}" in
  up)          cmd_up ;;
  down)        cmd_down ;;
  restart)     cmd_restart ;;
  status)      cmd_status ;;
  test)        shift; cmd_test "$@" ;;
  logs)        shift; cmd_logs "$@" ;;
  voice-purge) cmd_voice_purge ;;
  llm-stop)    stop_llm ;;
  -h|--help|help) grep '^#' "$0" | sed 's/^# \{0,1\}//; 1d' ;;
  *)           die "Unknown command: $1 (try up | down | restart | status | test | logs | voice-purge | llm-stop | help)" ;;
esac
