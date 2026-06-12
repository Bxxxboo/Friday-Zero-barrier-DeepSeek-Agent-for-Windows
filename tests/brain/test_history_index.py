from __future__ import annotations

import sqlite3

from friday.history_index import ensure_schema, search_messages
from friday.sessions import create_session, save_agent_state


def test_index_and_search(tmp_appdata):
    ensure_schema()
    session = create_session("搜索测试", activate=False)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "请整理 D:\\项目\\Friday 下的配置文件"},
        {"role": "assistant", "content": "已开始整理 Friday 项目"},
    ]
    save_agent_state(session.id, messages, user_text="请整理项目")
    hits = search_messages("Friday", limit=10)
    assert any(h.get("session_id") == session.id for h in hits)


def test_search_like_fallback_uses_raw_query(monkeypatch):
    executed: list[tuple[str, tuple]] = []
    needle = 'foo"bar'

    class FakeCursor:
        def fetchall(self):
            return [
                {
                    "session_id": "s1",
                    "role": "user",
                    "content": f"标记 {needle} 结束",
                    "updated_at": 1.0,
                }
            ]

    class FakeConn:
        def execute(self, sql, parameters=()):
            executed.append((str(sql), parameters))
            if "MATCH" in str(sql):
                raise sqlite3.OperationalError("fts syntax error")
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("friday.history_index.ensure_schema", lambda: None)
    monkeypatch.setattr("friday.history_index._connect", FakeConn)
    hits = search_messages(needle, limit=10)
    like_params = [params for sql, params in executed if "LIKE" in sql]
    assert like_params
    assert needle in like_params[0][0]
    assert any(needle in str(h.get("content", "")) for h in hits)
