"""会话 Plan / Todo 管理（可移植，存于 session JSON）。"""

from __future__ import annotations

import time
import uuid
from typing import Any

from friday.logging_config import get_logger
from friday.sessions import ChatSession, get_session, save_session_fields

_log = get_logger("plan")


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
    lines.append("长任务请按上述计划推进，完成项可调用 update_session_todos 标记。")
    return "\n".join(lines) + "\n"
