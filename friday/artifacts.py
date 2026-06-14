"""工作区生成物登记、TTL 回收与软删除（trash）。"""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.storage import UserSettings, load_settings, resolved_workspace

_log = get_logger("artifacts")

FRIDAY_DIR = ".friday"
ARTIFACTS_DIR = "artifacts"
DELIVERED_DIR = "delivered"
TRASH_DIR = "trash"
INDEX_FILE = "artifact_index.json"

LIFECYCLE_SCRATCH = "scratch"
LIFECYCLE_SESSION = "session"
LIFECYCLE_DELIVERED = "delivered"
LIFECYCLE_PINNED = "pinned"

STATUS_ACTIVE = "active"
STATUS_TRASHED = "trashed"

DEFAULT_SCRATCH_TTL_HOURS = 24
DEFAULT_SESSION_TTL_DAYS = 30
DEFAULT_TRASH_TTL_DAYS = 7
DEFAULT_SESSION_DELETE_GRACE_DAYS = 7
DEFAULT_WEIXIN_DELIVERED_TTL_DAYS = 7
SCRIPT_POST_RUN_GRACE_HOURS = 1


def friday_root(settings: UserSettings | None = None) -> Path:
    root = Path(resolved_workspace(settings or load_settings()))
    return (root / FRIDAY_DIR).resolve()


def artifacts_dir(settings: UserSettings | None = None) -> Path:
    target = friday_root(settings) / ARTIFACTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def delivered_dir(settings: UserSettings | None = None) -> Path:
    target = friday_root(settings) / DELIVERED_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def trash_dir(settings: UserSettings | None = None) -> Path:
    target = friday_root(settings) / TRASH_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_friday_dirs(settings: UserSettings | None = None) -> Path:
    artifacts_dir(settings)
    delivered_dir(settings)
    trash_dir(settings)
    return friday_root(settings)


def normalize_path(path: str | Path, *, settings: UserSettings | None = None) -> str:
    raw = Path(path).expanduser().resolve()
    return str(raw).replace("\\", "/")


def _index_path(settings: UserSettings | None = None) -> Path:
    root = ensure_friday_dirs(settings)
    return root / INDEX_FILE


def _load_index(settings: UserSettings | None = None) -> list[dict[str, Any]]:
    data = load_json(_index_path(settings))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _save_index(items: list[dict[str, Any]], settings: UserSettings | None = None) -> None:
    atomic_write_json(_index_path(settings), items)


def _ttl_settings(settings: UserSettings) -> dict[str, int]:
    return {
        "scratch_hours": max(1, int(getattr(settings, "artifact_scratch_ttl_hours", DEFAULT_SCRATCH_TTL_HOURS) or DEFAULT_SCRATCH_TTL_HOURS)),
        "session_days": max(1, int(getattr(settings, "artifact_session_ttl_days", DEFAULT_SESSION_TTL_DAYS) or DEFAULT_SESSION_TTL_DAYS)),
        "trash_days": max(1, int(getattr(settings, "artifact_trash_ttl_days", DEFAULT_TRASH_TTL_DAYS) or DEFAULT_TRASH_TTL_DAYS)),
        "session_delete_grace_days": max(
            1,
            int(getattr(settings, "artifact_session_delete_grace_days", DEFAULT_SESSION_DELETE_GRACE_DAYS) or DEFAULT_SESSION_DELETE_GRACE_DAYS),
        ),
    }


def _expires_at_for(lifecycle: str, *, settings: UserSettings, now: float | None = None) -> float | None:
    ts = now if now is not None else time.time()
    ttl = _ttl_settings(settings)
    if lifecycle == LIFECYCLE_SCRATCH:
        return ts + ttl["scratch_hours"] * 3600
    if lifecycle == LIFECYCLE_SESSION:
        return ts + ttl["session_days"] * 86400
    if lifecycle == LIFECYCLE_DELIVERED:
        return None
    if lifecycle == LIFECYCLE_PINNED:
        return None
    return None


def is_under_friday(path: str | Path, *, settings: UserSettings | None = None) -> bool:
    try:
        raw = Path(path).expanduser().resolve()
        raw.relative_to(friday_root(settings))
        return True
    except (ValueError, OSError):
        return False


def is_artifacts_path(path: str | Path, *, settings: UserSettings | None = None) -> bool:
    try:
        raw = Path(path).expanduser().resolve()
        raw.relative_to(artifacts_dir(settings))
        return True
    except (ValueError, OSError):
        return False


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def register_artifact(
    path: str | Path,
    *,
    kind: str = "other",
    lifecycle: str = LIFECYCLE_SCRATCH,
    tool: str = "",
    session_id: str = "",
    settings: UserSettings | None = None,
) -> dict[str, Any] | None:
    """登记可管理文件；非文件或不在工作区内则跳过。"""
    cfg = settings or load_settings()
    target = Path(path).expanduser()
    if not target.is_file():
        return None
    normalized = normalize_path(target, settings=cfg)
    workspace = Path(resolved_workspace(cfg)).resolve()
    try:
        target.resolve().relative_to(workspace)
    except ValueError:
        return None

    if lifecycle == LIFECYCLE_PINNED:
        pass
    elif is_artifacts_path(target, settings=cfg):
        if lifecycle not in {LIFECYCLE_PINNED, LIFECYCLE_DELIVERED}:
            lifecycle = LIFECYCLE_SCRATCH
    elif lifecycle == LIFECYCLE_SCRATCH:
        lifecycle = LIFECYCLE_SESSION

    sid = session_id.strip()
    if not sid:
        from friday.agent_context import current_session_id

        sid = current_session_id.get() or ""

    now = time.time()
    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "path": normalized,
        "kind": kind,
        "lifecycle": lifecycle,
        "session_id": sid,
        "tool": tool,
        "created_at": now,
        "last_used_at": now,
        "expires_at": _expires_at_for(lifecycle, settings=cfg, now=now),
        "status": STATUS_ACTIVE,
        "trashed_at": None,
        "size_bytes": _file_size(target.resolve()),
    }

    items = _load_index(cfg)
    replaced = False
    for idx, item in enumerate(items):
        if str(item.get("path", "")).replace("\\", "/") == normalized:
            entry["id"] = str(item.get("id") or entry["id"])
            entry["created_at"] = float(item.get("created_at") or now)
            items[idx] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    _save_index(items, cfg)
    return entry


def touch_artifact(path: str | Path, *, settings: UserSettings | None = None) -> None:
    cfg = settings or load_settings()
    normalized = normalize_path(path, settings=cfg)
    now = time.time()
    items = _load_index(cfg)
    changed = False
    for item in items:
        if str(item.get("path", "")).replace("\\", "/") != normalized:
            continue
        if item.get("status") != STATUS_ACTIVE:
            continue
        item["last_used_at"] = now
        lifecycle = str(item.get("lifecycle") or LIFECYCLE_SESSION)
        if lifecycle == LIFECYCLE_DELIVERED and item.get("weixin_sent_at"):
            changed = True
        else:
            item["expires_at"] = _expires_at_for(lifecycle, settings=cfg, now=now)
            changed = True
        break
    if changed:
        _save_index(items, cfg)


def _weixin_sent_expires_at(*, now: float | None = None) -> float:
    ts = now if now is not None else time.time()
    return ts + DEFAULT_WEIXIN_DELIVERED_TTL_DAYS * 86400


def _should_skip_gc_item(item: dict[str, Any]) -> bool:
    lifecycle = item.get("lifecycle")
    if lifecycle == LIFECYCLE_PINNED:
        return True
    if lifecycle == LIFECYCLE_DELIVERED and not item.get("weixin_sent_at"):
        return True
    return False


def mark_weixin_sent(path: str | Path, *, settings: UserSettings | None = None) -> None:
    """微信附件发送成功后登记，7 天后由 run_gc 移入 trash。"""
    cfg = settings or load_settings()
    target = Path(path).expanduser()
    if not target.is_file():
        return
    workspace = Path(resolved_workspace(cfg)).resolve()
    try:
        target.resolve().relative_to(workspace)
    except ValueError:
        return

    normalized = normalize_path(target, settings=cfg)
    now = time.time()
    expires = _weixin_sent_expires_at(now=now)
    items = _load_index(cfg)
    for item in items:
        if str(item.get("path", "")).replace("\\", "/") != normalized:
            continue
        if item.get("status") != STATUS_ACTIVE:
            return
        item["weixin_sent_at"] = now
        item["lifecycle"] = LIFECYCLE_DELIVERED
        item["expires_at"] = expires
        item["last_used_at"] = now
        _save_index(items, cfg)
        return

    suffix = target.suffix.lower()
    kind = "image" if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else "document"
    items.append(
        {
            "id": uuid.uuid4().hex[:12],
            "path": normalized,
            "kind": kind,
            "lifecycle": LIFECYCLE_DELIVERED,
            "session_id": "",
            "tool": "weixin_send",
            "created_at": now,
            "last_used_at": now,
            "expires_at": expires,
            "weixin_sent_at": now,
            "status": STATUS_ACTIVE,
            "trashed_at": None,
            "size_bytes": _file_size(target.resolve()),
        }
    )
    _save_index(items, cfg)


def mark_script_consumed(path: str | Path, *, settings: UserSettings | None = None) -> None:
    """一次性脚本执行后缩短保留时间。"""
    cfg = settings or load_settings()
    normalized = normalize_path(path, settings=cfg)
    now = time.time()
    items = _load_index(cfg)
    for item in items:
        if str(item.get("path", "")).replace("\\", "/") != normalized:
            continue
        if item.get("status") != STATUS_ACTIVE:
            return
        item["last_used_at"] = now
        item["lifecycle"] = LIFECYCLE_SCRATCH
        item["expires_at"] = now + SCRIPT_POST_RUN_GRACE_HOURS * 3600
        _save_index(items, cfg)
        return


def maybe_register_written_file(path: str | Path, *, tool: str = "write_text_file") -> None:
    cfg = load_settings()
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return
    if is_artifacts_path(target, settings=cfg):
        register_artifact(
            target,
            kind="script" if target.suffix.lower() == ".py" else "data",
            lifecycle=LIFECYCLE_SCRATCH,
            tool=tool,
            settings=cfg,
        )


def register_generated_image(path: str | Path, *, tool: str = "generate_image") -> None:
    register_artifact(
        path,
        kind="image",
        lifecycle=LIFECYCLE_DELIVERED,
        tool=tool,
    )


def register_pasted_image(path: str | Path) -> None:
    register_artifact(
        path,
        kind="image",
        lifecycle=LIFECYCLE_SESSION,
        tool="paste_image",
    )


def _extract_paths_from_session(session_id: str) -> set[str]:
    from friday.sessions import get_session, session_display_messages

    session = get_session(session_id)
    if session is None:
        return set()
    paths: set[str] = set()
    for msg in session_display_messages(session):
        content = str(msg.get("content") or "")
        for img in msg.get("generated_images") or []:
            p = str(img.get("path") if isinstance(img, dict) else img or "").strip()
            if p:
                paths.add(p.replace("\\", "/"))
        for token in content.replace("\\", "/").split():
            if token.startswith("/") or (len(token) > 2 and token[1] == ":"):
                if any(token.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".py", ".csv")):
                    paths.add(token.rstrip(".,;:)\"'"))
    for msg in session.agent_messages or []:
        if msg.get("role") != "tool":
            continue
        text = str(msg.get("content") or "")
        if "已生成图片并保存：" in text:
            line = text.split("已生成图片并保存：", 1)[1].splitlines()[0].strip()
            if line:
                paths.add(line.replace("\\", "/"))
    return paths


def sync_session_references(session_id: str, *, settings: UserSettings | None = None) -> int:
    """将会话仍引用的文件标记为 session 并刷新 TTL。"""
    cfg = settings or load_settings()
    refs = _extract_paths_from_session(session_id)
    if not refs:
        return 0
    items = _load_index(cfg)
    now = time.time()
    touched = 0
    for item in items:
        path = str(item.get("path", "")).replace("\\", "/")
        if path not in refs or item.get("status") != STATUS_ACTIVE:
            continue
        if item.get("lifecycle") == LIFECYCLE_SCRATCH:
            item["lifecycle"] = LIFECYCLE_SESSION
        item["session_id"] = session_id
        item["last_used_at"] = now
        lifecycle = str(item.get("lifecycle") or LIFECYCLE_SESSION)
        if not (lifecycle == LIFECYCLE_DELIVERED and item.get("weixin_sent_at")):
            item["expires_at"] = _expires_at_for(lifecycle, settings=cfg, now=now)
        touched += 1
    if touched:
        _save_index(items, cfg)
    return touched


def on_session_deleted(session_id: str, *, settings: UserSettings | None = None) -> int:
    """会话删除后缩短关联临时文件保留期。"""
    cfg = settings or load_settings()
    ttl = _ttl_settings(cfg)
    now = time.time()
    grace = now + ttl["session_delete_grace_days"] * 86400
    items = _load_index(cfg)
    updated = 0
    for item in items:
        if str(item.get("session_id") or "") != session_id:
            continue
        if item.get("status") != STATUS_ACTIVE:
            continue
        if item.get("lifecycle") in {LIFECYCLE_DELIVERED, LIFECYCLE_PINNED}:
            continue
        exp = item.get("expires_at")
        item["expires_at"] = min(float(exp), grace) if isinstance(exp, (int, float)) else grace
        updated += 1
    if updated:
        _save_index(items, cfg)
    return updated


def _move_file_to_trash(path: Path, *, settings: UserSettings) -> Path | None:
    if not path.is_file():
        return None
    root = trash_dir(settings)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = root / f"{stamp}_{path.name}"
    counter = 0
    while dest.exists():
        counter += 1
        dest = root / f"{stamp}_{counter}_{path.name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest))
    return dest


def _purge_trash_file(path: Path) -> bool:
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
            return True
    except OSError:
        _log.warning("删除 trash 文件失败 | path=%s", path)
    return False


def run_gc(*, settings: UserSettings | None = None, dry_run: bool = False) -> dict[str, Any]:
    """按 TTL 将过期文件移入 trash，并清空超期 trash。"""
    cfg = settings or load_settings()
    if not getattr(cfg, "artifact_auto_gc_enabled", True):
        return {"ok": True, "skipped": True, "reason": "auto_gc_disabled"}

    ttl = _ttl_settings(cfg)
    now = time.time()
    items = _load_index(cfg)
    trashed = 0
    purged = 0
    bytes_freed = 0

    for item in items:
        if item.get("status") != STATUS_ACTIVE:
            continue
        if _should_skip_gc_item(item):
            continue
        exp = item.get("expires_at")
        if not isinstance(exp, (int, float)) or exp > now:
            continue
        src = Path(str(item.get("path", "")).replace("/", "\\"))
        if dry_run:
            trashed += 1
            bytes_freed += int(item.get("size_bytes") or 0)
            continue
        if src.is_file():
            dest = _move_file_to_trash(src, settings=cfg)
            if dest:
                item["path"] = normalize_path(dest, settings=cfg)
                item["status"] = STATUS_TRASHED
                item["trashed_at"] = now
                trashed += 1
        else:
            item["status"] = STATUS_TRASHED
            item["trashed_at"] = now
            trashed += 1

    trash_cutoff = now - ttl["trash_days"] * 86400
    for item in items:
        if item.get("status") != STATUS_TRASHED:
            continue
        trashed_at = item.get("trashed_at")
        if not isinstance(trashed_at, (int, float)) or trashed_at > trash_cutoff:
            continue
        src = Path(str(item.get("path", "")).replace("/", "\\"))
        size = int(item.get("size_bytes") or 0)
        if dry_run:
            purged += 1
            bytes_freed += size
            item["_purge"] = True
            continue
        if _purge_trash_file(src):
            bytes_freed += size
        item["_purge"] = True
        purged += 1

    if not dry_run:
        items = [item for item in items if not item.pop("_purge", False)]
        _save_index(items, cfg)
        _purge_orphan_trash_files(trash_cutoff, settings=cfg)

    return {
        "ok": True,
        "dry_run": dry_run,
        "trashed": trashed,
        "purged": purged,
        "bytes_freed": bytes_freed,
    }


def _purge_orphan_trash_files(cutoff_ts: float, *, settings: UserSettings) -> None:
    root = trash_dir(settings)
    for path in root.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime <= cutoff_ts:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def finalize_agent_turn(session_id: str, *, settings: UserSettings | None = None) -> dict[str, Any]:
    cfg = settings or load_settings()
    sync_session_references(session_id, settings=cfg)
    return run_gc(settings=cfg)


def storage_summary(*, settings: UserSettings | None = None) -> dict[str, Any]:
    cfg = settings or load_settings()
    ensure_friday_dirs(cfg)
    items = _load_index(cfg)
    active = [i for i in items if i.get("status") == STATUS_ACTIVE]
    trashed = [i for i in items if i.get("status") == STATUS_TRASHED]

    def _sum_bytes(rows: list[dict[str, Any]]) -> int:
        total = 0
        for row in rows:
            path = Path(str(row.get("path", "")).replace("/", "\\"))
            if path.is_file():
                total += _file_size(path)
            else:
                total += int(row.get("size_bytes") or 0)
        return total

    def _dir_size(path: Path) -> int:
        if not path.is_dir():
            return 0
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                except OSError:
                    pass
        return total

    root = friday_root(cfg)
    return {
        "friday_root": str(root).replace("\\", "/"),
        "artifacts_dir": str(artifacts_dir(cfg)).replace("\\", "/"),
        "trash_dir": str(trash_dir(cfg)).replace("\\", "/"),
        "indexed_active_count": len(active),
        "indexed_trashed_count": len(trashed),
        "indexed_active_bytes": _sum_bytes(active),
        "indexed_trashed_bytes": _sum_bytes(trashed),
        "artifacts_dir_bytes": _dir_size(artifacts_dir(cfg)),
        "trash_dir_bytes": _dir_size(trash_dir(cfg)),
        "scratch_ttl_hours": _ttl_settings(cfg)["scratch_hours"],
        "session_ttl_days": _ttl_settings(cfg)["session_days"],
        "trash_ttl_days": _ttl_settings(cfg)["trash_days"],
    }
