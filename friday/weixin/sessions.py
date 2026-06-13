from __future__ import annotations

import re
from pathlib import Path

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir
from friday.sessions import (
    create_session,
    ensure_session_listed,
    get_session,
    rename_session,
    session_exists,
)

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


def has_weixin_mappings() -> bool:
    """侧栏「我的微信」会话映射是否存在（说明通道曾成功收发）。"""
    return bool(_read_mapping())


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


def _notify_sessions_changed() -> None:
    try:
        from friday.ws_broadcast import notify_sessions_changed

        notify_sessions_changed()
    except Exception:
        pass


def resolve_session_id(account_id: str, peer_id: str, *, activate: bool = False) -> str:
    key = peer_key(account_id, peer_id)
    mapping = _read_mapping()
    existing = mapping.get(key, "").strip()
    if existing and session_exists(existing):
        _maybe_upgrade_weixin_title(existing)
        ensure_session_listed(existing, prepend=True)
        return existing
    if existing:
        _log.warning("微信会话映射失效，将重建 | peer=%s stale=%s", peer_id, existing)
        mapping.pop(key, None)

    session = create_session(WEIXIN_SESSION_TITLE, title_pinned=True, activate=activate)
    mapping[key] = session.id
    _write_mapping(mapping)
    _log.info("创建微信会话 | peer=%s session=%s", peer_id, session.id)
    _notify_sessions_changed()
    return session.id


def ensure_weixin_sessions_ready() -> str | None:
    """启动时：为已登录微信账号预建「我的微信」会话并列入侧边栏。"""
    from friday.storage import load_settings
    from friday.weixin.client import resolve_account

    if not getattr(load_settings(), "weixin_bridge_enabled", True):
        return None

    account = resolve_account("")
    if account is None:
        return None

    peer_id = (account.user_id or "").strip()
    if not peer_id:
        return None

    session_id = resolve_session_id(account.account_id, peer_id, activate=True)
    ensure_session_listed(session_id, prepend=True)
    migrate_weixin_session_titles()
    _notify_sessions_changed()
    return session_id


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
