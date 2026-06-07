from __future__ import annotations

import json
import os
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("weixin.config")

BRIDGE_FILENAME = "weixin-bridge.json"


def bridge_config_path() -> Path:
    return get_appdata_dir() / BRIDGE_FILENAME


def write_bridge_config(port: int, token: str, *, enabled: bool = True) -> Path:
    path = bridge_config_path()
    payload = {
        "enabled": enabled,
        "port": port,
        "token": token,
        "base_url": f"http://127.0.0.1:{port}",
        "timeout_ms": 600_000,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info("微信桥接配置已写入 | path=%s port=%d", path, port)
    return path


def read_bridge_config() -> dict | None:
    path = bridge_config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def openclaw_state_dir() -> Path:
    override = os.environ.get("OPENCLAW_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".openclaw"
