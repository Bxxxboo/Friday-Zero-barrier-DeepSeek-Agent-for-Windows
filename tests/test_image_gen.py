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
)
from friday.safety import ToolDecision, evaluate_tool, should_request_approval, TurnApprovalState
from friday.storage import UserSettings


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


def test_generate_image_not_ready(tmp_appdata):
    result = generate_image(_settings(image_gen_enabled=False), "a cat")
    assert result["ok"] is False
    assert "未配置" in result["error"]


def test_generate_image_saves_file(tmp_appdata, monkeypatch):
    fake_png = b"\x89PNG\r\n\x1a\n" + b"x" * 200

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


def test_generate_image_fallback_urls(tmp_appdata, monkeypatch):
    fake_png = b"\x89PNG\r\n\x1a\n" + b"y" * 200
    calls: list[str] = []

    def fake_client(api_key, base_url):
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
