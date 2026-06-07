from friday.safety import describe_approval_plain
from friday.weixin.openclaw_cli import openclaw_shell_invocation
from friday.weixin.setup import (
    collect_setup_steps,
    configure_openclaw_plugins,
    install_openclaw_cli,
    launch_weixin_login_terminal,
)


def test_describe_powershell_desktop():
    text = describe_approval_plain(
        "run_powershell",
        {"command": 'Get-ChildItem "C:/Users/test/Desktop" -Name'},
    )
    assert "桌面" in text


def test_describe_powershell_wscript_shortcuts():
    cmd = (
        '$shell = New-Object -ComObject WScript.Shell; '
        'Get-ChildItem "C:/Users/test/Desktop" | ForEach-Object { $shell.CreateShortcut($_.FullName) }'
    )
    text = describe_approval_plain("run_powershell", {"command": cmd})
    assert "桌面" in text or "快捷方式" in text


def test_describe_powershell_includes_command_detail():
    from friday.safety import describe_approval_detail

    cmd = "Get-Service | Where-Object { $_.Status -eq 'Running' }"
    detail = describe_approval_detail("run_powershell", {"command": cmd})
    assert "命令摘要" in detail
    assert "Get-Service" in detail


def test_describe_powershell_no_vague_fallback():
    text = describe_approval_plain(
        "run_powershell",
        {"command": "Get-Service | Select-Object -First 5 Name, Status"},
    )
    assert "系统命令，可能会访问" not in text
    assert "Get-Service" in text or "查看" in text or "程序" in text


def test_collect_setup_steps_shape():
    steps = collect_setup_steps(port=8765, api_token="test")
    assert len(steps) >= 7
    assert steps[0].id == "openclaw_cli"


def test_configure_openclaw_plugins_idempotent(tmp_path, monkeypatch):
    cfg = tmp_path / "openclaw.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("friday.weixin.setup._openclaw_config_path", lambda: cfg)
    ok, _ = configure_openclaw_plugins()
    assert ok
    data = __import__("json").loads(cfg.read_text(encoding="utf-8"))
    assert "openclaw-weixin" in data["plugins"]["allow"]


def test_install_openclaw_cli_no_node(monkeypatch):
    monkeypatch.setattr("friday.weixin.setup._openclaw_cli_available", lambda: False)
    monkeypatch.setattr(
        "friday.weixin.setup.ensure_node_npm",
        lambda: (False, "无法自动安装 Node.js"),
    )
    ok, msg = install_openclaw_cli()
    assert not ok
    assert "Node" in msg


def test_openclaw_shell_invocation_quotes_cmd_path(monkeypatch, tmp_path):
    cmd = tmp_path / "open claw.cmd"
    cmd.write_text("@echo off", encoding="utf-8")
    monkeypatch.setattr(
        "friday.weixin.openclaw_cli.resolve_openclaw_command",
        lambda: ["cmd", "/c", str(cmd)],
    )
    line = openclaw_shell_invocation(["channels", "login", "--channel", "openclaw-weixin"])
    assert f'"{cmd}"' in line
    assert "channels login" in line


def test_launch_weixin_login_requires_cli(monkeypatch):
    monkeypatch.setattr("friday.weixin.setup._openclaw_cli_available", lambda: False)
    ok, msg = launch_weixin_login_terminal()
    assert not ok
    assert "openclaw" in msg.lower()


def test_launch_weixin_login_opens_terminal(monkeypatch):
    monkeypatch.setattr("friday.weixin.setup._openclaw_cli_available", lambda: True)
    monkeypatch.setattr(
        "friday.weixin.setup.openclaw_shell_invocation",
        lambda _args: "openclaw-test channels login",
    )
    calls: list[list[str]] = []

    def fake_popen(args, **kwargs):
        calls.append(list(args))
        return object()

    monkeypatch.setattr("friday.weixin.setup.subprocess.Popen", fake_popen)
    ok, msg = launch_weixin_login_terminal()
    assert ok
    assert "扫码" in msg
    assert calls and "openclaw-test channels login" in calls[0]
