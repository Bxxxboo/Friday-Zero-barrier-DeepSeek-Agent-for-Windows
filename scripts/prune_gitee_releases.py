#!/usr/bin/env python3
"""删除过旧 Gitee Release，释放附件配额（默认保留最近 3 个 tag）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://gitee.com/api/v5"


def _get(url: str) -> list | dict:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _delete(url: str) -> None:
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=60):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Bxxxboo/friday")
    parser.add_argument("--keep", type=int, default=3, help="保留最新 N 个 Release")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITEE_TOKEN", "").strip()
    if not token:
        print("GITEE_TOKEN required", file=sys.stderr)
        return 1

    repo = args.repo
    url = f"{API}/repos/{repo}/releases?access_token={token}&per_page=100&direction=desc"
    releases = _get(url)
    if not isinstance(releases, list):
        print("Unexpected API response", file=sys.stderr)
        return 1

    def _sort_key(rel: dict) -> str:
        return str(rel.get("created_at") or rel.get("published_at") or "")

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
        del_url = f"{API}/repos/{repo}/releases/{rid}?access_token={urllib.parse.quote(token)}"
        _delete(del_url)
        print(f"    done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
