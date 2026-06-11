from __future__ import annotations

import logging
import time

from friday.logging_config import (
    LOG_BASENAME,
    log_file_path,
    purge_expired_logs,
    read_recent_log_lines,
    setup_logging,
)


def test_read_recent_log_lines_empty(tmp_appdata):
    assert read_recent_log_lines() == []
    assert log_file_path().parent == tmp_appdata


def test_purge_expired_logs_removes_old_rotated_files(tmp_appdata):
    old = tmp_appdata / f"{LOG_BASENAME}.1"
    old.write_text("old log", encoding="utf-8")
    recent = tmp_appdata / f"{LOG_BASENAME}.2"
    recent.write_text("recent log", encoding="utf-8")

    ten_days_ago = time.time() - 10 * 86400
    old.touch()
    recent.touch()
    import os

    os.utime(old, (ten_days_ago, ten_days_ago))

    deleted = purge_expired_logs(retain_days=7)
    assert not old.exists()
    assert recent.exists()
    assert any(str(old) == p for p in deleted)


def test_rotating_handler_creates_backup(tmp_appdata, monkeypatch):
    from logging.handlers import RotatingFileHandler

    from friday.logging_config import get_logger, log_file_path

    root = logging.getLogger("friday")
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    handler = RotatingFileHandler(
        str(log_file_path()),
        maxBytes=64,
        backupCount=3,
        encoding="utf-8",
    )
    root.addHandler(handler)
    log = get_logger("test.rotate")
    for _ in range(12):
        log.info("rotate-test-line-" + "x" * 24)
    handler.flush()

    assert (tmp_appdata / f"{LOG_BASENAME}.1").is_file()
