"""静默启动 OpenClaw Gateway（无 CMD 窗口）。供计划任务 / 开机自启调用。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday.weixin.gateway import ensure_gateway_running, probe_gateway


def main() -> int:
    if probe_gateway():
        return 0
    result = ensure_gateway_running(wait_sec=60)
    if result.get("running"):
        return 0
    err = result.get("error") or "Gateway 未就绪"
    print(err, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
