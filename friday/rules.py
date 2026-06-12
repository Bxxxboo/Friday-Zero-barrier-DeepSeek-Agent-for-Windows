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
BUILTIN_FILE_SAFETY_RULE_ID = "builtin:file-safety"
BUILTIN_WINDOWS_C_OS_RULE_ID = "builtin:windows-c-os-delete-ban"
BUILTIN_TASK_SCOPE_RULE_ID = "builtin:task-scope"
BUILTIN_SOLUTION_FIRST_RULE_ID = "builtin:solution-first"

_SOLUTION_FIRST_CONTENT = (
    "非平凡任务先出方案与利弊，用户明确同意后再改代码。"
    "必须先出方案：新功能、较大 UI/架构、跨多文件、需求有歧义、多种实现路径、破坏性变更。"
    "可直接动手：用户说「直接改/开始实现/按方案 A」、单行 typo、纯只读排查、"
    "或用户规则规定必须立即执行的流程。"
    "方案阶段用简体中文交付：需求理解、推荐方案（可含备选）、优缺点、影响范围、验证方式、请用户决策；"
    "此阶段禁止改业务代码或跑会改变环境的命令（只读排查除外）。"
    "实现中若与方案重大偏差，暂停并征求确认。"
)

_BUILTIN_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": BUILTIN_SOLUTION_FIRST_RULE_ID,
        "title": "先方案、后改码（solution-first）",
        "content": _SOLUTION_FIRST_CONTENT,
        "enabled": True,
        "always_apply": True,
        "hidden": True,
        "source": "builtin",
    },
    {
        "id": BUILTIN_RESPONSE_RULE_ID,
        "title": "回复习惯（像 Cursor 一样具体）",
        "content": (
            "完成任务或一段执行后：① 用具体事实说明刚刚完成了什么（文件、路径、数量、结果）；"
            "② 简单任务（如单次生图/写文件已成功）2～4 句即可，不必写长篇「剩余项/下一步」；"
            "复杂任务再给 2～4 条与本任务直接相关的下一步建议（禁止只说「继续」）；"
            "③ 若当前任务未做完，只说明其剩余项，并给出一句用户可直接复制发送的后续指令。"
            "禁止空泛收尾如「这部分任务已完成，请说继续」。"
        ),
        "enabled": True,
        "always_apply": True,
        "hidden": True,
        "source": "builtin",
    },
    {
        "id": BUILTIN_TASK_SCOPE_RULE_ID,
        "title": "任务范围（勿串台）",
        "content": (
            "收尾时的「刚刚完成了什么」「剩余未完成」「下一步建议」只能围绕"
            "本轮对话里用户当前明确委托的任务及其直接后续"
            "（例如刚生成的图片是否满意、是否调整 prompt 或尺寸重生成）。"
            "禁止把历史会话、早前已完成或已搁置的其他话题"
            "（如版本升级、微信桥接、Python 环境、无关 bug）写进剩余项或建议。"
            "用户在本轮未提及的事项，视为与本任务无关，不要主动带回；"
            "只有用户在本轮重新提出时，才可继续该话题。"
        ),
        "enabled": True,
        "always_apply": True,
        "hidden": True,
        "source": "builtin",
    },
    {
        "id": BUILTIN_WINDOWS_C_OS_RULE_ID,
        "title": "C 盘系统文件绝对禁令",
        "content": (
            "绝对禁止删除、移动、覆盖或整理 C 盘操作系统路径下的任何文件或目录"
            "（含 C:\\Windows、C:\\Program Files、C:\\Program Files (x86)、"
            "C:\\ProgramData、C:\\Boot、C:\\Recovery 等；不含 C:\\Users 下用户个人文件）。"
            "不得用 delete_file、delete_directory、move_file、organize_directory、"
            "write_text_file、run_python、run_powershell 等任何方式绕过；"
            "即使用户或 Yolo 要求也不得执行。读-only 查看系统目录除外。"
        ),
        "enabled": True,
        "always_apply": True,
        "hidden": True,
        "source": "builtin",
    },
    {
        "id": BUILTIN_FILE_SAFETY_RULE_ID,
        "title": "文件删改安全",
        "content": (
            "删/改/移用户电脑上已存在的文件须用 delete_file、write_text_file、move_file、"
            "organize_directory 等专用工具，并等待用户在界面或微信点「同意」；"
            "禁止用 run_python、run_python_script、run_powershell 执行 os.remove、rmtree、"
            "shutil.move、os.replace 等删除/覆盖已有文件的方式绕过审批；"
            "工作区内新建文件可经普通 run_python（同轮确认一次），覆盖已有文件仍须专用工具。"
            "「整理」「清理」「修复」须先只读扫描并给出计划，用户确认后再执行；不等于同意删除。"
            "禁止修改 %AppData%\\Friday\\ 下 settings.json、operations.json 等应用配置。"
            "覆盖已有文件、删除、批量移动前须说明路径、数量与是否可恢复。"
            "Ask 模式只读；Agent 每次危险操作须确认；Yolo 下删除与 Python/PowerShell 仍须确认。"
            "收尾须列出实际动过的路径，或明确「未删除任何文件」。"
        ),
        "enabled": True,
        "always_apply": True,
        "hidden": True,
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
        items = [
            r for r in items
            if not r.get("hidden") and r.get("source") != "builtin"
        ]
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
    by_id = {r["id"]: idx for idx, r in enumerate(items)}
    changed = False
    for raw in _BUILTIN_RULES:
        rid = raw["id"]
        normalized = _normalize_rule(raw, source="builtin")
        if rid in by_id:
            idx = by_id[rid]
            existing = items[idx]
            if existing.get("source") != "builtin":
                continue
            for key in ("title", "content", "hidden"):
                if existing.get(key) != normalized.get(key):
                    existing[key] = normalized[key]
                    changed = True
            items[idx] = existing
        else:
            items.append(normalized)
            by_id[rid] = len(items) - 1
            changed = True
    if changed:
        _save_all(items)


def _rule_content_for_prompt(rule: dict[str, Any]) -> str:
    content = rule.get("content", "").strip()
    if rule.get("source") == "plugin" and rule.get("plugin_id"):
        from friday.plugins import substitute_plugin_text

        content = substitute_plugin_text(content, str(rule["plugin_id"]))
    return content


def _append_rule_lines(lines: list[str], rules: list[dict[str, Any]], *, start: int = 1) -> int:
    idx = start
    for rule in rules:
        content = _rule_content_for_prompt(rule)
        if not content:
            continue
        title = rule.get("title") or f"规则{idx}"
        lines.append(f"{idx}. [{title}] {content}")
        idx += 1
    return idx


def active_rules_prompt() -> str:
    """返回应注入系统提示词的规则文本。"""
    from friday.bundled import hidden_builtin_rules

    ensure_builtin_rules()
    all_active = [r for r in _load_all() if r.get("enabled") and r.get("always_apply")]
    builtin = [r for r in all_active if r.get("source") == "builtin"]
    user = [r for r in all_active if r.get("source") != "builtin"]
    for rule in hidden_builtin_rules():
        if rule.get("enabled") and rule.get("always_apply"):
            builtin.append(rule)
    if not builtin and not user:
        return ""

    lines: list[str] = []
    if builtin:
        lines.append("\n内置行为准则（默认遵守）：")
        _append_rule_lines(lines, builtin)
    if user:
        header = "\n用户自定义规则（必须遵守"
        if builtin:
            header += "；与内置冲突时以本条为准"
        header += "）："
        lines.append(header)
        _append_rule_lines(lines, user)
    return "\n".join(lines)
