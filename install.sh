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
#   MINICLOSEDAI_LLM_SHIM_SETUP=1         0 = clone miniclosedai-llm but skip
#                                         its setup_shim.sh (see point 4 below)
#   LAUNCH_ENGINE=auto                    docker|native|shim — forwarded as-is
#                                         to miniclosedai-llm; auto lets it
#                                         pick. Set docker/native to skip the
#                                         shim auto-install below.
#   MINICLOSEDAI_JETSON_TORCH=2.8.0      torch/torchaudio version to pull from
#                                         jetson-ai-lab on a Jetson (auto-picks
#                                         the newest cp310 wheel if unavailable)
#   OLLAMA_URL=...                        where Ollama listens; auto-detected
#                                         (probes :11434/:11433) when unset, and
#                                         written to ~/.bash_aliases for reuse
#   MINICLOSEDAI_VOICE_URL=...            local voice service URL to auto-register
#                                         in the app (default http://localhost:8090)
#
# What it does:
#   1. Verifies git + python3 ≥ 3.10 are present
#   2. Clones (or updates) the repo to $MINICLOSEDAI_DIR
#   3. Creates a venv, installs requirements.txt
#   4. On a CUDA machine (nvidia-smi answers), ALSO clones the two sibling
#      repos next to it — miniclosedai-llm (model server) and
#      miniclosedai-voice (ASR + TTS) — and runs each one's one-time setup.
#      NVIDIA Jetson (Tegra/Orin) is auto-detected: the voice env is built with
#      NVIDIA's jetson-ai-lab torch (sm_87) instead of pytorch.org's generic
#      aarch64 wheels (which load but crash on the Orin GPU), and the Tegra NVML
#      allocator workaround is baked into the voice venv. So a fresh Jetson
#      install gets working GPU voice out of the box.
#      For miniclosedai-llm: when Docker isn't usable (most RunPod pods can't
#      run Docker-in-Docker), its bare-metal transformers-shim engine is set up
#      HERE, synchronously, before the stack starts — not deferred to a
#      background job after the server is already up. That background-install
#      path still exists in miniclosedai-llm's own dev.sh as a safety net (e.g.
#      re-running dev.sh directly, without going through this installer), but
#      doing it here means there's no window where "Download & Run" is clicked
#      before the engine is ready: by the time this script prints "installed",
#      Download & Run already works.
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
LLM_SHIM_SETUP="${MINICLOSEDAI_LLM_SHIM_SETUP:-1}"
# Local voice service URL to auto-register in the app (gap-3 fix). Preset it in
# ~/.bash_aliases to point elsewhere; the installer reads it from the env.
VOICE_URL="${MINICLOSEDAI_VOICE_URL:-http://localhost:8090}"
# Where the app keeps its SQLite DB (mirrors app.py's default).
DB_PATH="${MINICLOSEDAI_DB_PATH:-$INSTALL_DIR/miniclosedai.db}"
VOICE_OK=0   # set to 1 once the voice env is built, gates auto-registration

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

# ---------- Gap-2: find where Ollama actually listens ----------
# A fresh DB seeds the built-in backend at OLLAMA_URL (default :11434), but a
# host may run Ollama on a custom port (e.g. :11433 via a systemd override).
# Honor an explicit OLLAMA_URL / OLLAMA_HOST, else probe the two common ports.
detect_ollama_url() {
    if [ -n "${OLLAMA_URL:-}" ]; then echo "$OLLAMA_URL"; return; fi
    if [ -n "${OLLAMA_HOST:-}" ]; then
        case "$OLLAMA_HOST" in http*) echo "$OLLAMA_HOST";; *) echo "http://$OLLAMA_HOST";; esac
        return
    fi
    local p
    for p in 11434 11433; do
        if curl -sf -m 2 "http://127.0.0.1:$p/api/tags" >/dev/null 2>&1; then
            echo "http://127.0.0.1:$p"; return
        fi
    done
    echo "http://localhost:11434"
}

# ---------- Gaps 2 + 3: reconcile backends in the app DB ----------
# Run AFTER the app has started (so the DB + schema exist). Points the built-in
# Ollama backend at the detected URL, and registers the local voice service so
# the mic buttons light up without a manual Settings step. Idempotent.
finalize_backends() {
    [ -f "$DB_PATH" ] || return 0
    "$INSTALL_DIR/.venv/bin/python" - "$DB_PATH" "$OLLAMA_URL_DETECTED" "$VOICE_URL" "$VOICE_OK" <<'PY' 2>/dev/null || true
import sqlite3, sys
db, ollama_url, voice_url, voice_ok = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
c = sqlite3.connect(db, timeout=15)
try:
    # gap 2: built-in ollama → detected URL
    c.execute("UPDATE backends SET base_url=? WHERE kind='ollama' AND (is_builtin=1 OR id=1)",
              (ollama_url,))
    # gap 3: register the local voice backend once (only if voice was built)
    if voice_ok == "1" and not c.execute(
            "SELECT 1 FROM backends WHERE kind='voice' AND base_url=?", (voice_url,)).fetchone():
        c.execute("INSERT INTO backends (name, kind, base_url, enabled) VALUES (?, 'voice', ?, 1)",
                  ("Voice (local, GPU)", voice_url))
    c.commit()
finally:
    c.close()
PY
    if [ "$VOICE_OK" = "1" ]; then
        ok "backends reconciled (Ollama → $OLLAMA_URL_DETECTED, voice → $VOICE_URL)"
    else
        ok "backends reconciled (Ollama → $OLLAMA_URL_DETECTED)"
    fi
}

# ---------- Persist env for future shells / installs (~/.bash_aliases) ----------
# The user asked that a fresh install pick these up automatically. We write a
# marked, idempotent block so re-running just refreshes it (never duplicates).
write_bash_aliases() {
    local f="$HOME/.bash_aliases"
    local begin="# >>> miniclosedai (auto) >>>"
    local end="# <<< miniclosedai (auto) <<<"
    touch "$f"
    # strip any previous managed block, then append the current one
    if grep -qF "$begin" "$f" 2>/dev/null; then
        sed -i "/${begin//\//\\/}/,/${end//\//\\/}/d" "$f"
    fi
    {
        echo "$begin"
        echo "# Auto-written by miniclosedai install.sh — points the app at the local"
        echo "# Ollama/voice services so a fresh install is recognized automatically."
        echo "export OLLAMA_URL=\"$OLLAMA_URL_DETECTED\""
        echo "export MINICLOSEDAI_VOICE_URL=\"$VOICE_URL\""
        echo "$end"
    } >> "$f"
    ok "wrote env to $f (OLLAMA_URL, MINICLOSEDAI_VOICE_URL)"
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

# ---------- Gap-2: detect Ollama + export so the fresh DB seeds correctly ----
# db.py seeds the built-in backend from $OLLAMA_URL at first app start, so
# exporting it here means a brand-new DB gets the right port with no edit.
OLLAMA_URL_DETECTED="$(detect_ollama_url)"
export OLLAMA_URL="$OLLAMA_URL_DETECTED"
ok "Ollama endpoint: $OLLAMA_URL_DETECTED"
write_bash_aliases

# ---------- GPU siblings (miniclosedai-llm + miniclosedai-voice) ----------
# The Models and Voice Studio tabs are the GUIs for two sibling services.
# They're GPU workloads, so they're only installed where CUDA actually works
# (same gate dev.sh uses at start time). MiniClosedAI itself stays fully
# functional without them — the tabs show a friendly "not running" state.
cuda_works() {
    command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1
}

# Is Docker actually usable for launching models (not just installed)? Mirrors
# miniclosedai-llm/dev.sh's own DOCKER_OK check exactly.
docker_works() {
    command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
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

# ---------- Jetson (Tegra) detection + GPU-voice recipe ----------
# NVIDIA Jetson (Orin/Xavier) is aarch64 with an *integrated* CUDA GPU whose
# compute capability (sm_87 on Orin) is NOT covered by pytorch.org's generic
# aarch64 wheels — those load but crash at the first GPU op ("no kernel image
# is available"). The voice repo's setup.sh installs exactly those wheels, so
# on Jetson we bypass it and build torch from NVIDIA's jetson-ai-lab index,
# which ships sm_87 wheels (built for cp310 = the Jetson system Python).
is_jetson() { [ "$(uname -m)" = "aarch64" ] && [ -f /etc/nv_tegra_release ]; }

jetson_index_url() {
    # JetPack major from the L4T release tag (R36→jp6, R35→jp5); CUDA from the
    # driver. Yields e.g. https://pypi.jetson-ai-lab.io/jp6/cu126/+simple/
    # (|| true guards keep a missing tool from aborting the installer.)
    local l4t jp cuda
    l4t=$(sed -nE 's/^# R([0-9]+).*/\1/p' /etc/nv_tegra_release 2>/dev/null) || true
    case "$l4t" in 35) jp=jp5 ;; *) jp=jp6 ;; esac
    cuda=$(nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9.]+' | awk '{print $NF}') || true
    if [ -z "$cuda" ]; then
        cuda=$(nvcc --version 2>/dev/null | sed -nE 's/.*release ([0-9]+\.[0-9]+).*/\1/p') || true
    fi
    [ -n "$cuda" ] || cuda=12.6
    echo "https://pypi.jetson-ai-lab.io/${jp}/cu${cuda//./}/+simple/"
}

jetson_pick_torch() {
    # Prefer the validated default; else the newest cp310 torch the index has.
    local idx="$1" want="${MINICLOSEDAI_JETSON_TORCH:-2.8.0}" list
    list=$(curl -s -m 20 "${idx}torch/" 2>/dev/null \
           | grep -oE 'torch-[0-9.]+-cp310' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | sort -uV) || list=""
    if echo "$list" | grep -qx "$want" 2>/dev/null; then echo "$want"
    elif [ -n "$list" ]; then echo "$list" | tail -1
    else echo "$want"; fi
}

jetson_voice_setup() {
    local vdir="$1" idx tv
    idx="$(jetson_index_url)"; tv="$(jetson_pick_torch "$idx")"
    say "Jetson/Tegra detected — building voice on system Python 3 + jetson-ai-lab torch $tv (sm_87)."
    say "  wheel index: $idx"
    ( set -e
      cd "$vdir"
      rm -rf env
      python3 -m venv env
      env/bin/pip install -q --upgrade pip wheel setuptools
      # torch/torchaudio built for the Jetson GPU (sm_87). Its own deps resolve
      # via the index's PyPI mirror. Keep this as its own step so nothing later
      # can pull a pytorch.org wheel over it.
      env/bin/pip install -q "torch==$tv" "torchaudio==$tv" --index-url "$idx"
      env/bin/pip install -q "numpy>=1.24,<2"
      env/bin/pip install -q --no-deps chatterbox-tts==0.1.6
      env/bin/pip install -q -r requirements.txt
      # Same patches the repo's setup.sh applies.
      DF_IO=$(find env -path "*/df/io.py" -not -path "*/__pycache__/*" 2>/dev/null | head -1) || true
      if [ -n "$DF_IO" ] && grep -q "from torchaudio.backend.common import AudioMetaData" "$DF_IO" 2>/dev/null; then
          sed -i 's|from torchaudio.backend.common import AudioMetaData|class AudioMetaData: pass  # stub for torchaudio>=2.1|' "$DF_IO"
      fi
      TURBO=$(find env -path "*/chatterbox/tts_turbo.py" -not -path "*/__pycache__/*" 2>/dev/null | head -1) || true
      if [ -n "$TURBO" ] && grep -q 'token=os.getenv("HF_TOKEN") or True' "$TURBO" 2>/dev/null; then
          sed -i 's|token=os.getenv("HF_TOKEN") or True|token=os.getenv("HF_TOKEN") or None|' "$TURBO"
      fi
      # Tegra has only partial NVML support, so torch's CUDA caching allocator
      # asserts when moving a model to GPU. Bake the documented workaround into
      # the venv so every `start.sh` (which sources this) picks it up.
      grep -q PYTORCH_NO_CUDA_MEMORY_CACHING env/bin/activate 2>/dev/null \
          || echo 'export PYTORCH_NO_CUDA_MEMORY_CACHING=1' >> env/bin/activate
    )
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
        # dev.sh creates its own venv + installs manager-requirements.txt on
        # first start — no pre-setup needed for that. But launching an actual
        # model needs a working engine: Docker, native vLLM, or the bare-metal
        # transformers shim. Most RunPod pods can't run Docker-in-Docker, so
        # without this, the manager comes up with "no launch engine" and stays
        # that way until someone notices and runs setup_shim.sh by hand.
        if docker_works; then
            ok "miniclosedai-llm ready (Docker available — models launch via Docker)"
        elif [ "${LAUNCH_ENGINE:-auto}" = "docker" ] || [ "${LAUNCH_ENGINE:-auto}" = "native" ]; then
            ok "miniclosedai-llm ready (LAUNCH_ENGINE=${LAUNCH_ENGINE} set — bare-metal shim setup skipped)"
        elif [ "$LLM_SHIM_SETUP" = "1" ] && [ -x "$LLM_DIR/setup_shim.sh" ]; then
            say "No Docker on this host — installing the bare-metal transformers shim now"
            say "(torch — several GB, can take minutes) so model launches work immediately…"
            if ( cd "$LLM_DIR" && ./setup_shim.sh ); then
                ok "miniclosedai-llm ready (bare-metal shim set up — models launch without Docker)"
            else
                warn "shim setup failed — fix and re-run: cd $LLM_DIR && ./setup_shim.sh"
            fi
        elif [ "$LLM_SHIM_SETUP" != "1" ]; then
            say "Skipping shim setup (MINICLOSEDAI_LLM_SHIM_SETUP=0) — run $LLM_DIR/setup_shim.sh later"
        else
            warn "miniclosedai-llm has no setup_shim.sh (old checkout?) — models may fail to launch without Docker"
        fi
    fi

    if clone_or_update "$VOICE_REPO_URL" "$VOICE_DIR" "miniclosedai-voice"; then
        if [ "$VOICE_SETUP" = "1" ]; then
            if is_jetson; then
                # Jetson path: build with jetson-ai-lab GPU wheels (see above).
                if jetson_voice_setup "$VOICE_DIR"; then
                    VOICE_OK=1
                    ok "voice service set up (Jetson GPU, sm_87)"
                else
                    warn "voice Jetson setup failed — re-run this installer, or build manually with jetson-ai-lab torch"
                fi
            elif [ -x "$VOICE_DIR/setup.sh" ]; then
                say "Running voice one-time setup (torch + TTS models — several GB, can take minutes)…"
                if ( cd "$VOICE_DIR" && ./setup.sh ); then
                    VOICE_OK=1
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
        finalize_backends   # gaps 2+3: point at the real Ollama, register voice
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
        finalize_backends   # gap 2: point the built-in backend at the real Ollama
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
