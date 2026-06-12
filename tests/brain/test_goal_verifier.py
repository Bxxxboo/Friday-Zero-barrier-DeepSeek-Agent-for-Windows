from __future__ import annotations

from friday.goal_verifier import should_verify, verify_goal_complete
from friday.sessions import create_session, save_session_fields
from friday.storage import UserSettings


def test_should_verify_open_todos(tmp_appdata):
    session = create_session("goal", activate=False)
    save_session_fields(
        session.id,
        todos=[{"text": "压缩备份", "done": False}],
    )
    settings = UserSettings(goal_verifier_enabled=True, context_smart_enabled=True)
    assert should_verify(session.id, "任务已完成，请查收。", settings=settings)


def test_verify_blocks_with_open_todos(tmp_appdata):
    session = create_session("goal2", activate=False)
    save_session_fields(
        session.id,
        todos=[{"text": "上传报告", "done": False}],
    )
    settings = UserSettings(goal_verifier_enabled=True, context_smart_enabled=True)
    result = verify_goal_complete(session.id, "已经全部完成了。", settings=settings)
    assert result.get("block") is True


def test_should_not_verify_partial_step_without_open_todos(tmp_appdata):
    session = create_session("部分完成", activate=False)
    save_session_fields(
        session.id,
        plan_markdown="1. 整理桌面\n2. 压缩旧文件\n3. 清理回收站",
        todos=[{"text": "整理桌面", "done": True}, {"text": "压缩旧文件", "done": True}],
    )
    settings = UserSettings(goal_verifier_enabled=True, context_smart_enabled=True)
    assert should_verify(session.id, "步骤 1 已完成，继续压缩。", settings=settings) is False


def test_parse_llm_json_strips_markdown_fence():
    from friday.goal_verifier import _parse_llm_json

    raw = '```json\n{"complete": false, "reason": "还差一步"}\n```'
    data = _parse_llm_json(raw)
    assert data["complete"] is False
    assert "还差" in data["reason"]
