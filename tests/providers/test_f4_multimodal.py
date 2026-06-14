from __future__ import annotations

from friday.image_gen import format_generate_result
from friday.plugins import format_plugin_catalog, plugin_catalog
from friday.storage import UserSettings
from friday.task_runner import run_scheduled_prompt
from friday.tools.web import download_software


def test_format_generate_result_failure_category():
    text = format_generate_result({"ok": False, "error": "生图中转账户余额不足，请充值"})
    assert text.startswith("【生图失败·余额不足】")


def test_download_software_unknown_name(tmp_appdata, monkeypatch):
    monkeypatch.setattr("friday.tools.web._SOFTWARE_PAGES", {})
    text = download_software("未知软件XYZ", "E:/setup.exe")
    assert text.startswith("【下载失败·未收录】")


def test_plugin_catalog_capabilities():
    items = plugin_catalog()
    assert items
    assert all(item.get("capabilities") for item in items)
    text = format_plugin_catalog(force_refresh=True)
    assert "能做什么" in text


def test_run_scheduled_prompt_returns_session_id(tmp_appdata, monkeypatch):
    class FakeAgent:
        messages = []

        def __init__(self, settings, bridge):
            pass

        def run(self, text):
            return "整理完成"

    monkeypatch.setattr("friday.task_runner.FridayAgent", FakeAgent)
    monkeypatch.setattr("friday.task_runner.save_agent_state", lambda *a, **k: None)
    monkeypatch.setattr(
        "friday.task_runner.load_settings",
        lambda: UserSettings(api_key="sk-live-test-key-abcdef12", model="deepseek-chat"),
    )

    status, message, session_id = run_scheduled_prompt(
        "整理下载夹",
        session_title="[定时] 测试",
        schedule_id="sched-1",
    )
    assert status == "ok"
    assert message == "整理完成"
    assert session_id
