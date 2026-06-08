from __future__ import annotations

from friday.brain import parse_api_usage
from friday.context import (
    compress_tool_result,
    detect_repeated_tool_loop,
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
