"""微信长任务进度文案 —— plan 待办完成时推送简短进度。"""

from __future__ import annotations

from typing import Any

from friday.plan import normalize_todos, todo_key


def collect_newly_completed_todos(
    done_keys: set[str],
    todos: list[dict[str, Any]] | None,
) -> tuple[list[str], set[str]]:
    """返回本轮新完成的待办文案，并更新 done key 集合。"""
    updated = set(done_keys)
    newly: list[str] = []
    for item in normalize_todos(todos):
        text = str(item.get("text", "")).strip()
        if not text or not item.get("done"):
            continue
        key = todo_key(text)
        if key in updated:
            continue
        updated.add(key)
        newly.append(text)
    return newly, updated


def format_weixin_task_progress(completed: list[str], todos: list[dict[str, Any]] | None) -> str:
    items = normalize_todos(todos)
    open_count = sum(1 for t in items if not t.get("done"))
    lines = ["【进度】"]
    for text in completed[:3]:
        lines.append(f"✓ {text}")
    if len(completed) > 3:
        lines.append(f"✓ …另有 {len(completed) - 3} 项已完成")
    if open_count:
        lines.append(f"还剩 {open_count} 项")
    else:
        lines.append("待办已全部完成")
    return "\n".join(lines)
