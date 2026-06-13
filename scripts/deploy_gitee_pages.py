#!/usr/bin/env python3
"""触发 Gitee Pages 构建（官网国内镜像）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

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


def get_pages(repo: str, token: str) -> dict | None:
    url = f"{API}/repos/{repo}/pages?access_token={urllib.parse.quote(token, safe='')}"
    try:
        data = _get_json(url)
        return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 405}:
            return None
        raise


def trigger_build(repo: str, token: str) -> dict:
    url = f"{API}/repos/{repo}/pages/builds"
    return _form_request("POST", url, {"access_token": token})


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger Gitee Pages build")
    parser.add_argument("--repo", default="Bxxxboo/friday")
    parser.add_argument("--token", default=os.environ.get("GITEE_TOKEN", "").strip())
    args = parser.parse_args()
    if not args.token:
        print("GITEE_TOKEN not set", file=sys.stderr)
        return 1

    pages = get_pages(args.repo, args.token)
    if pages:
        status = pages.get("status") or pages.get("build_status") or "unknown"
        print(f"Pages status: {status}")
        if pages.get("html_url"):
            print(f"Site: {pages['html_url']}")
    else:
        print(
            "Gitee Pages not enabled yet. Open "
            f"https://gitee.com/{args.repo}/pages and start Pages on branch `pages`.",
            file=sys.stderr,
        )

    try:
        result = trigger_build(args.repo, args.token)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Build request failed ({exc.code}): {body}", file=sys.stderr)
        if exc.code in {403, 404}:
            print(
                "Enable Gitee Pages first: "
                f"https://gitee.com/{args.repo}/pages (branch: pages)",
                file=sys.stderr,
            )
        return exc.code if 0 < exc.code < 256 else 1

    message = result.get("message") or result.get("status") or "ok"
    print(f"Build triggered: {message}")
    if result.get("html_url"):
        print(f"Site: {result['html_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
