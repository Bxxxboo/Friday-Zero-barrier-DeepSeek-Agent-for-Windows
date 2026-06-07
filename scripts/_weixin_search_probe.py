"""Probe Weixin sidebar search via UIAutomation (not 搜一搜)."""
import time

import psutil
import uiautomation as auto
import win32con
import win32gui
import win32process


def weixin_pid() -> int | None:
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["name"] == "Weixin.exe":
            return p.info["pid"]
    return None


def restore_main(pid: int) -> int | None:
    best = None

    def cb(hwnd, _):
        nonlocal best
        _, p = win32process.GetWindowThreadProcessId(hwnd)
        if p != pid:
            return
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if cls != "Qt51514QWindowIcon" or title not in ("微信", "Weixin"):
            return
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        area = max(0, r - l) * max(0, b - t)
        if area > 200_000:
            best = hwnd
        elif area == 0 and best is None:
            best = hwnd

    win32gui.EnumWindows(cb, None)
    if best and win32gui.GetWindowRect(best)[0] <= -1000:
        win32gui.ShowWindow(best, win32con.SW_RESTORE)
        time.sleep(1)
    return best


pid = weixin_pid()
print("pid", pid)
hwnd = restore_main(pid)
print("hwnd", hwnd, win32gui.GetWindowRect(hwnd) if hwnd else None)

root = auto.WindowControl(ProcessId=pid, searchDepth=1)
print("root", root.Name, root.ClassName, root.Exists())

# close 搜一搜 popups
for w in auto.GetRootControl().GetChildren():
    if w.ProcessId == pid and "ToolSaveBits" in (w.ClassName or ""):
        print("popup", w.Name, w.ClassName, w.BoundingRectangle)

found = []

def walk(c, depth=0):
    if depth > 12:
        return
    try:
        name = c.Name or ""
        aid = c.AutomationId or ""
        cls = c.ClassName or ""
        if "搜索" in name or "search" in aid.lower() or aid == "search_list":
            found.append((depth, c.ControlTypeName, name, aid, cls))
            print("HIT", depth, c.ControlTypeName, repr(name), repr(aid), repr(cls))
    except Exception:
        pass
    try:
        for ch in c.GetChildren():
            walk(ch, depth + 1)
    except Exception:
        pass

walk(root)
print("found count", len(found))

for ctrl_type, prop in [
    ("EditControl", {"Name": "搜索"}),
    ("ListControl", {"AutomationId": "search_list"}),
    ("ListControl", {"Name": "会话"}),
]:
    cls = getattr(auto, ctrl_type)
    c = cls(searchFromControl=root, searchDepth=20, **prop)
    print(ctrl_type, prop, "exists", c.Exists(1, 0.2), "rect", c.BoundingRectangle if c.Exists(0,0) else None)
