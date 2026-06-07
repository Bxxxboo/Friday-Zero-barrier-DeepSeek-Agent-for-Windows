"""行为规则 —— 注入系统提示词，持久化到 rules.json。"""

from __future__ import annotations

import time
import uuid
from typing import Any

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("rules")

BUILTIN_RESPONSE_RULE_ID = "builtin:cursor-style-reply"

_BUILTIN_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": BUILTIN_RESPONSE_RULE_ID,
        "title": "回复习惯（像 Cursor 一样具体）",
        "content": (
            "完成任务或一段执行后：① 用具体事实说明刚刚完成了什么（文件、路径、数量、结果）；"
            "② 给出 2～4 条可执行的下一步建议（禁止只说「继续」或「告诉我下一步」）；"
            "③ 若未做完，说明剩余项并给出一句用户可直接复制发送的后续指令。"
            "禁止空泛收尾如「这部分任务已完成，请说继续」。"
        ),
        "enabled": True,
        "always_apply": True,
        "source": "builtin",
    },
)


def _store_path():
    return get_appdata_dir() / "rules.json"


def _normalize_rule(raw: dict[str, Any], *, source: str = "custom", plugin_id: str = "") -> dict[str, Any]:
    return {
        "id": str(raw.get("id", uuid.uuid4().hex[:10])),
        "title": str(raw.get("title", "未命名规则")).strip(),
        "content": str(raw.get("content", "")).strip(),
        "enabled": bool(raw.get("enabled", True)),
        "always_apply": bool(raw.get("always_apply", True)),
        "hidden": bool(raw.get("hidden", False)),
        "source": str(raw.get("source", source)),
        "plugin_id": str(raw.get("plugin_id", plugin_id)),
        "created_at": float(raw.get("created_at", time.time())),
    }


def _load_all() -> list[dict[str, Any]]:
    raw = load_json(_store_path())
    if not isinstance(raw, list):
        return []
    return [_normalize_rule(item) for item in raw if isinstance(item, dict)]


def _save_all(items: list[dict[str, Any]]) -> None:
    atomic_write_json(_store_path(), items)


def list_rules(*, include_disabled: bool = True, for_ui: bool = False) -> list[dict[str, Any]]:
    ensure_builtin_rules()
    items = _load_all()
    if for_ui:
        items = [r for r in items if not r.get("hidden")]
    if include_disabled:
        return items
    return [r for r in items if r.get("enabled")]


def get_rule(rule_id: str) -> dict[str, Any] | None:
    for rule in _load_all():
        if rule["id"] == rule_id:
            return rule
    return None


def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
    rule = _normalize_rule({
        **payload,
        "id": uuid.uuid4().hex[:10],
        "source": "custom",
        "created_at": time.time(),
    })
    items = _load_all()
    items.append(rule)
    _save_all(items)
    return rule


def update_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    items = _load_all()
    for idx, rule in enumerate(items):
        if rule["id"] != rule_id:
            continue
        if rule.get("source") == "plugin" and any(k in payload for k in ("title", "content")):
            continue
        merged = rule.copy()
        for key in ("title", "content", "enabled", "always_apply"):
            if key in payload and payload[key] is not None:
                merged[key] = payload[key]
        items[idx] = _normalize_rule(merged, source=rule.get("source", "custom"), plugin_id=rule.get("plugin_id", ""))
        _save_all(items)
        return items[idx]
    return None


def delete_rule(rule_id: str) -> bool:
    rule = get_rule(rule_id)
    if rule is None:
        return False
    if rule.get("source") == "builtin":
        return False
    items = [r for r in _load_all() if r["id"] != rule_id]
    if len(items) == len(_load_all()):
        return False
    _save_all(items)
    return True


def remove_plugin_rules(plugin_id: str) -> int:
    items = [r for r in _load_all() if r.get("plugin_id") != plugin_id]
    removed = len(_load_all()) - len(items)
    _save_all(items)
    return removed


def upsert_plugin_rules(plugin_id: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = [r for r in _load_all() if r.get("plugin_id") != plugin_id]
    imported: list[dict[str, Any]] = []
    for raw in rules:
        rid = f"{plugin_id}:{raw.get('id', uuid.uuid4().hex[:8])}"
        imported.append(_normalize_rule({
            **raw,
            "id": rid,
            "source": "plugin",
            "plugin_id": plugin_id,
        }, source="plugin", plugin_id=plugin_id))
    _save_all(remaining + imported)
    return imported


def ensure_builtin_rules() -> None:
    items = _load_all()
    existing = {r["id"] for r in items}
    added = False
    for raw in _BUILTIN_RULES:
        if raw["id"] in existing:
            continue
        items.append(_normalize_rule(raw, source="builtin"))
        added = True
    if added:
        _save_all(items)


def active_rules_prompt() -> str:
    """返回应注入系统提示词的规则文本。"""
    from friday.bundled import hidden_builtin_rules

    ensure_builtin_rules()
    active = [r for r in _load_all() if r.get("enabled") and r.get("always_apply")]
    for rule in hidden_builtin_rules():
        if rule.get("enabled") and rule.get("always_apply"):
            active.append(rule)
    if not active:
        return ""
    lines = ["\n用户自定义规则（必须遵守）："]
    for idx, rule in enumerate(active, 1):
        title = rule.get("title") or f"规则{idx}"
        content = rule.get("content", "").strip()
        if rule.get("source") == "plugin" and rule.get("plugin_id"):
            from friday.plugins import substitute_plugin_text

            content = substitute_plugin_text(content, str(rule["plugin_id"]))
        if content:
            lines.append(f"{idx}. [{title}] {content}")
    return "\n".join(lines)
