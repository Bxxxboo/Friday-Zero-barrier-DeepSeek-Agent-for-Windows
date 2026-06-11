"""在工作区 Python 环境中执行代码或脚本。"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import os
from pathlib import Path

from friday.logging_config import get_logger
from friday.python_env import resolve_agent_python, setup_agent_env  # 返回 FridayAgent.exe（Windows）
from friday.storage import load_settings, resolved_workspace
from friday.tools._decorators import register_tool

_log = get_logger("python_runner")

_MAX_OUTPUT = 8000

_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\bos\.system\s*\(", "os.system"),
    (r"\bsubprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*true", "subprocess shell=True"),
    (r"\bshutil\.rmtree\s*\(\s*['\"]?(?:c:|/etc|/var|/usr|\\\\)", "删除系统目录"),
    (r"\b(?:format|diskpart)\b", "磁盘格式化"),
    (r"\bctypes\.windll\.(?:ntdll|kernel32)\b", "底层 Windows API 调用"),
]


def _normalize_code(code: str) -> str:
    # 与 shell._normalize_command 一致：去掉反引号续行混淆后再匹配
    return re.sub(r"\s+", " ", code.replace("`", "").strip().lower())


def _check_dangerous_code(code: str) -> str | None:
    normalized = _normalize_code(code)
    for pattern, reason in _DANGEROUS_PATTERNS:
        if re.search(pattern, normalized):
            _log.warning("拦截危险 Python 代码 | reason=%s", reason)
            return reason
    return None


def _resolve_cwd(cwd: str) -> Path:
    settings = load_settings()
    workspace = resolved_workspace(settings)
    if cwd.strip():
        return Path(cwd).expanduser().resolve()
    return Path(workspace).expanduser().resolve()


def _run_process(
    args: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> str:
    run_kwargs: dict = {
        "args": args,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "cwd": str(cwd),
        "env": {**os.environ, "PYTHONIOENCODING": "utf-8"},
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
        return f"Python 执行超时（>{timeout}s），已终止。"

    output = (completed.stdout or "") + (completed.stderr or "")
    output = output.strip() or "(无输出)"
    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + "\n... (输出已截断)"
    return f"exit={completed.returncode}\n{output}"


def _ensure_python(workspace: str) -> tuple[Path | None, str]:
    py, msg = resolve_agent_python(workspace, auto_setup=True)
    if py:
        return py, msg
    ok, setup_msg = setup_agent_env(workspace)
    if not ok:
        return None, setup_msg
    py, msg = resolve_agent_python(workspace, auto_setup=False)
    return py, msg or setup_msg


@register_tool(
    name="python_env_info",
    description="查看工作区 Agent Python 环境状态（版本、路径、是否已安装常用库）",
    parameters={"type": "object", "properties": {}},
)
def python_env_info() -> str:
    from friday.python_env import get_env_status

    workspace = resolved_workspace(load_settings())
    status = get_env_status(workspace)
    lines = [
        f"就绪: {'是' if status.ready else '否'}",
        f"环境目录: {status.env_dir}",
    ]
    if status.python_exe:
        lines.append(f"解释器: {status.python_exe}")
        lines.append(f"版本: {status.version}")
    lines.append(f"说明: {status.message}")
    return "\n".join(lines)


@register_tool(
    name="run_python",
    description=(
        "在工作区 .python-env 中一次性执行完整 Python 脚本（非 REPL 片段）。"
        "必须把 import、逻辑、输出合并为一段可独立运行的 code，禁止分多次调用做试探。"
        "多步任务（读配置、调 API、写文件、验证）应写进同一次 code。"
        "超长脚本用 write_text_file 保存后用 run_python_script。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要执行的 Python 源码"},
            "cwd": {"type": "string", "description": "工作目录，默认是默认操作文件夹"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 120"},
        },
        "required": ["code"],
    },
)
def run_python(code: str, cwd: str = "", timeout: int = 120) -> str:
    from friday.python_code_safety import analyze_python_code

    danger = _check_dangerous_code(code)
    if danger:
        return f"⛔ 已拒绝危险 Python 代码（{danger}）。"

    safety = analyze_python_code(code)
    if safety.blocked:
        return f"⛔ {safety.block_reason}"

    workspace = resolved_workspace(load_settings())
    python_exe, env_msg = _ensure_python(workspace)
    if not python_exe:
        return f"Python 环境不可用：{env_msg}"

    work_dir = _resolve_cwd(cwd)
    work_dir.mkdir(parents=True, exist_ok=True)

    _log.info("执行 Python 代码 | cwd=%s | timeout=%d | head=%.120s", work_dir, timeout, code[:120])

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".py",
        delete=False,
        dir=work_dir,
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = _run_process([str(python_exe), tmp_path], cwd=work_dir, timeout=timeout)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    if env_msg and "已就绪" in env_msg:
        return f"{env_msg}\n\n{result}"
    return result


@register_tool(
    name="run_python_script",
    description=(
        "运行工作区内的 .py 脚本（.python-env 解释器）。"
        "适合已用 write_text_file 写好的完整脚本；不要用来替代本应一次 run_python 完成的小片段。"
        "args 为传给脚本的命令行参数（空格分隔）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "脚本绝对或相对路径"},
            "args": {"type": "string", "description": "脚本参数，可选"},
            "cwd": {"type": "string", "description": "工作目录，默认同脚本所在目录"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 300"},
        },
        "required": ["path"],
    },
)
def run_python_script(path: str, args: str = "", cwd: str = "", timeout: int = 300) -> str:
    from friday.python_code_safety import analyze_python_script_file

    script = Path(path).expanduser().resolve()
    if not script.is_file():
        return f"脚本不存在: {path}"
    if script.suffix.lower() != ".py":
        return "仅支持 .py 脚本。"

    safety = analyze_python_script_file(str(script))
    if safety.blocked:
        return f"⛔ {safety.block_reason}"

    workspace = resolved_workspace(load_settings())
    python_exe, env_msg = _ensure_python(workspace)
    if not python_exe:
        return f"Python 环境不可用：{env_msg}"

    work_dir = _resolve_cwd(cwd) if cwd.strip() else script.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = [str(python_exe), str(script)]
    if args.strip():
        cmd.extend(args.split())

    _log.info("执行 Python 脚本 | script=%s | timeout=%d", script, timeout)
    result = _run_process(cmd, cwd=work_dir, timeout=timeout)
    try:
        from friday.artifacts import is_artifacts_path, mark_script_consumed

        if is_artifacts_path(script):
            mark_script_consumed(script)
    except Exception:
        pass
    if env_msg and "已就绪" in env_msg and "exit=0" not in result[:20]:
        return result
    return result
