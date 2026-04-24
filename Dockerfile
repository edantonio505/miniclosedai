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

# Application code — explicit COPY instead of `COPY . .` so new files don't
# accidentally land in the image. .dockerignore is defense-in-depth.
COPY app.py db.py llm.py ./
COPY static/ ./static/

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
