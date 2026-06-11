from __future__ import annotations

import asyncio

from friday.agent import FridayAgent
from friday.server import _agent_cache, get_status_bar
from friday.storage import save_settings, UserSettings


def test_status_bar_payload(tmp_appdata):
    ws = tmp_appdata / "ws"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        vision_enabled=False,
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")

    data = asyncio.run(get_status_bar())
    assert data["api_online"] is True
    assert data["vision_enabled"] is False
    assert data["model"] == "deepseek-chat"
    assert isinstance(data["tokens_total"], int)
    assert isinstance(data["tasks"], int)


def test_status_bar_cached_only_returns_cached_without_probe(tmp_appdata, monkeypatch):
    ws = tmp_appdata / "ws-cache"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        vision_enabled=False,
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-test",
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")
    record_service_status("image_gen", settings, True, "生图测试通过")

    def fail_probe(*_args, **_kwargs):
        raise AssertionError("cached_only 不应触发 live probe")

    monkeypatch.setattr("friday.api_connect.test_llm_service", fail_probe)
    monkeypatch.setattr("friday.api_connect.test_image_gen_service", fail_probe)

    data = asyncio.run(get_status_bar(cached_only=True))
    assert data["api_online"] is True
    assert data["image_gen_online"] is True
    assert data["api_checking"] is False
    assert data["image_gen_checking"] is False


def test_status_bar_skips_image_gen_live_probe_when_cached_ok(tmp_appdata, monkeypatch):
    ws = tmp_appdata / "ws-img-cache"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-test",
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")
    record_service_status("image_gen", settings, True, "生图测试通过")

    def fail_image_probe(*_args, **_kwargs):
        raise AssertionError("已有生图成功缓存时不应再 live probe")

    monkeypatch.setattr("friday.api_connect.test_llm_service", lambda *_a, **_k: (True, "API 可用"))
    monkeypatch.setattr("friday.api_connect.test_image_gen_service", fail_image_probe)

    data = asyncio.run(get_status_bar())
    assert data["image_gen_online"] is True
    assert "生图测试通过" in str(data["image_gen_reach_detail"])


def test_status_bar_gateway_disabled(tmp_appdata):
    ws = tmp_appdata / "ws-gw-off"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        weixin_bridge_enabled=False,
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")

    data = asyncio.run(get_status_bar())
    assert data["gateway_enabled"] is False
    assert data["gateway_online"] is False
    assert "关闭" in str(data["gateway_reach_detail"])


def test_status_bar_gateway_offline_when_bridge_on(tmp_appdata, monkeypatch):
    ws = tmp_appdata / "ws-gw-offline"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        weixin_bridge_enabled=True,
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")
    monkeypatch.setattr(
        "friday.health_check._gateway_service",
        lambda: {
            "status": "degraded",
            "detail": "Gateway 未响应",
            "running": False,
            "port": 18789,
            "cli_available": True,
        },
    )

    data = asyncio.run(get_status_bar())
    assert data["gateway_enabled"] is True
    assert data["gateway_configured"] is True
    assert data["gateway_online"] is False
    assert "Gateway" in str(data["gateway_reach_detail"])


def test_status_bar_session_tokens(tmp_appdata):
    ws = tmp_appdata / "ws2"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
    )
    save_settings(settings)

    agent = FridayAgent(settings, lambda _action: True)
    agent.brain.total_prompt_tokens = 120
    agent.brain.total_completion_tokens = 30
    agent._finalize_usage()

    session_id = "test-session-tokens"
    _agent_cache[session_id] = agent
    try:
        data = asyncio.run(get_status_bar(session_id=session_id))
        assert data["tokens_prompt"] == 120
        assert data["tokens_completion"] == 30
        assert data["tokens_total"] == 150
    finally:
        _agent_cache.pop(session_id, None)
