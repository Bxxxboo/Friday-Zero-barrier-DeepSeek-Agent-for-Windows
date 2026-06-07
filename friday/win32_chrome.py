"""Windows 无边框桌面窗 DWM / WebView 铺满调优。"""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes

WINDOW_TITLE = "星期五"

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

# DWM
DWMWA_NCRENDERING_POLICY = 2
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMNCRP_DISABLED = 1
DWMWCP_DONOTROUND = 1
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


def find_app_window() -> int | None:
    """按标题 + 当前进程查找主窗口（含最小化/隐藏）。"""
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = kernel32.GetCurrentProcessId()
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd: int, _lparam: int) -> bool:
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if proc.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd) + 1
        if length <= 1:
            return True
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        if buf.value == WINDOW_TITLE:
            found.append(hwnd)
        return True

    user32.EnumWindows(_callback, 0)
    return found[0] if found else None


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
        _set_dwm_int(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
        _set_dwm_int(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
        _set_dwm_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND)
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


def tune_desktop_window(hwnd: int, bg_hex: str, *, dark: bool, clip_thumbnail: bool = True) -> None:
    apply_desktop_window_chrome(hwnd, bg_hex, dark=dark)
    if clip_thumbnail:
        set_taskbar_thumbnail_clip(hwnd)
