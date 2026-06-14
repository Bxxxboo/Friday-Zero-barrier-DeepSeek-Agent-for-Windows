"""向已连接的桌面 WebSocket 客户端广播会话变更。"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable, Callable

SendFn = Callable[[str, dict[str, Any] | None], Awaitable[None]]

_lock = threading.Lock()
_clients: list[tuple[asyncio.AbstractEventLoop, SendFn]] = []


def register_ws_client(loop: asyncio.AbstractEventLoop, send: SendFn) -> None:
    with _lock:
        _clients.append((loop, send))


def unregister_ws_client(loop: asyncio.AbstractEventLoop, send: SendFn) -> None:
    with _lock:
        _clients[:] = [
            (client_loop, client_send)
            for client_loop, client_send in _clients
            if not (client_loop is loop and client_send is send)
        ]


def _dispatch(event_type: str, payload: dict[str, Any] | None = None) -> None:
    with _lock:
        targets = list(_clients)
    for loop, send in targets:
        try:
            asyncio.run_coroutine_threadsafe(send(event_type, payload), loop)
        except RuntimeError:
            continue


def notify_session_updated(session_id: str, *, source: str = "") -> None:
    """线程安全：微信后台线程也可调用。"""
    sid = (session_id or "").strip()
    if not sid:
        return
    payload: dict[str, Any] = {"session_id": sid}
    if source:
        payload["source"] = source
    _dispatch("session_updated", payload)


def notify_sessions_changed() -> None:
    """通知前端刷新侧边栏会话列表（新建微信会话等）。"""
    _dispatch("sessions_updated", {})


def notify_schedule_completed(
    *,
    schedule_id: str,
    session_id: str,
    title: str,
    status: str,
    message: str,
) -> None:
    """定时任务执行结束后通知桌面端刷新会话与任务列表。"""
    payload: dict[str, Any] = {
        "schedule_id": (schedule_id or "").strip(),
        "session_id": (session_id or "").strip(),
        "title": (title or "").strip(),
        "status": (status or "").strip(),
        "message": (message or "")[:500],
    }
    _dispatch("schedule_completed", payload)
