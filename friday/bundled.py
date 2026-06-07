"""内置扩展包 —— 原推荐插件，默认启用且不展示在扩展管理 UI。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from friday.logging_config import get_logger
from friday.paths import extensions_dir, get_appdata_dir

_log = get_logger("bundled")

BUNDLED_PLUGIN_IDS: frozenset[str] = frozenset({
    "vision-bridge",
    "storage-analyzer",
})

# 曾作为内置/推荐插件安装过的 ID，启动迁移时一并清理残留
_LEGACY_BUNDLED_IDS: frozenset[str] = BUNDLED_PLUGIN_IDS | frozenset({"demo-office"})

_RETIRED_RULE_TITLES: frozenset[str] = frozenset({"简洁回复"})

_MANIFEST = "friday-plugin.json"


def is_bundled_plugin(plugin_id: str) -> bool:
    return (plugin_id or "").strip() in BUNDLED_PLUGIN_IDS


def bundled_resource_dir(plugin_id: str) -> Path:
    """技能脚本等资源目录：优先使用曾下载到 AppData 的完整包，否则用仓库 extensions/。"""
    pid = plugin_id.strip()
    app_dir = get_appdata_dir() / "plugins" / pid
    ext_dir = extensions_dir() / pid
    if (app_dir / "scripts").is_dir() or (app_dir / "SKILL.md").is_file():
        return app_dir
    return ext_dir


def _substitute_dir(text: str, plugin_id: str) -> str:
    root = str(bundled_resource_dir(plugin_id)).replace("\\", "/")
    return text.replace("{plugin_dir}", root)


def _load_manifest(plugin_id: str) -> dict[str, Any] | None:
    for base in (bundled_resource_dir(plugin_id), extensions_dir() / plugin_id):
        path = base / _MANIFEST
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("读取内置扩展 manifest 失败 | id=%s err=%s", plugin_id, exc)
            return None
        if isinstance(data, dict):
            return data
    return None


@lru_cache(maxsize=1)
def _bundled_manifests() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for pid in sorted(BUNDLED_PLUGIN_IDS):
        manifest = _load_manifest(pid)
        if manifest:
            loaded[pid] = manifest
        else:
            _log.warning("内置扩展 manifest 缺失 | id=%s", pid)
    return loaded


def hidden_builtin_rules() -> list[dict[str, Any]]:
    """注入系统提示，不在设置页展示。"""
    rules: list[dict[str, Any]] = []
    for pid, manifest in _bundled_manifests().items():
        for raw in manifest.get("rules") or []:
            if not isinstance(raw, dict):
                continue
            rid = str(raw.get("id", "")).strip()
            if not rid:
                continue
            content = _substitute_dir(str(raw.get("content", "")), pid)
            rules.append({
                "id": f"builtin:{pid}:{rid}",
                "title": str(raw.get("title", rid)).strip(),
                "content": content,
                "enabled": bool(raw.get("enabled", True)),
                "always_apply": True,
                "source": "builtin",
                "hidden": True,
            })
    return rules


def _is_retired_rule(rule: dict[str, Any]) -> bool:
    title = str(rule.get("title", "")).strip()
    rid = str(rule.get("id", ""))
    if title in _RETIRED_RULE_TITLES:
        return True
    if "concise-replies" in rid or rid.endswith(":concise"):
        return True
    return False


def migrate_legacy_bundled_plugins() -> None:
    """将旧版「已安装插件」形式的捆绑包迁移为纯内置，并清理 UI 数据。"""
    from friday.plugins import _load_registry, _save_registry
    from friday.rules import delete_rule, list_rules
    from friday.skills import delete_skill, list_skills

    registry = _load_registry()
    filtered = [p for p in registry if p.get("id") not in _LEGACY_BUNDLED_IDS]
    if len(filtered) != len(registry):
        _save_registry(filtered)
        _log.info(
            "已从插件注册表移除内置/遗留扩展 | ids=%s",
            ", ".join(sorted(_LEGACY_BUNDLED_IDS)),
        )

    for skill in list(list_skills(include_disabled=True, for_ui=False)):
        pid = skill.get("plugin_id") or ""
        sid = skill.get("id", "")
        prefix = sid.split(":")[0] if ":" in sid else ""
        if pid in _LEGACY_BUNDLED_IDS or prefix in _LEGACY_BUNDLED_IDS:
            delete_skill(sid)

    for rule in list(list_rules(include_disabled=True, for_ui=False)):
        pid = rule.get("plugin_id") or ""
        rid = rule.get("id", "")
        prefix = rid.split(":")[0] if ":" in rid else ""
        if pid in _LEGACY_BUNDLED_IDS or prefix in _LEGACY_BUNDLED_IDS or _is_retired_rule(rule):
            delete_rule(rid)

    from friday.rules import _load_all, _save_all

    kept = [
        r for r in _load_all()
        if not _is_retired_rule(r)
        and not any(
            r.get("id", "").startswith(f"{p}:")
            or r.get("plugin_id") == p
            for p in _LEGACY_BUNDLED_IDS
        )
    ]
    if len(kept) != len(_load_all()):
        _save_all(kept)


def bundled_already_message(plugin_id: str) -> str:
    names = {
        "vision-bridge": "图片视觉桥接",
        "storage-analyzer": "存储分析",
    }
    label = names.get(plugin_id, plugin_id)
    return f"「{label}」已是星期五内置能力，无需安装插件。"


def resolve_bundled_source(source: str) -> str | None:
    """若来源指向内置扩展，返回插件 ID。"""
    raw = (source or "").strip()
    if not raw:
        return None
    if is_bundled_plugin(raw):
        return raw
    if raw.startswith("local:"):
        pid = raw.split(":", 1)[1].strip()
        return pid if is_bundled_plugin(pid) else None
    cleaned = raw.replace("https://github.com/", "").strip("/")
    tail = cleaned.split("/")[-1] if cleaned else ""
    if is_bundled_plugin(tail):
        return tail
    if re.search(r"storage-analyzer", cleaned, re.I):
        return "storage-analyzer"
    if re.search(r"vision-bridge", cleaned, re.I):
        return "vision-bridge"
    return None
