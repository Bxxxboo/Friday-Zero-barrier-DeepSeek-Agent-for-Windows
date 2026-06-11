"""Zip 解压路径安全 —— 防止 Zip Slip 写出目标目录。"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


def resolve_zip_member_path(dest_dir: Path, member: str) -> Path:
    """将 zip 成员解析为 dest_dir 下的绝对路径；逃逸则 ValueError。"""
    name = (member or "").replace("\\", "/").strip()
    if not name or name.endswith("/"):
        name = name.rstrip("/")
        if not name:
            raise ValueError("empty zip member path")
    dest_root = dest_dir.resolve()
    target = (dest_root / Path(name)).resolve()
    try:
        target.relative_to(dest_root)
    except ValueError as exc:
        raise ValueError(f"unsafe zip entry: {member!r}") from exc
    return target


def extract_zip_archive(zf: zipfile.ZipFile, dest_dir: Path) -> None:
    """将 zip 安全解压到 dest_dir（拒绝 .. 与绝对路径成员）。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for member in zf.namelist():
        if member.endswith("/"):
            resolve_zip_member_path(dest_dir, member.rstrip("/")).mkdir(parents=True, exist_ok=True)
            continue
        target = resolve_zip_member_path(dest_dir, member)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
