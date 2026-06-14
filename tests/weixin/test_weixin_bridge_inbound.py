from __future__ import annotations

import pytest

from friday.storage import UserSettings
from friday.weixin.bridge import InboundRequest, WEIXIN_TASK_ACK, handle_inbound
from friday.weixin.client import WeixinAccount


def _account() -> WeixinAccount:
    return WeixinAccount(
        account_id="bot-1",
        token="token-abc",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="user-1",
    )


@pytest.fixture(autouse=True)
def _reset_weixin_bridge_caches():
    import friday.weixin.bridge as bridge

    bridge._recent_inbound.clear()
    bridge._recent_approval_inbound.clear()
    bridge._recent_busy_notice.clear()
    bridge._processing_keys.clear()
    bridge._peer_processing_text.clear()
    bridge._approval_waiters.clear()
    bridge._approval_meta.clear()
    yield


def test_handle_inbound_returns_agent_reply_via_openclaw(tmp_appdata, monkeypatch):
    import time

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")
    monkeypatch.setattr("friday.weixin.bridge._run_agent", lambda **_k: "你好，我是星期五。")
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    result = handle_inbound(
        InboundRequest(
            text="帮我看一下 CPU",
            sender_id="peer-123",
            account_id="bot-1",
            context_token="ctx-token",
        )
    )

    time.sleep(0.3)
    assert result.handled is True
    assert result.reply == ""
    assert sent == [WEIXIN_TASK_ACK, "你好，我是星期五。"]


def test_handle_inbound_sends_immediate_ack_before_background_agent(tmp_appdata, monkeypatch):
    import time

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-ack")
    monkeypatch.setattr("friday.weixin.bridge._run_agent", lambda **_k: "最终结果")

    sent: list[str] = []

    def capture_send(*_a, text, **_k):
        sent.append(text)

    monkeypatch.setattr("friday.weixin.bridge.send_peer_text", capture_send)

    result = handle_inbound(
        InboundRequest(text="发文件", sender_id="peer-ack", account_id="bot-1"),
    )

    assert result.handled is True
    assert result.reply == ""
    assert sent[0] == WEIXIN_TASK_ACK
    time.sleep(0.3)
    assert sent == [WEIXIN_TASK_ACK, "最终结果"]


def test_handle_inbound_greeting_fast_path_skips_agent(tmp_appdata, monkeypatch):
    from friday.sessions import create_session, get_session

    session = create_session("我的微信", title_pinned=True, activate=False)
    notified: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-live-key-1234567890",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr(
        "friday.weixin.bridge.resolve_session_id",
        lambda *_a, **_k: session.id,
    )

    def fail_agent(**_kwargs):
        raise AssertionError("_run_agent should not be called for greetings")

    monkeypatch.setattr("friday.weixin.bridge._run_agent", fail_agent)
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )
    monkeypatch.setattr(
        "friday.weixin.bridge._notify_weixin_session_saved",
        lambda sid: notified.append(sid),
    )

    result = handle_inbound(
        InboundRequest(text="你好", sender_id="peer-123", account_id="bot-1"),
    )

    assert result.handled is True
    assert result.reply == ""
    assert len(sent) == 1
    assert "星期五" in sent[0]
    updated = get_session(session.id)
    assert updated is not None
    assert len(updated.display_messages) == 2
    assert "来自微信" in updated.display_messages[0]["content"]
    assert "星期五" in updated.display_messages[1]["content"]
    assert notified == [session.id]


def test_handle_inbound_falls_back_to_openclaw_when_ilink_fails(tmp_appdata, monkeypatch):
    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-live-key-1234567890",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")

    def fail_send(*_args, **_kwargs):
        raise RuntimeError("微信发送失败 (401)")

    monkeypatch.setattr("friday.weixin.bridge.send_peer_text", fail_send)

    result = handle_inbound(
        InboundRequest(
            text="你好",
            sender_id="peer-123",
            account_id="bot-1",
            context_token="ctx-token",
        )
    )

    assert result.handled is True
    assert "星期五" in result.reply


def test_handle_inbound_reports_missing_api(tmp_appdata, monkeypatch):
    import time

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(weixin_bridge_enabled=True),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    result = handle_inbound(
        InboundRequest(text="帮我看一下 CPU", sender_id="peer-123", account_id="bot-1"),
    )

    time.sleep(0.3)
    assert result.reply == ""
    assert sent[0] == WEIXIN_TASK_ACK
    assert sent[1] == "请先在星期五桌面版「设置 → API 连接」中配置并保存大模型 API Key。"


def test_format_weixin_agent_error_api_message():
    from friday.weixin.bridge import _format_weixin_agent_error

    class _FakeApiError(Exception):
        pass

    msg = _format_weixin_agent_error(_FakeApiError("Error code: 401 - Invalid API key"))
    assert "执行出错" in msg
    assert msg != "执行出错，请稍后重试，或在星期五桌面版查看日志。"


def test_handle_inbound_surfaces_agent_error(tmp_appdata, monkeypatch):
    import time

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")

    def boom(**_k):
        raise RuntimeError("Connection error: timed out")

    monkeypatch.setattr("friday.weixin.bridge._run_agent", boom)
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    result = handle_inbound(
        InboundRequest(text="帮我看一下 CPU", sender_id="peer-123", account_id="bot-1"),
    )

    time.sleep(0.3)
    assert result.handled is True
    assert result.reply == ""
    assert len(sent) == 2
    assert sent[0] == WEIXIN_TASK_ACK
    assert sent[1].startswith("执行出错")
    assert "timed out" in sent[1] or "连接" in sent[1]


def test_handle_inbound_ignores_duplicate_text(tmp_appdata, monkeypatch):
    import time

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")
    monkeypatch.setattr("friday.weixin.bridge._run_agent", lambda **_k: "完成")
    monkeypatch.setattr("friday.weixin.bridge.send_peer_text", lambda *_a, **_k: None)

    req = InboundRequest(text="帮我重复", sender_id="peer-dup", account_id="bot-1")
    first = handle_inbound(req)
    time.sleep(0.3)
    second = handle_inbound(req)

    assert first.reply == ""
    assert second.handled is True
    assert second.reply == ""


def test_handle_inbound_ignores_concurrent_duplicate_text(tmp_appdata, monkeypatch):
    import threading
    import time

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")

    gate = threading.Event()
    started = threading.Event()

    def slow_agent(**_k):
        started.set()
        gate.wait(timeout=2)
        return "额度查询结果"

    monkeypatch.setattr("friday.weixin.bridge._run_agent", slow_agent)
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    req = InboundRequest(text="我的deepseekapi额度还有多少", sender_id="peer-same", account_id="bot-1")
    handle_inbound(req)
    assert started.wait(timeout=2)

    duplicate = handle_inbound(req)
    gate.set()
    time.sleep(0.3)

    assert duplicate.reply == ""
    assert not any("处理中" in msg for msg in sent)
    assert any("额度查询结果" in msg for msg in sent)


def test_handle_inbound_busy_while_processing(tmp_appdata, monkeypatch):
    import threading

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    monkeypatch.setattr("friday.weixin.bridge.resolve_session_id", lambda *_a, **_k: "wx-session-1")

    gate = threading.Event()
    started = threading.Event()

    def slow_agent(**_k):
        started.set()
        gate.wait(timeout=2)
        return "done"

    monkeypatch.setattr("friday.weixin.bridge._run_agent", slow_agent)
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    worker = threading.Thread(
        target=lambda: handle_inbound(
            InboundRequest(text="第一个问题", sender_id="peer-busy", account_id="bot-1"),
        ),
    )
    worker.start()
    assert started.wait(timeout=2)

    result = handle_inbound(
        InboundRequest(text="第二个问题", sender_id="peer-busy", account_id="bot-1"),
    )
    gate.set()
    worker.join(timeout=3)

    assert result.reply == ""
    assert any("处理中" in msg for msg in sent)


def test_handle_inbound_bridge_disabled_replies(tmp_appdata, monkeypatch):
    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(weixin_bridge_enabled=False),
    )

    result = handle_inbound(
        InboundRequest(text="你好", sender_id="peer-123", account_id="bot-1"),
    )

    assert result.handled is True
    assert "桥接已关闭" in result.reply


def test_handle_inbound_ignores_duplicate_approval_after_resolve(tmp_appdata, monkeypatch):
    from concurrent.futures import Future

    import friday.weixin.bridge as bridge

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    future: Future[bool] = Future()
    bridge._approval_waiters["peer-approve"] = future

    first = handle_inbound(
        InboundRequest(text="同意", sender_id="peer-approve", account_id="bot-1"),
    )
    assert first.handled is True
    assert first.reply == ""
    assert future.result(timeout=1) is True
    assert sent == ["好的，已同意，继续执行。"]

    second = handle_inbound(
        InboundRequest(text="同意", sender_id="peer-approve", account_id="bot-1"),
    )
    assert second.handled is True
    assert second.reply == ""
    assert sent == ["好的，已同意，继续执行。"]


def test_handle_inbound_approval_unblocks_while_turn_lock_held(tmp_appdata, monkeypatch):
    from concurrent.futures import Future
    import threading

    import friday.weixin.bridge as bridge

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    peer = "peer-wait"
    lock = threading.Lock()
    lock.acquire()
    bridge._peer_processing_text[peer] = "继续发文件"
    bridge._processing_keys.add((peer, "继续发文件"))
    future: Future[bool] = Future()
    bridge._approval_waiters[peer] = future

    result = handle_inbound(
        InboundRequest(text="同意", sender_id=peer, account_id="bot-1"),
    )

    assert result.handled is True
    assert future.result(timeout=1) is True
    assert sent == ["好的，已同意，继续执行。"]


def test_handle_inbound_reports_orphan_approval(tmp_appdata, monkeypatch):
    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    result = handle_inbound(
        InboundRequest(text="同意", sender_id="peer-none", account_id="bot-1"),
    )

    assert result.handled is True
    assert result.reply == ""
    assert sent == ["当前没有待审批的操作。"]


def test_weixin_approval_gate_stops_followup_prompts(tmp_appdata, monkeypatch):
    from concurrent.futures import Future
    from threading import Thread

    import friday.weixin.bridge as bridge
    from friday.safety import PendingAction
    from friday.weixin.bridge import _make_weixin_approval_bridge

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )
    cancelled: list[bool] = []

    gate: dict[str, bool] = {"stop_prompts": False, "user_declined": False, "timed_out": False}
    approval = _make_weixin_approval_bridge(
        peer_id="peer-gate",
        account=_account(),
        approval_gate=gate,
        cancel_hook=lambda: cancelled.append(True),
    )
    action = PendingAction(
        tool_name="create_docx",
        arguments={"path": "文档.docx"},
        summary="创建 Word 文档",
        risk="medium",
    )

    worker = Thread(target=lambda: approval(action))
    worker.start()
    assert bridge._approval_waiters.get("peer-gate") is not None
    bridge._approval_waiters["peer-gate"].set_result(False)
    worker.join(timeout=2)

    assert gate["stop_prompts"] is True
    assert gate["user_declined"] is True
    assert cancelled == [True]
    assert len(sent) == 1
    assert "【需你确认】" in sent[0]

    second = approval(action)
    assert second is False
    assert len(sent) == 1


def test_handle_inbound_orphan_approval_hint_after_silent_window(tmp_appdata, monkeypatch):
    import time

    import friday.weixin.bridge as bridge

    monkeypatch.setattr(
        "friday.weixin.bridge.load_settings",
        lambda: UserSettings(
            api_key="sk-test-key-12345678",
            weixin_bridge_enabled=True,
        ),
    )
    monkeypatch.setattr("friday.weixin.bridge.resolve_account", lambda _aid: _account())
    sent: list[str] = []
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, text, **_k: sent.append(text),
    )

    bridge._recent_approval_inbound[("peer-hint", "同意")] = (
        time.monotonic() - bridge.APPROVAL_SILENT_DEDUPE_SEC - 5.0
    )

    result = handle_inbound(
        InboundRequest(text="同意", sender_id="peer-hint", account_id="bot-1"),
    )

    assert result.handled is True
    assert result.reply == ""
    assert sent == ["已收到，当前没有待审批的操作。"]
