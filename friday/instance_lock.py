"""单实例锁 —— 端口占用 + 激活已有窗口（runtime hook 与主进程共用）。"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

from friday.edition import instance_port, window_title

INSTANCE_HOST = "127.0.0.1"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _instance_port() -> int:
    return instance_port()


def _window_title() -> str:
    return window_title()


def _hidden_subprocess_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": _CREATE_NO_WINDOW, "startupinfo": startup}


def find_main_window() -> int | None:
    """查找主窗口（任意进程；含隐藏/无标题）。"""
    if sys.platform != "win32":
        return None

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titled: list[int] = []
    expected_title = _window_title()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd: int, _lparam: int) -> bool:
        if user32.GetParent(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd) + 1
        if length <= 1:
            return True
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        if buf.value == expected_title:
            titled.append(hwnd)
        return True

    user32.EnumWindows(_callback, 0)
    if titled:
        return titled[0]

    pid = _pid_listening_on(_instance_port())
    if pid is None:
        return None

    from friday.win32_chrome import find_window_for_pid

    return find_window_for_pid(pid)


def focus_existing_window() -> bool:
    """激活已有窗口。找到并激活返回 True，否则 False。"""
    hwnd = find_main_window()
    if hwnd is None:
        return False

    if sys.platform != "win32":
        return True

    import ctypes

    user32 = ctypes.windll.user32
    if not user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

    from friday.win32_chrome import focus_window

    return focus_window(hwnd)


def _pid_listening_on(port: int) -> int | None:
    """返回占用指定端口的进程 PID（Windows netstat）。"""
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            **_hidden_subprocess_kwargs(),
        )
    except (subprocess.SubprocessError, OSError):
        return None
    needle = f"{INSTANCE_HOST}:{port}"
    for line in out.splitlines():
        if needle not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if parts:
            try:
                return int(parts[-1])
            except ValueError:
                continue
    return None


def clear_stale_instance_lock() -> bool:
    """锁被占用但无可见窗口时，结束僵死进程以释放端口。"""
    if find_main_window() is not None:
        return False
    pid = _pid_listening_on(_instance_port())
    if pid is None or pid <= 0:
        return False
    if sys.platform != "win32":
        return False

    import ctypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_TERMINATE = 0x0001
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        if not kernel32.TerminateProcess(handle, 1):
            return False
    finally:
        kernel32.CloseHandle(handle)
    time.sleep(0.35)
    return True


def try_acquire_instance_lock() -> socket.socket | None:
    """占用单实例端口；返回 socket 或 None（已有实例）。"""
    port = _instance_port()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except OSError:
            pass
    try:
        sock.bind((INSTANCE_HOST, port))
        sock.listen(1)
    except OSError:
        sock.close()
        return None
    return sock


def acquire_instance_lock_or_recover() -> socket.socket | None:
    """获取单实例锁；若僵死则自动清理后重试。"""
    sock = try_acquire_instance_lock()
    if sock is not None:
        return sock
    if focus_existing_window():
        return None
    if clear_stale_instance_lock():
        return try_acquire_instance_lock()
    return None
