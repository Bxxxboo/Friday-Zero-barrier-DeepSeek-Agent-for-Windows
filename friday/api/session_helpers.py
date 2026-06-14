"""会话 API 的详情转换。"""

from __future__ import annotations

from friday.api.schemas import DisplayMessageResponse, GeneratedImageRef, SessionDetailResponse
from friday.sessions import ChatSession, session_display_messages


def session_to_detail(session: ChatSession) -> SessionDetailResponse:
    display = session_display_messages(session)
    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        updated_at=session.updated_at,
        created_at=session.created_at,
        plan_markdown=getattr(session, "plan_markdown", "") or "",
        todos=list(getattr(session, "todos", None) or []),
        messages=[
            DisplayMessageResponse(
                role=item["role"],
                content=item["content"],
                generated_images=[
                    GeneratedImageRef(path=str(img.get("path", "")))
                    for img in item.get("generated_images") or []
                    if str(img.get("path", "")).strip()
                ],
            )
            for item in display
        ],
    )


_session_to_detail = session_to_detail
