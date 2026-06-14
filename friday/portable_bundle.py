"""可移植配置包导出 / 导入（zip）。"""

from __future__ import annotations

import json
import shutil
import tempfile
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
_EXTRA_CONFIG_FILES = ("schedules.json",)


def _bundle_info(*, sections: list[str] | None = None) -> dict[str, Any]:
    from friday.version import __version__

    return {
        "bundle_version": BUNDLE_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "included_sections": sections or [],
    }


def _collect_export_sections(
    appdata: Path,
    *,
    include_sessions: bool,
) -> list[str]:
    sections: list[str] = []
    for name in _CONFIG_FILES + _EXTRA_CONFIG_FILES:
        if (appdata / name).is_file():
            sections.append(name)
    if (appdata / "credentials" / ".fernet_key").is_file() or (appdata / ".fernet_key").is_file():
        sections.append("credentials")
    if (appdata / "plugins").is_dir():
        sections.append("plugins")
    if include_sessions and (appdata / "sessions").is_dir():
        sections.append("sessions")
    return sections


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

    sections = _collect_export_sections(appdata, include_sessions=include_sessions)
    report: dict[str, Any] = {
        "path": str(dest),
        "included": [],
        "skipped": [],
        "warnings": [],
        "sections": sections,
    }

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bundle.json", json.dumps(_bundle_info(sections=sections), ensure_ascii=False, indent=2))

        for name in _CONFIG_FILES + _EXTRA_CONFIG_FILES:
            src = appdata / name
            if src.is_file():
                zf.write(src, name)
                report["included"].append(name)
            elif name in _CONFIG_FILES:
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
                report["warnings"].append(
                    "未包含 .fernet_key：导入后 API Key 将无法自动解密，需重新填写"
                )

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
            index_path = appdata / "sessions_index.json"
            if index_path.is_file():
                zf.write(index_path, "sessions_index.json")
                report["included"].append("sessions_index.json")
            elif sessions.is_dir() and any(sessions.glob("*.json")):
                report["warnings"].append("未找到 sessions_index.json，导入后将尝试从会话文件重建")

    if not include_sessions:
        report["warnings"].append("此包不含对话历史；换机后侧栏会话需重新导出（勾选「含对话历史」）")

    report["warnings"].append("此包不含微信扫码登录态，新机需重新配置微信端 AI")

    _log.info("已导出便携配置包 | path=%s files=%d", dest, len(report["included"]))
    return dest, report


def _backup_appdata_subset(appdata: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in _CONFIG_FILES + _EXTRA_CONFIG_FILES:
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

    sessions_backup = backup_dir / "sessions"
    sessions_src = appdata / "sessions"
    if sessions_src.is_dir():
        shutil.copytree(sessions_src, sessions_backup, dirs_exist_ok=True)
    index_src = appdata / "sessions_index.json"
    if index_src.is_file():
        shutil.copy2(index_src, backup_dir / "sessions_index.json")


def _restore_from_backup(backup_dir: Path, appdata: Path) -> None:
    if not backup_dir.is_dir():
        return
    for name in _CONFIG_FILES + _EXTRA_CONFIG_FILES:
        src = backup_dir / name
        if src.is_file():
            shutil.copy2(src, appdata / name)

    cred_backup = backup_dir / "credentials"
    if cred_backup.is_dir():
        dest_cred = appdata / "credentials"
        dest_cred.mkdir(parents=True, exist_ok=True)
        for name in (".fernet_key", "api_secrets.json"):
            src = cred_backup / name
            if src.is_file():
                shutil.copy2(src, dest_cred / name)

    legacy = backup_dir / ".fernet_key"
    if legacy.is_file():
        shutil.copy2(legacy, appdata / ".fernet_key")

    plugins_backup = backup_dir / "plugins"
    plugins_dest = appdata / "plugins"
    if plugins_backup.is_dir():
        if plugins_dest.is_dir():
            shutil.rmtree(plugins_dest)
        shutil.copytree(plugins_backup, plugins_dest)

    sessions_backup = backup_dir / "sessions"
    sessions_dest = appdata / "sessions"
    if sessions_backup.is_dir():
        if sessions_dest.is_dir():
            shutil.rmtree(sessions_dest)
        shutil.copytree(sessions_backup, sessions_dest)
    index_backup = backup_dir / "sessions_index.json"
    if index_backup.is_file():
        shutil.copy2(index_backup, appdata / "sessions_index.json")
    elif (appdata / "sessions_index.json").is_file():
        (appdata / "sessions_index.json").unlink(missing_ok=True)


def _apply_staging_to_appdata(
    staging: Path,
    appdata: Path,
    *,
    include_sessions: bool,
    report: dict[str, Any],
) -> None:
    from friday.zip_safety import resolve_zip_member_path

    for path in staging.rglob("*"):
        if not path.is_file():
            continue
        member = str(path.relative_to(staging)).replace("\\", "/")
        if member == "bundle.json":
            continue
        if member.startswith("sessions/") and not include_sessions:
            report["skipped"].append(member)
            continue
        if member == "sessions_index.json" and not include_sessions:
            report["skipped"].append(member)
            continue

        target = resolve_zip_member_path(appdata, member)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        report["imported"].append(member)


def import_portable_bundle(
    zip_path: Path,
    *,
    include_sessions: bool = True,
) -> dict[str, Any]:
    """从 zip 恢复配置；先解压校验再写入，失败时回滚。"""
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

    staging = Path(tempfile.mkdtemp(prefix="friday-import-stage-"))
    backup_dir = appdata / f".import-backup-{int(time.time())}"
    try:
        try:
            zf = zipfile.ZipFile(zip_path, "r")
        except zipfile.BadZipFile:
            report["errors"].append("无效的 zip 文件")
            return report

        with zf:
            from friday.zip_safety import resolve_zip_member_path

            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                try:
                    target = resolve_zip_member_path(staging, member)
                except ValueError:
                    report["errors"].append(f"便携包含非法路径（Zip Slip）: {member}")
                    return report
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))

        if not (staging / "bundle.json").is_file():
            report["errors"].append("无效的便携包：缺少 bundle.json")
            return report

        _backup_appdata_subset(appdata, backup_dir)
        report["backup_dir"] = str(backup_dir)

        try:
            _apply_staging_to_appdata(
                staging,
                appdata,
                include_sessions=include_sessions,
                report=report,
            )
        except Exception as exc:  # noqa: BLE001
            _restore_from_backup(backup_dir, appdata)
            report["errors"].append(f"导入失败已回滚: {exc}")
            _log.exception("便携包导入失败已回滚")
            return report

        from friday.plugins import migrate_installed_plugin_manifests
        from friday.portability import run_startup_portability_checks
        from friday.sessions import ensure_sessions_index_after_import
        from friday.storage import load_settings

        if include_sessions and ensure_sessions_index_after_import():
            report["warnings"].append("已从会话文件重建 sessions_index.json")

        migrated = migrate_installed_plugin_manifests()
        if migrated:
            report["warnings"].append(f"已迁移 {migrated} 个插件 manifest 为可移植格式")

        run_startup_portability_checks(load_settings())
        _log.info("已导入便携配置包 | from=%s items=%d", zip_path, len(report["imported"]))
        return report
    finally:
        shutil.rmtree(staging, ignore_errors=True)
