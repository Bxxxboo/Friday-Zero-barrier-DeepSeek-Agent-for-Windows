import os
import sys

# 打包版：pywebview(WinForms) 依赖 pythonnet，优先走 .NET Framework
if sys.platform == "win32" and getattr(sys, "frozen", False):
    os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
    _meipass = getattr(sys, "_MEIPASS", "")
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if _meipass:
        for _sub in (
            os.path.join(_meipass, "pythonnet", "runtime"),
            os.path.join(_meipass, "clr_loader", "ffi", "dlls", "amd64"),
            _meipass,
            _exe_dir,
        ):
            if os.path.isdir(_sub) and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(_sub)
                except OSError:
                    pass
        for _name in ("python312.dll", "python311.dll", "python3.dll"):
            _candidate = os.path.join(_meipass, _name)
            if os.path.isfile(_candidate):
                os.environ.setdefault("PYTHONNET_PYDLL", _candidate)
                break
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
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        from friday.win10_runtime import ensure_win10_runtime, notify_runtime_failure

        runtime_ok, runtime_msgs = ensure_win10_runtime(auto_install=True)
        if not runtime_ok:
            notify_runtime_failure(runtime_msgs)
            raise SystemExit(1)
    from friday.desktop import main

    main()
