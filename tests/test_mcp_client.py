from __future__ import annotations

from friday.mcp_client import default_mcp_config, load_mcp_config, save_mcp_config


def test_mcp_config_roundtrip(tmp_path, monkeypatch):
    from friday import mcp_client as mod

    monkeypatch.setattr(mod, "mcp_config_path", lambda: tmp_path / "mcp_servers.json")
    cfg = default_mcp_config()
    cfg["servers"] = [{"id": "s1", "name": "Test", "command": "echo", "args": [], "enabled": True}]
    save_mcp_config(cfg)
    loaded = load_mcp_config()
    assert len(loaded["servers"]) == 1
    assert loaded["servers"][0]["name"] == "Test"
