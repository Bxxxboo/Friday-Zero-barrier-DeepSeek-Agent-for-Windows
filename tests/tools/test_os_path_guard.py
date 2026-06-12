from __future__ import annotations

import sys

import pytest

from friday.os_path_guard import (
    OS_DELETE_BLOCK_REASON,
    block_reason_for_destructive_paths,
    is_windows_c_os_path,
)
from friday.safety import evaluate_tool
from friday.storage import UserSettings
from friday.tools.filesystem import delete_file


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 测试 C: 系统路径")
def test_is_windows_c_os_path_windows_dir():
    assert is_windows_c_os_path("C:/Windows/System32/kernel32.dll") is True
    assert is_windows_c_os_path("C:\\Program Files\\Windows NT") is True
    assert is_windows_c_os_path("C:/ProgramData/Microsoft/Windows") is True


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 测试 C: 系统路径")
def test_is_windows_c_os_path_users_allowed():
    assert is_windows_c_os_path("C:/Users/Someone/Desktop/note.txt") is False


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 测试 C: 系统路径")
def test_is_windows_c_os_path_other_drive_allowed():
    assert is_windows_c_os_path("D:/Windows/foo") is False


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 测试 C: 系统路径")
def test_evaluate_delete_file_blocked_on_windows():
    settings = UserSettings(
        restrict_to_workspace=False,
        require_approval_writes=False,
        interaction_mode="yolo",
    )
    decision = evaluate_tool(
        settings,
        "delete_file",
        {"path": "C:/Windows/temp_test_friday_guard.txt"},
        yolo_unlocked=True,
    )
    assert decision.allowed is False
    assert OS_DELETE_BLOCK_REASON in decision.reason


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 测试 C: 系统路径")
def test_delete_file_tool_returns_block_message():
    result = delete_file("C:/Windows/notepad.exe")
    assert "⛔" in result
    assert "绝对禁止" in result


def test_block_reason_skips_read_tools():
    assert block_reason_for_destructive_paths("read_text_file", ["C:/Windows/x"]) is None
