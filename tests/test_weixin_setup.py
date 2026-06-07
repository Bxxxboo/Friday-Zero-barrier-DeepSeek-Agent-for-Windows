from friday.safety import describe_approval_plain
from friday.weixin.setup import collect_setup_steps, configure_openclaw_plugins


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
