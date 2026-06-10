"""Playwright UI E2E — 需: pip install -r requirements-dev.txt && playwright install chromium"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base: str, timeout: float = 30.0) -> None:
    url = f"{base}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("status") == "ok":
                    return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass
        time.sleep(0.1)
    raise RuntimeError(f"E2E server not ready: {base}")


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    playwright = pytest.importorskip("playwright")

    appdata_root = tmp_path_factory.mktemp("e2e_appdata")
    os.environ["APPDATA"] = str(appdata_root)
    friday_dir = appdata_root / "Friday"
    friday_dir.mkdir()
    workspace = friday_dir / "workspace"
    workspace.mkdir()
    settings = {
        "onboarding_completed": True,
        "workspace": str(workspace),
    }
    (friday_dir / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False),
        encoding="utf-8",
    )

    import uvicorn

    import friday.auth as auth
    import friday.server as server_mod
    from friday.version import __version__

    port = _free_port()
    os.environ["FRIDAY_TEST"] = "1"
    os.environ["FRIDAY_PORT"] = str(port)
    auth._TOKEN = ""
    token = auth.ensure_api_token()
    os.environ["FRIDAY_API_TOKEN"] = token
    auth.set_api_token(token)
    server_mod._backend_ready = False

    settings["acknowledged_changelog_version"] = __version__
    (friday_dir / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False),
        encoding="utf-8",
    )

    thread = threading.Thread(
        target=lambda: uvicorn.run(
            server_mod.app,
            host="127.0.0.1",
            port=port,
            log_level="error",
        ),
        daemon=True,
    )
    thread.start()

    base = f"http://127.0.0.1:{port}"
    _wait_health(base)

    # 确认 Playwright 浏览器可用（未 install 时给出明确 skip）
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"Playwright Chromium 不可用（运行 playwright install chromium）: {exc}"
        )

    del playwright
    yield {"base": base, "port": port, "token": token}


def _dismiss_blocking_modals(page) -> None:
    """关闭更新说明 / 引导等遮挡层，避免拦截点击。"""
    for modal_id, btn_id in (
        ("releaseNotesModal", "releaseNotesDismissBtn"),
        ("onboardingModal", "onboardingSkipWelcomeBtn"),
    ):
        modal = page.locator(f"#{modal_id}:not(.hidden)")
        if modal.count() == 0:
            continue
        btn = page.locator(f"#{btn_id}")
        if btn.count():
            btn.click()
            page.locator(f"#{modal_id}.hidden").wait_for(timeout=5000)
        else:
            page.evaluate(
                "(id) => document.getElementById(id)?.classList.add('hidden')",
                modal_id,
            )


@pytest.fixture(scope="module")
def page(e2e_server: dict[str, Any]):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="zh-CN")
        pg = context.new_page()
        pg.goto(e2e_server["base"])
        pg.wait_for_selector("html.app-ready", timeout=45000)
        pg.wait_for_timeout(1200)
        _dismiss_blocking_modals(pg)
        yield pg
        context.close()
        browser.close()


@pytest.fixture(scope="module")
def dismiss_modals(page):
    def _dismiss() -> None:
        _dismiss_blocking_modals(page)

    return _dismiss


@pytest.fixture(scope="module")
def close_settings(page):
    def _close() -> None:
        modal = page.locator("#settingsModal")
        if modal.is_visible():
            page.locator("#closeSettingsBtn").click()
            modal.wait_for(state="hidden", timeout=5000)

    return _close


@pytest.fixture(scope="module")
def open_settings(page, dismiss_modals):
    def _open(panel: str = "llm") -> None:
        dismiss_modals()
        modal = page.locator("#settingsModal")
        if not modal.is_visible():
            page.locator("#openSettingsBtn").click()
            modal.wait_for(state="visible", timeout=5000)
        if panel != "llm":
            page.locator(f'.settings-nav-item[data-panel="{panel}"]').click()

    return _open
