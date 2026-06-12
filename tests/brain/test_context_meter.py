from __future__ import annotations

from friday.brain import compute_context_meter, resolve_max_context
from friday.storage import UserSettings


def test_compute_context_meter_empty_messages():
    settings = UserSettings(model="deepseek-chat", api_key="sk-test-key-1234567890")
    meter = compute_context_meter(settings, None)
    assert meter["context_tokens"] == 0
    assert meter["budget_ratio"] == 0.0
    assert meter["max_context"] == resolve_max_context(settings)
    assert meter["context_budget"] == int(meter["max_context"] * 0.85)
    assert meter["compact_threshold"] == int(meter["context_budget"] * 0.80)


def test_compute_context_meter_with_messages_increases_tokens():
    settings = UserSettings(model="deepseek-chat", api_key="sk-test-key-1234567890")
    messages = [
        {"role": "system", "content": "你是星期五"},
        {"role": "user", "content": "帮我整理桌面上的文件，路径在 C:\\Users\\me\\Desktop"},
        {"role": "assistant", "content": "好的，我先列出目录。"},
    ]
    meter = compute_context_meter(settings, messages, tool_definitions=[])
    assert meter["context_tokens"] > 0
    assert 0.0 < meter["budget_ratio"] < 1.0
