from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

from friday.edition import app_user_model_id, window_title
from friday.logging_config import setup_logging
from friday.net import find_free_port
from friday.paths import app_icon_path, get_appdata_dir, stable_icon_path
from friday.splash import blank_html, boot_splash_html, resolved_boot_theme, splash_background
from friday.storage import load_settings

_log = None  # 在 main() 中赋值
_startup_state: dict[str, int | str | None] = {"port": None, "token": None}


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except OSError:
            pass


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id())
    except (AttributeError, OSError):
        pass


def _resolve_icon_path() -> str | None:
    src = app_icon_path()
    if not src.is_file():
        return None
    try:
        dest = stable_icon_path()
        shutil.copy2(src, dest)
        return str(dest.resolve())
    except OSError:
        return str(src.resolve())


def _pick_folder_powershell(initial: str = "") -> str:
    """Windows 原生文件夹对话框（pywebview 在某些机器上打不开时的备用方案）。"""
    if sys.platform != "win32":
        return ""
    init = initial.strip()
    if init and not os.path.isdir(init):
        init = ""
    init_ps = init.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.ShowNewFolderButton = $true; "
        "$d.Description = '选择默认操作文件夹'; "
    )
    if init_ps:
        script += f"if (Test-Path -LiteralPath '{init_ps}') {{ $d.SelectedPath = '{init_ps}' }}; "
    script += (
        "$r = $d.ShowDialog(); "
        "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }"
    )
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0 and _log:
            _log.warning(
                "PowerShell 文件夹选择失败 | code=%s stderr=%s",
                proc.returncode,
                (proc.stderr or "").strip()[:200],
            )
        path = (proc.stdout or "").strip()
        return path.replace("\\", "/") if path else ""
    except Exception:
        if _log:
            _log.exception("PowerShell 文件夹选择异常")
        return ""


class WindowApi:
    def __init__(self) -> None:
        self._window = None
        self._hwnd: int | None = None
        self._chrome_bg = "#0a0d12"
        self._chrome_dark = True

    def bind(self, window) -> None:
        self._window = window

    def _resolve_hwnd(self) -> int | None:
        if self._hwnd and sys.platform == "win32":
            import ctypes

            if ctypes.windll.user32.IsWindow(self._hwnd):
                return self._hwnd
        from friday.win32_chrome import find_app_window

        self._hwnd = find_app_window()
        return self._hwnd

    def sync_window_chrome(self, bg_hex: str = "", dark: bool | None = None) -> bool:
        """同步 DWM 边框/任务栏缩略图，与界面背景一致。"""
        if sys.platform != "win32":
            return False
        if bg_hex:
            self._chrome_bg = bg_hex
        if dark is not None:
            self._chrome_dark = bool(dark)
        hwnd = self._resolve_hwnd()
        if not hwnd:
            return False
        from friday.win32_chrome import tune_desktop_window

        tune_desktop_window(hwnd, self._chrome_bg, dark=self._chrome_dark)
        return True

    def prepare_minimize(self) -> bool:
        """最小化前刷新窗口合成，避免任务栏预览黑框。"""
        if sys.platform != "win32":
            return False
        hwnd = self._resolve_hwnd()
        if not hwnd:
            return False
        from friday.win32_chrome import tune_desktop_window

        tune_desktop_window(hwnd, self._chrome_bg, dark=self._chrome_dark, clip_thumbnail=True)
        return True

    def is_maximized(self) -> bool:
        if self._window:
            return bool(self._window.maximized)
        return False

    def minimize_window(self) -> None:
        if self._window:
            self._window.minimize()

    def maximize_window(self) -> None:
        if self._window:
            self._window.maximize()

    def restore_window(self) -> None:
        if self._window:
            self._window.restore()

    def activate_window(self) -> bool:
        """点击界面时把窗口提到前台。"""
        if self._window:
            try:
                self._window.show()
            except Exception:
                pass
        if sys.platform != "win32":
            return True
        hwnd = self._resolve_hwnd()
        if not hwnd:
            return False
        from friday.win32_chrome import focus_window

        return focus_window(hwnd)

    def is_window_foreground(self) -> bool:
        if sys.platform != "win32":
            return True
        hwnd = self._resolve_hwnd()
        if not hwnd:
            return False
        from friday.win32_chrome import is_window_foreground

        return is_window_foreground(hwnd)

    def close_window(self) -> None:
        if self._window:
            self._window.destroy()

    def pick_folder(self, initial: str = "") -> str:
        directory = initial.strip() if initial and os.path.isdir(initial.strip()) else ""

        if self._window:
            try:
                import webview

                folder_dialog = webview.FOLDER_DIALOG
                file_dialog = getattr(webview, "FileDialog", None)
                if file_dialog is not None:
                    folder_dialog = file_dialog.FOLDER
                result = self._window.create_file_dialog(
                    folder_dialog,
                    directory=directory,
                    allow_multiple=False,
                )
                if result:
                    return str(result[0]).replace("\\", "/")
            except Exception:
                if _log:
                    _log.exception("pywebview 文件夹选择对话框失败，尝试备用方案")

        fallback = _pick_folder_powershell(directory or initial.strip())
        if fallback:
            if _log:
                _log.info("已通过 Windows 原生对话框选择文件夹")
            return fallback
        return ""

    def open_appdata_folder(self) -> bool:
        """在资源管理器中打开 %APPDATA%/Friday。"""
        try:
            import subprocess

            path = get_appdata_dir()
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True
        except Exception:
            if _log:
                _log.exception("打开日志文件夹失败")
            return False

    def open_external_url(self, url: str) -> bool:
        """在系统默认浏览器中打开 http(s) 链接，避免 WebView 整页跳走。"""
        cleaned = (url or "").strip()
        if not cleaned.startswith(("http://", "https://")):
            return False
        try:
            import webbrowser

            webbrowser.open(cleaned)
            return True
        except Exception:
            if _log:
                _log.exception("打开外部链接失败 | url=%s", cleaned[:120])
            return False


def _startup_failure_html(title: str, message: str) -> str:
    from friday.splash import resolved_boot_theme, splash_background

    settings = load_settings()
    bg = splash_background(settings)
    light = resolved_boot_theme(settings) == "light"
    text = "#2c3444" if light else "#d8dde8"
    muted = "#5c6578" if light else "#8b95a8"
    accent = "#b8862e" if light else "#d4a056"
    btn_bg = "#4070b8" if light else "#5b8fd9"
    btn_text = "#ffffff"
    border = "rgba(180, 150, 100, 0.22)" if light else "rgba(212, 160, 86, 0.14)"
    log_dir = str(get_appdata_dir()).replace("\\", "/")
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{safe_title}</title>"
        f"<style>"
        f"html,body{{margin:0;width:100%;height:100%;background:{bg};"
        f"font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;color:{text};"
        f"display:flex;align-items:center;justify-content:center;line-height:1.6;}}"
        f".card{{max-width:520px;padding:32px 28px;text-align:center;"
        f"border:1px solid {border};border-radius:16px;background:rgba(128,128,128,.06);}}"
        f"h3{{margin:0 0 12px;font-size:18px;font-weight:600;color:{accent};}}"
        f"p{{margin:0 0 10px;font-size:14px;color:{muted};}}"
        f"code{{font-size:12px;word-break:break-all;}}"
        f".actions{{display:flex;gap:10px;justify-content:center;margin-top:22px;flex-wrap:wrap;}}"
        f"button{{cursor:pointer;border:none;border-radius:10px;padding:10px 18px;font-size:14px;"
        f"font-family:inherit;transition:opacity .15s;}}"
        f"button:hover{{opacity:.88;}}"
        f".primary{{background:{btn_bg};color:{btn_text};}}"
        f".ghost{{background:transparent;color:{muted};border:1px solid {border};}}"
        f"</style></head><body><div class='card'>"
        f"<h3>{safe_title}</h3>"
        f"<p>{safe_message}</p>"
        f"<p>日志目录：<code>{log_dir}</code></p>"
        f"<p>请打开上述文件夹，查看 <strong>friday.log</strong> 获取详细错误。</p>"
        f"<div class='actions'>"
        f"<button class='primary' type='button' onclick='openLog()'>打开日志文件夹</button>"
        f"<button class='ghost' type='button' onclick='closeApp()'>关闭</button>"
        f"</div></div>"
        f"<script>"
        f"function closeApp(){{"
        f"if(window.pywebview&&window.pywebview.api&&window.pywebview.api.close_window)"
        f"{{window.pywebview.api.close_window();return;}}"
        f"window.close();"
        f"}}"
        f"function openLog(){{"
        f"if(window.pywebview&&window.pywebview.api&&window.pywebview.api.open_appdata_folder)"
        f"{{window.pywebview.api.open_appdata_folder();return;}}"
        f"alert('日志目录：{log_dir}');"
        f"}}"
        f"</script></body></html>"
    )


def wait_for_server(port: int, timeout: float = 45.0) -> bool:
    import json
    import time

    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.8) as resp:
                if resp.status != 200:
                    time.sleep(0.05)
                    continue
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("status") == "ok":
                    return True
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
            time.sleep(0.05)
    return False


def _prepare_backend() -> None:
    import uvicorn

    try:
        port = find_free_port()
        from friday.auth import ensure_api_token, set_api_token

        token = ensure_api_token()
        os.environ["FRIDAY_API_TOKEN"] = token
        os.environ["FRIDAY_PORT"] = str(port)
        set_api_token(token)
        _startup_state["port"] = port
        _startup_state["token"] = token

        from friday.server import app

        _log.info("启动后端服务 port=%d", port)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except Exception:
        _log.exception("后端线程异常")


def _wait_for_backend(timeout: float = 45.0) -> int | None:
    import time

    deadline = time.time() + timeout
    while _startup_state["port"] is None and time.time() < deadline:
        time.sleep(0.05)
    port = _startup_state["port"]
    if port is None:
        return None
    remaining = max(0.0, deadline - time.time())
    if wait_for_server(port, timeout=remaining):
        return int(port)
    return None


def _load_main_page(window, *, main_url: str) -> None:
    """正常 URL 导航，确保 /static 脚本在 WebView2 各版本下可加载。"""
    try:
        window.load_url(main_url)
    except Exception:
        _log.exception("加载主界面 URL 失败")


def _is_internal_app_url(url: str) -> bool:
    if not url:
        return True
    from urllib.parse import urlparse

    parsed = urlparse(url.strip())
    if parsed.scheme in ("about", "data", "file", ""):
        return True
    if parsed.scheme not in ("http", "https"):
        return False
    return parsed.hostname in ("127.0.0.1", "localhost")


def main() -> None:
    global _log
    os.environ.setdefault("FRIDAY_GUI", "1")
    setup_logging()
    from friday.logging_config import get_logger

    _log = get_logger("desktop")

    _enable_dpi_awareness()
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
    # 避免公司代理/VPN 拦截本机 WebSocket（测试机常见「一直正在连接」）
    _wv2_args = "--proxy-bypass-list=<-loopback>;127.0.0.1;localhost"
    existing_wv2 = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
    if existing_wv2:
        if _wv2_args not in existing_wv2:
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{existing_wv2} {_wv2_args}"
    else:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = _wv2_args
    _set_windows_app_id()

    settings = load_settings()
    boot_theme = resolved_boot_theme(settings)
    splash_bg = splash_background(settings)

    import webview

    threading.Thread(target=_prepare_backend, daemon=True).start()

    window_visible = {"shown": False}
    boot_phase = {"step": "splash", "main_url": ""}
    window_api = WindowApi()
    app_icon = _resolve_icon_path()
    failure_html: str | None = None

    def _apply_window_chrome(*, clip_thumbnail: bool = True) -> None:
        if sys.platform != "win32":
            return
        hwnd = window_api._resolve_hwnd()
        if not hwnd:
            return
        from friday.win32_chrome import tune_desktop_window

        window_api._chrome_bg = splash_bg
        window_api._chrome_dark = boot_theme == "dark"
        tune_desktop_window(
            hwnd,
            splash_bg,
            dark=boot_theme == "dark",
            clip_thumbnail=clip_thumbnail,
            icon_path=app_icon,
        )

    def _schedule_chrome_apply() -> None:
        for delay in (0.0, 0.05, 0.15, 0.35, 0.7, 1.2):
            threading.Timer(
                delay,
                lambda d=delay: _apply_window_chrome(clip_thumbnail=d >= 0.15),
            ).start()

    def _force_show_window() -> None:
        if window_visible["shown"]:
            return
        window_visible["shown"] = True
        try:
            window.show()
        except Exception:
            _log.exception("显示主窗口失败")
        if sys.platform == "win32":
            try:
                import ctypes

                from friday.win32_chrome import find_app_window

                hwnd = find_app_window()
                if hwnd:
                    user32 = ctypes.windll.user32
                    if not user32.IsWindowVisible(hwnd):
                        user32.ShowWindow(hwnd, 5)  # SW_SHOW
            except (AttributeError, OSError, TypeError):
                pass
        _schedule_chrome_apply()

    def _load_main_app() -> None:
        def _splash_status(text: str) -> None:
            try:
                window.evaluate_js(
                    "(function(t){var el=document.querySelector('.status');if(el)el.textContent=t;})("
                    + repr(text)
                    + ")",
                    False,
                )
            except Exception:
                pass

        _splash_status("正在启动服务…")
        port = _wait_for_backend()
        if port is None:
            _log.error("后端未能启动或未响应")
            nonlocal failure_html
            failure_html = _startup_failure_html(
                "星期五启动失败",
                "后端未响应，请检查端口是否被占用或查看 friday.log。",
            )
            boot_phase["step"] = "failure"
            try:
                window.load_html(failure_html)
            except Exception:
                _log.exception("加载失败页异常")
            return

        token = _startup_state.get("token") or ""
        try:
            from friday.weixin.config import write_bridge_config

            write_bridge_config(int(port), token)
        except OSError:
            _log.exception("同步微信桥接配置失败")
        token_q = f"&token={token}" if token else ""
        main_url = f"http://127.0.0.1:{port}/?desktop=1&boot={boot_theme}{token_q}"
        boot_phase["main_url"] = main_url
        _log.info("后端就绪 port=%d，准备加载主界面", port)
        _splash_status("正在加载界面…")
        boot_phase["step"] = "main"
        try:
            from friday.scheduler import start_scheduler

            start_scheduler()
        except Exception:
            _log.exception("定时调度器启动失败")
        _load_main_page(window, main_url=main_url)

    def _on_page_loaded() -> None:
        step = boot_phase["step"]
        if step == "splash":
            _force_show_window()
            boot_phase["step"] = "waiting"
            threading.Thread(target=_load_main_app, daemon=True).start()
            return
        if step in ("main", "failure"):
            if step == "main":
                try:
                    current = (window.get_current_url() or "").strip()
                    main_url = str(boot_phase.get("main_url") or "")
                    if current and main_url and not _is_internal_app_url(current):
                        import webbrowser

                        _log.info("WebView 外链导航已拦截，改在系统浏览器打开 | url=%s", current[:160])
                        webbrowser.open(current)
                        window.load_url(main_url)
                        return
                except Exception:
                    _log.exception("外链导航恢复失败")
            _apply_window_chrome(clip_thumbnail=False)
            if not window_visible["shown"]:
                _force_show_window()

    def _on_restored() -> None:
        _apply_window_chrome()
        def _repaint() -> None:
            try:
                window.evaluate_js(
                    "requestAnimationFrame(function(){"
                    "document.documentElement.style.willChange='transform';"
                    "requestAnimationFrame(function(){"
                    "document.documentElement.style.willChange='';});});",
                    False,
                )
            except Exception:
                pass

        threading.Timer(0.05, _repaint).start()

    def _on_minimized() -> None:
        _apply_window_chrome(clip_thumbnail=True)

    _log.info("创建启动窗口（先显示启动页，后端并行加载）")
    create_kwargs: dict = {
        "title": window_title(),
        "width": 980,
        "height": 720,
        "min_size": (820, 600),
        "background_color": splash_bg,
        "frameless": True,
        "easy_drag": False,
        "hidden": False,
        "shadow": False,
        "focus": False,
        "text_select": True,
        "zoomable": False,
        "js_api": window_api,
        "html": boot_splash_html(settings, status="正在启动服务…"),
    }

    window = webview.create_window(**create_kwargs)
    window_api.bind(window)
    from friday.update_installer import register_quit_handler

    register_quit_handler(window_api.close_window)
    window.events.loaded += _on_page_loaded
    window.events.restored += _on_restored
    window.events.minimized += _on_minimized
    window.events.resized += lambda _w, _h: _apply_window_chrome(clip_thumbnail=False)

    def _on_gui_start() -> None:
        if not window_visible["shown"]:
            threading.Timer(0.35, _force_show_window).start()
        threading.Timer(4.0, _force_show_window).start()

    webview_dir = get_appdata_dir() / "webview2"
    webview_dir.mkdir(parents=True, exist_ok=True)

    start_kwargs: dict = {
        "gui": "edgechromium",
        "func": _on_gui_start,
        "private_mode": False,
        "storage_path": str(webview_dir),
    }
    if app_icon:
        start_kwargs["icon"] = app_icon

    try:
        webview.start(**start_kwargs)
    except Exception as exc:
        _log.exception("WebView2 窗口启动失败")
        if sys.platform == "win32":
            from friday.win10_runtime import check_webview2, install_webview2, notify_runtime_failure

            wv2 = check_webview2()
            msgs = [f"界面启动失败：{exc}"]
            if not wv2.ok:
                ok, msg = install_webview2()
                msgs.append(f"WebView2：{msg}")
                if ok and check_webview2().ok:
                    try:
                        webview.start(**start_kwargs)
                        return
                    except Exception:
                        _log.exception("WebView2 安装后仍无法启动")
            notify_runtime_failure(msgs)
        raise


if __name__ == "__main__":
    main()
