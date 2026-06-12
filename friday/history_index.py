"""会话历史 FTS5 索引 —— 支持跨会话全文搜索。"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("history_index")

_DB_NAME = "history.db"
_INDEX_DEBOUNCE_SEC = 1.0
_LAST_INDEX_AT: dict[str, float] = {}


def db_path() -> Path:
    return get_appdata_dir() / _DB_NAME


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
            USING fts5(session_id, role, content, updated_at UNINDEXED)
            """
        )
        conn.commit()


def _display_text(msg: dict[str, Any]) -> str:
    role = str(msg.get("role", ""))
    content = str(msg.get("content", "")).strip()
    if not content:
        images = msg.get("generated_images")
        if isinstance(images, list) and images:
            paths = [str(i.get("path", "")) for i in images if isinstance(i, dict)]
            content = " ".join(p for p in paths if p)
    return content[:4000]


def index_session_messages(
    session_id: str,
    agent_messages: list[dict[str, Any]] | None = None,
    display_messages: list[dict[str, Any]] | None = None,
) -> None:
    if not session_id:
        return
    now = time.time()
    last = _LAST_INDEX_AT.get(session_id, 0.0)
    if now - last < _INDEX_DEBOUNCE_SEC:
        return
    ensure_schema()
    rows: list[tuple[str, str, str, float]] = []
    now = time.time()
    source = display_messages if display_messages else agent_messages or []
    for msg in source:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", ""))
        if role in {"system", "tool"}:
            continue
        text = _display_text(msg)
        if text:
            rows.append((session_id, role, text, now))
    if not rows:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
        for sid, role, content, ts in rows:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, updated_at) VALUES (?, ?, ?, ?)",
                (sid, role, content, ts),
            )
            conn.execute(
                "INSERT INTO messages_fts (session_id, role, content, updated_at) VALUES (?, ?, ?, ?)",
                (sid, role, content, ts),
            )
        conn.commit()
    _LAST_INDEX_AT[session_id] = now


def _escape_fts_query(query: str) -> str:
    import re

    cleaned = re.sub(r"[^\w\s\u4e00-\u9fff./\\:-]", " ", str(query or ""))
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    return " ".join(f'"{t.replace(chr(34), "")}"' for t in tokens[:12])


def search_messages(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    raw = str(query or "").strip()
    needle = _escape_fts_query(raw)
    if not raw:
        return []
    ensure_schema()
    with _connect() as conn:
        try:
            if not needle:
                raise sqlite3.OperationalError("empty fts needle")
            cur = conn.execute(
                """
                SELECT session_id, role, content, updated_at
                FROM messages_fts
                WHERE messages_fts MATCH ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (needle, limit),
            )
        except sqlite3.OperationalError:
            like_needle = f"%{raw[:120]}%"
            cur = conn.execute(
                """
                SELECT session_id, role, content, updated_at
                FROM messages
                WHERE content LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like_needle, limit),
            )
        return [dict(row) for row in cur.fetchall()]


def rebuild_index_from_sessions() -> int:
    from friday.sessions import list_sessions, session_display_messages

    ensure_schema()
    summaries, _ = list_sessions(limit=500)
    count = 0
    for item in summaries:
        from friday.sessions import get_session

        session = get_session(item.id)
        if not session:
            continue
        index_session_messages(
            session.id,
            session.agent_messages,
            session_display_messages(session),
        )
        count += 1
    return count
