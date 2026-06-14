from __future__ import annotations

from friday.agent import FridayAgent
from friday.safety import ToolDecision
from friday.storage import UserSettings


def _allowed_tool(*_a, **_k) -> ToolDecision:
    return ToolDecision(allowed=True, needs_approval=False)


def _agent() -> FridayAgent:
    settings = UserSettings(api_key="sk-test", base_url="http://127.0.0.1", model="m")
    return FridayAgent(settings, lambda _a: True)


def test_agent_emits_file_generated_for_docx(monkeypatch):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)
    monkeypatch.setattr(
        "friday.agent.execute_tool",
        lambda *_a, **_k: "已创建 Word 文档: C:\\work\\a.docx",
    )
    agent = _agent()
    agent._execute_single_tool(
        "create_docx",
        {"output_path": "a.docx", "title": "t", "sections": []},
        1,
        0,
        on_event,
    )
    assert ("file_generated", {"path": "C:\\work\\a.docx", "kind": "document"}) in events


def test_agent_emits_image_generated_for_screenshot(monkeypatch):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)
    monkeypatch.setattr(
        "friday.agent.execute_tool",
        lambda *_a, **_k: "截图已保存: C:\\work\\s.png (800x600)",
    )
    agent = _agent()
    agent._execute_single_tool(
        "screenshot",
        {"output_path": "s.png"},
        1,
        0,
        on_event,
    )
    assert ("image_generated", {"path": "C:\\work\\s.png"}) in events


def test_agent_emits_file_generated_for_md_write(monkeypatch):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)
    monkeypatch.setattr(
        "friday.agent.execute_tool",
        lambda *_a, **_k: "已写入: notes.md",
    )
    agent = _agent()
    agent._execute_single_tool(
        "write_text_file",
        {"path": "notes.md", "content": "hi"},
        1,
        0,
        on_event,
    )
    assert ("file_generated", {"path": "notes.md", "kind": "text"}) in events


def test_agent_skips_file_generated_for_non_text_write(monkeypatch):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)
    monkeypatch.setattr(
        "friday.agent.execute_tool",
        lambda *_a, **_k: "已写入: script.py",
    )
    agent = _agent()
    agent._execute_single_tool(
        "write_text_file",
        {"path": "script.py", "content": "print(1)"},
        1,
        0,
        on_event,
    )
    assert not any(et == "file_generated" for et, _ in events)


def test_agent_emits_file_generated_for_weixin_copy_to_delivered(monkeypatch):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)
    monkeypatch.setattr(
        "friday.agent.execute_tool",
        lambda *_a, **_k: (
            "已复制: C:\\Users\\me\\Desktop\\第五节辅导课.docx "
            "-> C:\\work\\.friday\\delivered\\第五节辅导课.docx"
        ),
    )
    monkeypatch.setattr(
        "friday.weixin.deliverables.should_emit_weixin_copy_deliverable",
        lambda dest, settings: True,
    )
    agent = _agent()
    agent.operation_meta = {"trigger": "weixin", "session_id": "s1"}
    agent._execute_single_tool(
        "copy_file",
        {
            "source": "C:\\Users\\me\\Desktop\\第五节辅导课.docx",
            "destination": "C:\\work\\.friday\\delivered\\第五节辅导课.docx",
        },
        1,
        0,
        on_event,
    )
    assert (
        "file_generated",
        {
            "path": "C:\\work\\.friday\\delivered\\第五节辅导课.docx",
            "kind": "document",
        },
    ) in events


def test_agent_skips_file_generated_for_copy_outside_weixin(monkeypatch):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)
    monkeypatch.setattr(
        "friday.agent.execute_tool",
        lambda *_a, **_k: "已复制: a.docx -> b.docx",
    )
    agent = _agent()
    agent.operation_meta = {"trigger": "chat", "session_id": "s1"}
    agent._execute_single_tool(
        "copy_file",
        {"source": "a.docx", "destination": "b.docx"},
        1,
        0,
        on_event,
    )
    assert not any(et == "file_generated" for et, _ in events)


def test_agent_emits_file_generated_for_weixin_powershell_copy_to_delivered(monkeypatch, tmp_path):
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    doc = delivered / "第五节辅导课.docx"

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)

    def fake_shell(*_a, **_k):
        doc.write_bytes(b"x" * 2048)
        return "exit=0\nOK"

    monkeypatch.setattr("friday.agent.execute_tool", fake_shell)
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    monkeypatch.setattr("friday.weixin.deliverables.resolved_workspace", lambda _s: str(ws))

    agent = _agent()
    agent.settings = UserSettings(workspace=str(ws))
    agent.operation_meta = {"trigger": "weixin", "session_id": "s1"}
    agent._execute_single_tool(
        "run_powershell",
        {"command": "Copy-Item ..."},
        1,
        0,
        on_event,
    )
    assert any(
        et == "file_generated" and payload.get("path", "").endswith("第五节辅导课.docx")
        for et, payload in events
    )


def test_agent_emits_file_generated_for_weixin_powershell_copy_to_workspace_root(
    monkeypatch, tmp_path
):
    import os
    import time

    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    ws = tmp_path / "ws"
    ws.mkdir()
    doc = ws / "第五节辅导课.docx"
    old = time.time() - 86400 * 30

    monkeypatch.setattr("friday.agent.evaluate_tool", _allowed_tool)

    def fake_shell(*_a, **_k):
        doc.write_bytes(b"x" * 2048)
        os.utime(doc, (old, old))
        return "exit=0\nOK"

    monkeypatch.setattr("friday.agent.execute_tool", fake_shell)
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    monkeypatch.setattr("friday.weixin.deliverables.resolved_workspace", lambda _s: str(ws))

    agent = _agent()
    agent.settings = UserSettings(workspace=str(ws))
    agent.operation_meta = {"trigger": "weixin", "session_id": "s1"}
    agent._execute_single_tool(
        "run_powershell",
        {"command": "Copy-Item ..."},
        1,
        0,
        on_event,
    )
    assert any(
        et == "file_generated" and payload.get("path", "").endswith("第五节辅导课.docx")
        for et, payload in events
    )
