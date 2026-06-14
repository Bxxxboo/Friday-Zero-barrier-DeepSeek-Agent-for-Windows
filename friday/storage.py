"""用户设置持久化 —— 支持 AES 加密存储 API Key。

加密策略：
- Fernet 密钥与 API Key 优先存储在 %APPDATA%/Friday/credentials/
- settings.json 仍保留加密副本（兼容旧版）；凭据库为权威来源
- 空 Key 保存时不覆盖已有加密值
- 旧版根目录 .fernet_key 首次读取时自动迁移
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import default_workspace, default_workspace_path, get_appdata_dir

_log = get_logger("storage")

# ── 加密工具 ──

_ENCRYPTION_PREFIX = "fernet:"


def _fernet_key_path() -> Path:
    from friday.credentials_store import ensure_credentials_migrated, fernet_key_path

    ensure_credentials_migrated()
    return fernet_key_path()


def _get_fernet():
    """获取或创建 Fernet 实例。"""
    from cryptography.fernet import Fernet

    key_path = _fernet_key_path()
    if key_path.exists():
        key = key_path.read_bytes()
        return Fernet(key)

    # 首次运行：生成密钥
    key = Fernet.generate_key()
    try:
        key_path.write_bytes(key)
        # Windows: 尝试限制权限
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(key_path), 2)  # FILE_ATTRIBUTE_HIDDEN
    except OSError:
        pass  # 非 Windows 或权限不足，静默跳过
    return Fernet(key)


def _encrypt_key(plaintext: str) -> str:
    """加密 API Key。空字符串不加密。"""
    if not plaintext:
        return ""
    try:
        f = _get_fernet()
        token = f.encrypt(plaintext.encode("utf-8"))
        return _ENCRYPTION_PREFIX + token.decode("utf-8")
    except Exception:
        _log.exception("加密 API Key 失败，回退为明文存储")
        return plaintext


def _decrypt_key(stored: str) -> str:
    """解密 API Key。明文或非 fernet 格式原样返回。"""
    if not stored:
        return ""
    if stored.startswith(_ENCRYPTION_PREFIX):
        try:
            f = _get_fernet()
            token = stored[len(_ENCRYPTION_PREFIX):].encode("utf-8")
            return f.decrypt(token).decode("utf-8")
        except Exception:
            _log.exception("解密 API Key 失败，返回空字符串")
            return ""
    return stored


# ── 设置模型 ──


@dataclass
class UserSettings:
    api_key: str = ""
    llm_provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    workspace: str = ""
    theme: str = "light"
    font_size: str = "medium"
    restrict_to_workspace: bool = True
    allow_read_user_folders: bool = True
    require_approval_writes: bool = True
    require_approval_exec: bool = True
    allow_write_files: bool = True
    allow_move_files: bool = True
    allow_organize: bool = True
    allow_create_documents: bool = True
    allow_powershell: bool = True
    allow_python: bool = True
    allow_web_browse: bool = True
    allow_downloads: bool = True
    require_trusted_downloads: bool = True
    auto_approve_scheduled_writes: bool = False
    approve_once_per_turn: bool = True
    interaction_mode: str = "agent"
    ui_language: str = "zh"
    vision_api_key: str = ""
    vision_provider: str = "ark"
    vision_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    vision_model: str = ""
    vision_enabled: bool = False
    image_gen_enabled: bool = False
    image_gen_provider: str = "openai_compat"
    image_gen_api_key: str = ""
    image_gen_base_url: str = "https://next.zhima.world"
    image_gen_model: str = ""
    image_gen_default_size: str = "1024x1024"
    image_gen_fallback_urls: str = ""
    image_gen_save_dir: str = ""
    weixin_bridge_enabled: bool = True
    weixin_task_progress_enabled: bool = True
    weixin_deliver_files_enabled: bool = True
    acknowledged_changelog_version: str = ""
    api_proxy: str = ""
    api_trust_env: bool = True
    llm_profiles: dict = field(default_factory=dict)
    vision_profiles: dict = field(default_factory=dict)
    image_gen_profiles: dict = field(default_factory=dict)
    llm_custom_endpoints: list = field(default_factory=list)
    llm_custom_active: str = ""
    vision_custom_endpoints: list = field(default_factory=list)
    vision_custom_active: str = ""
    image_gen_custom_endpoints: list = field(default_factory=list)
    image_gen_custom_active: str = ""
    onboarding_completed: bool = False
    artifact_scratch_ttl_hours: int = 24
    artifact_session_ttl_days: int = 30
    artifact_trash_ttl_days: int = 7
    artifact_session_delete_grace_days: int = 7
    artifact_auto_gc_enabled: bool = True
    context_smart_enabled: bool = True
    goal_verifier_enabled: bool = True
    dream_memory_enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "UserSettings":
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def merge(self, partial: dict) -> "UserSettings":
        merged = asdict(self)
        merged.update(partial)
        return UserSettings.from_dict(merged)

    @property
    def api_ready(self) -> bool:
        key = self.api_key.strip()
        if not key or key == "sk-your-key-here" or key.startswith("sk-test"):
            return False
        return True

    def masked_key(self) -> str:
        key = self.api_key.strip()
        if len(key) <= 8:
            return "未设置" if not key else "****"
        return f"{key[:4]}...{key[-4:]}"


def _settings_path() -> Path:
    return get_appdata_dir() / "settings.json"


def _encrypt_custom_endpoints(endpoints: list) -> list:
    from friday.custom_endpoints import normalize_endpoints

    out: list[dict[str, str]] = []
    for entry in normalize_endpoints(endpoints):
        item = dict(entry)
        if item.get("api_key"):
            item["api_key"] = _encrypt_key(item["api_key"])
        out.append(item)
    return out


def _decrypt_custom_endpoints(endpoints: list) -> list:
    from friday.custom_endpoints import normalize_endpoints

    out: list[dict[str, str]] = []
    for entry in normalize_endpoints(endpoints):
        item = dict(entry)
        if item.get("api_key"):
            item["api_key"] = _decrypt_key(item["api_key"])
        out.append(item)
    return out


def _encrypt_provider_profiles(profiles: dict, *, category: str) -> dict:
    from friday.category_profiles import normalize_category_profiles
    from friday.llm_profiles import normalize_profiles

    if category == "llm":
        entries = normalize_profiles(profiles)
    else:
        entries = normalize_category_profiles(UserSettings(), category, profiles)
    out: dict[str, dict[str, str]] = {}
    for pid, entry in entries.items():
        item = dict(entry)
        if item.get("api_key"):
            item["api_key"] = _encrypt_key(item["api_key"])
        out[pid] = item
    return out


def _decrypt_provider_profiles(profiles: dict, *, category: str) -> dict:
    from friday.category_profiles import normalize_category_profiles
    from friday.llm_profiles import normalize_profiles

    if category == "llm":
        entries = normalize_profiles(profiles)
    else:
        entries = normalize_category_profiles(UserSettings(), category, profiles)
    out: dict[str, dict[str, str]] = {}
    for pid, entry in entries.items():
        item = dict(entry)
        if item.get("api_key"):
            item["api_key"] = _decrypt_key(item["api_key"])
        out[pid] = item
    return out


def _encrypt_llm_profiles(profiles: dict) -> dict:
    return _encrypt_provider_profiles(profiles, category="llm")


def _decrypt_llm_profiles(profiles: dict) -> dict:
    return _decrypt_provider_profiles(profiles, category="llm")


def save_settings(settings: UserSettings) -> None:
    """保存设置到 settings.json；API 凭据写入 credentials/ 目录。"""
    from friday.credentials_store import (
        ALL_SECRET_KEYS,
        load_encrypted_secrets_raw,
        preserve_empty_secrets_in_settings,
        save_api_secrets,
    )
    from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION

    data = preserve_empty_secrets_in_settings(asdict(settings))
    save_api_secrets(data)

    encrypted_secrets = load_encrypted_secrets_raw()
    data["settings_schema_version"] = CURRENT_SETTINGS_SCHEMA_VERSION
    for key in ALL_SECRET_KEYS:
        if key in encrypted_secrets:
            data[key] = encrypted_secrets[key]
        elif key in ("api_key", "vision_api_key", "image_gen_api_key"):
            data[key] = _encrypt_key(str(data.get(key) or ""))
        elif key == "llm_profiles":
            data[key] = _encrypt_llm_profiles(data.get(key) or {})
        elif key == "vision_profiles":
            data[key] = _encrypt_provider_profiles(data.get(key) or {}, category="vision")
        elif key == "image_gen_profiles":
            data[key] = _encrypt_provider_profiles(data.get(key) or {}, category="image_gen")
        elif key in ("llm_custom_endpoints", "vision_custom_endpoints", "image_gen_custom_endpoints"):
            data[key] = _encrypt_custom_endpoints(data.get(key) or [])

    path = _settings_path()
    atomic_write_json(path, data)
    _log.info("设置已保存 | path=%s", path)


def load_settings() -> UserSettings:
    """加载设置；API 凭据优先从 credentials/ 读取。"""
    from friday.credentials_store import apply_secrets_to_settings_data, ensure_credentials_migrated, load_api_secrets
    from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION, try_migrate_legacy_appdata

    ensure_credentials_migrated()
    path = _settings_path()
    if not path.exists():
        try_migrate_legacy_appdata()
        ensure_credentials_migrated()
        path = _settings_path()
    secrets = load_api_secrets()
    if not path.exists():
        if secrets:
            settings = UserSettings.from_dict(apply_secrets_to_settings_data({}, secrets))
            _log.info("凭据库存在但 settings.json 缺失，已从 credentials/ 恢复 API 设置")
            return settings
        _log.info("设置文件不存在，使用默认设置 | path=%s", path)
        return UserSettings()
    data = load_json(path)
    if not isinstance(data, dict):
        _log.warning("设置文件无效，使用默认设置 | path=%s", path)
        if secrets:
            return UserSettings.from_dict(apply_secrets_to_settings_data({}, secrets))
        return UserSettings()
    schema = int(data.pop("settings_schema_version", 0) or 0)
    if "api_key" in data:
        data["api_key"] = _decrypt_key(data["api_key"])
    if "vision_api_key" in data:
        data["vision_api_key"] = _decrypt_key(data["vision_api_key"])
    if "image_gen_api_key" in data:
        data["image_gen_api_key"] = _decrypt_key(data["image_gen_api_key"])
    if "llm_profiles" in data:
        data["llm_profiles"] = _decrypt_llm_profiles(data.get("llm_profiles") or {})
    if "vision_profiles" in data:
        data["vision_profiles"] = _decrypt_provider_profiles(data.get("vision_profiles") or {}, category="vision")
    if "image_gen_profiles" in data:
        data["image_gen_profiles"] = _decrypt_provider_profiles(data.get("image_gen_profiles") or {}, category="image_gen")
    for key in ("llm_custom_endpoints", "vision_custom_endpoints", "image_gen_custom_endpoints"):
        if key in data:
            data[key] = _decrypt_custom_endpoints(data.get(key) or [])
    if secrets:
        data = apply_secrets_to_settings_data(data, secrets, profiles_fill_empty_only=True)
    settings = UserSettings.from_dict(data)
    if schema < CURRENT_SETTINGS_SCHEMA_VERSION:
        settings = _migrate_settings_schema(settings, schema)
    # 空字符串会覆盖 dataclass 默认值，导致 OpenAI SDK 报 Connection error
    fixes: dict[str, str] = {}
    if not str(settings.base_url or "").strip():
        fixes["base_url"] = UserSettings.base_url
    if not str(settings.model or "").strip():
        fixes["model"] = UserSettings.model
    if not str(settings.vision_base_url or "").strip():
        fixes["vision_base_url"] = UserSettings.vision_base_url
    if fixes:
        settings = settings.merge(fixes)
        save_settings(settings)
        _log.info("已修复空 base_url/model | base_url=%s model=%s", settings.base_url, settings.model)
    from friday.category_profiles import align_isolated_category_settings, repair_isolated_category_settings

    repaired = repair_isolated_category_settings(settings)
    if repaired != settings:
        save_settings(repaired)
        _log.info("已修复视觉/生图与服务商不匹配的配置")
        settings = repaired
    aligned_cat = align_isolated_category_settings(settings)
    if aligned_cat != settings:
        save_settings(aligned_cat)
        _log.info("已从 profile 回填视觉/生图活跃配置")
        settings = aligned_cat

    from friday.llm_profiles import active_provider_id, normalize_profiles, repair_llm_key_alignment, seed_profiles_from_active

    profiles = normalize_profiles(settings.llm_profiles)
    active = active_provider_id(settings)
    active_key = (profiles.get(active) or {}).get("api_key", "").strip()
    if settings.api_key.strip() and (active not in profiles or not active_key):
        seeded = seed_profiles_from_active(settings)
        if seeded.llm_profiles != settings.llm_profiles:
            save_settings(seeded)
            _log.info("已从当前 API Key 回填服务商配置记忆 | provider=%s", active)
            settings = seeded
    aligned = repair_llm_key_alignment(settings)
    if aligned.api_key != settings.api_key:
        save_settings(aligned)
        _log.info("已修复大模型 Key 与当前服务商 profile 不一致 | provider=%s", active)
        settings = aligned
    return settings


def _migrate_settings_schema(settings: UserSettings, old_schema: int) -> UserSettings:
    """settings.json 结构升级（保留用户数据）。"""
    from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION

    merged = asdict(settings)
    if old_schema < 1:
        merged.setdefault("allow_read_user_folders", True)
    if old_schema < 2:
        from friday.model_providers import infer_llm_provider, infer_vision_provider

        merged.setdefault("llm_provider", infer_llm_provider(settings))
        merged.setdefault("vision_provider", infer_vision_provider(settings))
    if old_schema < 3:
        from friday.llm_profiles import seed_profiles_from_active
        from friday.model_providers import infer_llm_provider

        merged["llm_provider"] = infer_llm_provider(settings)
        seeded = seed_profiles_from_active(
            UserSettings.from_dict({**merged, **{k: getattr(settings, k) for k in asdict(settings)}})
        )
        merged["llm_profiles"] = seeded.llm_profiles
    if old_schema < 4:
        from friday.custom_endpoints import seed_all_custom_endpoints
        from friday.llm_profiles import normalize_profiles

        base = UserSettings.from_dict({**merged, **{k: getattr(settings, k) for k in asdict(settings)}})
        migrated = seed_all_custom_endpoints(base)
        profiles = normalize_profiles(migrated.llm_profiles)
        custom_profile = profiles.pop("custom", None)
        if custom_profile and not migrated.llm_custom_endpoints:
            from friday.custom_endpoints import upsert_endpoint

            migrated = upsert_endpoint(
                migrated,
                "llm",
                name=str(custom_profile.get("model") or "默认配置"),
                api_key=custom_profile.get("api_key") or "",
                base_url=custom_profile.get("base_url") or "",
                model=custom_profile.get("model") or "",
                preserve_key_if_empty=False,
            )
            migrated = migrated.merge({"llm_profiles": profiles})
        merged.update(
            {
                "llm_custom_endpoints": migrated.llm_custom_endpoints,
                "llm_custom_active": migrated.llm_custom_active,
                "vision_custom_endpoints": migrated.vision_custom_endpoints,
                "vision_custom_active": migrated.vision_custom_active,
                "image_gen_custom_endpoints": migrated.image_gen_custom_endpoints,
                "image_gen_custom_active": migrated.image_gen_custom_active,
                "llm_profiles": migrated.llm_profiles,
            }
        )
    if old_schema < 5:
        from friday.custom_endpoints import get_active_id, provider_id_for_endpoint

        base = UserSettings.from_dict({**merged, **{k: getattr(settings, k) for k in asdict(settings)}})
        for cat, provider_field, active_field in (
            ("llm", "llm_provider", "llm_custom_active"),
            ("vision", "vision_provider", "vision_custom_active"),
            ("image_gen", "image_gen_provider", "image_gen_custom_active"),
        ):
            provider = str(getattr(base, provider_field, "") or "").strip()
            if provider == "custom":
                active = get_active_id(base, cat)
                if active:
                    merged[provider_field] = provider_id_for_endpoint(active)
                elif cat == "llm":
                    merged[provider_field] = "deepseek"
                elif cat == "vision":
                    merged[provider_field] = "ark"
                else:
                    merged[provider_field] = "openai_compat"
            elif provider.startswith("c:"):
                merged[provider_field] = provider
    if old_schema < 6:
        base = UserSettings.from_dict({**merged, **{k: getattr(settings, k) for k in asdict(settings)}})
        if base.onboarding_completed or base.api_ready or (base.workspace.strip() and base.api_key.strip()):
            merged["onboarding_completed"] = True
    if old_schema < 7:
        from friday.category_profiles import seed_category_profiles_from_active

        base = UserSettings.from_dict({**merged, **{k: getattr(settings, k) for k in asdict(settings)}})
        seeded = seed_category_profiles_from_active(base, "vision")
        seeded = seed_category_profiles_from_active(seeded, "image_gen")
        merged["vision_profiles"] = seeded.vision_profiles
        merged["image_gen_profiles"] = seeded.image_gen_profiles
    updated = UserSettings.from_dict(merged)
    save_settings(updated)
    _log.info("settings 已迁移 schema %d -> %d", old_schema, CURRENT_SETTINGS_SCHEMA_VERSION)
    return updated


def ensure_workspace(settings: UserSettings) -> str:
    """确保 workspace 目录存在，若为空或不可用则使用本机默认文件夹。"""
    from friday.portability import expand_config_path, validate_workspace_path

    raw = settings.workspace.strip()
    if raw:
        expanded = expand_config_path(raw, ensure_default_exists=True)
        ok, reason = validate_workspace_path(raw)
        if not ok:
            _log.warning("配置的 workspace 不可用 | path=%s reason=%s", raw, reason)
            path = default_workspace_path(ensure_exists=True)
            return _normalize(path)
        path = Path(expanded or raw).expanduser()
        if not path.is_dir():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                _log.warning("无法创建 workspace，改用默认目录 | path=%s err=%s", raw, exc)
                path = default_workspace_path(ensure_exists=True)
        return _normalize(path)
    path = default_workspace_path(ensure_exists=True)
    return _normalize(path)


def initialize_first_run() -> UserSettings:
    """首次启动：确保应用数据目录与默认操作文件夹就绪，并做跨机迁移自愈。"""
    from friday.portability import run_startup_portability_checks
    from friday.sessions import migrate_session_files

    get_appdata_dir()
    migrate_session_files()
    settings = load_settings()
    settings = run_startup_portability_checks(settings)
    if not settings.workspace.strip():
        workspace = _normalize(default_workspace_path(ensure_exists=True))
        settings = settings.merge({"workspace": workspace})
        save_settings(settings)
        _log.info("首次运行，已创建默认操作文件夹 | path=%s", workspace)
    else:
        workspace = ensure_workspace(settings)
        if workspace != settings.workspace.replace("\\", "/"):
            settings = settings.merge({"workspace": workspace})
            save_settings(settings)
    return load_settings()


def _normalize(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve()).replace("\\", "/")


def resolved_workspace(settings: UserSettings) -> str:
    """解析并规范化 workspace 路径。"""
    return ensure_workspace(settings)


def merge_settings(current: UserSettings, payload: dict) -> UserSettings:
    """合并前端传过来的部分设置更新；空 Key 保留原值，空 URL/模型回退默认值。"""
    from friday.category_profiles import merge_category_settings, persist_category_profile, repair_isolated_category_settings
    from friday.custom_endpoints import merge_custom_settings, persist_custom_on_save
    from friday.llm_profiles import merge_llm_settings, persist_active_profile

    custom = merge_custom_settings(current, payload)
    if custom is not None:
        return repair_isolated_category_settings(custom)

    switched = merge_llm_settings(current, payload)
    if switched is not None:
        return repair_isolated_category_settings(switched)

    for category in ("vision", "image_gen"):
        switched = merge_category_settings(current, payload, category)
        if switched is not None:
            return repair_isolated_category_settings(switched)

    merged = current.merge({k: v for k, v in payload.items() if k not in {
        "switch_llm_profile",
        "switch_custom_endpoint",
        "add_custom_endpoint",
        "delete_custom_endpoint",
        "switch_vision_profile",
        "switch_image_gen_profile",
        "custom_endpoint_category",
        "custom_endpoint_id",
        "custom_endpoint_name",
    }})
    if "api_key" in payload and not str(payload.get("api_key", "")).strip():
        merged = merged.merge({"api_key": current.api_key})
    if "vision_api_key" in payload and not str(payload.get("vision_api_key", "")).strip():
        merged = merged.merge({"vision_api_key": current.vision_api_key})
    if "vision_base_url" in payload and not str(payload.get("vision_base_url", "")).strip():
        merged = merged.merge({"vision_base_url": current.vision_base_url})
    if "vision_model" in payload and not str(payload.get("vision_model", "")).strip():
        merged = merged.merge({"vision_model": current.vision_model})
    if "image_gen_api_key" in payload and not str(payload.get("image_gen_api_key", "")).strip():
        merged = merged.merge({"image_gen_api_key": current.image_gen_api_key})
    if "image_gen_base_url" in payload and not str(payload.get("image_gen_base_url", "")).strip():
        merged = merged.merge({"image_gen_base_url": current.image_gen_base_url})
    if "image_gen_model" in payload and not str(payload.get("image_gen_model", "")).strip():
        merged = merged.merge({"image_gen_model": current.image_gen_model})
    if "image_gen_fallback_urls" in payload and not str(payload.get("image_gen_fallback_urls", "")).strip():
        merged = merged.merge({"image_gen_fallback_urls": current.image_gen_fallback_urls})
    if "base_url" in payload and not str(payload.get("base_url", "")).strip():
        merged = merged.merge({"base_url": UserSettings.base_url})
    if "model" in payload and not str(payload.get("model", "")).strip():
        merged = merged.merge({"model": UserSettings.model})
    if any(k in payload for k in ("api_key", "base_url", "model", "llm_provider")):
        merged = persist_active_profile(merged)
    if any(k in payload for k in ("vision_api_key", "vision_base_url", "vision_model", "vision_provider")):
        merged = persist_category_profile(merged, "vision")
    if any(
        k in payload
        for k in (
            "image_gen_api_key",
            "image_gen_base_url",
            "image_gen_model",
            "image_gen_provider",
            "image_gen_fallback_urls",
            "image_gen_default_size",
        )
    ):
        merged = persist_category_profile(merged, "image_gen")
    merged = persist_custom_on_save(merged, payload)
    return repair_isolated_category_settings(merged)
