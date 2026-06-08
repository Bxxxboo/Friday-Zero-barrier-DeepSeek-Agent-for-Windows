"""Plan / Todo 工具。"""

from __future__ import annotations

import json
from typing import Any

from friday.agent_context import current_session_id
from friday.plan import update_session_plan
from friday.tools._decorators import register_tool


@register_tool(
    name="update_session_plan",
    description="更新当前会话的任务计划（Markdown）。长任务开始前或计划变更时使用。",
    parameters={
        "type": "object",
        "properties": {
            "plan_markdown": {
                "type": "string",
                "description": "Markdown 格式的任务计划",
            },
        },
        "required": ["plan_markdown"],
    },
)
def update_session_plan_tool(plan_markdown: str) -> str:
    session_id = current_session_id.get()
    if not session_id:
        return "当前无活动会话，无法更新计划"
    result = update_session_plan(session_id, plan_markdown=plan_markdown)
    if not result.get("ok"):
        return str(result.get("message") or "更新失败")
    return "已更新任务计划"


@register_tool(
    name="update_session_todos",
    description="更新当前会话待办列表（JSON 数组：[{text, done}]）。",
    parameters={
        "type": "object",
        "properties": {
            "todos_json": {
                "type": "string",
                "description": 'JSON 数组，如 [{"text":"步骤1","done":false}]',
            },
        },
        "required": ["todos_json"],
    },
)
def update_session_todos_tool(todos_json: str) -> str:
    session_id = current_session_id.get()
    if not session_id:
        return "当前无活动会话，无法更新待办"
    try:
        raw = json.loads(todos_json)
    except json.JSONDecodeError as exc:
        return f"JSON 无效: {exc}"
    if not isinstance(raw, list):
        return "todos_json 必须是数组"
    todos: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            todos.append({
                "text": str(item.get("text", "")),
                "done": bool(item.get("done", False)),
            })
    result = update_session_plan(session_id, todos=todos)
    if not result.get("ok"):
        return str(result.get("message") or "更新失败")
    return f"已更新 {len(todos)} 条待办"
