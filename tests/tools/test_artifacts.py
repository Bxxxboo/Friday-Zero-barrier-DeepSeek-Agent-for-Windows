from __future__ import annotations

import time
from pathlib import Path

import pytest

from friday.artifacts import (
    LIFECYCLE_DELIVERED,
    LIFECYCLE_SCRATCH,
    LIFECYCLE_SESSION,
    artifacts_dir,
    register_artifact,
    run_gc,
    storage_summary,
    sync_session_references,
)
from friday.sessions import create_session, save_agent_state
from friday.storage import UserSettings, load_settings


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    cfg = load_settings().merge({"workspace": str(ws).replace("\\", "/")})
    monkeypatch.setattr("friday.storage.load_settings", lambda: cfg)
    monkeypatch.setattr("friday.artifacts.load_settings", lambda: cfg)
    return ws, cfg


def test_register_and_gc_scratch_to_trash(workspace):
    ws, cfg = workspace
    root = artifacts_dir(cfg)
    script = root / "once.py"
    script.write_text("print(1)", encoding="utf-8")
    entry = register_artifact(
        script,
        kind="script",
        lifecycle=LIFECYCLE_SCRATCH,
        settings=cfg,
    )
    assert entry is not None

    items_before = run_gc(settings=cfg, dry_run=True)
    assert items_before["trashed"] == 0

    from friday import artifacts as artifacts_mod

    items = artifacts_mod._load_index(cfg)
    items[0]["expires_at"] = time.time() - 10
    artifacts_mod._save_index(items, cfg)

    result = run_gc(settings=cfg)
    assert result["trashed"] == 1
    assert not script.exists()
    trash_files = list((ws / ".friday" / "trash").glob("*.py"))
    assert len(trash_files) == 1


def test_delivered_not_auto_gc(workspace):
    ws, cfg = workspace
    img = ws / "生成的图片" / "test.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    register_artifact(img, kind="image", lifecycle=LIFECYCLE_DELIVERED, settings=cfg)
    result = run_gc(settings=cfg)
    assert result["trashed"] == 0
    assert img.exists()


def test_sync_session_references_promotes_scratch(workspace):
    ws, cfg = workspace
    session = create_session()
    img_path = ws / "生成的图片" / "keep.png"
    img_path.parent.mkdir(parents=True, exist_ok=True)
    img_path.write_bytes(b"png")
    normalized = str(img_path).replace("\\", "/")
    save_agent_state(
        session.id,
        [
            {"role": "user", "content": "画图"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "function": {"name": "generate_image", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": f"已生成图片并保存：{normalized}"},
            {"role": "assistant", "content": "好了"},
        ],
        user_text="画图",
    )
    scratch = artifacts_dir(cfg) / "tmp.py"
    scratch.write_text("x=1", encoding="utf-8")
    register_artifact(scratch, lifecycle=LIFECYCLE_SCRATCH, settings=cfg)
    register_artifact(img_path, lifecycle=LIFECYCLE_DELIVERED, settings=cfg)

    from friday import artifacts as artifacts_mod

    items = artifacts_mod._load_index(cfg)
    for item in items:
        if item["path"].endswith("keep.png"):
            item["lifecycle"] = LIFECYCLE_SCRATCH
    artifacts_mod._save_index(items, cfg)

    touched = sync_session_references(session.id, settings=cfg)
    assert touched >= 1
    items = artifacts_mod._load_index(cfg)
    keep = next(i for i in items if i["path"].endswith("keep.png"))
    assert keep["lifecycle"] == LIFECYCLE_SESSION


def test_storage_summary(workspace):
    ws, cfg = workspace
    f = artifacts_dir(cfg) / "a.txt"
    f.write_text("hi", encoding="utf-8")
    register_artifact(f, lifecycle=LIFECYCLE_SCRATCH, settings=cfg)
    summary = storage_summary(settings=cfg)
    assert summary["indexed_active_count"] >= 1
    assert summary["artifacts_dir_bytes"] >= 2
