"""API 凭据独立存储 —— 与 settings.json 分离，避免配置迁移/修复时误删 Key。

存储位置：%APPDATA%/Friday/credentials/
  - .fernet_key        加密密钥（与 api_secrets.json 配对）
  - api_secrets.json   加密后的 API Key / profiles / 自定义端点
  - api_secrets.json.bak  每次保存前的备份
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("credentials")

SECRET_SCALAR_KEYS = ("api_key", "vision_api_key", "image_gen_api_key")
SECRET_PROFILE_KEYS = ("llm_profiles", "vision_profiles", "image_gen_profiles")
SECRET_ENDPOINT_KEYS = ("llm_custom_endpoints", "vision_custom_endpoints", "image_gen_custom_endpoints")
ALL_SECRET_KEYS = SECRET_SCALAR_KEYS + SECRET_PROFILE_KEYS + SECRET_ENDPOINT_KEYS

_SECRETS_FILE = "api_secrets.json"
_FERNET_FILE = ".fernet_key"


def credentials_dir() -> Path:
    return get_appdata_dir() / "credentials"


def secrets_path() -> Path:
    return credentials_dir() / _SECRETS_FILE


def fernet_key_path() -> Path:
    return credentials_dir() / _FERNET_FILE


def ensure_credentials_dir() -> Path:
    path = credentials_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_fernet_key_if_needed() -> None:
    """将根目录 .fernet_key 迁移到 credentials/（仅复制，不删除旧文件）。"""
    ensure_credentials_dir()
    cred_key = fernet_key_path()
    if cred_key.is_file():
        return
    legacy = get_appdata_dir() / _FERNET_FILE
    if not legacy.is_file():
        return
    try:
        shutil.copy2(legacy, cred_key)
        if os.name == "nt":
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(str(cred_key), 2)
        _log.info("已迁移 .fernet_key 到 credentials/ | path=%s", cred_key)
    except OSError as exc:
        _log.warning("迁移 .fernet_key 失败 | err=%s", exc)


def migrate_secrets_from_settings_json_if_needed() -> bool:
    """首次运行：从 settings.json 提取加密字段到 credentials/api_secrets.json。"""
    dest = secrets_path()
    if dest.is_file():
        return False
    settings_path = get_appdata_dir() / "settings.json"
    if not settings_path.is_file():
        return False
    raw = load_json(settings_path)
    if not isinstance(raw, dict):
        return False
    payload = {k: raw[k] for k in ALL_SECRET_KEYS if k in raw and raw[k]}
    if not payload:
        return False
    ensure_credentials_dir()
    atomic_write_json(dest, payload)
    _log.info("已从 settings.json 迁移 API 凭据 | path=%s keys=%d", dest, len(payload))
    return True


def ensure_credentials_migrated() -> None:
    migrate_fernet_key_if_needed()
    migrate_secrets_from_settings_json_if_needed()


def _extract_encrypted_payload(settings_dict: dict[str, Any]) -> dict[str, Any]:
    from friday.storage import (
        _encrypt_custom_endpoints,
        _encrypt_key,
        _encrypt_llm_profiles,
        _encrypt_provider_profiles,
    )

    out: dict[str, Any] = {}
    for key in SECRET_SCALAR_KEYS:
        val = settings_dict.get(key, "")
        if val:
            out[key] = _encrypt_key(str(val))
    if settings_dict.get("llm_profiles"):
        out["llm_profiles"] = _encrypt_llm_profiles(settings_dict["llm_profiles"])
    if settings_dict.get("vision_profiles"):
        out["vision_profiles"] = _encrypt_provider_profiles(
            settings_dict["vision_profiles"], category="vision"
        )
    if settings_dict.get("image_gen_profiles"):
        out["image_gen_profiles"] = _encrypt_provider_profiles(
            settings_dict["image_gen_profiles"], category="image_gen"
        )
    for key in SECRET_ENDPOINT_KEYS:
        items = settings_dict.get(key) or []
        if items:
            out[key] = _encrypt_custom_endpoints(items)
    return out


def _decrypt_payload(raw: dict[str, Any]) -> dict[str, Any]:
    from friday.storage import (
        _decrypt_custom_endpoints,
        _decrypt_key,
        _decrypt_llm_profiles,
        _decrypt_provider_profiles,
    )

    out: dict[str, Any] = {}
    for key in SECRET_SCALAR_KEYS:
        if key in raw:
            out[key] = _decrypt_key(str(raw.get(key) or ""))
    if "llm_profiles" in raw:
        out["llm_profiles"] = _decrypt_llm_profiles(raw.get("llm_profiles") or {})
    if "vision_profiles" in raw:
        out["vision_profiles"] = _decrypt_provider_profiles(
            raw.get("vision_profiles") or {}, category="vision"
        )
    if "image_gen_profiles" in raw:
        out["image_gen_profiles"] = _decrypt_provider_profiles(
            raw.get("image_gen_profiles") or {}, category="image_gen"
        )
    for key in SECRET_ENDPOINT_KEYS:
        if key in raw:
            out[key] = _decrypt_custom_endpoints(raw.get(key) or [])
    return out


def _merge_profile_maps(incoming: Any, stored: Any) -> dict[str, Any]:
    """合并 profile：incoming 中空 api_key 保留 stored 原值；stored 独有 id 保留。"""
    merged: dict[str, Any] = {}
    if isinstance(incoming, dict):
        for pid, entry in incoming.items():
            if isinstance(entry, dict):
                merged[str(pid)] = dict(entry)
    if not isinstance(stored, dict):
        return merged
    for pid, old_entry in stored.items():
        if not isinstance(old_entry, dict):
            continue
        key = str(pid or "").strip()
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(old_entry)
            continue
        new_entry = merged[key]
        if not str(new_entry.get("api_key") or "").strip():
            old_key = old_entry.get("api_key", "")
            if isinstance(old_key, str) and old_key.strip():
                merged[key] = {**new_entry, "api_key": old_key}
    return merged


def _merge_endpoint_lists(incoming: Any, stored: Any) -> list:
    from friday.custom_endpoints import normalize_endpoints

    new_norm = normalize_endpoints(incoming or [])
    old_norm = normalize_endpoints(stored or [])
    old_by_id = {e.get("id"): e for e in old_norm if e.get("id")}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in new_norm:
        item = dict(entry)
        eid = str(item.get("id") or "")
        if not str(item.get("api_key") or "").strip() and eid in old_by_id:
            old_key = old_by_id[eid].get("api_key", "")
            if old_key:
                item["api_key"] = old_key
        out.append(item)
        if eid:
            seen.add(eid)
    for eid, old_entry in old_by_id.items():
        if eid not in seen:
            out.append(dict(old_entry))
    return out


def _merge_preserve_encrypted_profiles(
    new_profiles: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    return _merge_profile_maps(new_profiles, existing)


def _merge_preserve_encrypted_endpoints(new_list: list, existing: list) -> list:
    return _merge_endpoint_lists(new_list, existing)


def _merge_preserve_encrypted(new_enc: dict[str, Any], existing_enc: dict[str, Any]) -> dict[str, Any]:
    merged = dict(new_enc)
    for key in SECRET_SCALAR_KEYS:
        new_val = merged.get(key, "")
        if isinstance(new_val, str) and not new_val.strip() and existing_enc.get(key):
            merged[key] = existing_enc[key]
    for key in SECRET_PROFILE_KEYS:
        if key in merged or key in existing_enc:
            merged[key] = _merge_preserve_encrypted_profiles(
                merged.get(key) or {},
                existing_enc.get(key) or {},
            )
    for key in SECRET_ENDPOINT_KEYS:
        if key in merged or key in existing_enc:
            merged[key] = _merge_preserve_encrypted_endpoints(
                merged.get(key) or [],
                existing_enc.get(key) or [],
            )
    return merged


def save_api_secrets(settings_dict: dict[str, Any]) -> None:
    """保存 API 凭据；空 Key 不覆盖已有加密值。"""
    ensure_credentials_migrated()
    dest = secrets_path()
    existing: dict[str, Any] = {}
    if dest.is_file():
        raw = load_json(dest)
        if isinstance(raw, dict):
            existing = raw
    new_enc = _extract_encrypted_payload(settings_dict)
    merged = _merge_preserve_encrypted(new_enc, existing)
    if not merged and not existing:
        return
    ensure_credentials_dir()
    if dest.is_file():
        bak = dest.with_suffix(".json.bak")
        try:
            shutil.copy2(dest, bak)
        except OSError:
            pass
    atomic_write_json(dest, merged)
    _log.info("API 凭据已保存 | path=%s", dest)


def load_api_secrets() -> dict[str, Any]:
    """读取并解密 credentials/api_secrets.json。"""
    ensure_credentials_migrated()
    path = secrets_path()
    if not path.is_file():
        return {}
    raw = load_json(path)
    if not isinstance(raw, dict):
        return {}
    return _decrypt_payload(raw)


def load_encrypted_secrets_raw() -> dict[str, Any]:
    """读取加密原始数据（不解密），供 settings.json 同步写入。"""
    path = secrets_path()
    if not path.is_file():
        return {}
    raw = load_json(path)
    return raw if isinstance(raw, dict) else {}


def _fill_empty_profile_keys(incoming: Any, stored: Any) -> dict[str, dict[str, str]]:
    merged = _merge_profile_maps(incoming, stored)
    return {k: dict(v) if isinstance(v, dict) else v for k, v in merged.items()}


def _fill_empty_endpoint_keys(incoming: Any, stored: Any) -> list:
    return _merge_endpoint_lists(incoming, stored)


def apply_secrets_to_settings_data(
    data: dict[str, Any],
    secrets: dict[str, Any],
    *,
    fill_empty_only: bool = False,
    profiles_fill_empty_only: bool = False,
) -> dict[str, Any]:
    """凭据库中的非空值覆盖 settings 数据；fill_empty_only 时仅回填空字段。"""
    merged = dict(data)
    for key in SECRET_SCALAR_KEYS:
        val = str(secrets.get(key) or "").strip()
        if not val:
            continue
        if fill_empty_only and str(merged.get(key) or "").strip():
            continue
        merged[key] = val
    for key in SECRET_PROFILE_KEYS:
        stored = secrets.get(key)
        if not stored:
            continue
        if fill_empty_only or profiles_fill_empty_only:
            merged[key] = _fill_empty_profile_keys(merged.get(key), stored)
            continue
        merged[key] = stored
    for key in SECRET_ENDPOINT_KEYS:
        stored = secrets.get(key)
        if not stored:
            continue
        if fill_empty_only:
            merged[key] = _fill_empty_endpoint_keys(merged.get(key), stored)
            continue
        merged[key] = stored
    return merged


def preserve_empty_secrets_in_settings(settings_dict: dict[str, Any]) -> dict[str, Any]:
    """保存前：空 Key 从凭据库回填，避免误覆盖。"""
    secrets = load_api_secrets()
    if not secrets:
        return settings_dict
    return apply_secrets_to_settings_data(settings_dict, secrets, fill_empty_only=True)


def copy_credentials_from_legacy_dir(legacy_dir: Path) -> bool:
    """从旧 AppData 目录复制 credentials/ 或 settings+fernet。"""
    import shutil

    dest_dir = ensure_credentials_dir()
    legacy_cred = legacy_dir / "credentials"
    copied = False

    if legacy_cred.is_dir():
        for name in (_FERNET_FILE, _SECRETS_FILE, "api_secrets.json.bak"):
            src = legacy_cred / name
            if src.is_file():
                shutil.copy2(src, dest_dir / name)
                copied = True

    legacy_fernet = legacy_dir / _FERNET_FILE
    if legacy_fernet.is_file() and not fernet_key_path().is_file():
        shutil.copy2(legacy_fernet, fernet_key_path())
        copied = True

    if not secrets_path().is_file():
        legacy_settings = legacy_dir / "settings.json"
        if legacy_settings.is_file():
            raw = load_json(legacy_settings)
            if isinstance(raw, dict):
                payload = {k: raw[k] for k in ALL_SECRET_KEYS if k in raw and raw[k]}
                if payload:
                    atomic_write_json(secrets_path(), payload)
                    copied = True
    return copied
