"""聊天运行时：Agent 缓存、审批、YOLO 与会话锁。"""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import Future
from typing import Any

from fastapi import WebSocket

from friday.approval_narration import build_approval_user_copy, enrich_approval_summary_async
from friday.auth import verify_api_token
from friday.safety import PendingAction, TurnApprovalState, mark_turn_approved, should_request_approval
from friday.sessions import get_session, save_agent_state, session_exists
from friday.storage import UserSettings, load_settings

_approval_waiters: dict[str, Future[bool]] = {}
_approval_sessions: dict[str, str] = {}
_agent_cache: dict[str, Any] = {}
_session_locks: dict[str, asyncio.Lock] = {}
_session_approval: dict[str, TurnApprovalState] = {}
_session_yolo_unlocked: set[str] = set()


def is_session_yolo_unlocked(session_id: str) -> bool:
    return bool(session_id) and session_id in _session_yolo_unlocked


def unlock_session_yolo(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    _session_yolo_unlocked.add(sid)
    return True


def lock_session_yolo(session_id: str) -> None:
    sid = (session_id or "").strip()
    if sid:
        _session_yolo_unlocked.discard(sid)


def clear_session_yolo_unlock(session_id: str | None = None) -> None:
    if session_id:
        lock_session_yolo(session_id)
    else:
        _session_yolo_unlocked.clear()


def _sync_session_approval(session_id: str, agent: Any) -> None:
    if not session_id:
        return
    if session_id in _session_approval:
        agent._turn_approval = _session_approval[session_id]
    else:
        _session_approval[session_id] = agent._turn_approval


def _save_session_approval(session_id: str, agent: Any) -> None:
    if session_id:
        _session_approval[session_id] = agent._turn_approval


def clear_session_approval(session_id: str | None = None) -> None:
    if session_id:
        _session_approval.pop(session_id, None)
        clear_session_yolo_unlock(session_id)
    else:
        _session_approval.clear()
        clear_session_yolo_unlock()


def clear_agent_cache(session_id: str | None = None) -> None:
    """清空 Agent 缓存；settings 变更后应调用。"""
    if session_id:
        _agent_cache.pop(session_id, None)
        clear_session_approval(session_id)
    else:
        _agent_cache.clear()
        clear_session_approval()


def _get_session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def drop_session_lock(session_id: str) -> None:
    _session_locks.pop(session_id, None)


_drop_session_lock = drop_session_lock


def _brain_config_changed(old: UserSettings | None, new: UserSettings) -> bool:
    if old is None:
        return True
    return (
        old.api_key != new.api_key
        or old.base_url != new.base_url
        or old.model != new.model
        or getattr(old, "api_proxy", "") != getattr(new, "api_proxy", "")
        or getattr(old, "api_trust_env", True) != getattr(new, "api_trust_env", True)
    )


def _apply_chat_settings(agent: Any, settings: UserSettings, *, yolo_unlocked: bool = False) -> None:
    from friday.api_connect import apply_network_environment, build_openai_client, invalidate_probe_cache
    from friday.brain import DeepSeekBrain

    apply_network_environment(settings)
    prev = agent.settings
    if agent.brain is None or _brain_config_changed(prev, settings):
        agent.brain = DeepSeekBrain(settings)
        invalidate_probe_cache()
    else:
        agent.brain.settings = settings
        agent.brain.client = build_openai_client(
            settings.api_key,
            settings.base_url,
            settings,
        )
    agent.refresh_prefix_if_needed(settings, yolo_unlocked=yolo_unlocked)


def _get_agent(session_id: str, settings: UserSettings, approval_bridge: Any) -> Any:
    from friday.agent import FridayAgent

    agent = _agent_cache.get(session_id)
    if agent is None:
        session = get_session(session_id)
        agent = FridayAgent(settings, approval_bridge)
        if session:
            agent.load_history(session.agent_messages)
        _agent_cache[session_id] = agent
    else:
        agent.request_approval = approval_bridge
    return agent


def _make_approval_bridge(
    loop: asyncio.AbstractEventLoop,
    emit: Any,
    session_id: str,
) -> Any:
    def approval_bridge(action: PendingAction) -> bool:
        from friday.interaction_modes import normalize_mode, tool_allowed_in_mode
        from friday.safety import ToolDecision

        agent = _agent_cache.get(session_id)
        mode_settings = agent.settings if agent else load_settings()
        mode = normalize_mode(getattr(mode_settings, "interaction_mode", "agent"))
        if not tool_allowed_in_mode(action.tool_name, mode):
            return False

        settings = mode_settings
        state = _session_approval.setdefault(session_id, TurnApprovalState())
        pseudo = ToolDecision(
            allowed=True,
            needs_approval=True,
            large_download=action.large_download,
            untrusted_download=action.untrusted_download,
        )
        if not should_request_approval(settings, pseudo, state):
            return True

        approval_id = str(uuid.uuid4())
        future: Future[bool] = Future()
        _approval_waiters[approval_id] = future
        _approval_sessions[approval_id] = session_id
        plain_summary, preview = build_approval_user_copy(action, settings=settings)
        asyncio.run_coroutine_threadsafe(
            emit(
                "approval_request",
                {
                    "approval_id": approval_id,
                    "summary": plain_summary,
                    "tool_name": action.tool_name,
                    "arguments": action.arguments,
                    "risk": action.risk.value,
                    "large_download": action.large_download,
                    "download_size_bytes": action.download_size_bytes,
                    "untrusted_download": action.untrusted_download,
                    "trust_label": action.trust_label,
                    "preview": preview,
                },
            ),
            loop,
        ).result(timeout=10.0)

        def _on_narrated(summary: str) -> None:
            if approval_id not in _approval_waiters:
                return
            asyncio.run_coroutine_threadsafe(
                emit(
                    "approval_summary_update",
                    {"approval_id": approval_id, "summary": summary},
                ),
                loop,
            )

        enrich_approval_summary_async(
            action,
            settings=settings,
            on_narrated=_on_narrated,
        )
        approved = False
        try:
            while True:
                agent = _agent_cache.get(session_id)
                if agent and agent._cancel_event.is_set():
                    return False
                try:
                    approved = future.result(timeout=0.5)
                    break
                except TimeoutError:
                    continue
        finally:
            _approval_waiters.pop(approval_id, None)
            _approval_sessions.pop(approval_id, None)

        if approved:
            mark_turn_approved(state, pseudo)
        else:
            _session_approval[session_id] = TurnApprovalState()
        return approved

    return approval_bridge


def resolve_approval(approval_id: str, approved: bool) -> bool:
    future = _approval_waiters.pop(approval_id, None)
    _approval_sessions.pop(approval_id, None)
    if future and not future.done():
        future.set_result(approved)
        return True
    return False


_resolve_approval = resolve_approval


def _cancel_session_approvals(session_id: str) -> None:
    for approval_id, sid in list(_approval_sessions.items()):
        if sid == session_id:
            resolve_approval(approval_id, False)


async def run_chat_guarded(
    session_id: str,
    text: str,
    emit: Any,
    loop: asyncio.AbstractEventLoop,
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
    interaction_mode: str = "",
) -> None:
    lock = _get_session_lock(session_id)
    if lock.locked():
        await emit("busy", {"message": "请等待当前任务完成"})
        return
    async with lock:
        await run_chat(
            session_id,
            text,
            emit,
            loop,
            image_path=image_path,
            image_paths=image_paths,
            interaction_mode=interaction_mode,
        )


_run_chat_guarded = run_chat_guarded


def _normalize_image_paths(image_path: str = "", image_paths: list[str] | None = None) -> list[str]:
    paths = [p.strip() for p in (image_paths or []) if (p or "").strip()]
    if not paths and (image_path or "").strip():
        paths = [image_path.strip()]
    return paths


def _compose_user_message(
    text: str,
    vision_summary: str = "",
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
) -> str:
    from friday.vision import compose_chat_message

    return compose_chat_message(
        text,
        image_path,
        vision_summary,
        image_paths=_normalize_image_paths(image_path, image_paths),
    )


async def _prefetch_vision(
    text: str,
    settings: Any,
    emit: Any,
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
) -> str:
    paths = _normalize_image_paths(image_path, image_paths)
    if not paths:
        return ""
    from friday.vision import build_vision_prompt, describe_image, vision_ready

    if not vision_ready(settings):
        return ""

    total = len(paths)
    summaries: list[str] = []
    for idx, path in enumerate(paths, start=1):
        await emit(
            "progress",
            {
                "round": 1,
                "max_rounds": 1,
                "tool_count": total,
                "tools": ["describe_image"],
                "step": idx,
            },
        )
        prompt = build_vision_prompt(text)
        part = await asyncio.to_thread(describe_image, settings, path, prompt)
        label = f"图{idx}" if total > 1 else "截图"
        summaries.append(f"【{label}】\n{part}")
    return "\n\n".join(summaries)


async def run_chat(
    session_id: str,
    text: str,
    emit: Any,
    loop: asyncio.AbstractEventLoop,
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
    interaction_mode: str = "",
) -> None:
    from friday.interaction_modes import normalize_mode

    settings = load_settings()
    if interaction_mode:
        settings = settings.merge({"interaction_mode": normalize_mode(interaction_mode)})
    if not settings.api_ready:
        from friday.error_hints import classify_error, format_user_message

        hint = classify_error("", context="api_key_missing")
        await emit("error", {"message": format_user_message(hint)})
        return

    if not session_id or not session_exists(session_id):
        await emit("error", {"message": "会话不存在，请刷新或新建对话"})
        return

    approval_bridge = _make_approval_bridge(loop, emit, session_id)
    try:
        agent = _get_agent(session_id, settings, approval_bridge)
    except Exception as exc:
        from friday.logging_config import get_logger

        get_logger("chat").exception("Agent 初始化失败")
        from friday.api_connect import format_api_error
        from friday.model_providers import llm_service_label

        await emit(
            "error",
            {"message": format_api_error(exc, context="api_test", service=llm_service_label(settings))},
        )
        return
    yolo_unlocked = (
        normalize_mode(settings.interaction_mode) == "yolo"
        and is_session_yolo_unlocked(session_id)
    )
    _apply_chat_settings(agent, settings, yolo_unlocked=yolo_unlocked)
    _sync_session_approval(session_id, agent)
    agent.operation_meta = {
        "session_id": session_id,
        "trigger": "chat",
        "schedule_id": "",
    }
    await emit("agent_step", {"message": "正在理解你的请求…"})

    paths = _normalize_image_paths(image_path, image_paths)
    vision_summary = await _prefetch_vision(
        text,
        settings,
        emit,
        image_path=image_path,
        image_paths=paths,
    )
    user_message = _compose_user_message(
        text,
        vision_summary,
        image_path=image_path,
        image_paths=paths,
    )

    from friday.plan import plan_prompt_block

    session = get_session(session_id)
    plan_block = plan_prompt_block(session)
    if plan_block:
        user_message = f"{plan_block}\n{user_message}"

    def on_event(event_type: str, payload: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(emit(event_type, payload), loop)

    def worker() -> str:
        return agent.run(user_message, on_event=on_event)

    try:
        result = await asyncio.to_thread(worker)
        saved = save_agent_state(session_id, agent.messages, user_text=user_message)
        from friday.api_connect import record_service_status

        record_service_status("llm", settings, True, "对话成功")
        await emit(
            "assistant",
            {
                "content": result,
                "session": {
                    "id": saved.id,
                    "title": saved.title,
                    "updated_at": saved.updated_at,
                },
                "usage": agent.usage_snapshot(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        from friday.api_connect import format_api_error, is_transient_api_error, record_service_status
        from friday.model_providers import llm_service_label

        err_msg = format_api_error(
            exc, context="api_test", service=llm_service_label(settings)
        )
        record_service_status(
            "llm",
            settings,
            False,
            err_msg.split("\n")[0],
            transient=is_transient_api_error(exc),
        )
        await emit("error", {"message": err_msg})
    finally:
        _save_session_approval(session_id, agent)
        await emit("status", {"message": "就绪"})


_run_chat = run_chat


async def verify_ws_token(websocket: WebSocket) -> bool:
    token = websocket.query_params.get("token") or websocket.headers.get("x-friday-token")
    if verify_api_token(token):
        return True
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except (TimeoutError, ValueError):
        return False
    if str(data.get("type", "")).strip() != "auth":
        return False
    return verify_api_token(str(data.get("token", "")).strip() or None)


_verify_ws_token = verify_ws_token
