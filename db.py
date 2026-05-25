"""SQLite persistence for MiniClosedAI. Stdlib only.

Two tables:
  - `backends`      — registered LLM endpoints (Ollama + any OpenAI-compat).
  - `conversations` — saved bots. Each has a logical FK `backend_id → backends.id`
                      (not a real SQL FK; see note below).

Migration policy: additive. `init_db()` is safe to run against an existing
database — new columns are added via `ALTER TABLE ... ADD COLUMN` when absent,
and the built-in Ollama backend is seeded with `INSERT OR IGNORE`.

Note on FKs: SQLite cannot add a `REFERENCES backends(id)` constraint to an
existing column post-hoc. `conversations.backend_id` is a logical FK only —
application code enforces existence (see `_load_backend()` in app.py).
"""
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("MINICLOSEDAI_DB_PATH") or (Path(__file__).parent / "miniclosedai.db"))

_DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _no_ollama_mode() -> bool:
    """Lite install — skip seeding the built-in Ollama backend.

    Set ``MINICLOSEDAI_NO_OLLAMA=1`` (also accepts ``true`` / ``yes``) when
    running the web app on a machine that does not have Ollama installed.
    The user registers their own external endpoint via the Settings page
    instead. Existing built-in row (if any) is auto-disabled at startup so
    upgrading from a heavy install to lite doesn't leave a permanently-
    unreachable endpoint cluttering the dropdown.
    """
    return (os.environ.get("MINICLOSEDAI_NO_OLLAMA") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL DEFAULT 'New Chat',
    model        TEXT    NOT NULL,
    system_prompt TEXT   NOT NULL DEFAULT 'You are a helpful AI assistant.',
    messages     TEXT    NOT NULL DEFAULT '[]',
    params       TEXT    NOT NULL DEFAULT '{}',
    backend_id   INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backends (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('ollama', 'openai')),
    base_url    TEXT    NOT NULL,
    api_key     TEXT,
    headers     TEXT    NOT NULL DEFAULT '{}',
    enabled     INTEGER NOT NULL DEFAULT 1,
    is_builtin  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Per-bot knowledge base ("books"). A document is one uploaded file; it's
-- split into chunks, each with an embedding stored as a packed float32 BLOB.
-- Retrieval is brute-force cosine over a single conversation's chunks (no
-- external vector DB — SQLite IS the store). Cleanup of a conversation's KB
-- rows happens in app.py's delete handler (logical FK, like backend_id).
CREATE TABLE IF NOT EXISTS kb_documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    filename        TEXT    NOT NULL,
    char_count      INTEGER NOT NULL DEFAULT 0,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    embed_model     TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    ordinal         INTEGER NOT NULL,
    text            TEXT    NOT NULL,
    embedding       BLOB    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_conv ON kb_chunks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_kb_docs_conv  ON kb_documents(conversation_id);

-- Per-bot evaluation set. Each row is one test case: an input and the expected
-- response. Scoring (accuracy over the set) is computed on demand, not stored.
-- Cleanup of a conversation's cases happens in app.py's delete handler.
CREATE TABLE IF NOT EXISTS eval_cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    input           TEXT    NOT NULL,
    expected        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_cases_conv ON eval_cases(conversation_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db() -> None:
    """Idempotent schema setup + additive migrations + built-in backend seed."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)

        # Additive migration: existing DBs that predate the multi-backend feature
        # won't have `backend_id` on `conversations`. Add it on the fly.
        if not _column_exists(conn, "conversations", "backend_id"):
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN backend_id INTEGER NOT NULL DEFAULT 1"
            )

        # Additive migration: per-bot MCP servers (plugin extensions). JSON list
        # of {name, url, enabled}. Empty list = no plugins (the common case).
        if not _column_exists(conn, "conversations", "mcp_servers"):
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN mcp_servers TEXT NOT NULL DEFAULT '[]'"
            )

        # Seed the built-in Ollama backend at id=1, but ONLY when the backends
        # table is completely empty. The looser `INSERT OR IGNORE` we used to
        # do here would resurrect the built-in on every restart after the
        # user deleted it (since the row at id=1 was now free) — defeating
        # the GUI's "Delete the built-in" affordance. Counting rows instead
        # of probing id=1 means: a fresh DB gets the seed once, but any DB
        # with at least one user-managed backend keeps the user's choices
        # across restarts. (User-deletes-everything still re-seeds — they
        # need at least one backend to use the app.)
        #
        # Lite mode (MINICLOSEDAI_NO_OLLAMA): skip the seed even on a fresh
        # DB so the user registers their own external endpoint via Settings,
        # and auto-disable any pre-existing built-in row on a DB that was
        # created in heavy mode (upgrading doesn't leave a permanently-
        # unreachable backend in the dropdown).
        backend_count = conn.execute("SELECT COUNT(*) FROM backends").fetchone()[0]
        if _no_ollama_mode():
            conn.execute(
                "UPDATE backends SET enabled = 0 WHERE is_builtin = 1 AND kind = 'ollama'"
            )
        elif backend_count == 0:
            conn.execute(
                """INSERT INTO backends (id, name, kind, base_url, is_builtin, enabled)
                   VALUES (1, 'Ollama (built-in)', 'ollama', ?, 1, 1)""",
                (_DEFAULT_OLLAMA_URL,),
            )

        conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    """Generic row → dict with JSON-column decoding.

    Knows about `messages`, `params`, and `headers` — any other text column
    flows through unchanged.
    """
    d = dict(row)
    if "messages" in d and isinstance(d["messages"], str):
        d["messages"] = json.loads(d["messages"] or "[]")
    if "params" in d and isinstance(d["params"], str):
        d["params"] = json.loads(d["params"] or "{}")
    if "headers" in d and isinstance(d["headers"], str):
        d["headers"] = json.loads(d["headers"] or "{}")
    if "mcp_servers" in d and isinstance(d["mcp_servers"], str):
        d["mcp_servers"] = json.loads(d["mcp_servers"] or "[]")
    return d
