from __future__ import annotations

from friday.weixin.bridge import _make_weixin_progress_handler
from friday.weixin.client import WeixinAccount
from friday.weixin.progress import collect_newly_completed_todos, format_weixin_task_progress
from friday.storage import UserSettings


def test_collect_newly_completed_todos():
    done = set()
    todos = [
        {"text": "整理下载夹", "done": True},
        {"text": "写汇总", "done": False},
    ]
    newly, updated = collect_newly_completed_todos(done, todos)
    assert newly == ["整理下载夹"]
    assert len(updated) == 1

    todos[1]["done"] = True
    newly2, _ = collect_newly_completed_todos(updated, todos)
    assert newly2 == ["写汇总"]


def test_format_weixin_task_progress_open_remaining():
    text = format_weixin_task_progress(
        ["整理下载夹"],
        [{"text": "整理下载夹", "done": True}, {"text": "写汇总", "done": False}],
    )
    assert "【进度】" in text
    assert "整理下载夹" in text
    assert "还剩 1 项" in text


def test_format_weixin_task_progress_all_done():
    text = format_weixin_task_progress(
        ["写汇总"],
        [{"text": "写汇总", "done": True}],
    )
    assert "待办已全部完成" in text


def test_progress_handler_sends_on_plan_updated(monkeypatch):
    sent: list[str] = []

    def fake_send(account, *, peer_id, text, fallback_token=""):
        sent.append(text)

    monkeypatch.setattr("friday.weixin.bridge.send_peer_text", fake_send)
    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=UserSettings(weixin_task_progress_enabled=True),
        initial_done_keys=set(),
    )
    handler("tool_start", {})
    handler(
        "plan_updated",
        {
            "ok": True,
            "todos": [
                {"text": "扫描桌面", "done": True},
                {"text": "清理下载", "done": False},
            ],
        },
    )
    assert len(sent) == 1
    assert "扫描桌面" in sent[0]
    assert "还剩 1 项" in sent[0]

    handler(
        "plan_updated",
        {
            "ok": True,
            "todos": [
                {"text": "扫描桌面", "done": True},
                {"text": "清理下载", "done": True},
            ],
        },
    )
    assert len(sent) == 2
    assert "待办已全部完成" in sent[1]


def test_progress_handler_respects_disabled_setting(monkeypatch):
    sent: list[str] = []

    def fake_send(account, *, peer_id, text, fallback_token=""):
        sent.append(text)

    monkeypatch.setattr("friday.weixin.bridge.send_peer_text", fake_send)
    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=UserSettings(weixin_task_progress_enabled=False),
        initial_done_keys=set(),
    )
    handler(
        "plan_updated",
        {"ok": True, "todos": [{"text": "扫描桌面", "done": True}]},
    )
    assert sent == []
