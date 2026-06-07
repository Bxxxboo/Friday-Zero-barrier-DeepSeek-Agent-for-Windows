from __future__ import annotations

import re
from pathlib import Path

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir
from friday.sessions import create_session, get_session, rename_session, session_exists

_log = get_logger("weixin.sessions")

_MAPPING_FILE = "weixin_sessions.json"
WEIXIN_SESSION_TITLE = "我的微信"
_LEGACY_TITLE_RE = re.compile(r"^微信(?:\s+[0-9a-f]{8})?$", re.I)


def _mapping_path() -> Path:
    return get_appdata_dir() / _MAPPING_FILE


def _read_mapping() -> dict[str, str]:
    data = load_json(_mapping_path())
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(v).strip()}


def _write_mapping(mapping: dict[str, str]) -> None:
    atomic_write_json(_mapping_path(), mapping)


def is_weixin_session(session_id: str) -> bool:
    sid = session_id.strip()
    if not sid:
        return False
    return sid in set(_read_mapping().values())


def peer_key(account_id: str, peer_id: str) -> str:
    return f"{account_id.strip()}::{peer_id.strip()}"


def _maybe_upgrade_weixin_title(session_id: str) -> None:
    session = get_session(session_id)
    if session is None or session.title_pinned:
        return
    if session.title == WEIXIN_SESSION_TITLE or _LEGACY_TITLE_RE.match(session.title.strip()):
        rename_session(session_id, WEIXIN_SESSION_TITLE)


def resolve_session_id(account_id: str, peer_id: str) -> str:
    key = peer_key(account_id, peer_id)
    mapping = _read_mapping()
    existing = mapping.get(key, "").strip()
    if existing and session_exists(existing):
        _maybe_upgrade_weixin_title(existing)
        return existing

    session = create_session(WEIXIN_SESSION_TITLE, title_pinned=True)
    mapping[key] = session.id
    _write_mapping(mapping)
    _log.info("创建微信会话 | peer=%s session=%s", peer_id, session.id)
    return session.id


def migrate_weixin_session_titles() -> int:
    """将旧版「微信 xxxxxxxx」标题升级为「我的微信」。"""
    updated = 0
    for session_id in set(_read_mapping().values()):
        before = get_session(session_id)
        if before is None:
            continue
        old_title = before.title
        _maybe_upgrade_weixin_title(session_id)
        after = get_session(session_id)
        if after and after.title != old_title:
            updated += 1
    return updated


def session_title_for_peer(account_id: str, peer_id: str) -> str:
    session_id = resolve_session_id(account_id, peer_id)
    session = get_session(session_id)
    return session.title if session else WEIXIN_SESSION_TITLE
