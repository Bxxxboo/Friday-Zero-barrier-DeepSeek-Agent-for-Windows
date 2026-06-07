from __future__ import annotations

from unittest.mock import patch

from friday.win10_runtime import (
    RuntimeItem,
    check_dotnet_framework,
    check_vc_redist,
    check_webview2,
    collect_runtime_status,
    ensure_win10_runtime,
    runtime_status_payload,
)


def test_collect_runtime_status_shape():
    items = collect_runtime_status()
    assert len(items) == 3
    assert {item.id for item in items} == {"dotnet", "vcredist", "webview2"}


def test_runtime_status_payload():
    payload = runtime_status_payload()
    assert "items" in payload
    assert isinstance(payload["items"], list)


def test_check_webview2_ok_when_registry_has_version(monkeypatch):
    monkeypatch.setattr(
        "friday.win10_runtime._read_reg_str",
        lambda root, path, name: "120.0.0.0" if name == "pv" else "",
    )
    item = check_webview2()
    assert item.ok
    assert "120.0.0.0" in item.message


def test_check_vc_redist_ok_when_dll_loads(monkeypatch):
    class _FakeDll:
        pass

    monkeypatch.setattr("ctypes.WinDLL", lambda _name: _FakeDll())
    monkeypatch.setattr("friday.win10_runtime._read_reg_dword", lambda *args, **kwargs: None)
    item = check_vc_redist()
    assert item.ok


def test_ensure_win10_runtime_blocks_missing_dotnet(monkeypatch):
    monkeypatch.setattr(
        "friday.win10_runtime.check_dotnet_framework",
        lambda: RuntimeItem("dotnet", ".NET", False, "缺少 .NET"),
    )
    monkeypatch.setattr(
        "friday.win10_runtime.check_vc_redist",
        lambda: RuntimeItem("vcredist", "VC++", True, "ok"),
    )
    monkeypatch.setattr(
        "friday.win10_runtime.check_webview2",
        lambda: RuntimeItem("webview2", "WebView2", True, "ok"),
    )
    ok, msgs = ensure_win10_runtime(auto_install=False)
    assert not ok
    assert any(".NET" in m for m in msgs)


def test_ensure_win10_runtime_auto_install_webview2(monkeypatch):
    state = {"wv2": False}

    def _wv2():
        if state["wv2"]:
            return RuntimeItem("webview2", "WebView2", True, "ok")
        return RuntimeItem("webview2", "WebView2", False, "missing", can_auto_install=True)

    monkeypatch.setattr(
        "friday.win10_runtime.check_dotnet_framework",
        lambda: RuntimeItem("dotnet", ".NET", True, "ok"),
    )
    monkeypatch.setattr("friday.win10_runtime.check_vc_redist", lambda: RuntimeItem("vcredist", "VC++", True, "ok"))
    monkeypatch.setattr("friday.win10_runtime.check_webview2", _wv2)

    def _install():
        state["wv2"] = True
        return True, "installed"

    monkeypatch.setattr("friday.win10_runtime.install_webview2", _install)
    ok, msgs = ensure_win10_runtime(auto_install=True)
    assert ok
    assert any("WebView2" in m for m in msgs)


def test_check_dotnet_non_windows(monkeypatch):
    monkeypatch.setattr("friday.win10_runtime.sys.platform", "linux")
    item = check_dotnet_framework()
    assert item.ok
