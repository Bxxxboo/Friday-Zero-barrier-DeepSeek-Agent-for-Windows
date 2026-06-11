#!/usr/bin/env python3
"""GitHub Release 发布/更新（UTF-8 安全）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday.version import __version__, release_setup_name, release_update_zip_name, release_zip_name

API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"


def _request(
    method: str,
    url: str,
    token: str,
    *,
    data: dict | None = None,
    content_type: str = "application/json; charset=utf-8",
    raw: bytes | None = None,
    timeout: float = 120.0,
) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = raw
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = content_type
    elif raw is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except OSError:
            pass
        if exc.code == 403:
            hint = (
                "GitHub 403：Token 无权写入 Release/Assets。"
                "Classic PAT 需勾选 repo；Fine-grained 需对该仓库授权 Contents: Read and write。"
            )
            raise urllib.error.HTTPError(
                exc.url, exc.code, f"{exc.reason} — {hint}\n{detail[:500]}", exc.headers, exc.fp
            ) from exc
        raise


def render_notes() -> str:
    from scripts.render_release_notes import render

    return render(__version__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Bxxxboo/Friday-WeChat-Windows-AI-Butler")
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--zip", default=str(ROOT / "release" / release_zip_name()))
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        try:
            import winreg  # type: ignore[import-untyped]

            for hive, subkey in (
                (winreg.HKEY_CURRENT_USER, r"Environment"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        token = str(winreg.QueryValueEx(key, "GITHUB_TOKEN")[0]).strip()
                        if token:
                            break
                except OSError:
                    continue
        except ImportError:
            pass
    if not token:
        print("GITHUB_TOKEN required (session env or Windows User env var)", file=sys.stderr)
        return 1
    os.environ["GITHUB_TOKEN"] = token

    tag = f"v{args.version}"
    repo = args.repo
    notes = render_notes()
    title = f"Friday v{args.version}"

    try:
        release = _request("GET", f"{API}/repos/{repo}/releases/tags/{tag}", token)
        release_id = release["id"]
        print(f"Updating release {tag} (id {release_id}) ...")
        try:
            _request(
                "PATCH",
                f"{API}/repos/{repo}/releases/{release_id}",
                token,
                data={"name": title, "body": notes},
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 403:
                raise
            print("Warning: 无法更新 Release 说明（403），继续尝试上传 zip …", file=sys.stderr)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        print(f"Creating release {tag} on {repo} ...")
        release = _request(
            "POST",
            f"{API}/repos/{repo}/releases",
            token,
            data={
                "tag_name": tag,
                "target_commitish": "main",
                "name": title,
                "body": notes,
                "make_latest": "true",
            },
        )
        release_id = release["id"]

    def upload_asset(path: Path, *, content_type: str) -> None:
        if not path.is_file():
            print(f"Asset not found (optional): {path}", file=sys.stderr)
            return
        release_data = _request("GET", f"{API}/repos/{repo}/releases/{release_id}", token)
        for asset in release_data.get("assets") or []:
            if str(asset.get("name", "")) == path.name:
                aid = asset["id"]
                print(f"Removing existing asset {path.name} (id {aid}) ...")
                _request("DELETE", f"{API}/repos/{repo}/releases/assets/{aid}", token)
        size_mb = path.stat().st_size // (1024 * 1024)
        upload_timeout = max(600.0, size_mb * 12.0)
        print(f"Uploading {path.name} ({size_mb} MB, timeout {int(upload_timeout)}s) ...")
        payload = path.read_bytes()
        last_err: Exception | None = None
        for attempt in range(1, 4):
            try:
                _request(
                    "POST",
                    f"{UPLOAD}/repos/{repo}/releases/{release_id}/assets?name={urllib.parse.quote(path.name)}",
                    token,
                    raw=payload,
                    content_type=content_type,
                    timeout=upload_timeout,
                )
                last_err = None
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_err = exc
                if attempt >= 3:
                    raise
                print(f"  retry {attempt}/3 after network timeout: {exc}", file=sys.stderr)
        if last_err:
            raise last_err

    if args.skip_upload:
        print("Skip upload.")
    else:
        zip_path = Path(args.zip)
        if not zip_path.is_file():
            print(f"Zip not found: {zip_path}", file=sys.stderr)
            return 1
        upload_asset(zip_path, content_type="application/zip")
        upload_asset(ROOT / "release" / release_update_zip_name(args.version), content_type="application/zip")
        upload_asset(ROOT / "release" / release_setup_name(args.version), content_type="application/octet-stream")
        sums_path = ROOT / "release" / "SHA256SUMS.txt"
        if sums_path.is_file():
            upload_asset(sums_path, content_type="text/plain")
        else:
            print(f"SHA256SUMS.txt not found (run make-release.ps1 first): {sums_path}", file=sys.stderr)

    print(f"Done: https://github.com/{repo}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
