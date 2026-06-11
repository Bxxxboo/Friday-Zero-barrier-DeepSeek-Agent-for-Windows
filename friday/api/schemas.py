"""FastAPI 请求与响应模型（从 server.py 拆出，便于浏览路由逻辑）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# --- 设置 / 诊断 ---


class SettingsPayload(BaseModel):
    api_key: str = ""
    llm_provider: str = ""
    switch_llm_profile: bool | None = None
    base_url: str = ""
    model: str = ""
    workspace: str = ""
    theme: str = ""
    font_size: str = ""
    restrict_to_workspace: bool | None = None
    allow_read_user_folders: bool | None = None
    require_approval_writes: bool | None = None
    require_approval_exec: bool | None = None
    allow_write_files: bool | None = None
    allow_move_files: bool | None = None
    allow_organize: bool | None = None
    allow_create_documents: bool | None = None
    allow_powershell: bool | None = None
    allow_python: bool | None = None
    allow_web_browse: bool | None = None
    allow_downloads: bool | None = None
    require_trusted_downloads: bool | None = None
    auto_approve_scheduled_writes: bool | None = None
    approve_once_per_turn: bool | None = None
    interaction_mode: str | None = None
    ui_language: str | None = None
    vision_api_key: str = ""
    vision_provider: str = ""
    vision_base_url: str = ""
    vision_model: str = ""
    vision_enabled: bool | None = None
    image_gen_enabled: bool | None = None
    image_gen_provider: str = ""
    image_gen_api_key: str = ""
    image_gen_base_url: str = ""
    image_gen_model: str = ""
    image_gen_default_size: str = ""
    image_gen_fallback_urls: str = ""
    image_gen_save_dir: str = ""
    weixin_bridge_enabled: bool | None = None
    acknowledged_changelog_version: str | None = None
    api_proxy: str = ""
    api_trust_env: bool | None = None
    custom_endpoint_category: str = ""
    custom_endpoint_id: str = ""
    custom_endpoint_name: str = ""
    switch_custom_endpoint: bool | None = None
    add_custom_endpoint: bool | None = None
    delete_custom_endpoint: bool | None = None
    switch_vision_profile: bool | None = None
    switch_image_gen_profile: bool | None = None
    onboarding_completed: bool | None = None
    artifact_scratch_ttl_hours: int | None = None
    artifact_session_ttl_days: int | None = None
    artifact_trash_ttl_days: int | None = None
    artifact_session_delete_grace_days: int | None = None
    artifact_auto_gc_enabled: bool | None = None


class SettingsResponse(BaseModel):
    api_key_masked: str
    llm_provider: str = "deepseek"
    llm_profiles_summary: dict[str, dict[str, object]] = {}
    vision_profiles_summary: dict[str, dict[str, object]] = {}
    image_gen_profiles_summary: dict[str, dict[str, object]] = {}
    llm_custom_endpoints: list[dict[str, object]] = []
    llm_custom_active: str = ""
    base_url: str
    model: str
    workspace: str
    api_ready: bool
    llm_status_hint: str = ""
    theme: str
    font_size: str
    restrict_to_workspace: bool
    allow_read_user_folders: bool = True
    require_approval_writes: bool
    require_approval_exec: bool
    allow_write_files: bool
    allow_move_files: bool
    allow_organize: bool
    allow_create_documents: bool
    allow_powershell: bool
    allow_python: bool
    allow_web_browse: bool
    allow_downloads: bool
    require_trusted_downloads: bool
    auto_approve_scheduled_writes: bool
    approve_once_per_turn: bool
    interaction_mode: str
    ui_language: str = "zh"
    vision_api_key_masked: str
    vision_provider: str = "ark"
    vision_base_url: str
    vision_model: str
    vision_enabled: bool
    vision_ready: bool
    vision_status_hint: str = ""
    vision_custom_endpoints: list[dict[str, object]] = []
    vision_custom_active: str = ""
    image_gen_api_key_masked: str
    image_gen_provider: str
    image_gen_base_url: str
    image_gen_model: str
    image_gen_default_size: str
    image_gen_fallback_urls: str
    image_gen_save_dir: str
    image_gen_enabled: bool
    image_gen_ready: bool
    image_gen_status_hint: str = ""
    image_gen_custom_endpoints: list[dict[str, object]] = []
    image_gen_custom_active: str = ""
    weixin_bridge_enabled: bool = True
    acknowledged_changelog_version: str = ""
    portability_notices: list[str] = []
    launch_at_logon: bool = False
    launch_at_logon_available: bool = False
    launch_at_logon_detail: str = ""
    api_proxy: str = ""
    api_trust_env: bool = True
    onboarding_completed: bool = False
    artifact_scratch_ttl_hours: int = 24
    artifact_session_ttl_days: int = 30
    artifact_trash_ttl_days: int = 7
    artifact_session_delete_grace_days: int = 7
    artifact_auto_gc_enabled: bool = True


class TestResponse(BaseModel):
    ok: bool
    message: str
    code: str = ""
    hint: str = ""


class DiagnoseResponse(BaseModel):
    llm: dict[str, object]
    vision: dict[str, object]
    image_gen: dict[str, object]


class AutostartPayload(BaseModel):
    enabled: bool


class DiagnosticsLogsResponse(BaseModel):
    path: str
    lines: list[str]


class PortableExportPayload(BaseModel):
    include_sessions: bool = False


class PortableImportPayload(BaseModel):
    zip_base64: str = ""
    filename: str = "Friday-portable.zip"


# --- 对话 / 会话 ---


class ChatPayload(BaseModel):
    message: str = ""
    session_id: str = ""
    image_path: str = ""


class PasteImagePayload(BaseModel):
    image_base64: str = ""
    data_url: str = ""
    mime_type: str = "image/png"


class PasteImageResponse(BaseModel):
    path: str
    filename: str


class ApprovalPayload(BaseModel):
    approval_id: str
    approved: bool


class CancelPayload(BaseModel):
    session_id: str = ""


class YoloUnlockPayload(BaseModel):
    session_id: str = ""


class SessionCreatePayload(BaseModel):
    title: str = "新对话"


class SessionRenamePayload(BaseModel):
    title: str = ""


class LocalStorageMigrationPayload(BaseModel):
    sessions: list[dict[str, Any]] = []
    active_session_id: str = ""


class SessionSummaryResponse(BaseModel):
    id: str
    title: str
    updated_at: float
    created_at: float
    is_weixin: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionSummaryResponse]
    active_session_id: str


class GeneratedImageRef(BaseModel):
    path: str


class DisplayMessageResponse(BaseModel):
    role: str
    content: str
    generated_images: list[GeneratedImageRef] = []


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    updated_at: float
    created_at: float
    messages: list[DisplayMessageResponse]
    plan_markdown: str = ""
    todos: list[dict[str, Any]] = []


class SessionPlanPayload(BaseModel):
    plan_markdown: str | None = None
    todos: list[dict[str, Any]] | None = None


# --- 操作历史 / 定时任务 ---


class OperationResponse(BaseModel):
    id: str
    ts: float
    tool: str
    risk: str
    summary: str
    args: dict[str, Any]
    result: str
    success: bool
    session_id: str
    trigger: str
    schedule_id: str
    approved: bool | None = None


class OperationListResponse(BaseModel):
    operations: list[OperationResponse]


class SchedulePayload(BaseModel):
    title: str = ""
    prompt: str = ""
    frequency: str = "weekly"
    day_of_week: int = 4
    hour: int = 9
    minute: int = 0
    cron_expr: str = ""
    interval_hours: int = 6
    enabled: bool = True
    retry_on_failure: bool = True
    max_retries: int = 1


class ScheduleUpdatePayload(BaseModel):
    title: str | None = None
    prompt: str | None = None
    frequency: str | None = None
    day_of_week: int | None = None
    hour: int | None = None
    minute: int | None = None
    cron_expr: str | None = None
    interval_hours: int | None = None
    enabled: bool | None = None
    retry_on_failure: bool | None = None
    max_retries: int | None = None


class ScheduleResponse(BaseModel):
    id: str
    title: str
    prompt: str
    frequency: str
    day_of_week: int
    hour: int
    minute: int
    cron_expr: str
    interval_hours: int
    enabled: bool
    retry_on_failure: bool
    max_retries: int
    retry_count: int
    schedule_label: str
    last_run_at: float | None
    next_run_at: float | None
    last_run_status: str
    last_run_message: str
    created_at: float


class ScheduleListResponse(BaseModel):
    schedules: list[ScheduleResponse]


# --- 技能 / 规则 / 插件 ---


class SkillPayload(BaseModel):
    label: str = ""
    icon: str = "✨"
    category: str = "custom"
    prompt: str = ""


class SkillUpdatePayload(BaseModel):
    label: str | None = None
    icon: str | None = None
    category: str | None = None
    prompt: str | None = None
    enabled: bool | None = None


class SkillResponse(BaseModel):
    id: str
    label: str
    icon: str
    category: str
    prompt: str
    builtin: bool
    enabled: bool
    source: str
    plugin_id: str
    created_at: float


class SkillGroupResponse(BaseModel):
    category: str
    label: str
    skills: list[SkillResponse]


class RulePayload(BaseModel):
    title: str = ""
    content: str = ""
    enabled: bool = True
    always_apply: bool = True


class RuleUpdatePayload(BaseModel):
    title: str | None = None
    content: str | None = None
    enabled: bool | None = None
    always_apply: bool | None = None


class RuleResponse(BaseModel):
    id: str
    title: str
    content: str
    enabled: bool
    always_apply: bool
    source: str
    plugin_id: str
    created_at: float


class PluginInstallPayload(BaseModel):
    source: str = ""


class PluginResponse(BaseModel):
    id: str
    name: str
    version: str
    description: str
    author: str
    source: str
    installed_at: float
    updated_at: float
    skill_count: int
    rule_count: int


# --- 更新 / 公告 ---


class UpdateApplyPayload(BaseModel):
    download_url: str = ""
    version: str = ""
    expected_sha256: str = ""


class UpdateCheckResponse(BaseModel):
    current: str
    latest: str
    update_available: bool
    download_url: str
    download_sha256: str = ""
    release_notes: str
    checked: bool
    source_repo: str = ""
    source_url: str = ""
    source_kind: str = ""
    can_auto_update: bool = False
    auto_update_hint: str = ""


class UpdateApplyResponse(BaseModel):
    started: bool
    already_running: bool = False
    message: str = ""
    hint: str = ""


class UpdateApplyProgressResponse(BaseModel):
    running: bool
    phase: str = "idle"
    percent: int = 0
    message: str = ""
    detail: str = ""
    ok: bool | None = None
    version: str = ""
    result_message: str = ""
    hint: str = ""
    log: list[str] = []


class ChangelogSectionResponse(BaseModel):
    label: str
    items: list[str]


class ChangelogEntryResponse(BaseModel):
    version: str
    date: str = ""
    title: str = ""
    sections: list[ChangelogSectionResponse] = []


class ChangelogResponse(BaseModel):
    current: str
    acknowledged: str
    has_unseen: bool
    entries: list[ChangelogEntryResponse]
    unseen: list[ChangelogEntryResponse]


# --- MCP ---


class MCPServerPayload(BaseModel):
    id: str = ""
    name: str = ""
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    enabled: bool = True
    cwd: str = ""


class MCPConfigPayload(BaseModel):
    servers: list[MCPServerPayload] = []


# --- 微信桥 ---


class WeixinInboundPayload(BaseModel):
    text: str = ""
    sender_id: str = ""
    peer_id: str = ""
    account_id: str = ""
    context_token: str = ""
    channel: str = "openclaw-weixin"


class WeixinInboundResponse(BaseModel):
    handled: bool
    reply: str = ""


class WeixinSetupRunPayload(BaseModel):
    action: str = "full"


class WeixinBridgeTogglePayload(BaseModel):
    enabled: bool = True
