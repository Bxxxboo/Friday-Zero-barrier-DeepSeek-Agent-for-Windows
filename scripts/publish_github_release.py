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

from friday.version import __version__, release_zip_name

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
        with urllib.request.urlopen(req, timeout=120) as resp:
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
        print("GITHUB_TOKEN required", file=sys.stderr)
        return 1

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

    if args.skip_upload:
        print("Skip upload.")
    else:
        zip_path = Path(args.zip)
        if not zip_path.is_file():
            print(f"Zip not found: {zip_path}", file=sys.stderr)
            return 1
        zip_name = zip_path.name
        release = _request("GET", f"{API}/repos/{repo}/releases/{release_id}", token)
        for asset in release.get("assets") or []:
            name = str(asset.get("name", ""))
            if name == zip_name or name == "Friday-Windows.zip":
                aid = asset["id"]
                print(f"Removing existing asset {name} (id {aid}) ...")
                _request("DELETE", f"{API}/repos/{repo}/releases/assets/{aid}", token)
        print(f"Uploading {zip_name} ...")
        data = zip_path.read_bytes()
        _request(
            "POST",
            f"{UPLOAD}/repos/{repo}/releases/{release_id}/assets?name={urllib.parse.quote(zip_name)}",
            token,
            raw=data,
            content_type="application/zip",
        )

    print(f"Done: https://github.com/{repo}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
