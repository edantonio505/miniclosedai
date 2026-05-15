#!/usr/bin/env bash
# MiniClosedAI — one-line installer (macOS, Linux, WSL)
#
# Quick install:
#   curl -fsSL https://raw.githubusercontent.com/edantonio505/miniclosedai/main/install.sh | bash
# Or with wget:
#   wget -qO- https://raw.githubusercontent.com/edantonio505/miniclosedai/main/install.sh | bash
#
# Env vars (all optional):
#   MINICLOSEDAI_DIR=$HOME/miniclosedai   where to clone
#   MINICLOSEDAI_PORT=8095                port to bind on auto-start
#   MINICLOSEDAI_START=1                  1 = start server detached, 0 = skip
#   MINICLOSEDAI_REPO=...                 override repo URL (forks)
#   MINICLOSEDAI_BRANCH=main              checkout a non-main branch
#
# What it does:
#   1. Verifies git + python3 ≥ 3.10 are present
#   2. Clones (or updates) the repo to $MINICLOSEDAI_DIR
#   3. Creates a venv, installs requirements.txt
#   4. Auto-starts uvicorn detached on $MINICLOSEDAI_PORT (skip with MINICLOSEDAI_START=0)
#   5. Prints the dashboard URL
#
# Re-runnable: if $MINICLOSEDAI_DIR already exists and is a git checkout,
# the script `git pull`s it and re-installs deps instead of failing.

set -euo pipefail

REPO_URL="${MINICLOSEDAI_REPO:-https://github.com/edantonio505/miniclosedai.git}"
BRANCH="${MINICLOSEDAI_BRANCH:-main}"
INSTALL_DIR="${MINICLOSEDAI_DIR:-$HOME/miniclosedai}"
PORT="${MINICLOSEDAI_PORT:-8095}"
START_SERVER="${MINICLOSEDAI_START:-1}"

if [ -t 1 ]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; RED=$'\e[31m'; DIM=$'\e[2m'; RST=$'\e[0m'
else
    BOLD=''; GREEN=''; RED=''; DIM=''; RST=''
fi

say()  { printf '%s\n' "$1"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$RST" "$1"; }
warn() { printf '%s!%s %s\n' "$RED"   "$RST" "$1" >&2; }
fail() { warn "$1"; exit 1; }

need() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required tool: $1. Install it, then re-run."
}

printf '%sMiniClosedAI installer%s\n' "$BOLD" "$RST"
printf '%s  repo:   %s%s\n' "$DIM" "$REPO_URL"     "$RST"
printf '%s  branch: %s%s\n' "$DIM" "$BRANCH"       "$RST"
printf '%s  dir:    %s%s\n' "$DIM" "$INSTALL_DIR"  "$RST"
echo

# ---------- Prereqs ----------
need git
need python3

PYV=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_MAJOR=${PYV%%.*}
PY_MINOR=${PYV#*.}
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required, found $PYV. Upgrade Python and re-run."
fi
ok "python3 ($PYV)"
ok "git ($(git --version | awk '{print $3}'))"

# ---------- Clone or update ----------
if [ -d "$INSTALL_DIR/.git" ]; then
    ok "existing checkout at $INSTALL_DIR — fetching $BRANCH"
    git -C "$INSTALL_DIR" fetch --quiet --prune origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
    git -C "$INSTALL_DIR" pull --quiet --ff-only origin "$BRANCH" \
        || fail "Could not fast-forward $BRANCH (local has diverging commits). Sort it out manually, then re-run."
elif [ -e "$INSTALL_DIR" ]; then
    fail "$INSTALL_DIR exists but isn't a git checkout. Remove it, or set MINICLOSEDAI_DIR=path/to/somewhere/else."
else
    say "Cloning…"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    ok "cloned"
fi

cd "$INSTALL_DIR"

# ---------- Venv + deps ----------
if [ ! -d ".venv" ]; then
    say "Creating Python venv (.venv)…"
    python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
ok "dependencies installed"

# ---------- Stop any existing server before we maybe start a new one ----------
if [ "$START_SERVER" = "1" ]; then
    if pgrep -f "uvicorn app:app.*--port $PORT" >/dev/null 2>&1; then
        say "Stopping previous uvicorn on port $PORT…"
        pkill -f "uvicorn app:app.*--port $PORT" 2>/dev/null || true
        sleep 1
    fi
fi

# ---------- Done ----------
echo
printf '%s%s✓ MiniClosedAI installed at %s%s\n' "$BOLD" "$GREEN" "$INSTALL_DIR" "$RST"
echo

if [ "$START_SERVER" != "1" ]; then
    echo "Start the server when you're ready:"
    echo
    echo "  cd $INSTALL_DIR"
    echo "  .venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port $PORT"
    echo
    echo "Then open: http://localhost:$PORT"
    exit 0
fi

# Auto-start detached so this script returns.
say "Starting server on port $PORT (detached)…"
LOG=/tmp/miniclosedai.log
nohup .venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port "$PORT" \
    >>"$LOG" 2>&1 &
disown 2>/dev/null || true

# Wait up to 15s for the server to answer.
for _ in $(seq 1 30); do
    sleep 0.5
    if curl -sf -m 2 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
        ok "server running"
        echo
        printf '%sOpen: %shttp://localhost:%s%s\n' "$BOLD" "$GREEN" "$PORT" "$RST"
        echo
        echo "Logs:        $LOG"
        echo "Stop:        pkill -f 'uvicorn app:app.*--port $PORT'"
        echo "Re-run:      curl -fsSL https://raw.githubusercontent.com/edantonio505/miniclosedai/main/install.sh | bash"
        exit 0
    fi
done

warn "Server didn't answer within 15s. Last log lines:"
tail -20 "$LOG" >&2
exit 1
