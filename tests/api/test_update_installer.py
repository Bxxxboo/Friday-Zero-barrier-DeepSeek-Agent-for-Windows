from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from friday.update_installer import (
    _find_friday_app_dir,
    _format_update_error,
    _validate_download_url,
    can_auto_update,
    start_apply_update,
)
import urllib.error


def test_validate_download_url():
    assert _validate_download_url("https://gitee.com/Bxxxboo/friday/releases/download/v1/Friday-Windows-1.2.4.zip")
    assert _validate_download_url("https://github.com/user/repo/releases/download/v1/a.zip")
    assert not _validate_download_url("http://evil.example/update.zip")
    assert not _validate_download_url("")


def test_find_friday_app_dir(tmp_path: Path):
    app = tmp_path / "Friday"
    app.mkdir()
    (app / "星期五.exe").write_text("", encoding="utf-8")
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
