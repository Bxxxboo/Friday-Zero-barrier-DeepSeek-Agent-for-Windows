"""内置更新公告 —— 从 assets/changelog.json 加载各版本说明。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from friday.io_utils import load_json
from friday.paths import bundle_dir
from friday.version import __version__

_CHANGELOG_PATH = bundle_dir() / "assets" / "changelog.json"


def parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts[:4]) or (0,)


def _changelog_path() -> Path:
    return _CHANGELOG_PATH


@lru_cache(maxsize=1)
def load_entries() -> list[dict[str, Any]]:
    path = _changelog_path()
    if not path.is_file():
        return []
    data = load_json(path)
    if not isinstance(data, dict):
        return []
    entries = data.get("entries")
    if not isinstance(entries, list):
        return []
    valid: list[dict[str, Any]] = []
    for item in entries:
        if isinstance(item, dict) and item.get("version"):
            valid.append(item)
    valid.sort(key=lambda e: parse_version(str(e.get("version", ""))), reverse=True)
    return valid


def clear_cache() -> None:
    load_entries.cache_clear()


def unseen_entries(acknowledged: str, current: str | None = None) -> list[dict[str, Any]]:
    """返回 acknowledged 之后、current 及以下的未读公告（新版在前）。"""
    cur = current or __version__
    ack_v = parse_version(acknowledged)
    cur_v = parse_version(cur)
    if ack_v >= cur_v:
        return []
    result: list[dict[str, Any]] = []
    for entry in load_entries():
        ev = parse_version(str(entry.get("version", "")))
        if ack_v < ev <= cur_v:
            result.append(entry)
    return result


def has_unseen(acknowledged: str, current: str | None = None) -> bool:
    return bool(unseen_entries(acknowledged, current))


def changelog_payload(acknowledged: str, current: str | None = None) -> dict[str, Any]:
    cur = current or __version__
    unseen = unseen_entries(acknowledged, cur)
    return {
        "current": cur,
        "acknowledged": acknowledged or "",
        "has_unseen": bool(unseen),
        "entries": load_entries(),
        "unseen": unseen,
    }
