"""对话、审批、生图预览、生成物与 WebSocket 路由。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from friday.api.chat_runtime import (
    _agent_cache,
    _cancel_session_approvals,
    is_session_yolo_unlocked,
    lock_session_yolo,
    resolve_approval,
    run_chat_guarded,
    unlock_session_yolo,
    verify_ws_token,
)
from friday.api.schemas import (
    ApprovalPayload,
    CancelPayload,
    PasteImagePayload,
    PasteImageResponse,
    YoloUnlockPayload,
)
from friday.sessions import session_exists
from friday.storage import load_settings


def register_chat_routes(app: FastAPI) -> None:
    @app.post("/api/chat/paste-image", response_model=PasteImageResponse)
    async def paste_chat_image(payload: PasteImagePayload) -> PasteImageResponse:
        from friday.paste_images import save_pasted_image

        cfg = load_settings()
        try:
            path, filename = await asyncio.to_thread(
                save_pasted_image,
                cfg,
                image_base64=payload.image_base64,
                data_url=payload.data_url,
                mime_type=payload.mime_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PasteImageResponse(path=path, filename=filename)

    @app.get("/api/artifacts/summary")
    async def api_artifacts_summary() -> dict[str, Any]:
        from friday.artifacts import storage_summary

        return await asyncio.to_thread(storage_summary)

    @app.post("/api/artifacts/gc")
    async def api_artifacts_gc(dry_run: bool = False) -> dict[str, Any]:
        from friday.artifacts import run_gc

        return await asyncio.to_thread(run_gc, dry_run=dry_run)

    @app.get("/api/chat/generated-image")
    async def get_generated_image(path: str, preview: int = 0) -> Response:
        from friday.image_gen import guess_image_media_type, render_preview_bytes, resolve_generated_image_path

        raw = (path or "").strip()
        if not raw:
            raise HTTPException(status_code=400, detail="缺少 path")
        cfg = load_settings()
        try:
            target = await asyncio.to_thread(resolve_generated_image_path, raw, cfg)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        if preview:
            data, media_type = await asyncio.to_thread(render_preview_bytes, target)
            return Response(content=data, media_type=media_type)

        return FileResponse(target, media_type=guess_image_media_type(target))

    @app.post("/api/chat/approve")
    async def approve_chat(payload: ApprovalPayload) -> dict[str, bool]:
        ok = resolve_approval(payload.approval_id, payload.approved)
        return {"ok": ok}

    @app.post("/api/chat/cancel")
    async def cancel_chat(payload: CancelPayload) -> dict[str, bool]:
        session_id = payload.session_id.strip()
        agent = _agent_cache.get(session_id)
        if agent:
            agent.cancel()
            _cancel_session_approvals(session_id)
            return {"ok": True}
        return {"ok": False}

    @app.get("/api/chat/yolo-unlock/{session_id}")
    async def get_yolo_unlock(session_id: str) -> dict[str, bool]:
        return {"unlocked": is_session_yolo_unlocked(session_id.strip())}

    @app.post("/api/chat/yolo-unlock")
    async def post_yolo_unlock(payload: YoloUnlockPayload) -> dict[str, bool]:
        session_id = payload.session_id.strip()
        if not session_id or not session_exists(session_id):
            raise HTTPException(status_code=400, detail="会话不存在")
        return {"ok": unlock_session_yolo(session_id)}

    @app.delete("/api/chat/yolo-unlock/{session_id}")
    async def delete_yolo_unlock(session_id: str) -> dict[str, bool]:
        lock_session_yolo(session_id.strip())
        return {"ok": True}

    @app.websocket("/ws/chat")
    async def chat_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        if not await verify_ws_token(websocket):
            await websocket.close(code=4401, reason="Unauthorized")
            return
        loop = asyncio.get_running_loop()
        from friday.ws_broadcast import register_ws_client, unregister_ws_client

        async def send(event_type: str, payload: dict[str, Any] | None = None) -> None:
            body = {"type": event_type}
            if payload:
                body.update(payload)
            await websocket.send_json(body)

        register_ws_client(loop, send)
        await send("connected")

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "approval_response":
                    resolve_approval(str(data.get("approval_id", "")), bool(data.get("approved")))
                    continue

                if msg_type != "chat":
                    continue

                text = str(data.get("message", "")).strip()
                session_id = str(data.get("session_id", "")).strip()
                interaction_mode = str(data.get("interaction_mode", "")).strip()
                raw_paths = data.get("image_paths")
                if isinstance(raw_paths, list):
                    image_paths = [str(p).strip() for p in raw_paths if str(p).strip()]
                else:
                    image_paths = []
                image_path = str(data.get("image_path", "")).strip()
                if not image_paths and image_path:
                    image_paths = [image_path]
                if not text and not image_paths:
                    continue

                asyncio.create_task(
                    run_chat_guarded(
                        session_id,
                        text,
                        send,
                        loop,
                        image_path=image_paths[0] if len(image_paths) == 1 else "",
                        image_paths=image_paths,
                        interaction_mode=interaction_mode,
                    )
                )
        except WebSocketDisconnect:
            pass
        finally:
            unregister_ws_client(loop, send)
