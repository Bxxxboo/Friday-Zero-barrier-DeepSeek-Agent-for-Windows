from __future__ import annotations

from friday.brain import parse_api_usage
from friday.context import (
    compress_tool_result,
    detect_probe_tool_thrash,
    detect_repeated_tool_loop,
    sanitize_agent_messages,
    sort_tool_definitions,
)


def test_compress_tool_result_head_tail():
    raw = "A" * 5000 + "IMPORTANT" + "B" * 5000
    out = compress_tool_result("read_text_file", raw, max_chars=1200)
    assert len(out) < len(raw)
    assert "IMPORTANT" in out
    assert "已压缩" in out


def test_compress_strips_base64():
    blob = "data:image/png;base64," + ("A" * 500)
    raw = f"preview {blob} end"
    out = compress_tool_result("describe_image", raw, max_chars=2000)
    assert "base64 数据已省略" in out


def test_sort_tool_definitions_stable():
    defs = [
        {"type": "function", "function": {"name": "z_tool"}},
        {"type": "function", "function": {"name": "a_tool"}},
    ]
    sorted_defs = sort_tool_definitions(defs)
    names = [d["function"]["name"] for d in sorted_defs]
    assert names == ["a_tool", "z_tool"]


def test_detect_repeated_tool_loop():
    sig = "list_directory"
    messages = []
    for _ in range(3):
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "function": {"name": sig, "arguments": "{}"},
            }],
        })
    looping, hint = detect_repeated_tool_loop(messages)
    assert looping is True
    assert hint


def test_detect_repeated_tool_name_thrash():
    messages = []
    for i in range(3):
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "function": {
                    "name": "search_files",
                    "arguments": f'{{"root":"C:/test{i}"}}',
                },
            }],
        })
    looping, hint = detect_repeated_tool_loop(messages)
    assert looping is True
    assert "search_files" in hint


def test_detect_probe_tool_thrash_python_env():
    messages = []
    for _ in range(2):
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "function": {"name": "python_env_info", "arguments": "{}"},
            }],
        })
    thrashing, hint = detect_probe_tool_thrash(messages)
    assert thrashing is True
    assert "python_env_info" in hint


def test_detect_probe_tool_thrash_run_python():
    messages = []
    for _ in range(2):
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "function": {
                    "name": "run_python",
                    "arguments": '{"code":"import sys\\nprint(sys.path)"}',
                },
            }],
        })
    thrashing, hint = detect_probe_tool_thrash(messages)
    assert thrashing is True
    assert "run_python" in hint


def test_parse_api_usage_cache_fields():
    stats = parse_api_usage({
        "prompt_tokens": 1000,
        "completion_tokens": 50,
        "prompt_cache_hit_tokens": 900,
        "prompt_cache_miss_tokens": 100,
    })
    assert stats.cache_hit_tokens == 900
    assert stats.cache_miss_tokens == 100
    assert abs(stats.cache_hit_rate - 0.9) < 0.001


def test_sanitize_agent_messages_drops_orphan_tool():
    raw = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "x", "content": "orphan"},
    ]
    out = sanitize_agent_messages(raw)
    assert [m["role"] for m in out] == ["system", "user"]


def test_sanitize_agent_messages_keeps_complete_tool_round():
    raw = [
        {"role": "user", "content": "run"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "run_python", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    out = sanitize_agent_messages(raw)
    assert len(out) == 3
    assert out[-1]["role"] == "tool"


def test_sanitize_agent_messages_strips_incomplete_tool_round():
    raw = [
        {"role": "user", "content": "run"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "run_python", "arguments": "{}"}}],
        },
    ]
    out = sanitize_agent_messages(raw)
    assert len(out) == 2
    assert "tool_calls" not in out[-1]
    assert "未完成" in out[-1]["content"]
