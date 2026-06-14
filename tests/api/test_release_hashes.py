"""Release SHA256 清单与校验测试（M3.3 / M3.4）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from friday.release_hashes import (
    derive_sums_download_url,
    expected_sha256_for_download,
    parse_sums_text,
    sha256_hex_file,
    verify_file_sha256,
)


def test_parse_sums_text():
    digest = "a" * 64
    text = f"""
# comment
{digest}  Friday-Update-1.3.1.zip
"""
    parsed = parse_sums_text(text)
    assert parsed["friday-update-1.3.1.zip"] == digest


def test_derive_sums_download_url():
    url = "https://gitee.com/Bxxxboo/friday/releases/download/v1.3.1/Friday-Update-1.3.1.zip"
    assert derive_sums_download_url(url).endswith("/v1.3.1/SHA256SUMS.txt")


def test_expected_sha256_for_download_from_map():
    url = "https://gitee.com/Bxxxboo/friday/releases/download/v1.3.1/Friday-Update-1.3.1.zip"
    digest = "a" * 64
    found = expected_sha256_for_download(
        url,
        sums_map={"friday-update-1.3.1.zip": digest},
    )
    assert found == digest


def test_expected_sha256_fetches_sums_from_release_url(monkeypatch):
    url = "https://gitee.com/Bxxxboo/friday/releases/download/v1.3.7/Friday-Update-1.3.7.zip"
    digest = "b" * 64
    sums_url = derive_sums_download_url(url)
    assert sums_url

    def fake_fetch(target: str, *, timeout: float = 30.0) -> dict[str, str]:
        assert target == sums_url
        return parse_sums_text(f"{digest}  Friday-Update-1.3.7.zip\n")

    monkeypatch.setattr("friday.release_hashes.fetch_sums_map", fake_fetch)
    assert expected_sha256_for_download(url) == digest


def test_sha256_hex_file_and_verify(tmp_path: Path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"friday-update-payload")
    digest = sha256_hex_file(path)
    verify_file_sha256(path, digest)
    with pytest.raises(RuntimeError, match="SHA256"):
        verify_file_sha256(path, "b" * 64)


def test_verify_skips_when_expected_empty(tmp_path: Path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"x")
    verify_file_sha256(path, "")
