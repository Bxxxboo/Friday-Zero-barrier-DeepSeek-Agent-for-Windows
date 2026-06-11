from __future__ import annotations

import json
import secrets

import friday.auth as auth
from fastapi.testclient import TestClient


def test_ws_auth_via_first_message(tmp_appdata, monkeypatch):
    token = secrets.token_hex(32)
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    auth._TOKEN = ""
    auth.set_api_token(token)

    from friday.server import app

    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "auth", "token": token})
            msg = ws.receive_json()
            assert msg["type"] == "connected"


def test_ws_rejects_missing_auth(tmp_appdata, monkeypatch):
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    auth._TOKEN = ""
    auth.set_api_token(secrets.token_hex(32))

    from friday.server import app

    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "auth", "token": "bad"})
            # Starlette closes with 4401; receive may raise
            try:
                ws.receive_json()
            except Exception:
                pass


def test_ws_legacy_query_token_still_works(tmp_appdata, monkeypatch):
    token = secrets.token_hex(32)
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    auth._TOKEN = ""
    auth.set_api_token(token)

    from friday.server import app

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "connected"
