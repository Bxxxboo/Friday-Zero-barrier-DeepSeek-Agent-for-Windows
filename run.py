import os
import sys

# 打包版：pywebview(WinForms) 依赖 pythonnet，优先走 .NET Framework
if sys.platform == "win32" and getattr(sys, "frozen", False):
    os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
    _meipass = getattr(sys, "_MEIPASS", "")
    if _meipass:
        _ca = os.path.join(_meipass, "certifi", "cacert.pem")
        if os.path.isfile(_ca):
            os.environ.setdefault("SSL_CERT_FILE", _ca)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
    else:
        try:
            import certifi

            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
            os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
        except Exception:
            pass

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
