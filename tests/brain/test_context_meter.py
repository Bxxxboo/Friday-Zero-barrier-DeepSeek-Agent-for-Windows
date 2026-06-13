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


def test_compute_context_meter_uses_effective_messages_not_raw_bulk(tmp_appdata):
    from friday.brain import effective_context_messages_for_meter

    settings = UserSettings(model="deepseek-chat", api_key="sk-test-key-1234567890")
    system = {"role": "system", "content": "你是星期五"}
    filler = "x" * 12000
    messages = [system]
    for i in range(24):
        messages.append({"role": "user", "content": f"轮次{i} {filler}"})
        messages.append({"role": "assistant", "content": f"回复{i} {filler}"})

    from friday.brain import DeepSeekBrain

    brain = DeepSeekBrain(settings)
    raw_tokens = brain.count_tokens(messages)
    effective = effective_context_messages_for_meter(settings, messages, tool_definitions=[])
    assert len(effective) < len(messages)
    effective_meter = compute_context_meter(settings, messages, tool_definitions=[])
    assert effective_meter["context_tokens"] < raw_tokens


def test_model_switch_shrinks_budget_and_raises_ratio():
    settings_large = UserSettings(model="mimo-v2.5-pro", api_key="sk-test-key-1234567890")
    settings_small = UserSettings(model="deepseek-chat", api_key="sk-test-key-1234567890")
    messages = [
        {"role": "system", "content": "你是星期五"},
        {"role": "user", "content": "长任务历史 " + ("y" * 50000)},
        {"role": "assistant", "content": "大段回复 " + ("z" * 50000)},
    ]
    large = compute_context_meter(settings_large, messages, tool_definitions=[])
    small = compute_context_meter(settings_small, messages, tool_definitions=[])
    assert small["context_budget"] < large["context_budget"]
    assert small["budget_ratio"] > large["budget_ratio"]
