"""跨设备 / 跨用户迁移时的路径与配置自愈。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from friday.io_utils import load_json
from friday.logging_config import get_logger
from friday.paths import default_workspace_path, get_appdata_dir
from friday.storage import UserSettings, _decrypt_key, _settings_path, load_settings, save_settings

_log = get_logger("portability")

_startup_notices: list[str] = []

CURRENT_SETTINGS_SCHEMA_VERSION = 7


def pop_startup_notices() -> list[str]:
    items = _startup_notices.copy()
    _startup_notices.clear()
    return items


def _remember_notice(text: str) -> None:
    text = (text or "").strip()
    if text and text not in _startup_notices:
        _startup_notices.append(text)


def _normalize_path(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve()).replace("\\", "/")


def expand_config_path(raw: str, *, ensure_default_exists: bool = False) -> str:
    """展开 workspace 等配置路径：支持 ~/、%VAR%、auto。"""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.lower() == "auto":
        return _normalize_path(default_workspace_path(ensure_exists=ensure_default_exists))
    expanded = os.path.expandvars(text)
    try:
        return _normalize_path(Path(expanded).expanduser())
    except (OSError, RuntimeError, ValueError):
        return expanded.replace("\\", "/")

def _current_username() -> str:
    return (os.getenv("USERNAME") or os.getenv("USER") or "").strip()


def path_belongs_to_current_user(path: Path) -> bool:
    """拒绝明显属于其他 Windows 用户目录的路径。"""
    try:
        resolved = path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False

    try:
        resolved.relative_to(Path.home().resolve())
        return True
    except ValueError:
        pass

    parts = resolved.parts
    for idx, part in enumerate(parts):
        if part.lower() != "users" or idx + 1 >= len(parts):
            continue
        owner = parts[idx + 1]
        current = _current_username()
        if current and owner.lower() != current.lower():
            return False
    return True


def drive_exists(path: Path) -> bool:
    if sys.platform != "win32":
        return True
    drive = path.drive
    if not drive:
        return True
    return Path(f"{drive}\\").exists()


def validate_workspace_path(raw: str) -> tuple[bool, str]:
    """判断 workspace 是否可在本机使用（不创建目录）。"""
    text = expand_config_path(raw)
    if not (raw or "").strip():
        return True, ""
    if not text:
        return False, "路径为空"
    try:
        path = Path(text)
        resolved = path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        return False, f"路径无效: {exc}"

    if not drive_exists(resolved):
        return False, f"盘符不存在: {resolved.drive}"

    if not path_belongs_to_current_user(resolved):
        return False, "路径指向其他用户目录，无法在本机使用"

    if resolved.is_dir():
        if os.access(resolved, os.W_OK):
            return True, ""
        return False, "目录不可写"

    parent = resolved.parent
    if not parent.exists():
        return False, "父目录不存在"
    if not os.access(parent, os.W_OK):
        return False, "无法在父目录创建工作区"
    return True, ""


def repair_workspace(settings: UserSettings) -> tuple[UserSettings, list[str]]:
    """无效 workspace 重置为本机默认 Documents/星期五。"""
    notices: list[str] = []
    raw = settings.workspace.strip()
    if not raw:
        return settings, notices

    ok, reason = validate_workspace_path(raw)
    if ok:
        return settings, notices

    default_ws = _normalize_path(default_workspace_path(ensure_exists=True))
    _log.warning("workspace 不可用，已重置 | old=%s reason=%s new=%s", raw, reason, default_ws)
    notices.append(
        f"默认操作文件夹来自其他电脑或已失效（{reason}），已重置为：{default_ws}"
    )
    updated = settings.merge({"workspace": default_ws})
    save_settings(updated)
    return updated, notices


def repair_image_gen_save_dir(settings: UserSettings) -> tuple[UserSettings, list[str]]:
    notices: list[str] = []
    raw = (settings.image_gen_save_dir or "").strip()
    if not raw:
        return settings, notices

    expanded = expand_config_path(raw)
    ok, reason = validate_workspace_path(raw)
    if ok and Path(expanded).is_dir():
        return settings, notices

    _log.warning("生图保存目录无效，已清空 | path=%s reason=%s", raw, reason)
    notices.append(f"生图保存目录无效（{reason}），已恢复为工作区内默认文件夹。")
    updated = settings.merge({"image_gen_save_dir": ""})
    save_settings(updated)
    return updated, notices


_LEGACY_APPDATA_FOLDERS: dict[str, list[str]] = {
    "Friday": ["Friday-Test"],
    "Friday-Test": ["Friday"],
}


def _decrypt_with_fernet_file(stored: str, fernet_path: Path) -> str:
    """用指定 .fernet_key 解密字段（不依赖当前 AppData 密钥）。"""
    if not stored or not isinstance(stored, str):
        return ""
    if not stored.startswith("fernet:"):
        return stored.strip()
    if not fernet_path.is_file():
        return ""
    try:
        from cryptography.fernet import Fernet

        f = Fernet(fernet_path.read_bytes())
        return f.decrypt(stored[len("fernet:"):].encode("utf-8")).decode("utf-8").strip()
    except Exception:
        return ""


def _settings_pair_usable(settings_path: Path, fernet_path: Path) -> bool:
    """settings.json / credentials 与 .fernet_key 能否正确解密至少一个 API Key。"""
    from friday.credentials_store import secrets_path

    cred_secrets = secrets_path()
    if cred_secrets.is_file() and fernet_path.is_file():
        data = load_json(cred_secrets)
        if isinstance(data, dict):
            candidates: list[str] = []
            for field in ("api_key", "vision_api_key", "image_gen_api_key"):
                stored = data.get(field, "")
                if isinstance(stored, str) and stored.strip():
                    candidates.append(stored)
            profiles = data.get("llm_profiles")
            if isinstance(profiles, dict):
                for entry in profiles.values():
                    if isinstance(entry, dict):
                        key = entry.get("api_key", "")
                        if isinstance(key, str) and key.strip():
                            candidates.append(key)
            if not candidates:
                return True
            for stored in candidates:
                if stored.startswith("fernet:"):
                    if _decrypt_with_fernet_file(stored, fernet_path):
                        return True
                elif stored.strip():
                    return True
            return False

    if not settings_path.is_file():
        return False
    data = load_json(settings_path)
    if not isinstance(data, dict):
        return False

    candidates: list[str] = []
    for field in ("api_key", "vision_api_key", "image_gen_api_key"):
        stored = data.get(field, "")
        if isinstance(stored, str) and stored.strip():
            candidates.append(stored)

    profiles = data.get("llm_profiles")
    if isinstance(profiles, dict):
        for entry in profiles.values():
            if isinstance(entry, dict):
                key = entry.get("api_key", "")
                if isinstance(key, str) and key.strip():
                    candidates.append(key)

    if not candidates:
        return True

    for stored in candidates:
        if stored.startswith("fernet:"):
            if _decrypt_with_fernet_file(stored, fernet_path):
                return True
        elif stored.strip():
            return True
    return False


def try_migrate_legacy_appdata() -> bool:
    """从旧版 AppData 目录（如 Friday-Test）迁移 settings + 凭据。"""
    import shutil

    from friday.credentials_store import copy_credentials_from_legacy_dir, fernet_key_path

    appdata = os.getenv("APPDATA")
    if not appdata:
        return False

    from friday.edition import appdata_folder_name

    current_name = appdata_folder_name()
    current_dir = Path(appdata) / current_name
    settings_path = current_dir / "settings.json"
    fernet_path = fernet_key_path()
    root_fernet = current_dir / ".fernet_key"
    check_fernet = fernet_path if fernet_path.is_file() else root_fernet

    if _settings_pair_usable(settings_path, check_fernet):
        return False

    for legacy_name in _LEGACY_APPDATA_FOLDERS.get(current_name, []):
        legacy_dir = Path(appdata) / legacy_name
        legacy_settings = legacy_dir / "settings.json"
        legacy_fernet = legacy_dir / ".fernet_key"
        legacy_cred_fernet = legacy_dir / "credentials" / ".fernet_key"
        legacy_check_fernet = legacy_cred_fernet if legacy_cred_fernet.is_file() else legacy_fernet
        if not _settings_pair_usable(legacy_settings, legacy_check_fernet):
            continue

        current_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_settings, settings_path)
        copy_credentials_from_legacy_dir(legacy_dir)
        if legacy_fernet.is_file() and not root_fernet.is_file():
            shutil.copy2(legacy_fernet, root_fernet)
        _log.info("已从旧数据目录迁移设置 | from=%s to=%s", legacy_dir, current_dir)
        _remember_notice(
            f"已从 {legacy_name} 自动迁移 API 设置（含 credentials/ 与 .fernet_key）。"
            " 更新后若 Key 曾丢失，通常是因为只拷贝了 settings.json 而未带上加密密钥。"
        )
        return True
    return False


def scan_encryption_migration_issues() -> list[str]:
    """settings / credentials 与 .fernet_key 未配对迁移时给出明确提示。"""
    from friday.credentials_store import credentials_dir, load_api_secrets, secrets_path

    notices: list[str] = []
    prefix = "fernet:"
    cred_dir = credentials_dir()
    fernet_path = cred_dir / ".fernet_key"
    if not fernet_path.is_file():
        fernet_path = get_appdata_dir() / ".fernet_key"

    secrets = load_api_secrets()
    labels = {
        "api_key": "大模型 API Key",
        "vision_api_key": "视觉 API Key",
        "image_gen_api_key": "生图 API Key",
    }

    cred_raw = load_json(secrets_path()) if secrets_path().is_file() else {}
    if not isinstance(cred_raw, dict):
        cred_raw = {}

    for field, label in labels.items():
        stored = cred_raw.get(field, "")
        if not isinstance(stored, str) or not stored.startswith(prefix):
            continue
        if not str(secrets.get(field) or "").strip():
            notices.append(
                f"{label} 无法解密。请重新在设置中填写，"
                f"或完整拷贝 {cred_dir} 文件夹（必须包含 .fernet_key）。"
            )

    profiles = cred_raw.get("llm_profiles")
    if isinstance(profiles, dict):
        decrypted_profiles = secrets.get("llm_profiles") or {}
        for provider_id, entry in profiles.items():
            if not isinstance(entry, dict):
                continue
            stored = entry.get("api_key", "")
            if not isinstance(stored, str) or not stored.startswith(prefix):
                continue
            dec_entry = decrypted_profiles.get(provider_id) if isinstance(decrypted_profiles, dict) else {}
            dec_key = dec_entry.get("api_key", "") if isinstance(dec_entry, dict) else ""
            if not str(dec_key).strip():
                notices.append(
                    f"服务商「{provider_id}」的 API Key 无法解密。"
                    f"请重新填写，或从备份恢复 credentials/ 目录。"
                )

    if notices:
        return notices

    path = _settings_path()
    if not path.is_file():
        return []

    data = load_json(path)
    if not isinstance(data, dict):
        return []

    for field, label in labels.items():
        stored = data.get(field, "")
        if not isinstance(stored, str) or not stored.startswith(prefix):
            continue
        if not _decrypt_key(stored).strip():
            notices.append(
                f"{label} 无法解密。请重新在设置中填写，"
                f"或完整拷贝 {cred_dir} 文件夹（必须包含 .fernet_key）。"
            )

    profiles = data.get("llm_profiles")
    if isinstance(profiles, dict):
        for provider_id, entry in profiles.items():
            if not isinstance(entry, dict):
                continue
            stored = entry.get("api_key", "")
            if not isinstance(stored, str) or not stored.startswith(prefix):
                continue
            if not _decrypt_with_fernet_file(stored, fernet_path):
                notices.append(
                    f"服务商「{provider_id}」的 API Key 无法解密。"
                    f"请重新填写，或从备份恢复 credentials/ 与 .fernet_key。"
                )
    return notices


def to_portable_path(path: str, workspace: str) -> str:
    """工作区内的绝对路径存为相对路径，便于整夹迁移。"""
    raw = (path or "").strip()
    if not raw:
        return raw
    try:
        target = Path(raw).expanduser().resolve()
        root = Path(workspace).expanduser().resolve()
        rel = target.relative_to(root)
        return rel.as_posix()
    except (ValueError, OSError, RuntimeError):
        return raw.replace("\\", "/")


def resolve_portable_path(path: str, workspace: str) -> Path:
    """解析相对或绝对路径为绝对 Path。"""
    raw = (path or "").strip()
    if not raw:
        raise ValueError("路径为空")
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    root = Path(workspace).expanduser().resolve()
    return (root / candidate).resolve()


def migrate_session_portable_paths(workspace: str) -> int:
    """将会话中的生图路径改为相对路径（可重复执行）。"""
    from friday.sessions import _parse_session_data, _save_session, _sessions_dir

    marker = get_appdata_dir() / ".session_paths_portable_v1"
    if marker.is_file():
        return 0

    root = workspace.replace("\\", "/")
    updated = 0
    for path in _sessions_dir().glob("*.json"):
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        session = _parse_session_data(data)
        if session is None:
            continue
        changed = False
        display = session.display_messages or []
        for msg in display:
            images = msg.get("generated_images")
            if not isinstance(images, list):
                continue
            new_images: list[dict[str, str]] = []
            for item in images:
                if not isinstance(item, dict):
                    continue
                old = str(item.get("path", "")).strip()
                if not old:
                    new_images.append(item)
                    continue
                portable = to_portable_path(old, root)
                if portable != old.replace("\\", "/"):
                    changed = True
                new_images.append({"path": portable})
            msg["generated_images"] = new_images
        if changed:
            session.display_messages = display
            _save_session(session)
            updated += 1
    if updated:
        _log.info("已迁移会话图片路径为相对路径 | count=%d", updated)
    try:
        marker.write_text(str(updated), encoding="utf-8")
    except OSError:
        pass
    return updated


def run_portability_audit(settings: UserSettings) -> list[dict[str, object]]:
    """返回可移植性自检项（供设置页展示）。"""
    from friday.plugins import audit_plugin_portability

    items: list[dict[str, object]] = []
    raw_ws = settings.workspace.strip()
    expanded = expand_config_path(raw_ws) if raw_ws else _normalize_path(default_workspace_path(ensure_exists=False))
    ok, reason = validate_workspace_path(raw_ws) if raw_ws else (True, "")
    items.append({
        "id": "workspace",
        "ok": ok,
        "label": "默认操作文件夹",
        "detail": reason or expanded or "使用本机默认路径",
    })

    enc_issues = scan_encryption_migration_issues()
    if enc_issues:
        for idx, note in enumerate(enc_issues):
            items.append({
                "id": f"encryption-{idx}",
                "ok": False,
                "label": "API Key 加密",
                "detail": note,
            })
    else:
        items.append({
            "id": "encryption",
            "ok": True,
            "label": "API Key 加密",
            "detail": "credentials/ 与 .fernet_key 配对正常",
        })

    items.extend(audit_plugin_portability())

    try:
        from friday.python_env import _venv_is_stale, agent_env_dir

        workspace = expanded or _normalize_path(default_workspace_path(ensure_exists=True))
        env_dir = agent_env_dir(workspace)
        if env_dir.is_dir() and _venv_is_stale(env_dir):
            items.append({
                "id": "python-venv",
                "ok": False,
                "label": "Agent Python 环境",
                "detail": "虚拟环境来自其他电脑或已损坏，请在设置中重新初始化",
            })
        elif env_dir.is_dir():
            items.append({
                "id": "python-venv",
                "ok": True,
                "label": "Agent Python 环境",
                "detail": str(env_dir),
            })
    except Exception:
        pass

    return items


def run_startup_portability_checks(settings: UserSettings) -> UserSettings:
    """启动时自愈配置并记录需展示给用户的提示。"""
    from friday.plugins import migrate_installed_plugin_manifests

    if try_migrate_legacy_appdata():
        settings = load_settings()

    migrated = migrate_installed_plugin_manifests()
    if migrated:
        _log.info("已迁移 %d 个插件 manifest 为可移植格式", migrated)

    settings, ws_notes = repair_workspace(settings)
    for note in ws_notes:
        _remember_notice(note)

    settings, img_notes = repair_image_gen_save_dir(settings)
    for note in img_notes:
        _remember_notice(note)

    for note in scan_encryption_migration_issues():
        _remember_notice(note)

    workspace = settings.workspace.strip() or _normalize_path(default_workspace_path(ensure_exists=True))
    migrate_session_portable_paths(workspace)
    return settings
