"""Send a file to Weixin File Transfer Assistant via sidebar search (NOT 搜一搜)."""
from __future__ import annotations

import ctypes
import struct
import sys
import time
from pathlib import Path

import psutil
import pyautogui
import pyperclip
import win32clipboard
import win32con
import win32gui
import win32process

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.12

CONTACT = "文件传输助手"


def _weixin_pids() -> list[int]:
    return [
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name"])
        if p.info["name"] == "Weixin.exe"
    ]


def _main_hwnd(pid: int) -> int | None:
    candidates: list[tuple[int, int]] = []

    def cb(hwnd, _):
        _, p = win32process.GetWindowThreadProcessId(hwnd)
        if p != pid:
            return
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if cls != "Qt51514QWindowIcon" or title not in ("微信", "Weixin"):
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        area = max(0, right - left) * max(0, bottom - top)
        candidates.append((hwnd, area))

    win32gui.EnumWindows(cb, None)
    if not candidates:
        return None

    candidates.sort(key=lambda item: item[1], reverse=True)
    if candidates[0][1] >= 400_000:
        return candidates[0][0]

    # 主窗口可能被最小化，先恢复再取最大窗口
    for hwnd, _ in candidates:
        if win32gui.GetWindowRect(hwnd)[0] <= -1000:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(0.8)

    best: tuple[int, int] | None = None

    def cb2(hwnd, _):
        nonlocal best
        _, p = win32process.GetWindowThreadProcessId(hwnd)
        if p != pid:
            return
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if cls != "Qt51514QWindowIcon" or title not in ("微信", "Weixin"):
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        area = max(0, right - left) * max(0, bottom - top)
        if area > (best[1] if best else 0):
            best = (hwnd, area)

    win32gui.EnumWindows(cb2, None)
    return best[0] if best else candidates[0][0]


def _close_souyisou(pid: int) -> None:
    """关闭「搜一搜」等弹层。"""
    for _ in range(3):
        pyautogui.press("escape")
        time.sleep(0.25)
    for ctrl in __import__("uiautomation").GetRootControl().GetChildren():
        if ctrl.ProcessId != pid:
            continue
        cls = ctrl.ClassName or ""
        if "ToolSaveBits" in cls:
            try:
                ctrl.SendKeys("{Esc}")
            except Exception:
                pass


def _focus_hwnd(hwnd: int) -> tuple[int, int, int, int]:
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.8)
    user32 = ctypes.windll.user32
    user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
    user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.4)
    rect = win32gui.GetWindowRect(hwnd)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    pyautogui.click(cx, cy)
    time.sleep(0.3)
    return rect


def _sidebar_search_point(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    """左侧会话栏顶部「搜索」输入框（不是搜一搜）。"""
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    # 图标栏 ~56px，会话列表搜索框约在列表区域顶部
    x = left + 56 + int(min(width * 0.12, 160))
    y = top + int(height * 0.055)
    return x, y


def _sidebar_result_point(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    x = left + 56 + int(min(width * 0.12, 160))
    y = top + int(height * 0.13)
    return x, y


def _open_contact(rect: tuple[int, int, int, int], contact: str) -> None:
    sx, sy = _sidebar_search_point(rect)
    pyautogui.click(sx, sy)
    time.sleep(0.5)
    pyperclip.copy(contact)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.9)
    # 点击「联系人」下的第一条结果，比 Enter 更稳
    rx, ry = _sidebar_result_point(rect)
    pyautogui.click(rx, ry)
    time.sleep(0.8)


def _copy_file_to_clipboard(path: str) -> None:
    files = (path,)
    file_list = "\0".join(files) + "\0\0"
    drop_files = struct.pack("IiiII", 20, 0, 0, 0, 1) + file_list.encode("utf-16le")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, drop_files)
    finally:
        win32clipboard.CloseClipboard()


def send_file(file_path: str, contact: str = CONTACT) -> None:
    path = str(Path(file_path).resolve())
    if not Path(path).is_file():
        raise FileNotFoundError(path)

    hwnd = None
    pid = None
    for candidate in _weixin_pids():
        hwnd = _main_hwnd(candidate)
        if hwnd:
            pid = candidate
            break
    if not hwnd or pid is None:
        raise RuntimeError("未找到微信主窗口，请先登录并打开微信")

    print(f"微信 pid={pid} hwnd={hwnd}")
    _close_souyisou(pid)
    rect = _focus_hwnd(hwnd)
    _close_souyisou(pid)
    _open_contact(rect, contact)

    _copy_file_to_clipboard(path)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.7)
    pyautogui.press("enter")
    print(f"已发送: {path} -> {contact}")


if __name__ == "__main__":
    src = (
        sys.argv[1]
        if len(sys.argv) > 1
        else str(Path(__file__).resolve().parents[1] / "extensions" / "vision-bridge" / "vision-bridge-skill.txt")
    )
    temp = Path(__import__("os").environ["TEMP"]) / "vision-bridge-skill.txt"
    temp.write_bytes(Path(src).read_bytes())
    send_file(str(temp))
