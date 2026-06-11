"""Windows 无边框桌面窗 DWM / WebView 铺满调优。"""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes

from friday.edition import window_title

# Win32
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_DLGFRAME = 0x00400000
WS_BORDER = 0x00800000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
GWLP_WNDPROC = -4
WM_MOUSEACTIVATE = 0x0021
MA_ACTIVATE = 1
GA_ROOT = 2
ASFW_ANY = 0xFFFFFFFF
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_SHOWWINDOW = 0x0040

# DWM
DWMWA_NCRENDERING_POLICY = 2
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMNCRP_DISABLED = 1
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3
DWMWA_COLOR_NONE = 0xFFFFFFFE
DWMSBT_NONE = 1


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def _hex_to_colorref(hex_color: str) -> int:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return 0x000000
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return r | (g << 8) | (b << 16)


def _set_dwm_int(hwnd: int, attr: int, value: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    packed = ctypes.c_int(value)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        attr,
        ctypes.byref(packed),
        ctypes.sizeof(packed),
    )


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _guid_from_str(value: str) -> _GUID:
    u = uuid.UUID(value)
    data4 = (wintypes.BYTE * 8)(*u.bytes[8:])
    return _GUID(u.time_low, u.time_hi_version & 0xFFFF, u.time_mid, data4)


def find_window_for_pid(pid: int) -> int | None:
    """按进程 ID 查找最大顶层窗口（含隐藏/无标题）。"""
    if sys.platform != "win32" or pid <= 0:
        return None

    user32 = ctypes.windll.user32
    titled: list[int] = []
    fallback: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd: int, _lparam: int) -> bool:
        if user32.GetParent(hwnd):
            return True
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if proc.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd) + 1
        title = ""
        if length > 1:
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            title = buf.value
        if title == window_title():
            titled.append(hwnd)
            return True
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            if area >= 10_000:
                fallback.append((area, hwnd))
        return True

    user32.EnumWindows(_callback, 0)
    if titled:
        return titled[0]
    if fallback:
        fallback.sort(reverse=True)
        return fallback[0][1]
    return None


def find_app_window() -> int | None:
    """按标题 + 当前进程查找主窗口（含最小化/隐藏）。"""
    if sys.platform != "win32":
        return None

    return find_window_for_pid(ctypes.windll.kernel32.GetCurrentProcessId())


_subclass_procs: dict[int, tuple[int, object]] = {}
if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    if hasattr(_user32, "GetWindowLongPtrW"):
        _GetWindowLongPtr = _user32.GetWindowLongPtrW
        _SetWindowLongPtr = _user32.SetWindowLongPtrW
    else:
        _GetWindowLongPtr = _user32.GetWindowLongW
        _SetWindowLongPtr = _user32.SetWindowLongW
    _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLongPtr.restype = ctypes.c_void_p
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _SetWindowLongPtr.restype = ctypes.c_void_p
    _CallWindowProcW = _user32.CallWindowProcW
    _LRESULT = ctypes.c_ssize_t
    _WNDPROC = ctypes.WINFUNCTYPE(
        _LRESULT,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    _CallWindowProcW.argtypes = [
        ctypes.c_void_p,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    _CallWindowProcW.restype = _LRESULT
else:
    _GetWindowLongPtr = _SetWindowLongPtr = _CallWindowProcW = None
    _WNDPROC = None


def _window_root(hwnd: int) -> int:
    if sys.platform != "win32" or not hwnd:
        return hwnd
    root = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
    return int(root or hwnd)


def is_window_foreground(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    user32 = ctypes.windll.user32
    root = _window_root(hwnd)
    return user32.GetForegroundWindow() == root


def _subclass_hwnd_for_click_activate(hwnd: int, root_hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd or not _WNDPROC:
        return
    if hwnd in _subclass_procs:
        return
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return
    old_proc = _GetWindowLongPtr(hwnd, GWLP_WNDPROC)
    if not old_proc:
        return

    @_WNDPROC
    def proc(h: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_MOUSEACTIVATE:
            target_root = _window_root(h)
            if user32.GetForegroundWindow() != target_root:
                focus_window(target_root or root_hwnd)
            return MA_ACTIVATE
        return _CallWindowProcW(old_proc, h, msg, wparam, lparam)

    _subclass_procs[hwnd] = (old_proc, proc)
    _SetWindowLongPtr(hwnd, GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p))


def install_click_to_focus(root_hwnd: int) -> None:
    """WebView2 子窗口常返回 MA_NOACTIVATE，点击被遮挡露出的区域无法置顶。"""
    if sys.platform != "win32" or not root_hwnd:
        return
    try:
        _subclass_hwnd_for_click_activate(root_hwnd, root_hwnd)

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum_child(child: int, _lparam: int) -> bool:
            _subclass_hwnd_for_click_activate(child, root_hwnd)
            return True

        ctypes.windll.user32.EnumChildWindows(root_hwnd, _enum_child, 0)
    except (OSError, TypeError, ValueError, ctypes.ArgumentError):
        pass


def focus_window(hwnd: int) -> bool:
    """把指定 HWND 提到前台（无边框 WebView 点击时常需显式调用）。"""
    if sys.platform != "win32" or not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    root = _window_root(hwnd)
    target = root or hwnd
    if user32.GetForegroundWindow() == target:
        return True

    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except (AttributeError, OSError):
        pass

    if user32.IsIconic(target):
        user32.ShowWindow(target, 9)
    else:
        user32.ShowWindow(target, 5)

    foreground = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(target, None)
    current_thread = kernel32.GetCurrentThreadId()
    attached: list[tuple[int, int]] = []
    try:
        for thread in (fg_thread, target_thread):
            if thread and thread != current_thread:
                if user32.AttachThreadInput(thread, current_thread, True):
                    attached.append((thread, current_thread))
        user32.BringWindowToTop(target)
        user32.SetForegroundWindow(target)
        if user32.GetForegroundWindow() != target:
            user32.SetWindowPos(
                target,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.SetWindowPos(
                target,
                HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.SetForegroundWindow(target)
        if user32.GetForegroundWindow() != target:
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.SetForegroundWindow(target)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    finally:
        for thread, curr in reversed(attached):
            user32.AttachThreadInput(thread, curr, False)
    return user32.GetForegroundWindow() == target


def clear_dwm_extended_frame(hwnd: int) -> None:
    """关闭 pywebview/DWM 扩展进客户区的玻璃黑框。"""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        margins = _MARGINS(0, 0, 0, 0)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    except (AttributeError, OSError):
        pass


def enforce_frameless_window(hwnd: int) -> None:
    """若仍残留系统标题栏，强制去掉（避免双层标题栏 + 黑边）。"""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if not (style & (WS_CAPTION | WS_THICKFRAME | WS_DLGFRAME | WS_BORDER)):
            return
        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_DLGFRAME | WS_BORDER)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
    except (AttributeError, OSError):
        pass


def resize_webview_to_client(hwnd: int) -> None:
    """WebView2 子控件铺满客户区，避免四周露出默认黑底。"""
    if sys.platform != "win32" or not hwnd:
        return
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return
    width = max(0, rect.right - rect.left)
    height = max(0, rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        return

    flags = SWP_NOZORDER | SWP_NOACTIVATE

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _resize_child(child: int, _lparam: int) -> bool:
        user32.SetWindowPos(child, 0, 0, 0, width, height, flags)
        return True

    user32.EnumChildWindows(hwnd, _resize_child, 0)


def apply_desktop_window_chrome(hwnd: int, bg_hex: str, *, dark: bool) -> None:
    """隐藏 Win11 系统边框/背景，避免无边框窗出现半透明黑框。"""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        clear_dwm_extended_frame(hwnd)
        enforce_frameless_window(hwnd)
        _set_dwm_int(hwnd, DWMWA_BORDER_COLOR, _hex_to_colorref(bg_hex))
        _set_dwm_int(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
        _set_dwm_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
        _set_dwm_int(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED)
        _set_dwm_int(hwnd, DWMWA_CAPTION_COLOR, _hex_to_colorref(bg_hex))
        _set_dwm_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)
        resize_webview_to_client(hwnd)
    except (AttributeError, OSError):
        pass


def set_taskbar_thumbnail_clip(hwnd: int) -> None:
    """任务栏预览只截取客户区，去掉周围黑边。"""
    if sys.platform != "win32" or not hwnd:
        return

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return

    clip = wintypes.RECT(0, 0, rect.right, rect.bottom)

    try:
        clsid = _guid_from_str("56FDF344-FD6D-11d0-958A-006097C9A090")
        iid = _guid_from_str("EA1AFB91-9E28-4B86-90E9-9E9F8E5EEFAF")
        ptr = ctypes.c_void_p()
        hr = ctypes.OleDLL("ole32").CoCreateInstance(
            ctypes.byref(clsid),
            None,
            1,
            ctypes.byref(iid),
            ctypes.byref(ptr),
        )
        if hr != 0 or not ptr.value:
            return

        vtable_ptr = ctypes.cast(
            ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )

        hr_init = ctypes.WINFUNCTYPE(wintypes.HRESULT, ctypes.c_void_p)(vtable_ptr[3])
        if hr_init(ptr) != 0:
            return

        set_clip = ctypes.WINFUNCTYPE(
            wintypes.HRESULT,
            ctypes.c_void_p,
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        )(vtable_ptr[15])
        set_clip(ptr, hwnd, ctypes.byref(clip))
    except (AttributeError, OSError, TypeError):
        pass


def set_window_icons(hwnd: int, icon_path: str | None) -> None:
    """任务栏/Alt+Tab 图标。pythonw 开发启动时 pywebview 的 icon 参数常无效。"""
    if sys.platform != "win32" or not hwnd or not icon_path:
        return
    from pathlib import Path

    path = Path(icon_path)
    if not path.is_file():
        return
    try:
        user32 = ctypes.windll.user32
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        IMAGE_ICON = 1
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        path_w = str(path.resolve())

        hicon_sm = user32.LoadImageW(None, path_w, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        hicon_big = user32.LoadImageW(None, path_w, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = user32.LoadImageW(
                None, path_w, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
        if hicon_sm:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
    except (AttributeError, OSError):
        pass


def tune_desktop_window(
    hwnd: int,
    bg_hex: str,
    *,
    dark: bool,
    clip_thumbnail: bool = True,
    icon_path: str | None = None,
) -> None:
    apply_desktop_window_chrome(hwnd, bg_hex, dark=dark)
    set_window_icons(hwnd, icon_path)
    install_click_to_focus(hwnd)
    if clip_thumbnail:
        set_taskbar_thumbnail_clip(hwnd)
