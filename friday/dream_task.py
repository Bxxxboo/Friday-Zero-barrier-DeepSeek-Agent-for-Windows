"""Dream 定期蒸馏 —— 合并去重工作区 MEMORY（默认关闭，opt-in）。"""

from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_text
from friday.logging_config import get_logger
from friday.storage import UserSettings, load_settings, resolved_workspace
from friday.workspace_memory import load_memory, memory_path, save_memory

_log = get_logger("dream_task")

_LAST_RUN_FILE = "dream_last_run.txt"
_MIN_INTERVAL_SEC = 7 * 24 * 3600


def _last_run_path() -> Path:
    from friday.paths import get_appdata_dir

    return get_appdata_dir() / _LAST_RUN_FILE


def _should_run(settings: UserSettings) -> bool:
    if not getattr(settings, "dream_memory_enabled", False):
        return False
    path = _last_run_path()
    if not path.exists():
        return True
    try:
        last = float(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return True
    return (time.time() - last) >= _MIN_INTERVAL_SEC


def _mark_ran() -> None:
    atomic_write_text(_last_run_path(), f"{time.time():.0f}\n")


def _dedupe_lines(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    unique: list[str] = []
    for line in lines:
        norm = line.casefold()
        if any(difflib.SequenceMatcher(None, norm, u.casefold()).ratio() > 0.9 for u in unique):
            continue
        unique.append(line)
    return "\n".join(unique)


def run_dream_if_due(*, settings: UserSettings | None = None, force: bool = False) -> dict[str, Any]:
    cfg = settings or load_settings()
    if not force and not _should_run(cfg):
        return {"ok": True, "ran": False, "message": "未到执行窗口或未开启"}
    workspace = resolved_workspace(cfg)
    before = load_memory(workspace)
    if not before.strip():
        _mark_ran()
        return {"ok": True, "ran": True, "message": "MEMORY 为空，跳过"}

    backup = memory_path(workspace).with_suffix(".md.bak")
    atomic_write_text(backup, before + "\n")
    merged = _dedupe_lines(before)
    save_memory(workspace, merged)
    _mark_ran()
    _log.info("Dream 蒸馏完成 | workspace=%s", workspace)
    return {
        "ok": True,
        "ran": True,
        "backup": str(backup),
        "before_lines": len(before.splitlines()),
        "after_lines": len(merged.splitlines()),
    }
