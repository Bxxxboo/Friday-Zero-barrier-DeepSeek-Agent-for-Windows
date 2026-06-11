"""诊断包导出测试（M4.2）。"""

from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

import friday.server as server_mod
from friday.auth import ensure_api_token
from friday.diagnostics_bundle import export_diagnostic_bundle, redact_text
from friday.logging_config import log_file_path
from friday.storage import UserSettings, save_settings


def test_redact_text_masks_api_keys():
    raw = 'api_key=sk-secret123456 token Bearer abc.def token "api_key": "sk-foo-bar"'
    out = redact_text(raw)
    assert "sk-secret123456" not in out
    assert "sk-foo-bar" not in out
    assert "sk-***" in out
    assert "Bearer ***" in out


def test_export_diagnostic_bundle_includes_core_files(tmp_appdata):
    secret = "sk-diagnostic-test-secret-key"
    log_file_path().write_text(f"boot ok key={secret}\n", encoding="utf-8")
    settings = UserSettings(
        api_key=secret,
        vision_api_key="ark-vision-secret-key",
        image_gen_api_key="sk-image-gen-secret",
    )
    save_settings(settings)

    dest = tmp_appdata / "diag.zip"
    path, report = export_diagnostic_bundle(dest)

    assert path == dest
    assert dest.is_file()
    assert "manifest.json" in report["included"]
    assert "settings_summary.json" in report["included"]
    assert "runtime.json" in report["included"]
    assert "weixin_status.json" in report["included"]

    with zipfile.ZipFile(dest, "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "settings_summary.json" in names
        assert "logs/friday.log.tail.txt" in names
        blob = zf.read("settings_summary.json").decode("utf-8")
        summary = json.loads(blob)
        assert summary["api_key_masked"] != secret
        assert secret not in blob
        log_tail = zf.read("logs/friday.log.tail.txt").decode("utf-8")
        assert secret not in log_tail
        assert "sk-***" in log_tail


def test_api_diagnostics_export_returns_zip_without_secrets(tmp_appdata):
    secret = "sk-api-export-secret-key"
    save_settings(UserSettings(api_key=secret))
    log_file_path().write_text(f"line with {secret}\n", encoding="utf-8")

    server_mod._backend_ready = True
    client = TestClient(server_mod.app)
    token = ensure_api_token()
    res = client.post("/api/diagnostics/export", headers={"X-Friday-Token": token})

    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("application/zip")
    disposition = res.headers.get("content-disposition", "")
    assert "Friday-diagnostic" in disposition

    with zipfile.ZipFile(io.BytesIO(res.content), "r") as zf:
        combined = "".join(zf.read(name).decode("utf-8", errors="replace") for name in zf.namelist())
        assert secret not in combined
        assert "settings.json" not in zf.namelist()
        assert not any(n.startswith("credentials/") for n in zf.namelist())
