#!/usr/bin/env bash
# MiniClosedAI in-place upgrade script.
#
# Pulls main, reinstalls deps, restarts uvicorn on PORT (default 8095),
# verifies the new server actually comes up, and ROLLS BACK to the
# previous SHA on any failure so a broken upgrade can't strand you.
#
# Two ways to invoke:
#   ./upgrade.sh                  — from the terminal (you'll see output)
#   POST /api/upgrade/run         — from the GUI Update button (server
#                                   spawns this script in a detached
#                                   session, then this script outlives
#                                   the server it was launched from)
#
# Progress is written to /tmp/miniclosedai-upgrade.json so the GUI can
# poll it and show meaningful state.

set -uo pipefail

PORT="${MINICLOSEDAI_PORT:-8095}"
PROGRESS=/tmp/miniclosedai-upgrade.json
LOG=/tmp/miniclosedai-upgrade.log
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Helper: write a JSON progress record. Phases the GUI shows: pulling,
# installing, restarting, verifying, done, failed.
write_state() {
    local state="$1" error_msg="${2:-}" from="${3:-}" to="${4:-}"
    local err_field
    if [ -z "$error_msg" ]; then err_field='null'
    else err_field=$(printf '%s' "$error_msg" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
    fi
    cat > "$PROGRESS" <<EOF
{"state":"$state","error":$err_field,"from_sha":"$from","to_sha":"$to","ts":"$(date -Iseconds)"}
EOF
}

fail() {
    write_state "failed" "$1" "${PREV_SHORT:-}" "${NEW_SHORT:-}"
    echo "✗ $1" >&2
    exit 1
}

# Give the GUI's POST /api/upgrade/run a moment to flush its 202 response
# before we go and kill the server. Skipped when run from terminal (no
# parent we'd interrupt).
[ "${MINICLOSEDAI_UPGRADE_VIA_GUI:-0}" = "1" ] && sleep 1

# 1. Preflight ---------------------------------------------------------------
[ -d .git ] || fail "not a git checkout"

PREV_SHA=$(git rev-parse HEAD)
PREV_SHORT=$(git rev-parse --short HEAD)
NEW_SHORT="$PREV_SHORT"  # placeholder until we pull

if [ -n "$(git status --porcelain)" ]; then
    fail "local changes present — commit, stash, or 'git checkout -- .' first"
fi

write_state "pulling" "" "$PREV_SHORT" ""
echo "Currently on $PREV_SHORT. Pulling latest…"

# 2. git pull ----------------------------------------------------------------
git fetch --prune origin main >>"$LOG" 2>&1 || fail "git fetch failed (see $LOG)"
git pull --ff-only origin main >>"$LOG" 2>&1 || fail "git pull --ff-only failed (see $LOG)"

NEW_SHA=$(git rev-parse HEAD)
NEW_SHORT=$(git rev-parse --short HEAD)

if [ "$PREV_SHA" = "$NEW_SHA" ]; then
    write_state "done" "" "$PREV_SHORT" "$NEW_SHORT"
    echo "Already on latest ($NEW_SHORT)."
    exit 0
fi

# 3. pip install -------------------------------------------------------------
write_state "installing" "" "$PREV_SHORT" "$NEW_SHORT"
echo "Installing dependencies…"
if [ -x ".venv/bin/pip" ]; then
    PIP=".venv/bin/pip"
else
    PIP="pip"
fi
"$PIP" install -qr requirements.txt >>"$LOG" 2>&1 || {
    git reset --hard "$PREV_SHA" >>"$LOG" 2>&1
    fail "pip install failed; rolled back to $PREV_SHORT (see $LOG)"
}

# 4. Restart uvicorn ---------------------------------------------------------
write_state "restarting" "" "$PREV_SHORT" "$NEW_SHORT"

# Stop the running server (if any). We started detached, so it might or
# might not be a child of this script — find it by command line.
OLD_PID=$(pgrep -f "uvicorn app:app" | head -1 || true)
if [ -n "$OLD_PID" ]; then
    echo "Stopping running server (pid $OLD_PID)…"
    kill "$OLD_PID" 2>/dev/null || true
    # Wait up to 5s for graceful shutdown.
    for _ in 1 2 3 4 5; do
        kill -0 "$OLD_PID" 2>/dev/null || break
        sleep 1
    done
    # Force-kill if still alive.
    kill -9 "$OLD_PID" 2>/dev/null || true
fi

# Pick the right Python.
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    PY="python3"
fi

# Spawn the new server detached so it survives this script exiting.
echo "Starting new server…"
nohup "$PY" -m uvicorn app:app --host 0.0.0.0 --port "$PORT" \
    >>/tmp/miniclosedai.log 2>&1 &
NEW_PID=$!
disown 2>/dev/null || true

# 5. Verify the new server actually came up ---------------------------------
write_state "verifying" "" "$PREV_SHORT" "$NEW_SHORT"

# Give it up to 15s to bind the port and answer /api/upgrade/status.
# Polling at 0.5s intervals catches a typical 1–3s startup.
UP=0
for _ in $(seq 1 30); do
    sleep 0.5
    if curl -sf -m 2 "http://127.0.0.1:$PORT/api/upgrade/status" > /dev/null 2>&1; then
        UP=1
        break
    fi
done

if [ "$UP" -eq 1 ]; then
    write_state "done" "" "$PREV_SHORT" "$NEW_SHORT"
    echo "✓ Upgraded $PREV_SHORT → $NEW_SHORT"
    echo "  Rollback (if you ever want it): git reset --hard $PREV_SHA && ./upgrade.sh"
    exit 0
fi

# 6. New server failed to start — auto-rollback ------------------------------
echo "✗ New server didn't answer within 15s. Rolling back to $PREV_SHORT…" >&2
kill "$NEW_PID" 2>/dev/null || true
sleep 1
kill -9 "$NEW_PID" 2>/dev/null || true

git reset --hard "$PREV_SHA" >>"$LOG" 2>&1
"$PIP" install -qr requirements.txt >>"$LOG" 2>&1

# Boot the old code back up.
nohup "$PY" -m uvicorn app:app --host 0.0.0.0 --port "$PORT" \
    >>/tmp/miniclosedai.log 2>&1 &
disown 2>/dev/null || true

fail "new server failed to start; rolled back to $PREV_SHORT"
