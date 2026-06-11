#!/usr/bin/env python3
"""删除过旧 GitHub Release（默认保留最近 N 个 tag）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def _resolve_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
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
                        return token
            except OSError:
                continue
    except ImportError:
        pass
    return ""


def _request(method: str, url: str, token: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Bxxxboo/Friday-WeChat-Windows-AI-Butler")
    parser.add_argument("--keep", type=int, default=3, help="保留最新 N 个 Release")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = _resolve_token()
    if not token:
        print("GITHUB_TOKEN required (session or Windows User env var)", file=sys.stderr)
        return 1

    repo = args.repo
    releases = _request("GET", f"{API}/repos/{repo}/releases?per_page=100", token)
    if not isinstance(releases, list):
        print("Unexpected API response", file=sys.stderr)
        return 1

    def _sort_key(rel: dict) -> str:
        return str(rel.get("published_at") or rel.get("created_at") or "")

    releases = sorted(releases, key=_sort_key, reverse=True)
    keep = max(1, args.keep)
    to_delete = releases[keep:]
    kept = releases[:keep]
    print("Keeping:", [r.get("tag_name") for r in kept])
    print(f"Total releases: {len(releases)}; keep {keep}; delete {len(to_delete)}")
    for rel in to_delete:
        tag = rel.get("tag_name", "")
        rid = rel.get("id")
        assets = [a.get("name") for a in (rel.get("assets") or [])]
        print(f"  DELETE {tag} (id={rid}) assets={assets}")
        if args.dry_run or rid is None:
            continue
        try:
            _request("DELETE", f"{API}/repos/{repo}/releases/{rid}", token)
            print("    done")
        except urllib.error.HTTPError as exc:
            print(f"    failed: {exc.code} {exc.reason}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
