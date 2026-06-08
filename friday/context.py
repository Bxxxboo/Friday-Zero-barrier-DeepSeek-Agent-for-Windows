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
    window: int = 6,
    repeat_threshold: int = 3,
) -> tuple[bool, str]:
    """检测最近是否重复同一工具调用（参数相同或同名空转）。"""
    signatures: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            name = str(fn.get("name", ""))
            args = str(fn.get("arguments", ""))
            sig = hashlib.sha1(f"{name}|{args}".encode("utf-8")).hexdigest()[:12]
            signatures.append(sig)
        if len(signatures) >= window:
            break
    if len(signatures) < repeat_threshold:
        return False, ""
    recent = signatures[:repeat_threshold]
    if len(set(recent)) == 1:
        return True, "检测到连续重复的工具调用，建议合并步骤或换一种方式。"
    return False, ""


def sort_tool_definitions(definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按工具名稳定排序，利于 DeepSeek 前缀缓存命中。"""
    return sorted(
        definitions,
        key=lambda item: str((item.get("function") or {}).get("name", "")),
    )
