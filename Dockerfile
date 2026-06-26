# MiniClosedAI FastAPI app image. Thin — three Python deps, no extras.
#
# Two traps baked out:
#   - CMD uses `uvicorn --host 0.0.0.0` NOT `python app.py`: the __main__
#     block at the bottom of app.py binds 127.0.0.1, which is invisible
#     outside the container.
#   - DB path is set via MINICLOSEDAI_DB_PATH → /app/data (a named volume
#     mount point), rather than living inside the app code tree at
#     Path(__file__).parent — which would require mounting over /app and
#     shadowing the code.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first — separate layer so app edits don't reinstall deps on
# every rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code — glob all root-level .py files (sdkgen.py, voice.py,
# and any future module are picked up automatically). .dockerignore excludes
# test_e2e.py and editor cruft so the glob doesn't drag in non-runtime files.
# voice.py is the LAN client adapter MiniClosedAI uses to talk to a separately-
# deployed voice service; it must be present even when no voice backend is
# configured — without it `import voice` at app.py:36 crashes the process.
COPY *.py ./
COPY static/ ./static/

# Build-time SHA so Docker installs (which don't ship .git inside the image)
# can still tell whether origin/main on GitHub has moved past them. Pass at
# build via `--build-arg GIT_SHA=$(git rev-parse HEAD)`; docker-compose.yml
# does this automatically. Falls back to "unknown" — the runtime status
# endpoint then can't compute `behind` but won't crash.
ARG GIT_SHA=unknown
ENV MINICLOSEDAI_BUILD_SHA=$GIT_SHA

# Non-root user + writable data dir for the SQLite DB volume mount.
RUN useradd --create-home --shell /bin/bash --uid 1000 app \
 && mkdir -p /app/data \
 && chown -R app:app /app
USER app

# Container defaults. These are overridden by docker-compose.yml for the
# two-service setup, but also let you `docker run` the image standalone for
# testing (pointing OLLAMA_URL at a host-accessible daemon).
ENV MINICLOSEDAI_DB_PATH=/app/data/miniclosedai.db \
    OLLAMA_URL=http://ollama:11434

EXPOSE 8095

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/', timeout=2)" || exit 1

# Bind to 0.0.0.0 so the published port on the host actually reaches the
# app. `python app.py` would silently bind to loopback-only via the
# __main__ block.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8095"]
