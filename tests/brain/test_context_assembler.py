from __future__ import annotations

from friday.config import PLAN_ANCHOR_MARKER
from friday.context_assembler import (
    assemble_injection_blocks,
    rebuild_messages,
    should_rebuild,
)
from friday.sessions import create_session, save_session_fields
from friday.storage import UserSettings


def test_assemble_layers_order(tmp_appdata):
    session = create_session("组装", activate=False)
    save_session_fields(
        session.id,
        plan_markdown="1. 整理桌面\n2. 压缩旧文件",
        todos=[{"text": "整理桌面", "done": False}],
    )
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "帮我整理桌面"},
        {"role": "assistant", "content": "好的"},
    ]
    blocks = assemble_injection_blocks(session.id, messages)
    assert blocks
    combined = "\n".join(b["content"] for b in blocks)
    assert "整理桌面" in combined


def test_rebuild_triggers_at_high_ratio(tmp_appdata, monkeypatch):
    session = create_session("rebuild", activate=False)
    settings = UserSettings(context_smart_enabled=True, api_key="sk-test-key-1234567890")
    long_tail = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
    messages = [{"role": "system", "content": "sys"}, *long_tail]

    monkeypatch.setattr(
        "friday.brain.compute_context_meter",
        lambda *a, **k: {
            "budget_ratio": 0.9,
            "context_tokens": 90000,
            "context_budget": 100000,
        },
    )
    should, _ = should_rebuild(settings, messages)
    assert should is True

    rebuilt, did = rebuild_messages(session.id, messages, settings=settings, min_keep_recent=4)
    assert did is True
    assert len(rebuilt) < len(messages)
    assert rebuilt[0]["role"] == "system"


def test_assemble_skips_plan_when_anchor_present(tmp_appdata):
    session = create_session("计划去重", activate=False)
    save_session_fields(
        session.id,
        plan_markdown="1. 整理桌面\n2. 压缩旧文件",
        todos=[{"text": "整理桌面", "done": False}],
    )
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": f"{PLAN_ANCHOR_MARKER}\n已有计划块"},
        {"role": "assistant", "content": "好的"},
    ]
    blocks = assemble_injection_blocks(session.id, messages)
    combined = "\n".join(b["content"] for b in blocks)
    assert PLAN_ANCHOR_MARKER not in combined
    assert combined.count("整理桌面") == 0


def test_append_work_note_skips_approval():
    from friday.safety import evaluate_tool

    decision = evaluate_tool(UserSettings(), "append_work_note", {"text": "记录决策"})
    assert decision.allowed is True
    assert decision.needs_approval is False
