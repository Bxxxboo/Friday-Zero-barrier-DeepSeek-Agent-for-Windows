"""会话检查点写入器 —— 异步单写者，维护 checkpoint.md / notes.md。"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from friday.config import (
    CHECKPOINT_FIELD_KEYS,
    CHECKPOINT_FIELD_LABELS,
    CHECKPOINT_MARKER,
    CHECKPOINT_TRIGGER_RATIOS,
)
from friday.io_utils import atomic_write_json, atomic_write_text, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("checkpoint_writer")

_SESSION_LOCKS: dict[str, threading.Lock] = {}
_SCHEDULED_MAX_TIER: dict[str, int] = {}
_WORKER_STARTED = False
_TASK_QUEUE: queue.Queue[tuple[str, Callable[[], None]]] = queue.Queue()


def _session_lock(session_id: str) -> threading.Lock:
    lock = _SESSION_LOCKS.get(session_id)
    if lock is None:
        lock = threading.Lock()
        _SESSION_LOCKS[session_id] = lock
    return lock


def session_sidecar_dir(session_id: str) -> Path:
    path = get_appdata_dir() / "sessions" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def checkpoint_path(session_id: str) -> Path:
    return session_sidecar_dir(session_id) / "checkpoint.md"


def checkpoint_meta_path(session_id: str) -> Path:
    return session_sidecar_dir(session_id) / "checkpoint_meta.json"


def notes_path(session_id: str) -> Path:
    return session_sidecar_dir(session_id) / "notes.md"


def _ensure_worker() -> None:
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    _WORKER_STARTED = True
    thread = threading.Thread(target=_worker_loop, name="checkpoint-writer", daemon=True)
    thread.start()


def _worker_loop() -> None:
    while True:
        session_id, fn = _TASK_QUEUE.get()
        try:
            fn()
        except Exception:
            _log.exception("checkpoint 写入失败 | session=%s", session_id)
        finally:
            _TASK_QUEUE.task_done()


def _enqueue(session_id: str, fn: Callable[[], None]) -> None:
    _ensure_worker()
    _TASK_QUEUE.put((session_id, fn))


@dataclass
class CheckpointMeta:
    version: int = 0
    last_trigger_tier: int = -1
    updated_at: float = 0.0
    trigger_ratio: float = 0.0
    token_count: int = 0
    budget: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "last_trigger_tier": self.last_trigger_tier,
            "updated_at": self.updated_at,
            "trigger_ratio": self.trigger_ratio,
            "token_count": self.token_count,
            "budget": self.budget,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CheckpointMeta:
        if not isinstance(data, dict):
            return cls()
        return cls(
            version=int(data.get("version", 0) or 0),
            last_trigger_tier=int(data.get("last_trigger_tier", -1) or -1),
            updated_at=float(data.get("updated_at", 0) or 0),
            trigger_ratio=float(data.get("trigger_ratio", 0) or 0),
            token_count=int(data.get("token_count", 0) or 0),
            budget=int(data.get("budget", 0) or 0),
        )


@dataclass
class CheckpointFields:
    goal_context: str = ""
    current_state: str = ""
    key_paths: str = ""
    completed: str = ""
    pending: str = ""
    decisions: str = ""
    user_prefs: str = ""
    errors_avoid: str = ""
    tools_summary: str = ""
    todos_snapshot: str = ""
    resume_hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return {key: getattr(self, key, "") for key in CHECKPOINT_FIELD_KEYS}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CheckpointFields:
        values = {key: "" for key in CHECKPOINT_FIELD_KEYS}
        if isinstance(data, dict):
            for key in CHECKPOINT_FIELD_KEYS:
                values[key] = str(data.get(key, "") or "").strip()
        return cls(**values)


_SECTION_RE = re.compile(
    r"^##\s+(?P<label>.+?)\s*$",
    re.MULTILINE,
)


def _label_to_key(label: str) -> str | None:
    cleaned = label.strip()
    for key, name in CHECKPOINT_FIELD_LABELS.items():
        if name == cleaned:
            return key
    return None


def parse_checkpoint_md(content: str) -> tuple[CheckpointMeta, CheckpointFields]:
    """解析 checkpoint.md 正文与内嵌 metadata JSON。"""
    text = str(content or "")
    meta = CheckpointMeta()
    fields = CheckpointFields()

    meta_match = re.search(r"<!--\s*checkpoint-meta\s*(\{.*?\})\s*-->", text, re.DOTALL)
    if meta_match:
        try:
            meta = CheckpointMeta.from_dict(json.loads(meta_match.group(1)))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        text = text[: meta_match.start()] + text[meta_match.end() :]

    matches = list(_SECTION_RE.finditer(text))
    for idx, match in enumerate(matches):
        key = _label_to_key(match.group("label"))
        if not key:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        setattr(fields, key, body)

    return meta, fields


def render_checkpoint_md(fields: CheckpointFields, meta: CheckpointMeta) -> str:
    lines = [
        f"# 工作记忆 · 检查点 v{meta.version}",
        "",
        f"<!-- checkpoint-meta {json.dumps(meta.to_dict(), ensure_ascii=False)} -->",
        "",
    ]
    for key in CHECKPOINT_FIELD_KEYS:
        label = CHECKPOINT_FIELD_LABELS[key]
        body = getattr(fields, key, "").strip() or "（暂无）"
        lines.extend([f"## {label}", "", body, ""])
    return "\n".join(lines).rstrip() + "\n"


def load_checkpoint_meta(session_id: str) -> CheckpointMeta:
    data = load_json(checkpoint_meta_path(session_id), default={})
    if isinstance(data, dict):
        return CheckpointMeta.from_dict(data)
    return CheckpointMeta()


def save_checkpoint_meta(session_id: str, meta: CheckpointMeta) -> None:
    atomic_write_json(checkpoint_meta_path(session_id), meta.to_dict())


def read_checkpoint(session_id: str) -> dict[str, Any]:
    """供 API / assembler 读取。"""
    path = checkpoint_path(session_id)
    if not path.exists():
        return {
            "ok": True,
            "exists": False,
            "version": 0,
            "updated_at": 0.0,
            "markdown": "",
            "fields": CheckpointFields().as_dict(),
        }
    content = path.read_text(encoding="utf-8")
    meta, fields = parse_checkpoint_md(content)
    return {
        "ok": True,
        "exists": True,
        "version": meta.version,
        "updated_at": meta.updated_at,
        "markdown": content,
        "fields": fields.as_dict(),
        "meta": meta.to_dict(),
    }


def append_session_note(session_id: str, text: str) -> None:
    """主 Agent append-only 通道。"""
    cleaned = str(text or "").strip()
    if not cleaned or not session_id:
        return
    path = notes_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    block = f"\n\n### {stamp}\n{cleaned}\n"
    with _session_lock(session_id):
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing.rstrip() + block, encoding="utf-8")
        else:
            path.write_text(f"# 会话笔记\n{block.lstrip()}", encoding="utf-8")


def _read_notes(session_id: str) -> str:
    path = notes_path(session_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _clear_notes(session_id: str) -> None:
    path = notes_path(session_id)
    if path.exists():
        path.unlink()


def _extract_paths(text: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"[A-Za-z]:\\[^\s\"'<>|]+", text):
        piece = match.group(0).rstrip(".,;)")
        if piece and piece not in found:
            found.append(piece)
    for match in re.finditer(r"/[\w./-]{3,}", text):
        piece = match.group(0).rstrip(".,;)")
        if piece.startswith("//"):
            continue
        if piece not in found:
            found.append(piece)
    return found[:20]


def _merge_notes_into_fields(fields: CheckpointFields, notes: str) -> CheckpointFields:
    if not notes.strip():
        return fields
    merged = CheckpointFields(**fields.as_dict())
    appendix = notes.strip()
    if merged.tools_summary and merged.tools_summary != "（暂无）":
        merged.tools_summary = f"{merged.tools_summary}\n\n{appendix}"
    else:
        merged.tools_summary = appendix
    paths = _extract_paths(notes)
    if paths:
        path_block = "\n".join(f"- {p}" for p in paths)
        if merged.key_paths and merged.key_paths != "（暂无）":
            merged.key_paths = f"{merged.key_paths}\n{path_block}"
        else:
            merged.key_paths = path_block
    return merged


def _summarize_for_checkpoint(
    *,
    session_id: str,
    messages: list[dict[str, Any]],
    previous: CheckpointFields,
    notes: str,
    summarize_fn: Callable[[list[dict[str, Any]]], str] | None = None,
) -> CheckpointFields:
    from friday.prefix_cache import deterministic_summary, format_messages_for_summary
    from friday.plan import get_session_plan

    batch = [m for m in messages if m.get("role") in {"user", "assistant", "tool"}][-40:]
    if summarize_fn:
        summary_body = summarize_fn(batch)
    else:
        summary_body = deterministic_summary(batch)

    plan = get_session_plan(session_id)
    plan_md = str(plan.get("plan_markdown", "") or "").strip()
    todos = plan.get("todos") or []
    open_todos = [
        str(t.get("text", "")).strip()
        for t in todos
        if isinstance(t, dict) and not t.get("done")
    ]
    done_todos = [
        str(t.get("text", "")).strip()
        for t in todos
        if isinstance(t, dict) and t.get("done")
    ]

    fields = CheckpointFields(**previous.as_dict())
    if plan_md:
        fields.goal_context = plan_md[:1200]
    elif not fields.goal_context:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = str(msg.get("content", "")).strip()
                if content and not content.startswith("【系统提示】"):
                    fields.goal_context = content[:600]
                    break

    fields.current_state = summary_body[:2000]
    paths = _extract_paths(format_messages_for_summary(batch, max_chars=8000))
    if paths:
        fields.key_paths = "\n".join(f"- {p}" for p in paths)
    if done_todos:
        fields.completed = "\n".join(f"- {t}" for t in done_todos[:12])
    if open_todos:
        fields.pending = "\n".join(f"- {t}" for t in open_todos[:12])
        fields.resume_hint = f"继续完成：{open_todos[0]}"
    elif not fields.resume_hint:
        fields.resume_hint = "可直接说「继续」或补充新的子任务。"

    if todos:
        lines = []
        for item in todos[:20]:
            if not isinstance(item, dict):
                continue
            mark = "x" if item.get("done") else " "
            lines.append(f"- [{mark}] {str(item.get('text', '')).strip()}")
        fields.todos_snapshot = "\n".join(lines)

    fields = _merge_notes_into_fields(fields, notes)
    return fields


def _write_checkpoint_locked(
    session_id: str,
    *,
    tier: int,
    ratio: float,
    token_count: int,
    budget: int,
    messages: list[dict[str, Any]],
    summarize_fn: Callable[[list[dict[str, Any]]], str] | None = None,
) -> CheckpointMeta:
    with _session_lock(session_id):
        prev_meta = load_checkpoint_meta(session_id)
        prev_fields = CheckpointFields()
        ck_path = checkpoint_path(session_id)
        if ck_path.exists():
            _, prev_fields = parse_checkpoint_md(ck_path.read_text(encoding="utf-8"))

        notes = _read_notes(session_id)
        fields = _summarize_for_checkpoint(
            session_id=session_id,
            messages=messages,
            previous=prev_fields,
            notes=notes,
            summarize_fn=summarize_fn,
        )

        new_meta = CheckpointMeta(
            version=prev_meta.version + 1,
            last_trigger_tier=max(prev_meta.last_trigger_tier, tier),
            updated_at=time.time(),
            trigger_ratio=ratio,
            token_count=token_count,
            budget=budget,
        )
        content = render_checkpoint_md(fields, new_meta)
        atomic_write_text(ck_path, content)
        save_checkpoint_meta(session_id, new_meta)
        if notes:
            _clear_notes(session_id)

        try:
            from friday.sessions import save_session_fields

            save_session_fields(session_id, checkpoint_version=new_meta.version)
        except Exception:
            _log.exception("更新 session checkpoint_version 失败 | id=%s", session_id)

        try:
            from friday.workspace_memory import maybe_promote_from_checkpoint

            maybe_promote_from_checkpoint(session_id, fields)
        except Exception:
            _log.debug("workspace memory 晋升跳过 | id=%s", session_id, exc_info=True)

        _log.info(
            "checkpoint 已更新 | session=%s version=%d tier=%d ratio=%.2f",
            session_id,
            new_meta.version,
            tier,
            ratio,
        )
        return new_meta


def write_checkpoint_sync(
    session_id: str,
    *,
    tier: int,
    ratio: float,
    token_count: int,
    budget: int,
    messages: list[dict[str, Any]],
    summarize_fn: Callable[[list[dict[str, Any]]], str] | None = None,
) -> CheckpointMeta:
    return _write_checkpoint_locked(
        session_id,
        tier=tier,
        ratio=ratio,
        token_count=token_count,
        budget=budget,
        messages=messages,
        summarize_fn=summarize_fn,
    )


def checkpoint_tier_for_ratio(ratio: float) -> int:
    """返回应触发的最高档位索引（-1 表示未达 20%）。"""
    tier = -1
    for idx, threshold in enumerate(CHECKPOINT_TRIGGER_RATIOS):
        if ratio >= threshold:
            tier = idx
    return tier


def maybe_schedule_checkpoint(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    settings: Any | None = None,
) -> bool:
    """按 token 比例调度异步 checkpoint 写入。返回是否已调度。"""
    if not session_id or not messages:
        return False

    from friday.storage import UserSettings, load_settings

    cfg = settings if isinstance(settings, UserSettings) else load_settings()
    if not getattr(cfg, "context_smart_enabled", True):
        return False

    from friday.brain import compute_context_meter

    meter = compute_context_meter(cfg, messages)
    ratio = float(meter.get("budget_ratio", 0) or 0)
    tier = checkpoint_tier_for_ratio(ratio)
    if tier < 0:
        return False

    with _session_lock(session_id):
        meta = load_checkpoint_meta(session_id)
        scheduled = _SCHEDULED_MAX_TIER.get(session_id, -1)
        effective_tier = max(meta.last_trigger_tier, scheduled)
        if tier <= effective_tier:
            return False
        _SCHEDULED_MAX_TIER[session_id] = tier

    token_count = int(meter.get("context_tokens", 0) or 0)
    budget = int(meter.get("context_budget", 0) or 0)

    def _job() -> None:
        try:
            summarize_fn = None
            try:
                from friday.brain import DeepSeekBrain

                brain = DeepSeekBrain(cfg)

                def _fn(batch: list[dict[str, Any]]) -> str:
                    return brain._summarize_message_batch(batch)

                summarize_fn = _fn
            except Exception:
                _log.debug("checkpoint LLM 摘要不可用，使用 deterministic fallback", exc_info=True)

            write_checkpoint_sync(
                session_id,
                tier=tier,
                ratio=ratio,
                token_count=token_count,
                budget=budget,
                messages=messages,
                summarize_fn=summarize_fn,
            )
        finally:
            with _session_lock(session_id):
                done = load_checkpoint_meta(session_id).last_trigger_tier
                if _SCHEDULED_MAX_TIER.get(session_id, -1) <= done:
                    _SCHEDULED_MAX_TIER.pop(session_id, None)

    _enqueue(session_id, _job)
    return True


def format_checkpoint_for_prompt(session_id: str, *, max_chars: int = 3200) -> str:
    data = read_checkpoint(session_id)
    if not data.get("exists"):
        return ""
    fields = CheckpointFields.from_dict(data.get("fields"))
    parts = [f"{CHECKPOINT_MARKER}"]
    for key in CHECKPOINT_FIELD_KEYS:
        body = getattr(fields, key, "").strip()
        if not body or body == "（暂无）":
            continue
        label = CHECKPOINT_FIELD_LABELS[key]
        parts.append(f"### {label}\n{body}")
    text = "\n\n".join(parts).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...(检查点已截断)"
