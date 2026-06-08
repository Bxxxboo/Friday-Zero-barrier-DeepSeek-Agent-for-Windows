from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from openai import OpenAI

from friday.config import (
    COMPACT_SUMMARY_MARKER,
    CONTEXT_COMPACT_BATCH,
    CONTEXT_COMPACT_RATIO,
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
- 联网：浏览网页查找下载链接、验证官方来源（TLS/域名）、从网址下载文件到本地
- 应用：打开网页、启动程序、执行 PowerShell、运行 Python（工作区 .python-env）
- 扩展：从 GitHub 安装/卸载第三方插件包（技能+规则），用户可在「设置 → 扩展」管理
  · 图片视觉桥接、存储分析已内置，无需安装
  · 安装其他插件前先 list_friday_plugins 看是否已装；不知仓库地址时用 list_plugin_catalog
  · GitHub Agent Skill 用 skill:owner/repo/目录 格式
  · 不要用猜错的 owner/repo 连续重试

规则：
1. 自称「星期五」，语气亲切、简洁，像可靠的电脑管家。
2. 优先使用工具完成任务，不要只给空泛建议；同一任务尽量合并步骤，避免无意义的试探性多次调用。
3. 用户说「下载文件夹」「桌面」「文档」「图片」等时，使用下方「本机常用文件夹路径」中的绝对路径；未指定时优先使用「默认操作文件夹」。
4. 文件操作前先了解目录结构（list_directory / search_files）。
5. 删除文件/目录前务必告知用户后果，获得确认后再执行。
6. 帮用户下载软件时（务必高效、少步骤）：
   - 禁止用 run_powershell / Invoke-WebRequest 下载；系统会直接拒绝此类命令。
   - 优先使用 download_software(软件名, 保存路径) 一键完成（内部浏览官网+验证+下载，只需用户确认一次）。
   - 备选：browse_webpage → verify_download_source → download_file，总共不超过 3 步。
   - 用户指定 E 盘等路径时，destination 直接用该绝对路径。
   - 填写 expected_software（netease_music、chrome、微信等）提高识别率。
   - 下载完成后用户要求打开时，用 open_app 启动安装包，不要开浏览器或 PowerShell。
7. Python / PowerShell / 集成配置类任务（少步、大块执行）：
   - 每条用户消息约有 20 轮工具上限；禁止把同一任务拆成多次 run_python / run_powershell 试探（如「先 import」「再 pip install」「再试连接」分三次跑）。
   - 需要多步逻辑时，写成一个完整可运行脚本（含 import、依赖安装、主逻辑、print 最终结果），一次 run_python 执行；超过约 80 行则 write_text_file 保存为 .py 后 run_python_script 一次运行。
   - python_env_info 整个任务最多调用 1 次；不要用 run_python 做 print/path 式环境探测。
   - 读配置、改配置、重启服务、验证结果应合并进同一脚本或同一 PowerShell 命令块，不要每步单独调工具。
   - 复杂任务（接 API、写桥接、批量处理）先在心里列清步骤，再一次性写完整代码；失败时在下一轮用「继续」并基于上次输出改一个完整脚本，不要碎片化补丁。
8. 复杂数据处理、统计分析、批量转换、绘图等优先用上述 Python 方式（工作区 .python-env，含 pandas/numpy 等）；Windows 下用 python 路径，不要用 python3 命令。
9. 回答使用简体中文；说明已完成的动作和结果，避免暴露工具函数名、API 名等技术细节。
10. 危险操作（不要执行删除系统文件、格式化磁盘等）。
11. 若用户问与电脑无关的闲聊（写诗、百科等），简短回应后引导回电脑事务。
12. 微信远程（消息含「[来自微信 remote]」）：必须亲自用工具完成任务，禁止让用户自己跑命令。
13. 【任务完成后的回复格式 · 必须遵守】
    每次完成用户任务，或本轮工具执行告一段落时，必须用具体、可核对的方式回复；风格参考 Cursor：先交代交付物，再给计划。
    禁止敷衍收尾，例如：只说「已完成」「任务完成」、只说「若还有剩余工作请说继续」、不说明刚刚做了什么、不给出下一步计划。
    每次收尾须包含三块（自然中文，可用小标题或列表）：
    (1) 刚刚完成了什么：至少 2 条具体事实——改了/生成了哪些文件、在哪个文件夹、数量或关键结果；有输出文件须写清名称与保存位置；不写完整命令或代码。
    (2) 建议的下一步：主动给出 2～4 条可执行建议，每条是具体动作（如「把扫描结果整理成表格保存到桌面」）；禁止空泛的「如需继续请告诉我」；若任务已全部完成，说明「当前任务已做完」并可选 1～2 条延伸建议。
    (3) 若未完全做完：明确还剩什么；并给出一条用户可直接复制发送的后续指令（放在引号里），让用户知道下一句说什么，而不是只说「继续」。
"""

# 兼容旧引用
SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE

_CONTEXT_MARKER = "\n\n--- 会话上下文（随工作区/模式/规则变化，置于末尾以利前缀缓存）---\n"


def build_system_prompt(settings: UserSettings, *, yolo_unlocked: bool = False) -> str:
    from friday.interaction_modes import mode_prompt_block
    from friday.rules import active_rules_prompt
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
    dynamic = f"本机常用文件夹路径：\n{folder_block}\n{mode_block}\n{rules_block}\n"
    return f"{stable}{_CONTEXT_MARKER}{dynamic}"

# ── 模型上下文窗口（保守取值，留 15% 给响应） ──
_MODEL_MAX_TOKENS: dict[str, int] = {
    "deepseek-v4-flash": 130_000,
    "deepseek-v4-pro": 130_000,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
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
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self._encoder: Any = None
        self._encoder_initialized = False
        self._max_context = resolve_max_context(settings)
        self.usage_stats = UsageStats()
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
        """延迟导入 tiktoken，避免未安装时启动崩溃。"""
        try:
            import tiktoken
            return tiktoken.get_encoding("cl100k_base")
        except ImportError:
            _log.warning("tiktoken 未安装，token 计数将使用字符估算")
            return None
        except Exception:
            _log.warning("tiktoken 初始化失败，使用 o200k_base")
            import tiktoken
            return tiktoken.get_encoding("o200k_base")

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
        # 工具定义的开销（粗略估算，一次即可）
        return total + 200

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

        token_count = self.count_tokens(messages) + tool_tokens
        if token_count <= threshold:
            return messages

        return self._compact_append_only(messages, budget=budget, tool_tokens=tool_tokens)

    def _summarize_message_batch(self, batch: list[dict[str, Any]]) -> str:
        from friday.prefix_cache import deterministic_summary, format_messages_for_summary

        if not batch:
            return ""
        if not self.settings.api_key or str(self.settings.api_key).startswith("sk-test"):
            return deterministic_summary(batch)

        source = format_messages_for_summary(batch)
        try:
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
    ) -> list[dict[str, Any]]:
        """折叠最老的可压缩消息为一条摘要（追加式，不原地改写）。"""
        from friday.prefix_cache import split_message_regions

        working = list(messages)
        min_keep = CONTEXT_MIN_KEEP_RECENT
        max_rounds = 8

        for round_idx in range(max_rounds):
            token_count = self.count_tokens(working) + tool_tokens
            if token_count <= budget:
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
            batch = compactable[:batch_size]
            remaining = compactable[batch_size:]

            summary_body = self._summarize_message_batch(batch)
            summary_msg = {
                "role": "user",
                "content": f"{COMPACT_SUMMARY_MARKER}\n{summary_body}",
            }
            working = [system, *summaries, summary_msg, *remaining, *tail]
            _log.info(
                "上下文 append-only 折叠 | round=%d folded=%d kept=%d tokens≈%d",
                round_idx + 1,
                batch_size,
                len(working),
                self.count_tokens(working) + tool_tokens,
            )

        return working

    def trim_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """兼容旧接口，委托 prepare_messages（无工具 token 估算）。"""
        return self.prepare_messages(messages)

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
        return self.client.chat.completions.create(**kwargs)

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

        stream = self.client.chat.completions.create(**kwargs)
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
        """返回本次会话的 token 用量摘要。"""
        total = self.usage_stats.prompt_tokens + self.usage_stats.completion_tokens
        hit = self.usage_stats.cache_hit_tokens
        if hit > 0:
            rate = self.usage_stats.cache_hit_rate * 100
            return (
                f"📊 Token：输入 {self.usage_stats.prompt_tokens:,} | "
                f"输出 {self.usage_stats.completion_tokens:,} | "
                f"合计 {total:,} | 缓存命中 {hit:,} ({rate:.1f}%)"
            )
        return (
            f"📊 Token 用量：输入 {self.usage_stats.prompt_tokens:,} | "
            f"输出 {self.usage_stats.completion_tokens:,} | "
            f"合计 {total:,}"
        )

    def test_connection(self) -> tuple[bool, str]:
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=8,
            )
            text = response.choices[0].message.content or "ok"
            return True, f"连接成功，模型响应: {text.strip()}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
