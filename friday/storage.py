"""用户设置持久化 —— 支持 AES 加密存储 API Key。

加密策略：
- Fernet 密钥存储在 %APPDATA%/Friday/.fernet_key
- api_key 落盘前加密，读取时解密
- 旧版明文 Key 首次读取时自动迁移为加密存储
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import default_workspace, default_workspace_path, get_appdata_dir

_log = get_logger("storage")

# ── 加密工具 ──

_ENCRYPTION_PREFIX = "fernet:"


def _fernet_key_path() -> Path:
    return get_appdata_dir() / ".fernet_key"


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
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    workspace: str = ""
    theme: str = "dark"
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
    acknowledged_changelog_version: str = ""

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
        return bool(key and key != "sk-your-key-here")

    def masked_key(self) -> str:
        key = self.api_key.strip()
        if len(key) <= 8:
            return "未设置" if not key else "****"
        return f"{key[:4]}...{key[-4:]}"


def _settings_path() -> Path:
    return get_appdata_dir() / "settings.json"


def save_settings(settings: UserSettings) -> None:
    """保存设置到 %APPDATA%/Friday/settings.json，api_key 加密后落盘。"""
    from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION

    data = asdict(settings)
    data["api_key"] = _encrypt_key(data["api_key"])
    data["vision_api_key"] = _encrypt_key(data.get("vision_api_key", ""))
    data["image_gen_api_key"] = _encrypt_key(data.get("image_gen_api_key", ""))
    data["settings_schema_version"] = CURRENT_SETTINGS_SCHEMA_VERSION
    path = _settings_path()
    atomic_write_json(path, data)
    _log.info("设置已保存 | path=%s", path)


def load_settings() -> UserSettings:
    """从 %APPDATA%/Friday/settings.json 加载设置，api_key 自动解密。"""
    from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION

    path = _settings_path()
    if not path.exists():
        _log.info("设置文件不存在，使用默认设置 | path=%s", path)
        return UserSettings()
    data = load_json(path)
    if not isinstance(data, dict):
        _log.warning("设置文件无效，使用默认设置 | path=%s", path)
        return UserSettings()
    schema = int(data.pop("settings_schema_version", 0) or 0)
    if "api_key" in data:
        data["api_key"] = _decrypt_key(data["api_key"])
    if "vision_api_key" in data:
        data["vision_api_key"] = _decrypt_key(data["vision_api_key"])
    if "image_gen_api_key" in data:
        data["image_gen_api_key"] = _decrypt_key(data["image_gen_api_key"])
    settings = UserSettings.from_dict(data)
    if schema < CURRENT_SETTINGS_SCHEMA_VERSION:
        settings = _migrate_settings_schema(settings, schema)
    return settings


def _migrate_settings_schema(settings: UserSettings, old_schema: int) -> UserSettings:
    """settings.json 结构升级（保留用户数据）。"""
    from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION

    merged = asdict(settings)
    if old_schema < 1:
        merged.setdefault("allow_read_user_folders", True)
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
    """合并前端传过来的部分设置更新；空 Key 保留原值。"""
    merged = current.merge(payload)
    if "api_key" in payload and not str(payload.get("api_key", "")).strip():
        merged = merged.merge({"api_key": current.api_key})
    if "vision_api_key" in payload and not str(payload.get("vision_api_key", "")).strip():
        merged = merged.merge({"vision_api_key": current.vision_api_key})
    if "image_gen_api_key" in payload and not str(payload.get("image_gen_api_key", "")).strip():
        merged = merged.merge({"image_gen_api_key": current.image_gen_api_key})
    return merged
