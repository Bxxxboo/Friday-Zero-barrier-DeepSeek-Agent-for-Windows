from __future__ import annotations

from typing import Any, Callable

import threading

from friday.brain import ChatCompletionResult, DeepSeekBrain, UsageStats
from friday.config import MAX_TOOL_RESULT_CHARS, MAX_TOOL_ROUNDS
from friday.logging_config import get_logger
from friday.safety import (
    PendingAction,
    TurnApprovalState,
    classify_tool,
    describe_approval_plain,
    evaluate_tool,
    mark_turn_approved,
    should_request_approval,
    summarize_action,
    summarize_preview,
)
from friday.storage import UserSettings
from friday.operations import log_operation
from friday.tools.registry import CANCELLED_TOOL_MESSAGE, execute_tool, is_download_task_context, parse_tool_arguments

ApprovalCallback = Callable[[PendingAction], bool]
EventCallback = Callable[[str, dict[str, Any]], None]

_log = get_logger("agent")

CANCELLED_MESSAGE = "⏹ 已停止生成。"


class FridayAgent:
    def __init__(
        self,
        settings: UserSettings,
        request_approval: ApprovalCallback,
    ) -> None:
        self.settings = settings
        self.brain = DeepSeekBrain(settings)
        self.request_approval = request_approval
        self.messages: list[dict[str, Any]] = []
        self._round_count = 0
        self._cancel_event = threading.Event()  # #2 取消机制
        self.operation_meta: dict[str, Any] = {}
        self._turn_approval = TurnApprovalState()
        self.yolo_unlocked = False
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_cache_hit_tokens = 0
        self.session_cache_miss_tokens = 0
        self._frozen_prefix: Any = None
        self._pin_prefix(force=True)

    def _pin_prefix(self, *, force: bool = False) -> bool:
        """冻结 system + tools，会话内保持字节稳定以利于前缀缓存。"""
        from friday.prefix_cache import build_frozen_prefix, log_prefix_drift

        frozen = build_frozen_prefix(self.settings, yolo_unlocked=self.yolo_unlocked)
        changed = force or (
            self._frozen_prefix is None
            or frozen.fingerprint != self._frozen_prefix.fingerprint
        )
        self._frozen_prefix = frozen
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0] = {"role": "system", "content": frozen.system_prompt}
        else:
            self.messages = [{"role": "system", "content": frozen.system_prompt}, *self.messages]
        if changed:
            _log.info(
                "前缀已冻结 | fingerprint=%s tools=%d",
                frozen.fingerprint[:12],
                len(frozen.tool_definitions),
            )
        else:
            drift = self._prefix_drift_reasons()
            if drift:
                log_prefix_drift(drift, fingerprint=frozen.fingerprint)
        return changed

    def _prefix_drift_reasons(self) -> list[str]:
        if self._frozen_prefix is None:
            return []
        from friday.prefix_cache import detect_prefix_drift

        return detect_prefix_drift(
            self._frozen_prefix,
            self.messages,
            self.settings,
            yolo_unlocked=self.yolo_unlocked,
        )

    def refresh_prefix_if_needed(
        self,
        settings: UserSettings,
        *,
        yolo_unlocked: bool = False,
    ) -> bool:
        """设置变更影响前缀时重新冻结（会重置缓存命中）。"""
        from friday.prefix_cache import compute_settings_fingerprint, log_prefix_drift

        prev_fp = (
            self._frozen_prefix.settings_fingerprint
            if self._frozen_prefix is not None
            else ""
        )
        self.settings = settings
        self.yolo_unlocked = yolo_unlocked
        new_fp = compute_settings_fingerprint(settings, yolo_unlocked=yolo_unlocked)
        if new_fp != prev_fp:
            _log.info("设置影响前缀，重新冻结 | was=%s now=%s", prev_fp[:12], new_fp[:12])
            return self._pin_prefix(force=True)
        drift = self._prefix_drift_reasons()
        if drift and self._frozen_prefix is not None:
            log_prefix_drift(drift, fingerprint=self._frozen_prefix.fingerprint)
        return False

    # ── 生命周期 ──

    def cancel(self) -> None:
        """取消当前正在执行的对话。"""
        _log.info("用户请求取消对话")
        self._cancel_event.set()

    def reset(self) -> None:
        self._cancel_event.clear()
        self._turn_approval = TurnApprovalState()
        self.messages = []
        self._round_count = 0
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.session_cache_hit_tokens = 0
        self.session_cache_miss_tokens = 0
        self._pin_prefix(force=True)

    def _finalize_usage(self) -> None:
        """将本轮 brain 计数累加到会话总量，并清零本轮计数。"""
        self.session_prompt_tokens += self.brain.usage_stats.prompt_tokens or self.brain.total_prompt_tokens
        self.session_completion_tokens += (
            self.brain.usage_stats.completion_tokens or self.brain.total_completion_tokens
        )
        self.session_cache_hit_tokens += self.brain.usage_stats.cache_hit_tokens
        self.session_cache_miss_tokens += self.brain.usage_stats.cache_miss_tokens
        self.brain.usage_stats = UsageStats()
        self.brain.total_prompt_tokens = 0
        self.brain.total_completion_tokens = 0

    def usage_snapshot(self) -> dict[str, int | float]:
        stats = self.brain.usage_stats
        prompt = self.session_prompt_tokens + stats.prompt_tokens + self.brain.total_prompt_tokens
        completion = (
            self.session_completion_tokens + stats.completion_tokens + self.brain.total_completion_tokens
        )
        cache_hit = self.session_cache_hit_tokens + stats.cache_hit_tokens
        cache_miss = self.session_cache_miss_tokens + stats.cache_miss_tokens
        cache_total = cache_hit + cache_miss
        rate = (cache_hit / cache_total) if cache_total > 0 else 0.0
        return {
            "tokens_prompt": int(prompt),
            "tokens_completion": int(completion),
            "tokens_total": int(prompt + completion),
            "cache_hit_tokens": int(cache_hit),
            "cache_miss_tokens": int(cache_miss),
            "cache_hit_rate": round(rate, 4),
        }

    def _finish_run(self, content: str) -> str:
        self._finalize_usage()
        return content

    def load_history(self, messages: list[dict[str, Any]] | None) -> None:
        if not messages:
            self.reset()
            return
        self.messages = list(messages)
        self._pin_prefix(force=True)

    # ── 事件发射 ──

    def _emit(self, on_event: EventCallback | None, event_type: str, payload: dict[str, Any]) -> None:
        if on_event:
            on_event(event_type, payload)

    # ── 流式消费 ──

    def _consume_stream(self, on_event: EventCallback | None, *, tools: bool = True) -> ChatCompletionResult:
        """与模型交互一次，返回 delta + finish 结果。"""
        if self._frozen_prefix is None:
            self._pin_prefix(force=True)

        drift = self._prefix_drift_reasons()
        if drift:
            from friday.prefix_cache import log_prefix_drift

            log_prefix_drift(drift, fingerprint=self._frozen_prefix.fingerprint)

        prepared = self.brain.prepare_messages(
            self.messages,
            tool_definitions=self._frozen_prefix.tool_definitions if tools else None,
        )
        if prepared is not self.messages and prepared != self.messages:
            self.messages = prepared

        tool_defs = self._frozen_prefix.tool_definitions if tools else None

        stream_started = False
        finish: ChatCompletionResult | None = None

        for kind, payload in self.brain.iter_chat(
            self.messages,
            tools=tools,
            tool_definitions=tool_defs,
            should_cancel=self._cancel_event.is_set,
        ):
            if self._cancel_event.is_set():
                break
            if kind == "delta":
                if on_event:
                    if not stream_started:
                        self._emit(on_event, "assistant_start", {})
                        stream_started = True
                    self._emit(on_event, "assistant_delta", {"delta": payload})
            elif kind == "finish":
                finish = payload

        if finish is None:
            finish = ChatCompletionResult()

        if finish.tool_calls and stream_started:
            self._emit(on_event, "assistant_clear", {})

        return finish

    def _wrap_up_reply(self, on_event: EventCallback | None, *, reason: str = "round_limit") -> str:
        """工具轮次用尽或需收尾时，让模型用自然语言总结已完成工作与下一步计划。"""
        if self._cancel_event.is_set():
            return CANCELLED_MESSAGE

        if reason == "round_limit":
            hint = (
                "【系统提示】本轮工具调用次数已达上限，请不要再调用任何工具。"
                "请仅根据上文已执行的操作，按系统提示中的「任务完成后的回复格式」向用户回复："
                "① 刚刚具体完成了什么（文件、路径、数量、结果）；"
                "② 若还有未完成部分，说明剩余什么；"
                "③ 给出 2～4 条可执行的下一步建议，并给出一句用户可直接复制发送的后续指令。"
                "禁止只说「已完成」或「请说继续」。"
            )
        else:
            hint = (
                "【系统提示】请根据上文，按「任务完成后的回复格式」向用户说明刚刚完成了什么，"
                "并给出具体的下一步建议；禁止空泛收尾。"
            )
        self.messages.append({"role": "user", "content": hint})
        finish = self._consume_stream(on_event, tools=False)
        if self._cancel_event.is_set():
            return CANCELLED_MESSAGE
        content = (finish.content or "").strip()
        if content:
            self.messages.append({"role": "assistant", "content": content})
            return self._finish_run(content)
        return self._finish_run(
            "本轮执行步骤较多，我暂时无法自动生成完整总结。"
            "你可以说「总结一下刚才做了什么，并告诉我下一步建议」，我会按你的要求整理。"
        )

    # ── 工具调用处理 ──

    def _latest_user_text(self) -> str:
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""

    def _execute_single_tool(
        self,
        name: str,
        args: dict[str, Any],
        tool_count: int,
        idx: int,
        on_event: EventCallback | None,
    ) -> str:
        """执行单个工具调用，包含安全评估和审批流程。返回工具结果文本。"""
        from friday.interaction_modes import ASK_BLOCK_REASON, normalize_mode, tool_allowed_in_mode

        mode = normalize_mode(getattr(self.settings, "interaction_mode", "agent"))
        if not tool_allowed_in_mode(name, mode):
            result = ASK_BLOCK_REASON
            if on_event:
                on_event("ask_blocked", {"tool_name": name, "message": result})
            meta = self.operation_meta or {}
            log_operation(
                name, args, result,
                session_id=str(meta.get("session_id", "")),
                trigger=str(meta.get("trigger", "chat")),
                schedule_id=str(meta.get("schedule_id", "")),
            )
            return result

        if name in {"run_powershell", "run_python", "run_python_script", "open_url"} and is_download_task_context(self._latest_user_text()):
            result = (
                f"工具 {name} 在下载任务中不可用。"
                f"请改用 download_software(软件名, 保存路径) 一次完成下载。"
            )
            meta = self.operation_meta or {}
            log_operation(
                name, args, result,
                session_id=str(meta.get("session_id", "")),
                trigger=str(meta.get("trigger", "chat")),
                schedule_id=str(meta.get("schedule_id", "")),
            )
            return result

        decision = evaluate_tool(
            self.settings,
            name,
            args,
            yolo_unlocked=getattr(self, "yolo_unlocked", False),
        )

        if not decision.allowed:
            result = decision.reason or "该操作已被安全策略阻止。"
            meta = self.operation_meta or {}
            log_operation(
                name, args, result,
                session_id=str(meta.get("session_id", "")),
                trigger=str(meta.get("trigger", "chat")),
                schedule_id=str(meta.get("schedule_id", "")),
            )
            return result

        approved: bool | None = None
        exec_args = dict(args)
        preview = summarize_preview(name, args)
        needs_approval = should_request_approval(self.settings, decision, self._turn_approval)
        if needs_approval:
            pending = PendingAction(
                tool_name=name,
                arguments=args,
                summary=summarize_action(name, args),
                risk=classify_tool(name),
                large_download=decision.large_download,
                download_size_bytes=decision.download_size_bytes,
                untrusted_download=decision.untrusted_download,
                trust_label=decision.trust_label,
            )
            if self._cancel_event.is_set():
                return CANCELLED_MESSAGE
            approved = self.request_approval(pending)
            if self._cancel_event.is_set():
                return CANCELLED_MESSAGE
            if not approved:
                self._turn_approval = TurnApprovalState()
                result = "用户拒绝了该操作。"
                meta = self.operation_meta or {}
                log_operation(
                    name, args, result,
                    session_id=str(meta.get("session_id", "")),
                    trigger=str(meta.get("trigger", "chat")),
                    schedule_id=str(meta.get("schedule_id", "")),
                    approved=False,
                )
                return result

            mark_turn_approved(self._turn_approval, decision)
            if decision.large_download:
                exec_args["_allow_large"] = True
            if decision.untrusted_download:
                exec_args["confirm_untrusted_source"] = True
                exec_args["_untrusted_approved"] = True

            # 审批通过后复查（设置可能在审批期间变更）
            recheck = evaluate_tool(self.settings, name, exec_args)
            if not recheck.allowed:
                result = recheck.reason or "该操作已被安全策略阻止。"
                meta = self.operation_meta or {}
                log_operation(
                    name, args, result,
                    session_id=str(meta.get("session_id", "")),
                    trigger=str(meta.get("trigger", "chat")),
                    schedule_id=str(meta.get("schedule_id", "")),
                    approved=True,
                )
                return result
        elif decision.needs_approval:
            approved = True
            mark_turn_approved(self._turn_approval, decision)
            if decision.large_download:
                exec_args["_allow_large"] = True
            if decision.untrusted_download:
                exec_args["confirm_untrusted_source"] = True
                exec_args["_untrusted_approved"] = True
            self._emit(on_event, "approval_auto", {
                "summary": describe_approval_plain(name, args),
                "tool_name": name,
            })

        self._emit(on_event, "tool_start", {
            "tool": name,
            "preview": preview,
            "step": idx,
            "tool_count": tool_count,
            "round": self._round_count + 1,
        })
        if self._cancel_event.is_set():
            return CANCELLED_MESSAGE

        pending_old_text = ""
        if name == "write_text_file":
            from friday.file_diff import read_text_if_exists

            pending_old_text = read_text_if_exists(str(args.get("path", "")))

        result = execute_tool(name, exec_args, cancel_event=self._cancel_event)
        if self._cancel_event.is_set() or result == CANCELLED_TOOL_MESSAGE:
            return CANCELLED_MESSAGE

        if name == "write_text_file" and result.startswith("已写入"):
            from friday.file_diff import build_file_change_payload

            path_arg = str(args.get("path", ""))
            payload = build_file_change_payload(
                path_arg,
                pending_old_text,
                str(args.get("content", "")),
            )
            self._emit(on_event, "file_change", payload)

        meta = self.operation_meta or {}
        entry = log_operation(
            name, args, result,
            session_id=str(meta.get("session_id", "")),
            trigger=str(meta.get("trigger", "chat")),
            schedule_id=str(meta.get("schedule_id", "")),
            approved=approved,
        )
        self._emit(on_event, "operation_logged", entry)
        if name == "generate_image":
            from friday.image_gen import extract_path_from_tool_result

            img_path = extract_path_from_tool_result(result)
            if img_path:
                self._emit(on_event, "image_generated", {"path": img_path})
        return result

    def _append_tool_result(self, call_id: str, name: str, result: str) -> None:
        """压缩并追加工具结果到消息历史。"""
        from friday.context import compress_tool_result

        original_len = len(result)
        compressed = compress_tool_result(name, result, max_chars=MAX_TOOL_RESULT_CHARS)
        if len(compressed) < original_len:
            _log.info(
                "工具 %s 输出压缩 (%d -> %d 字符)",
                name,
                original_len,
                len(compressed),
            )
        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": compressed,
        })

    def _execute_round(self, finish: ChatCompletionResult, on_event: EventCallback | None) -> None:
        """处理单轮工具调用列表。"""
        tool_count = len(finish.tool_calls)
        tool_names = [
            (c.get("function") or {}).get("name", "unknown") for c in finish.tool_calls
        ]
        self._emit(on_event, "progress", {
            "round": self._round_count + 1,
            "max_rounds": MAX_TOOL_ROUNDS,
            "tool_count": tool_count,
            "tools": tool_names,
        })

        for idx, call in enumerate(finish.tool_calls, 1):
            if self._cancel_event.is_set():
                break
            function = call.get("function") or {}
            name = str(function.get("name", ""))
            raw_args = str(function.get("arguments", ""))
            args = parse_tool_arguments(raw_args)
            call_id = str(call.get("id", ""))

            if "__parse_error__" in args:
                self._append_tool_result(
                    call_id,
                    name,
                    f"工具参数无效（JSON 解析失败）: {args['__parse_error__']}",
                )
                continue

            result = self._execute_single_tool(name, args, tool_count, idx, on_event)
            if result == CANCELLED_MESSAGE:
                break
            self._append_tool_result(call_id, name, result)

    # ── 主循环 ──

    def run(self, user_text: str, on_event: EventCallback | None = None) -> str:
        self._cancel_event.clear()
        from friday.agent_context import current_session_id

        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if session_id:
            current_session_id.set(session_id)
        # 保留 _turn_approval：当前对话内首次确认后，后续操作自动继续
        if is_download_task_context(user_text):
            hint = (
                "\n\n【当前任务：下载/安装软件】"
                "必须使用 download_software 或 download_file，严禁 run_powershell / open_url。"
                "一次 download_software 调用即可，不要分多步试探链接。"
            )
            user_text = user_text + hint
        self.messages.append({"role": "user", "content": user_text})

        for self._round_count in range(MAX_TOOL_ROUNDS):
            if self._cancel_event.is_set():
                _log.info("对话已取消 @ round %d", self._round_count)
                return self._finish_run(CANCELLED_MESSAGE)

            from friday.context import detect_repeated_tool_loop

            looping, loop_hint = detect_repeated_tool_loop(self.messages)
            if looping:
                self._emit(on_event, "progress", {
                    "round": self._round_count + 1,
                    "max_rounds": MAX_TOOL_ROUNDS,
                    "hint": loop_hint,
                })

            finish = self._consume_stream(on_event)
            if self._cancel_event.is_set():
                _log.info("对话已取消 @ round %d (流式响应)", self._round_count)
                return self._finish_run(CANCELLED_MESSAGE)

            # 记录 assistant 消息
            assistant_payload: dict[str, Any] = {"role": "assistant"}
            if finish.content:
                assistant_payload["content"] = finish.content
            if finish.tool_calls:
                assistant_payload["tool_calls"] = finish.tool_calls
            self.messages.append(assistant_payload)

            # 无工具调用 → 对话结束
            if not finish.tool_calls:
                _log.info("对话完成 | %s", self.brain.usage_summary())
                reply = (finish.content or "").strip()
                if not reply:
                    return self._wrap_up_reply(on_event, reason="empty_reply")
                return self._finish_run(reply)

            # 执行工具轮次
            self._execute_round(finish, on_event)
            if self._cancel_event.is_set():
                _log.info("对话已取消 @ round %d (工具执行)", self._round_count)
                return self._finish_run(CANCELLED_MESSAGE)

        _log.warning("达到最大轮次限制 rounds=%d | %s", MAX_TOOL_ROUNDS, self.brain.usage_summary())
        return self._wrap_up_reply(on_event, reason="round_limit")
