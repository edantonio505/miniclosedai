#!/usr/bin/env bash
#
# start.sh — boot, monitor, and manage the MiniClosedAI voice service.
#
# Usage:
#   ./start.sh           # default: build (if needed) + start + wait for /health
#   ./start.sh up        # same as default
#   ./start.sh down      # stop the container
#   ./start.sh restart   # down then up
#   ./start.sh logs      # tail the voice service logs
#   ./start.sh health    # one-shot /health probe
#   ./start.sh status    # ports + container state + LAN URL
#
# Env vars (override before running):
#   VOICE_PORT          host port to publish (default: 8090)
#   VOICE_ASR_MODEL     faster-whisper model (default: small; use large-v3 on GPU)
#   VOICE_DEVICE        auto / cuda / cpu (default: auto)
#   VOICE_API_KEY       optional Bearer token; clients must send the same value
#
set -euo pipefail
cd "$(dirname "$0")"

PORT="${VOICE_PORT:-8090}"
HEALTH_URL="http://localhost:${PORT}/health"

# Best-guess LAN IPv4 — the address you'd paste into MiniClosedAI Settings
# if the chat app runs on a different machine on the same LAN.
LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1 || true)"

c_blue=$'\e[1;34m'; c_green=$'\e[1;32m'; c_red=$'\e[1;31m'; c_yellow=$'\e[1;33m'; c_off=$'\e[0m'
step() { printf "\n%s▶ %s%s\n" "$c_blue"   "$1" "$c_off"; }
ok()   { printf   "%s✓ %s%s\n" "$c_green"  "$1" "$c_off"; }
warn() { printf   "%s! %s%s\n" "$c_yellow" "$1" "$c_off"; }
die()  { printf   "%s✗ %s%s\n" "$c_red"    "$1" "$c_off" >&2; exit 1; }

ensure_prereqs() {
  command -v docker >/dev/null            || die "Docker is not installed."
  docker compose version >/dev/null 2>&1  || die "Docker Compose v2 plugin missing."
}

print_paste_url() {
  local url="${LAN_IP:+http://${LAN_IP}:${PORT}}"
  url="${url:-http://localhost:${PORT}}"
  cat <<EOF

${c_green}Ready.${c_off} In MiniClosedAI: Settings → LLM Endpoints → + Add endpoint
  Name:      anything you like
  Kind:      Voice (ASR + TTS)
  Base URL:  ${url}

Other commands:
  $0 logs      # tail logs
  $0 down      # stop the container
  $0 restart   # full bounce
  $0 health    # /health probe
EOF
}

cmd_up() {
  ensure_prereqs

  # ufw is best-effort — if it's active and the port isn't allowed, add a rule
  # scoped to the LAN. Silent skip otherwise (root or remote may not be available).
  if command -v ufw >/dev/null 2>&1 && sudo -n ufw status >/dev/null 2>&1; then
    if ! sudo -n ufw status | grep -qE "^${PORT}\b|^${PORT}/tcp\b"; then
      step "Adding ufw rule for port ${PORT} (LAN only)"
      sudo -n ufw allow from 192.168.0.0/24 to any port "${PORT}" proto tcp \
        comment "MiniClosedAI voice service" >/dev/null \
        && ok "ufw allowed ${PORT}/tcp from 192.168.0.0/24" \
        || warn "Could not add ufw rule automatically; run with sudo or open it manually."
    fi
  fi

  step "Building image + starting container (first build takes 5-10 minutes)"
  docker compose up -d --build

  step "Waiting for ${HEALTH_URL} (up to 6 minutes — first run also downloads models + voices)"
  local attempts=72 delay=5 elapsed=0
  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1; then
      break
    fi
    # Bail early if the container died — no point waiting for a corpse.
    if [[ "$(docker compose ps --status=exited --quiet voice 2>/dev/null)" ]]; then
      warn "The voice container exited. Last 80 log lines:"
      docker compose logs --tail 80 voice
      die "Bring-up failed."
    fi
    printf "."
    sleep "${delay}"
    elapsed=$((elapsed + delay))
  done
  printf "\n"

  if ! curl -fsS --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1; then
    warn "Service did not respond within ${elapsed}s. Last 80 log lines:"
    docker compose logs --tail 80 voice
    die "Bring-up failed."
  fi

  ok "Voice service is up: $(curl -fsS "${HEALTH_URL}")"
  print_paste_url
}

cmd_down() {
  step "Stopping voice service"
  docker compose down
  ok "Stopped (volumes preserved — \`docker volume rm voice_models voice_pipers\` to wipe model cache)"
}

cmd_logs() { docker compose logs -f voice; }

cmd_health() {
  if curl -fsS "${HEALTH_URL}"; then
    echo
  else
    die "Health probe failed. Is the container running? Try: $0 status"
  fi
}

cmd_status() {
  step "Container"
  docker compose ps voice 2>/dev/null || echo "(not running)"
  step "Host port ${PORT}"
  ss -tlnp 2>/dev/null | grep ":${PORT} " || echo "(nothing listening on :${PORT})"
  step "Health"
  curl -fsS --max-time 3 "${HEALTH_URL}" 2>/dev/null && echo || echo "(unreachable)"
  step "LAN URL"
  echo "${LAN_IP:+http://${LAN_IP}:${PORT}}${LAN_IP:-http://localhost:${PORT}}"
}

case "${1:-up}" in
  up)      cmd_up ;;
  down)    cmd_down ;;
  restart) cmd_down; cmd_up ;;
  logs)    cmd_logs ;;
  health)  cmd_health ;;
  status)  cmd_status ;;
  -h|--help|help)
    grep '^#' "$0" | sed 's/^# \{0,1\}//; 1d'
    ;;
  *)
    die "Unknown command: $1 (try up | down | restart | logs | health | status | help)"
    ;;
esac
