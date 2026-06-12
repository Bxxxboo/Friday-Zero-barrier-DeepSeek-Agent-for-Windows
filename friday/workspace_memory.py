"""工作区级 MEMORY.md —— 跨会话项目规矩与稳定事实。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_text, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("workspace_memory")

_MEMORY_MARKER = "# 工作区记忆"
_PROMOTION_PATH = "workspace_memory_promotion.json"


def _workspace_hash(workspace: str) -> str:
    return hashlib.sha256(str(workspace or "").encode("utf-8")).hexdigest()[:12]


def workspace_memory_dir(workspace: str) -> Path:
    path = get_appdata_dir() / "workspaces" / _workspace_hash(workspace)
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_path(workspace: str) -> Path:
    return workspace_memory_dir(workspace) / "MEMORY.md"


def promotion_tracker_path(workspace: str) -> Path:
    return workspace_memory_dir(workspace) / _PROMOTION_PATH


def load_memory(workspace: str) -> str:
    path = memory_path(workspace)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def save_memory(workspace: str, content: str) -> None:
    body = str(content or "").strip()
    if not body.startswith(_MEMORY_MARKER):
        body = f"{_MEMORY_MARKER}\n\n{body}"
    atomic_write_text(memory_path(workspace), body + "\n")


def format_for_prompt(workspace: str, *, max_chars: int = 1800) -> str:
    text = load_memory(workspace)
    if not text:
        return ""
    if len(text) <= max_chars:
        return f"[工作区记忆]\n{text}"
    return f"[工作区记忆]\n{text[: max_chars - 10]}...(已截断)"


def _load_promotion_tracker(workspace: str) -> dict[str, int]:
    data = load_json(promotion_tracker_path(workspace), default={})
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items()}


def _save_promotion_tracker(workspace: str, tracker: dict[str, int]) -> None:
    from friday.io_utils import atomic_write_json

    atomic_write_json(promotion_tracker_path(workspace), tracker)


def _candidate_facts(fields: Any) -> list[str]:
    facts: list[str] = []
    for key in ("decisions", "user_prefs"):
        body = str(getattr(fields, key, "") or "").strip()
        if not body or body == "（暂无）":
            continue
        for line in body.splitlines():
            piece = line.strip().lstrip("-•* ").strip()
            if len(piece) >= 8:
                facts.append(piece[:240])
    return facts[:12]


def maybe_promote_from_checkpoint(session_id: str, fields: Any) -> list[str]:
    """重复出现 2 次 checkpoint 后晋升到 MEMORY.md。"""
    from friday.storage import load_settings, resolved_workspace

    workspace = resolved_workspace(load_settings())
    tracker = _load_promotion_tracker(workspace)
    promoted: list[str] = []
    for fact in _candidate_facts(fields):
        key = fact.casefold()
        tracker[key] = tracker.get(key, 0) + 1
        if tracker[key] >= 2:
            current = load_memory(workspace)
            if fact not in current:
                block = f"- {fact}（来自会话 {session_id}）"
                save_memory(workspace, f"{current}\n{block}".strip() if current else block)
                promoted.append(fact)
    _save_promotion_tracker(workspace, tracker)
    if promoted:
        _log.info("MEMORY 晋升 | workspace=%s count=%d", _workspace_hash(workspace), len(promoted))
    return promoted
