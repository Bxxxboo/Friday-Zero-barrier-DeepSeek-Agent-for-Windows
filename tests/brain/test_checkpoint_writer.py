from __future__ import annotations

import threading
import time

import pytest

from friday.checkpoint_writer import (
    CheckpointFields,
    append_session_note,
    checkpoint_tier_for_ratio,
    load_checkpoint_meta,
    parse_checkpoint_md,
    read_checkpoint,
    render_checkpoint_md,
    write_checkpoint_sync,
    CheckpointMeta,
)
from friday.config import CHECKPOINT_TRIGGER_RATIOS
from friday.sessions import create_session, get_session


def test_checkpoint_tier_thresholds():
    assert checkpoint_tier_for_ratio(0.1) == -1
    assert checkpoint_tier_for_ratio(0.20) == 0
    assert checkpoint_tier_for_ratio(0.44) == 0
    assert checkpoint_tier_for_ratio(0.45) == 1
    assert checkpoint_tier_for_ratio(0.70) == 2


def test_render_and_parse_roundtrip():
    fields = CheckpointFields(
        goal_context="整理 E 盘下载目录",
        key_paths="- E:\\Downloads\\foo.zip",
        pending="- 验证安装包",
    )
    meta = CheckpointMeta(version=3, last_trigger_tier=2, updated_at=1_700_000_000.0)
    md = render_checkpoint_md(fields, meta)
    parsed_meta, parsed_fields = parse_checkpoint_md(md)
    assert parsed_meta.version == 3
    assert parsed_fields.goal_context == "整理 E 盘下载目录"
    assert "E:\\Downloads" in parsed_fields.key_paths


def test_write_increment_versions(tmp_appdata):
    session = create_session("测试检查点", activate=False)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "请整理 C:\\Users\\test\\Desktop"},
        {"role": "assistant", "content": "已开始"},
    ]
    write_checkpoint_sync(
        session.id,
        tier=0,
        ratio=CHECKPOINT_TRIGGER_RATIOS[0],
        token_count=1000,
        budget=5000,
        messages=messages,
    )
    first = read_checkpoint(session.id)
    assert first["exists"]
    assert first["version"] == 1

    write_checkpoint_sync(
        session.id,
        tier=1,
        ratio=CHECKPOINT_TRIGGER_RATIOS[1],
        token_count=2500,
        budget=5000,
        messages=messages,
    )
    second = read_checkpoint(session.id)
    assert second["version"] == 2
    meta = load_checkpoint_meta(session.id)
    assert meta.last_trigger_tier >= 1


def test_notes_absorbed_on_checkpoint(tmp_appdata):
    session = create_session("笔记吸收", activate=False)
    append_session_note(session.id, "决策：默认保存到 E 盘")
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "记住路径 E:\\软件"},
    ]
    write_checkpoint_sync(
        session.id,
        tier=0,
        ratio=0.2,
        token_count=900,
        budget=4000,
        messages=messages,
    )
    data = read_checkpoint(session.id)
    tools_summary = (data.get("fields") or {}).get("tools_summary", "")
    assert "E 盘" in tools_summary or "决策" in tools_summary
    from friday.checkpoint_writer import notes_path

    assert not notes_path(session.id).exists()


def test_concurrent_writes_do_not_corrupt(tmp_appdata):
    session = create_session("并发写", activate=False)
    messages = [{"role": "user", "content": "并发测试"}]
    errors: list[Exception] = []

    def worker(tier: int) -> None:
        try:
            write_checkpoint_sync(
                session.id,
                tier=tier,
                ratio=0.2 + tier * 0.1,
                token_count=100 + tier,
                budget=5000,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    data = read_checkpoint(session.id)
    assert data["exists"]
    assert data["version"] >= 1


def test_schedule_gate_uses_meta_tier(tmp_appdata, monkeypatch):
    from friday.checkpoint_writer import save_checkpoint_meta, CheckpointMeta, maybe_schedule_checkpoint

    monkeypatch.setattr(
        "friday.brain.compute_context_meter",
        lambda *a, **k: {
            "budget_ratio": 0.5,
            "context_tokens": 2000,
            "context_budget": 4000,
        },
    )
    session = create_session("调度", activate=False)
    save_checkpoint_meta(session.id, CheckpointMeta(last_trigger_tier=1))
    assert maybe_schedule_checkpoint(session.id, [{"role": "user", "content": "短"}]) is False


def test_schedule_dedupes_pending_tier(tmp_appdata, monkeypatch):
    from friday.checkpoint_writer import maybe_schedule_checkpoint

    enqueued: list[str] = []
    monkeypatch.setattr(
        "friday.checkpoint_writer._enqueue",
        lambda session_id, _job: enqueued.append(session_id),
    )
    monkeypatch.setattr(
        "friday.brain.compute_context_meter",
        lambda *a, **k: {
            "budget_ratio": 0.5,
            "context_tokens": 2000,
            "context_budget": 4000,
        },
    )
    session = create_session("去重调度", activate=False)
    messages = [{"role": "user", "content": "长任务"}]
    assert maybe_schedule_checkpoint(session.id, messages) is True
    assert maybe_schedule_checkpoint(session.id, messages) is False
    assert enqueued == [session.id]
