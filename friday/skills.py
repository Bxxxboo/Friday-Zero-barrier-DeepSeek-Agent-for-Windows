"""技能 / 模板 —— 内置 + 用户自定义，持久化到 skills.json。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("skills")

_BUILTIN: list[dict[str, Any]] = [
    {"id": "sys-status", "label": "查电脑状态", "icon": "💻", "category": "system",
     "prompt": "帮我全面检查这台电脑的状态，包括 CPU、内存、磁盘和占用最高的进程。"},
    {"id": "sys-disk", "label": "看磁盘空间", "icon": "📊", "category": "system",
     "prompt": "查看各磁盘使用情况，告诉我哪些盘空间紧张、还剩多少。"},
    {"id": "sys-proc", "label": "查占用进程", "icon": "⚡", "category": "system",
     "prompt": "列出当前占用内存和 CPU 最高的 10 个进程，并简要说明。"},
    {"id": "file-downloads", "label": "整理下载文件夹", "icon": "📁", "category": "files",
     "prompt": "查看我的下载文件夹，按文件类型整理（移动前先告诉我计划）。"},
    {"id": "file-desktop", "label": "分析桌面", "icon": "🧹", "category": "files",
     "prompt": "查看桌面上的文件，分析是否杂乱，给出整理建议（先只读，不要直接移动）。"},
    {"id": "file-search", "label": "搜索文档", "icon": "🔍", "category": "files",
     "prompt": "在我的文档目录搜索 PDF 和 Word 文件，列出路径和大小。"},
    {"id": "file-large", "label": "找大文件", "icon": "📦", "category": "files",
     "prompt": "帮我找出这台电脑上体积最大的 10 个文件并列出来。"},
    {"id": "doc-weekly", "label": "生成周报", "icon": "📝", "category": "docs",
     "prompt": "在我的文档目录生成一份本周工作周报 docx 和 pptx，各包含 3 个章节，内容你可以先合理拟定。"},
    {"id": "doc-ppt", "label": "做汇报 PPT", "icon": "📊", "category": "docs",
     "prompt": "在我的文档目录创建一份项目汇报 pptx，共 5 页：封面、背景、进展、问题、下一步。主题你先帮我拟定一个通用模板。"},
    {"id": "doc-meeting", "label": "会议纪要", "icon": "✍️", "category": "docs",
     "prompt": "在我的文档目录生成一份 docx 会议纪要模板，包含时间、参会人、议题、结论、待办事项等栏目。"},
    {"id": "daily-screenshot", "label": "截屏", "icon": "📸", "category": "daily",
     "prompt": "帮我截一张当前屏幕的截图，保存到我的文档目录。"},
    {"id": "daily-image-gen", "label": "生成图片", "icon": "🎨", "category": "daily",
     "prompt": "根据我的描述生成一张图片，保存到「生成的图片」文件夹，并告诉我保存路径。"},
    {"id": "daily-dup", "label": "查重复文件", "icon": "🗂", "category": "daily",
     "prompt": "在我的文档和下载文件夹中查找重复文件，先列出结果不要直接删除。"},
     {"id": "net-download", "label": "下载软件", "icon": "⬇️", "category": "daily",
     "prompt": "我想下载一个软件。请问我软件名称和保存位置，然后用 download_software 一键下载（不要用 PowerShell）。"},
    {"id": "daily-help", "label": "我能做什么", "icon": "💡", "category": "daily",
     "prompt": "介绍一下你能帮我打理这台电脑的哪些事情。"},
]

_CATEGORY_LABELS = {
    "system": "系统",
    "files": "文件",
    "docs": "文档",
    "daily": "日常",
    "custom": "我的技能",
    "plugin": "插件技能",
}


def _store_path() -> Path:
    return get_appdata_dir() / "skills.json"


def _normalize_skill(raw: dict[str, Any], *, builtin: bool = False) -> dict[str, Any]:
    source = "builtin" if builtin else str(raw.get("source", "custom"))
    return {
        "id": str(raw.get("id", uuid.uuid4().hex[:10])),
        "label": str(raw.get("label", "未命名")).strip(),
        "icon": str(raw.get("icon", "✨")),
        "category": str(raw.get("category", "custom")),
        "prompt": str(raw.get("prompt", "")).strip(),
        "builtin": bool(raw.get("builtin", builtin)),
        "enabled": bool(raw.get("enabled", True)),
        "hidden": bool(raw.get("hidden", False)),
        "source": source,
        "plugin_id": str(raw.get("plugin_id", "")),
        "created_at": float(raw.get("created_at", time.time())),
    }


def _load_custom() -> list[dict[str, Any]]:
    raw = load_json(_store_path())
    if not isinstance(raw, list):
        return []
    return [_normalize_skill(item) for item in raw if isinstance(item, dict)]


def _save_custom(items: list[dict[str, Any]]) -> None:
    custom = [s for s in items if not s.get("builtin")]
    atomic_write_json(_store_path(), custom)


def _resolve_plugin_skill(skill: dict[str, Any]) -> dict[str, Any]:
    plugin_id = str(skill.get("plugin_id", "")).strip()
    if skill.get("source") != "plugin" or not plugin_id:
        return skill
    from friday.plugins import substitute_plugin_text

    resolved = skill.copy()
    resolved["prompt"] = substitute_plugin_text(str(skill.get("prompt", "")), plugin_id)
    return resolved


def list_skills(*, include_disabled: bool = False, for_ui: bool = False) -> list[dict[str, Any]]:
    builtins = [_normalize_skill(s, builtin=True) for s in _BUILTIN]
    custom = _load_custom()
    all_skills = builtins + custom
    if for_ui:
        all_skills = [s for s in all_skills if not s.get("hidden")]
    if include_disabled:
        result = all_skills
    else:
        result = [s for s in all_skills if s.get("enabled", True)]
    return [_resolve_plugin_skill(s) for s in result]


def list_skills_grouped(*, include_disabled: bool = False, for_ui: bool = False) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for skill in list_skills(include_disabled=include_disabled, for_ui=for_ui):
        cat = skill.get("category") or "custom"
        groups.setdefault(cat, []).append(skill)
    order = ["system", "files", "docs", "daily", "plugin", "custom"]
    result = []
    for cat in order:
        if cat in groups:
            result.append({
                "category": cat,
                "label": _CATEGORY_LABELS.get(cat, cat),
                "skills": groups.pop(cat),
            })
    for cat, skills in groups.items():
        result.append({"category": cat, "label": _CATEGORY_LABELS.get(cat, cat), "skills": skills})
    return result


def create_skill(payload: dict[str, Any]) -> dict[str, Any]:
    skill = _normalize_skill({
        **payload,
        "id": uuid.uuid4().hex[:10],
        "category": payload.get("category") or "custom",
        "source": "custom",
        "created_at": time.time(),
    })
    custom = [s for s in _load_custom()]
    custom.append(skill)
    _save_custom(custom)
    return skill


def update_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    custom = _load_custom()
    for idx, skill in enumerate(custom):
        if skill["id"] != skill_id:
            continue
        merged = skill.copy()
        if skill.get("source") == "plugin":
            if "enabled" in payload and payload["enabled"] is not None:
                merged["enabled"] = payload["enabled"]
        else:
            for key in ("label", "icon", "category", "prompt", "enabled"):
                if key in payload and payload[key] is not None:
                    merged[key] = payload[key]
        updated = _normalize_skill(merged)
        custom[idx] = updated
        _save_custom(custom)
        return updated
    return None


def delete_skill(skill_id: str) -> bool:
    skill = get_skill(skill_id)
    if skill is None or skill.get("builtin"):
        return False
    custom = [s for s in _load_custom() if s["id"] != skill_id]
    if len(custom) == len(_load_custom()):
        return False
    _save_custom(custom)
    return True


def remove_plugin_skills(plugin_id: str) -> int:
    custom = [s for s in _load_custom() if s.get("plugin_id") != plugin_id]
    removed = len(_load_custom()) - len(custom)
    _save_custom(custom)
    return removed


def upsert_plugin_skills(plugin_id: str, skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = [s for s in _load_custom() if s.get("plugin_id") != plugin_id]
    imported: list[dict[str, Any]] = []
    for raw in skills:
        sid = f"{plugin_id}:{raw.get('id', uuid.uuid4().hex[:8])}"
        imported.append(_normalize_skill({
            **raw,
            "id": sid,
            "source": "plugin",
            "plugin_id": plugin_id,
            "category": raw.get("category") or "plugin",
        }))
    _save_custom(remaining + imported)
    return imported


def get_skill(skill_id: str) -> dict[str, Any] | None:
    for skill in list_skills(include_disabled=True):
        if skill["id"] == skill_id:
            return skill
    return None
