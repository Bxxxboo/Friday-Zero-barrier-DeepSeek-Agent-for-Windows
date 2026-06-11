"""崩溃捕获与落盘测试（M4.1）。"""

from __future__ import annotations

import sys
import threading

from friday.crash_handler import (
    crashes_dir,
    format_crash_report,
    install_crash_handler,
    write_crash_report,
)


def test_write_crash_report_creates_file(tmp_appdata):
    try:
        raise RuntimeError("friday-crash-test")
    except RuntimeError:
        exc_type, exc_value, exc_tb = sys.exc_info()
    path = write_crash_report(exc_type, exc_value, exc_tb, context="test")
    assert path is not None
    assert path.is_file()
    assert path.parent == crashes_dir()
    text = path.read_text(encoding="utf-8")
    assert "friday-crash-test" in text
    assert "version:" in text
    assert "traceback:" in text


def test_format_crash_report_includes_context():
    try:
        raise ValueError("ctx")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()
    body = format_crash_report(exc_type, exc_value, exc_tb, context="unit")
    assert "context: unit" in body
    assert "ctx" in body


def test_main_excepthook_writes_report(tmp_appdata):
    install_crash_handler()
    try:
        raise OSError("hook-test")
    except OSError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        sys.excepthook(exc_type, exc_value, exc_tb)
    files = list(crashes_dir().glob("crash-*.log"))
    assert files
    assert any("hook-test" in f.read_text(encoding="utf-8") for f in files)


def test_threading_excepthook_writes_report(tmp_appdata):
    if not hasattr(threading, "excepthook"):
        return
    install_crash_handler()

    def boom() -> None:
        raise RuntimeError("thread-crash-test")

    thread = threading.Thread(target=boom, name="CrashTestThread")
    thread.start()
    thread.join(timeout=2.0)
    files = list(crashes_dir().glob("crash-*.log"))
    assert any("thread-crash-test" in f.read_text(encoding="utf-8") for f in files)
    assert any("thread:CrashTestThread" in f.read_text(encoding="utf-8") for f in files)
