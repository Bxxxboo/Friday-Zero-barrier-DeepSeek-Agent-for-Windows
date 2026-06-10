"""POST /api/sessions/{id}/activate 响应校验。"""

from fastapi.testclient import TestClient

import friday.server as server_mod
from friday.auth import ensure_api_token
from friday.sessions import create_session, list_sessions


def test_activate_session_returns_ok(tmp_appdata):
    server_mod._backend_ready = True
    client = TestClient(server_mod.app)
    token = ensure_api_token()
    headers = {"X-Friday-Token": token}

    session = create_session(title="激活测试")
    other = create_session(title="另一条")

    res = client.post(f"/api/sessions/{other.id}/activate", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["active_session_id"] == other.id

    _, active_id = list_sessions()
    assert active_id == other.id

    res = client.post(f"/api/sessions/{session.id}/activate", headers=headers)
    assert res.status_code == 200
    assert res.json()["active_session_id"] == session.id


def test_activate_missing_session_404(tmp_appdata):
    server_mod._backend_ready = True
    client = TestClient(server_mod.app)
    token = ensure_api_token()
    headers = {"X-Friday-Token": token}

    res = client.post("/api/sessions/no-such-id/activate", headers=headers)
    assert res.status_code == 404
