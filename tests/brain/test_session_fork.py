from __future__ import annotations

from friday.checkpoint_writer import write_checkpoint_sync
from friday.sessions import fork_session, create_session, get_session, save_session_fields


def test_fork_copies_checkpoint_seed(tmp_appdata):
    parent = create_session("父会话", activate=False)
    write_checkpoint_sync(
        parent.id,
        tier=0,
        ratio=0.2,
        token_count=500,
        budget=3000,
        messages=[{"role": "user", "content": "长期任务"}],
    )
    child = fork_session(parent.id)
    assert child is not None
    assert child.id != parent.id
    assert child.source == "fork"
    loaded = get_session(child.id)
    assert loaded is not None
    assert loaded.agent_messages
    combined = str(loaded.agent_messages[0].get("content", ""))
    assert "工作记忆" in combined or "检查点" in combined


def test_fork_resets_checkpoint_version(tmp_appdata):
    parent = create_session("父版本", activate=False)
    save_session_fields(parent.id, checkpoint_version=3)
    child = fork_session(parent.id)
    assert child is not None
    assert child.checkpoint_version == 0
