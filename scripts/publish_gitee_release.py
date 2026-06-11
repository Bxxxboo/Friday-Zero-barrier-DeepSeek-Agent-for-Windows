#!/usr/bin/env python3
"""Gitee Release 发布/更新（UTF-8 安全）。"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday.version import __version__, release_setup_name, release_update_zip_name, release_zip_name

API = "https://gitee.com/api/v5"


def _form_request(method: str, url: str, fields: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(value.encode("utf-8"))
        buf.write(b"\r\n")
    for name, (filename, content, content_type) in files.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
        buf.write(f"Content-Type: {content_type}\r\n\r\n".encode())
        buf.write(content)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def render_notes(version: str) -> str:
    from scripts.render_release_notes import render

    return render(version)


def find_release(repo: str, tag: str, token: str) -> dict | None:
    tag_q = urllib.parse.quote(tag, safe="")
    for url in (
        f"{API}/repos/{repo}/releases/tags/{tag_q}?access_token={token}",
        f"{API}/repos/{repo}/releases/tags/{tag_q}",
    ):
        try:
            data = _get_json(url)
            if isinstance(data, dict) and data.get("id"):
                return data
        except urllib.error.HTTPError:
            continue
    return None


def upload_asset(repo: str, release_id: int, token: str, zip_path: Path) -> None:
    release = _get_json(f"{API}/repos/{repo}/releases/{release_id}?access_token={token}")
    for asset in release.get("assets") or []:
        if asset.get("name") == zip_path.name:
            aid = asset.get("id")
            if aid is None:
                continue
            print(f"Removing existing asset {zip_path.name} (id {aid}) ...")
            req = urllib.request.Request(
                f"{API}/repos/{repo}/releases/assets/{aid}?access_token={token}",
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=60):
                pass

    print(f"Uploading {zip_path.name} ({zip_path.stat().st_size // (1024 * 1024)} MB) ...")
    body, boundary = _multipart(
        {"access_token": token},
        {"file": (zip_path.name, zip_path.read_bytes(), "application/zip")},
    )
    req = urllib.request.Request(
        f"{API}/repos/{repo}/releases/{release_id}/attach_files",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Bxxxboo/friday")
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--zip", default=str(ROOT / "release" / release_zip_name()))
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITEE_TOKEN", "").strip()
    if not token:
        print("GITEE_TOKEN required", file=sys.stderr)
        return 1

    tag = f"v{args.version}"
    repo = args.repo
    notes = render_notes(args.version)
    title = f"星期五 v{args.version}"

    existing = find_release(repo, tag, token)
    if existing:
        release_id = int(existing["id"])
        print(f"Updating Gitee release {tag} (id {release_id}) ...")
        _form_request(
            "PATCH",
            f"{API}/repos/{repo}/releases/{release_id}",
            {
                "access_token": token,
                "tag_name": tag,
                "name": title,
                "body": notes,
            },
        )
    else:
        print(f"Creating Gitee release {tag} on {repo} ...")
        created = _form_request(
            "POST",
            f"{API}/repos/{repo}/releases",
            {
                "access_token": token,
                "tag_name": tag,
                "name": title,
                "body": notes,
                "target_commitish": "main",
            },
        )
        release_id = int(created["id"])

    if not args.skip_upload:
        zip_path = Path(args.zip)
        if not zip_path.is_file():
            print(f"Zip not found: {zip_path}", file=sys.stderr)
            return 1
        upload_asset(repo, release_id, token, zip_path)
        update_path = ROOT / "release" / release_update_zip_name(args.version)
        if update_path.is_file():
            print(f"Uploading update zip: {update_path.name} ...")
            upload_asset(repo, release_id, token, update_path)
        else:
            print(f"Update zip not found (optional): {update_path}")
        setup_path = ROOT / "release" / release_setup_name(args.version)
        if setup_path.is_file():
            print(f"Uploading setup: {setup_path.name} ...")
            upload_asset(repo, release_id, token, setup_path)
        else:
            print(f"Setup not found (optional): {setup_path}")
    else:
        print("Skip upload.")

    print(f"Done: https://gitee.com/{repo}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
