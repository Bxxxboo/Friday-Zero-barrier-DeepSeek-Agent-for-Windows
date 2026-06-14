"""分层上下文组装 —— rebuild 时按预算注入 plan / checkpoint / 记忆 / tail。"""

from __future__ import annotations

from typing import Any

from friday.config import CHECKPOINT_MARKER, CONTEXT_REBUILD_RATIO, PLAN_ANCHOR_MARKER
from friday.logging_config import get_logger
from friday.storage import UserSettings, load_settings, resolved_workspace

_log = get_logger("context_assembler")

LAYER_CAPS_CHARS = {
    "plan": 2200,
    "checkpoint": 3200,
    "recent_user": 1600,
    "workspace_memory": 1800,
    "user_memory": 900,
}


def _truncate(text: str, cap: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= cap:
        return cleaned
    return cleaned[: cap - 12] + "\n...(已截断)"


def _recent_user_text(messages: list[dict[str, Any]], *, cap: int) -> str:
    lines: list[str] = []
    used = 0
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content", "")).strip()
        if not content or content.startswith("【系统提示】"):
            continue
        if content.startswith(PLAN_ANCHOR_MARKER) or content.startswith(CHECKPOINT_MARKER):
            continue
        piece = content[:500]
        if used + len(piece) > cap:
            break
        lines.insert(0, piece)
        used += len(piece)
    return "\n\n".join(lines)


def assemble_injection_blocks(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    settings: UserSettings | None = None,
) -> list[dict[str, Any]]:
    """返回应置于 system 之后的前缀 user 消息块（不含 tail）。"""
    cfg = settings or load_settings()
    blocks: list[dict[str, Any]] = []

    if session_id:
        from friday.plan import plan_prompt_block
        from friday.prefix_cache import is_plan_anchor_message
        from friday.sessions import get_session

        has_plan_anchor = any(is_plan_anchor_message(m) for m in messages)
        session = get_session(session_id)
        if session and not has_plan_anchor:
            plan_block = plan_prompt_block(session)
            if plan_block:
                blocks.append({
                    "role": "user",
                    "content": _truncate(plan_block, LAYER_CAPS_CHARS["plan"]),
                })

        from friday.checkpoint_writer import format_checkpoint_for_prompt

        ck = format_checkpoint_for_prompt(session_id, max_chars=LAYER_CAPS_CHARS["checkpoint"])
        if ck:
            blocks.append({"role": "user", "content": ck})

    recent = _recent_user_text(messages, cap=LAYER_CAPS_CHARS["recent_user"])
    if recent:
        blocks.append({
            "role": "user",
            "content": f"[近期用户要点]\n{recent}",
        })

    try:
        from friday.workspace_memory import format_for_prompt as ws_memory_prompt

        ws_block = ws_memory_prompt(resolved_workspace(cfg))
        if ws_block:
            blocks.append({
                "role": "user",
                "content": _truncate(ws_block, LAYER_CAPS_CHARS["workspace_memory"]),
            })
    except Exception:
        _log.debug("workspace memory 注入跳过", exc_info=True)

    from friday.user_memory import format_for_prompt as user_memory_prompt

    mem = user_memory_prompt()
    if mem:
        blocks.append({
            "role": "user",
            "content": _truncate(mem, LAYER_CAPS_CHARS["user_memory"]),
        })

    return blocks


def should_rebuild(
    settings: UserSettings,
    messages: list[dict[str, Any]],
    *,
    tool_definitions: list[dict[str, Any]] | None = None,
) -> tuple[bool, dict[str, Any]]:
    if not getattr(settings, "context_smart_enabled", True):
        return False, {}
    from friday.brain import compute_context_meter

    meter = compute_context_meter(settings, messages, tool_definitions=tool_definitions)
    ratio = float(meter.get("budget_ratio", 0) or 0)
    return ratio >= CONTEXT_REBUILD_RATIO, meter


def rebuild_messages(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    settings: UserSettings | None = None,
    min_keep_recent: int = 8,
) -> tuple[list[dict[str, Any]], bool]:
    """85% 触发 rebuild：注入 assembler 层 + 保留最近 tail。"""
    cfg = settings or load_settings()
    if not messages:
        return messages, False

    should, meter = should_rebuild(cfg, messages)
    if not should:
        return messages, False

    system = messages[0] if messages[0].get("role") == "system" else None
    rest = messages[1:] if system else list(messages)
    tail = rest[-min_keep_recent:] if len(rest) > min_keep_recent else rest

    # rebuild 裁掉早期消息（含计划锚点），须基于 tail 重新注入 plan/checkpoint 层
    injection = assemble_injection_blocks(session_id, tail, settings=cfg)
    rebuilt: list[dict[str, Any]] = []
    if system:
        rebuilt.append(system)
    rebuilt.extend(injection)
    rebuilt.extend(tail)

    from friday.context import prune_old_tool_results

    rebuilt = prune_old_tool_results(rebuilt, keep_tail_blocks=3)

    _log.info(
        "上下文 rebuild | session=%s tokens≈%s ratio=%.2f",
        session_id,
        meter.get("context_tokens"),
        meter.get("budget_ratio"),
    )
    return rebuilt, True
