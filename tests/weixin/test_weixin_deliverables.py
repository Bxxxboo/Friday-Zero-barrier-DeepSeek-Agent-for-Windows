from __future__ import annotations

from pathlib import Path

from friday.storage import UserSettings
from friday.weixin.deliverables import (
    deliver_turn_new_attachments,
    extract_copy_file_destination,
    extract_deliverable_path,
    extract_move_file_destination,
    extract_requested_filename,
    file_generated_kind_for_path,
    find_deliverable_for_weixin_request,
    format_deliverable_caption,
    is_text_file_deliverable,
    list_deliverables_in_delivered,
    list_deliverables_in_workspace_root,
    list_turn_deliverable_candidates,
    list_turn_new_deliverables,
    newest_deliverable_in_delivered,
    snapshot_deliverable_path_keys,
    resolve_attachment_path,
    should_emit_weixin_copy_deliverable,
    try_deliver_existing_weixin_file,
    user_requests_weixin_file_delivery,
)


def test_extract_deliverable_path_docx():
    result = "已创建 Word 文档: C:\\work\\report.docx"
    assert extract_deliverable_path("create_docx", result) == "C:\\work\\report.docx"


def test_extract_deliverable_path_screenshot():
    result = "截图已保存: C:\\work\\shot.png (1920x1080)"
    assert extract_deliverable_path("screenshot", result) == "C:\\work\\shot.png"


def test_extract_deliverable_path_write_text():
    result = "已写入: notes.md"
    assert extract_deliverable_path("write_text_file", result) == "notes.md"


def test_is_text_file_deliverable():
    assert is_text_file_deliverable("a.md")
    assert not is_text_file_deliverable("a.docx")


def test_format_deliverable_caption():
    assert format_deliverable_caption(Path("C:/x/report.docx")) == "已生成：report.docx"


def test_extract_copy_file_destination():
    result = "已复制: C:\\Users\\me\\Desktop\\a.docx -> C:\\work\\.friday\\delivered\\a.docx"
    assert extract_copy_file_destination(result) == "C:\\work\\.friday\\delivered\\a.docx"


def test_file_generated_kind_for_path():
    assert file_generated_kind_for_path("a.docx") == "document"
    assert file_generated_kind_for_path("notes.md") == "text"
    assert file_generated_kind_for_path("script.py") is None


def test_should_emit_weixin_copy_deliverable_for_delivered_dir(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    doc = delivered / "lesson5.docx"
    doc.write_bytes(b"doc")
    settings = UserSettings(workspace=str(ws))
    assert should_emit_weixin_copy_deliverable(str(doc), settings=settings)


def test_extract_move_file_destination():
    result = "已移动: C:\\Users\\me\\Desktop\\a.docx -> C:\\work\\.friday\\delivered\\a.docx"
    assert extract_move_file_destination(result) == "C:\\work\\.friday\\delivered\\a.docx"


def test_newest_deliverable_in_delivered(tmp_path, monkeypatch):
    import os
    import time

    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    old = delivered / "old.docx"
    old.write_bytes(b"old")
    old_mtime = time.time() - 60
    os.utime(old, (old_mtime, old_mtime))
    new = delivered / "lesson5.docx"
    new.write_bytes(b"new")
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    found = newest_deliverable_in_delivered(settings, min_mtime=time.time() - 5)
    assert found == new.resolve()


def test_list_deliverables_in_delivered_returns_all_new_files(tmp_path, monkeypatch):
    import os
    import time

    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    base = time.time()
    for idx, name in enumerate(("卷一.docx", "卷二.docx", "卷三.docx"), start=1):
        path = delivered / name
        path.write_bytes(f"paper{idx}".encode())
        os.utime(path, (base + idx, base + idx))
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    found = list_deliverables_in_delivered(settings, min_mtime=base)
    assert [p.name for p in found] == ["卷一.docx", "卷二.docx", "卷三.docx"]


def test_list_deliverables_in_workspace_root_returns_new_docx(tmp_path, monkeypatch):
    import os
    import time

    ws = tmp_path / "ws"
    ws.mkdir()
    base = time.time()
    for idx, name in enumerate(("第一节辅导课.docx", "第二节课.docx"), start=1):
        path = ws / name
        path.write_bytes(f"paper{idx}".encode())
        os.utime(path, (base + idx, base + idx))
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    found = list_deliverables_in_workspace_root(settings, min_mtime=base)
    assert [p.name for p in found] == ["第一节辅导课.docx", "第二节课.docx"]


def test_deliver_turn_new_attachments_emits_workspace_root_files(tmp_path, monkeypatch):
    import os
    import time

    ws = tmp_path / "ws"
    ws.mkdir()
    base = time.time()
    paths = []
    for idx, name in enumerate(
        (
            "第一节辅导课.docx",
            "应用密码学与网络安全第二节课.docx",
            "第三节辅导课.docx",
            "第四节辅导课.docx",
            "第五节辅导课.docx",
        ),
        start=1,
    ):
        path = ws / name
        path.write_bytes(f"paper{idx}".encode())
        os.utime(path, (base + idx, base + idx))
        paths.append(path.resolve())
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    count = deliver_turn_new_attachments(
        settings=settings,
        on_event=on_event,
        min_mtime=base,
        already_sent=set(),
    )
    assert count == 5
    emitted = [payload["path"] for _type, payload in events]
    assert len(emitted) == 5
    for path in paths:
        assert str(path) in emitted


def test_deliver_turn_new_attachments_snapshot_catches_old_mtime(tmp_path, monkeypatch):
    import os
    import time

    ws = tmp_path / "ws"
    ws.mkdir()
    old = time.time() - 86400 * 30
    path = ws / "第五节辅导课.docx"
    path.write_bytes(b"doc")
    os.utime(path, (old, old))
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    count = deliver_turn_new_attachments(
        settings=settings,
        on_event=on_event,
        min_mtime=time.time(),
        before_path_keys=set(),
    )
    assert count == 1
    assert events[0][1]["path"] == str(path.resolve())


def test_turn_deliverable_candidates_includes_unsent_delivered_before_snapshot(
    tmp_path, monkeypatch
):
    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    doc = delivered / "第三节辅导课.docx"
    doc.write_bytes(b"doc")
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    before = {str(doc.resolve())}
    found = list_turn_deliverable_candidates(
        settings,
        min_mtime=0,
        before_path_keys=before,
        already_sent=set(),
    )
    assert [p.name for p in found] == ["第三节辅导课.docx"]


def test_deliver_turn_new_attachments_emits_all_unsent(tmp_path, monkeypatch):
    import os
    import time

    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    base = time.time()
    paths = []
    for idx, name in enumerate(("卷一.docx", "卷二.docx", "卷三.docx"), start=1):
        path = delivered / name
        path.write_bytes(f"paper{idx}".encode())
        os.utime(path, (base + idx, base + idx))
        paths.append(path.resolve())
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    already = {str(paths[2])}
    count = deliver_turn_new_attachments(
        settings=settings,
        on_event=on_event,
        min_mtime=base,
        already_sent=already,
    )
    assert count == 2
    emitted = [payload["path"] for _type, payload in events]
    assert str(paths[0]) in emitted
    assert str(paths[1]) in emitted
    assert str(paths[2]) not in emitted


def test_extract_requested_filename_strips_markdown():
    assert extract_requested_filename("给我发送**第五节辅导课.docx**") == "第五节辅导课.docx"


def test_extract_requested_filename_long_chinese_prefix():
    text = "帮我把桌面上的上课内容文件夹中的第五节辅导课.docx给我发过来"
    assert extract_requested_filename(text) == "第五节辅导课.docx"


def test_find_deliverable_for_long_request_in_delivered(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    doc = delivered / "第五节辅导课.docx"
    doc.write_bytes(b"doc")
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    text = "帮我把桌面上的上课内容文件夹中的第五节辅导课.docx给我发过来"
    found = find_deliverable_for_weixin_request(text, settings)
    assert found == doc.resolve()


def test_user_requests_weixin_file_delivery():
    assert user_requests_weixin_file_delivery("给我发送第五节辅导课.docx")
    assert not user_requests_weixin_file_delivery("第五节辅导课.docx 是什么")


def test_find_deliverable_for_weixin_request_in_delivered(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    doc = delivered / "第五节辅导课.docx"
    doc.write_bytes(b"doc")
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    found = find_deliverable_for_weixin_request("给我发送第五节辅导课.docx", settings)
    assert found == doc.resolve()


def test_find_deliverable_for_weixin_request_in_subfolder(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    folder = ws / "上课内容"
    folder.mkdir()
    doc = folder / "第五节辅导课.docx"
    doc.write_bytes(b"doc")
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    monkeypatch.setattr(
        "friday.weixin.deliverables.deliverable_roots",
        lambda _s: [ws],
    )
    found = find_deliverable_for_weixin_request("给我发送第五节辅导课.docx", settings)
    assert found == doc.resolve()


def test_try_deliver_existing_weixin_file_emits_event(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    delivered = ws / ".friday" / "delivered"
    delivered.mkdir(parents=True)
    doc = delivered / "第五节辅导课.docx"
    doc.write_bytes(b"doc")
    settings = UserSettings(workspace=str(ws))
    monkeypatch.setattr("friday.artifacts.resolved_workspace", lambda _s: str(ws))
    monkeypatch.setattr("friday.weixin.deliverables.resolved_workspace", lambda _s: str(ws))
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    assert try_deliver_existing_weixin_file(
        "给我发送第五节辅导课.docx",
        settings=settings,
        on_event=on_event,
    )
    assert events == [("file_generated", {"path": str(doc.resolve()), "kind": "document"})]


def test_resolve_attachment_path_allows_desktop_docx(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    doc = desktop / "lesson.docx"
    doc.write_bytes(b"doc")
    monkeypatch.setattr(
        "friday.paths.known_folders",
        lambda *_a, **_k: {"桌面": str(desktop)},
    )
    resolved = resolve_attachment_path(str(doc), UserSettings(workspace=str(ws)))
    assert resolved == doc.resolve()
