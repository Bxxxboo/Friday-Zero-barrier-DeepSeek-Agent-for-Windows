from __future__ import annotations

import json
from pathlib import Path

import pytest

from friday.io_utils import load_json
from friday.portability import (
    expand_config_path,
    migrate_session_portable_paths,
    repair_workspace,
    resolve_portable_path,
    run_portability_audit,
    to_portable_path,
    validate_workspace_path,
)
from friday.sessions import create_session, get_session, save_agent_state
from friday.storage import UserSettings, load_settings, save_settings


def test_validate_workspace_rejects_missing_drive(tmp_appdata, monkeypatch):
    if not hasattr(Path, "drive"):
        pytest.skip("non-Windows")
    ok, reason = validate_workspace_path("Z:/DefinitelyMissingFridayWorkspace")
    assert not ok
    assert "盘符" in reason or "父目录" in reason


def test_repair_workspace_resets_other_user_path(tmp_appdata, monkeypatch):
    monkeypatch.setenv("USERNAME", "CurrentUser")
    settings = UserSettings(workspace="C:/Users/OtherUser/Documents/Friday")
    updated, notices = repair_workspace(settings)
    assert updated.workspace
    assert "OtherUser" not in updated.workspace or notices
    assert notices
    assert load_settings().workspace == updated.workspace


def test_to_portable_and_resolve_roundtrip(tmp_appdata):
    settings = load_settings()
    workspace = settings.workspace or str(tmp_appdata / "workspace")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    img_dir = Path(workspace) / "生成的图片"
    img_dir.mkdir(parents=True, exist_ok=True)
    img = img_dir / "test.png"
    img.write_bytes(b"png")

    absolute = str(img.resolve()).replace("\\", "/")
    portable = to_portable_path(absolute, workspace)
    assert portable == "生成的图片/test.png"

    resolved = resolve_portable_path(portable, workspace)
    assert resolved == img.resolve()


def test_save_session_stores_portable_image_paths(tmp_appdata):
    workspace = str(tmp_appdata / "workspace")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    from friday.storage import save_settings

    save_settings(load_settings().merge({"workspace": workspace.replace("\\", "/")}))
    img_dir = Path(workspace) / "generated"
    img_dir.mkdir(parents=True, exist_ok=True)
    img = img_dir / "grass.png"
    img.write_bytes(b"png")
    absolute = str(img.resolve()).replace("\\", "/")

    session = create_session()
    messages = [
        {"role": "user", "content": "draw"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_img_1",
                    "type": "function",
                    "function": {"name": "generate_image", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_img_1",
            "content": f"已生成图片并保存：{absolute}\n尺寸：1024x1024，模型：test。",
        },
        {"role": "assistant", "content": "done"},
    ]
    save_agent_state(session.id, messages, user_text="draw")

    loaded = get_session(session.id)
    assert loaded is not None
    imgs = loaded.display_messages[-1]["generated_images"]
    assert imgs == [{"path": "generated/grass.png"}]

    from friday.image_gen import resolve_generated_image_path

    resolved = resolve_generated_image_path(imgs[0]["path"], load_settings())
    assert resolved == img.resolve()


def test_migrate_session_image_paths_legacy_absolute(tmp_appdata):
    workspace = str(tmp_appdata / "workspace")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    img = Path(workspace) / "legacy.png"
    img.write_bytes(b"png")
    absolute = str(img.resolve()).replace("\\", "/")

    session = create_session()
    raw_path = tmp_appdata / "sessions" / f"{session.id}.json"
    payload = {
        "format_version": 2,
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "title_pinned": False,
        "display_messages": [
            {
                "role": "assistant",
                "content": "ok",
                "generated_images": [{"path": absolute}],
            }
        ],
        "agent_messages": [],
    }
    raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    count = migrate_session_portable_paths(workspace)
    assert count == 1
    loaded = get_session(session.id)
    assert loaded is not None
    assert loaded.display_messages[0]["generated_images"] == [{"path": "legacy.png"}]


def test_expand_config_path_auto(tmp_appdata):
    path = expand_config_path("auto", ensure_default_exists=True)
    assert path
    ok, _ = validate_workspace_path("auto")
    assert ok


def test_expand_config_path_tilde(tmp_appdata, monkeypatch):
    home = tmp_appdata / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    ws = home / "Friday"
    ws.mkdir()
    expanded = expand_config_path("~/Friday")
    assert expanded.replace("\\", "/") == str(ws.resolve()).replace("\\", "/")


def test_run_portability_audit_basic(tmp_appdata):
    settings = load_settings()
    items = run_portability_audit(settings)
    ids = {item["id"] for item in items}
    assert "workspace" in ids
    assert "encryption" in ids


def test_export_import_portable_bundle_roundtrip(tmp_appdata):
    from friday.portable_bundle import export_portable_bundle, import_portable_bundle

    save_settings(load_settings().merge({"workspace": str(tmp_appdata / "workspace").replace("\\", "/")}))
    export_path = tmp_appdata / "out.zip"
    path, report = export_portable_bundle(export_path)
    assert path.is_file()
    assert "settings.json" in report["included"]

    (tmp_appdata / "settings.json").write_text("{}", encoding="utf-8")
    result = import_portable_bundle(path)
    assert not result["errors"]
    assert "settings.json" in result["imported"]
    loaded = load_json(tmp_appdata / "settings.json")
    assert isinstance(loaded, dict)
    assert "workspace" in loaded
