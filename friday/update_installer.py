"""Windows 打包版一键更新：下载 Release zip → 解压 → 替换安装目录 → 重启。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir, is_frozen, resolve_packaged_exe_in_dir
from friday.update_rollback import backup_install_dir, install_backup_dir, mark_pending_update

_log = get_logger("update_installer")

_apply_lock = threading.Lock()
_apply_state: dict[str, object] = {
    "running": False,
    "phase": "idle",
    "percent": 0,
    "message": "",
    "detail": "",
    "ok": None,
    "version": "",
    "result_message": "",
    "hint": "",
    "log": [],
}

_quit_handler: Callable[[], None] | None = None


def register_quit_handler(handler: Callable[[], None] | None) -> None:
    global _quit_handler
    _quit_handler = handler


def request_app_quit(*, delay: float = 0.8) -> None:
    def _run() -> None:
        if _quit_handler:
            try:
                _quit_handler()
                return
            except Exception:
                _log.exception("退出应用失败")
        os._exit(0)

    threading.Timer(max(0.1, delay), _run).start()


def app_install_dir() -> Path | None:
    """当前 Friday.exe 所在目录（Friday 文件夹）。"""
    if not is_frozen():
        return None
    exe = Path(sys.executable).resolve()
    if exe.is_file():
        return exe.parent
    return None


def can_auto_update() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "一键更新目前仅支持 Windows。"
    if not is_frozen():
        return False, "源码运行模式不支持一键更新，请下载安装包后使用。"
    install = app_install_dir()
    if install is None or not install.is_dir():
        return False, "无法定位程序安装目录。"
    if not (install / Path(sys.executable).name).is_file():
        return False, "安装目录不完整，请重新运行安装程序或覆盖解压 Friday-Update.zip。"
    return True, ""


def _updates_dir() -> Path:
    path = get_appdata_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _report(phase: str, percent: int, message: str, detail: str = "") -> None:
    with _apply_lock:
        _apply_state["phase"] = phase
        _apply_state["percent"] = max(0, min(100, int(percent)))
        _apply_state["message"] = message
        if detail:
            _apply_state["detail"] = detail
        log = _apply_state.setdefault("log", [])
        if isinstance(log, list):
            line = " · ".join(x for x in (message, detail) if x)
            if line and (not log or log[-1] != line):
                log.append(line)
                if len(log) > 12:
                    del log[:-12]


def get_apply_progress_dict() -> dict[str, object]:
    with _apply_lock:
        return dict(_apply_state)


def _format_update_error(exc: BaseException) -> tuple[str, str]:
    """将异常转为 (失败原因, 修复建议)。"""
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code == 404:
            return (
                "更新包下载失败（404：文件不存在）",
                "Release 可能尚未发布完成，请稍后再点「检查更新」，或使用「手动下载」。",
            )
        if code in {401, 403}:
            return (
                f"更新包下载被拒绝（HTTP {code}）",
                "请检查网络或代理设置；也可在浏览器打开 Gitee Releases 手动下载。",
            )
        if code == 429:
            return (
                "更新源请求过于频繁（429）",
                "请等待 1–2 分钟后重试，或使用「手动下载」。",
            )
        if code >= 500:
            return (
                f"更新服务器暂时异常（HTTP {code}）",
                "请稍后重试；若持续失败，请用手动下载覆盖安装。",
            )
        return (
            f"更新包下载失败（HTTP {code}）",
            "请检查网络后重试，或使用「手动下载」。",
        )

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        text = str(reason or exc).lower()
        if isinstance(reason, TimeoutError) or "timed out" in text:
            return (
                "下载更新包超时",
                "网络较慢或被防火墙拦截，请检查网络/代理后重试，或使用「手动下载」。",
            )
        if "ssl" in text or "certificate" in text:
            return (
                "下载更新包时 SSL 证书验证失败",
                "请检查系统时间是否正确；公司网络需配置代理或导入根证书。",
            )
        if "getaddrinfo" in text or "name or service not known" in text:
            return (
                "无法连接更新服务器（DNS 解析失败）",
                "请检查网络与 DNS；国内用户优先使用 Gitee 更新源。",
            )
        return (
            "无法连接更新服务器",
            "请检查网络、防火墙与代理设置，或使用「手动下载」。",
        )

    if isinstance(exc, TimeoutError):
        return (
            "下载或解压更新包超时",
            "请保持网络畅通后重试；文件较大时可能需要数分钟。",
        )

    if isinstance(exc, zipfile.BadZipFile):
        return (
            "更新包已损坏或不是有效的 zip 文件",
            "请重新「检查更新」后再试，或从 Gitee Releases 手动下载完整包。",
        )

    if isinstance(exc, OSError):
        text = str(exc).lower()
        if "permission" in text or "access is denied" in text:
            return (
                "没有权限写入安装目录",
                "请确认星期五安装在可写路径（建议 D:\\Friday），并以普通用户运行；不要装在 Program Files。",
            )
        if "no space" in text or "disk full" in text:
            return (
                "磁盘空间不足，无法完成更新",
                "请清理系统盘或安装目录所在磁盘后重试。",
            )

    if isinstance(exc, RuntimeError):
        detail = str(exc).strip()
        if detail:
            hint = "若反复失败，请完全退出星期五后，用手动下载 zip 覆盖解压。"
            if "Friday 程序文件夹" in detail:
                hint = "请确认下载的是官方 Friday-Update.zip，不要使用配置包或其它 zip。"
            return detail[:240], hint

    detail = str(exc).strip() or type(exc).__name__
    return (
        detail[:240],
        "可打开 设置 → 数据与日志 → 打开日志文件夹 查看 friday.log；仍失败请使用「手动下载」。",
    )


def _fail_apply(*, detail: str, hint: str, percent: int = 5) -> None:
    _report("error", percent, "更新失败", detail)
    with _apply_lock:
        _apply_state["ok"] = False
        _apply_state["phase"] = "error"
        _apply_state["result_message"] = detail
        _apply_state["hint"] = hint
        _apply_state["running"] = False


def _validate_download_url(url: str) -> bool:
    lower = (url or "").strip().lower()
    if not lower.startswith("https://"):
        return False
    allowed = ("gitee.com", "github.com", "githubusercontent.com")
    return any(host in lower for host in allowed)


def _download_release(url: str, dest: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Friday-Desktop"},
    )
    try:
        resp_ctx = urllib.request.urlopen(request, timeout=300)
    except urllib.error.HTTPError as exc:
        detail, hint = _format_update_error(exc)
        raise RuntimeError(f"{detail}\n{hint}") from exc
    except urllib.error.URLError as exc:
        detail, hint = _format_update_error(exc)
        raise RuntimeError(f"{detail}\n{hint}") from exc

    with resp_ctx as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        read = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                read += len(chunk)
                if total > 0:
                    pct = 5 + int(read * 60 / total)
                    mb = read / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    _report(
                        "downloading",
                        pct,
                        "正在下载更新包…",
                        f"{mb:.1f} / {total_mb:.1f} MB",
                    )
                else:
                    _report("downloading", 35, "正在下载更新包…", f"已下载 {read // (1024 * 1024)} MB")

    if not dest.is_file() or dest.stat().st_size < 1024 * 1024:
        raise RuntimeError(
            "下载的更新包过小或为空，可能下载链接失效。"
        )


def _find_friday_app_dir(root: Path) -> Path | None:
    direct = root / "Friday"
    if direct.is_dir() and any(direct.glob("*.exe")):
        return direct
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        if folder.name.lower() == "friday" and any(folder.glob("*.exe")):
            return folder
    for exe in root.rglob("*.exe"):
        parent = exe.parent
        if parent.name.lower() != "friday":
            continue
        if exe.name.lower() == "friday.exe":
            return parent
    for exe in root.rglob("*.exe"):
        parent = exe.parent
        if parent.name.lower() == "friday" or "星期五" in exe.name:
            return parent
    return None


def _extract_release(zip_path: Path, dest_dir: Path) -> Path:
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        detail, hint = _format_update_error(exc)
        raise RuntimeError(f"{detail}\n{hint}") from exc
    with zf:
        members = zf.namelist()
        if not members:
            raise RuntimeError("更新包为空，请从官方 Release 重新下载。")
        for index, member in enumerate(members, start=1):
            zf.extract(member, dest_dir)
            if index % 40 == 0 or index == len(members):
                pct = 65 + int(index * 20 / max(len(members), 1))
                _report("extracting", pct, "正在解压更新包…", f"{index}/{len(members)}")
    app_dir = _find_friday_app_dir(dest_dir)
    if app_dir is None:
        raise RuntimeError(
            "更新包中未找到 Friday 程序文件夹（应含 Friday.exe）。"
            "请确认下载的是 Friday-Update.zip 官方更新包。"
        )
    return app_dir


def _write_updater_script() -> Path:
    script = r"""param(
    [Parameter(Mandatory = $true)][int]$ParentPid,
    [Parameter(Mandatory = $true)][string]$TargetDir,
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$CleanupDir
)

$ErrorActionPreference = "SilentlyContinue"
$deadline = (Get-Date).AddMinutes(3)
while ((Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 400
}
Start-Sleep -Seconds 1

if (-not (Test-Path -LiteralPath $SourceDir)) { exit 2 }
if (-not (Test-Path -LiteralPath $TargetDir)) { New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null }

$BackupDir = Join-Path (Split-Path -Parent $TargetDir) "Friday.bak"
$robolog = Join-Path $env:TEMP ("friday-update-" + [guid]::NewGuid().ToString("n") + ".log")
& robocopy $SourceDir $TargetDir /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NJH /NJS /NP /LOG:$robolog | Out-Null
$code = $LASTEXITCODE
if ($code -ge 8) {
    if (Test-Path -LiteralPath $BackupDir) {
        $restoreLog = Join-Path $env:TEMP ("friday-restore-" + [guid]::NewGuid().ToString("n") + ".log")
        & robocopy $BackupDir $TargetDir /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NJH /NJS /NP /LOG:$restoreLog | Out-Null
    }
    exit $code
}

Get-ChildItem -LiteralPath $TargetDir -Recurse -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $ExePath) {
    Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath)
}

if ($CleanupDir -and (Test-Path -LiteralPath $CleanupDir)) {
    Start-Sleep -Seconds 2
    Remove-Item -LiteralPath $CleanupDir -Recurse -Force -ErrorAction SilentlyContinue
}
exit 0
"""
    path = _updates_dir() / "apply-update.ps1"
    path.write_text(script, encoding="utf-8")
    return path


def _launch_updater(*, target_dir: Path, source_dir: Path, exe_path: Path, cleanup_dir: Path) -> None:
    script = _write_updater_script()
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script),
        "-ParentPid",
        str(os.getpid()),
        "-TargetDir",
        str(target_dir),
        "-SourceDir",
        str(source_dir),
        "-ExePath",
        str(exe_path),
        "-CleanupDir",
        str(cleanup_dir),
    ]
    creationflags = subprocess.CREATE_NO_WINDOW
    if sys.platform == "win32":
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    subprocess.Popen(
        args,
        creationflags=creationflags,
        close_fds=True,
    )


def _apply_worker(*, download_url: str, version: str) -> None:
    ok = False
    message = ""
    hint = ""
    try:
        install_dir = app_install_dir()
        if install_dir is None:
            raise RuntimeError("无法定位安装目录。")
        exe_path = resolve_packaged_exe_in_dir(install_dir) or Path(sys.executable).resolve()
        if not exe_path.is_file():
            raise RuntimeError("无法定位 Friday.exe，请重新解压安装包。")
        if not _validate_download_url(download_url):
            raise RuntimeError("更新下载地址无效，请从设置页重新检查更新。")

        safe_version = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in version) or "latest"
        work_dir = _updates_dir() / f"work-{safe_version}-{int(time.time())}"
        zip_path = work_dir / "Friday-Windows.zip"
        stage_dir = work_dir / "stage"

        _report("downloading", 5, "准备下载…", f"版本 {version}")
        _download_release(download_url, zip_path)

        _report("extracting", 65, "正在解压更新包…")
        new_app_dir = _extract_release(zip_path, stage_dir)
        restart_exe = resolve_packaged_exe_in_dir(new_app_dir) or exe_path

        _report("preparing", 82, "正在备份当前版本…", str(install_backup_dir(install_dir)))
        backup_install_dir(install_dir)
        mark_pending_update(version=version, install_dir=install_dir)

        _report("preparing", 88, "正在准备安装…", "即将自动重启并完成替换")
        _launch_updater(
            target_dir=install_dir,
            source_dir=new_app_dir,
            exe_path=restart_exe,
            cleanup_dir=work_dir,
        )

        _report("restarting", 100, "更新已开始，正在重启星期五…", "请勿手动关闭 PowerShell 窗口")
        ok = True
        message = "更新已开始，应用即将重启。"
        hint = ""
        request_app_quit(delay=1.2)
    except Exception as exc:
        _log.exception("一键更新失败")
        detail, hint = _format_update_error(exc)
        if isinstance(exc, RuntimeError) and str(exc).strip():
            raw = str(exc).strip()
            if "\n" in raw:
                lines = [line.strip() for line in raw.splitlines() if line.strip()]
                detail = lines[0]
                if len(lines) > 1 and lines[1] not in hint:
                    hint = lines[1]
            else:
                detail = raw[:240]
        message = detail
        pct = int(_apply_state.get("percent") or 5)
        _fail_apply(detail=detail, hint=hint, percent=pct)
        return
    finally:
        if ok:
            with _apply_lock:
                _apply_state["running"] = False
                _apply_state["ok"] = ok
                _apply_state["result_message"] = message
                _apply_state["hint"] = hint


def start_apply_update(*, download_url: str, version: str) -> dict[str, object]:
    """后台下载并触发替换脚本；成功后会自动退出当前进程。"""
    can, reason = can_auto_update()
    if not can:
        return {"started": False, "message": reason, "hint": "请使用「手动下载」获取 Friday-Update.zip 后覆盖解压。"}

    url = (download_url or "").strip()
    ver = (version or "").strip()
    if not url:
        return {
            "started": False,
            "message": "缺少更新下载地址",
            "hint": "请先点「检查更新」，确认有新版本后再试。",
        }

    with _apply_lock:
        if _apply_state.get("running"):
            return {"started": True, "already_running": True}
        _apply_state.clear()
        _apply_state.update(
            {
                "running": True,
                "phase": "starting",
                "percent": 0,
                "message": "正在启动更新…",
                "detail": "",
                "ok": None,
                "version": ver,
                "result_message": "",
                "hint": "",
                "log": [],
            }
        )

    thread = threading.Thread(
        target=_apply_worker,
        kwargs={"download_url": url, "version": ver},
        daemon=True,
        name="friday-update-apply",
    )
    thread.start()
    return {"started": True, "already_running": False}
