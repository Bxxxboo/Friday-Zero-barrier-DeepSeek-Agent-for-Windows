"""Probe Weixin login window and file-transfer-only mode."""
import time

import uiautomation as auto
import win32gui
import win32process


def find_login_window():
    result = None

    def cb(hwnd, _):
        nonlocal result
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        if cls == "mmui::LoginWindow" or (cls == "Qt51514QWindowIcon" and title == "微信" and rect[0] > -1000):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            result = (hwnd, title, cls, rect, pid)

    win32gui.EnumWindows(cb, None)
    return result


def walk(ctrl, depth=0, limit=120):
    if depth > 8 or limit <= 0:
        return limit
    limit -= 1
    try:
        name = (ctrl.Name or "")[:50]
        print(
            "  " * depth
            + f"{ctrl.ControlTypeName} name={name!r} class={(ctrl.ClassName or '')[:25]!r}"
        )
    except Exception as exc:
        print("  " * depth + str(exc))
    try:
        for ch in ctrl.GetChildren():
            limit = walk(ch, depth + 1, limit)
    except Exception:
        pass
    return limit


info = find_login_window()
print("LOGIN", info)
if not info:
    raise SystemExit("no login window")

hwnd = info[0]
win32gui.SetForegroundWindow(hwnd)
time.sleep(0.5)
w = auto.ControlFromHandle(hwnd)
walk(w)

# click 仅传输文件
for btn in w.GetChildren():
    pass

def find_button(root, keyword):
    try:
        if root.ControlTypeName == "ButtonControl" and keyword in (root.Name or ""):
            return root
        for ch in root.GetChildren():
            hit = find_button(ch, keyword)
            if hit:
                return hit
    except Exception:
        pass
    return None

btn = find_button(w, "传输文件") or find_button(w, "文件")
print("BUTTON", btn.Name if btn else None)
if btn:
    btn.Click()
    time.sleep(2)
    print("After click, enumerate windows:")
    def cb2(hwnd, out):
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if "Weixin" in cls or "mmui" in cls or "Qt515" in cls or title:
            out.append((hwnd, title, cls, win32gui.GetWindowRect(hwnd)))
    out = []
    win32gui.EnumWindows(cb2, out)
    for item in out:
        print(item)
