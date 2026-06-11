"""崩溃钩子与更新回滚联动测试（M4.5）。"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from friday.crash_handler import install_crash_handler
from friday.update_rollback import (
    MAX_STARTUP_FAILURES,
    guard_startup_after_update,
    has_pending_update,
    mark_pending_update,
    record_startup_crash,
)


def test_main_excepthook_records_startup_crash(tmp_appdata, tmp_path: Path, monkeypatch):
    install = tmp_path / "Friday"
    install.mkdir()
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)
    mark_pending_update(version="1.2.3", install_dir=install)

    install_crash_handler()
    try:
        raise RuntimeError("startup-crash-hook")
    except RuntimeError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        sys.excepthook(exc_type, exc_value, exc_tb)

    failures_path = tmp_appdata / "updates" / "startup-failures.json"
    assert failures_path.is_file()
    import json

    data = json.loads(failures_path.read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert data["reason"] == "crash"


def test_guard_no_rollback_without_enough_crashes(tmp_appdata, tmp_path: Path, monkeypatch):
    install = tmp_path / "Friday"
    install.mkdir()
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)
    monkeypatch.setattr("friday.update_installer.app_install_dir", lambda: install)
    mark_pending_update(version="1.0.0", install_dir=install)

    record_startup_crash(context="one")
    record_startup_crash(context="two")

    assert guard_startup_after_update() is True
    assert has_pending_update() is True


def test_threading_excepthook_records_startup_crash(tmp_appdata, tmp_path: Path, monkeypatch):
    if not hasattr(threading, "excepthook"):
        return
    install = tmp_path / "Friday"
    install.mkdir()
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)
    mark_pending_update(version="1.2.3", install_dir=install)

    install_crash_handler()

    def boom() -> None:
        raise RuntimeError("thread-startup-crash")

    thread = threading.Thread(target=boom, name="RollbackTestThread")
    thread.start()
    thread.join(timeout=2.0)

    failures_path = tmp_appdata / "updates" / "startup-failures.json"
    assert failures_path.is_file()
    assert MAX_STARTUP_FAILURES > 0
