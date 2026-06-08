from __future__ import annotations

from unittest.mock import patch

from friday.brain import DeepSeekBrain
from friday.config import COMPACT_SUMMARY_MARKER
from friday.prefix_cache import (
    build_frozen_prefix,
    compute_prefix_fingerprint,
    compute_settings_fingerprint,
    deterministic_summary,
    is_compact_summary_message,
    split_message_regions,
)
from friday.storage import UserSettings


def test_frozen_prefix_stable_for_same_settings():
    settings = UserSettings(api_key="sk-test", model="deepseek-chat")
    a = build_frozen_prefix(settings)
    b = build_frozen_prefix(settings)
    assert a.fingerprint == b.fingerprint
    assert a.system_prompt == b.system_prompt
    assert len(a.tool_definitions) == len(b.tool_definitions)


def test_prefix_fingerprint_changes_with_mode():
    agent_settings = UserSettings(api_key="sk-test", interaction_mode="agent")
    ask_settings = UserSettings(api_key="sk-test", interaction_mode="ask")
    assert compute_settings_fingerprint(agent_settings) != compute_settings_fingerprint(ask_settings)


def test_is_compact_summary_message():
    assert is_compact_summary_message({"role": "user", "content": f"{COMPACT_SUMMARY_MARKER}\nfoo"})
    assert not is_compact_summary_message({"role": "user", "content": "hello"})


def test_split_message_regions():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": f"{COMPACT_SUMMARY_MARKER}\nsummary"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]
    system, summaries, compactable, tail = split_message_regions(
        messages,
        min_keep_recent=3,
    )
    assert system["content"] == "sys"
    assert len(summaries) == 1
    assert len(compactable) == 3
    assert len(tail) == 3


def test_deterministic_summary_keeps_paths():
    batch = [
        {"role": "user", "content": "请读取 E:\\data\\report.txt"},
        {"role": "assistant", "content": "好的，我来读取。"},
        {"role": "tool", "content": "文件内容：OK"},
    ]
    out = deterministic_summary(batch)
    assert "report.txt" in out


def test_prepare_messages_does_not_mutate_in_place():
    settings = UserSettings(api_key="sk-test", model="deepseek-chat")
    brain = DeepSeekBrain(settings)
    original_tool = "X" * 8000
    messages = [{"role": "system", "content": "sys"}]
    for i in range(12):
        messages.append({"role": "user", "content": f"question {i}"})
        messages.append({"role": "assistant", "content": f"answer {i}"})
        messages.append({"role": "tool", "content": original_tool})

    snapshot = [dict(m) for m in messages]
    brain._max_context = 800
    with patch.object(
        brain,
        "_summarize_message_batch",
        side_effect=lambda batch: deterministic_summary(batch),
    ):
        prepared = brain.prepare_messages(messages, tool_definitions=[])

    for before, after in zip(snapshot, messages):
        assert before == after
    assert len(prepared) < len(messages)
    assert any(is_compact_summary_message(m) for m in prepared)


def test_prepare_messages_skips_when_under_threshold():
    settings = UserSettings(api_key="sk-test", model="deepseek-chat")
    brain = DeepSeekBrain(settings)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    out = brain.prepare_messages(messages, tool_definitions=[])
    assert out is messages or out == messages


def test_agent_pins_prefix_on_init():
    from friday.agent import FridayAgent

    settings = UserSettings(api_key="sk-test", model="deepseek-chat")
    agent = FridayAgent(settings, lambda _action: True)
    assert agent._frozen_prefix is not None
    assert agent.messages[0]["content"] == agent._frozen_prefix.system_prompt
    fp = compute_prefix_fingerprint(
        agent._frozen_prefix.system_prompt,
        agent._frozen_prefix.tool_definitions,
    )
    assert fp == agent._frozen_prefix.fingerprint
