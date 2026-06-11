from __future__ import annotations

from pathlib import Path

from friday.update_rollback import (
    BACKUP_DIR_NAME,
    MAX_STARTUP_FAILURES,
    backup_install_dir,
    clear_pending_update,
    confirm_startup_success,
    guard_startup_after_update,
    has_pending_update,
    install_backup_dir,
    mark_pending_update,
    record_startup_crash,
    restore_install_dir,
)


def test_install_backup_dir_sibling(tmp_path: Path):
    install = tmp_path / "Friday"
    install.mkdir()
    assert install_backup_dir(install) == tmp_path / BACKUP_DIR_NAME


def test_backup_and_restore_roundtrip(tmp_path: Path):
    install = tmp_path / "Friday"
    install.mkdir()
    (install / "Friday.exe").write_text("app", encoding="utf-8")
    (install / "note.txt").write_text("keep", encoding="utf-8")

    backup_install_dir(install)
    backup = install_backup_dir(install)
    assert backup.is_dir()
    assert (backup / "Friday.exe").read_text(encoding="utf-8") == "app"

    (install / "Friday.exe").write_text("broken", encoding="utf-8")
    ok, msg = restore_install_dir(install)
    assert ok is True
    assert (install / "Friday.exe").read_text(encoding="utf-8") == "app"
    assert msg


def test_mark_pending_and_clear(tmp_appdata, tmp_path: Path):
    install = tmp_path / "Friday"
    install.mkdir()
    mark_pending_update(version="9.9.9", install_dir=install)
    assert has_pending_update() is True
    clear_pending_update()
    assert has_pending_update() is False


def test_guard_startup_noop_without_pending(monkeypatch):
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)
    clear_pending_update()
    assert guard_startup_after_update() is True


def test_record_startup_crash_only_when_pending(tmp_appdata, tmp_path: Path, monkeypatch):
    install = tmp_path / "Friday"
    install.mkdir()
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)

    assert record_startup_crash(context="test") == 0

    mark_pending_update(version="1.0.0", install_dir=install)
    count = record_startup_crash(context="boom")
    assert count == 1


def test_record_startup_crash_ignored_after_confirm(tmp_appdata, tmp_path: Path, monkeypatch):
    install = tmp_path / "Friday"
    install.mkdir()
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)
    mark_pending_update(version="1.0.0", install_dir=install)
    confirm_startup_success()
    assert record_startup_crash(context="late") == 0


def test_guard_triggers_rollback_after_three_crashes(
    tmp_appdata,
    tmp_path: Path,
    monkeypatch,
):
    install = tmp_path / "Friday"
    install.mkdir()
    (install / "Friday.exe").write_text("app", encoding="utf-8")
    backup_install_dir(install)
    (install / "Friday.exe").write_text("broken", encoding="utf-8")

    mark_pending_update(version="2.0.0", install_dir=install)
    monkeypatch.setattr("friday.update_rollback.is_frozen", lambda: True)
    monkeypatch.setattr("friday.update_installer.app_install_dir", lambda: install)

    for _ in range(MAX_STARTUP_FAILURES):
        record_startup_crash(context="test-crash")

    notified: list[str] = []
    restarted: list[Path] = []
    monkeypatch.setattr("friday.update_rollback._notify_rollback", lambda m: notified.append(m))
    monkeypatch.setattr("friday.update_rollback._restart_exe", lambda d: restarted.append(d))

    assert guard_startup_after_update() is False
    assert (install / "Friday.exe").read_text(encoding="utf-8") == "app"
    assert not has_pending_update()
    assert notified
    assert "崩溃" in notified[0]
    assert restarted == [install]
