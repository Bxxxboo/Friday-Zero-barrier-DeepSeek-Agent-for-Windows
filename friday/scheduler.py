"""后台定时调度 —— 每分钟检查到期任务并执行。"""

from __future__ import annotations

import threading
import time

from friday.logging_config import get_logger
from friday.schedules import due_schedules, mark_schedule_run
from friday.task_runner import run_scheduled_prompt

_log = get_logger("scheduler")

_thread: threading.Thread | None = None
_stop = threading.Event()
_running_ids: set[str] = set()
_lock = threading.Lock()
_gateway_health_ticks = 0
_gc_ticks = 0


def _notify_schedule_result(
    *,
    schedule_id: str,
    session_id: str,
    title: str,
    status: str,
    message: str,
) -> None:
    try:
        from friday.ws_broadcast import notify_schedule_completed, notify_session_updated, notify_sessions_changed

        if session_id:
            notify_session_updated(session_id, source="schedule")
        notify_sessions_changed()
        notify_schedule_completed(
            schedule_id=schedule_id,
            session_id=session_id,
            title=title,
            status=status,
            message=message,
        )
    except Exception:
        _log.exception("定时任务结果通知失败 | id=%s", schedule_id)


def _execute_task(task_id: str, title: str, prompt: str) -> None:
    with _lock:
        if task_id in _running_ids:
            return
        _running_ids.add(task_id)

    try:
        status, message, session_id = run_scheduled_prompt(
            prompt,
            session_title=f"[定时] {title}",
            schedule_id=task_id,
            trigger="scheduled",
        )
        mark_schedule_run(task_id, status=status, message=message)
        _notify_schedule_result(
            schedule_id=task_id,
            session_id=session_id,
            title=title,
            status=status,
            message=message,
        )
        _log.info("定时任务完成 | id=%s status=%s", task_id, status)
    except Exception:
        _log.exception("定时任务异常 | id=%s", task_id)
        mark_schedule_run(task_id, status="error", message="执行异常，请查看日志")
    finally:
        with _lock:
            _running_ids.discard(task_id)


def run_schedule_now(schedule_id: str) -> tuple[str, str]:
    """手动立即执行一条定时任务。"""
    from friday.schedules import get_schedule

    task = get_schedule(schedule_id)
    if task is None:
        return "error", "任务不存在"

    with _lock:
        if schedule_id in _running_ids:
            return "error", "该任务正在执行中"
        _running_ids.add(schedule_id)

    try:
        status, message, session_id = run_scheduled_prompt(
            task.prompt,
            session_title=f"[定时] {task.title}",
            schedule_id=schedule_id,
            trigger="scheduled",
        )
        mark_schedule_run(schedule_id, status=status, message=message)
        _notify_schedule_result(
            schedule_id=schedule_id,
            session_id=session_id,
            title=task.title,
            status=status,
            message=message,
        )
        return status, message
    finally:
        with _lock:
            _running_ids.discard(schedule_id)


def _maybe_ensure_openclaw_gateway() -> None:
    global _gateway_health_ticks
    from friday.storage import load_settings

    if not getattr(load_settings(), "weixin_bridge_enabled", True):
        return
    _gateway_health_ticks += 1
    if _gateway_health_ticks < 2:
        if _gateway_health_ticks == 1:
            from friday.weixin.gateway import ensure_weixin_gateway_with_retries, probe_gateway

            if not probe_gateway():
                ensure_weixin_gateway_with_retries(attempts=2, delay_sec=3.0)
        return
    if _gateway_health_ticks < 5:
        return
    _gateway_health_ticks = 0

    from friday.weixin.gateway import ensure_gateway_running_background, probe_gateway

    if probe_gateway():
        return
    ensure_gateway_running_background()


def _tick() -> None:
    global _gc_ticks
    now = time.time()
    _maybe_ensure_openclaw_gateway()
    _gc_ticks += 1
    if _gc_ticks >= 30:
        _gc_ticks = 0
        try:
            from friday.artifacts import run_gc
            from friday.storage import load_settings

            run_gc(settings=load_settings())
        except Exception:
            _log.exception("定时生成物回收失败")
    for task in due_schedules(now):
        _log.info("触发定时任务 | id=%s title=%s", task.id, task.title)
        worker = threading.Thread(
            target=_execute_task,
            args=(task.id, task.title, task.prompt),
            daemon=True,
        )
        worker.start()


def _loop() -> None:
    _log.info("定时调度器已启动")
    while not _stop.is_set():
        try:
            _tick()
        except Exception:
            _log.exception("定时调度 tick 失败")
        _stop.wait(60)


def start_scheduler() -> None:
    """在桌面应用启动后调用，后台每分钟检查一次。"""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="friday-scheduler")
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()
