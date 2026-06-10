"""视觉 / 生图服务商配置记忆 —— 按 provider 分别保存 Key / URL / 模型。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from friday.custom_endpoints import (
    Category as EndpointCategory,
    _DEFAULT_BUILTIN,
    _cfg,
    active_provider_id,
    endpoint_id_from_provider,
    find_endpoint,
    get_endpoints,
    is_custom_provider_id,
    snapshot_from_active,
    switch_custom_endpoint,
    upsert_endpoint,
)
from friday.storage import UserSettings

Category = Literal["vision", "image_gen"]


def _profiles_field(category: Category) -> str:
    return "vision_profiles" if category == "vision" else "image_gen_profiles"


def normalize_category_profiles(
    settings: UserSettings,
    category: Category,
    raw: Any = None,
) -> dict[str, dict[str, str]]:
    field = _profiles_field(category)
    data = raw if raw is not None else getattr(settings, field, None)
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for provider_id, entry in data.items():
        if not isinstance(entry, dict):
            continue
        pid = str(provider_id or "").strip()
        if not pid or is_custom_provider_id(pid):
            continue
        normalized = {
            "api_key": str(entry.get("api_key") or ""),
            "base_url": str(entry.get("base_url") or "").strip(),
            "model": str(entry.get("model") or "").strip(),
        }
        if category == "image_gen":
            normalized["fallback_urls"] = str(entry.get("fallback_urls") or "").strip()
            normalized["default_size"] = str(entry.get("default_size") or "").strip()
        out[pid] = normalized
    return out


def snapshot_category_profile(
    settings: UserSettings,
    category: Category,
    *,
    provider_id: str | None = None,
    profiles: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    pid = (provider_id or active_provider_id(settings, category)).strip()
    if not pid or is_custom_provider_id(pid):
        return normalize_category_profiles(settings, category, profiles)
    store = deepcopy(profiles if profiles is not None else normalize_category_profiles(settings, category))
    snap = snapshot_from_active(settings, category)
    entry = {
        "api_key": snap["api_key"],
        "base_url": snap["base_url"],
        "model": snap["model"],
    }
    if category == "image_gen":
        entry["fallback_urls"] = snap.get("fallback_urls", "")
        entry["default_size"] = (settings.image_gen_default_size or "").strip()
    store[pid] = entry
    return store


def _default_model(category: Category, provider_id: str) -> str:
    if category == "vision":
        from friday.model_providers import default_vision_model

        return default_vision_model(provider_id)
    from friday.model_providers import default_image_gen_model

    return default_image_gen_model(provider_id)


def _normalize_model(category: Category, provider_id: str, model: str) -> str:
    if category == "vision":
        from friday.model_providers import normalize_vision_model

        return normalize_vision_model(provider_id, model)
    from friday.model_providers import normalize_image_gen_model

    return normalize_image_gen_model(provider_id, model)


def _preset_default_base_url(category: Category, provider_id: str) -> str:
    if category == "vision":
        from friday.model_providers import get_vision_provider

        return (get_vision_provider(provider_id).default_base_url or "").strip()
    from friday.model_providers import get_image_gen_provider

    return (get_image_gen_provider(provider_id).default_base_url or "").strip()


def _resolve_profile_api_key(
    category: Category,
    provider_id: str,
    current_key: str,
    saved_key: str,
) -> str:
    """切换服务商时避免把旧 profile 里格式不匹配的 Key 覆盖掉当前可用 Key。"""
    current = (current_key or "").strip()
    saved = (saved_key or "").strip()
    if category in ("vision", "image_gen") and provider_id == "ark":
        if not saved:
            return current
        if not current:
            return saved
        if saved.startswith("sk-") and current.startswith("ark-"):
            return current
        if current.startswith("sk-") and saved.startswith("ark-"):
            return saved
        return saved
    return saved


def switch_category_profile(
    settings: UserSettings,
    category: EndpointCategory,
    new_provider_id: str,
) -> UserSettings:
    c = _cfg(category)
    old_id = active_provider_id(settings, category)
    new_id = (new_provider_id or "").strip() or _DEFAULT_BUILTIN[category]
    profiles = normalize_category_profiles(settings, category)

    if old_id != new_id and is_custom_provider_id(old_id):
        old_eid = endpoint_id_from_provider(old_id)
        if old_eid and find_endpoint(get_endpoints(settings, category), old_eid):
            settings = upsert_endpoint(settings, category, endpoint_id=old_eid, preserve_key_if_empty=True)
    elif old_id and old_id not in {"", "custom"} and old_id != new_id:
        profiles = snapshot_category_profile(settings, category, provider_id=old_id, profiles=profiles)

    if is_custom_provider_id(new_id):
        eid = endpoint_id_from_provider(new_id)
        if eid:
            settings = switch_custom_endpoint(settings, category, eid)
        return settings.merge({c["provider"]: new_id, _profiles_field(category): profiles})

    saved = profiles.get(new_id) or {}
    current_key = str(getattr(settings, c["api_key"], "") or "").strip()
    current_base = str(getattr(settings, c["base_url"], "") or "").strip()
    current_model = str(getattr(settings, c["model"], "") or "").strip()
    switching_builtin = old_id != new_id and not is_custom_provider_id(new_id)
    if switching_builtin:
        resolved_key = _resolve_profile_api_key(
            category,
            new_id,
            current_key,
            str(saved.get("api_key") or ""),
        )
        if (
            not saved.get("api_key")
            and new_id not in ("ark",)
            and resolved_key == current_key
            and current_key
        ):
            resolved_key = ""
        base_url = (saved.get("base_url") or _preset_default_base_url(category, new_id)).strip()
        model = _normalize_model(
            category,
            new_id,
            (saved.get("model") or current_model or _default_model(category, new_id)).strip(),
        )
    else:
        resolved_key = _resolve_profile_api_key(
            category,
            new_id,
            current_key,
            str(saved.get("api_key") or ""),
        )
        base_url = (saved.get("base_url") or current_base or _preset_default_base_url(category, new_id)).strip()
        model = _normalize_model(
            category,
            new_id,
            (saved.get("model") or current_model or _default_model(category, new_id)).strip(),
        )
    patch: dict[str, Any] = {
        c["provider"]: new_id,
        c["api_key"]: resolved_key,
        c["base_url"]: base_url,
        c["model"]: model,
        _profiles_field(category): profiles,
    }
    if category == "image_gen":
        current_fallback = (settings.image_gen_fallback_urls or "").strip()
        patch["image_gen_fallback_urls"] = saved.get("fallback_urls") or current_fallback or ""

    return settings.merge(patch)


def persist_category_profile(settings: UserSettings, category: Category) -> UserSettings:
    pid = active_provider_id(settings, category)
    if is_custom_provider_id(pid):
        eid = endpoint_id_from_provider(pid)
        return upsert_endpoint(settings, category, endpoint_id=eid or "", preserve_key_if_empty=True)
    profiles = snapshot_category_profile(settings, category, provider_id=pid)
    return settings.merge({_profiles_field(category): profiles})


def seed_category_profiles_from_active(settings: UserSettings, category: Category) -> UserSettings:
    profiles = normalize_category_profiles(settings, category)
    if profiles:
        return settings
    pid = active_provider_id(settings, category)
    if is_custom_provider_id(pid):
        return settings.merge({_profiles_field(category): {}})
    cfg = _cfg(category)
    if not getattr(settings, cfg["api_key"]).strip() and not getattr(settings, cfg["base_url"]).strip():
        return settings.merge({_profiles_field(category): {}})
    return settings.merge(
        {_profiles_field(category): snapshot_category_profile(settings, category, provider_id=pid, profiles={})}
    )


def category_profiles_summary(settings: UserSettings, category: Category) -> dict[str, dict[str, object]]:
    from friday.llm_profiles import masked_profile_key

    profiles = normalize_category_profiles(settings, category)
    active = active_provider_id(settings, category)
    out: dict[str, dict[str, object]] = {}
    for pid, entry in profiles.items():
        key = (entry.get("api_key") or "").strip()
        item: dict[str, object] = {
            "configured": bool(key),
            "api_key_masked": masked_profile_key(key),
            "base_url": entry.get("base_url") or "",
            "model": entry.get("model") or "",
            "active": pid == active,
        }
        if category == "image_gen":
            item["fallback_urls"] = entry.get("fallback_urls") or ""
            item["default_size"] = entry.get("default_size") or ""
        out[pid] = item
    return out


def _url_host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _provider_url_allowed(category: Category, provider_id: str, base_url: str) -> bool:
    from friday.custom_endpoints import is_custom_provider_id

    if is_custom_provider_id(provider_id):
        return True
    host = _url_host(base_url)
    if not host:
        return True
    if category == "image_gen":
        if provider_id == "openai_compat":
            return "xiaomimimo" not in host
        if provider_id == "mimo":
            return "xiaomimimo" in host or "mimo" in host
        if provider_id == "ark":
            return "volces" in host or "ark" in host
        if provider_id == "openai":
            return "openai.com" in host
        if provider_id == "siliconflow":
            return "siliconflow" in host
        if provider_id == "qwen":
            return "dashscope" in host or "aliyuncs" in host
    if category == "vision":
        if provider_id == "mimo":
            return "xiaomimimo" in host or "mimo" in host
        if provider_id == "ark":
            return "volces" in host or "ark" in host
    return True


def repair_category_settings(settings: UserSettings, category: Category) -> UserSettings:
    """修正当前服务商与 URL/模型不匹配的配置（避免 LLM/视觉/生图串台）。"""
    from friday.custom_endpoints import is_custom_provider_id

    cfg = _cfg(category)
    provider = active_provider_id(settings, category)
    if is_custom_provider_id(provider):
        return settings

    base_url = str(getattr(settings, cfg["base_url"], "") or "").strip()
    model = str(getattr(settings, cfg["model"], "") or "").strip()
    current_key = str(getattr(settings, cfg["api_key"], "") or "").strip()

    profiles = normalize_category_profiles(settings, category)
    saved = profiles.get(provider) or {}
    saved_url = str(saved.get("base_url") or "").strip()
    saved_model = str(saved.get("model") or "").strip()
    saved_key = str(saved.get("api_key") or "").strip()

    url_mismatch = not _provider_url_allowed(category, provider, base_url)
    model_mismatch = category == "image_gen" and model.startswith("mimo-") and provider != "mimo"
    key_mismatch = (
        category in ("vision", "image_gen")
        and provider == "ark"
        and current_key.startswith("sk-")
        and saved_key.startswith("ark-")
    )
    if not (url_mismatch or model_mismatch or key_mismatch):
        return settings

    if saved_url and _provider_url_allowed(category, provider, saved_url):
        repair_url = saved_url
    else:
        repair_url = _preset_default_base_url(category, provider)

    if category == "image_gen":
        from friday.model_providers import normalize_image_gen_model

        repair_model = normalize_image_gen_model(provider, saved_model or model)
    else:
        from friday.model_providers import normalize_vision_model

        repair_model = normalize_vision_model(provider, saved_model or model)

    patch: dict[str, Any] = {
        cfg["base_url"]: repair_url,
        cfg["model"]: repair_model,
    }
    if category in ("vision", "image_gen") and provider == "ark":
        if current_key.startswith("sk-") and saved_key.startswith("ark-"):
            patch[cfg["api_key"]] = saved_key
        elif not current_key and saved_key:
            patch[cfg["api_key"]] = saved_key
    elif saved_key:
        patch[cfg["api_key"]] = saved_key

    repaired = settings.merge(patch)
    profiles = snapshot_category_profile(repaired, category, provider_id=provider, profiles=profiles)
    if saved_url and not _provider_url_allowed(category, provider, saved_url):
        entry = dict(profiles.get(provider) or {})
        entry["base_url"] = repair_url
        entry["model"] = repair_model
        profiles[provider] = entry
    return repaired.merge({_profiles_field(category): profiles})


def repair_isolated_category_settings(settings: UserSettings) -> UserSettings:
    updated = repair_category_settings(settings, "vision")
    updated = repair_category_settings(updated, "image_gen")
    return updated


def merge_category_settings(current: UserSettings, payload: dict, category: Category) -> UserSettings | None:
    cfg = _cfg(category)
    switch_flag = "switch_vision_profile" if category == "vision" else "switch_image_gen_profile"
    provider_field = cfg["provider"]
    if payload.get(switch_flag) and payload.get(provider_field):
        return switch_category_profile(current, category, str(payload[provider_field]))
    new_provider = str(payload.get(provider_field) or "").strip()
    old_provider = active_provider_id(current, category)
    api_key_field = cfg["api_key"]
    explicit_key = api_key_field in payload and str(payload.get(api_key_field) or "").strip()
    if new_provider and new_provider != old_provider and not explicit_key:
        return switch_category_profile(current, category, new_provider)
    return None
