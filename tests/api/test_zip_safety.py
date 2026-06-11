from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from friday.zip_safety import extract_zip_archive, resolve_zip_member_path


def test_resolve_zip_member_path_allows_normal(tmp_path: Path):
    root = tmp_path / "dest"
    root.mkdir()
    target = resolve_zip_member_path(root, "Friday/Friday.exe")
    assert target == (root / "Friday" / "Friday.exe").resolve()


def test_resolve_zip_member_path_rejects_traversal(tmp_path: Path):
    root = tmp_path / "dest"
    root.mkdir()
    with pytest.raises(ValueError, match="unsafe"):
        resolve_zip_member_path(root, "../outside.txt")


def test_extract_zip_archive_blocks_escape(tmp_path: Path):
    root = tmp_path / "dest"
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("ok.txt", "fine")
        zf.writestr("../../escape.txt", "bad")
    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(ValueError, match="unsafe"):
            extract_zip_archive(zf, root)
    assert not (tmp_path / "escape.txt").exists()
