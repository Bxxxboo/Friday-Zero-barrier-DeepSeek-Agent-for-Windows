"""Release 工件 SHA256 清单解析与校验（M3.3 / M3.4）。"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SUMS_FILENAME = "SHA256SUMS.txt"


def sha256_hex_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_sums_text(text: str) -> dict[str, str]:
    """解析 `hash  filename` 行，返回小写文件名 → 小写 hex。"""
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0].strip().lower(), parts[1].strip()
        if re.fullmatch(r"[a-f0-9]{64}", digest):
            out[Path(name).name.lower()] = digest
    return out


def filename_from_download_url(url: str) -> str:
    path = urllib.parse.urlparse((url or "").strip()).path
    return Path(path).name


def derive_sums_download_url(download_url: str) -> str | None:
    """从 Release 直链推导同 tag 下的 SHA256SUMS.txt 地址。"""
    url = (download_url or "").strip()
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    base_parts = parts[:-1] + [SUMS_FILENAME]
    new_path = "/" + "/".join(base_parts)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, new_path, "", "", ""))


def fetch_sums_map(sums_url: str, *, timeout: float = 30.0) -> dict[str, str]:
    request = urllib.request.Request(
        sums_url,
        headers={"User-Agent": "Friday-Desktop"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return parse_sums_text(text)


def expected_sha256_for_download(
    download_url: str,
    *,
    sums_map: dict[str, str] | None = None,
    sums_url: str | None = None,
) -> str:
    """按下载 URL 的文件名在清单中查找期望哈希；找不到返回空字符串。"""
    name = filename_from_download_url(download_url).lower()
    if not name:
        return ""
    mapping = sums_map
    if mapping is None and sums_url:
        try:
            mapping = fetch_sums_map(sums_url)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return ""
    if not mapping:
        return ""
    return mapping.get(name, "")


def verify_file_sha256(path: Path, expected_hex: str) -> None:
    expected = (expected_hex or "").strip().lower()
    if not expected:
        return
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise RuntimeError("更新包校验信息无效，请从官方 Release 重新下载。")
    actual = sha256_hex_file(path)
    if actual != expected:
        raise RuntimeError(
            "更新包校验失败（SHA256 不匹配），可能下载不完整或被篡改。"
            "请重新「检查更新」，或从 Gitee Releases 手动下载 Friday-Update.zip。"
        )
