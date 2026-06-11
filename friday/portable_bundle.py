"""可移植配置包导出 / 导入（zip）。"""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("portable_bundle")

BUNDLE_VERSION = 1
_CONFIG_FILES = ("settings.json", "skills.json", "rules.json", "plugins.json", "mcp_servers.json")


def _bundle_info() -> dict[str, Any]:
    from friday.version import __version__

    return {
        "bundle_version": BUNDLE_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def export_portable_bundle(
    dest: Path | None = None,
    *,
    include_sessions: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """打包 AppData 配置到 zip，便于换机迁移。"""
    appdata = get_appdata_dir()
    if dest is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = appdata / f"friday-portable-{stamp}.zip"

    report: dict[str, Any] = {"path": str(dest), "included": [], "skipped": [], "warnings": []}

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bundle.json", json.dumps(_bundle_info(), ensure_ascii=False, indent=2))

        for name in _CONFIG_FILES:
            src = appdata / name
            if src.is_file():
                zf.write(src, name)
                report["included"].append(name)
            else:
                report["skipped"].append(name)

        fernet = appdata / "credentials" / ".fernet_key"
        if fernet.is_file():
            zf.write(fernet, "credentials/.fernet_key")
            report["included"].append("credentials/.fernet_key")
        else:
            legacy_fernet = appdata / ".fernet_key"
            if legacy_fernet.is_file():
                zf.write(legacy_fernet, "credentials/.fernet_key")
                report["included"].append("credentials/.fernet_key (from legacy)")
            else:
                report["warnings"].append("未包含 .fernet_key，导入后 API Key 可能需重新填写")

        cred_secrets = appdata / "credentials" / "api_secrets.json"
        if cred_secrets.is_file():
            zf.write(cred_secrets, "credentials/api_secrets.json")
            report["included"].append("credentials/api_secrets.json")
        else:
            report["warnings"].append("未包含 credentials/api_secrets.json，导入后 API Key 可能需重新填写")

        plugins_root = appdata / "plugins"
        if plugins_root.is_dir():
            for path in plugins_root.rglob("*"):
                if path.is_file():
                    arc = str(Path("plugins") / path.relative_to(plugins_root)).replace("\\", "/")
                    zf.write(path, arc)
            report["included"].append("plugins/")

        if include_sessions:
            sessions = appdata / "sessions"
            if sessions.is_dir():
                for path in sessions.glob("*.json"):
                    zf.write(path, f"sessions/{path.name}")
                report["included"].append("sessions/")

    _log.info("已导出便携配置包 | path=%s files=%d", dest, len(report["included"]))
    return dest, report


def import_portable_bundle(
    zip_path: Path,
    *,
    include_sessions: bool = True,
) -> dict[str, Any]:
    """从 zip 恢复配置；导入前备份当前 AppData 子集。"""
    appdata = get_appdata_dir()
    report: dict[str, Any] = {
        "imported": [],
        "skipped": [],
        "warnings": [],
        "errors": [],
        "backup_dir": "",
    }

    if not zip_path.is_file():
        report["errors"].append("文件不存在")
        return report

    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile:
        report["errors"].append("无效的 zip 文件")
        return report

    with zf:
        if "bundle.json" not in zf.namelist():
            report["errors"].append("无效的便携包：缺少 bundle.json")
            return report

        backup_dir = appdata / f".import-backup-{int(time.time())}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        report["backup_dir"] = str(backup_dir)

        for name in _CONFIG_FILES:
            src = appdata / name
            if src.is_file():
                shutil.copy2(src, backup_dir / name)

        cred_backup = backup_dir / "credentials"
        cred_backup.mkdir(parents=True, exist_ok=True)
        for name in (".fernet_key", "api_secrets.json"):
            src = appdata / "credentials" / name
            if src.is_file():
                shutil.copy2(src, cred_backup / name)

        legacy_fernet = appdata / ".fernet_key"
        if legacy_fernet.is_file():
            shutil.copy2(legacy_fernet, backup_dir / ".fernet_key")

        plugins_backup = appdata / "plugins"
        if plugins_backup.is_dir():
            shutil.copytree(plugins_backup, backup_dir / "plugins", dirs_exist_ok=True)

        from friday.zip_safety import resolve_zip_member_path

        for member in zf.namelist():
            if member.endswith("/"):
                continue
            if member == "bundle.json":
                continue
            if member.startswith("sessions/") and not include_sessions:
                report["skipped"].append(member)
                continue

            try:
                target = resolve_zip_member_path(appdata, member)
            except ValueError:
                report["errors"].append(f"便携包含非法路径（Zip Slip）: {member}")
                return report
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))
            report["imported"].append(member)

    from friday.plugins import migrate_installed_plugin_manifests
    from friday.portability import run_startup_portability_checks
    from friday.storage import load_settings

    migrated = migrate_installed_plugin_manifests()
    if migrated:
        report["warnings"].append(f"已迁移 {migrated} 个插件 manifest 为可移植格式")

    run_startup_portability_checks(load_settings())
    _log.info("已导入便携配置包 | from=%s items=%d", zip_path, len(report["imported"]))
    return report
