"""Agent 运行时上下文（工具回调用）。"""

from __future__ import annotations

from contextvars import ContextVar

current_session_id: ContextVar[str] = ContextVar("friday_session_id", default="")
