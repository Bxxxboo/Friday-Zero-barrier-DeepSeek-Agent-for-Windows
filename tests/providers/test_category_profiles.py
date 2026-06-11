"""视觉 / 生图服务商配置记忆测试。"""

from friday.category_profiles import (
    category_profiles_summary,
    persist_category_profile,
    switch_category_profile,
)
from friday.custom_endpoints import switch_category_provider
from friday.storage import UserSettings, merge_settings, save_settings, load_settings


def test_switch_image_gen_snapshots_and_restores_api(tmp_appdata):
    settings = UserSettings(
        image_gen_provider="ark",
        image_gen_api_key="ark-secret-key-123456",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_model="ep-20260609014727-895pn",
        image_gen_profiles={
            "openai_compat": {
                "api_key": "sk-zhima-key-12345678",
                "base_url": "https://next.zhima.world",
                "model": "flux-schnell",
                "fallback_urls": "https://crs.happycode.online",
            }
        },
    )
    save_settings(settings)

    switched = switch_category_provider(load_settings(), "image_gen", "openai_compat")
    assert switched.image_gen_api_key == "sk-zhima-key-12345678"
    assert "zhima" in switched.image_gen_base_url
    assert switched.image_gen_model == "flux-schnell"
    assert switched.image_gen_fallback_urls == "https://crs.happycode.online"
    assert switched.image_gen_profiles["ark"]["api_key"] == "ark-secret-key-123456"

    back = switch_category_provider(switched, "image_gen", "ark")
    assert back.image_gen_provider == "ark"
    assert back.image_gen_api_key == "ark-secret-key-123456"
    assert "volces" in back.image_gen_base_url
    assert back.image_gen_model == "ep-20260609014727-895pn"


def test_switch_image_gen_clears_foreign_key_when_unconfigured(tmp_appdata):
    settings = UserSettings(
        image_gen_provider="ark",
        image_gen_api_key="ark-only-key-123456",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_model="ep-20260609014727-895pn",
    )
    switched = switch_category_profile(settings, "image_gen", "openai_compat")
    assert switched.image_gen_provider == "openai_compat"
    assert switched.image_gen_api_key == ""
    assert switched.image_gen_model == ""


def test_switch_image_gen_preserves_ark_key_when_ark_profile_has_sk(tmp_appdata):
    settings = UserSettings(
        image_gen_provider="openai_compat",
        image_gen_api_key="ark-secret-key-123456",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_fallback_urls="https://crs.happycode.online",
        image_gen_profiles={
            "ark": {
                "api_key": "sk-stale-key-12345678",
                "base_url": "",
                "model": "",
            }
        },
    )
    switched = switch_category_profile(settings, "image_gen", "ark")
    assert switched.image_gen_provider == "ark"
    assert switched.image_gen_api_key == "ark-secret-key-123456"
    assert switched.image_gen_model == "ep-20260609235327-pf4mr"
    assert switched.image_gen_fallback_urls == "https://crs.happycode.online"


def test_repair_image_gen_key_mismatch_restores_ark_profile_key(tmp_appdata):
    from friday.category_profiles import repair_category_settings
    from friday.image_gen import image_gen_config_hint

    settings = UserSettings(
        image_gen_provider="ark",
        image_gen_api_key="sk-stale-key-12345678",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_model="ep-20260609235327-pf4mr",
        image_gen_profiles={
            "ark": {
                "api_key": "ark-secret-key-123456",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "ep-20260609235327-pf4mr",
            }
        },
    )
    repaired = repair_category_settings(settings, "image_gen")
    assert repaired.image_gen_api_key == "ark-secret-key-123456"
    assert image_gen_config_hint(repaired) == ""


def test_merge_settings_switch_image_gen_profile(tmp_appdata):
    settings = UserSettings(
        image_gen_provider="ark",
        image_gen_api_key="ark-key-12345678",
        image_gen_base_url="https://ark.cn-beijing.volces.com/api/v3",
        image_gen_model="ep-abc",
        image_gen_profiles={
            "openai_compat": {
                "api_key": "sk-compat-12345678",
                "base_url": "https://next.zhima.world",
                "model": "image2",
                "fallback_urls": "https://sg.zhima.world",
            }
        },
    )
    save_settings(settings)
    merged = merge_settings(
        load_settings(),
        {"image_gen_provider": "openai_compat", "switch_image_gen_profile": True},
    )
    assert merged.image_gen_api_key == "sk-compat-12345678"
    assert merged.image_gen_model == "image2"
    assert merged.image_gen_fallback_urls == "https://sg.zhima.world"


def test_category_profiles_summary_masks_keys(tmp_appdata):
    settings = UserSettings(
        image_gen_provider="ark",
        image_gen_profiles={
            "ark": {"api_key": "ark-secret-key-123456", "base_url": "https://ark.example", "model": "ep-1"},
        },
    )
    summary = category_profiles_summary(settings, "image_gen")
    assert summary["ark"]["configured"] is True
    assert "..." in str(summary["ark"]["api_key_masked"])


def test_repair_vision_ark_keeps_saved_relay_url(tmp_appdata):
    from friday.category_profiles import repair_category_settings

    settings = UserSettings(
        vision_provider="ark",
        vision_api_key="ark-secret-key-123456",
        vision_base_url="https://next.zhima.world/v1",
        vision_model="ep-20260609014727-895pn",
        vision_profiles={
            "ark": {
                "api_key": "ark-secret-key-123456",
                "base_url": "https://next.zhima.world/v1",
                "model": "ep-20260609014727-895pn",
            }
        },
    )
    repaired = repair_category_settings(settings, "vision")
    assert repaired.vision_base_url == "https://next.zhima.world/v1"
    assert repaired.vision_model == "ep-20260609014727-895pn"


def test_load_settings_restores_vision_model_from_credentials_profile(tmp_appdata):
    """settings.json 中 profile 模型被清空时，启动应从凭据库回填。"""
    import json

    from friday.io_utils import load_json

    settings = UserSettings(
        vision_enabled=True,
        vision_provider="ark",
        vision_api_key="ark-secret-key-123456",
        vision_base_url="https://ark.cn-beijing.volces.com/api/v3",
        vision_model="ep-20260611011923-jdgm5",
        vision_profiles={
            "ark": {
                "api_key": "ark-secret-key-123456",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "ep-20260611011923-jdgm5",
            }
        },
        image_gen_enabled=True,
        image_gen_provider="openai_compat",
        image_gen_api_key="sk-zhima-key-12345678",
        image_gen_base_url="https://next.zhima.world",
        image_gen_model="flux-schnell",
        image_gen_profiles={
            "openai_compat": {
                "api_key": "sk-zhima-key-12345678",
                "base_url": "https://next.zhima.world",
                "model": "flux-schnell",
            }
        },
    )
    save_settings(settings)
    raw = load_json(tmp_appdata / "settings.json")
    raw["vision_model"] = ""
    raw["vision_enabled"] = False
    profiles = raw.get("vision_profiles") or {}
    if "ark" in profiles:
        profiles["ark"]["model"] = ""
    raw["vision_profiles"] = profiles
    raw["image_gen_model"] = ""
    ig_profiles = raw.get("image_gen_profiles") or {}
    if "openai_compat" in ig_profiles:
        ig_profiles["openai_compat"]["model"] = ""
    raw["image_gen_profiles"] = ig_profiles
    (tmp_appdata / "settings.json").write_text(json.dumps(raw), encoding="utf-8")

    loaded = load_settings()
    assert loaded.vision_model == "ep-20260611011923-jdgm5"
    assert loaded.image_gen_model == "flux-schnell"
    assert loaded.vision_profiles["ark"]["model"] == "ep-20260611011923-jdgm5"


def test_load_settings_preserves_vision_relay_after_restart(tmp_appdata):
    settings = UserSettings(
        vision_enabled=True,
        vision_provider="ark",
        vision_api_key="ark-secret-key-123456",
        vision_base_url="https://next.zhima.world/v1",
        vision_model="ep-20260609014727-895pn",
        image_gen_enabled=True,
        image_gen_provider="openai_compat",
        image_gen_api_key="sk-zhima-key-12345678",
        image_gen_base_url="https://next.zhima.world",
        image_gen_model="flux-schnell",
        image_gen_profiles={
            "openai_compat": {
                "api_key": "sk-zhima-key-12345678",
                "base_url": "https://next.zhima.world",
                "model": "flux-schnell",
            }
        },
    )
    save_settings(settings)
    loaded = load_settings()
    assert loaded.vision_base_url == "https://next.zhima.world/v1"
    assert loaded.vision_model == "ep-20260609014727-895pn"
    assert loaded.image_gen_base_url == "https://next.zhima.world"
    assert loaded.image_gen_model == "flux-schnell"


def test_merge_settings_preserves_empty_vision_and_image_gen_fields(tmp_appdata):
    settings = UserSettings(
        vision_enabled=True,
        vision_provider="ark",
        vision_api_key="ark-secret-key-123456",
        vision_base_url="https://next.zhima.world/v1",
        vision_model="ep-keep-me",
        image_gen_enabled=True,
        image_gen_provider="openai_compat",
        image_gen_api_key="sk-zhima-key-12345678",
        image_gen_base_url="https://next.zhima.world",
        image_gen_model="flux-keep-me",
        image_gen_fallback_urls="https://sg.zhima.world",
    )
    save_settings(settings)
    merged = merge_settings(
        load_settings(),
        {
            "vision_api_key": "",
            "vision_base_url": "",
            "vision_model": "",
            "image_gen_api_key": "",
            "image_gen_base_url": "",
            "image_gen_model": "",
            "image_gen_fallback_urls": "",
        },
    )
    assert merged.vision_base_url == "https://next.zhima.world/v1"
    assert merged.vision_model == "ep-keep-me"
    assert merged.image_gen_base_url == "https://next.zhima.world"
    assert merged.image_gen_model == "flux-keep-me"
    assert merged.image_gen_fallback_urls == "https://sg.zhima.world"


def test_repair_image_gen_openai_compat_with_mimo_url(tmp_appdata):
    from friday.category_profiles import repair_category_settings

    settings = UserSettings(
        image_gen_provider="openai_compat",
        image_gen_base_url="https://api.xiaomimimo.com/v1",
        image_gen_model="image2",
        image_gen_api_key="sk-zhima-key-12345678",
        image_gen_profiles={
            "openai_compat": {
                "api_key": "sk-zhima-key-12345678",
                "base_url": "https://next.zhima.world",
                "model": "image2",
            }
        },
    )
    repaired = repair_category_settings(settings, "image_gen")
    assert "zhima" in repaired.image_gen_base_url
    assert repaired.image_gen_model == "image2"
    assert repaired.image_gen_api_key == "sk-zhima-key-12345678"


def test_delete_custom_vision_restores_ark_profile(tmp_appdata):
    from friday.custom_endpoints import delete_custom_endpoint, upsert_endpoint

    settings = upsert_endpoint(
        UserSettings(
            vision_provider="ark",
            vision_api_key="ark-real-key-12345678",
            vision_base_url="https://ark.cn-beijing.volces.com/api/v3",
            vision_model="ep-20260609014727-895pn",
            vision_profiles={
                "ark": {
                    "api_key": "ark-real-key-12345678",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "model": "ep-20260609014727-895pn",
                }
            },
        ),
        "vision",
        name="自定义视觉",
        api_key="sk-custom-vision-key123",
        base_url="https://relay.example.com/v1",
        model="gpt-4o",
        preserve_key_if_empty=False,
    )
    assert settings.vision_provider.startswith("c:")
    eid = settings.vision_provider.split(":", 1)[1]

    deleted = delete_custom_endpoint(settings, "vision", eid)
    assert deleted.vision_provider == "ark"
    assert deleted.vision_api_key == "ark-real-key-12345678"
    assert "volces" in deleted.vision_base_url
    assert deleted.vision_model == "ep-20260609014727-895pn"
    assert deleted.vision_profiles["ark"]["api_key"] == "ark-real-key-12345678"


def test_repair_vision_ark_restores_key_from_profile(tmp_appdata):
    from friday.category_profiles import repair_category_settings

    settings = UserSettings(
        vision_provider="ark",
        vision_api_key="sk-polluted-from-custom",
        vision_base_url="https://ark.cn-beijing.volces.com/api/v3",
        vision_model="",
        vision_profiles={
            "ark": {
                "api_key": "ark-saved-key-12345678",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": "ep-20260609014727-895pn",
            }
        },
    )
    repaired = repair_category_settings(settings, "vision")
    assert repaired.vision_api_key == "ark-saved-key-12345678"
    assert repaired.vision_model == "ep-20260609014727-895pn"


def test_delete_custom_llm_restores_vision_after_mimo(tmp_appdata):
    from friday.custom_endpoints import delete_custom_endpoint, upsert_endpoint

    settings = upsert_endpoint(
        UserSettings(
            llm_provider="mimo",
            api_key="mimo-key-12345678",
            base_url="https://api.xiaomimimo.com/v1",
            model="mimo-v2-flash",
            vision_provider="ark",
            vision_api_key="ark-vision-key-12345678",
            vision_base_url="https://ark.cn-beijing.volces.com/api/v3",
            vision_model="ep-20260609014727-895pn",
            vision_profiles={
                "ark": {
                    "api_key": "ark-vision-key-12345678",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "model": "ep-20260609014727-895pn",
                }
            },
        ),
        "llm",
        name="小米自定义",
        api_key="mimo-custom-key123456",
        base_url="https://api.xiaomimimo.com/v1",
        model="mimo-v2-flash",
        preserve_key_if_empty=False,
    )
    eid = settings.llm_provider.split(":", 1)[1]
    deleted = delete_custom_endpoint(settings, "llm", eid)
    assert deleted.llm_provider == "deepseek"
    assert deleted.vision_provider == "ark"
    assert deleted.vision_api_key == "ark-vision-key-12345678"
    assert deleted.vision_profiles["ark"]["api_key"] == "ark-vision-key-12345678"


def test_delete_custom_llm_does_not_touch_image_gen(tmp_appdata):
    from friday.custom_endpoints import delete_custom_endpoint, upsert_endpoint

    settings = upsert_endpoint(
        UserSettings(
            image_gen_provider="openai_compat",
            image_gen_base_url="https://next.zhima.world",
            image_gen_model="image2",
            image_gen_api_key="sk-zhima-key-12345678",
        ),
        "llm",
        name="小米自定义",
        api_key="mimo-key-12345678",
        base_url="https://api.xiaomimimo.com/v1",
        model="mimo-v2-flash",
        preserve_key_if_empty=False,
    )
    eid = settings.llm_provider.split(":", 1)[1]
    deleted = delete_custom_endpoint(settings, "llm", eid)
    assert deleted.image_gen_base_url == "https://next.zhima.world"
    assert deleted.image_gen_model == "image2"
    assert deleted.llm_provider == "deepseek"
