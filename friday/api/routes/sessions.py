"""会话 CRUD、计划、检查点、分叉与历史搜索路由。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from friday.api.chat_runtime import (
    _agent_cache,
    clear_session_approval,
    drop_session_lock,
)
from friday.api.schemas import (
    LocalStorageMigrationPayload,
    SessionCreatePayload,
    SessionDetailResponse,
    SessionListResponse,
    SessionPlanPayload,
    SessionRenamePayload,
    SessionSummaryResponse,
)
from friday.api.session_helpers import session_to_detail
from friday.sessions import (
    create_session,
    delete_session,
    ensure_default_session,
    get_session,
    list_sessions,
    migrate_local_storage,
    rename_session,
    session_exists,
    set_active_session,
)


def register_sessions_routes(app: FastAPI) -> None:
    @app.get("/api/sessions/{session_id}/plan")
    async def get_session_plan_api(session_id: str) -> dict[str, Any]:
        from friday.plan import get_session_plan

        result = get_session_plan(session_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail="会话不存在")
        return result

    @app.put("/api/sessions/{session_id}/plan")
    async def put_session_plan_api(session_id: str, payload: SessionPlanPayload) -> dict[str, Any]:
        from friday.plan import update_session_plan

        if not session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        return update_session_plan(
            session_id,
            plan_markdown=payload.plan_markdown,
            todos=payload.todos,
        )

    @app.post("/api/sessions/{session_id}/plan/sync")
    async def sync_session_plan_api(session_id: str) -> dict[str, Any]:
        from friday.plan import sync_todos_from_plan

        if not session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        result = sync_todos_from_plan(session_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail="会话不存在")
        return result

    @app.get("/api/sessions/{session_id}/checkpoint")
    async def get_session_checkpoint_api(session_id: str) -> dict[str, Any]:
        if not session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        from friday.checkpoint_writer import read_checkpoint

        return read_checkpoint(session_id)

    @app.post("/api/sessions/{session_id}/fork", response_model=SessionDetailResponse)
    async def fork_session_api(session_id: str) -> SessionDetailResponse:
        from friday.sessions import fork_session

        if not session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        child = fork_session(session_id)
        if child is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        set_active_session(child.id)
        _agent_cache.pop(child.id, None)
        return session_to_detail(child)

    @app.get("/api/history/search")
    async def search_history_api(q: str = "", limit: int = 30) -> dict[str, Any]:
        from friday.history_index import search_messages

        hits = search_messages(q, limit=min(max(limit, 1), 100))
        return {"ok": True, "query": q, "hits": hits}

    @app.get("/api/sessions", response_model=SessionListResponse)
    async def api_list_sessions() -> SessionListResponse:
        from friday.weixin.sessions import is_weixin_session

        summaries, active = list_sessions()
        if not summaries:
            session = ensure_default_session()
            summaries = [session.to_summary()]
            active = session.id
        return SessionListResponse(
            sessions=[
                SessionSummaryResponse(
                    id=item.id,
                    title=item.title,
                    updated_at=item.updated_at,
                    created_at=item.created_at,
                    is_weixin=is_weixin_session(item.id),
                )
                for item in summaries
            ],
            active_session_id=active,
        )

    @app.post("/api/sessions/migrate-local")
    async def api_migrate_local_storage(payload: LocalStorageMigrationPayload) -> dict[str, Any]:
        if not payload.sessions:
            return {"ok": True, "imported": 0, "skipped": 0, "active_session_id": ""}
        result = migrate_local_storage(payload.sessions, payload.active_session_id.strip())
        return {"ok": True, **result}

    @app.post("/api/sessions", response_model=SessionDetailResponse)
    async def api_create_session(payload: SessionCreatePayload | None = None) -> SessionDetailResponse:
        title = payload.title if payload else "新对话"
        session = create_session(title=title)
        set_active_session(session.id)
        _agent_cache.pop(session.id, None)
        return session_to_detail(session)

    @app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    async def api_get_session(session_id: str) -> SessionDetailResponse:
        session = get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return session_to_detail(session)

    @app.delete("/api/sessions/{session_id}")
    async def api_delete_session(session_id: str) -> dict[str, Any]:
        _agent_cache.pop(session_id, None)
        clear_session_approval(session_id)
        drop_session_lock(session_id)
        next_session, next_id = delete_session(session_id)
        detail = session_to_detail(next_session) if next_session else None
        return {"ok": True, "active_session_id": next_id, "session": detail}

    @app.post("/api/sessions/{session_id}/activate")
    async def api_activate_session(session_id: str) -> dict[str, Any]:
        if not session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        set_active_session(session_id)
        return {"ok": True, "active_session_id": session_id}

    @app.patch("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    async def api_rename_session(session_id: str, payload: SessionRenamePayload) -> SessionDetailResponse:
        if not session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="名称不能为空")
        try:
            session = rename_session(session_id, title)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return session_to_detail(session)
