from __future__ import annotations

import os
import secrets
import shutil
import sys
import threading
import urllib.error
import urllib.request

from friday.logging_config import setup_logging
from friday.net import find_free_port
from friday.paths import app_icon_path, get_appdata_dir, stable_icon_path
from friday.splash import blank_html, resolved_boot_theme, splash_background
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

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Friday.AIDesktop.2")
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

    def close_window(self) -> None:
        if self._window:
            self._window.destroy()

    def pick_folder(self, initial: str = "") -> str:
        if not self._window:
            return ""
        try:
            import webview

            directory = initial if initial and os.path.isdir(initial) else ""
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                directory=directory,
                allow_multiple=False,
            )
            if result:
                return str(result[0]).replace("\\", "/")
            return ""
        except Exception:
            if _log:
                _log.exception("打开文件夹选择对话框失败")
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


def _startup_failure_html(title: str, message: str) -> str:
    log_dir = str(get_appdata_dir()).replace("\\", "/")
    return (
        f"<body style='font-family:sans-serif;padding:24px;line-height:1.6'>"
        f"<h3>{title}</h3><p>{message}</p>"
        f"<p>日志目录：<code>{log_dir}</code></p>"
        f"<p>请打开上述文件夹，查看 <strong>friday.log</strong> 获取详细错误。</p>"
        f"</body>"
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
        token = secrets.token_hex(32)
        os.environ["FRIDAY_API_TOKEN"] = token
        os.environ["FRIDAY_PORT"] = str(port)
        from friday.auth import set_api_token

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


def _prefetch_url(url: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=5.0) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        pass


def main() -> None:
    global _log
    os.environ.setdefault("FRIDAY_GUI", "1")
    setup_logging()
    from friday.logging_config import get_logger

    _log = get_logger("desktop")

    _enable_dpi_awareness()
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
    _set_windows_app_id()

    settings = load_settings()
    boot_theme = resolved_boot_theme(settings)
    splash_bg = splash_background(settings)

    import webview

    threading.Thread(target=_prepare_backend, daemon=True).start()
    port = _wait_for_backend()
    main_url: str | None = None
    failure_html: str | None = None
    if port is not None:
        main_url = f"http://127.0.0.1:{port}/?desktop=1&boot={boot_theme}"
        _log.info("后端就绪 port=%d，准备加载主界面", port)
        _prefetch_url(main_url)
    else:
        _log.error("后端未能启动或未响应")
        failure_html = _startup_failure_html(
            "星期五启动失败",
            "后端未响应，请检查端口是否被占用或查看 friday.log。",
        )

    window_visible = {"shown": False}
    window_api = WindowApi()

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
        )

    def _schedule_chrome_apply() -> None:
        for delay in (0.0, 0.05, 0.15, 0.35, 0.7, 1.2):
            threading.Timer(
                delay,
                lambda d=delay: _apply_window_chrome(clip_thumbnail=d >= 0.15),
            ).start()

    def _show_when_painted(*, force: bool = False) -> None:
        if window_visible["shown"]:
            return

        def _attempt(try_no: int = 0) -> None:
            if window_visible["shown"]:
                return
            ready = force
            if not ready and try_no < 12:
                try:
                    ready = bool(
                        window.evaluate_js(
                            "(function(){"
                            "if(document.readyState!=='complete')return false;"
                            "var bg=getComputedStyle(document.documentElement).backgroundColor;"
                            "if(!bg||bg==='rgba(0, 0, 0, 0)')return false;"
                            "return !!document.getElementById('appBootOverlay')||!!document.body;"
                            "})()",
                            True,
                        )
                    )
                except Exception:
                    ready = try_no >= 4
            if ready or try_no >= 12:
                window_visible["shown"] = True
                try:
                    window.show()
                    _schedule_chrome_apply()
                except Exception:
                    _log.exception("显示主窗口失败")
            else:
                threading.Timer(0.04, lambda: _attempt(try_no + 1)).start()

        _attempt()

    def _on_page_loaded() -> None:
        _show_when_painted(force=failure_html is not None)

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

    _log.info("创建启动窗口（隐藏至首帧绘制完成）")
    create_kwargs: dict = {
        "title": "星期五",
        "width": 980,
        "height": 720,
        "min_size": (820, 600),
        "background_color": splash_bg,
        "frameless": True,
        "easy_drag": False,
        "hidden": True,
        "shadow": False,
        "focus": False,
        "text_select": True,
        "zoomable": False,
        "js_api": window_api,
    }
    if main_url:
        create_kwargs["url"] = main_url
    else:
        create_kwargs["html"] = failure_html or blank_html(settings)

    window = webview.create_window(**create_kwargs)
    window_api.bind(window)
    window.events.loaded += _on_page_loaded
    window.events.restored += _on_restored
    window.events.minimized += _on_minimized
    window.events.resized += lambda _w, _h: _apply_window_chrome(clip_thumbnail=False)

    icon_holder: dict[str, str | None] = {"path": None}

    def _load_icon() -> None:
        icon_holder["path"] = _resolve_icon_path()

    def _on_gui_start() -> None:
        threading.Thread(target=_load_icon, daemon=True).start()
        if port is not None:
            try:
                from friday.scheduler import start_scheduler

                start_scheduler()
            except Exception:
                _log.exception("定时调度器启动失败")

    webview_dir = get_appdata_dir() / "webview2"
    webview_dir.mkdir(parents=True, exist_ok=True)

    start_kwargs: dict = {
        "gui": "edgechromium",
        "func": _on_gui_start,
        "private_mode": False,
        "storage_path": str(webview_dir),
    }
    if icon_holder["path"]:
        start_kwargs["icon"] = icon_holder["path"]
    elif (path := _resolve_icon_path()):
        start_kwargs["icon"] = path

    webview.start(**start_kwargs)


if __name__ == "__main__":
    main()
