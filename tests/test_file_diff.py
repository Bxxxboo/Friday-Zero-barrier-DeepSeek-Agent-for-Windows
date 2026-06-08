from __future__ import annotations

from friday.file_diff import build_file_change_payload, read_text_if_exists


def test_build_file_change_payload_new_file():
    payload = build_file_change_payload("E:/test.txt", "", "hello\nworld")
    assert payload["is_new"] is True
    assert "hello" in str(payload["diff"])


def test_read_text_if_exists(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("content", encoding="utf-8")
    assert read_text_if_exists(f) == "content"
    assert read_text_if_exists(tmp_path / "missing.txt") == ""
