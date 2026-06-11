"""健康检查端点测试（M4.3）。"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import friday.server as server_mod
from friday.health_check import build_health_payload


def test_health_payload_starting_when_backend_not_ready():
    payload = build_health_payload(backend_ready=False)
    assert payload["status"] == "starting"
    assert payload["services"]["backend"]["status"] == "starting"


def test_health_payload_includes_service_states(tmp_appdata):
    with patch("friday.health_check._webview_service", return_value={"status": "ok", "detail": "wv", "installed": True}):
        with patch(
            "friday.health_check._gateway_service",
            return_value={
                "status": "degraded",
                "detail": "Gateway 未响应",
                "running": False,
                "port": 18789,
                "cli_available": True,
            },
        ):
            with patch(
                "friday.health_check._python_env_service",
                return_value={"status": "ok", "detail": "已就绪", "ready": True, "setup_running": False},
            ):
                payload = build_health_payload(backend_ready=True)

    assert payload["status"] == "ok"
    assert payload["degraded"] is True
    services = payload["services"]
    assert services["backend"]["status"] == "ok"
    assert services["webview"]["status"] == "ok"
    assert services["gateway"]["status"] == "degraded"
    assert services["python_env"]["status"] == "ok"


def test_api_health_returns_subservices(tmp_appdata):
    server_mod._backend_ready = True
    client = TestClient(server_mod.app)

    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    services = data.get("services") or {}
    for name in ("backend", "webview", "gateway", "python_env"):
        assert name in services
        assert services[name]["status"] in {"ok", "degraded", "skipped", "starting"}


def test_api_health_starting_before_backend_ready(tmp_appdata):
    server_mod._backend_ready = False
    client = TestClient(server_mod.app)

    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "starting"
    assert data["services"]["backend"]["status"] == "starting"
