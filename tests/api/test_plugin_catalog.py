"""GET /api/plugins/catalog 推荐列表。"""

from fastapi.testclient import TestClient

import friday.server as server_mod
from friday.auth import ensure_api_token
from friday.plugins import plugin_catalog, resolve_plugin_source


def test_plugin_catalog_has_recommendations():
    catalog = plugin_catalog()
    assert len(catalog) >= 2
    ids = {item["id"] for item in catalog}
    assert "scipilot-figure-skill" in ids
    assert "karpathy-guidelines" in ids
    for item in catalog:
        assert item.get("name")
        assert item.get("source")
        assert item.get("description")


def test_resolve_plugin_source_catalog_ids():
    assert resolve_plugin_source("scipilot-figure-skill") == "local:scipilot-figure-skill"
    assert resolve_plugin_source("karpathy-guidelines") == "local:karpathy-guidelines"


def test_plugin_catalog_api(tmp_appdata):
    server_mod._backend_ready = True
    client = TestClient(server_mod.app)
    token = ensure_api_token()
    headers = {"X-Friday-Token": token}

    res = client.get("/api/plugins/catalog", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data.get("catalog"), list)
    assert len(data["catalog"]) >= 2
