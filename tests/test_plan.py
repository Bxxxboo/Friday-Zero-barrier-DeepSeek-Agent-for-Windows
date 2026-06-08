from __future__ import annotations

from friday.plan import normalize_todos, plan_prompt_block
from friday.sessions import ChatSession


def test_normalize_todos():
    items = normalize_todos([{"text": "a", "done": True}, {"text": ""}, "bad"])
    assert len(items) == 1
    assert items[0]["text"] == "a"


def test_plan_prompt_block():
    session = ChatSession(
        id="s1",
        title="t",
        created_at=0,
        updated_at=0,
        plan_markdown="## 步骤\n1. 整理桌面",
        todos=[{"id": "1", "text": "扫描", "done": False}],
    )
    block = plan_prompt_block(session)
    assert "步骤" in block
    assert "扫描" in block
