"""PowerShell 命令执行 —— 带安全加固。

安全策略：
1. 执行时加 --NoProfile --NonInteractive 减少侧载风险
2. 隐藏控制台窗口（Windows CREATE_NO_WINDOW）
3. 正则匹配危险模式（格式化磁盘、删除系统文件、关机、修改安全策略等）
4. 禁止 Invoke-WebRequest 等下载命令（应使用 download_software / download_file）
5. 所有命令写入日志以便审计
"""

from __future__ import annotations

import re
import subprocess
import sys

from friday.logging_config import get_logger
from friday.tools._decorators import register_tool

_log = get_logger("shell")

_PS_UTF8_PREFIX = (
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
    "$OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
)
# 注意：攻击者可能用 `b`acktick 混淆，这里去反引号后再匹配
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # 格式化磁盘
    (r"\bformat\b.*[a-z]:", "格式化磁盘"),
    # 删除系统根目录
    (r"\b(remove-item|rm|del|rmdir|rd)\b.*-(r|recurse|force)\b.*(c:\\|d:\\|e:\\|f:\\|g:\\|h:\\|/etc|/var|/home|~)", "递归删除系统根目录"),
    # 关机 / 重启
    (r"\b(stop-computer|restart-computer|shutdown)\b", "关机/重启"),
    # 停止关键进程
    (r"\bstop-process\b.*\b(lsass|csrss|winlogon|smss|services|svchost|explorer)\b", "停止系统关键进程"),
    # 修改防火墙/安全策略
    (r"\b(set-netfirewallprofile|netsh\s+advfirewall|set-executionpolicy)\b.*\b(disable|bypass|unrestricted)\b", "禁用防火墙/安全策略"),
    # 清除事件日志
    (r"\b(clear-eventlog|wevtutil\s+cl)\b", "清除系统日志"),
    # 添加用户/提权
    (r"\bnet\s+(localgroup\s+administrators\s+/add|user\s+\S+\s+/add)\b", "添加用户/提权"),
    # 注册表关键路径写入
    (r"\b(set-itemproperty|new-item)\b.*\b(HKLM:\\|HKEY_LOCAL_MACHINE)\b.*-(force|value)", "修改 HKLM 注册表"),
    # base64 编码命令 (高度可疑)
    (r"\b-(e|enc|encodedcommand|encoded)\b", "使用 Base64 编码命令"),
]

_DOWNLOAD_PATTERNS = (
    r"\b(iwr|invoke-webrequest|invoke-restmethod|wget|curl|start-bitstransfer)\b",
    r"\b(webclient|downloadfile|downloadstring)\b",
)


def _is_download_command(cmd: str) -> bool:
    normalized = _normalize_command(cmd)
    return any(re.search(p, normalized) for p in _DOWNLOAD_PATTERNS)


def _normalize_command(cmd: str) -> str:
    """移除 PowerShell 反引号续行符，合并多余空白。"""
    return re.sub(r"\s+", " ", cmd.replace("`", "")).strip().lower()


def _check_dangerous(cmd: str) -> str | None:
    """返回第一条匹配的危险原因，安全时返回 None。"""
    normalized = _normalize_command(cmd)
    for pattern, reason in _DANGEROUS_PATTERNS:
        if re.search(pattern, normalized):
            _log.warning("拦截危险命令 | pattern=%s | cmd_head=%.120s", reason, cmd[:120])
            return reason
    return None


@register_tool(
    name="run_powershell",
    description=(
        "执行 PowerShell 命令并返回输出。"
        "多步操作应合并为一条命令或脚本块（用 ; 或 here-string），不要分多次调用试探。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "required": ["command"],
    },
)
def run_powershell(command: str, timeout: int = 60) -> str:
    """执行 PowerShell 命令（自动安全检查）。"""
    if _is_download_command(command):
        return (
            "⛔ 不要用 PowerShell 下载文件。请改用 download_software（推荐）或 download_file 工具。"
        )

    # ── 安全检测 ──
    danger = _check_dangerous(command)
    if danger:
        return f"⛔ 已拒绝危险命令（{danger}）。如需执行，请在 PowerShell 终端中手动操作。"

    wrapped = _PS_UTF8_PREFIX + command
    _log.info("执行 PowerShell | cmd_head=%.200s | timeout=%d", command[:200], timeout)

    run_kwargs: dict = {
        "args": [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            wrapped,
        ],
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if sys.platform == "win32":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        run_kwargs["startupinfo"] = startup

    try:
        completed = subprocess.run(**run_kwargs)
    except subprocess.TimeoutExpired:
        _log.warning("PowerShell 超时 timeout=%d | cmd_head=%.120s", timeout, command[:120])
        return f"命令执行超时（>{timeout}s），已自动终止。"

    output = (completed.stdout or "") + (completed.stderr or "")
    output = output.strip() or "(无输出)"
    if len(output) > 6000:
        output = output[:6000] + "\n... (输出已截断)"
    return f"exit={completed.returncode}\n{output}"
