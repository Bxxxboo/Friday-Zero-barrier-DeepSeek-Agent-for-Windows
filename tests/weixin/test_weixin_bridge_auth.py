from __future__ import annotations

import json

import friday.auth as auth
from friday.auth import ensure_api_token, set_api_token
from friday.weixin.config import read_bridge_config, write_bridge_config


def test_write_bridge_config_matches_runtime_token(tmp_appdata, monkeypatch):
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    auth._TOKEN = ""
    monkeypatch.setenv("FRIDAY_PORT", "8765")
    set_api_token("a" * 64)
    write_bridge_config(8765, ensure_api_token())
    cfg = read_bridge_config()
    assert cfg is not None
    assert cfg["port"] == 8765
    assert "token" not in cfg
    assert cfg["token_file"] == "api_token.txt"
    assert cfg["base_url"] == "http://127.0.0.1:8765"


def test_sync_bridge_config_from_runtime(tmp_appdata, monkeypatch):
    monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
    auth._TOKEN = ""
    monkeypatch.setenv("FRIDAY_PORT", "8777")
    set_api_token("b" * 64)
    from friday.weixin.config import sync_bridge_config_from_runtime

    path = sync_bridge_config_from_runtime()
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["port"] == 8777
    assert "token" not in data
    assert data["token_file"] == "api_token.txt"
