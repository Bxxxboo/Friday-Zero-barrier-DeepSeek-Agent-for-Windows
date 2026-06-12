from __future__ import annotations

import fnmatch
import hashlib
import shutil
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from friday.os_path_guard import block_reason_for_destructive_paths
from friday.tools._decorators import register_tool


def _reject_windows_c_os(tool_name: str, *paths: str) -> str | None:
    reason = block_reason_for_destructive_paths(tool_name, [str(p) for p in paths if p])
    if reason:
        return f"⛔ {reason}"
    return None

_SKIP_SEARCH_DIRS = frozenset({
    "$Recycle.Bin",
    "System Volume Information",
    "$WinREAgent",
    "Recovery",
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
})


def _resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


@register_tool(
    name="list_directory",
    description="列出目录内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径"},
            "max_items": {"type": "integer", "description": "最多返回条目数"},
        },
        "required": ["path"],
    },
)
def list_directory(path: str, max_items: int = 50) -> str:
    target = _resolve(path)
    if not target.exists():
        return f"路径不存在: {target}"
    if not target.is_dir():
        return f"不是目录: {target}"

    items = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        kind = "DIR" if item.is_dir() else "FILE"
        size = item.stat().st_size if item.is_file() else 0
        items.append(f"[{kind}] {item.name} ({size} bytes)")
        if len(items) >= max_items:
            items.append(f"... 仅显示前 {max_items} 项")
            break
    return "\n".join(items) or "(空目录)"


@register_tool(
    name="search_files",
    description="在目录中搜索文件",
    parameters={
        "type": "object",
        "properties": {
            "root": {"type": "string"},
            "pattern": {"type": "string", "description": "glob 模式，如 *.pdf"},
            "max_results": {"type": "integer"},
            "max_depth": {"type": "integer", "description": "最大搜索深度，默认 8"},
        },
        "required": ["root"],
    },
)
def search_files(
    root: str,
    pattern: str = "*",
    max_results: int = 30,
    max_depth: int = 8,
) -> str:
    base = _resolve(root)
    if not base.exists():
        return f"路径不存在: {base}"
    matches: list[str] = []
    queue: deque[tuple[Path, int]] = deque([(base, 0)])

    while queue and len(matches) < max_results:
        current, depth = queue.popleft()
        if depth > max_depth:
            continue
        try:
            entries = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for item in entries:
            if item.is_dir():
                if item.name in _SKIP_SEARCH_DIRS:
                    continue
                queue.append((item, depth + 1))
            elif fnmatch.fnmatch(item.name, pattern):
                matches.append(str(item))
                if len(matches) >= max_results:
                    break
    return "\n".join(matches) or "未找到匹配文件"


@register_tool(
    name="read_text_file",
    description="读取文本文件内容",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)
def read_text_file(path: str, max_chars: int = 8000) -> str:
    target = _resolve(path)
    if not target.exists() or not target.is_file():
        return f"文件不存在: {target}"
    raw = target.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... (截断，共 {len(text)} 字符)"
    return text


@register_tool(
    name="write_text_file",
    description="写入文本文件",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def write_text_file(path: str, content: str) -> str:
    if blocked := _reject_windows_c_os("write_text_file", path):
        return blocked
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    try:
        from friday.artifacts import maybe_register_written_file

        maybe_register_written_file(target)
    except Exception:
        pass
    return f"已写入: {target}"


@register_tool(
    name="move_file",
    description="移动或重命名文件",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["source", "destination"],
    },
)
def move_file(source: str, destination: str) -> str:
    if blocked := _reject_windows_c_os("move_file", source, destination):
        return blocked
    src = _resolve(source)
    dst = _resolve(destination)
    if not src.exists():
        return f"源文件不存在: {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"已移动: {src} -> {dst}"


@register_tool(
    name="organize_directory",
    description="整理目录。by=extension 按扩展名分文件夹；by=date 按修改月份分文件夹",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "by": {"type": "string", "enum": ["extension", "date"]},
        },
        "required": ["path"],
    },
)
def organize_directory(path: str, by: str = "extension") -> str:
    if blocked := _reject_windows_c_os("organize_directory", path):
        return blocked
    target = _resolve(path)
    if not target.exists() or not target.is_dir():
        return f"目录不存在: {target}"

    moved = 0
    if by == "date":
        for item in target.iterdir():
            if not item.is_file():
                continue
            stamp = datetime.fromtimestamp(item.stat().st_mtime)
            bucket = target / stamp.strftime("%Y-%m")
            bucket.mkdir(exist_ok=True)
            shutil.move(str(item), str(bucket / item.name))
            moved += 1
    else:
        buckets: dict[str, list[Path]] = defaultdict(list)
        for item in target.iterdir():
            if not item.is_file():
                continue
            ext = item.suffix.lower().lstrip(".") or "no_extension"
            buckets[ext].append(item)
        for ext, files in buckets.items():
            bucket = target / ext
            bucket.mkdir(exist_ok=True)
            for item in files:
                shutil.move(str(item), str(bucket / item.name))
                moved += 1
    return f"已整理 {moved} 个文件，规则: {by}"


# ── 新增工具 ──

@register_tool(
    name="delete_file",
    description="删除指定文件（不可恢复，需审批）",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要删除的文件路径"},
        },
        "required": ["path"],
    },
)
def delete_file(path: str) -> str:
    if blocked := _reject_windows_c_os("delete_file", path):
        return blocked
    target = _resolve(path)
    if not target.exists():
        return f"文件不存在: {target}"
    if target.is_dir():
        return f"目标是目录，请用 delete_directory: {target}"
    target.unlink()
    return f"已删除: {target}"


@register_tool(
    name="delete_directory",
    description="递归删除目录及其所有内容（不可恢复，需审批）",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要删除的目录路径"},
        },
        "required": ["path"],
    },
)
def delete_directory(path: str) -> str:
    if blocked := _reject_windows_c_os("delete_directory", path):
        return blocked
    target = _resolve(path)
    if not target.exists():
        return f"目录不存在: {target}"
    if not target.is_dir():
        return f"不是目录: {target}"
    shutil.rmtree(target)
    return f"已删除目录: {target}"


@register_tool(
    name="copy_file",
    description="复制文件或目录到目标位置",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源路径"},
            "destination": {"type": "string", "description": "目标路径"},
        },
        "required": ["source", "destination"],
    },
)
def copy_file(source: str, destination: str) -> str:
    src = _resolve(source)
    dst = _resolve(destination)
    if not src.exists():
        return f"源路径不存在: {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return f"已复制: {src} -> {dst}"


@register_tool(
    name="get_file_info",
    description="获取文件或目录的详细信息（大小、修改时间、MD5）",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件或目录路径"},
        },
        "required": ["path"],
    },
)
def get_file_info(path: str) -> str:
    target = _resolve(path)
    if not target.exists():
        return f"路径不存在: {target}"

    stat = target.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    ctime = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"路径: {target}",
        f"类型: {'目录' if target.is_dir() else '文件'}",
        f"大小: {stat.st_size:,} bytes ({stat.st_size / 1024:.1f} KB)",
        f"修改时间: {mtime}",
        f"创建时间: {ctime}",
    ]

    if target.is_file():
        try:
            hasher = hashlib.md5()
            with target.open("rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            lines.append(f"MD5: {hasher.hexdigest()}")
        except OSError:
            lines.append("MD5: (无法读取)")

    if target.is_dir():
        items = list(target.iterdir())
        files = sum(1 for i in items if i.is_file())
        dirs = sum(1 for i in items if i.is_dir())
        lines.append(f"包含: {files} 个文件, {dirs} 个子目录")

    return "\n".join(lines)
