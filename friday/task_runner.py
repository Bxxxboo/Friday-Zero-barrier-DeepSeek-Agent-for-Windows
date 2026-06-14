"""定时 / 手动触发 Agent 任务执行。"""

from __future__ import annotations

from friday.agent import FridayAgent
from friday.logging_config import get_logger
from friday.safety import PendingAction, RiskLevel, classify_tool
from friday.sessions import create_session, save_agent_state
from friday.storage import UserSettings, load_settings

_log = get_logger("task_runner")


def make_scheduled_approval_bridge(settings: UserSettings):
    """无人值守场景下的审批桥：只读自动通过，执行类拒绝，写入类看设置。"""

    def bridge(action: PendingAction) -> bool:
        risk = classify_tool(action.tool_name)
        if action.large_download or action.untrusted_download:
            _log.warning(
                "定时任务拒绝大文件/非官方下载 | tool=%s trust=%s",
                action.tool_name, action.trust_label,
            )
            return False
        if risk == RiskLevel.READ:
            return True
        if risk == RiskLevel.EXEC:
            _log.warning("定时任务拒绝执行类操作 | tool=%s", action.tool_name)
            return False
        if settings.auto_approve_scheduled_writes:
            return True
        _log.info("定时任务需审批但未开启自动批准 | tool=%s", action.tool_name)
        return False

    return bridge


def run_scheduled_prompt(
    prompt: str,
    *,
    session_title: str,
    schedule_id: str = "",
    trigger: str = "scheduled",
) -> tuple[str, str, str]:
    """执行一条 Agent 指令。返回 (status, message, session_id)，status 为 ok 或 error。"""
    settings = load_settings()
    if not settings.api_ready:
        return "error", "请先在设置中配置 API Key", ""

    text = prompt.strip()
    if not text:
        return "error", "任务指令为空", ""

    session = create_session(title=session_title)
    agent = FridayAgent(settings, make_scheduled_approval_bridge(settings))
    agent.operation_meta = {
        "session_id": session.id,
        "trigger": trigger,
        "schedule_id": schedule_id,
    }

    try:
        result = agent.run(text)
        save_agent_state(session.id, agent.messages, user_text=text)
        preview = result.strip() or "已完成"
        if len(preview) > 500:
            preview = preview[:500] + "…"
        return "ok", preview, session.id
    except Exception as exc:  # noqa: BLE001
        _log.exception("任务执行失败 | schedule_id=%s", schedule_id)
        return "error", str(exc), session.id
