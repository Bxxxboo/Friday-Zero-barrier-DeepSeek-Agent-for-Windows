"""微信扫码登录控制台：转发 openclaw 输出，终端二维码优先，浏览器链接作备用。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir
from friday.weixin.config import openclaw_env, openclaw_state_dir
from friday.weixin.openclaw_cli import openclaw_shell_invocation, resolve_node_exe, resolve_openclaw_command

_log = get_logger("weixin.login")

WEIXIN_PLUGIN_ID = "openclaw-weixin"
WEIXIN_LOGIN_URL_RE = re.compile(
    r"https://(?:liteapp\.weixin\.qq\.com|[\w.-]*weixin\.qq\.com)/[^\s)\]\",]+",
    re.I,
)
CONSOLE_TITLE = "Friday 微信扫码"
WT_WINGET_ID = "Microsoft.WindowsTerminal"


def _runner_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--weixin-login"]
    return [sys.executable, "-m", "friday.weixin.login_runner"]


def _login_url_cache_path() -> Path:
    return get_appdata_dir() / "runtime" / "weixin-login-url.txt"


def _login_bridge_mjs_path() -> Path:
    return get_appdata_dir() / "runtime" / "weixin-login.mjs"


def clear_cached_login_url() -> None:
    try:
        _login_url_cache_path().unlink(missing_ok=True)
    except OSError:
        pass


def read_cached_login_url(*, max_age_sec: float = 600.0) -> str:
    path = _login_url_cache_path()
    if not path.is_file():
        return ""
    try:
        if max_age_sec > 0 and time.time() - path.stat().st_mtime > max_age_sec:
            return ""
        url = path.read_text(encoding="utf-8").strip()
        return url if url.startswith("https://") else ""
    except OSError:
        return ""


def _cache_login_url(url: str) -> None:
    cleaned = url.rstrip(").,]")
    if not cleaned.startswith("https://"):
        return
    path = _login_url_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(cleaned, encoding="utf-8")
    except OSError as exc:
        _log.warning("无法缓存扫码链接 | %s", exc)


def extract_login_url(line: str) -> str | None:
    match = WEIXIN_LOGIN_URL_RE.search(line)
    if match:
        return match.group(0).rstrip(").,]")
    for candidate in re.findall(r"https://[^\s)\]\",]+", line):
        cleaned = candidate.rstrip(").,]")
        if re.search(r"weixin|liteapp", cleaned, re.I):
            return cleaned
    return None


def _creationflags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _wt_state_path() -> Path:
    return get_appdata_dir() / "runtime" / "windows-terminal.json"


def _load_wt_state() -> dict:
    path = _wt_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_wt_state(**fields: object) -> None:
    path = _wt_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_wt_state()
    state.update(fields)
    state["updated_at"] = time.time()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_windows_terminal() -> str | None:
    for name in ("wt", "wt.exe"):
        found = shutil.which(name)
        if found:
            return found
    local_apps = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "wt.exe"
    if local_apps.is_file():
        return str(local_apps)
    return None


def _try_winget_windows_terminal() -> bool:
    if os.name != "nt":
        return False
    winget = shutil.which("winget")
    if not winget:
        _log.info("未找到 winget，跳过 Windows Terminal 自动安装")
        return False
    _log.info("尝试通过 winget 安装 Windows Terminal…")
    try:
        proc = subprocess.run(
            [
                winget,
                "install",
                "-e",
                "--id",
                WT_WINGET_ID,
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
            creationflags=_creationflags(),
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-400:]
            _log.warning("winget 安装 Windows Terminal 失败 | code=%s %s", proc.returncode, tail)
            return False
        return _find_windows_terminal() is not None
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log.warning("winget 安装 Windows Terminal 异常 | %s", exc)
        return False


def ensure_windows_terminal(*, allow_install: bool = True) -> str | None:
    """查找 wt.exe；缺失时最多尝试一次 winget 自动安装。"""
    found = _find_windows_terminal()
    if found:
        _save_wt_state(installed=True, path=found)
        return found

    state = _load_wt_state()
    if state.get("install_attempted"):
        return None

    if not allow_install:
        return None

    _save_wt_state(install_attempted=True)
    if _try_winget_windows_terminal():
        found = _find_windows_terminal()
        if found:
            _save_wt_state(installed=True, path=found, install_attempted=True)
            _log.info("Windows Terminal 已就绪 | path=%s", found)
            return found
    return None


def _prepare_console() -> None:
    if os.name != "nt":
        return
    os.system("chcp 65001 >nul")
    os.system("mode con cols=100 lines=55 >nul")
    print()
    print("=" * 52)
    print("  微信扫码登录")
    print("  请优先扫描下方终端二维码")
    print("  若无法扫描，可到星期五设置页点「浏览器打开扫码页」")
    print("=" * 52)
    print()
    print("正在启动 OpenClaw 登录流程，请稍候…")
    print()


def _print_browser_fallback_hint(url: str) -> None:
    print()
    print("请优先扫描上方终端里的二维码。")
    print("若二维码无法显示或无法扫描，请到星期五设置 → 微信桥接，点「浏览器打开扫码页」。")
    print(f"备用链接：{url}")
    print()


def _note_login_url(url: str) -> None:
    """缓存扫码链接并提示备用方式，不自动打开浏览器。"""
    cleaned = url.rstrip(").,]")
    _cache_login_url(cleaned)
    _print_browser_fallback_hint(cleaned)


def _open_login_url(url: str) -> bool:
    cleaned = url.rstrip(").,]")
    _cache_login_url(cleaned)
    try:
        webbrowser.open(cleaned)
        return True
    except OSError as exc:
        _log.warning("无法打开浏览器 | url=%s err=%s", cleaned, exc)
        return False


def _write_login_shell_cmd() -> Path:
    """openclaw channels login 子脚本（由 weixin-login.cmd / mjs 调用）。"""
    path = get_appdata_dir() / "runtime" / "weixin-login-shell.cmd"
    path.parent.mkdir(parents=True, exist_ok=True)
    openclaw_line = openclaw_shell_invocation(["channels", "login", "--channel", WEIXIN_PLUGIN_ID])
    path.write_text(f"@echo off\r\n{openclaw_line}\r\n", encoding="utf-8")
    return path


def _batch_set(name: str, value: str) -> str:
    escaped = str(value).replace("%", "%%")
    return f'set "{name}={escaped}"'


def _login_cmd_env() -> dict[str, str]:
    """扫码 .cmd 仅需的环境变量（勿写入整个 os.environ）。"""
    from friday.edition import openclaw_gateway_port
    from friday.weixin.node_runtime import NODE_HOME, NPM_GLOBAL, NPM_REGISTRY_DEFAULT

    path_parts: list[str] = []
    if NODE_HOME.is_dir():
        path_parts.append(str(NODE_HOME))
    if NPM_GLOBAL.is_dir():
        path_parts.append(str(NPM_GLOBAL))
    existing = os.environ.get("PATH", "")
    merged_path = os.pathsep.join(path_parts + ([existing] if existing else []))

    return {
        "OPENCLAW_STATE_DIR": str(openclaw_state_dir()),
        "OPENCLAW_GATEWAY_PORT": str(openclaw_gateway_port()),
        "PATH": merged_path,
        "NPM_CONFIG_REGISTRY": NPM_REGISTRY_DEFAULT,
        "npm_config_registry": NPM_REGISTRY_DEFAULT,
    }


def _write_login_cmd() -> Path:
    """自包含扫码启动脚本：不依赖 wt 传递环境变量。"""
    path = get_appdata_dir() / "runtime" / "weixin-login.cmd"
    path.parent.mkdir(parents=True, exist_ok=True)
    env = _login_cmd_env()
    shell_cmd = _write_login_shell_cmd()
    url_cache = _login_url_cache_path()
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f"title {CONSOLE_TITLE}",
        "echo.",
        "echo ====================================================",
        "echo   微信扫码登录",
        "echo   请优先扫描下方终端二维码",
        "echo   若无法扫描，回到星期五点「浏览器打开扫码页」",
        "echo ====================================================",
        "echo.",
    ]
    for key in sorted(env):
        lines.append(_batch_set(key, env[key]))
    lines.append(_batch_set("FRIDAY_WEIXIN_LOGIN_URL_FILE", str(url_cache)))
    lines.append(_batch_set("FRIDAY_OPENCLAW_LOGIN_SHELL_FILE", str(shell_cmd)))

    node = resolve_node_exe()
    mjs = _write_login_bridge_mjs()
    if node and mjs.is_file():
        lines.append(f'"{node}" "{mjs}"')
    else:
        lines.extend(
            [
                "echo.",
                "echo [错误] 未找到 Node.js，无法启动扫码。请先完成「一键配置」。",
                "echo.",
            ]
        )
        lines.append(subprocess.list2cmdline(_runner_argv()))
    lines.extend(
        [
            "if errorlevel 1 (",
            "  echo.",
            "  echo 登录进程异常退出，请查看上方错误信息。",
            ")",
            "echo.",
            "pause",
        ]
    )
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def _write_login_bridge_mjs() -> Path:
    path = _login_bridge_mjs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const shellFile = process.env.FRIDAY_OPENCLAW_LOGIN_SHELL_FILE;
if (!shellFile) {
  console.error("缺少 FRIDAY_OPENCLAW_LOGIN_SHELL_FILE 环境变量");
  process.exit(1);
}

console.log("");
console.log("=".repeat(52));
console.log("  微信扫码登录");
console.log("  请优先扫描下方终端二维码");
console.log("  若无法扫描，回到星期五点「浏览器打开扫码页」");
console.log("=".repeat(52));
console.log("");
console.log("正在启动 OpenClaw 登录流程，请稍候…");
console.log("");

const URL_RE = /https:\\/\\/(?:liteapp\\.weixin\\.qq\\.com|[\\w.-]*weixin\\.qq\\.com)\\/[^\\s)\\]\\",]+/gi;
let urlNoted = false;

function maybeNoteUrl(chunk) {
  if (urlNoted) return;
  const text = String(chunk);
  const matches = text.match(URL_RE) || [];
  for (const raw of matches) {
    const url = raw.replace(/[).,\\]]+$/, "");
    if (!/weixin|liteapp/i.test(url)) continue;
    urlNoted = true;
    const cachePath = process.env.FRIDAY_WEIXIN_LOGIN_URL_FILE;
    if (cachePath) {
      try {
        mkdirSync(dirname(cachePath), { recursive: true });
        writeFileSync(cachePath, url, "utf8");
      } catch {
        /* non-critical */
      }
    }
    console.log("");
    console.log("请优先扫描上方终端里的二维码。");
    console.log("若二维码无法显示或无法扫描，请到星期五设置 → 微信桥接，点「浏览器打开扫码页」。");
    console.log(`备用链接：${url}`);
    console.log("");
    break;
  }
}

const child = spawn("cmd.exe", ["/c", shellFile], {
  env: process.env,
  stdio: ["inherit", "pipe", "inherit"],
  windowsHide: false,
});

child.stdout.setEncoding("utf8");
child.stdout.on("data", (chunk) => {
  process.stdout.write(chunk);
  maybeNoteUrl(chunk);
});

child.on("close", (code) => process.exit(code ?? 1));
""",
        encoding="utf-8",
    )
    return path


def _login_launch_env() -> dict[str, str]:
    return openclaw_env()


def _spawn_login_console(*, wt: str | None) -> None:
    cmd_path = _write_login_cmd()
    call_cmd = f'call "{cmd_path}"'
    _log.info(
        "打开微信扫码窗口 | script=%s node=%s wt=%s",
        cmd_path,
        resolve_node_exe() or "(missing)",
        wt or "(cmd start)",
    )
    if wt:
        # wt 对 cmd /k 后的复杂引号解析不稳定，统一 call 自包含 .cmd
        subprocess.Popen(
            [wt, "-w", "0", "new-tab", "--title", CONSOLE_TITLE, "cmd.exe", "/k", call_cmd],
            cwd=str(get_appdata_dir() / "runtime"),
        )
        return
    subprocess.Popen(
        ["cmd.exe", "/c", "start", CONSOLE_TITLE, "cmd.exe", "/k", call_cmd],
        cwd=str(get_appdata_dir() / "runtime"),
    )


def run_weixin_login_console() -> int:
    _prepare_console()
    cmd = [*resolve_openclaw_command(), "channels", "login", "--channel", WEIXIN_PLUGIN_ID]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=openclaw_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    url_noted = False
    try:
        stream = proc.stdout
        if stream is None:
            return proc.wait() or 1
        for line in stream:
            sys.stdout.write(line)
            sys.stdout.flush()
            if url_noted:
                continue
            url = extract_login_url(line)
            if not url:
                continue
            _note_login_url(url)
            url_noted = True
    finally:
        return proc.wait()


def launch_weixin_login_console() -> tuple[bool, str]:
    if os.name != "nt":
        line = " ".join(_runner_argv())
        return False, f"请在终端执行：{line}"
    try:
        using_node = resolve_node_exe() is not None
        wt = ensure_windows_terminal()
        _spawn_login_console(wt=wt)
        if using_node:
            return True, (
                "已打开扫码窗口。请优先扫描终端里的二维码；"
                "若无法扫描，再点「浏览器打开扫码页」。"
            )
        if wt:
            return True, (
                "已打开扫码窗口。若未看到输出，请关闭后重试，"
                "或先完成「一键配置」安装 Node.js / OpenClaw。"
            )
        return True, (
            "已打开扫码窗口（经典 CMD）。"
            "请优先扫描终端二维码；若不行，在设置页点「浏览器打开扫码页」。"
        )
    except OSError as exc:
        _log.warning("无法打开扫码窗口 | %s", exc)
        return False, f"无法打开登录窗口：{exc}"


def open_cached_login_url_in_browser() -> tuple[bool, str]:
    url = read_cached_login_url()
    if url:
        if _open_login_url(url):
            return True, "已在浏览器打开最近的扫码链接"
        return False, "无法打开浏览器，请手动复制链接：" + url
    return False, "暂无扫码链接。请先点「打开微信扫码登录」，等待终端输出链接后再试。"


def main() -> None:
    code = run_weixin_login_console()
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
