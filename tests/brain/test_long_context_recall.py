from __future__ import annotations

from friday.context_assembler import rebuild_messages
from friday.plan import upsert_plan_anchor_for_session
from friday.sessions import create_session, save_session_fields
from friday.storage import UserSettings


def test_plan_survives_rebuild_with_long_tail(tmp_appdata, monkeypatch):
    session = create_session("长聊回忆", activate=False)
    save_session_fields(
        session.id,
        plan_markdown="## 任务\n- [ ] 整理 E:\\Downloads\\旧项目\n- [ ] 写汇总报告",
        todos=[
            {"text": "整理 E:\\Downloads\\旧项目", "done": False},
            {"text": "写汇总报告", "done": False},
        ],
    )
    messages = [{"role": "system", "content": "sys"}]
    for i in range(40):
        messages.append({"role": "user", "content": f"步骤讨论 {i}"})
        messages.append({"role": "assistant", "content": f"收到 {i}"})
    messages = upsert_plan_anchor_for_session(session.id, messages)

    settings = UserSettings(context_smart_enabled=True, api_key="sk-test-key-1234567890")
    monkeypatch.setattr(
        "friday.brain.compute_context_meter",
        lambda *a, **k: {
            "budget_ratio": 0.92,
            "context_tokens": 92000,
            "context_budget": 100000,
        },
    )
    rebuilt, did = rebuild_messages(session.id, messages, settings=settings, min_keep_recent=6)
    assert did is True
    combined = "\n".join(
        str(m.get("content", "")) for m in rebuilt if isinstance(m.get("content"), str)
    )
    assert "Downloads" in combined or "整理" in combined or "汇总报告" in combined
