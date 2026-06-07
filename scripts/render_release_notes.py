#!/usr/bin/env python3
"""从 assets/changelog.json 生成 UTF-8 Release 说明。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday.changelog import clear_cache, load_entries
from friday.version import __version__


def format_entry(entry: dict) -> str:
    lines = [f"## 星期五 v{entry['version']}"]
    if entry.get("date"):
        lines.append(f"\n**发布日期：** {entry['date']}")
    if entry.get("title"):
        lines.append(f"\n{entry['title']}")
    for sec in entry.get("sections") or []:
        items = sec.get("items") or []
        if not items:
            continue
        lines.append(f"\n### {sec.get('label', '更新')}")
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def render(version: str | None = None) -> str:
    clear_cache()
    version = version or __version__
    match = next((e for e in load_entries() if str(e.get("version")) == version), None)
    if not match:
        return f"## 星期五 v{version}\n\nWindows AI 电脑管家。"
    body = format_entry(match)
    body += """

### 安装
1. 下载 `Friday-Windows.zip`
2. 解压后运行 `星期五.exe`
3. 详见压缩包内 `安装教程.txt`

---
Gitee: https://gitee.com/Bxxxboo/friday/releases
GitHub: https://github.com/Bxxxboo/Friday-Zero-barrier-DeepSeek-Agent-for-Windows/releases
"""
    return body


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    text = render(version)
    out_path = ROOT / "release" / ".release-notes.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    if "--print" in sys.argv:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
