from __future__ import annotations

import json
from pathlib import Path

from friday.config import MAX_PERSISTED_TOOL_CHARS, SESSION_FORMAT_VERSION
from friday.sessions import (
    get_session,
    migrate_session_files,
    save_agent_state,
    create_session,
)


def test_session_save_compresses_tool_messages(tmp_appdata):
    session = create_session()
    long_result = "x" * 5000
    messages = [
        {"role": "user", "content": "查文件"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "read_text_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "1", "content": long_result},
    ]
    save_agent_state(session.id, messages, user_text="查文件")

    raw = json.loads((tmp_appdata / "sessions" / f"{session.id}.json").read_text(encoding="utf-8"))
    assert raw["format_version"] == SESSION_FORMAT_VERSION
    assert len(raw["display_messages"]) == 1
    tool_content = raw["agent_messages"][-1]["content"]
    assert len(tool_content) < len(long_result)
    assert "已压缩" in tool_content
    assert len(tool_content) <= MAX_PERSISTED_TOOL_CHARS + 40


def test_session_save_persists_generated_images(tmp_appdata):
    session = create_session()
    img_path = "C:/FridayWorkspace/生成的图片/test.png"
    messages = [
        {"role": "user", "content": "画一张草原"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_img_1",
                    "type": "function",
                    "function": {"name": "generate_image", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_img_1",
            "content": f"已生成图片并保存：{img_path}\n尺寸：1024x1024，模型：test。",
        },
        {"role": "assistant", "content": "图片已生成，请查看。"},
    ]
    save_agent_state(session.id, messages, user_text="画一张草原")

    loaded = get_session(session.id)
    assert loaded is not None
    display = loaded.display_messages
    assert len(display) == 2
    assistant = display[-1]
    assert assistant["role"] == "assistant"
    assert assistant.get("generated_images") == [{"path": img_path}]

    from friday.sessions import session_display_messages

    api_display = session_display_messages(loaded)
    assert api_display[-1].get("generated_images") == [{"path": img_path}]


def test_build_display_messages_hides_internal_system_hints(tmp_appdata):
    from friday.sessions import build_display_messages, save_agent_state

    session = create_session()
    messages = [
        {"role": "user", "content": "看看 GitHub 上有什么 rules"},
        {"role": "assistant", "content": "让我搜索一下"},
        {
            "role": "user",
            "content": "【系统提示】已连续 3 次调用 browse_webpage 但进展不明显，请停止重复试探。",
        },
        {"role": "assistant", "content": "好的，我换个方式。"},
    ]
    save_agent_state(session.id, messages, user_text="看看 GitHub 上有什么 rules")

    display = build_display_messages(messages)
    assert [m["content"] for m in display if m["role"] == "user"] == ["看看 GitHub 上有什么 rules"]
    assert not any("【系统提示】" in m.get("content", "") for m in display)


def test_migrate_old_session_format(tmp_appdata):
    session = create_session(title="旧格式")
    path = tmp_appdata / "sessions" / f"{session.id}.json"
    path.write_text(
        json.dumps(
            {
                "id": session.id,
                "title": "旧格式",
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "agent_messages": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好！"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert migrate_session_files() >= 1
    loaded = get_session(session.id)
    assert loaded is not None
    assert loaded.display_messages
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("format_version") == SESSION_FORMAT_VERSION
