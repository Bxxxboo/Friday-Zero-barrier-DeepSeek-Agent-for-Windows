"""主界面启动与基础交互 E2E。"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_boot_reaches_main_ui(page) -> None:
    assert page.locator("#appBootOverlay.hidden").count() == 1
    assert page.locator("#chatInput").is_visible()
    assert page.locator("#sendBtn").is_visible()
    assert page.locator("#sessionList").is_visible()


@pytest.mark.e2e
def test_new_chat_creates_session(page, dismiss_modals) -> None:
    before = page.locator(".session-item").count()
    dismiss_modals()
    page.locator("#newChatBtn").click()
    page.wait_for_timeout(400)
    after = page.locator(".session-item").count()
    assert after >= before + 1


@pytest.mark.e2e
def test_settings_modal_opens(page, open_settings, close_settings) -> None:
    open_settings("llm")
    assert page.locator("#panel-llm").is_visible()
    close_settings()
    assert not page.locator("#settingsModal").is_visible()
