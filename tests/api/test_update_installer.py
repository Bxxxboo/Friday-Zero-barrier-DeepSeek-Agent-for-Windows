from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest

from friday.update_installer import (
    _extract_release,
    _find_friday_app_dir,
    _format_update_error,
    _validate_download_url,
    can_auto_update,
    clear_last_apply_result,
    format_last_apply_failure,
    last_apply_result_path,
    read_last_apply_result,
    register_quit_handler,
    request_app_quit,
    resolve_update_digest,
    start_apply_update,
)
import urllib.error


def test_validate_download_url():
    assert _validate_download_url("https://gitee.com/Bxxxboo/friday/releases/download/v1/Friday-Windows-1.2.4.zip")
    assert _validate_download_url("https://github.com/user/repo/releases/download/v1/a.zip")
    assert _validate_download_url("https://raw.githubusercontent.com/user/repo/v1/a.zip")
    assert not _validate_download_url("http://evil.example/update.zip")
    assert not _validate_download_url("https://evil.example/gitee.com/foo.zip")
    assert not _validate_download_url("https://gitee.com.evil.net/foo.zip")
    assert not _validate_download_url("")


def test_resolve_update_digest_requires_hash():
    url = "https://gitee.com/Bxxxboo/friday/releases/download/v1.3.1/Friday-Update-1.3.1.zip"
    digest = "a" * 64
    assert resolve_update_digest(url, digest) == digest
    with pytest.raises(RuntimeError, match="SHA256"):
        resolve_update_digest(url, "")


def test_extract_release_rejects_zip_slip(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    app = tmp_path / "stage_inner" / "Friday"
    app.mkdir(parents=True)
    (app / "Friday.exe").write_text("", encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Friday/Friday.exe", "ok")
        zf.writestr("../outside.txt", "pwn")
    dest = tmp_path / "extract"
    with pytest.raises(ValueError, match="unsafe zip"):
        _extract_release(zip_path, dest)


def test_find_friday_app_dir(tmp_path: Path):
    app = tmp_path / "Friday"
    app.mkdir()
    (app / "Friday.exe").write_text("", encoding="utf-8")
    assert _find_friday_app_dir(tmp_path) == app


def test_resolve_packaged_exe_in_dir_prefers_friday(tmp_path: Path):
    from friday.paths import resolve_packaged_exe_in_dir

    app = tmp_path / "Friday"
    app.mkdir()
    legacy = "\u661f\u671f\u4e94.exe"
    (app / legacy).write_text("", encoding="utf-8")
    (app / "Friday.exe").write_text("", encoding="utf-8")
    assert resolve_packaged_exe_in_dir(app).name == "Friday.exe"


def test_find_friday_app_dir_legacy_chinese_exe(tmp_path: Path):
    app = tmp_path / "Friday"
    app.mkdir()
    legacy = "\u661f\u671f\u4e94.exe"
    (app / legacy).write_text("", encoding="utf-8")
    assert _find_friday_app_dir(tmp_path) == app


def test_find_friday_app_dir_from_zip_layout(tmp_path: Path):
    stage = tmp_path / "stage"
    app = stage / "Friday"
    app.mkdir(parents=True)
    (app / "app.exe").write_text("", encoding="utf-8")
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in app.rglob("*"):
            zf.write(path, path.relative_to(stage))
    extract = tmp_path / "extract"
    extract.mkdir()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract)
    found = _find_friday_app_dir(extract)
    assert found is not None
    assert found.name == "Friday"


def test_can_auto_update_false_in_dev():
    ok, reason = can_auto_update()
    assert ok is False
    assert reason


def test_start_apply_update_requires_url():
    ok, _ = can_auto_update()
    if ok:
        pytest.skip("packaged runtime only")
    result = start_apply_update(download_url="", version="1.0.0")
    assert result["started"] is False
    assert result.get("message")
    assert result.get("hint")


def test_format_update_error_http_404():
    exc = urllib.error.HTTPError("https://gitee.com/x", 404, "Not Found", {}, None)
    detail, hint = _format_update_error(exc)
    assert "404" in detail
    assert hint


def test_format_update_error_bad_zip():
    import zipfile

    detail, hint = _format_update_error(zipfile.BadZipFile("bad"))
    assert "zip" in detail.lower() or "损坏" in detail
    assert hint


def test_request_app_quit_exits_even_when_handler_succeeds(monkeypatch):
    """关闭窗口后仍须 os._exit，否则 Friday.exe 占用导致 robocopy 无法替换。"""
    exits: list[int] = []

    def _fake_exit(code: int) -> None:
        exits.append(code)

    monkeypatch.setattr("friday.update_installer.os._exit", _fake_exit)
    register_quit_handler(lambda: None)
    request_app_quit(delay=0.01)
    time.sleep(0.2)
    assert exits == [0]


def test_format_last_apply_failure_after_robocopy(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.update_installer._updates_dir", lambda: tmp_path)
    path = last_apply_result_path()
    path.write_text(
        '{"ok": false, "version": "1.3.5", "detail": "robocopy_failed log=x"}',
        encoding="utf-8",
    )
    hint = format_last_apply_failure(current="1.3.2")
    assert "1.3.5" in hint
    assert "robocopy" in hint or "占用" in hint or "失败" in hint
    clear_last_apply_result()
    assert read_last_apply_result() == {}


def test_format_last_apply_failure_clears_when_already_updated(tmp_path, monkeypatch):
    monkeypatch.setattr("friday.update_installer._updates_dir", lambda: tmp_path)
    last_apply_result_path().write_text(
        '{"ok": false, "version": "1.3.2", "detail": "robocopy_failed"}',
        encoding="utf-8",
    )
    assert format_last_apply_failure(current="1.3.5") == ""


def test_request_app_quit_force_skips_handler(monkeypatch):
    """一键更新须 force 退出，避免非主线程 destroy 卡死。"""
    exits: list[int] = []
    called: list[bool] = []

    def _fake_exit(code: int) -> None:
        exits.append(code)

    monkeypatch.setattr("friday.update_installer.os._exit", _fake_exit)
    register_quit_handler(lambda: called.append(True))
    request_app_quit(delay=0.01, force=True)
    time.sleep(0.2)
    assert exits == [0]
    assert called == []
