from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import threading

from friday.brain import ChatCompletionResult, DeepSeekBrain, UsageStats
from friday.config import MAX_TOOL_RESULT_CHARS, MAX_TOOL_ROUNDS, MAX_TOOL_ROUNDS_CAP
from friday.logging_config import get_logger
from friday.safety import (
    PendingAction,
    RiskLevel,
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
        self._frozen_prefix: Any = None
        self._loop_hint_injected = False
        self._probe_hint_injected = False
        self._python_env_info_used = False
        self._context_rebuilt = False
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
        self._pin_prefix(force=True)

    def _finalize_usage(self) -> None:
        """将本轮 brain 计数累加到会话总量，并清零本轮计数。"""
        self.session_prompt_tokens += self.brain.usage_stats.prompt_tokens or self.brain.total_prompt_tokens
        self.session_completion_tokens += (
            self.brain.usage_stats.completion_tokens or self.brain.total_completion_tokens
        )
        self.brain.usage_stats = UsageStats()
        self.brain.total_prompt_tokens = 0
        self.brain.total_completion_tokens = 0

    def usage_snapshot(self) -> dict[str, int | float]:
        stats = self.brain.usage_stats
        prompt = self.session_prompt_tokens + stats.prompt_tokens + self.brain.total_prompt_tokens
        completion = (
            self.session_completion_tokens + stats.completion_tokens + self.brain.total_completion_tokens
        )
        return {
            "tokens_prompt": int(prompt),
            "tokens_completion": int(completion),
            "tokens_total": int(prompt + completion),
        }

    def _finish_run(self, content: str) -> str:
        if self.brain._turn_api_calls > 0:
            _log.info("本次对话共调用 %d 次 API | %s", self.brain._turn_api_calls, self.brain.usage_summary())
        self._finalize_usage()
        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if session_id:
            try:
                from friday.artifacts import finalize_agent_turn

                finalize_agent_turn(session_id)
            except Exception:
                _log.exception("生成物回收失败 | session=%s", session_id)
        return content

    def load_history(self, messages: list[dict[str, Any]] | None) -> None:
        if not messages:
            self.reset()
            return
        from friday.context import sanitize_agent_messages

        self.messages = sanitize_agent_messages(list(messages))
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

        from friday.context import sanitize_agent_messages

        sanitized = sanitize_agent_messages(self.messages)
        if sanitized != self.messages:
            _log.warning("已修复会话中损坏的 tool 消息顺序")
            self.messages = sanitized

        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if session_id:
            from friday.plan import upsert_plan_anchor_for_session

            self.messages = upsert_plan_anchor_for_session(session_id, self.messages)

            from friday.context_assembler import rebuild_messages

            rebuilt, did_rebuild = (self.messages, False)
            if not self._context_rebuilt:
                rebuilt, did_rebuild = rebuild_messages(
                    session_id,
                    self.messages,
                    settings=self.settings,
                )
            if did_rebuild:
                self._context_rebuilt = True
                self.messages = rebuilt
                self._emit(on_event, "context_rebuild", {"session_id": session_id})
                try:
                    from friday.sessions import get_session, save_session_fields

                    session = get_session(session_id)
                    if session:
                        save_session_fields(session_id, context_cycle=session.context_cycle + 1)
                except Exception:
                    _log.debug("context_cycle 更新失败", exc_info=True)

        prepared = self.brain.prepare_messages(
            self.messages,
            tool_definitions=self._frozen_prefix.tool_definitions if tools else None,
        )
        if prepared is not self.messages and prepared != self.messages:
            self.messages = prepared

        if session_id:
            from friday.checkpoint_writer import maybe_schedule_checkpoint

            maybe_schedule_checkpoint(session_id, self.messages, settings=self.settings)

        tool_defs = self._frozen_prefix.tool_definitions if tools else None

        stream_started = False
        finish: ChatCompletionResult | None = None
        pending_tool_names: list[str] = []

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
            elif kind == "reasoning_delta":
                self._emit(on_event, "reasoning_delta", {"delta": payload})
            elif kind == "finish":
                finish = payload

        if finish is None:
            finish = ChatCompletionResult()

        if finish.tool_calls:
            for call in finish.tool_calls:
                name = str((call.get("function") or {}).get("name", "")).strip()
                if name and name not in pending_tool_names:
                    pending_tool_names.append(name)
            if pending_tool_names:
                from friday.tools.registry import tool_display_name

                labels = [tool_display_name(n) for n in pending_tool_names]
                self._emit(on_event, "agent_step", {
                    "message": f"准备执行：{'、'.join(labels)}",
                })

        if finish.tool_calls and stream_started:
            self._emit(on_event, "assistant_clear", {})

        return finish

    def _last_round_tool_results(
        self,
        finish: ChatCompletionResult,
    ) -> list[tuple[str, dict[str, Any], str]]:
        meta: dict[str, tuple[str, dict[str, Any]]] = {}
        order: list[str] = []
        for call in finish.tool_calls:
            name, args, call_id = self._parse_tool_call(call)
            if not call_id:
                continue
            order.append(call_id)
            meta[call_id] = (name, args)
        by_id: dict[str, str] = {}
        for msg in self.messages:
            if msg.get("role") != "tool":
                continue
            cid = str(msg.get("tool_call_id", ""))
            if cid in meta:
                by_id[cid] = str(msg.get("content", ""))
        return [(meta[cid][0], meta[cid][1], by_id.get(cid, "")) for cid in order if cid in meta]

    def _try_fast_finish_after_tools(
        self,
        finish: ChatCompletionResult,
    ) -> str | None:
        from friday.fast_finish import try_fast_finish_reply

        session_id = str((self.operation_meta or {}).get("session_id", ""))
        pending = 0
        if session_id:
            from friday.plan import get_session_plan

            todos = get_session_plan(session_id).get("todos") or []
            pending = sum(
                1 for item in todos if isinstance(item, dict) and not item.get("done")
            )
        return try_fast_finish_reply(
            self._last_round_tool_results(finish),
            user_goal=self._approval_user_goal(),
            pending_todos=pending,
        )

    def _wrap_up_reply(self, on_event: EventCallback | None, *, reason: str = "round_limit") -> str:
        """工具轮次用尽或需收尾时，让模型用自然语言总结已完成工作与下一步计划。"""
        if self._cancel_event.is_set():
            return CANCELLED_MESSAGE

        if reason == "round_limit":
            hint = (
                "【系统提示】本轮工具调用次数已达上限，请不要再调用任何工具。"
                "请仅根据上文已执行的操作向用户回复：简单任务 2～4 句说明交付物即可；"
                "复杂任务再按「任务完成后的回复格式」说明完成了什么、剩余项与下一步。"
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

    def _max_tool_rounds(self) -> int:
        """复杂计划任务自动放宽工具轮次上限。"""
        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if not session_id:
            return MAX_TOOL_ROUNDS
        from friday.plan import get_session_plan

        plan = get_session_plan(session_id)
        todos = plan.get("todos") or []
        pending = sum(
            1 for item in todos if isinstance(item, dict) and not item.get("done")
        )
        extra = min(pending * 2, 12)
        return min(MAX_TOOL_ROUNDS_CAP, MAX_TOOL_ROUNDS + extra)

    def _can_parallelize_round(self, tool_names: list[str]) -> bool:
        if len(tool_names) < 2:
            return False
        from friday.plan import PLAN_TOOL_NAMES

        for name in tool_names:
            if not name or name in PLAN_TOOL_NAMES:
                return False
            if classify_tool(name) != RiskLevel.READ:
                return False
        return True

    def _latest_user_text(self) -> str:
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                return str(msg.get("content", ""))
        return ""

    def _approval_user_goal(self) -> str:
        for msg in reversed(self.messages):
            if msg.get("role") != "user":
                continue
            text = str(msg.get("content", "")).strip()
            if not text or text.startswith("【系统提示】"):
                continue
            if "\n\n【当前任务：" in text:
                text = text.split("\n\n【当前任务：", 1)[0].strip()
            if "\n\n【复杂任务提示】" in text:
                text = text.split("\n\n【复杂任务提示】", 1)[0].strip()
            return text
        return ""

    def _latest_assistant_text(self) -> str:
        for msg in reversed(self.messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
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

        if name == "python_env_info" and self._python_env_info_used:
            return (
                "本任务已调用过 python_env_info，请根据已有环境信息编写完整脚本，"
                "一次 run_python 或 run_python_script 执行。"
            )
        if name == "python_env_info":
            self._python_env_info_used = True

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
                user_goal=self._approval_user_goal(),
                assistant_note=self._latest_assistant_text(),
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

        meta = self.operation_meta or {}
        shell_deliver_snapshot: set[str] | None = None
        if (
            str(meta.get("trigger", "")) == "weixin"
            and name in {"run_powershell", "run_python", "run_python_script"}
        ):
            from friday.weixin.deliverables import snapshot_deliverable_path_keys as _snap_keys

            shell_deliver_snapshot = _snap_keys(self.settings)

        on_heartbeat = None
        if on_event and name in ("generate_image", "describe_image"):
            def on_heartbeat() -> None:
                self._emit(on_event, "progress", {
                    "tools": [name],
                    "heartbeat": True,
                    "step": idx,
                    "tool_count": tool_count,
                    "round": self._round_count + 1,
                })

        result = execute_tool(
            name,
            exec_args,
            cancel_event=self._cancel_event,
            on_heartbeat=on_heartbeat,
        )
        if self._cancel_event.is_set() or result == CANCELLED_TOOL_MESSAGE:
            return CANCELLED_MESSAGE

        self._maybe_update_plan_from_tool(name, args, result, on_event)

        if name == "write_text_file" and result.startswith("已写入"):
            from friday.file_diff import build_file_change_payload

            path_arg = str(args.get("path", ""))
            payload = build_file_change_payload(
                path_arg,
                pending_old_text,
                str(args.get("content", "")),
            )
            self._emit(on_event, "file_change", payload)

        entry = log_operation(
            name, args, result,
            session_id=str(meta.get("session_id", "")),
            trigger=str(meta.get("trigger", "chat")),
            schedule_id=str(meta.get("schedule_id", "")),
            approved=approved,
        )
        self._emit(on_event, "operation_logged", entry)
        from friday.weixin.deliverables import (
            extract_copy_file_destination,
            extract_deliverable_path,
            extract_move_file_destination,
            file_generated_kind_for_path,
            is_text_file_deliverable,
            list_deliverables_since_path_snapshot,
            should_emit_weixin_copy_deliverable,
        )

        def _emit_weixin_file_generated(path: str) -> None:
            if not should_emit_weixin_copy_deliverable(path, settings=self.settings):
                return
            kind = file_generated_kind_for_path(path)
            if kind:
                self._emit(on_event, "file_generated", {"path": path, "kind": kind})

        if name == "generate_image":
            img_path = extract_deliverable_path(name, result)
            if img_path:
                self._emit(on_event, "image_generated", {"path": img_path})
        elif name == "screenshot":
            shot_path = extract_deliverable_path(name, result)
            if shot_path:
                self._emit(on_event, "image_generated", {"path": shot_path})
        elif name in {"create_docx", "create_pptx"}:
            doc_path = extract_deliverable_path(name, result)
            if doc_path:
                self._emit(on_event, "file_generated", {"path": doc_path, "kind": "document"})
        elif name == "write_text_file" and result.startswith("已写入"):
            text_path = extract_deliverable_path(name, result)
            if text_path and is_text_file_deliverable(text_path):
                self._emit(on_event, "file_generated", {"path": text_path, "kind": "text"})
        elif name == "copy_file" and str(meta.get("trigger", "")) == "weixin":
            dest = extract_copy_file_destination(result)
            if dest:
                _emit_weixin_file_generated(dest)
        elif name == "move_file" and str(meta.get("trigger", "")) == "weixin":
            dest = extract_move_file_destination(result)
            if dest:
                _emit_weixin_file_generated(dest)
        elif (
            name in {"run_powershell", "run_python", "run_python_script"}
            and str(meta.get("trigger", "")) == "weixin"
            and shell_deliver_snapshot is not None
            and (result or "").strip().startswith("exit=0")
        ):
            for delivered_path in list_deliverables_since_path_snapshot(
                self.settings,
                before_keys=shell_deliver_snapshot,
            ):
                _emit_weixin_file_generated(str(delivered_path))
        return result

    def _emit_plan_update(self, on_event: EventCallback | None) -> None:
        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if not session_id:
            return
        from friday.plan import get_session_plan

        plan = get_session_plan(session_id)
        if plan.get("ok"):
            self._emit(on_event, "plan_updated", plan)

    def _maybe_update_plan_from_tool(
        self,
        name: str,
        args: dict[str, Any],
        result: str,
        on_event: EventCallback | None,
    ) -> None:
        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if not session_id:
            return
        from friday.plan import PLAN_TOOL_NAMES, auto_complete_todos_from_tool, sync_todos_from_plan

        if name in PLAN_TOOL_NAMES:
            if name == "update_session_plan":
                sync_todos_from_plan(session_id)
            self._emit_plan_update(on_event)
            return
        changed = auto_complete_todos_from_tool(session_id, name, args, result)
        if changed.get("changed"):
            self._emit_plan_update(on_event)

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
        session_id = str((self.operation_meta or {}).get("session_id", ""))
        if session_id and len(result) > 120:
            try:
                from friday.checkpoint_writer import append_session_note

                snippet = result[:400].replace("\n", " ")
                append_session_note(session_id, f"工具 {name}: {snippet}")
            except Exception:
                _log.debug("append_session_note 跳过", exc_info=True)

    def _parse_tool_call(self, call: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        function = call.get("function") or {}
        name = str(function.get("name", ""))
        raw_args = str(function.get("arguments", ""))
        args = parse_tool_arguments(raw_args)
        call_id = str(call.get("id", ""))
        return name, args, call_id

    def _execute_round(self, finish: ChatCompletionResult, on_event: EventCallback | None) -> None:
        """处理单轮工具调用列表。"""
        tool_count = len(finish.tool_calls)
        tool_names = [
            (c.get("function") or {}).get("name", "unknown") for c in finish.tool_calls
        ]
        max_rounds = self._max_tool_rounds()
        self._emit(on_event, "progress", {
            "round": self._round_count + 1,
            "max_rounds": max_rounds,
            "tool_count": tool_count,
            "tools": tool_names,
        })

        parsed: list[tuple[str, dict[str, Any], str]] = []
        for call in finish.tool_calls:
            name, args, call_id = self._parse_tool_call(call)
            if "__parse_error__" in args:
                self._append_tool_result(
                    call_id,
                    name,
                    f"工具参数无效（JSON 解析失败）: {args['__parse_error__']}",
                )
                continue
            parsed.append((name, args, call_id))

        if not parsed:
            return

        if self._can_parallelize_round([name for name, _, _ in parsed]):
            results: dict[str, str] = {}
            with ThreadPoolExecutor(max_workers=min(4, len(parsed))) as pool:
                futures = {
                    pool.submit(
                        self._execute_single_tool,
                        name,
                        args,
                        tool_count,
                        idx,
                        on_event,
                    ): call_id
                    for idx, (name, args, call_id) in enumerate(parsed, 1)
                }
                for future in as_completed(futures):
                    if self._cancel_event.is_set():
                        break
                    call_id = futures[future]
                    try:
                        results[call_id] = future.result()
                    except Exception as exc:
                        _log.exception("并行工具执行失败")
                        results[call_id] = f"工具执行异常: {exc}"
            if self._cancel_event.is_set():
                return
            for name, args, call_id in parsed:
                result = results.get(call_id, "工具未返回结果")
                if result == CANCELLED_MESSAGE:
                    break
                self._append_tool_result(call_id, name, result)
            return

        for idx, (name, args, call_id) in enumerate(parsed, 1):
            if self._cancel_event.is_set():
                break
            result = self._execute_single_tool(name, args, tool_count, idx, on_event)
            if result == CANCELLED_MESSAGE:
                break
            self._append_tool_result(call_id, name, result)

    # ── 主循环 ──

    def run(self, user_text: str, on_event: EventCallback | None = None) -> str:
        self._cancel_event.clear()
        self._loop_hint_injected = False
        self._probe_hint_injected = False
        self._python_env_info_used = False
        self._context_rebuilt = False
        self.brain.reset_turn_api_calls()
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
        from friday.plan import maybe_append_complex_task_plan_hint

        user_text = maybe_append_complex_task_plan_hint(user_text, session_id)
        self.messages.append({"role": "user", "content": user_text})

        max_rounds = self._max_tool_rounds()
        for self._round_count in range(max_rounds):
            if self._cancel_event.is_set():
                _log.info("对话已取消 @ round %d", self._round_count)
                return self._finish_run(CANCELLED_MESSAGE)

            if self._round_count == 0:
                self._emit(on_event, "agent_step", {"message": "理解任务并规划步骤…"})
            else:
                self._emit(on_event, "agent_step", {
                    "message": f"第 {self._round_count + 1} 轮：正在选择下一步…",
                })

            from friday.context import detect_probe_tool_thrash, detect_repeated_tool_loop

            looping, loop_hint = detect_repeated_tool_loop(self.messages)
            if looping:
                self._emit(on_event, "progress", {
                    "round": self._round_count + 1,
                    "max_rounds": max_rounds,
                    "hint": loop_hint,
                })
                if not self._loop_hint_injected:
                    self.messages.append({
                        "role": "user",
                        "content": f"【系统提示】{loop_hint} 请立即调整策略，不要继续相同调用。",
                    })
                    self._loop_hint_injected = True

            probing, probe_hint = detect_probe_tool_thrash(self.messages)
            if probing and not self._probe_hint_injected:
                self._emit(on_event, "progress", {
                    "round": self._round_count + 1,
                    "max_rounds": max_rounds,
                    "hint": probe_hint,
                })
                self.messages.append({
                    "role": "user",
                    "content": f"【系统提示】{probe_hint}",
                })
                self._probe_hint_injected = True

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
                reply = (finish.content or "").strip()
                if not reply:
                    return self._wrap_up_reply(on_event, reason="empty_reply")
                if session_id:
                    from friday.goal_verifier import verify_goal_complete

                    verdict = verify_goal_complete(session_id, reply, settings=self.settings, brain=self.brain)
                    if verdict.get("block"):
                        hint = str(verdict.get("reason") or "任务可能尚未完成")
                        self.messages.append({
                            "role": "user",
                            "content": f"【系统提示】{hint} 请继续执行未完成项，不要过早收尾。",
                        })
                        continue
                if session_id:
                    from friday.plan import auto_complete_todos_from_assistant

                    assistant_result = auto_complete_todos_from_assistant(session_id, reply)
                    if assistant_result.get("changed"):
                        self._emit_plan_update(on_event)
                return self._finish_run(reply)

            # 执行工具轮次
            self._execute_round(finish, on_event)
            if self._cancel_event.is_set():
                _log.info("对话已取消 @ round %d (工具执行)", self._round_count)
                return self._finish_run(CANCELLED_MESSAGE)

            fast_reply = self._try_fast_finish_after_tools(finish)
            if fast_reply:
                _log.info("快速收尾 | round=%d skip_summary=1", self._round_count + 1)
                self.messages.append({"role": "assistant", "content": fast_reply})
                if session_id:
                    from friday.plan import auto_complete_todos_from_assistant

                    assistant_result = auto_complete_todos_from_assistant(session_id, fast_reply)
                    if assistant_result.get("changed"):
                        self._emit_plan_update(on_event)
                return self._finish_run(fast_reply)

        _log.warning("达到最大轮次限制 rounds=%d", max_rounds)
        return self._wrap_up_reply(on_event, reason="round_limit")
