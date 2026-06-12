"""上下文卫生：工具结果压缩、重复调用检测、历史消息瘦身。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from friday.config import (
    MAX_TOOL_RESULT_CHARS,
    TOOL_RESULT_ARCHIVE_CHARS,
    TOOL_RESULT_HEAD_CHARS,
    TOOL_RESULT_TAIL_CHARS,
)

_BASE64_RE = re.compile(
    r"data:[a-zA-Z0-9/+.-]+;base64,[A-Za-z0-9+/=\s]{200,}",
    re.MULTILINE,
)
_LONG_HEX_RE = re.compile(r"(?i)(?=[0-9a-f]*[0-9])[0-9a-f]{128,}")


def _strip_noisy_payloads(text: str) -> str:
    text = _BASE64_RE.sub("[base64 数据已省略]", text)
    text = _LONG_HEX_RE.sub("[长十六进制数据已省略]", text)
    return text


def _collapse_duplicate_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= 3:
        return text
    out: list[str] = []
    prev = None
    repeat = 0
    for line in lines:
        if line == prev:
            repeat += 1
            continue
        if repeat > 0:
            out.append(f"... (上一行重复 {repeat + 1} 次)")
            repeat = 0
        out.append(line)
        prev = line
    if repeat > 0:
        out.append(f"... (上一行重复 {repeat + 1} 次)")
    return "\n".join(out)


def _sample_long_listing(text: str, *, head_lines: int = 40, tail_lines: int = 15) -> str:
    lines = text.splitlines()
    if len(lines) <= head_lines + tail_lines + 5:
        return text
    head = lines[:head_lines]
    tail = lines[-tail_lines:]
    omitted = len(lines) - len(head) - len(tail)
    return "\n".join(
        [
            *head,
            f"... (省略 {omitted} 行目录/列表项) ...",
            *tail,
        ]
    )


_MARKER_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9_]{3,48}")


def _extract_middle_highlights(text: str, *, max_chars: int = 120) -> str:
    """从被截断的中间段提取短而信息密度高的行（错误、标记等）。"""
    if not text or len(text) <= max_chars:
        return text
    highlights: list[str] = []
    used = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) <= 80 and not (len(set(stripped)) <= 2 and len(stripped) > 20):
            if used + len(stripped) + 1 > max_chars:
                break
            highlights.append(stripped)
            used += len(stripped) + 1
            continue
        for match in _MARKER_TOKEN_RE.finditer(stripped):
            token = match.group(0)
            if used + len(token) + 1 > max_chars:
                break
            if token not in highlights:
                highlights.append(token)
                used += len(token) + 1
    return "\n".join(highlights)


def compress_tool_result(
    tool_name: str,
    result: str,
    *,
    max_chars: int | None = None,
    aggressive: bool = False,
) -> str:
    """将工具输出压缩到预算内，保留头尾与关键信息。"""
    if not result:
        return result

    budget = max_chars or (TOOL_RESULT_ARCHIVE_CHARS if aggressive else MAX_TOOL_RESULT_CHARS)
    cleaned = _strip_noisy_payloads(result)
    cleaned = _collapse_duplicate_lines(cleaned)
    if len(cleaned) <= budget:
        return cleaned
    if tool_name in {"list_directory", "search_files", "find_duplicates", "get_process_list"}:
        cleaned = _sample_long_listing(cleaned)

    if len(cleaned) <= budget:
        return cleaned

    head_budget = min(TOOL_RESULT_HEAD_CHARS, max(budget // 2, 400))
    tail_budget = min(TOOL_RESULT_TAIL_CHARS, max(budget - head_budget - 80, 200))
    head = cleaned[:head_budget]
    tail = cleaned[-tail_budget:] if tail_budget else ""
    middle = cleaned[head_budget : len(cleaned) - tail_budget] if tail_budget else cleaned[head_budget:]
    middle_keep = _extract_middle_highlights(middle)
    original_len = len(result)
    note = f"\n... (已压缩，原长 {original_len} 字符；保留首尾关键内容) ..."
    if middle_keep:
        merged = f"{head}\n{middle_keep}{note}\n{tail}" if tail else f"{head}\n{middle_keep}{note}"
    else:
        merged = f"{head}{note}\n{tail}" if tail else f"{head}{note}"
    if len(merged) > budget + 120:
        merged = merged[: budget + 120] + "..."
    return merged


def compress_tool_message_content(content: str) -> str:
    """历史 tool 消息归档压缩（更激进）。"""
    return compress_tool_result("tool", content, aggressive=True)


def detect_repeated_tool_loop(
    messages: list[dict[str, Any]],
    *,
    window: int = 8,
    repeat_threshold: int = 3,
) -> tuple[bool, str]:
    """检测最近是否重复同一工具调用（参数相同或同名空转）。"""
    signatures: list[str] = []
    names: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            name = str(fn.get("name", ""))
            args = str(fn.get("arguments", ""))
            sig = hashlib.sha1(f"{name}|{args}".encode("utf-8")).hexdigest()[:12]
            signatures.append(sig)
            if name:
                names.append(name)
        if len(signatures) >= window:
            break
    if len(signatures) < repeat_threshold:
        return False, ""
    recent_sigs = signatures[:repeat_threshold]
    if len(set(recent_sigs)) == 1:
        return True, "检测到连续重复的工具调用（参数相同），请合并步骤、改写脚本，或向用户说明卡点。"
    recent_names = names[:repeat_threshold]
    if len(recent_names) >= repeat_threshold and len(set(recent_names)) == 1:
        tool = recent_names[0]
        return (
            True,
            f"已连续 {repeat_threshold} 次调用 {tool} 但进展不明显，请停止重复试探，"
            "改用不同工具/路径/脚本，或调用 update_session_plan 调整计划。",
        )
    return False, ""


def sort_tool_definitions(definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按工具名稳定排序，利于 DeepSeek 前缀缓存命中。"""
    return sorted(
        definitions,
        key=lambda item: str((item.get("function") or {}).get("name", "")),
    )


def sanitize_agent_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """修复 OpenAI 兼容 API 要求的 tool 消息顺序，丢弃孤儿 tool / 未完成 tool 轮次。"""
    if not messages:
        return messages

    out: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = str(msg.get("role", ""))

        if role == "system":
            out.append(msg)
            i += 1
            continue

        if role == "tool":
            i += 1
            continue

        if role == "assistant" and msg.get("tool_calls"):
            calls = [c for c in (msg.get("tool_calls") or []) if isinstance(c, dict)]
            call_ids = [str(c.get("id", "")).strip() for c in calls if str(c.get("id", "")).strip()]
            block = [msg]
            j = i + 1
            seen: set[str] = set()
            while j < len(messages) and messages[j].get("role") == "tool":
                tid = str(messages[j].get("tool_call_id", "")).strip()
                if tid in call_ids:
                    block.append(messages[j])
                    seen.add(tid)
                j += 1
            if call_ids and seen == set(call_ids):
                out.extend(block)
            else:
                stripped = dict(msg)
                stripped.pop("tool_calls", None)
                note = "[此前工具调用未完成，已从上下文中省略]"
                content = str(stripped.get("content") or "").strip()
                stripped["content"] = f"{content}\n{note}".strip() if content else note
                out.append(stripped)
            i = j
            continue

        out.append(msg)
        i += 1

    return out


def iter_message_blocks(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """将消息列表拆成不可拆的块（assistant+tool_calls 与其 tool 结果为一组）。"""
    blocks: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            block = [msg]
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                block.append(messages[j])
                j += 1
            blocks.append(block)
            i = j
            continue
        if msg.get("role") == "tool":
            i += 1
            continue
        blocks.append([msg])
        i += 1
    return blocks


def flatten_message_blocks(blocks: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for block in blocks:
        flat.extend(block)
    return flat


def prune_old_tool_results(
    messages: list[dict[str, Any]],
    *,
    keep_tail_blocks: int = 4,
) -> list[dict[str, Any]]:
    """checkpoint/rebuild 后丢弃旧 tool 输出，保留最近若干工具轮次。"""
    if not messages:
        return messages
    blocks = iter_message_blocks(messages)
    if len(blocks) <= keep_tail_blocks:
        return messages

    pruned_blocks: list[list[dict[str, Any]]] = []
    tail_start = len(blocks) - keep_tail_blocks
    for idx, block in enumerate(blocks):
        if idx < tail_start and len(block) > 1 and block[0].get("role") == "assistant":
            assistant = dict(block[0])
            assistant.pop("tool_calls", None)
            note = "[较早工具结果已 prune，完整记录见会话展示层]"
            content = str(assistant.get("content") or "").strip()
            assistant["content"] = f"{content}\n{note}".strip() if content else note
            pruned_blocks.append([assistant])
            continue
        pruned_blocks.append(block)
    return flatten_message_blocks(pruned_blocks)
