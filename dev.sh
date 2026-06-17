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

c_blue=$'\e[1;34m'; c_green=$'\e[1;32m'; c_red=$'\e[1;31m'; c_yellow=$'\e[1;33m'; c_dim=$'\e[2m'; c_off=$'\e[0m'
step() { printf "\n%s▶ %s%s\n" "$c_blue"   "$1" "$c_off"; }
ok()   { printf   "%s✓ %s%s\n" "$c_green"  "$1" "$c_off"; }
warn() { printf   "%s! %s%s\n" "$c_yellow" "$1" "$c_off"; }
die()  { printf   "%s✗ %s%s\n" "$c_red"    "$1" "$c_off" >&2; exit 1; }

app_pid()    { pgrep -f "uvicorn app:app.*${PORT_APP}" | head -1; }
app_alive()  { [[ -n "$(app_pid)" ]]; }
app_health() { curl -fsSk --max-time 2 "https://localhost:${PORT_APP}/" >/dev/null 2>&1; }

voice_running() { docker compose -f $VOICE_DIR/docker-compose.yml ps --status=running --quiet voice 2>/dev/null | grep -q .; }
voice_health()  { curl -fsS --max-time 2 "http://localhost:${PORT_VOICE}/health" >/dev/null 2>&1; }

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
  if voice_running && voice_health; then
    ok "Voice service already running   ${c_dim}$(curl -fsS http://localhost:${PORT_VOICE}/health)${c_off}"
    return
  fi
  step "Starting voice service (docker compose)"
  ( cd "$VOICE_DIR" && docker compose up -d --build voice > /dev/null )
  # /health may take ~20s the first time after a fresh build (model warmup)
  for _ in $(seq 1 60); do
    if voice_health; then
      ok "Voice service ready   ${c_dim}$(curl -fsS http://localhost:${PORT_VOICE}/health)${c_off}"
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
  # `docker compose stop` (not `down`) — leaves the container defined so the
  # next `start` doesn't recreate it. Models stay on disk; restart is fast.
  if voice_running; then
    step "Stopping voice service"
    ( cd "$VOICE_DIR" && docker compose stop voice ) > /dev/null
    ok "Voice service stopped (use '$0 voice-purge' to fully remove)"
  else
    ok "Voice service not running"
  fi
}

cmd_voice_purge() {
  # Explicit teardown — removes the container so the next start rebuilds.
  step "Tearing down voice container (will rebuild on next start)"
  ( cd "$VOICE_DIR" && docker compose down ) > /dev/null
  ok "Voice service removed"
}

# By design `down` leaves the voice container running so models stay warm
# across MiniClosedAI restarts. Add `voice-purge` if you actually want to
# nuke it (e.g., after a Dockerfile change).
cmd_up()      { start_voice; start_app; }
cmd_down()    { stop_app; ok "Voice service left running (use '$0 voice-purge' to stop)"; }
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
      ok "$(curl -fsS http://localhost:${PORT_VOICE}/health)"
    else
      warn "container running but /health not responding"
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
    *)     die "logs target must be 'app' or 'voice'" ;;
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
  -h|--help|help) grep '^#' "$0" | sed 's/^# \{0,1\}//; 1d' ;;
  *)           die "Unknown command: $1 (try up | down | restart | status | test | logs | voice-purge | help)" ;;
esac
