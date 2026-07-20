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
#   MINICLOSEDAI_FULL=auto                auto = install the GPU siblings when CUDA
#                                         works; 1 = force; 0 = app only
#   MINICLOSEDAI_LLM_REPO=...             override miniclosedai-llm repo URL
#   MINICLOSEDAI_VOICE_REPO=...           override miniclosedai-voice repo URL
#   MINICLOSEDAI_VOICE_SETUP=1            0 = clone voice but skip its setup.sh
#                                         (the multi-GB torch install)
#
# What it does:
#   1. Verifies git + python3 ≥ 3.10 are present
#   2. Clones (or updates) the repo to $MINICLOSEDAI_DIR
#   3. Creates a venv, installs requirements.txt
#   4. On a CUDA machine (nvidia-smi answers), ALSO clones the two sibling
#      repos next to it — miniclosedai-llm (model server) and
#      miniclosedai-voice (ASR + TTS) — and runs the voice one-time setup.
#      The full stack then starts via ./dev.sh up (voice + models + app) and
#      the Models / Voice Studio tabs are live. CPU-only boxes skip this and
#      run the app alone — same UI, register remote endpoints in Settings.
#   5. Auto-starts detached (skip with MINICLOSEDAI_START=0) and prints the URL
#
# Re-runnable: existing checkouts (main repo AND siblings) are `git pull`ed
# and deps re-installed instead of failing.

set -euo pipefail

REPO_URL="${MINICLOSEDAI_REPO:-https://github.com/edantonio505/miniclosedai.git}"
BRANCH="${MINICLOSEDAI_BRANCH:-main}"
INSTALL_DIR="${MINICLOSEDAI_DIR:-$HOME/miniclosedai}"
PORT="${MINICLOSEDAI_PORT:-8095}"
START_SERVER="${MINICLOSEDAI_START:-1}"
FULL_MODE="${MINICLOSEDAI_FULL:-auto}"
LLM_REPO_URL="${MINICLOSEDAI_LLM_REPO:-https://github.com/edantonio505/miniclosedai-llm.git}"
VOICE_REPO_URL="${MINICLOSEDAI_VOICE_REPO:-https://github.com/edantonio505/miniclosedai-voice.git}"
VOICE_SETUP="${MINICLOSEDAI_VOICE_SETUP:-1}"

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

# ---------- GPU siblings (miniclosedai-llm + miniclosedai-voice) ----------
# The Models and Voice Studio tabs are the GUIs for two sibling services.
# They're GPU workloads, so they're only installed where CUDA actually works
# (same gate dev.sh uses at start time). MiniClosedAI itself stays fully
# functional without them — the tabs show a friendly "not running" state.
cuda_works() {
    command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1
}

clone_or_update() {
    # $1 = repo url, $2 = target dir, $3 = label
    if [ -d "$2/.git" ]; then
        ok "$3: existing checkout — pulling"
        git -C "$2" pull --quiet --ff-only \
            || warn "$3: could not fast-forward (local changes?) — using it as-is"
    elif [ -e "$2" ]; then
        warn "$3: $2 exists but isn't a git checkout — skipping"
        return 1
    else
        say "Cloning $3…"
        git clone --quiet "$1" "$2"
        ok "$3 cloned"
    fi
}

INSTALL_FULL=0
case "$FULL_MODE" in
    1) INSTALL_FULL=1 ;;
    0) INSTALL_FULL=0 ;;
    *) cuda_works && INSTALL_FULL=1 || true ;;
esac

SIB_ROOT="$(dirname "$INSTALL_DIR")"
LLM_DIR="$SIB_ROOT/miniclosedai-llm"
VOICE_DIR="$SIB_ROOT/miniclosedai-voice"

if [ "$INSTALL_FULL" = "1" ]; then
    echo
    printf '%sFull stack (CUDA detected): installing the model server + voice service%s\n' "$BOLD" "$RST"

    if clone_or_update "$LLM_REPO_URL" "$LLM_DIR" "miniclosedai-llm"; then
        # No pre-setup needed: its dev.sh creates a venv + installs
        # manager-requirements.txt on first start.
        ok "miniclosedai-llm ready (bootstraps itself on first start)"
    fi

    if clone_or_update "$VOICE_REPO_URL" "$VOICE_DIR" "miniclosedai-voice"; then
        if [ "$VOICE_SETUP" = "1" ]; then
            if [ -x "$VOICE_DIR/setup.sh" ]; then
                say "Running voice one-time setup (torch + TTS models — several GB, can take minutes)…"
                if ( cd "$VOICE_DIR" && ./setup.sh ); then
                    ok "voice service set up"
                else
                    warn "voice setup failed — fix and re-run: cd $VOICE_DIR && ./setup.sh"
                fi
            else
                warn "voice repo has no setup.sh — set it up manually"
            fi
        else
            say "Skipping voice setup (MINICLOSEDAI_VOICE_SETUP=0) — run $VOICE_DIR/setup.sh later"
        fi
    fi
else
    say "No working CUDA (or MINICLOSEDAI_FULL=0) — installing MiniClosedAI only."
    say "The Models / Voice Studio tabs will show 'not running'; register remote"
    say "endpoints in Settings, or re-run with MINICLOSEDAI_FULL=1 to force."
fi

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
LOG=/tmp/miniclosedai.log

if [ "$INSTALL_FULL" = "1" ] && [ -x "$INSTALL_DIR/dev.sh" ] && command -v openssl >/dev/null 2>&1; then
    # Full stack: dev.sh up brings voice + model server + app online together
    # (HTTPS with a self-signed dev cert; dev.sh generates it).
    say "Starting the full stack via ./dev.sh up (voice + models + app)…"
    ( cd "$INSTALL_DIR" && ./dev.sh up ) || warn "dev.sh up reported a problem — check output above"
    if curl -skf -m 3 "https://127.0.0.1:$PORT/" >/dev/null 2>&1; then
        ok "server running (https)"
        echo
        printf '%sOpen: %shttps://localhost:%s%s  (self-signed cert — accept the warning)\n' "$BOLD" "$GREEN" "$PORT" "$RST"
        echo
        echo "Status:      cd $INSTALL_DIR && ./dev.sh status"
        echo "Stop:        cd $INSTALL_DIR && ./dev.sh down"
        echo "Logs:        $LOG  (also: ./dev.sh logs llm | voice)"
        exit 0
    fi
    warn "App didn't answer on https://127.0.0.1:$PORT after dev.sh up. Last log lines:"
    tail -20 "$LOG" >&2
    exit 1
fi

# App-only start (CPU box, or openssl missing): plain HTTP uvicorn, as before.
say "Starting server on port $PORT (detached)…"
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
