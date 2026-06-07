import sys

# 尽早隐藏 python.exe 附带的 CMD，避免启动/重启时黑框一闪
if sys.platform == "win32" and not getattr(sys, "frozen", False):
    try:
        import ctypes

        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)
    except (AttributeError, OSError):
        pass

from friday.single_instance import ensure_single_instance

if __name__ == "__main__":
    ensure_single_instance()
    from friday.desktop import main

    main()
