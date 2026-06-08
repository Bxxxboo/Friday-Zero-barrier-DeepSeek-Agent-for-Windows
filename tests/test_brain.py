from __future__ import annotations

from unittest.mock import patch

from friday.brain import DeepSeekBrain, build_system_prompt, resolve_max_context, _CONTEXT_MARKER
from friday.storage import UserSettings


def test_brain_lazy_encoder():
    brain = DeepSeekBrain(UserSettings(api_key="sk-test", model="deepseek-chat"))
    assert brain._encoder_initialized is False
    with patch.object(DeepSeekBrain, "_init_encoder", return_value=None) as init:
        brain.count_tokens([{"role": "user", "content": "hello"}])
        init.assert_called_once()
    assert brain._encoder_initialized is True


def test_resolve_max_context_fallback():
    settings = UserSettings(model="deepseek-chat")
    assert resolve_max_context(settings) == 64_000


def test_build_system_prompt_cache_marker():
    prompt = build_system_prompt(UserSettings(api_key="sk-test"))
    marker_idx = prompt.index(_CONTEXT_MARKER)
    assert prompt.index("你是「星期五」") < marker_idx
    assert "本机常用文件夹路径" in prompt[marker_idx:]


def test_resolve_max_context_from_api():
    settings = UserSettings(model="deepseek-chat", api_key="sk-test")

    class FakeModel:
        max_context_tokens = 120_000

    class FakeClient:
        class models:
            @staticmethod
            def retrieve(_model: str):
                return FakeModel()

    assert resolve_max_context(settings, client=FakeClient()) == 120_000
