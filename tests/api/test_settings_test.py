"""POST /api/settings/test 异常兜底。"""

from unittest.mock import patch

from fastapi.testclient import TestClient

import friday.server as server_mod
from friday.auth import ensure_api_token


def test_settings_test_returns_json_on_merge_failure(tmp_appdata, monkeypatch):
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    import friday.auth as auth

    auth._TOKEN = ""
    server_mod._backend_ready = True
    client = TestClient(server_mod.app)
    token = ensure_api_token()
    headers = {"X-Friday-Token": token, "Content-Type": "application/json"}

    with patch.object(server_mod, "_merge_payload", side_effect=RuntimeError("boom")):
        res = client.post("/api/settings/test", headers=headers, json={"api_key": "sk-x"})

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert data["message"]
    assert data["code"]
