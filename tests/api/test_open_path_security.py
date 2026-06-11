from __future__ import annotations

import secrets
from pathlib import Path

import friday.auth as auth
from fastapi.testclient import TestClient


def _client_with_token(monkeypatch, tmp_appdata, token: str) -> TestClient:
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    auth._TOKEN = ""
    auth.set_api_token(token)
    from friday.server import app

    return TestClient(app)


def test_open_path_allows_workspace_file(tmp_appdata, monkeypatch):
    token = secrets.token_hex(32)
    client = _client_with_token(monkeypatch, tmp_appdata, token)
    workspace = Path(tmp_appdata) / "workspace"
    workspace.mkdir(parents=True)
    target = workspace / "note.txt"
    target.write_text("hi", encoding="utf-8")

    from friday.storage import load_settings, save_settings

    cfg = load_settings()
    save_settings(cfg.merge({"workspace": str(workspace)}))

    res = client.post(
        "/api/open-path",
        json={"path": str(target)},
        headers={"X-Friday-Token": token},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_open_path_rejects_outside_workspace(tmp_appdata, monkeypatch):
    token = secrets.token_hex(32)
    client = _client_with_token(monkeypatch, tmp_appdata, token)
    outside = Path(tmp_appdata) / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    from friday.storage import load_settings, save_settings

    workspace = Path(tmp_appdata) / "workspace"
    workspace.mkdir(parents=True)
    cfg = load_settings()
    save_settings(cfg.merge({"workspace": str(workspace)}))

    res = client.post(
        "/api/open-path",
        json={"path": str(outside)},
        headers={"X-Friday-Token": token},
    )
    assert res.status_code == 403


def test_index_does_not_inline_api_token(tmp_appdata, monkeypatch):
    token = secrets.token_hex(32)
    client = _client_with_token(monkeypatch, tmp_appdata, token)

    res = client.get("/")
    assert res.status_code == 200
    assert f'window.__FRIDAY_TOKEN__="{token}"' not in res.text
    assert token not in res.text
