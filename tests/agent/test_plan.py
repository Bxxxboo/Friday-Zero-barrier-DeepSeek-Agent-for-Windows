from __future__ import annotations

from friday.config import PLAN_ANCHOR_MARKER
from friday.plan import (
    auto_complete_todos_from_assistant,
    auto_complete_todos_from_tool,
    extract_todos_from_plan_markdown,
    is_complex_task,
    maybe_append_complex_task_plan_hint,
    merge_todos_from_plan,
    normalize_todos,
    plan_prompt_block,
    session_has_actionable_plan,
    sync_todos_from_plan,
    upsert_plan_anchor,
)
from friday.prefix_cache import is_plan_anchor_message
from friday.sessions import ChatSession, create_session, get_session, save_session_fields


def test_normalize_todos():
    items = normalize_todos([{"text": "a", "done": True}, {"text": ""}, "bad"])
    assert len(items) == 1
    assert items[0]["text"] == "a"


def test_upsert_plan_anchor_replaces_stale_anchor():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": f"{PLAN_ANCHOR_MARKER}\n旧计划"},
        {"role": "user", "content": "hello"},
    ]
    out = upsert_plan_anchor(messages, "【当前任务计划】\n新步骤")
    anchors = [m for m in out if is_plan_anchor_message(m)]
    assert len(anchors) == 1
    assert "新步骤" in anchors[0]["content"]
    assert out[0]["content"] == "sys"
    assert out[1] is anchors[0]


def test_plan_prompt_block():
    session = ChatSession(
        id="s1",
        title="t",
        created_at=0,
        updated_at=0,
        plan_markdown="## 步骤\n1. 整理桌面",
        todos=[{"id": "1", "text": "扫描", "done": False}],
    )
    block = plan_prompt_block(session)
    assert "步骤" in block
    assert "扫描" in block


def test_extract_todos_from_plan_markdown():
    md = "## 任务\n- [ ] 整理下载文件夹\n- [x] 查磁盘空间\n1. [ ] 写周报"
    items = extract_todos_from_plan_markdown(md)
    assert len(items) == 3
    assert items[0]["text"] == "整理下载文件夹"
    assert items[0]["done"] is False
    assert items[1]["done"] is True


def test_merge_todos_from_plan_preserves_done_state():
    existing = [{"id": "a", "text": "整理下载文件夹", "done": True}]
    md = "- [ ] 整理下载文件夹\n- [ ] 新增步骤"
    merged, added = merge_todos_from_plan(existing, md)
    assert added == ["新增步骤"]
    assert merged[0]["done"] is True
    assert merged[0]["id"] == "a"
    assert any(item["text"] == "新增步骤" for item in merged)


def test_sync_todos_from_plan(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.sessions.get_appdata_dir", lambda: tmp_path)
    session = create_session("计划会话")
    save_session_fields(
        session.id,
        plan_markdown="- [ ] 扫描桌面\n- [ ] 清理下载",
        todos=[{"id": "1", "text": "手动待办", "done": False}],
    )
    result = sync_todos_from_plan(session.id)
    assert result["ok"] is True
    assert result["changed"] is True
    assert "扫描桌面" in [t["text"] for t in result["todos"]]
    assert "手动待办" in [t["text"] for t in result["todos"]]
    saved = get_session(session.id)
    assert saved is not None
    assert len(saved.todos) == 3


def test_auto_complete_todos_from_tool(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.sessions.get_appdata_dir", lambda: tmp_path)
    session = create_session("工具会话")
    save_session_fields(
        session.id,
        todos=[{"id": "1", "text": "整理下载文件夹", "done": False}],
    )
    result = auto_complete_todos_from_tool(
        session.id,
        "list_directory",
        {"path": "~/Downloads"},
        "已列出下载文件夹中的 12 个文件",
    )
    assert result["changed"] is True
    assert "整理下载文件夹" in result["completed"]
    saved = get_session(session.id)
    assert saved is not None
    assert saved.todos[0]["done"] is True


def test_auto_complete_todos_from_assistant(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.sessions.get_appdata_dir", lambda: tmp_path)
    session = create_session("回复会话")
    save_session_fields(
        session.id,
        todos=[{"id": "1", "text": "查磁盘空间", "done": False}],
    )
    result = auto_complete_todos_from_assistant(
        session.id,
        "已完成查磁盘空间，C 盘剩余 120GB。",
    )
    assert result["changed"] is True
    saved = get_session(session.id)
    assert saved is not None
    assert saved.todos[0]["done"] is True


def test_is_complex_task_multi_step():
    assert is_complex_task("帮我整理桌面，然后排查下载文件夹里的重复文件，最后写个汇总脚本")
    assert is_complex_task("1. 扫描桌面\n2. 移动大文件\n3. 写报告")
    assert not is_complex_task("你好")
    assert not is_complex_task("打开记事本")


def test_session_has_actionable_plan(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.sessions.get_appdata_dir", lambda: tmp_path)
    session = create_session("计划检测")
    assert session_has_actionable_plan(session.id) is False
    save_session_fields(
        session.id,
        plan_markdown="## 步骤\n1. 整理下载文件夹\n2. 压缩旧包",
        todos=[{"text": "整理下载文件夹", "done": False}, {"text": "压缩旧包", "done": False}],
    )
    assert session_has_actionable_plan(session.id) is True


def test_maybe_append_complex_task_plan_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.sessions.get_appdata_dir", lambda: tmp_path)
    session = create_session("提示")
    text = "请帮我批量整理下载文件夹，然后排查重复文件并写脚本汇总"
    out = maybe_append_complex_task_plan_hint(text, session.id)
    assert "【复杂任务提示】" in out
    assert "update_session_plan" in out
    save_session_fields(
        session.id,
        plan_markdown="## 计划\n- [ ] 整理\n- [ ] 排查",
        todos=[{"text": "整理", "done": False}, {"text": "排查", "done": False}],
    )
    again = maybe_append_complex_task_plan_hint(text, session.id)
    assert again == text
