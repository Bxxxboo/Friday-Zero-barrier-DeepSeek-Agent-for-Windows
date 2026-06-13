from __future__ import annotations

import json

from friday.credentials_store import (
    credentials_dir,
    load_api_secrets,
    migrate_secrets_from_settings_json_if_needed,
    secrets_path,
)
from friday.io_utils import load_json
from friday.storage import UserSettings, load_settings, save_settings


def test_api_secrets_saved_in_credentials_dir(tmp_appdata):
    original = UserSettings(api_key="sk-test-credentials-store-key")
    save_settings(original)
    assert secrets_path().is_file()
    assert (credentials_dir() / ".fernet_key").is_file()
    loaded = load_settings()
    assert loaded.api_key == "sk-test-credentials-store-key"


def test_empty_save_does_not_wipe_existing_key(tmp_appdata):
    save_settings(UserSettings(api_key="sk-preserve-me-please"))
    save_settings(UserSettings(api_key=""))
    loaded = load_settings()
    assert loaded.api_key == "sk-preserve-me-please"


def test_migrate_secrets_from_legacy_settings_json(tmp_appdata):
    from friday.storage import _encrypt_key

    settings_path = tmp_appdata / "settings.json"
    settings_path.write_text(
        json.dumps({"api_key": _encrypt_key("sk-migrated-from-settings"), "model": "deepseek-chat"}),
        encoding="utf-8",
    )
    assert migrate_secrets_from_settings_json_if_needed()
    assert secrets_path().is_file()
    secrets = load_api_secrets()
    assert secrets.get("api_key") == "sk-migrated-from-settings"
    loaded = load_settings()
    assert loaded.api_key == "sk-migrated-from-settings"


def test_save_replaces_existing_key_when_credentials_present(tmp_appdata):
    save_settings(UserSettings(api_key="sk-old-key-12345678"))
    save_settings(UserSettings(api_key="sk-new-mimo-key-12345678901234567890"))
    loaded = load_settings()
    assert loaded.api_key == "sk-new-mimo-key-12345678901234567890"


def test_merge_profile_maps_preserves_stored_model_and_url():
    from friday.credentials_store import _fill_empty_profile_keys

    incoming = {
        "ark": {"api_key": "", "base_url": "", "model": ""},
        "openai_compat": {"api_key": "sk-keep", "base_url": "", "model": ""},
    }
    stored = {
        "ark": {
            "api_key": "ark-secret-key-123456",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "ep-20260611011923-jdgm5",
        },
        "openai_compat": {
            "api_key": "sk-zhima-key-12345678",
            "base_url": "https://next.zhima.world",
            "model": "flux-schnell",
            "fallback_urls": "https://sg.zhima.world",
        },
    }
    merged = _fill_empty_profile_keys(incoming, stored)
    assert merged["ark"]["model"] == "ep-20260611011923-jdgm5"
    assert merged["ark"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
    assert merged["ark"]["api_key"] == "ark-secret-key-123456"
    assert merged["openai_compat"]["model"] == "flux-schnell"
    assert merged["openai_compat"]["fallback_urls"] == "https://sg.zhima.world"
    assert merged["openai_compat"]["api_key"] == "sk-keep"


def test_delete_custom_endpoint_persists_after_save(tmp_appdata):
    from friday.custom_endpoints import add_blank_endpoint, delete_custom_endpoint, upsert_endpoint
    from friday.storage import merge_settings

    settings = upsert_endpoint(
        UserSettings(),
        "llm",
        name="mimo-ultra-speed",
        api_key="sk-test-endpoint-a",
        base_url="https://api.example/v1",
        model="model-a",
        preserve_key_if_empty=False,
    )
    settings = add_blank_endpoint(settings, "llm", name="GPT")
    save_settings(settings)

    gpt_id = settings.llm_custom_endpoints[1]["id"]
    deleted = delete_custom_endpoint(load_settings(), "llm", gpt_id)
    save_settings(deleted)

    reloaded = load_settings()
    names = [e["name"] for e in reloaded.llm_custom_endpoints]
    assert names == ["mimo-ultra-speed"]


def test_merge_settings_delete_custom_endpoint_persists(tmp_appdata):
    from friday.custom_endpoints import add_blank_endpoint, upsert_endpoint
    from friday.storage import merge_settings

    settings = upsert_endpoint(
        UserSettings(),
        "llm",
        name="A",
        api_key="sk-test-endpoint-a",
        base_url="https://api.example/v1",
        model="model-a",
        preserve_key_if_empty=False,
    )
    settings = add_blank_endpoint(settings, "llm", name="B")
    save_settings(settings)

    gpt_id = settings.llm_custom_endpoints[1]["id"]
    merged = merge_settings(
        load_settings(),
        {
            "custom_endpoint_category": "llm",
            "delete_custom_endpoint": True,
            "custom_endpoint_id": gpt_id,
        },
    )
    save_settings(merged)

    reloaded = load_settings()
    assert len(reloaded.llm_custom_endpoints) == 1
    assert reloaded.llm_custom_endpoints[0]["name"] == "A"


def test_credentials_preferred_when_settings_decrypt_fails(tmp_appdata):
    save_settings(UserSettings(api_key="sk-authoritative-key"))
    raw = load_json(tmp_appdata / "settings.json")
    raw["api_key"] = "fernet:invalid-token"
    (tmp_appdata / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_settings()
    assert loaded.api_key == "sk-authoritative-key"
