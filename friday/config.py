from __future__ import annotations

APP_NAME = "星期五"
MAX_TOOL_ROUNDS = 30
MAX_TOOL_ROUNDS_CAP = 45
MAX_TOOL_RESULT_CHARS = 4000  # 写入上下文的工具结果预算（配合智能压缩）
TOOL_RESULT_HEAD_CHARS = 2400
TOOL_RESULT_TAIL_CHARS = 1200
TOOL_RESULT_ARCHIVE_CHARS = 900  # 历史 tool 消息归档压缩
MAX_PERSISTED_TOOL_CHARS = 800  # 落盘时 tool 消息内容上限
SESSION_FORMAT_VERSION = 2

# API 网络（跨机连通）
API_CONNECT_TIMEOUT = 20.0
API_READ_TIMEOUT = 120.0
API_MAX_RETRIES = 2

# 前缀缓存 / append-only 上下文（Reasonix 式）
CONTEXT_COMPACT_RATIO = 0.80  # 达到上下文预算 80% 时触发折叠
CONTEXT_MIN_KEEP_RECENT = 8  # 折叠时保留最近 N 条（不含 system）
CONTEXT_COMPACT_BATCH = 10  # 每次折叠的消息条数
CONTEXT_COMPACT_TOOL_ROUNDS = 15  # 自上次摘要以来工具轮次达 N 时也触发折叠
COMPACT_SUMMARY_MARKER = "[前文摘要 · 自动压缩]"
PLAN_ANCHOR_MARKER = "[任务计划 · 会话锚点]"

# Checkpoint writer（M6.2 P1）
CHECKPOINT_TRIGGER_RATIOS = (0.20, 0.45, 0.70)  # token 预算比例触发档位
CONTEXT_REBUILD_RATIO = 0.85  # rebuild 触发（P2）
CHECKPOINT_MARKER = "[工作记忆 · 会话检查点]"
CHECKPOINT_FIELD_KEYS = (
    "goal_context",
    "current_state",
    "key_paths",
    "completed",
    "pending",
    "decisions",
    "user_prefs",
    "errors_avoid",
    "tools_summary",
    "todos_snapshot",
    "resume_hint",
)
CHECKPOINT_FIELD_LABELS = {
    "goal_context": "目标与背景",
    "current_state": "当前状态",
    "key_paths": "关键路径",
    "completed": "已完成",
    "pending": "未完成",
    "decisions": "重要决策",
    "user_prefs": "用户偏好",
    "errors_avoid": "错误与规避",
    "tools_summary": "工具与操作摘要",
    "todos_snapshot": "待办快照",
    "resume_hint": "续聊提示",
}

# 工具执行超时（秒）
TOOL_TIMEOUT_READ = 30
TOOL_TIMEOUT_VISION = 120
TOOL_TIMEOUT_IMAGE_GEN = 180  # 生图默认工具超时；实际按分辨率/画质动态上调
IMAGE_GEN_TOOL_TIMEOUT_MIN = 120
IMAGE_GEN_TOOL_TIMEOUT_MAX = 600  # 4K + quality=high 最长约 10 分钟
IMAGE_GEN_HTTP_TIMEOUT_MIN = 90
IMAGE_GEN_HTTP_TIMEOUT_MAX = 480
TOOL_TIMEOUT_WRITE = 60
TOOL_TIMEOUT_EXEC = 120
TOOL_TIMEOUT_DOWNLOAD = 900
TOOL_TIMEOUT_DOWNLOAD_LARGE = 3600
CANCEL_POLL_INTERVAL = 0.3  # 停止请求轮询间隔（秒）
VISION_HTTP_TIMEOUT = 90  # 视觉 API 单次 HTTP 读超时（秒）
IMAGE_GEN_HTTP_TIMEOUT = 180  # 生图 HTTP 默认读超时；实际按分辨率动态上调
IMAGE_GEN_PROBE_TIMEOUT = 8.0  # 设置页「测试生图」轻量认证总超时预算（秒）
IMAGE_GEN_IMAGES_PROBE_TIMEOUT = 3.0  # POST /images/generations 探测上限（避免等完整生图）
STATUS_BAR_IMAGE_GEN_PROBE_TIMEOUT = 8.0  # 状态栏快速探测（秒；慢端点可能仍 inconclusive）

# 联网限制
WEB_PAGE_MAX_BYTES = 10 * 1024 * 1024
DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024
DOWNLOAD_LARGE_THRESHOLD_BYTES = 1024 * 1024 * 1024
DOWNLOAD_LARGE_MAX_BYTES = 10 * 1024 * 1024 * 1024

__all__ = [
    "APP_NAME",
    "MAX_TOOL_ROUNDS",
    "MAX_TOOL_ROUNDS_CAP",
    "MAX_TOOL_RESULT_CHARS",
    "TOOL_RESULT_HEAD_CHARS",
    "TOOL_RESULT_TAIL_CHARS",
    "TOOL_RESULT_ARCHIVE_CHARS",
    "MAX_PERSISTED_TOOL_CHARS",
    "SESSION_FORMAT_VERSION",
    "API_CONNECT_TIMEOUT",
    "API_READ_TIMEOUT",
    "API_MAX_RETRIES",
    "CONTEXT_COMPACT_RATIO",
    "CONTEXT_MIN_KEEP_RECENT",
    "CONTEXT_COMPACT_BATCH",
    "CONTEXT_COMPACT_TOOL_ROUNDS",
    "COMPACT_SUMMARY_MARKER",
    "PLAN_ANCHOR_MARKER",
    "CHECKPOINT_TRIGGER_RATIOS",
    "CONTEXT_REBUILD_RATIO",
    "CHECKPOINT_MARKER",
    "CHECKPOINT_FIELD_KEYS",
    "CHECKPOINT_FIELD_LABELS",
    "TOOL_TIMEOUT_READ",
    "TOOL_TIMEOUT_VISION",
    "TOOL_TIMEOUT_IMAGE_GEN",
    "IMAGE_GEN_TOOL_TIMEOUT_MIN",
    "IMAGE_GEN_TOOL_TIMEOUT_MAX",
    "IMAGE_GEN_HTTP_TIMEOUT_MIN",
    "IMAGE_GEN_HTTP_TIMEOUT_MAX",
    "TOOL_TIMEOUT_WRITE",
    "TOOL_TIMEOUT_EXEC",
    "TOOL_TIMEOUT_DOWNLOAD",
    "TOOL_TIMEOUT_DOWNLOAD_LARGE",
    "CANCEL_POLL_INTERVAL",
    "VISION_HTTP_TIMEOUT",
    "IMAGE_GEN_HTTP_TIMEOUT",
    "IMAGE_GEN_PROBE_TIMEOUT",
    "IMAGE_GEN_IMAGES_PROBE_TIMEOUT",
    "STATUS_BAR_IMAGE_GEN_PROBE_TIMEOUT",
    "WEB_PAGE_MAX_BYTES",
    "DOWNLOAD_MAX_BYTES",
    "DOWNLOAD_LARGE_THRESHOLD_BYTES",
    "DOWNLOAD_LARGE_MAX_BYTES",
]
