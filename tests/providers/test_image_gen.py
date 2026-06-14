from __future__ import annotations

from unittest.mock import MagicMock, patch

from pathlib import Path

import pytest

from friday.image_gen import (
    default_base_url,
    extract_path_from_tool_result,
    format_generate_result,
    generate_image,
    image_gen_ready,
    masked_image_gen_key,
    resolve_generated_image_path,
    resolve_image_gen_size,
    resolve_image_gen_timeouts,
    verify_image_gen_api,
    _is_ark_image_gen_endpoint,
    _should_skip_images_probe,
)
import friday.image_gen as image_gen_module
from friday.safety import ToolDecision, evaluate_tool, should_request_approval, TurnApprovalState
from friday.storage import UserSettings, save_settings


def _minimal_png(width: int = 64, height: int = 64) -> bytes:
    import io

    from PIL import Image

    img = Image.new("RGB", (width, height), color=(120, 80, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _settings(**kwargs) -> UserSettings:
    base = UserSettings(
        image_gen_enabled=True,
        image_gen_api_key="sk-test-key-12345678",
        image_gen_model="test-model",
        image_gen_base_url="https://next.zhima.world",
        workspace="",
    )
    return base.merge(kwargs)


def test_image_gen_ready_requires_model(tmp_appdata):
    assert not image_gen_ready(_settings(image_gen_model=""))
    assert image_gen_ready(_settings())


def test_masked_image_gen_key(tmp_appdata):
    masked = masked_image_gen_key(_settings())
    assert masked.startswith("sk-t")
    assert "..." in masked


def test_default_base_url_provider(tmp_appdata):
    assert "zhima" in default_base_url(_settings(image_gen_provider="openai_compat"))
    assert "ark" in default_base_url(_settings(image_gen_provider="ark", image_gen_base_url=""))

    relay = "https://relay.example.com/v1"
    inherited = default_base_url(
        _settings(
            image_gen_provider="openai_compat",
            image_gen_base_url="",
            base_url=relay,
        )
    )
    assert inherited == relay

    explicit_zhima = default_base_url(
        _settings(
            image_gen_provider="openai_compat",
            image_gen_base_url=UserSettings.image_gen_base_url,
            base_url=relay,
        )
    )
    assert explicit_zhima == UserSettings.image_gen_base_url.strip().rstrip("/")

    explicit = default_base_url(
        _settings(
            image_gen_provider="openai_compat",
            image_gen_base_url="https://other-relay.example.com/v1",
            base_url=relay,
        )
    )
    assert explicit == "https://other-relay.example.com/v1"


def test_generate_image_not_ready(tmp_appdata):
    result = generate_image(_settings(image_gen_enabled=False), "a cat")
    assert result["ok"] is False
    assert "未配置" in result["error"]


def test_normalize_size_upgrades_for_mimo_host(tmp_appdata):
    from friday.image_gen import _minimum_pixels, _parse_min_pixels_from_error, _pick_size_for_pixels

    settings = _settings(
        image_gen_provider="openai_compat",
        image_gen_base_url="https://api.xiaomimimo.com/v1",
        image_gen_model="seedream",
        image_gen_default_size="1024x1024",
    )
    assert _minimum_pixels(settings) == 3_686_400
    assert resolve_image_gen_size("", settings) == "1920x1920"
    assert _pick_size_for_pixels(3_686_400, "1280x720") == "2560x1440"
    assert _parse_min_pixels_from_error("requires at least 3,686,400 pixels") == 3_686_400


def test_resolve_image_gen_timeouts_scale_with_resolution(tmp_appdata):
    small_settings = _settings(
        image_gen_model="test-model",
        image_gen_default_size="1024x1024",
    )
    large_settings = _settings(
        image_gen_model="gpt-image-2",
        image_gen_default_size="4096x4096",
        image_gen_fallback_urls="https://backup.example.com",
    )
    small_tool, small_http, small_per_url = resolve_image_gen_timeouts(small_settings, "1024x1024")
    large_tool, large_http, large_per_url = resolve_image_gen_timeouts(
        large_settings,
        "",
        prompt="4K 电影级壁纸",
    )
    assert small_tool == 120
    assert large_tool > small_tool
    assert large_tool >= 360
    assert large_http > small_http
    assert large_per_url <= large_http
    assert large_per_url < large_tool


def test_tool_timeout_generate_image_uses_dynamic_budget(tmp_appdata):
    from friday.tools.registry import _tool_timeout

    save_settings(
        _settings(
            image_gen_model="gpt-image-2",
            image_gen_default_size="3840x2160",
        )
    )
    timeout = _tool_timeout(
        "generate_image",
        {"prompt": "龙与城堡", "size": "3840x2160"},
    )
    assert timeout >= 480


def test_resolve_image_gen_size_defaults_to_1k_without_explicit_request(tmp_appdata):
    settings = _settings(
        image_gen_model="test-model",
        image_gen_default_size="4096x4096",
    )
    assert resolve_image_gen_size("", settings) == "1024x1024"
    assert resolve_image_gen_size("", settings, prompt="吉卜力风格浮空船") == "1024x1024"


def test_resolve_image_gen_size_honors_explicit_tool_size(tmp_appdata):
    settings = _settings(
        image_gen_provider="mimo",
        image_gen_base_url="https://api.xiaomimimo.com/v1",
        image_gen_default_size="2048x2048",
    )
    assert resolve_image_gen_size("", settings) == "1920x1920"
    assert resolve_image_gen_size("1920x1920", settings) == "1920x1920"


def test_resolve_image_gen_size_from_8k_prompt(tmp_appdata):
    settings = _settings(image_gen_default_size="1920x1920")
    prompt = "龙骑士与银龙，8K分辨率，电影级光影"
    assert resolve_image_gen_size("1920x1920", settings, prompt=prompt) == "7680x4320"
    assert resolve_image_gen_size("8k", settings) == "7680x4320"
    assert resolve_image_gen_size("", settings, prompt="4k画质壁纸") == "3840x2160"


def test_image2_caps_8k_to_4k(tmp_appdata):
    settings = _settings(
        image_gen_model="image2",
        image_gen_base_url="https://next.zhima.world",
        image_gen_default_size="4096x4096",
    )
    prompt = "龙骑士，8K分辨率"
    assert resolve_image_gen_size("", settings) == "1024x1024"
    assert resolve_image_gen_size("", settings, prompt=prompt) == "3840x2160"
    assert resolve_image_gen_size("8k", settings) == "3840x2160"
    assert resolve_image_gen_size("4096x4096", settings) == "3840x2160"
    assert resolve_image_gen_size("", settings, prompt="4K 壁纸") == "3840x2160"


def test_infer_size_from_prompt_explicit_dimensions(tmp_appdata):
    from friday.image_gen import _infer_size_from_prompt

    assert _infer_size_from_prompt("壁纸 5120×2880 超宽") == "5120x2880"


def test_step_down_size(tmp_appdata):
    from friday.image_gen import _step_down_size

    assert _step_down_size("7680x4320") == "4096x4096"
    image2 = _settings(image_gen_model="image2", image_gen_base_url="https://next.zhima.world")
    assert _step_down_size("3840x2160", settings=image2) == "2048x2048"


def test_describe_approval_uses_explicit_image_size(tmp_appdata):
    from friday.safety import describe_approval_plain

    save_settings(_settings(image_gen_default_size="2048x2048"))
    text = describe_approval_plain(
        "generate_image",
        {"prompt": "书房", "size": "1920x1920"},
    )
    assert "1920x1920" in text


def test_generate_image_retries_larger_size(tmp_appdata, monkeypatch):
    calls: list[str] = []
    settings = _settings(image_gen_default_size="1024x1024")

    with patch("friday.image_gen._call_images_api") as mock_api:
        def side_effect(**kwargs):
            size = kwargs["size"]
            calls.append(size)
            if size == "1024x1024":
                raise RuntimeError("at least 3,686,400 pixels")
            return _minimal_png(1920, 1920)

        mock_api.side_effect = side_effect
        result = generate_image(settings, "a cat")

    assert result["ok"] is True
    assert calls == ["1024x1024", "1920x1920"]
    assert result["size"] == "1920x1920"


def test_generate_image_reports_actual_size_when_upstream_is_smaller(tmp_appdata, monkeypatch):
    settings = _settings(
        image_gen_model="image2",
        image_gen_default_size="3840x2160",
    )

    with patch("friday.image_gen._call_images_api") as mock_api:
        mock_api.return_value = _minimal_png(1672, 941)
        result = generate_image(settings, "dragon knight", size="3840x2160")

    assert result["ok"] is True
    assert result["size"] == "1672x941"
    assert result["requested_size"] == "3840x2160"
    assert "1672×941" in result["size_warning"]
    text = format_generate_result(result)
    assert "实际尺寸：1672x941" in text
    assert "请求尺寸：3840x2160" in text


def test_generate_image_saves_file(tmp_appdata, monkeypatch):
    fake_png = _minimal_png(1024, 1024)

    mock_response = MagicMock()
    mock_response.data = [MagicMock(b64_json=__import__("base64").b64encode(fake_png).decode(), url=None)]

    mock_client = MagicMock()
    mock_client.images.generate.return_value = mock_response

    with patch("friday.image_gen._images_client", return_value=mock_client):
        result = generate_image(_settings(), "a cute cat", filename="test-cat.png")

    assert result["ok"] is True
    path = __import__("pathlib").Path(result["path"])
    assert path.is_file()
    assert path.name == "test-cat.png"
    assert format_generate_result(result).startswith("已生成图片")


def test_generate_image_records_service_status_on_success(tmp_appdata, monkeypatch):
    from friday.api_connect import _auth_status_key, _read_auth_status

    fake_png = _minimal_png(1024, 1024)
    mock_response = MagicMock()
    mock_response.data = [MagicMock(b64_json=__import__("base64").b64encode(fake_png).decode(), url=None)]
    mock_client = MagicMock()
    mock_client.images.generate.return_value = mock_response
    settings = _settings()

    with patch("friday.image_gen._images_client", return_value=mock_client):
        result = generate_image(settings, "a cute cat")

    assert result["ok"] is True
    cached = _read_auth_status(_auth_status_key("image_gen", settings), service="image_gen")
    assert cached is not None
    assert cached[0] is True
    assert "对话生图成功" in cached[1]


def test_generate_image_preserves_existing_test_status(tmp_appdata, monkeypatch):
    from friday.api_connect import _auth_status_key, _read_auth_status, record_service_status

    fake_png = _minimal_png(1024, 1024)
    mock_response = MagicMock()
    mock_response.data = [MagicMock(b64_json=__import__("base64").b64encode(fake_png).decode(), url=None)]
    mock_client = MagicMock()
    mock_client.images.generate.return_value = mock_response
    settings = _settings()
    record_service_status("image_gen", settings, True, "生图测试通过，模型「gpt-image-2」可正常调用")

    with patch("friday.image_gen._images_client", return_value=mock_client):
        result = generate_image(settings, "a cute cat")

    assert result["ok"] is True
    cached = _read_auth_status(_auth_status_key("image_gen", settings), service="image_gen")
    assert cached is not None
    assert "测试" in cached[1]
    assert "对话生图成功" not in cached[1]


def test_generate_image_fallback_urls(tmp_appdata, monkeypatch):
    fake_png = _minimal_png(1024, 1024)
    calls: list[str] = []

    def fake_client(api_key, base_url, settings=None, **kwargs):
        calls.append(base_url)

        if len(calls) == 1:
            raise RuntimeError("primary failed")

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(b64_json=__import__("base64").b64encode(fake_png).decode(), url=None)
        ]
        mock_client_inst = MagicMock()
        mock_client_inst.images.generate.return_value = mock_response
        return mock_client_inst

    settings = _settings(
        image_gen_fallback_urls="https://backup.example.com",
    )
    with patch("friday.image_gen._images_client", side_effect=fake_client):
        result = generate_image(settings, "sunset")

    assert result["ok"] is True
    assert len(calls) == 2


def test_generate_image_always_requires_approval(tmp_appdata):
    settings = UserSettings(
        require_approval_writes=True,
        approve_once_per_turn=True,
        image_gen_enabled=True,
    )
    decision = evaluate_tool(settings, "generate_image", {"prompt": "a logo"})
    assert decision.needs_approval is True
    assert decision.always_require_approval is True

    state = TurnApprovalState(general=True)
    assert should_request_approval(settings, decision, state) is True


def test_extract_path_from_tool_result():
    text = "已生成图片并保存：E:/docs/星期五/生成的图片/a.png\n尺寸：1024x1024"
    assert extract_path_from_tool_result(text) == "E:/docs/星期五/生成的图片/a.png"
    assert extract_path_from_tool_result("失败") is None


def test_resolve_generated_image_path(tmp_appdata):
    settings = _settings()
    from friday.storage import resolved_workspace

    ws = Path(resolved_workspace(settings))
    img = ws / "生成的图片" / "sample.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"\x89PNG\r\n")
    resolved = resolve_generated_image_path(str(img), settings)
    assert resolved == img.resolve()


def test_should_skip_images_probe_for_ark(tmp_appdata):
    ark_settings = _settings(image_gen_provider="ark")
    base = "https://ark.cn-beijing.volces.com/api/v3"
    assert _should_skip_images_probe(base, ark_settings)
    assert _should_skip_images_probe(base, ark_settings, strict=True) is False
    assert _should_skip_images_probe("https://example.com", _settings(image_gen_provider="openai_compat")) is False


def test_is_ark_image_gen_endpoint_detects_ep_and_volces(tmp_appdata):
    ep_settings = _settings(
        image_gen_provider="openai_compat",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
    )
    assert _is_ark_image_gen_endpoint(ep_settings)
    assert not _is_ark_image_gen_endpoint(_settings(image_gen_model="dall-e-3"))


def test_verify_models_http_ark_ep_not_in_list_defers_to_images(tmp_appdata, monkeypatch):
    import json
    import urllib.error

    class _FakeResp:
        status = 200

        def read(self, _n: int = -1) -> bytes:
            payload = {"data": [{"id": "some-other-model"}]}
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("friday.api_connect.urlopen_request", lambda *_a, **_k: _FakeResp())

    settings = _settings(
        image_gen_provider="openai_compat",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
    )
    ok, msg = image_gen_module._verify_image_gen_models_http(
        "ark-test-key",
        settings.image_gen_base_url,
        settings,
        timeout=3.0,
        strict=True,
    )
    assert ok is None
    assert msg == ""


def test_verify_image_gen_api_ark_strict_uses_images_when_models_misses_ep(tmp_appdata, monkeypatch):
    calls: list[str] = []

    def fake_models(*_a, **_k):
        calls.append("models")
        return None, ""

    def fake_images(*_a, **_k):
        calls.append("images")
        return True, "生图端点可用，模型「ep-20260609235327-pf4mr」可正常调用（探测尺寸 1920x1920）"

    monkeypatch.setattr("friday.image_gen._verify_image_gen_models_http", fake_models)
    monkeypatch.setattr("friday.image_gen._verify_image_gen_images_auth", fake_images)

    ok, message = verify_image_gen_api(
        _settings(
            image_gen_provider="openai_compat",
            image_gen_api_key="ark-test-key-12345678",
            image_gen_model="ep-20260609235327-pf4mr",
            image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        ),
        strict=True,
        primary_only=True,
    )
    assert ok is True
    assert "可正常调用" in message
    assert calls == ["models", "images"]


def test_verify_image_gen_api_prefers_models_http(tmp_appdata, monkeypatch):
    calls: list[str] = []

    def fake_models(*_a, **_k):
        calls.append("models")
        return True, "API 认证通过"

    def fake_images(*_a, **_k):
        calls.append("images")
        return True, "生图 API 认证通过"

    monkeypatch.setattr("friday.image_gen._verify_image_gen_models_http", fake_models)
    monkeypatch.setattr("friday.image_gen._verify_image_gen_images_auth", fake_images)

    ok, message = verify_image_gen_api(_settings(), primary_only=True)
    assert ok is True
    assert "认证通过" in message
    assert calls == ["models"]
    assert "images" not in calls


def test_test_image_gen_connection_skips_short_probe(tmp_appdata, monkeypatch):
    client_calls: list[float] = []
    verify_calls: list[object] = []

    monkeypatch.setattr(
        "friday.image_gen.verify_image_gen_api",
        lambda *_a, **_k: verify_calls.append(True) or (False, "should not run"),
    )
    monkeypatch.setattr(
        "friday.image_gen._strict_test_via_images_client",
        lambda _settings, *, timeout: client_calls.append(timeout) or (False, "client failed"),
    )

    with patch("friday.image_gen.generate_image") as mock_generate:
        ok, _message = image_gen_module.test_image_gen_connection(_settings())
        assert not ok
        assert verify_calls == []
        assert client_calls
        assert client_calls[0] >= 120
        mock_generate.assert_not_called()


def test_test_image_gen_connection_uses_full_client_timeout(tmp_appdata, monkeypatch):
    client_calls: list[float] = []

    monkeypatch.setattr(
        "friday.image_gen._strict_test_via_images_client",
        lambda _settings, *, timeout: client_calls.append(timeout)
        or (True, "生图测试通过，模型「gpt-image-2」可正常调用（探测尺寸 1024x1024）"),
    )

    ok, msg = image_gen_module.test_image_gen_connection(_settings())
    assert ok
    assert "可正常调用" in msg
    assert client_calls
    assert client_calls[0] >= 120


def test_test_image_gen_connection_ark_uses_client_probe(tmp_appdata, monkeypatch):
    client_calls: list[float] = []
    verify_calls: list[object] = []

    monkeypatch.setattr(
        "friday.image_gen._strict_test_via_images_client",
        lambda _settings, *, timeout: client_calls.append(timeout) or (
            True,
            "生图测试通过，模型「ep-20260609235327-pf4mr」可正常调用（探测尺寸 1920x1920）",
        ),
    )
    monkeypatch.setattr(
        "friday.image_gen.verify_image_gen_api",
        lambda *_a, **_k: verify_calls.append(True) or (False, "should not run"),
    )

    ok, msg = image_gen_module.test_image_gen_connection(
        _settings(
            image_gen_api_key="ark-test-key-12345678",
            image_gen_model="ep-20260609235327-pf4mr",
            image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
    )
    assert ok
    assert "可正常调用" in msg
    assert client_calls
    assert client_calls[0] >= 120
    assert verify_calls == []


def test_format_image_gen_failures_multi_endpoint():
    from friday.image_gen import _format_image_gen_failures

    msg = _format_image_gen_failures(
        [
            (
                "https://next.zhima.world",
                "Error code: 503 - {'error': {'message': 'No available compatible accounts', 'type': 'api_error'}}",
            ),
            (
                "https://api.iotwq.top/v1",
                "Error code: 401 - {'code': 'INVALID_API_KEY', 'message': 'Invalid API key'}",
            ),
        ]
    )
    assert "所有生图地址均不可用" in msg
    assert "next.zhima.world" in msg
    assert "api.iotwq.top" in msg
    assert "503" in msg or "通道" in msg
    assert "Key" in msg
    assert "生图 API Key 无效" not in msg


def test_humanize_html_404_client_error():
    from friday.image_gen import _humanize_image_gen_client_error

    msg = _humanize_image_gen_client_error(
        "<html><head><title>404 Not Found</title></head><body>openresty</body></html>",
        settings=_settings(
            image_gen_base_url="https://next.zhima.world",
            image_gen_fallback_urls="https://api.iotwq.top/v1",
        ),
    )
    assert "404" in msg
    assert "next.zhima.world" in msg
    assert "<html>" not in msg


def test_humanize_insufficient_balance_not_key_invalid():
    from friday.image_gen import _humanize_image_gen_http_error

    msg = _humanize_image_gen_http_error(
        403,
        "{'code': 'INSUFFICIENT_BALANCE', 'message': 'Insufficient account balance'}",
        base_url="https://api.iotwq.top/v1",
        model="gpt-image-2",
    )
    assert "余额不足" in msg
    assert "Key 无效" not in msg
    assert "api.iotwq.top" in msg


def test_strict_test_tries_all_candidate_base_urls(tmp_appdata, monkeypatch):
    captured: list[list[str]] = []

    def fake_call(**kwargs):
        captured.append(kwargs["base_urls"])
        return b"x" * 128

    monkeypatch.setattr(image_gen_module, "_call_images_api", fake_call)
    ok, _msg = image_gen_module._strict_test_via_images_client(
        _settings(
            image_gen_base_url="https://primary.example/v1",
            image_gen_fallback_urls="https://backup.example/v1",
        ),
        timeout=60,
    )
    assert ok
    assert len(captured) == 1
    assert len(captured[0]) >= 2
    assert "https://primary.example/v1" in captured[0]
    assert "https://backup.example/v1" in captured[0]


def test_humanize_image_gen_http_error_ep_404():
    from friday.image_gen import _humanize_image_gen_http_error

    msg = _humanize_image_gen_http_error(
        404,
        '{"error":{"message":"endpoint not found"}}',
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-20260609014727-895pn",
    )
    assert "ep-20260609014727-895pn" in msg
    assert "HTTP 404" not in msg


def test_image_gen_config_hint_rejects_sk_on_ark():
    from friday.image_gen import image_gen_config_hint

    hint = image_gen_config_hint(
        _settings(
            image_gen_provider="ark",
            image_gen_api_key="sk-wrong-key-12345678",
            image_gen_model="ep-abc",
        )
    )
    assert "ark-" in hint


def test_resolve_image_gen_size_clamps_8k_for_ark_ep(tmp_appdata):
    from friday.image_gen import _pixel_count

    settings = _settings(
        image_gen_provider="ark",
        image_gen_model="ep-20260609014727-895pn",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
    )
    size = resolve_image_gen_size("8k", settings)
    assert _pixel_count(size) <= 16_777_216


def test_humanize_image_gen_size_error_in_chinese():
    from friday.image_gen import _humanize_image_gen_http_error

    msg = _humanize_image_gen_http_error(
        400,
        '{"error":{"message":"The parameter `size` specified in the request is not valid: '
        'image size must be at least 3686400 pixels."}}',
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-test",
        settings=_settings(image_gen_provider="ark", image_gen_model="ep-test"),
    )
    assert "尺寸过小" in msg
    assert "3,686,400" in msg
    assert "1920" in msg
    assert "The parameter" not in msg


def test_verify_images_auth_retries_larger_size(tmp_appdata, monkeypatch):
    import json
    import urllib.error

    calls: list[str] = []

    class _FakeResp:
        status = 200

        def read(self, _n: int = -1) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(req, **_k):
        payload = json.loads(req.data.decode("utf-8"))
        calls.append(payload["size"])
        if payload["size"] == "1024x1024":
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            )
        return _FakeResp()

    monkeypatch.setattr("friday.api_connect.urlopen_request", fake_urlopen)
    monkeypatch.setattr(
        "friday.image_gen._read_http_error_body",
        lambda _exc: (
            '{"error":{"message":"image size must be at least 3686400 pixels"}}'
        ),
    )

    ok, msg = image_gen_module._verify_image_gen_images_auth(
        "sk-test-key-12345678",
        "https://example.com",
        _settings(image_gen_model="test-model", image_gen_provider="openai_compat"),
        timeout=3.0,
        strict=True,
    )
    assert ok is True
    assert calls[0] == "1024x1024"
    assert calls[-1] != "1024x1024"
    assert "可正常调用" in msg


def test_verify_images_auth_strict_does_not_treat_400_as_success(tmp_appdata, monkeypatch):
    import urllib.error

    def fake_urlopen(*_a, **_k):
        raise urllib.error.HTTPError(
            url="https://example.com/images/generations",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("friday.api_connect.urlopen_request", fake_urlopen)
    monkeypatch.setattr(
        "friday.image_gen._read_http_error_body",
        lambda _exc: '{"error":{"message":"model not found"}}',
    )

    ok, msg = image_gen_module._verify_image_gen_images_auth(
        "sk-test-key-12345678",
        "https://example.com",
        _settings(image_gen_model="bad-model"),
        timeout=3.0,
        strict=True,
    )
    assert ok is False
    assert "HTTP 400" not in msg
