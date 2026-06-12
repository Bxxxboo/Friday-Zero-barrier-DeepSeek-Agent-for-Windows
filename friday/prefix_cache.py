"""DeepSeek 前缀缓存：冻结 system/tools、append-only 日志、漂移诊断。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from friday.config import COMPACT_SUMMARY_MARKER, PLAN_ANCHOR_MARKER
from friday.logging_config import get_logger
from friday.storage import UserSettings, resolved_workspace

_log = get_logger("prefix_cache")


@dataclass(frozen=True)
class FrozenPrefix:
    system_prompt: str
    tool_definitions: list[dict[str, Any]]
    fingerprint: str
    settings_fingerprint: str


def compute_tools_fingerprint(tools: list[dict[str, Any]]) -> str:
    payload = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def compute_prefix_fingerprint(system_prompt: str, tools: list[dict[str, Any]]) -> str:
    payload = f"{system_prompt}\n---\n{compute_tools_fingerprint(tools)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def compute_settings_fingerprint(settings: UserSettings, *, yolo_unlocked: bool = False) -> str:
    """影响 system/tools 冻结内容的设置指纹。"""
    from friday.brain import build_system_prompt
    from friday.interaction_modes import normalize_mode
    from friday.rules import active_rules_prompt
    from friday.tools.registry import get_frozen_tool_definitions
    from friday.vision import vision_ready

    mode = normalize_mode(getattr(settings, "interaction_mode", "agent"))
    parts = [
        settings.model,
        str(resolved_workspace(settings)),
        mode,
        str(bool(yolo_unlocked)),
        str(bool(vision_ready(settings))),
        active_rules_prompt(),
        build_system_prompt(settings, yolo_unlocked=yolo_unlocked),
        compute_tools_fingerprint(get_frozen_tool_definitions(settings)),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def build_frozen_prefix(
    settings: UserSettings,
    *,
    yolo_unlocked: bool = False,
) -> FrozenPrefix:
    from friday.brain import build_system_prompt
    from friday.tools.registry import get_frozen_tool_definitions

    system_prompt = build_system_prompt(settings, yolo_unlocked=yolo_unlocked)
    tools = get_frozen_tool_definitions(settings)
    settings_fp = compute_settings_fingerprint(settings, yolo_unlocked=yolo_unlocked)
    prefix_fp = compute_prefix_fingerprint(system_prompt, tools)
    return FrozenPrefix(
        system_prompt=system_prompt,
        tool_definitions=tools,
        fingerprint=prefix_fp,
        settings_fingerprint=settings_fp,
    )


def is_compact_summary_message(msg: dict[str, Any]) -> bool:
    if msg.get("role") != "user":
        return False
    content = str(msg.get("content", ""))
    return content.startswith(COMPACT_SUMMARY_MARKER)


def is_plan_anchor_message(msg: dict[str, Any]) -> bool:
    if msg.get("role") != "user":
        return False
    content = str(msg.get("content", ""))
    return content.startswith(PLAN_ANCHOR_MARKER)


def is_protected_context_message(msg: dict[str, Any]) -> bool:
    return is_compact_summary_message(msg) or is_plan_anchor_message(msg)


def count_tool_rounds_since_last_compact(messages: list[dict[str, Any]]) -> int:
    """统计最近一次自动摘要之后已完成的工具调用轮次。"""
    start = 0
    for idx, msg in enumerate(messages):
        if is_compact_summary_message(msg):
            start = idx + 1
    count = 0
    for msg in messages[start:]:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            count += 1
    return count


def split_message_regions(
    messages: list[dict[str, Any]],
    *,
    min_keep_recent: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """拆分为 system、摘要区、可折叠区、最近保留区。"""
    if not messages:
        raise ValueError("messages 为空")
    system = messages[0]
    rest = messages[1:]
    if len(rest) <= min_keep_recent:
        return system, [], [], rest

    tail = rest[-min_keep_recent:]
    body = rest[:-min_keep_recent]
    summaries: list[dict[str, Any]] = []
    compactable: list[dict[str, Any]] = []
    for msg in body:
        if is_protected_context_message(msg):
            summaries.append(msg)
        else:
            compactable.append(msg)
    return system, summaries, compactable, tail


def detect_prefix_drift(
    frozen: FrozenPrefix,
    messages: list[dict[str, Any]],
    settings: UserSettings,
    *,
    yolo_unlocked: bool = False,
) -> list[str]:
    """检测当前 messages/settings 是否与冻结前缀不一致。"""
    reasons: list[str] = []
    if not messages or messages[0].get("role") != "system":
        reasons.append("缺少 system 消息")
    elif str(messages[0].get("content", "")) != frozen.system_prompt:
        reasons.append("system 字节已变化")

    current_settings_fp = compute_settings_fingerprint(settings, yolo_unlocked=yolo_unlocked)
    if current_settings_fp != frozen.settings_fingerprint:
        reasons.append("设置/规则/工作区已变化")

    return reasons


def log_prefix_drift(reasons: list[str], *, fingerprint: str) -> None:
    if reasons:
        _log.warning(
            "前缀漂移 | fingerprint=%s | %s",
            fingerprint[:12],
            "；".join(reasons),
        )


def format_messages_for_summary(batch: list[dict[str, Any]], *, max_chars: int = 12_000) -> str:
    lines: list[str] = []
    used = 0
    for msg in batch:
        role = str(msg.get("role", ""))
        if role == "assistant" and msg.get("tool_calls"):
            names = [
                str((tc.get("function") or {}).get("name", ""))
                for tc in (msg.get("tool_calls") or [])
            ]
            piece = f"[assistant 调用工具: {', '.join(n for n in names if n)}]"
        else:
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            piece = f"[{role}] {content}"
        if used + len(piece) + 1 > max_chars:
            lines.append("... (更早内容已省略)")
            break
        lines.append(piece)
        used += len(piece) + 1
    return "\n".join(lines)


def deterministic_summary(batch: list[dict[str, Any]]) -> str:
    """无 API 时的确定性摘要（测试与离线 fallback）。"""
    text = format_messages_for_summary(batch, max_chars=4000)
    if len(text) <= 900:
        return text
    return f"{text[:420]}...\n... (共 {len(batch)} 条消息，细节已省略) ...\n{text[-420:]}"
