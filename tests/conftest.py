from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """隔离 %APPDATA%/Friday，避免测试污染用户数据。

    凡调用 create_session / save_agent_state / save_settings / ensure_api_token
    的测试都必须依赖本 fixture（或等价 mock get_appdata_dir）。
    """
    appdata_root = tmp_path / "AppDataRoaming"
    appdata_root.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata_root))
    friday_dir = appdata_root / "Friday"
    friday_dir.mkdir()
    yield friday_dir


@pytest.fixture
def workspace(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "inside.txt").write_text("hello", encoding="utf-8")
    return ws
