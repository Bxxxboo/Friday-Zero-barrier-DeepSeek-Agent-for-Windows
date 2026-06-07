from __future__ import annotations

from friday.sessions import create_session, get_session, rename_session, save_agent_state
from friday.weixin.sessions import WEIXIN_SESSION_TITLE, resolve_session_id


def test_rename_session_pins_title(tmp_appdata):
    session = create_session(title="新对话")
    renamed = rename_session(session.id, "自定义名称")
    assert renamed.title == "自定义名称"
    assert renamed.title_pinned is True

    save_agent_state(
        session.id,
        [{"role": "user", "content": "这条消息不应覆盖标题"}],
        user_text="这条消息不应覆盖标题",
    )
    updated = get_session(session.id)
    assert updated is not None
    assert updated.title == "自定义名称"


def test_weixin_session_default_title(tmp_appdata):
    session_id = resolve_session_id("acc1", "peer1@im.wechat")
    session = get_session(session_id)
    assert session is not None
    assert session.title == WEIXIN_SESSION_TITLE
    assert session.title_pinned is True


def test_weixin_legacy_title_upgrade(tmp_appdata):
    legacy = create_session(title="微信 821ab0ba")
    mapping_path = tmp_appdata / "weixin_sessions.json"
    mapping_path.write_text(
        '{"acc1::peer1@im.wechat": "%s"}' % legacy.id,
        encoding="utf-8",
    )
    session_id = resolve_session_id("acc1", "peer1@im.wechat")
    assert session_id == legacy.id
    session = get_session(session_id)
    assert session is not None
    assert session.title == WEIXIN_SESSION_TITLE
    assert session.title_pinned is True
