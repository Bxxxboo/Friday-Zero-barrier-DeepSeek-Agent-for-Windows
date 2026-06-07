# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— 生成 dist/Friday/星期五.exe"""

from pathlib import Path

import certifi
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH)

import pythonnet

_pn_runtime = Path(pythonnet.__file__).resolve().parent / "runtime"
_pn_runtime_files = [
    (str(path), "pythonnet/runtime")
    for path in sorted(_pn_runtime.iterdir())
    if path.is_file()
]

_clr_loader_binaries = collect_dynamic_libs("clr_loader")
_pythonnet_datas = collect_data_files("pythonnet")

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=_clr_loader_binaries,
    datas=[
        (str(ROOT / "web"), "web"),
        (str(ROOT / "assets"), "assets"),
        (str(ROOT / "extensions"), "extensions"),
        (str(ROOT / "requirements-python.txt"), "."),
        (str(Path(certifi.where())), "certifi"),
    ]
    + _pythonnet_datas
    + _pn_runtime_files,
    hiddenimports=[
        "friday",
        "friday.agent",
        "friday.auth",
        "friday.brain",
        "friday.config",
        "friday.desktop",
        "friday.win32_chrome",
        "friday.instance_lock",
        "friday.interaction_modes",
        "friday.logging_config",
        "friday.operations",
        "friday.paste_images",
        "friday.plugins",
        "friday.rules",
        "friday.scheduler",
        "friday.schedules",
        "friday.single_instance",
        "friday.skills",
        "friday.splash",
        "friday.task_runner",
        "friday.updates",
        "friday.changelog",
        "friday.vision",
        "friday.net",
        "friday.paths",
        "friday.safety",
        "friday.server",
        "friday.sessions",
        "friday.storage",
        "friday.tools",
        "friday.tools._decorators",
        "friday.tools.documents",
        "friday.tools.extensions",
        "friday.tools.filesystem",
        "friday.tools.media",
        "friday.tools.registry",
        "friday.tools.shell",
        "friday.tools.python_runner",
        "friday.python_env",
        "friday.tools.system",
        "friday.tools.web",
        "friday.tools.web_limits",
        "friday.tools.web_security",
        "friday.tools.web_trust",
        "friday.tools.vision",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "fastapi",
        "starlette.routing",
        "starlette.responses",
        "starlette.websockets",
        "starlette.staticfiles",
        "websockets",
        "websockets.legacy",
        "websockets.legacy.server",
        "webview",
        "clr_loader",
        "pythonnet",
        "clr",
        "tiktoken",
        "multipart",
        "anyio",
        "anyio._backends._asyncio",
        "httptools",
        "fitz",
        "openpyxl",
        "docx",
        "pptx",
        "PIL",
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat.primitives.kdf.pbkdf2",
        "openai",
        "httpx",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(ROOT / "scripts" / "pyi_rth_single_instance.py"),
        str(ROOT / "scripts" / "pyi_rth_pythonnet.py"),
    ],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

icon_file = ROOT / "assets" / "friday.ico"
version_file = ROOT / "scripts" / "version_info.py"

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="星期五",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
    version=str(version_file) if version_file.exists() else None,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Friday",
)
