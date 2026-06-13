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
    assert data["context_tokens"] == 0
    assert data["max_context"] > 0
    assert data["context_budget"] > 0
    assert data["compact_threshold"] > 0
    assert data["budget_ratio"] == 0.0


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


def test_status_bar_cached_only_image_gen_without_cache_shows_checking(tmp_appdata):
    from friday.api_connect import _AUTH_STATUS_CACHE, _PROBE_LOCK

    with _PROBE_LOCK:
        _AUTH_STATUS_CACHE.clear()

    ws = tmp_appdata / "ws-img-pending"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="gpt-image-2",
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")

    data = asyncio.run(get_status_bar(cached_only=True))
    assert data["image_gen_checking"] is True
    assert data["image_gen_online"] is False


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


def test_status_bar_gateway_online_when_account_ready(tmp_appdata, monkeypatch):
    ws = tmp_appdata / "ws-gw-account"
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

    class _FakeAccount:
        account_id = "wx-test"

    monkeypatch.setattr("friday.weixin.gateway.probe_gateway", lambda **_k: False)
    monkeypatch.setattr("friday.weixin.gateway.cli_available", lambda: True)
    monkeypatch.setattr("friday.weixin.client.discover_account", lambda *_a, **_k: _FakeAccount())

    data = asyncio.run(get_status_bar())
    assert data["gateway_online"] is True
    assert "微信通道已登录" in str(data["gateway_reach_detail"])


def test_status_bar_gateway_online_when_remote_mapping_exists(tmp_appdata, monkeypatch):
    ws = tmp_appdata / "ws-gw-remote"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        weixin_bridge_enabled=True,
    )
    save_settings(settings)
    from friday.api_connect import record_service_status
    from friday.paths import get_appdata_dir

    record_service_status("llm", settings, True, "API 可用")

    mapping_path = get_appdata_dir() / "weixin_sessions.json"
    mapping_path.write_text('{"wx-test::peer-1": "sess-remote"}', encoding="utf-8")

    monkeypatch.setattr("friday.weixin.gateway.probe_gateway", lambda **_k: False)
    monkeypatch.setattr("friday.weixin.gateway.cli_available", lambda: True)
    monkeypatch.setattr("friday.weixin.client.discover_account", lambda *_a, **_k: None)

    data = asyncio.run(get_status_bar())
    assert data["gateway_online"] is True
    assert "remote" in str(data["gateway_reach_detail"]).lower()


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
    monkeypatch.setattr("friday.weixin.gateway.probe_gateway", lambda **_k: False)
    monkeypatch.setattr("friday.weixin.gateway.cli_available", lambda: True)
    monkeypatch.setattr("friday.weixin.client.discover_account", lambda *_a, **_k: None)
    monkeypatch.setattr("friday.weixin.sessions.has_weixin_mappings", lambda: False)

    data = asyncio.run(get_status_bar())
    assert data["gateway_enabled"] is True
    assert data["gateway_configured"] is True
    assert data["gateway_online"] is False
    assert "Gateway" in str(data["gateway_reach_detail"])


def test_status_bar_cached_only_without_cache_shows_checking(tmp_appdata):
    from friday.api_connect import _AUTH_STATUS_CACHE, _PROBE_LOCK

    with _PROBE_LOCK:
        _AUTH_STATUS_CACHE.clear()

    ws = tmp_appdata / "ws-no-cache"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
        vision_enabled=True,
        vision_api_key="ark-test-key-12345678",
        vision_model="ep-test-vision",
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-test",
    )
    save_settings(settings)

    data = asyncio.run(get_status_bar(cached_only=True))
    assert data["api_checking"] is True
    assert data["vision_checking"] is True
    assert data["image_gen_checking"] is True


def test_status_bar_cached_only_llm_without_cache_shows_checking(tmp_appdata):
    from friday.api_connect import _AUTH_STATUS_CACHE, _PROBE_LOCK

    with _PROBE_LOCK:
        _AUTH_STATUS_CACHE.clear()

    ws = tmp_appdata / "ws-llm-pending"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
    )
    save_settings(settings)

    data = asyncio.run(get_status_bar(cached_only=True))
    assert data["api_checking"] is True
    assert data["api_online"] is False


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
        assert data["context_tokens"] > 0
        assert data["max_context"] == 64_000
        assert data["context_budget"] == int(64_000 * 0.85)
        assert 0.0 < data["budget_ratio"] < 1.0
    finally:
        _agent_cache.pop(session_id, None)


def test_status_bar_session_context_from_persisted_session(tmp_appdata):
    from friday.sessions import create_session, save_session_fields

    ws = tmp_appdata / "ws-ctx"
    ws.mkdir()
    settings = UserSettings(
        api_key="sk-fake-key-for-testing1234567890",
        model="deepseek-chat",
        workspace=str(ws),
    )
    save_settings(settings)
    from friday.api_connect import record_service_status

    record_service_status("llm", settings, True, "API 可用")

    session = create_session(title="上下文测试", activate=False)
    save_session_fields(
        session.id,
        agent_messages=[
            {"role": "system", "content": "你是星期五"},
            {"role": "user", "content": "读取 E:\\Friday\\README.md 并总结"},
        ],
    )

    data = asyncio.run(get_status_bar(session_id=session.id))
    assert data["context_tokens"] > 0
    assert data["budget_ratio"] > 0.0
