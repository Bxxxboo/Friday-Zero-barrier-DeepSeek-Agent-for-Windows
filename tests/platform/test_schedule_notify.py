from __future__ import annotations

from unittest.mock import patch

import pytest

from friday.ws_broadcast import notify_schedule_completed


def test_notify_schedule_completed_dispatches():
    sent: list[tuple[str, dict | None]] = []

    def fake_dispatch(event_type: str, payload: dict | None = None) -> None:
        sent.append((event_type, payload))

    with patch("friday.ws_broadcast._dispatch", side_effect=fake_dispatch):
        notify_schedule_completed(
            schedule_id="sched-1",
            session_id="sess-1",
            title="每周整理",
            status="ok",
            message="已完成",
        )

    assert sent == [
        (
            "schedule_completed",
            {
                "schedule_id": "sched-1",
                "session_id": "sess-1",
                "title": "每周整理",
                "status": "ok",
                "message": "已完成",
            },
        )
    ]
