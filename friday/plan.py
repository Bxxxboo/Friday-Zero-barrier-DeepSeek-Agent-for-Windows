"""会话 Plan / Todo 管理（可移植，存于 session JSON）。"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from friday.config import PLAN_ANCHOR_MARKER
from friday.logging_config import get_logger
from friday.prefix_cache import is_plan_anchor_message
from friday.sessions import ChatSession, get_session, save_session_fields

_log = get_logger("plan")

PLAN_TOOL_NAMES = frozenset({"update_session_plan", "update_session_todos"})

_CHECKBOX_RE = re.compile(
    r"^\s*(?:[-*+]|\d+\.)\s*\[(?P<mark>[ xX])\]\s+(?P<text>.+?)\s*$",
    re.MULTILINE,
)
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def normalize_todos(raw: list[Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        items.append({
            "id": str(entry.get("id") or uuid.uuid4().hex[:10]),
            "text": text,
            "done": bool(entry.get("done", False)),
        })
    return items


def _todo_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().casefold())


def extract_todos_from_plan_markdown(markdown: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in _CHECKBOX_RE.finditer(markdown or ""):
        text = str(match.group("text") or "").strip()
        if not text:
            continue
        mark = str(match.group("mark") or " ").strip().lower()
        items.append({
            "id": uuid.uuid4().hex[:10],
            "text": text,
            "done": mark == "x",
        })
    return items


def merge_todos_from_plan(
    existing: list[dict[str, Any]] | None,
    plan_markdown: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """将 Markdown 计划里的 checkbox 合并进待办，保留已有 id / 完成态。"""
    current = normalize_todos(existing)
    by_key = {_todo_key(item["text"]): item for item in current}
    added: list[str] = []
    merged: list[dict[str, Any]] = []

    for item in extract_todos_from_plan_markdown(plan_markdown):
        key = _todo_key(item["text"])
        prev = by_key.get(key)
        if prev:
            merged.append({
                "id": prev["id"],
                "text": prev["text"],
                "done": prev["done"] or item["done"],
            })
            continue
        merged.append(item)
        added.append(item["text"])

    for item in current:
        key = _todo_key(item["text"])
        if key not in {_todo_key(x["text"]) for x in merged}:
            merged.append(item)
    return merged, added


def get_session_plan(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        return {"ok": False, "plan_markdown": "", "todos": []}
    return {
        "ok": True,
        "plan_markdown": getattr(session, "plan_markdown", "") or "",
        "todos": normalize_todos(getattr(session, "todos", None)),
    }


def update_session_plan(
    session_id: str,
    *,
    plan_markdown: str | None = None,
    todos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        return {"ok": False, "message": "会话不存在"}
    fields: dict[str, Any] = {"updated_at": time.time()}
    if plan_markdown is not None:
        fields["plan_markdown"] = plan_markdown.strip()
    if todos is not None:
        fields["todos"] = normalize_todos(todos)
    save_session_fields(session_id, **fields)
    return get_session_plan(session_id)


def sync_todos_from_plan(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        return {"ok": False, "changed": False, "added": []}
    plan = (getattr(session, "plan_markdown", "") or "").strip()
    todos = normalize_todos(getattr(session, "todos", None))
    merged, added = merge_todos_from_plan(todos, plan)
    changed = merged != todos
    if changed:
        save_session_fields(session_id, todos=merged, updated_at=time.time())
        _log.info("已从计划同步待办 | session=%s added=%d", session_id[:8], len(added))
    return {"ok": True, "changed": changed, "added": added, **get_session_plan(session_id)}


def _todo_match_tokens(text: str) -> list[str]:
    raw = [t.casefold() for t in _TOKEN_RE.findall(text or "") if len(t) >= 2]
    tokens: list[str] = []
    for chunk in raw:
        if chunk not in tokens:
            tokens.append(chunk)
        if len(chunk) >= 4:
            for i in range(len(chunk) - 1):
                gram = chunk[i : i + 2]
                if gram not in tokens:
                    tokens.append(gram)
    return tokens


def _tool_context(tool_name: str, tool_args: dict[str, Any], tool_result: str) -> str:
    parts = [tool_name, tool_result]
    for value in (tool_args or {}).values():
        parts.append(str(value))
    return "\n".join(parts).casefold()


def _looks_like_failure(text: str) -> bool:
    sample = (text or "").strip().casefold()
    if not sample:
        return True
    fail_markers = (
        "失败", "错误", "无法", "不能", "拒绝", "异常", "invalid", "error", "failed",
        "traceback", "不存在", "未找到", "permission denied",
    )
    return any(marker in sample for marker in fail_markers)


def _score_todo_match(todo_text: str, haystack: str) -> float:
    todo_cf = todo_text.casefold()
    if todo_cf and todo_cf in haystack:
        return 1.0
    for size in range(len(todo_cf), 3, -1):
        for start in range(len(todo_cf) - size + 1):
            fragment = todo_cf[start : start + size]
            if len(fragment) >= 4 and fragment in haystack:
                return min(0.92, size / max(len(todo_cf), 1))
    tokens = _todo_match_tokens(todo_text)
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in haystack)
    if hits == 0:
        return 0.0
    if any(key in todo_cf for key in ("log", "日志", "报错", "friday.log")):
        if any(key in haystack for key in ("friday.log", "日志", "log")):
            return 0.85
    return hits / len(tokens)


def _mark_todos_done(
    session_id: str,
    matcher: Any,
    *,
    min_score: float = 0.66,
) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        return {"ok": False, "changed": False, "completed": []}
    todos = normalize_todos(getattr(session, "todos", None))
    completed: list[str] = []
    changed = False
    for item in todos:
        if item.get("done"):
            continue
        score = float(matcher(item.get("text", "")))
        if score >= min_score:
            item["done"] = True
            completed.append(str(item.get("text", "")))
            changed = True
    if changed:
        save_session_fields(session_id, todos=todos, updated_at=time.time())
        _log.info("自动勾选待办 | session=%s count=%d", session_id[:8], len(completed))
    return {"ok": True, "changed": changed, "completed": completed}


def auto_complete_todos_from_tool(
    session_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: str,
) -> dict[str, Any]:
    if tool_name in PLAN_TOOL_NAMES:
        return {"ok": True, "changed": False, "completed": []}
    if _looks_like_failure(tool_result):
        return {"ok": True, "changed": False, "completed": []}
    haystack = _tool_context(tool_name, tool_args, tool_result)

    def matcher(todo_text: str) -> float:
        return _score_todo_match(todo_text, haystack)

    return _mark_todos_done(session_id, matcher)


def auto_complete_todos_from_assistant(session_id: str, assistant_text: str) -> dict[str, Any]:
    text = (assistant_text or "").strip()
    if not text:
        return {"ok": True, "changed": False, "completed": []}
    haystack = text.casefold()
    completion_markers = ("已完成", "完成了", "已搞定", "已处理", "done", "✅", "☑")
    if not any(marker.casefold() in haystack for marker in completion_markers):
        return {"ok": True, "changed": False, "completed": []}

    def matcher(todo_text: str) -> float:
        return _score_todo_match(todo_text, haystack)

    return _mark_todos_done(session_id, matcher, min_score=0.5)


def upsert_plan_anchor(
    messages: list[dict[str, Any]],
    plan_block: str,
) -> list[dict[str, Any]]:
    """刷新计划锚点消息：折叠时保留在摘要区，优先于可压缩正文。"""
    filtered = [m for m in messages if not is_plan_anchor_message(m)]
    block = (plan_block or "").strip()
    if not block:
        return filtered
    anchor = {
        "role": "user",
        "content": f"{PLAN_ANCHOR_MARKER}\n{block}",
    }
    if not filtered:
        return [anchor]
    if filtered[0].get("role") == "system":
        return [filtered[0], anchor, *filtered[1:]]
    return [anchor, *filtered]


def upsert_plan_anchor_for_session(
    session_id: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    session = get_session(session_id)
    return upsert_plan_anchor(messages, plan_prompt_block(session))


def plan_prompt_block(session: ChatSession | None) -> str:
    if session is None:
        return ""
    plan = (getattr(session, "plan_markdown", "") or "").strip()
    todos = normalize_todos(getattr(session, "todos", None))
    if not plan and not todos:
        return ""
    lines = ["【当前任务计划】"]
    if plan:
        lines.append(plan)
    if todos:
        lines.append("待办：")
        for item in todos:
            mark = "x" if item.get("done") else " "
            lines.append(f"- [{mark}] {item.get('text', '')}")
    lines.append(
        "长任务请严格按上述计划推进；开始前若计划过粗可先 update_session_plan 细化。"
        "完成项用 update_session_todos 标记；信息收集阶段可并行多个只读工具。"
    )
    return "\n".join(lines) + "\n"
