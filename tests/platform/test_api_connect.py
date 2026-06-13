from __future__ import annotations

from friday.api_connect import (
    _auth_status_key,
    _read_auth_status,
    apply_network_environment,
    diagnose_llm,
    format_api_error,
    is_transient_api_error,
    parse_host_port,
    probe_llm_status,
    quick_reachability,
    record_service_status,
)
from friday.error_hints import classify_error
from friday.storage import UserSettings


def test_parse_host_port_https_default():
    host, port, scheme = parse_host_port("https://api.deepseek.com")
    assert host == "api.deepseek.com"
    assert port == 443
    assert scheme == "https"


def test_format_api_error_connection():
    msg = format_api_error("Connection error", context="api_test")
    assert "连接" in msg or "API" in msg
    assert classify_error("Connection error", context="api_test").code == "api_network"


def test_format_api_error_uses_service_label_not_hardcoded_deepseek():
    msg = format_api_error(
        "Error code: 429 - Too many requests",
        context="api_test",
        service="小米 MiMo",
    )
    assert "DeepSeek" not in msg
    assert "429" in msg
    assert "重试" in msg


def test_diagnose_llm_missing_key():
    settings = UserSettings(api_key="", base_url="https://api.deepseek.com")
    steps = diagnose_llm(settings, include_api=False)
    assert steps[0].ok
    assert any(s.name == "DNS 解析" for s in steps)


def test_apply_network_proxy(monkeypatch):
    import os

    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    settings = UserSettings(api_proxy="http://127.0.0.1:7890")
    apply_network_environment(settings)
    assert os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:7890"


def test_quick_reachability_invalid_url():
    ok, detail = quick_reachability("", None)
    assert ok is False
    assert detail


def test_probe_llm_status_not_configured():
    settings = UserSettings(api_key="")
    ok, detail = probe_llm_status(settings)
    assert ok is False
    assert "未配置" in detail


def test_probe_image_gen_status_not_enabled():
    from friday.api_connect import probe_image_gen_status

    settings = UserSettings(image_gen_enabled=False)
    ok, detail = probe_image_gen_status(settings)
    assert ok is False
    assert "未启用" in detail


def test_probe_image_gen_status_uses_lightweight_verify(monkeypatch):
    from friday.api_connect import probe_image_gen_status

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="image2",
        image_gen_base_url="https://next.zhima.world",
    )

    monkeypatch.setattr(
        "friday.api_connect.quick_reachability",
        lambda *_a, **_k: (True, "next.zhima.world 网络可达"),
    )
    monkeypatch.setattr(
        "friday.image_gen.verify_image_gen_api",
        lambda *_a, **_k: (True, "API 认证通过"),
    )

    ok, detail = probe_image_gen_status(settings, force=True)
    assert ok is True
    assert "认证通过" in detail


def test_record_service_status_cached():
    settings = UserSettings(api_key="sk-test-key-123456", base_url="https://api.deepseek.com")
    record_service_status("llm", settings, False, "连接失败")
    cached = _read_auth_status(_auth_status_key("llm", settings), service="llm")
    assert cached is not None
    assert cached[0] is False


def test_image_gen_auth_status_key_uses_default_base_url():
    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="image2",
        image_gen_base_url="",
        image_gen_provider="openai_compat",
    )
    key = _auth_status_key("image_gen", settings)
    assert "https://next.zhima.world" in key
    assert "openai_compat" not in key


def test_probe_image_gen_status_uses_test_cache(monkeypatch):
    from friday.api_connect import probe_image_gen_status

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="image2",
        image_gen_base_url="",
        image_gen_provider="openai_compat",
    )
    record_service_status("image_gen", settings, True, "生图测试通过")

    monkeypatch.setattr(
        "friday.api_connect.quick_reachability",
        lambda *_a, **_k: (False, "should not be called"),
    )

    ok, detail = probe_image_gen_status(settings)
    assert ok is True
    assert "生图测试通过" in detail


def test_save_settings_preserves_image_gen_test_cache():
    from friday.api_connect import invalidate_auth_status_for_settings_change

    before = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_provider="openai_compat",
    )
    after = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_provider="openai_compat",
        workspace="D:/Friday-workspace",
    )
    record_service_status("image_gen", after, True, "生图测试通过，模型可正常调用")
    invalidate_auth_status_for_settings_change(before, after)
    cached = _read_auth_status(_auth_status_key("image_gen", after), service="image_gen")
    assert cached is not None
    assert cached[0] is True


def test_probe_image_gen_status_keeps_ok_cache_on_inconclusive_failure(monkeypatch):
    from friday.api_connect import probe_image_gen_status, record_service_status, _auth_status_key, _read_auth_status

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_provider="openai_compat",
    )
    record_service_status("image_gen", settings, True, "生图测试通过，模型可正常调用")

    def fake_probe(*_args, **_kwargs):
        from friday.api_connect import ConnectivityStep

        return ConnectivityStep("生图 API", False, "生图探测超时（端点响应较慢）", "确认 Key")

    monkeypatch.setattr("friday.api_connect._probe_image_gen_api", fake_probe)

    ok, detail = probe_image_gen_status(settings, force=True)
    assert ok is True
    assert "生图测试通过" in detail
    cached = _read_auth_status(_auth_status_key("image_gen", settings), service="image_gen")
    assert cached is not None
    assert cached[0] is True


def test_test_image_gen_service_preserves_ok_cache_on_soft_failure(monkeypatch):
    from friday.api_connect import test_image_gen_service, record_service_status, _auth_status_key, _read_auth_status

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="gpt-image-2",
        image_gen_base_url="https://next.zhima.world",
    )
    record_service_status("image_gen", settings, True, "生图测试通过，模型「gpt-image-2」可正常调用")

    monkeypatch.setattr(
        "friday.image_gen.test_image_gen_connection",
        lambda *_a, **_k: (False, "生图探测超时（端点响应较慢）"),
    )

    ok, detail = test_image_gen_service(settings)
    assert ok is True
    assert "生图测试通过" in detail
    cached = _read_auth_status(_auth_status_key("image_gen", settings), service="image_gen")
    assert cached is not None
    assert cached[0] is True


def test_test_image_gen_service_overwrites_ok_cache_on_hard_failure(monkeypatch):
    from friday.api_connect import test_image_gen_service, record_service_status, _auth_status_key, _read_auth_status

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="gpt-image-2",
        image_gen_base_url="https://next.zhima.world",
    )
    record_service_status("image_gen", settings, True, "生图测试通过")

    monkeypatch.setattr(
        "friday.image_gen.test_image_gen_connection",
        lambda *_a, **_k: (False, "Error code: 401 - Invalid API key"),
    )

    ok, _detail = test_image_gen_service(settings)
    assert ok is False
    cached = _read_auth_status(_auth_status_key("image_gen", settings), service="image_gen")
    assert cached is not None
    assert cached[0] is False


def test_probe_image_gen_status_quick_failure_does_not_clobber_ok_cache(monkeypatch):
    from friday.api_connect import probe_image_gen_status, record_service_status, _auth_status_key, _read_auth_status

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_provider="openai_compat",
    )
    record_service_status("image_gen", settings, True, "生图测试通过，模型可正常调用")

    def fake_probe(*_args, **_kwargs):
        from friday.api_connect import ConnectivityStep

        return ConnectivityStep("生图 API", False, "所有端点均无法用于生图", "确认 Key")

    monkeypatch.setattr("friday.api_connect._probe_image_gen_api", fake_probe)

    ok, detail = probe_image_gen_status(settings, force=True, quick=True)
    assert ok is True
    assert "生图测试通过" in detail
    cached = _read_auth_status(_auth_status_key("image_gen", settings), service="image_gen")
    assert cached is not None
    assert cached[0] is True


def test_verify_image_gen_api_ark_quick_probe_when_models_inconclusive(tmp_appdata, monkeypatch):
    from friday.image_gen import verify_image_gen_api

    settings = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="ark-test-key-12345678",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_provider="openai_compat",
    )

    monkeypatch.setattr(
        "friday.image_gen._verify_image_gen_models_http",
        lambda *_a, **_k: (None, ""),
    )
    monkeypatch.setattr(
        "friday.image_gen._verify_image_gen_images_auth",
        lambda *_a, **_k: (None, "生图探测超时（端点响应较慢）"),
    )

    ok, message = verify_image_gen_api(settings, timeout=4.0, primary_only=True)
    assert ok is True
    assert "超时" in message or "可达" in message


def test_is_transient_api_error():
    assert is_transient_api_error("httpx.ReadTimeout: read operation timed out") is True
    assert is_transient_api_error("Connection refused") is False
    assert is_transient_api_error("429 Too Many Requests") is True


def test_record_service_status_skips_transient_failure():
    settings = UserSettings(
        api_key="sk-live-key-1234567890",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    record_service_status("llm", settings, True, "对话成功")
    record_service_status("llm", settings, False, "API 响应超时", transient=True)
    cached = _read_auth_status(_auth_status_key("llm", settings), service="llm")
    assert cached is not None
    assert cached[0] is True


def test_test_llm_service_preserves_ok_cache_on_soft_failure(monkeypatch):
    from friday.api_connect import test_llm_service

    settings = UserSettings(
        api_key="sk-live-key-1234567890",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    record_service_status("llm", settings, True, "API 可用")

    class _FailBrain:
        def __init__(self, _settings):
            pass

        def test_connection(self):
            return False, "API 响应超时（端点响应较慢）"

    monkeypatch.setattr("friday.brain.DeepSeekBrain", _FailBrain)

    ok, detail = test_llm_service(settings)
    assert ok is True
    assert "API 可用" in detail
    cached = _read_auth_status(_auth_status_key("llm", settings), service="llm")
    assert cached is not None
    assert cached[0] is True


def test_test_llm_service_overwrites_ok_cache_on_hard_failure(monkeypatch):
    from friday.api_connect import test_llm_service

    settings = UserSettings(
        api_key="sk-live-key-1234567890",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    record_service_status("llm", settings, True, "API 可用")

    class _FailBrain:
        def __init__(self, _settings):
            pass

        def test_connection(self):
            return False, "Error code: 401 - Invalid API key"

    monkeypatch.setattr("friday.brain.DeepSeekBrain", _FailBrain)

    ok, _detail = test_llm_service(settings)
    assert ok is False
    cached = _read_auth_status(_auth_status_key("llm", settings), service="llm")
    assert cached is not None
    assert cached[0] is False


def test_test_vision_service_preserves_ok_cache_on_soft_failure(monkeypatch):
    from friday.api_connect import test_vision_service

    settings = UserSettings(
        vision_enabled=True,
        vision_api_key="ark-test-key-12345678",
        vision_model="ep-test",
    )
    record_service_status("vision", settings, True, "视觉 API 可用")

    monkeypatch.setattr(
        "friday.vision.test_vision_connection",
        lambda *_a, **_k: (False, "视觉探测超时（端点响应较慢）"),
    )

    result = test_vision_service(settings)
    assert result is not None
    ok, detail = result
    assert ok is True
    assert "视觉 API 可用" in detail
    cached = _read_auth_status(_auth_status_key("vision", settings), service="vision")
    assert cached is not None
    assert cached[0] is True


def test_invalidate_probe_cache_can_preserve_auth_status():
    from friday.api_connect import invalidate_probe_cache, read_cached_service_status

    settings = UserSettings(
        api_key="sk-live-key-1234567890",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        vision_enabled=True,
        vision_api_key="ark-test-key-12345678",
        vision_model="ep-test",
    )
    record_service_status("vision", settings, True, "视觉 API 可用")
    invalidate_probe_cache(clear_auth=False)
    cached = read_cached_service_status("vision", settings)
    assert cached is not None
    assert cached[0] is True


def test_llm_test_success_does_not_clear_vision_auth_cache(monkeypatch):
    from friday.api_connect import read_cached_service_status, test_llm_service

    settings = UserSettings(
        api_key="sk-live-key-1234567890",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        vision_enabled=True,
        vision_api_key="ark-test-key-12345678",
        vision_model="ep-test",
    )
    record_service_status("vision", settings, True, "视觉 API 可用")

    class _FakeBrain:
        def __init__(self, _settings):
            pass

        def test_connection(self):
            return True, "API 可用"

    monkeypatch.setattr("friday.brain.DeepSeekBrain", _FakeBrain)
    ok, _msg = test_llm_service(settings)
    assert ok is True
    cached = read_cached_service_status("vision", settings)
    assert cached is not None
    assert cached[0] is True
