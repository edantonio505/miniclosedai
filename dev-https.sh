#!/usr/bin/env bash
#
# dev-https.sh — serve MiniClosedAI over HTTPS (port 8443) with a self-signed
# cert, **for development only**, so browsers expose the microphone API on LAN
# access from another machine.
#
# Why this exists:
#   navigator.mediaDevices.getUserMedia is gated behind a "secure context" —
#   browsers expose it on https:// or http://localhost, never on a plain-HTTP
#   LAN IP like http://192.168.0.110:8095. To use the 🎤 button from your
#   laptop while MiniClosedAI runs on a different machine on your LAN, you
#   need HTTPS — even self-signed will do.
#
# What this gives you:
#   • A self-signed certificate at .devcerts/ valid for localhost + 127.0.0.1
#     + your LAN IP for 825 days. Browser will show a one-time security warning
#     ("Your connection is not private") which you click through ("Advanced →
#     Proceed to ...") — that's the expected dev UX.
#   • A second uvicorn worker on :8443 with TLS, alongside your existing HTTP
#     :8095 server. Both share the same SQLite DB and serve the same app.
#
# Not for production. For production, put a real reverse proxy (Caddy /
# nginx with a Let's Encrypt cert, or your corp CA) in front of :8095.
#
# Usage:
#   ./dev-https.sh                # default: ensure cert + start HTTPS on :8443
#   ./dev-https.sh start          # same as default
#   ./dev-https.sh stop            # stop the HTTPS uvicorn (leaves :8095 alone)
#   ./dev-https.sh status          # quick health probe + cert info
#   ./dev-https.sh regenerate     # nuke the cert and make a fresh one
#
set -euo pipefail
cd "$(dirname "$0")"

PORT="${MINICLOSEDAI_HTTPS_PORT:-8443}"
CERT_DIR=".devcerts"
CERT="${CERT_DIR}/dev-cert.pem"
KEY="${CERT_DIR}/dev-key.pem"
LOG="/tmp/miniclosedai-https.log"

LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1 || echo '')"

c_blue=$'\e[1;34m'; c_green=$'\e[1;32m'; c_red=$'\e[1;31m'; c_yellow=$'\e[1;33m'; c_off=$'\e[0m'
step() { printf "\n%s▶ %s%s\n" "$c_blue"   "$1" "$c_off"; }
ok()   { printf   "%s✓ %s%s\n" "$c_green"  "$1" "$c_off"; }
warn() { printf   "%s! %s%s\n" "$c_yellow" "$1" "$c_off"; }
die()  { printf   "%s✗ %s%s\n" "$c_red"    "$1" "$c_off" >&2; exit 1; }

generate_cert() {
  command -v openssl >/dev/null || die "openssl is not installed."
  mkdir -p "$CERT_DIR"

  # openssl req -newkey -nodes -x509 in one shot, with a temp config to set
  # Subject Alternative Names (modern browsers ignore CN; SANs are required).
  local cfg
  cfg=$(mktemp)
  cat > "$cfg" <<EOF
[req]
distinguished_name = req_dn
x509_extensions    = v3_req
prompt             = no
[req_dn]
CN = miniclosedai.dev
O  = MiniClosedAI (Development)
[v3_req]
basicConstraints     = CA:FALSE
keyUsage             = digitalSignature, keyEncipherment
extendedKeyUsage     = serverAuth
subjectAltName       = @alt_names
[alt_names]
DNS.1 = localhost
DNS.2 = miniclosedai.dev
IP.1  = 127.0.0.1
EOF
  [ -n "$LAN_IP" ] && echo "IP.2 = $LAN_IP" >> "$cfg"

  step "Generating self-signed cert (RSA 2048, 825-day validity)"
  openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout "$KEY" -out "$CERT" \
      -days 825 -config "$cfg" >/dev/null 2>&1
  rm "$cfg"
  chmod 600 "$KEY"

  ok "Cert: $CERT"
  ok "Key:  $KEY"
  ok "Valid for: localhost, 127.0.0.1${LAN_IP:+, $LAN_IP}"
}

cmd_start() {
  if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    warn "Cert not found — generating one now."
    generate_cert
  else
    ok "Using existing cert at $CERT"
  fi

  # If an HTTPS instance is already running on this port, bail out cleanly
  # instead of double-starting and producing confusing errors.
  if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
    warn "Port ${PORT} is already in use — stopping the existing instance"
    pkill -f "uvicorn app:app.*--port ${PORT}" 2>/dev/null || true
    sleep 1
  fi

  if [ ! -x .venv/bin/python ]; then
    die "Expected .venv/bin/python — adjust the script if your venv lives elsewhere."
  fi

  step "Starting MiniClosedAI on HTTPS port ${PORT}"
  nohup .venv/bin/python -m uvicorn app:app \
      --host 0.0.0.0 --port "${PORT}" \
      --ssl-certfile "${CERT}" --ssl-keyfile "${KEY}" \
      > "$LOG" 2>&1 &
  local pid=$!
  echo "uvicorn pid: $pid"

  # Wait for the port to become reachable. -k accepts the self-signed cert.
  for _ in $(seq 1 30); do
    if curl -fkS --max-time 2 "https://localhost:${PORT}/" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! curl -fkS --max-time 2 "https://localhost:${PORT}/" >/dev/null 2>&1; then
    warn "HTTPS server did not respond within 30s. Last 50 log lines:"
    tail -50 "$LOG"
    die "Bring-up failed."
  fi

  cat <<EOF

${c_green}Ready.${c_off} Visit in your browser:
  https://localhost:${PORT}                  (same machine)
${LAN_IP:+  https://${LAN_IP}:${PORT}        (LAN access — accept the warning once per browser)}

Expect "Your connection is not private" — that's the self-signed cert. Click
"Advanced → Proceed to ..." and the mic API works (origin is now https://).
Your plain HTTP server on :8095 is untouched.

Other commands:
  ./dev-https.sh stop          # stop the HTTPS server
  ./dev-https.sh status        # health probe + cert info
  ./dev-https.sh regenerate    # nuke the cert and make a fresh one

Log: $LOG
EOF
}

cmd_stop() {
  step "Stopping HTTPS server (port ${PORT})"
  if pkill -f "uvicorn app:app.*--port ${PORT}" 2>/dev/null; then
    ok "Stopped"
  else
    warn "Nothing was running on :${PORT}"
  fi
}

cmd_status() {
  step "Cert"
  if [ -f "$CERT" ]; then
    openssl x509 -in "$CERT" -noout -subject -issuer -dates \
      -ext subjectAltName 2>/dev/null | sed 's/^/  /'
  else
    echo "  (no cert yet — run: $0 regenerate)"
  fi
  step "Port ${PORT}"
  ss -tlnp 2>/dev/null | grep ":${PORT} " || echo "  (nothing listening)"
  step "Health"
  curl -fkS --max-time 2 -o /dev/null -w "  https://localhost:${PORT}/ → %{http_code}\n" \
       "https://localhost:${PORT}/" 2>/dev/null \
       || echo "  unreachable"
  [ -n "$LAN_IP" ] && curl -fkS --max-time 2 -o /dev/null -w "  https://${LAN_IP}:${PORT}/ → %{http_code}\n" \
       "https://${LAN_IP}:${PORT}/" 2>/dev/null \
       || true
}

cmd_regenerate() {
  rm -f "$CERT" "$KEY"
  generate_cert
  ok "Done. Restart the server: $0 stop && $0 start"
}

case "${1:-start}" in
  start|up)      cmd_start ;;
  stop|down)     cmd_stop ;;
  status)        cmd_status ;;
  regenerate|new) cmd_regenerate ;;
  -h|--help|help)
    grep '^#' "$0" | sed 's/^# \{0,1\}//; 1d'
    ;;
  *)
    die "Unknown command: $1 (try start | stop | status | regenerate | help)"
    ;;
esac
