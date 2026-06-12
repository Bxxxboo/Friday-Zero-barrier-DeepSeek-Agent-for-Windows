"""C 盘 Windows 操作系统路径保护（内置绝对禁令，不可被 Yolo/审批绕过）。"""

from __future__ import annotations

import sys
from pathlib import Path

# C:\ 下视为操作系统区域的顶层目录（不含 Users，用户文档仍在 C:\Users\...）
_WINDOWS_C_OS_TOP_DIRS: frozenset[str] = frozenset({
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "boot",
    "recovery",
    "efi",
    "$recycle.bin",
    "system volume information",
    "$winreagent",
    "perflogs",
    "documents and settings",
})

# C:\ 根目录常见系统文件（单文件名，不含子路径）
_WINDOWS_C_OS_ROOT_FILES: frozenset[str] = frozenset({
    "bootmgr",
    "bootnxt",
    "boottel.dat",
    "hiberfil.sys",
    "pagefile.sys",
    "swapfile.sys",
    "vfcompat.dll",
    "vfcompatsc.dll",
})

OS_DELETE_BLOCK_REASON = (
    "绝对禁止删除 C 盘操作系统文件"
    "（如 C:\\Windows、C:\\Program Files、C:\\ProgramData 等），"
    "无法通过审批或 Yolo 解除。"
)

_DESTRUCTIVE_PATH_TOOLS: frozenset[str] = frozenset({
    "delete_file",
    "delete_directory",
    "move_file",
    "organize_directory",
    "batch_rename",
    "write_text_file",
})


def _resolve_path(path: str) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def is_windows_c_os_path(path: str) -> bool:
    """路径是否位于 C: 盘 Windows 操作系统保护区内。"""
    if sys.platform != "win32":
        return False
    resolved = _resolve_path(path)
    if resolved is None:
        return False
    if resolved.drive.upper() != "C:":
        return False
    try:
        rel = resolved.relative_to(Path("C:/"))
    except ValueError:
        return False
    parts = rel.parts
    if not parts:
        return True
    head = parts[0].lower()
    if head in _WINDOWS_C_OS_TOP_DIRS:
        return True
    if len(parts) == 1 and head in _WINDOWS_C_OS_ROOT_FILES:
        return True
    return False


def block_reason_for_destructive_paths(tool_name: str, paths: list[str]) -> str | None:
    """若工具参数触及受保护路径，返回拒绝原因；否则 None。"""
    if tool_name not in _DESTRUCTIVE_PATH_TOOLS:
        return None
    for raw in paths:
        text = str(raw or "").strip()
        if not text:
            continue
        if is_windows_c_os_path(text):
            return OS_DELETE_BLOCK_REASON
    return None
