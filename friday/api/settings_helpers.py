"""设置 API 的 merge / response 转换（供 settings 路由与测试连接使用）。"""

from __future__ import annotations

from friday.api.schemas import SettingsResponse
from friday.storage import UserSettings, load_settings, merge_settings, resolved_workspace


def merge_settings_payload(payload) -> UserSettings:
    from friday.llm_profiles import repair_llm_key_alignment

    current = load_settings()
    merged = merge_settings(current, payload.model_dump(exclude_unset=True))
    return repair_llm_key_alignment(merged)


def settings_to_response(cfg: UserSettings) -> SettingsResponse:
    from friday.category_profiles import category_profiles_summary
    from friday.custom_endpoints import active_provider_id as category_active_provider
    from friday.custom_endpoints import endpoints_summary, get_active_id
    from friday.image_gen import (
        default_base_url,
        image_gen_config_hint,
        image_gen_ready,
        masked_image_gen_key,
    )
    from friday.llm_profiles import active_provider_id, llm_config_hint, profiles_summary
    from friday.model_providers import infer_vision_provider
    from friday.portability import pop_startup_notices
    from friday.vision import masked_vision_key, vision_config_hint, vision_ready

    llm_provider = active_provider_id(cfg)
    vision_provider = category_active_provider(cfg, "vision") or infer_vision_provider(cfg)

    notices = pop_startup_notices()
    autostart = {}
    try:
        from friday.autostart import autostart_status

        autostart = autostart_status()
    except Exception:
        autostart = {"enabled": False, "available": False, "detail": ""}
    return SettingsResponse(
        api_key_masked=cfg.masked_key(),
        llm_provider=llm_provider,
        llm_profiles_summary=profiles_summary(cfg),
        vision_profiles_summary=category_profiles_summary(cfg, "vision"),
        image_gen_profiles_summary=category_profiles_summary(cfg, "image_gen"),
        llm_custom_endpoints=endpoints_summary(cfg, "llm"),
        llm_custom_active=get_active_id(cfg, "llm"),
        base_url=cfg.base_url,
        model=cfg.model,
        workspace=resolved_workspace(cfg),
        api_ready=cfg.api_ready,
        llm_status_hint=llm_config_hint(cfg),
        theme=cfg.theme,
        font_size=cfg.font_size,
        restrict_to_workspace=cfg.restrict_to_workspace,
        allow_read_user_folders=getattr(cfg, "allow_read_user_folders", True),
        require_approval_writes=cfg.require_approval_writes,
        require_approval_exec=cfg.require_approval_exec,
        allow_write_files=cfg.allow_write_files,
        allow_move_files=cfg.allow_move_files,
        allow_organize=cfg.allow_organize,
        allow_create_documents=cfg.allow_create_documents,
        allow_powershell=cfg.allow_powershell,
        allow_python=cfg.allow_python,
        allow_web_browse=cfg.allow_web_browse,
        allow_downloads=cfg.allow_downloads,
        require_trusted_downloads=cfg.require_trusted_downloads,
        auto_approve_scheduled_writes=cfg.auto_approve_scheduled_writes,
        approve_once_per_turn=cfg.approve_once_per_turn,
        interaction_mode=cfg.interaction_mode,
        ui_language=getattr(cfg, "ui_language", "zh") or "zh",
        vision_api_key_masked=masked_vision_key(cfg),
        vision_provider=vision_provider,
        vision_base_url=cfg.vision_base_url,
        vision_model=cfg.vision_model,
        vision_enabled=cfg.vision_enabled,
        vision_ready=vision_ready(cfg),
        vision_status_hint=vision_config_hint(cfg),
        vision_custom_endpoints=endpoints_summary(cfg, "vision"),
        vision_custom_active=get_active_id(cfg, "vision"),
        image_gen_api_key_masked=masked_image_gen_key(cfg),
        image_gen_provider=cfg.image_gen_provider or "openai_compat",
        image_gen_base_url=cfg.image_gen_base_url.strip() or default_base_url(cfg),
        image_gen_model=cfg.image_gen_model,
        image_gen_default_size=cfg.image_gen_default_size or "1024x1024",
        image_gen_fallback_urls=cfg.image_gen_fallback_urls,
        image_gen_save_dir=cfg.image_gen_save_dir,
        image_gen_enabled=cfg.image_gen_enabled,
        image_gen_ready=image_gen_ready(cfg),
        image_gen_status_hint=image_gen_config_hint(cfg),
        image_gen_custom_endpoints=endpoints_summary(cfg, "image_gen"),
        image_gen_custom_active=get_active_id(cfg, "image_gen"),
        weixin_bridge_enabled=getattr(cfg, "weixin_bridge_enabled", True),
        weixin_task_progress_enabled=getattr(cfg, "weixin_task_progress_enabled", True),
        weixin_deliver_files_enabled=getattr(cfg, "weixin_deliver_files_enabled", True),
        acknowledged_changelog_version=getattr(cfg, "acknowledged_changelog_version", "") or "",
        portability_notices=notices,
        launch_at_logon=bool(autostart.get("enabled")),
        launch_at_logon_available=bool(autostart.get("available")),
        launch_at_logon_detail=str(autostart.get("detail") or ""),
        api_proxy=getattr(cfg, "api_proxy", "") or "",
        api_trust_env=bool(getattr(cfg, "api_trust_env", True)),
        onboarding_completed=bool(getattr(cfg, "onboarding_completed", False)),
        artifact_scratch_ttl_hours=int(getattr(cfg, "artifact_scratch_ttl_hours", 24) or 24),
        artifact_session_ttl_days=int(getattr(cfg, "artifact_session_ttl_days", 30) or 30),
        artifact_trash_ttl_days=int(getattr(cfg, "artifact_trash_ttl_days", 7) or 7),
        artifact_session_delete_grace_days=int(getattr(cfg, "artifact_session_delete_grace_days", 7) or 7),
        artifact_auto_gc_enabled=bool(getattr(cfg, "artifact_auto_gc_enabled", True)),
        context_smart_enabled=bool(getattr(cfg, "context_smart_enabled", True)),
        goal_verifier_enabled=bool(getattr(cfg, "goal_verifier_enabled", True)),
        dream_memory_enabled=bool(getattr(cfg, "dream_memory_enabled", False)),
    )


# 兼容旧私有名（server 模块 re-export）
_merge_payload = merge_settings_payload
_to_response = settings_to_response
