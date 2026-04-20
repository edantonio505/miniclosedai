"""SQLite persistence for conversations. Stdlib only."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "miniclosedai.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL DEFAULT 'New Chat',
    model        TEXT    NOT NULL,
    system_prompt TEXT   NOT NULL DEFAULT 'You are a helpful AI assistant.',
    messages     TEXT    NOT NULL DEFAULT '[]',
    params       TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "messages" in d and isinstance(d["messages"], str):
        d["messages"] = json.loads(d["messages"] or "[]")
    if "params" in d and isinstance(d["params"], str):
        d["params"] = json.loads(d["params"] or "{}")
    return d
