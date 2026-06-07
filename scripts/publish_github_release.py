#!/usr/bin/env python3
"""GitHub Release 发布/更新（UTF-8 安全）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday.version import __version__

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
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


def render_notes() -> str:
    from scripts.render_release_notes import render

    return render(__version__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Bxxxboo/Friday-Zero-barrier-DeepSeek-Agent-for-Windows")
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--zip", default=str(ROOT / "release" / "Friday-Windows.zip"))
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
        _request(
            "PATCH",
            f"{API}/repos/{repo}/releases/{release_id}",
            token,
            data={"name": title, "body": notes},
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        print(f"Creating release {tag} on {repo} ...")
        release = _request(
            "POST",
            f"{API}/repos/{repo}/releases",
            token,
            data={"tag_name": tag, "name": title, "body": notes},
        )
        release_id = release["id"]

    if args.skip_upload:
        print("Skip upload.")
    else:
        zip_path = Path(args.zip)
        if not zip_path.is_file():
            print(f"Zip not found: {zip_path}", file=sys.stderr)
            return 1
        release = _request("GET", f"{API}/repos/{repo}/releases/{release_id}", token)
        for asset in release.get("assets") or []:
            if asset.get("name") == "Friday-Windows.zip":
                aid = asset["id"]
                print(f"Removing existing asset id {aid} ...")
                _request("DELETE", f"{API}/repos/{repo}/releases/assets/{aid}", token)
        print(f"Uploading {zip_path.name} ...")
        data = zip_path.read_bytes()
        _request(
            "POST",
            f"{UPLOAD}/repos/{repo}/releases/{release_id}/assets?name=Friday-Windows.zip",
            token,
            raw=data,
            content_type="application/zip",
        )

    print(f"Done: https://github.com/{repo}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
