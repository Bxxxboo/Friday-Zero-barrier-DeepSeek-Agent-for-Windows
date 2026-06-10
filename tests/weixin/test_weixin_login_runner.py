from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from friday.weixin.login_runner import (
    WEIXIN_LOGIN_URL_RE,
    clear_cached_login_url,
    ensure_windows_terminal,
    extract_login_url,
    launch_weixin_login_console,
    read_cached_login_url,
    run_weixin_login_console,
)


def test_weixin_login_url_regex():
    line = "https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=abc123&bot_type=3"
    match = WEIXIN_LOGIN_URL_RE.search(line)
    assert match is not None
    assert "liteapp.weixin.qq.com" in match.group(0)


def test_extract_login_url_from_logger_line():
    line = "二维码链接: https://liteapp.weixin.qq.com/q/test?qrcode=abc&bot_type=3"
    url = extract_login_url(line)
    assert url is not None
    assert url.startswith("https://liteapp.weixin.qq.com/")


def test_read_cached_login_url(tmp_path, monkeypatch):
    cache = tmp_path / "weixin-login-url.txt"
    cache.write_text("https://liteapp.weixin.qq.com/q/x", encoding="utf-8")
    monkeypatch.setattr("friday.weixin.login_runner._login_url_cache_path", lambda: cache)
    assert read_cached_login_url() == "https://liteapp.weixin.qq.com/q/x"
    clear_cached_login_url()
    assert read_cached_login_url() == ""


def test_write_login_cmd_contains_env_and_node(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    mjs = runtime / "weixin-login.mjs"
    mjs.write_text("// stub", encoding="utf-8")
    monkeypatch.setattr("friday.weixin.login_runner.get_appdata_dir", lambda: tmp_path)
    monkeypatch.setattr("friday.weixin.login_runner.resolve_node_exe", lambda: r"C:\node\node.exe")
    monkeypatch.setattr(
        "friday.weixin.login_runner._login_cmd_env",
        lambda: {"OPENCLAW_STATE_DIR": r"C:\Users\me\.openclaw", "PATH": r"C:\node"},
    )
    monkeypatch.setattr(
        "friday.weixin.login_runner.openclaw_shell_invocation",
        lambda args: 'openclaw.cmd channels login --channel openclaw-weixin',
    )
    monkeypatch.setattr("friday.weixin.login_runner._write_login_bridge_mjs", lambda: mjs)

    from friday.weixin.login_runner import _write_login_cmd

    cmd_path = _write_login_cmd()
    text = cmd_path.read_text(encoding="utf-8")
    assert "OPENCLAW_STATE_DIR" in text
    assert r"C:\node\node.exe" in text
    assert "weixin-login.mjs" in text
    assert "pause" in text


def test_run_weixin_login_console_caches_url_without_browser(monkeypatch):
    output = (
        "正在启动微信扫码登录...\n"
        "若二维码未能显示或无法使用，你可以访问以下链接以继续：\n"
        "https://liteapp.weixin.qq.com/q/test?qrcode=deadbeef&bot_type=3\n"
        "正在等待操作...\n"
    )

    class _FakeProc:
        returncode = 0

        def __init__(self):
            self.stdout = io.StringIO(output)

        def wait(self):
            return 0

    noted: list[str] = []

    monkeypatch.setattr(
        "friday.weixin.login_runner.resolve_openclaw_command",
        lambda: ["openclaw"],
    )
    monkeypatch.setattr("friday.weixin.login_runner._prepare_console", lambda: None)
    monkeypatch.setattr("friday.weixin.login_runner.subprocess.Popen", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(
        "friday.weixin.login_runner._note_login_url",
        lambda url: noted.append(url),
    )

    code = run_weixin_login_console()
    assert code == 0
    assert noted
    assert noted[0].startswith("https://liteapp.weixin.qq.com/")


def test_launch_weixin_login_console_prefers_windows_terminal(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_popen(args, **kwargs):
        calls.append(list(args))
        return MagicMock()

    monkeypatch.setattr(
        "friday.weixin.login_runner.ensure_windows_terminal",
        lambda **kwargs: r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\wt.exe",
    )
    monkeypatch.setattr("friday.weixin.login_runner.get_appdata_dir", lambda: tmp_path)
    monkeypatch.setattr("friday.weixin.login_runner.resolve_node_exe", lambda: r"C:\node\node.exe")
    monkeypatch.setattr(
        "friday.weixin.login_runner._login_cmd_env",
        lambda: {"OPENCLAW_STATE_DIR": r"C:\Users\me\.openclaw"},
    )
    monkeypatch.setattr(
        "friday.weixin.login_runner.openclaw_shell_invocation",
        lambda args: "openclaw.cmd channels login --channel openclaw-weixin",
    )
    monkeypatch.setattr(
        "friday.weixin.login_runner._write_login_bridge_mjs",
        lambda: tmp_path / "runtime" / "weixin-login.mjs",
    )
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "weixin-login.mjs").write_text("// stub", encoding="utf-8")
    monkeypatch.setattr("friday.weixin.login_runner.subprocess.Popen", fake_popen)

    ok, msg = launch_weixin_login_console()
    assert ok
    assert "终端" in msg
    assert calls
    assert calls[0][0].endswith("wt.exe")
    assert "Friday 微信扫码" in calls[0]
    assert calls[0][-1].startswith('call "')
    assert calls[0][-1].endswith('weixin-login.cmd"')


def test_launch_weixin_login_console_falls_back_to_cmd(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    monkeypatch.setattr("friday.weixin.login_runner.ensure_windows_terminal", lambda **kwargs: None)
    monkeypatch.setattr("friday.weixin.login_runner.get_appdata_dir", lambda: tmp_path)
    monkeypatch.setattr("friday.weixin.login_runner.resolve_node_exe", lambda: r"C:\node\node.exe")
    monkeypatch.setattr(
        "friday.weixin.login_runner._login_cmd_env",
        lambda: {"OPENCLAW_STATE_DIR": r"C:\Users\me\.openclaw"},
    )
    monkeypatch.setattr(
        "friday.weixin.login_runner.openclaw_shell_invocation",
        lambda args: "openclaw.cmd channels login --channel openclaw-weixin",
    )
    monkeypatch.setattr(
        "friday.weixin.login_runner._write_login_bridge_mjs",
        lambda: tmp_path / "runtime" / "weixin-login.mjs",
    )
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "weixin-login.mjs").write_text("// stub", encoding="utf-8")
    monkeypatch.setattr(
        "friday.weixin.login_runner.subprocess.Popen",
        lambda args, **kwargs: calls.append(list(args)) or MagicMock(),
    )

    ok, msg = launch_weixin_login_console()
    assert ok
    assert calls
    assert calls[0][:4] == ["cmd.exe", "/c", "start", "Friday 微信扫码"]
    assert calls[0][-1].startswith('call "')


def test_ensure_windows_terminal_skips_repeat_winget(tmp_path, monkeypatch):
    state = tmp_path / "windows-terminal.json"
    state.write_text('{"install_attempted": true}', encoding="utf-8")
    monkeypatch.setattr("friday.weixin.login_runner._wt_state_path", lambda: state)
    monkeypatch.setattr("friday.weixin.login_runner._find_windows_terminal", lambda: None)

    def fail_winget():
        raise AssertionError("winget should not run twice")

    monkeypatch.setattr("friday.weixin.login_runner._try_winget_windows_terminal", fail_winget)
    assert ensure_windows_terminal() is None


def test_ensure_windows_terminal_tries_winget_once(tmp_path, monkeypatch):
    state = tmp_path / "windows-terminal.json"
    monkeypatch.setattr("friday.weixin.login_runner._wt_state_path", lambda: state)
    find_results = [None, r"C:\wt.exe"]

    def fake_find():
        return find_results.pop(0) if find_results else r"C:\wt.exe"

    monkeypatch.setattr("friday.weixin.login_runner._find_windows_terminal", fake_find)
    monkeypatch.setattr("friday.weixin.login_runner._try_winget_windows_terminal", lambda: True)

    found = ensure_windows_terminal()
    assert found == r"C:\wt.exe"
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved.get("install_attempted") is True


def test_launch_weixin_login_requires_cli(monkeypatch):
    monkeypatch.setattr("friday.weixin.setup._openclaw_cli_available", lambda: False)
    from friday.weixin.setup import launch_weixin_login_terminal

    ok, msg = launch_weixin_login_terminal()
    assert not ok
    assert "openclaw" in msg.lower()


def test_launch_weixin_login_requires_gateway(monkeypatch):
    monkeypatch.setattr("friday.weixin.setup._openclaw_cli_available", lambda: True)
    monkeypatch.setattr("friday.weixin.setup._weixin_channel_available", lambda: True)
    monkeypatch.setattr("friday.weixin.setup.configure_openclaw_plugins", lambda: (True, "ok"))
    monkeypatch.setattr("friday.weixin.setup.start_gateway", lambda: (False, "端口被占用"))
    from friday.weixin.setup import launch_weixin_login_terminal

    ok, msg = launch_weixin_login_terminal()
    assert not ok
    assert "Gateway" in msg


def test_launch_weixin_login_delegates_to_runner(monkeypatch):
    monkeypatch.setattr("friday.weixin.setup._openclaw_cli_available", lambda: True)
    monkeypatch.setattr("friday.weixin.setup._weixin_channel_available", lambda: True)
    monkeypatch.setattr("friday.weixin.setup.configure_openclaw_plugins", lambda: (True, "ok"))
    monkeypatch.setattr("friday.weixin.setup.start_gateway", lambda: (True, "running"))
    monkeypatch.setattr("friday.weixin.login_runner.clear_cached_login_url", lambda: None)
    monkeypatch.setattr(
        "friday.weixin.login_runner.launch_weixin_login_console",
        lambda: (True, "已打开扫码窗口；浏览器会自动弹出扫码页"),
    )
    from friday.weixin.setup import launch_weixin_login_terminal

    ok, msg = launch_weixin_login_terminal()
    assert ok
    assert "浏览器" in msg
    assert "刷新状态" in msg
