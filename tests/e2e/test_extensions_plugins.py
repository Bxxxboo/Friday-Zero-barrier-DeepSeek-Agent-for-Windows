"""设置 → 扩展 → 插件 catalog E2E。"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_plugin_catalog_shows_recommendations(page, open_settings, close_settings) -> None:
    open_settings("extensions")
    page.locator('[data-ext-tab="plugins"]').click()
    page.locator(".plugin-catalog-row").first.wait_for(timeout=8000)

    rows = page.locator(".plugin-catalog-row")
    assert rows.count() >= 2

    names = rows.locator("strong").all_text_contents()
    assert any("SciPilot" in n for n in names)
    assert any("Karpathy" in n for n in names)

    install_btns = page.locator(".plugin-install-btn")
    assert install_btns.count() >= 2
    close_settings()


@pytest.mark.e2e
def test_install_local_plugin_from_catalog(page, open_settings, close_settings) -> None:
    open_settings("extensions")
    page.locator('[data-ext-tab="plugins"]').click()
    page.locator(".plugin-catalog-row").first.wait_for(timeout=8000)

    row = page.locator(".plugin-catalog-row", has_text="Karpathy")
    row.locator(".plugin-install-btn").click()

    result_el = page.locator("#pluginResult.settings-result.ok")
    result_el.filter(has_text="已安装").wait_for(timeout=20000)
    result = result_el.inner_text()
    assert "已安装" in result

    row.locator(".plugin-installed-badge").wait_for(timeout=5000)
    assert page.locator("#pluginList .plugin-card", has_text="Karpathy").count() >= 1
    close_settings()
