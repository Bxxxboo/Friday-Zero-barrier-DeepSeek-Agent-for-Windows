"""诊断包导出（脱敏，不含 API Key 明文）—— M4.2。"""

from __future__ import annotations

import json
import platform
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from friday.crash_handler import crashes_dir
from friday.logging_config import get_logger, log_file_path, read_recent_log_lines
from friday.paths import get_appdata_dir
from friday.storage import UserSettings, load_settings

_log = get_logger("diagnostics")

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9._-]{6,}", re.I), "sk-***"),
    (re.compile(r"ark-[A-Za-z0-9._-]{6,}", re.I), "ark-***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.I), "Bearer ***"),
    (re.compile(r'"api_key"\s*:\s*"[^"]*"', re.I), '"api_key": "***"'),
    (re.compile(r'"vision_api_key"\s*:\s*"[^"]*"', re.I), '"vision_api_key": "***"'),
    (re.compile(r'"image_gen_api_key"\s*:\s*"[^"]*"', re.I), '"image_gen_api_key": "***"'),
    (re.compile(r"fernet:[A-Za-z0-9+/=_-]{8,}", re.I), "fernet:***"),
)


def redact_text(text: str) -> str:
    out = text or ""
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redacted_settings_summary(settings: UserSettings) -> dict[str, Any]:
    from friday.category_profiles import category_profiles_summary
    from friday.custom_endpoints import get_active_id
    from friday.image_gen import image_gen_config_hint, image_gen_ready, masked_image_gen_key
    from friday.llm_profiles import active_provider_id, llm_config_hint, profiles_summary
    from friday.vision import masked_vision_key, vision_config_hint, vision_ready

    return {
        "llm_provider": active_provider_id(settings),
        "api_key_masked": settings.masked_key(),
        "base_url": settings.base_url,
        "model": settings.model,
        "api_ready": settings.api_ready,
        "llm_status_hint": llm_config_hint(settings),
        "llm_profiles_summary": profiles_summary(settings),
        "vision_enabled": settings.vision_enabled,
        "vision_provider": settings.vision_provider,
        "vision_api_key_masked": masked_vision_key(settings),
        "vision_base_url": settings.vision_base_url,
        "vision_model": settings.vision_model,
        "vision_ready": vision_ready(settings),
        "vision_status_hint": vision_config_hint(settings),
        "vision_profiles_summary": category_profiles_summary(settings, "vision"),
        "image_gen_enabled": settings.image_gen_enabled,
        "image_gen_provider": settings.image_gen_provider,
        "image_gen_api_key_masked": masked_image_gen_key(settings),
        "image_gen_base_url": settings.image_gen_base_url,
        "image_gen_model": settings.image_gen_model,
        "image_gen_ready": image_gen_ready(settings),
        "image_gen_status_hint": image_gen_config_hint(settings),
        "image_gen_profiles_summary": category_profiles_summary(settings, "image_gen"),
        "workspace": settings.workspace,
        "weixin_bridge_enabled": getattr(settings, "weixin_bridge_enabled", True),
        "llm_custom_active": get_active_id(settings, "llm"),
        "vision_custom_active": get_active_id(settings, "vision"),
        "image_gen_custom_active": get_active_id(settings, "image_gen"),
    }


def _system_info() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python_version": sys.version.replace("\n", " "),
        "executable": str(Path(sys.executable)),
        "cwd": str(Path.cwd()),
        "appdata": str(get_appdata_dir()),
    }


def _autostart_info() -> dict[str, Any]:
    try:
        from friday.autostart import autostart_status

        return autostart_status()
    except Exception as exc:
        return {"available": False, "detail": str(exc)}


def _weixin_info() -> dict[str, Any]:
    try:
        from friday.weixin.setup import weixin_status_payload

        return weixin_status_payload()
    except Exception as exc:
        return {"error": str(exc)}


def export_diagnostic_bundle(dest: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """打包诊断信息为 zip（脱敏，不含 credentials/ 与 settings.json 原文）。"""
    from friday.edition import display_version
    from friday.portability import run_portability_audit
    from friday.runtime_info import runtime_info_payload
    from friday.version import __version__

    appdata = get_appdata_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    if dest is None:
        dest = appdata / f"Friday-diagnostic-{stamp}.zip"

    settings = load_settings()
    manifest = {
        "kind": "friday-diagnostic",
        "app_version": __version__,
        "display_version": display_version(__version__),
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    report: dict[str, Any] = {
        "path": str(dest),
        "included": [],
        "warnings": [],
    }

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        def add_json(name: str, payload: Any) -> None:
            zf.writestr(name, json.dumps(payload, ensure_ascii=False, indent=2))
            report["included"].append(name)

        add_json("manifest.json", manifest)
        add_json("runtime.json", runtime_info_payload())
        add_json("settings_summary.json", redacted_settings_summary(settings))
        add_json("system.json", _system_info())
        add_json("autostart.json", _autostart_info())
        add_json("weixin_status.json", _weixin_info())
        add_json("portability_audit.json", {"items": run_portability_audit(settings)})

        log_lines = read_recent_log_lines(200)
        if log_lines:
            body = redact_text("\n".join(log_lines) + "\n")
            zf.writestr("logs/friday.log.tail.txt", body)
            report["included"].append("logs/friday.log.tail.txt")
        elif log_file_path().is_file():
            report["warnings"].append("日志文件存在但未能读取尾部")

        crash_files = sorted(crashes_dir().glob("crash-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for crash in crash_files[:3]:
            try:
                text = redact_text(crash.read_text(encoding="utf-8", errors="replace"))
                arc = f"crashes/{crash.name}"
                zf.writestr(arc, text)
                report["included"].append(arc)
            except OSError as exc:
                report["warnings"].append(f"跳过崩溃报告 {crash.name}: {exc}")

    _log.info("已导出诊断包 | path=%s files=%d", dest, len(report["included"]))
    return dest, report
