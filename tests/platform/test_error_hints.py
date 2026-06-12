from __future__ import annotations

import pytest

from friday.error_hints import (
    build_test_response,
    classify_error,
    format_error_hint,
    format_user_message,
    resolve_error_context,
)


def test_classify_backend_starting():
    hint = classify_error("", context="backend_starting")
    assert hint.code == "backend_starting"
    assert "启动" in hint.detail
    assert hint.hint


def test_classify_pythonnet():
    hint = classify_error("ImportError: Python.Runtime")
    assert hint.code == "runtime_lib"
    assert "VC++" in hint.detail or "运行库" in hint.detail


def test_classify_multipart():
    hint = classify_error("No module named 'multipart'")
    assert hint.code == "missing_multipart"


def test_classify_api_network():
    hint = classify_error("Connection timed out", context="api_test")
    assert hint.code == "api_network"


def test_classify_api_read_timeout():
    hint = classify_error("httpx.ReadTimeout: read operation timed out", context="api_test")
    assert hint.code == "api_timeout"
    assert "超时" in hint.detail


def test_classify_image_gen_read_timeout():
    hint = classify_error("httpx.ReadTimeout: read operation timed out", context="image_gen")
    assert hint.code == "api_timeout"
    assert "生图" in hint.detail


def test_classify_api_rate_limit():
    hint = classify_error(
        "Error code: 429 - {'error': {'message': 'Too many requests'}}",
        context="api_test",
    )
    assert hint.code == "api_rate_limit"
    assert "429" in hint.detail
    assert "重试" in hint.hint


def test_classify_auth_401():
    hint = classify_error("Unauthorized", context="auth_401")
    assert hint.code == "auth_401"
    assert "本地认证" in hint.detail


def test_classify_remote_unauthorized_not_local_auth():
    hint = classify_error("Error code: 401 - Unauthorized", context="api_test")
    assert hint.code == "api_auth"
    assert hint.code != "auth_401"


def test_classify_image_gen_unauthorized():
    hint = classify_error("Error code: 401 - Unauthorized", context="image_gen")
    assert hint.code == "image_gen_auth"
    assert hint.detail == "生图 API Key 无效"


def test_classify_insufficient_balance_not_auth():
    raw = "Error code: 403 - {'code': 'INSUFFICIENT_BALANCE', 'message': 'Insufficient account balance'}"
    hint = classify_error(raw, context="image_gen")
    assert hint.code == "api_balance"
    assert "余额" in hint.detail
    assert hint.code != "image_gen_auth"


def test_classify_vision_unauthorized():
    hint = classify_error("Error code: 401 - Unauthorized", context="vision")
    assert hint.code == "vision_auth"
    assert "视觉" in hint.detail


def test_classify_image_gen_via_service_prefix():
    hint = classify_error("生图 API: Unauthorized", context="api_test")
    assert hint.code == "image_gen_auth"


def test_classify_api_key_missing():
    hint = classify_error("", context="api_key_missing")
    assert hint.code == "api_key_missing"


def test_format_user_message_includes_hint():
    hint = classify_error("", context="backend_starting")
    text = format_user_message(hint)
    assert hint.detail in text
    assert hint.hint in text


def test_resolve_error_context_from_service():
    assert resolve_error_context(service="生图 API") == "image_gen"
    assert resolve_error_context(service="视觉 API") == "vision"
    assert resolve_error_context(service="DeepSeek") == "llm"


def test_format_error_hint_uses_service_context():
    hint = format_error_hint("Error code: 401 - Unauthorized", service="视觉 API")
    assert hint.code == "vision_auth"


def test_build_test_response_success():
    payload = build_test_response(True, "连接成功", service="DeepSeek")
    assert payload["ok"] is True
    assert payload["message"] == "连接成功"
    assert payload["code"] == "ok"


def test_build_test_response_preserves_existing_hint_lines():
    payload = build_test_response(
        False,
        "无法连接 API 服务器\n请检查网络与防火墙",
        service="DeepSeek",
    )
    assert payload["ok"] is False
    assert payload["message"] == "无法连接 API 服务器"
    assert "防火墙" in payload["hint"]


def test_build_test_response_classifies_technical_error():
    payload = build_test_response(
        False,
        "Error code: 401 - Unauthorized",
        service="生图 API",
        context="image_gen",
    )
    assert payload["ok"] is False
    assert payload["message"] == "生图 API Key 无效"
    assert payload["code"] == "image_gen_auth"
    assert payload["hint"]


def test_build_test_response_preserves_multi_endpoint_image_gen():
    payload = build_test_response(
        False,
        "所有生图地址均不可用：\n"
        "· next.zhima.world：暂无可用通道(503)\n"
        "· api.iotwq.top：Key 对此中转无效\n"
        "请为每个中转填写匹配的 Key，或只保留支持 gpt-image-2 且有余额的主地址",
        service="生图 API",
        context="image_gen",
    )
    assert payload["code"] == "image_gen_endpoints"
    assert "next.zhima.world" in payload["message"]
    assert payload["message"] != "生图 API Key 无效"


def test_build_test_response_keeps_user_facing_message():
    payload = build_test_response(
        False,
        "请先勾选「启用生图」",
        service="生图 API",
        context="image_gen",
    )
    assert payload["message"] == "请先勾选「启用生图」"
