from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from openai import OpenAI

from friday.config import (
    COMPACT_SUMMARY_MARKER,
    CONTEXT_COMPACT_BATCH,
    CONTEXT_COMPACT_RATIO,
    CONTEXT_COMPACT_TOOL_ROUNDS,
    CONTEXT_MIN_KEEP_RECENT,
)
from friday.logging_config import get_logger
from friday.paths import format_folders_for_prompt, known_folders
from friday.storage import UserSettings, resolved_workspace
from friday.tools.registry import get_tool_definitions, get_tool_definitions_for_messages

_log = get_logger("brain")

_SYSTEM_PROMPT_BASE = """你是「星期五」，住在这台 Windows 电脑里的 AI 管家。
职责：帮用户打理电脑——整理文件、查看系统状态、生成文档、执行日常电脑事务。

能力概览：
- 文件：列出/搜索/读取/写入/移动/复制/删除/整理/重命名/查重/压缩/解压/查看详情
- 文档：创建 Word/PPT、读取 PDF/Excel
- 系统：CPU/内存/磁盘/进程/网络信息、截图、剪贴板读写
- 图片：DeepSeek 无法直接看图；用户粘贴截图或在对话框发图时，路径会在消息里给出，请用 describe_image 分析
- 生图：用户要求画图、插画、壁纸、海报、头像时，用 generate_image；未配置时引导「设置 → API 连接 → 生图」
  · 未指定画质时默认 1K（1024×1024）；用户提到 8K/4K/2K 或具体分辨率时，在 generate_image 的 size 填 8K、4K 或如 7680x4320，prompt 里写也会自动识别；超出模型上限会自动降到该模型最高画质
- 联网：浏览网页查找下载链接、验证官方来源（TLS/域名）、从网址下载文件到本地
- 应用：打开网页、启动程序、执行 PowerShell、运行 Python（工作区 .python-env）
- 扩展：从 GitHub 安装/卸载第三方插件包（技能+规则），用户可在「设置 → 扩展」管理
  · 图片视觉桥接、存储分析已内置，无需安装
  · 安装其他插件前先 list_friday_plugins 看是否已装；不知仓库地址时用 list_plugin_catalog
  · 用户问「有哪些插件/技能/规则/GitHub skill」时：同一轮须并行调用 list_friday_plugins 与 list_plugin_catalog，禁止先用 search_files / browse_webpage 试探
  · GitHub Agent Skill 用 skill:owner/repo/目录 格式；整仓 Skill（根目录 SKILL.md）用 skill:owner/repo/.

规则：
1. 自称「星期五」，语气亲切、简洁，像可靠的电脑管家。
2. 优先使用工具完成任务，不要只给空泛建议；同一任务尽量合并步骤，避免无意义的试探性多次调用。
3. 用户说「下载文件夹」「桌面」「文档」「图片」等时，使用下方「本机常用文件夹路径」中的绝对路径；未指定时优先使用「默认操作文件夹」。
4. 文件操作前先了解目录结构（list_directory / search_files）。
5. 删除、覆盖、移动、批量整理用户已有文件前：说明路径与后果，使用专用文件工具并等待用户审批；禁止用 run_python/PowerShell 脚本删写绕过审批。「整理/清理/修复」须先只读给计划，不等于同意删除。
6. 帮用户下载软件时（务必高效、少步骤）：
   - 禁止用 run_powershell / Invoke-WebRequest 下载；系统会直接拒绝此类命令。
   - 优先使用 download_software(软件名, 保存路径) 一键完成（内部浏览官网+验证+下载，只需用户确认一次）。
   - 备选：browse_webpage → verify_download_source → download_file，总共不超过 3 步。
   - 用户指定 E 盘等路径时，destination 直接用该绝对路径。
   - 填写 expected_software（netease_music、chrome、微信等）提高识别率。
   - 下载完成后用户要求打开时，用 open_app 启动安装包，不要开浏览器或 PowerShell。
7. Python / PowerShell / 集成配置类任务（少步、大块执行）：
   - 每条用户消息约有 30 轮工具上限（有计划待办时可能更多）；禁止把同一任务拆成多次 run_python / run_powershell 试探（如「先 import」「再 pip install」「再试连接」分三次跑）。
   - 需要多步逻辑时，写成一个完整可运行脚本（含 import、依赖安装、主逻辑、print 最终结果），一次 run_python 执行；超过约 80 行则 write_text_file 保存为 .py 后 run_python_script 一次运行。
   - 一次性脚本、调试输出、中间 CSV/图片等临时文件须写入工作区 `.friday/artifacts/`（系统会登记并按 TTL 移入 trash）；用户明确要的交付物不要放在该目录。
   - python_env_info 整个任务最多调用 1 次；不要用 run_python 做 print/path 式环境探测。
   - 读配置、改配置、重启服务、验证结果应合并进同一脚本或同一 PowerShell 命令块，不要每步单独调工具。
   - 复杂任务（接 API、写桥接、批量处理）先在心里列清步骤，再一次性写完整代码；失败时在下一轮用「继续」并基于上次输出改一个完整脚本，不要碎片化补丁。
   - run_python 不得用于删除/覆盖/移动用户文件或修改 %AppData%\\Friday\\ 配置；此类操作须用 delete_file、write_text_file、move_file 等并等用户审批。
8. 复杂数据处理、统计分析、批量转换、绘图等优先用上述 Python 方式（工作区 .python-env，含 pandas/numpy 等）；Windows 下用 python 路径，不要用 python3 命令。
9. 回答使用简体中文；说明已完成的动作和结果，避免暴露工具函数名、API 名等技术细节。
10. 危险操作（不要执行删除系统文件、格式化磁盘等）；不得未经审批删改用户文档、桌面、下载目录或星期五自身配置文件。
11. 用户闲聊、问百科、写诗等时，可正常友好回应，不必强行拉回电脑管理话题；若对方顺便需要电脑上的帮助，再自然衔接即可。
12. 微信远程（消息含「[来自微信 remote]」）：
    - 必须亲自用工具完成任务，禁止让用户自己跑命令。
    - 用户**仅询问原因、现象、文件名含义**（如「为啥」「为什么」「什么意思」「多了个后缀」）且**未明确要求**修文件、重命名、清理或发送时：只用文字解释，**禁止**调用会移动/复制/删除/重命名文件的工具；不要顺带清理、重命名或重发附件。
    - 生图、截图、新建 Word/PPT、写入 txt/md/csv/json 等任务完成后，系统会自动把图片或文件附件发到微信；用文字说明文件名与结果即可，禁止说「无法通过微信发文件」或让用户自己去文件夹找。
    - 用户要桌面上已有文件时：先用 search_files / list_directory 定位，再用 copy_file 复制到工作区 `.friday/delivered/`（保持原文件名），系统会在复制成功后立即发送附件；禁止用 run_powershell / run_python 复制文件；不要只读内容贴聊天代替发文件。
    - 禁止说「本轮对话结束后会自动发送」「稍后会发到微信」等——附件在工具成功当下就发，不要承诺延后发送。
    - 若文件已在 delivered/ 而用户再次要求发送：不要只说「应该会自动发送」就结束；用 copy_file 再复制到 delivered/ 一次以确保附件发出。
13. 【任务完成后的回复格式】
    简单任务（单次工具已成功、交付物明确，如生图已保存路径、文件已写入）：2～4 句话说明结果与保存位置即可，可附 1 条可选后续；不必强行写「剩余未完成」或多条下一步。
    复杂或多步任务：用具体、可核对的方式收尾；风格参考 Cursor：先交代交付物，再给计划。
    禁止敷衍收尾，例如：只说「已完成」、不说明刚刚做了什么。
    复杂任务收尾须包含：
    (1) 刚刚完成了什么：至少 2 条具体事实——改了/生成了哪些文件、在哪个文件夹、数量或关键结果。
    (2) 建议的下一步：2～4 条可执行建议；若已全部完成，说明「当前任务已做完」并可选 1～2 条延伸建议。
    (3) 若未完全做完：明确还剩什么，并给出一句用户可直接复制发送的后续指令。
14. 【复杂任务 · 强执行模式】
    - 涉及 3 步以上的整理、排查、批量处理、接 API、写脚本时：先调用 update_session_plan 写出可核对的分步计划（含 checkbox 待办），再按计划推进。
    - 信息收集阶段：同一轮可并行调用多个只读工具（list_directory、search_files、get_system_status、list_open_windows、list_friday_plugins、list_plugin_catalog 等），不要逐个试探。
    - 工具报错或结果为空时：先分析原因（路径错？权限？依赖缺失？），换策略重试；禁止无脑重复同一调用。
    - 用户表达的稳定偏好（默认盘符、常用软件、命名习惯）用 remember_user_fact 记入长期记忆，下次主动参考。
    - 需要操控具体窗口/程序时：先用 list_open_windows 了解前台环境，再 open_app 或 PowerShell/Python 精准操作。
15. 【改代码 · 少轮次】
    - 用户消息里已有足够代码/修改说明时，直接 write_text_file，不要先 read_text_file。
    - 必须先读时：read_text_file 一次后立即 write_text_file；禁止改前反复 read、改后再 read 验证（除非用户明确要求检查）。
    - 单文件小改禁止 write → read → write 循环；同一文件在一轮对话里最多 read 一次。
    - 不要用 run_python / run_powershell 做「打开文件改一行」类小改，应用 write_text_file。
"""

# 兼容旧引用
SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE

_CONTEXT_MARKER = "\n\n--- 会话上下文（随工作区/模式/规则变化，置于末尾以利前缀缓存）---\n"


def build_system_prompt(settings: UserSettings, *, yolo_unlocked: bool = False) -> str:
    from friday.interaction_modes import mode_prompt_block
    from friday.rules import active_rules_prompt
    from friday.user_memory import format_for_prompt as user_memory_prompt
    from friday.vision import vision_ready

    folders = known_folders(resolved_workspace(settings))
    folder_block = format_folders_for_prompt(folders)
    rules_block = active_rules_prompt()
    mode_block = mode_prompt_block(
        getattr(settings, "interaction_mode", "agent"),
        yolo_unlocked=yolo_unlocked,
    )
    vision_block = ""
    if vision_ready(settings):
        vision_block = (
            "\n【视觉辅助已启用】用户发图或消息中含截图路径时，必须先调用 describe_image 分析，"
            "再根据返回的文字描述回答；不要声称无法看图。\n"
        )
    stable = f"{_SYSTEM_PROMPT_BASE}{vision_block}"
    memory_block = user_memory_prompt()
    dynamic = f"本机常用文件夹路径：\n{folder_block}\n{memory_block}{mode_block}\n{rules_block}\n"
    return f"{stable}{_CONTEXT_MARKER}{dynamic}"

# ── 模型上下文窗口（保守取值，留 15% 给响应） ──
_MODEL_MAX_TOKENS: dict[str, int] = {
    "deepseek-v4-flash": 130_000,
    "deepseek-v4-pro": 130_000,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "gpt-4o": 120_000,
    "gpt-4o-mini": 120_000,
    "o3-mini": 120_000,
    "qwen-plus": 120_000,
    "qwen-turbo": 120_000,
    "qwen-max": 120_000,
    "glm-4-plus": 120_000,
    "glm-4-flash": 120_000,
    "glm-4-air": 120_000,
    "kimi-k2-0711-preview": 120_000,
    "mimo-v2-flash": 120_000,
    "mimo-v2.5-pro": 120_000,
    "moonshot-v1-32k": 32_000,
    "moonshot-v1-8k": 8_000,
}

_DEFAULT_MAX_CONTEXT = 100_000  # 未知模型保守估计
_SAFETY_RATIO = 0.85  # 请求 token 不超过上下文的 85%，留空间给响应


def resolve_max_context(settings: UserSettings, *, client: OpenAI | None = None) -> int:
    """解析模型上下文上限：硬编码表为 fallback，优先尝试 API。"""
    fallback = _MODEL_MAX_TOKENS.get(settings.model, _DEFAULT_MAX_CONTEXT)
    if client is None:
        return fallback
    try:
        info = client.models.retrieve(settings.model)
        for attr in ("max_context_tokens", "context_length", "max_tokens"):
            value = getattr(info, attr, None)
            if isinstance(value, int) and value > 0:
                return value
        if isinstance(info, dict):
            for key in ("max_context_tokens", "context_length", "max_tokens"):
                value = info.get(key)
                if isinstance(value, int) and value > 0:
                    return value
    except Exception:  # noqa: BLE001
        pass
    return fallback


@dataclass
class ChatCompletionResult:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hit_tokens + self.cache_miss_tokens
        if total <= 0:
            return 0.0
        return self.cache_hit_tokens / total

    def merge(self, other: UsageStats) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cache_hit_tokens += other.cache_hit_tokens
        self.cache_miss_tokens += other.cache_miss_tokens


def parse_api_usage(usage: Any) -> UsageStats:
    """解析 OpenAI 兼容 usage（含 DeepSeek 前缀缓存字段）。"""
    if usage is None:
        return UsageStats()
    if isinstance(usage, dict):
        data = usage
    else:
        data = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
            "prompt_cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", 0),
            "prompt_cache_miss_tokens": getattr(usage, "prompt_cache_miss_tokens", 0),
        }
    hit = int(
        data.get("prompt_cache_hit_tokens")
        or data.get("cached_tokens")
        or 0
    )
    miss = int(data.get("prompt_cache_miss_tokens") or 0)
    prompt = int(data.get("prompt_tokens") or 0)
    if miss <= 0 and hit > 0 and prompt > hit:
        miss = max(prompt - hit, 0)
    return UsageStats(
        prompt_tokens=prompt,
        completion_tokens=int(data.get("completion_tokens") or 0),
        cache_hit_tokens=hit,
        cache_miss_tokens=miss,
    )


class DeepSeekBrain:
    def __init__(self, settings: UserSettings) -> None:
        self.settings = settings
        from friday.api_connect import apply_network_environment, build_openai_client

        apply_network_environment(settings)
        self.client = build_openai_client(
            settings.api_key,
            settings.base_url,
            settings,
        )
        self._encoder: Any = None
        self._encoder_initialized = False
        self._max_context = resolve_max_context(settings)
        self.usage_stats = UsageStats()
        self._turn_api_calls = 0
        # 兼容旧字段（逐步迁移到 usage_stats）
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @property
    def encoder(self):
        """tiktoken 编码器，仅在首次 token 计数时加载。"""
        if not self._encoder_initialized:
            self._encoder = self._init_encoder()
            self._encoder_initialized = True
        return self._encoder

    def _init_encoder(self):
        """延迟导入 tiktoken，避免未安装时启动崩溃；打包环境需预加载 tiktoken_ext。"""
        try:
            import tiktoken

            from friday.paths import is_frozen

            if is_frozen():
                import tiktoken_ext.openai_public  # noqa: F401 — 注册 cl100k_base 等编码

            return tiktoken.get_encoding("cl100k_base")
        except ImportError:
            _log.warning("tiktoken 未安装，token 计数将使用字符估算")
            return None
        except Exception as exc:
            _log.warning("tiktoken 不可用，token 计数将使用字符估算 | %s", exc)
            return None

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的 token 数。未安装 tiktoken 时用字符数/4 估算。"""
        enc = self.encoder
        if enc is None:
            return sum(len(str(m)) // 4 for m in messages)

        total = 0
        for msg in messages:
            total += 4  # 每条消息的框架开销
            for key, value in msg.items():
                if isinstance(value, str):
                    total += len(enc.encode(value))
                elif isinstance(value, list):
                    total += self._count_tool_calls(value)
        return total

    def _count_tool_calls(self, tool_calls: list[dict[str, Any]]) -> int:
        enc = self.encoder
        if enc is None:
            return sum(len(str(tc)) // 4 for tc in tool_calls)
        total = 0
        for tc in tool_calls:
            total += len(enc.encode(str(tc)))
        return total

    def _estimate_tools_tokens(self, tools: list[dict[str, Any]]) -> int:
        enc = self.encoder
        payload = json.dumps(tools, ensure_ascii=False, sort_keys=True)
        if enc is None:
            return len(payload) // 4
        return len(enc.encode(payload))

    def prepare_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Append-only 上下文：不改写已有消息，超限时折叠早期轮次为摘要。"""
        tools = tool_definitions or []
        tool_tokens = self._estimate_tools_tokens(tools) if tools else 200
        budget = int(self._max_context * _SAFETY_RATIO)
        threshold = int(budget * CONTEXT_COMPACT_RATIO)

        from friday.prefix_cache import count_tool_rounds_since_last_compact

        token_count = self.count_tokens(messages) + tool_tokens
        tool_rounds = count_tool_rounds_since_last_compact(messages)
        over_ratio = token_count > threshold
        over_tool_rounds = tool_rounds >= CONTEXT_COMPACT_TOOL_ROUNDS
        if not over_ratio and not over_tool_rounds:
            return messages

        return self._compact_append_only(
            messages,
            budget=budget,
            tool_tokens=tool_tokens,
            force_once=over_tool_rounds and not over_ratio,
        )

    def _summarize_message_batch(self, batch: list[dict[str, Any]]) -> str:
        from friday.prefix_cache import deterministic_summary, format_messages_for_summary

        if not batch:
            return ""
        if not self.settings.api_key or str(self.settings.api_key).startswith("sk-test"):
            return deterministic_summary(batch)

        source = format_messages_for_summary(batch)
        try:
            self.record_api_call()
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是摘要助手。将以下对话片段压缩为简洁中文要点，"
                            "保留：用户目标、已执行操作、文件路径、关键结果、未完成项。"
                            "不要遗漏路径和数字。"
                        ),
                    },
                    {"role": "user", "content": source},
                ],
                max_tokens=800,
                temperature=0.1,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            _log.warning("摘要 API 失败，使用确定性 fallback | %s", exc)
        return deterministic_summary(batch)

    def _compact_append_only(
        self,
        messages: list[dict[str, Any]],
        *,
        budget: int,
        tool_tokens: int,
        force_once: bool = False,
    ) -> list[dict[str, Any]]:
        """折叠最老的可压缩消息为一条摘要（追加式，不原地改写）。"""
        from friday.prefix_cache import split_message_regions

        working = list(messages)
        min_keep = CONTEXT_MIN_KEEP_RECENT
        max_rounds = 8
        forced_pending = force_once

        for round_idx in range(max_rounds):
            token_count = self.count_tokens(working) + tool_tokens
            if token_count <= budget and not forced_pending:
                break
            if len(working) <= 1 + min_keep:
                break

            system, summaries, compactable, tail = split_message_regions(
                working,
                min_keep_recent=min_keep,
            )
            if len(compactable) < 2:
                _log.warning(
                    "上下文仍超限但可折叠消息不足 | tokens=%d budget=%d",
                    token_count,
                    budget,
                )
                break

            batch_size = min(CONTEXT_COMPACT_BATCH, len(compactable))
            from friday.context import flatten_message_blocks, iter_message_blocks

            compact_blocks = iter_message_blocks(compactable)
            fold_blocks: list[list[dict[str, Any]]] = []
            folded = 0
            for block in compact_blocks:
                if fold_blocks and folded + len(block) > batch_size:
                    break
                fold_blocks.append(block)
                folded += len(block)
            if not fold_blocks and compact_blocks:
                fold_blocks = [compact_blocks[0]]

            batch = flatten_message_blocks(fold_blocks)
            remaining = flatten_message_blocks(compact_blocks[len(fold_blocks) :])

            summary_body = self._summarize_message_batch(batch)
            summary_msg = {
                "role": "user",
                "content": f"{COMPACT_SUMMARY_MARKER}\n{summary_body}",
            }
            working = [system, *summaries, summary_msg, *remaining, *tail]
            forced_pending = False
            _log.info(
                "上下文 append-only 折叠 | round=%d folded=%d kept=%d tokens≈%d",
                round_idx + 1,
                batch_size,
                len(working),
                self.count_tokens(working) + tool_tokens,
            )

        return working

    def reset_turn_api_calls(self) -> None:
        self._turn_api_calls = 0

    def record_api_call(self) -> None:
        self._turn_api_calls += 1

    def trim_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """兼容旧接口，委托 prepare_messages（无工具 token 估算）。"""
        return self.prepare_messages(messages)

    def _call_with_transient_retry(self, fn: Callable[[], Any]) -> Any:
        """对瞬态网络/超时错误自动重试一次，减少「用着用着突然报错」。"""
        from friday.api_connect import is_transient_api_error

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                self.record_api_call()
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= 1 or not is_transient_api_error(exc):
                    raise
                _log.warning("大模型 API 瞬态失败，正在重试 | %s", exc)
                time.sleep(1.5)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("API 调用失败")

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: bool = True,
        *,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            kwargs["tools"] = tool_definitions or get_tool_definitions_for_messages(
                messages,
                settings=self.settings,
            )
            kwargs["tool_choice"] = "auto"
        kwargs["stream_options"] = {"include_usage": True}
        return self._call_with_transient_retry(lambda: self.client.chat.completions.create(**kwargs))

    def iter_chat(
        self,
        messages: list[dict[str, Any]],
        tools: bool = True,
        *,
        tool_definitions: list[dict[str, Any]] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> Iterator[tuple[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tool_definitions or get_tool_definitions_for_messages(
                messages,
                settings=self.settings,
            )
            kwargs["tool_choice"] = "auto"
        kwargs["stream_options"] = {"include_usage": True}

        stream = self._call_with_transient_retry(lambda: self.client.chat.completions.create(**kwargs))
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        stream_usage = UsageStats()

        for chunk in stream:
            if should_cancel and should_cancel():
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
                break
            if getattr(chunk, "usage", None):
                stream_usage.merge(parse_api_usage(chunk.usage))
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content_parts.append(delta.content)
                yield "delta", delta.content

            reasoning = getattr(delta, "reasoning_content", None) or ""
            if reasoning:
                yield "reasoning_delta", reasoning

            if delta.tool_calls:
                for call in delta.tool_calls:
                    idx = call.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_acc[idx]
                    if call.id:
                        acc["id"] = call.id
                    if call.function:
                        if call.function.name:
                            acc["function"]["name"] += call.function.name
                        if call.function.arguments:
                            acc["function"]["arguments"] += call.function.arguments

        tool_calls = [tool_calls_acc[idx] for idx in sorted(tool_calls_acc)]
        result = ChatCompletionResult(
            content="".join(content_parts),
            tool_calls=tool_calls,
        )

        if stream_usage.prompt_tokens or stream_usage.completion_tokens:
            self.usage_stats.merge(stream_usage)
            self.total_prompt_tokens += stream_usage.prompt_tokens
            self.total_completion_tokens += stream_usage.completion_tokens
        else:
            est_prompt = self.count_tokens(messages)
            enc = self.encoder
            est_completion = (
                len(enc.encode(result.content))
                if enc is not None
                else len(result.content) // 4
            )
            self.total_prompt_tokens += est_prompt
            self.total_completion_tokens += est_completion
            self.usage_stats.prompt_tokens += est_prompt
            self.usage_stats.completion_tokens += est_completion

        yield "finish", result

    def usage_summary(self) -> str:
        """返回本次对话的 API 调用次数与 token 用量摘要。"""
        total = self.usage_stats.prompt_tokens + self.usage_stats.completion_tokens
        api_part = f"本次共调用 {self._turn_api_calls} 次 API"
        return (
            f"{api_part} | 📊 Token 用量：输入 {self.usage_stats.prompt_tokens:,} | "
            f"输出 {self.usage_stats.completion_tokens:,} | "
            f"合计 {total:,}"
        )

    def test_connection(self) -> tuple[bool, str]:
        from friday.api_connect import diagnose_llm, format_api_error, invalidate_probe_cache

        try:
            steps = diagnose_llm(self.settings, include_api=True)
            if steps and steps[-1].ok:
                invalidate_probe_cache(clear_auth=False)
                return True, steps[-1].detail
            failed = next((s for s in reversed(steps) if not s.ok), steps[-1] if steps else None)
            if failed is None:
                return False, "连接测试失败"
            msg = failed.detail
            if failed.hint:
                msg = f"{msg}\n{failed.hint}"
            return False, msg
        except Exception as exc:  # noqa: BLE001
            from friday.model_providers import llm_service_label

            return False, format_api_error(
                exc, context="api_test", service=llm_service_label(self.settings)
            )


def effective_context_messages_for_meter(
    settings: UserSettings,
    messages: list[dict[str, Any]],
    *,
    session_id: str = "",
    tool_definitions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """与真实发请求前一致：rebuild + 折叠，避免状态栏按磁盘全量历史高估。"""
    from friday.tools.registry import get_frozen_tool_definitions

    tools = tool_definitions if tool_definitions is not None else get_frozen_tool_definitions(settings)
    msgs = list(messages or [])
    if not msgs:
        return []
    if session_id:
        from friday.context_assembler import rebuild_messages

        msgs, _ = rebuild_messages(session_id, msgs, settings=settings)
    brain = DeepSeekBrain(settings)
    return brain.prepare_messages(msgs, tool_definitions=tools)


def compute_context_meter(
    settings: UserSettings,
    messages: list[dict[str, Any]] | None = None,
    *,
    tool_definitions: list[dict[str, Any]] | None = None,
    session_id: str = "",
) -> dict[str, int | float]:
    """估算下一轮 API 请求的上下文占用（消息 + 工具定义）。"""
    from friday.tools.registry import get_frozen_tool_definitions

    tools = tool_definitions if tool_definitions is not None else get_frozen_tool_definitions(settings)
    max_context = resolve_max_context(settings)
    budget = int(max_context * _SAFETY_RATIO)
    threshold = int(budget * CONTEXT_COMPACT_RATIO)

    raw_list = list(messages or [])
    if not raw_list:
        return {
            "context_tokens": 0,
            "max_context": max_context,
            "context_budget": budget,
            "compact_threshold": threshold,
            "budget_ratio": 0.0,
        }

    msg_list = effective_context_messages_for_meter(
        settings,
        raw_list,
        session_id=session_id,
        tool_definitions=tools,
    )
    brain = DeepSeekBrain(settings)
    message_tokens = brain.count_tokens(msg_list)
    tool_tokens = brain._estimate_tools_tokens(tools) if tools else 200
    context_tokens = int(message_tokens + tool_tokens)
    ratio = float(context_tokens / budget) if budget > 0 else 0.0
    return {
        "context_tokens": context_tokens,
        "max_context": max_context,
        "context_budget": budget,
        "compact_threshold": threshold,
        "budget_ratio": round(ratio, 4),
    }
