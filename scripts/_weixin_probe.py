import ctypes
import time
import win32con
import win32gui
import win32process

import uiautomation as auto

SW_RESTORE = 9


def enum_weixin():
    out = []

    def cb(hwnd, _):
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if cls in ("Qt51514QWindowIcon", "mmui::LoginWindow") or title in ("微信",):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            out.append((hwnd, title, cls, pid, win32gui.GetWindowRect(hwnd)))

    win32gui.EnumWindows(cb, None)
    return out


def walk(ctrl, depth=0, limit=80):
    if depth > 6:
        return
    limit -= 1
    if limit < 0:
        return
    try:
        print(
            "  " * depth
            + f"{ctrl.ControlTypeName} name={(ctrl.Name or '')[:40]!r} class={(ctrl.ClassName or '')[:30]!r}"
        )
    except Exception as exc:
        print("  " * depth + f"ERR {exc}")
    try:
        for ch in ctrl.GetChildren():
            limit = walk(ch, depth + 1, limit)
    except Exception:
        pass
    return limit


for item in enum_weixin():
    print("WIN", item)

for hwnd, title, cls, pid, rect in enum_weixin():
    if rect[0] <= -1000 and title == "微信":
        print("\n=== RESTORE", hwnd, "===")
        win32gui.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(1.5)
        w = auto.ControlFromHandle(hwnd)
        print("Restored:", w.Name, w.ClassName, w.BoundingRectangle)
        walk(w)
