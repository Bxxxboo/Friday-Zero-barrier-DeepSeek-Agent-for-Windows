"""文件变更 diff 预览（供聊天区审查）。"""

from __future__ import annotations

import difflib
from pathlib import Path


def read_text_if_exists(path: str | Path) -> str:
    target = Path(path).expanduser()
    if not target.is_file():
        return ""
    try:
        return target.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_file_change_payload(
    path: str | Path,
    old_text: str,
    new_text: str,
    *,
    tool_name: str = "write_text_file",
    max_lines: int = 48,
) -> dict[str, object]:
    """生成 file_change 事件 payload。"""
    resolved = str(path)
    is_new = not old_text and bool(new_text)
    old_lines = old_text.splitlines() if old_text else []
    new_lines = new_text.splitlines() if new_text else []
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="修改前",
            tofile="修改后",
            lineterm="",
        )
    )
    truncated = len(diff_lines) > max_lines
    preview_lines = diff_lines[:max_lines]
    if truncated:
        preview_lines.append(f"... (diff 已截断，共 {len(diff_lines)} 行)")
    diff_text = "\n".join(preview_lines) if preview_lines else "(无文本差异)"
    return {
        "tool": tool_name,
        "path": resolved,
        "is_new": is_new,
        "old_chars": len(old_text),
        "new_chars": len(new_text),
        "diff": diff_text,
        "truncated": truncated,
    }
