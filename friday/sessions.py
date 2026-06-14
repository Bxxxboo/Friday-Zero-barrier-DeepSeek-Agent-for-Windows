"""会话管理 —— 持久化聊天会话到 %APPDATA%/Friday/sessions/。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from friday.config import MAX_PERSISTED_TOOL_CHARS, SESSION_FORMAT_VERSION
from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("sessions")


@dataclass
class SessionSummary:
    id: str
    title: str
    updated_at: float
    created_at: float


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: float
    updated_at: float
    agent_messages: list[dict[str, Any]] = field(default_factory=list)
    display_messages: list[dict[str, Any]] = field(default_factory=list)
    title_pinned: bool = False
    plan_markdown: str = ""
    todos: list[dict[str, Any]] = field(default_factory=list)
    checkpoint_version: int = 0
    context_cycle: int = 0
    workspace_id: str = ""
    source: str = "desktop"

    def to_summary(self) -> SessionSummary:
        return SessionSummary(
            id=self.id,
            title=self.title,
            updated_at=self.updated_at,
            created_at=self.created_at,
        )


def _sessions_dir() -> Path:
    path = get_appdata_dir() / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path() -> Path:
    return get_appdata_dir() / "sessions_index.json"


def _session_path(session_id: str) -> Path:
    return _sessions_dir() / f"{session_id}.json"


def _read_index() -> dict[str, Any]:
    path = _index_path()
    data = load_json(path)
    if not isinstance(data, dict):
        return {"active_session_id": "", "order": []}
    return {
        "active_session_id": str(data.get("active_session_id", "")),
        "order": [str(item) for item in data.get("order", [])],
    }


def _write_index(active_session_id: str, order: list[str]) -> None:
    atomic_write_json(
        _index_path(),
        {"active_session_id": active_session_id, "order": order},
    )


def _slim_display_messages(agent_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UI 用精简消息：user / assistant 文本，并附带同轮生图路径。"""
    return build_display_messages(agent_messages)


def _user_message_for_display(content: str) -> str:
    """从 agent 内部 user 消息提取可展示文本，过滤系统注入内容。"""
    text = str(content or "").strip()
    if not text or text.startswith("【系统提示】"):
        return ""
    if "\n\n【当前任务：" in text:
        text = text.split("\n\n【当前任务：", 1)[0].strip()
    return text


def build_display_messages(agent_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 agent 历史构建展示消息，将 generate_image 结果挂到紧随的 assistant 回复。"""
    from friday.image_gen import extract_path_from_tool_result

    display: list[dict[str, Any]] = []
    pending_images: list[dict[str, str]] = []
    tool_names: dict[str, str] = {}
    pending_calls: dict[str, str] = {}

    for msg in agent_messages:
        role = str(msg.get("role", ""))
        if role == "system":
            continue
        if role == "user":
            pending_images = []
            content = _user_message_for_display(msg.get("content", ""))
            if content:
                display.append({"role": "user", "content": content})
            continue
        if role == "assistant":
            for call in msg.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") or {}
                call_id = str(call.get("id", "")).strip()
                if call_id:
                    tool_names[call_id] = str(fn.get("name", ""))
                    pending_calls[call_id] = tool_names[call_id]
            content = str(msg.get("content", "")).strip()
            if content or pending_images:
                item: dict[str, Any] = {"role": "assistant", "content": content}
                if pending_images:
                    item["generated_images"] = pending_images.copy()
                    pending_images = []
                display.append(item)
            continue
        if role == "tool":
            call_id = str(msg.get("tool_call_id", "")).strip()
            pending_calls.pop(call_id, None)
            if tool_names.get(call_id) == "generate_image":
                path = extract_path_from_tool_result(str(msg.get("content", "")))
                if path:
                    pending_images.append({"path": path})
            continue

    if pending_calls:
        display.append({"role": "assistant", "content": "（正在处理…）"})

    if pending_images:
        display.append(
            {
                "role": "assistant",
                "content": "已生成图片。",
                "generated_images": pending_images,
            }
        )
    return display


def _compress_agent_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """落盘时压缩 tool 结果，减小 session 文件体积。"""
    compressed: list[dict[str, Any]] = []
    for msg in messages:
        item = dict(msg)
        if item.get("role") == "tool":
            content = str(item.get("content", ""))
            if len(content) > MAX_PERSISTED_TOOL_CHARS:
                item["content"] = (
                    content[:MAX_PERSISTED_TOOL_CHARS]
                    + f"\n...(已压缩，原 {len(content)} 字符)"
                )
        compressed.append(item)
    return compressed


def _parse_session_data(data: dict[str, Any]) -> ChatSession | None:
    try:
        agent_messages = data.get("agent_messages", [])
        if not isinstance(agent_messages, list):
            agent_messages = []
        display = data.get("display_messages")
        if not isinstance(display, list):
            display = _slim_display_messages(agent_messages)
        return ChatSession(
            id=str(data["id"]),
            title=str(data.get("title", "新对话")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            agent_messages=agent_messages,
            display_messages=display,
            title_pinned=bool(data.get("title_pinned", False)),
            plan_markdown=str(data.get("plan_markdown", "") or ""),
            todos=list(data.get("todos") or []) if isinstance(data.get("todos"), list) else [],
            checkpoint_version=int(data.get("checkpoint_version", 0) or 0),
            context_cycle=int(data.get("context_cycle", 0) or 0),
            workspace_id=str(data.get("workspace_id", "") or ""),
            source=str(data.get("source", "desktop") or "desktop"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _save_session(session: ChatSession) -> None:
    from friday.portability import to_portable_path
    from friday.storage import load_settings, resolved_workspace

    display = session.display_messages or _slim_display_messages(session.agent_messages)
    workspace = resolved_workspace(load_settings())
    for msg in display:
        images = msg.get("generated_images")
        if not isinstance(images, list):
            continue
        normalized: list[dict[str, str]] = []
        for item in images:
            if not isinstance(item, dict):
                continue
            old = str(item.get("path", "")).strip()
            normalized.append({"path": to_portable_path(old, workspace) if old else ""})
        msg["generated_images"] = normalized
    session.display_messages = display
    payload = {
        "format_version": SESSION_FORMAT_VERSION,
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "title_pinned": session.title_pinned,
        "plan_markdown": session.plan_markdown,
        "todos": session.todos,
        "checkpoint_version": session.checkpoint_version,
        "context_cycle": session.context_cycle,
        "workspace_id": session.workspace_id,
        "source": session.source,
        "display_messages": display,
        "agent_messages": _compress_agent_messages(session.agent_messages),
    }
    atomic_write_json(_session_path(session.id), payload)


def migrate_session_files() -> int:
    """升级旧版 session 文件为 v2 格式。返回迁移数量。"""
    migrated = 0
    for path in _sessions_dir().glob("*.json"):
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        if int(data.get("format_version", 1)) >= SESSION_FORMAT_VERSION:
            continue
        session = _parse_session_data(data)
        if session is None:
            continue
        _save_session(session)
        migrated += 1
    if migrated:
        _log.info("已迁移 session 文件 | count=%d", migrated)
    return migrated


def _workspace_id_for_session() -> str:
    from friday.storage import load_settings, resolved_workspace

    ws = resolved_workspace(load_settings())
    import hashlib

    digest = hashlib.sha256(str(ws).encode("utf-8")).hexdigest()[:12]
    return digest


def create_session(
    title: str = "新对话",
    *,
    title_pinned: bool = False,
    activate: bool = True,
    source: str = "desktop",
) -> ChatSession:
    session_id = uuid.uuid4().hex[:12]
    now = time.time()
    session = ChatSession(
        id=session_id,
        title=title or "新对话",
        created_at=now,
        updated_at=now,
        agent_messages=[],
        display_messages=[],
        title_pinned=title_pinned,
        workspace_id=_workspace_id_for_session(),
        source=source or "desktop",
    )
    _save_session(session)
    index = _read_index()
    index["order"].insert(0, session_id)
    if activate:
        index["active_session_id"] = session_id
    _write_index(index["active_session_id"], index["order"])
    return session


def session_exists(session_id: str) -> bool:
    return _session_path(session_id).exists()


def get_session(session_id: str) -> ChatSession | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    data = load_json(path)
    if not isinstance(data, dict):
        return None
    session = _parse_session_data(data)
    if session is None:
        return None
    if int(data.get("format_version", 1)) < SESSION_FORMAT_VERSION:
        _save_session(session)
    return session


def save_session_fields(session_id: str, **fields: Any) -> ChatSession | None:
    session = get_session(session_id)
    if session is None:
        return None
    for key, value in fields.items():
        if hasattr(session, key):
            setattr(session, key, value)
    _save_session(session)
    return session


def save_agent_state(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    user_text: str = "",
    activate: bool = True,
    promote_active: bool | None = None,
) -> ChatSession:
    if promote_active is not None:
        activate = promote_active
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"会话不存在: {session_id}")

    from friday.context import sanitize_agent_messages

    session.agent_messages = sanitize_agent_messages(messages)
    session.display_messages = _slim_display_messages(messages)
    session.updated_at = time.time()
    if (
        not session.title_pinned
        and session.title == "新对话"
        and user_text.strip()
    ):
        title = user_text.strip().replace("\n", " ")
        session.title = title[:32] + ("…" if len(title) > 32 else "")

    _save_session(session)
    try:
        from friday.checkpoint_writer import maybe_schedule_checkpoint

        maybe_schedule_checkpoint(session_id, session.agent_messages)
    except Exception:
        _log.debug("checkpoint 调度跳过 | id=%s", session_id, exc_info=True)
    try:
        from friday.history_index import index_session_messages

        index_session_messages(session_id, session.agent_messages, session.display_messages)
    except Exception:
        _log.debug("history 索引跳过 | id=%s", session_id, exc_info=True)
    try:
        from friday.artifacts import sync_session_references

        sync_session_references(session_id)
    except Exception:
        _log.exception("同步会话生成物引用失败 | id=%s", session_id)
    index = _read_index()
    if session.id in index["order"]:
        index["order"].remove(session.id)
    index["order"].insert(0, session.id)
    if activate:
        index["active_session_id"] = session.id
    _write_index(index["active_session_id"], index["order"])
    return session


def set_active_session(session_id: str) -> None:
    index = _read_index()
    index["active_session_id"] = session_id
    _write_index(index["active_session_id"], index["order"])


def ensure_session_listed(session_id: str, *, prepend: bool = False) -> bool:
    """确保会话 id 出现在侧边栏索引中（不改动当前激活会话）。"""
    sid = session_id.strip()
    if not sid or not session_exists(sid):
        return False
    index = _read_index()
    order = index["order"]
    if sid in order:
        return False
    if prepend:
        order.insert(0, sid)
    else:
        order.append(sid)
    _write_index(index["active_session_id"], order)
    return True


def rename_session(session_id: str, title: str) -> ChatSession:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"会话不存在: {session_id}")
    clean = (title or "").strip() or "新对话"
    session.title = clean[:64]
    session.title_pinned = True
    session.updated_at = time.time()
    _save_session(session)
    return session


def list_sessions(limit: int = 50) -> tuple[list[SessionSummary], str]:
    index = _read_index()
    summaries: list[SessionSummary] = []
    for sid in index["order"]:
        if len(summaries) >= limit:
            break
        session = get_session(sid)
        if session:
            summaries.append(session.to_summary())
    active = str(index.get("active_session_id", ""))
    if not active and summaries:
        active = summaries[0].id
    return summaries, active


def delete_session(session_id: str) -> tuple[ChatSession | None, str]:
    path = _session_path(session_id)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            _log.warning("删除会话文件失败 | id=%s", session_id)

    index = _read_index()
    if session_id in index["order"]:
        index["order"].remove(session_id)
    if index["active_session_id"] == session_id:
        index["active_session_id"] = index["order"][0] if index["order"] else ""
    _write_index(index["active_session_id"], index["order"])

    next_id = index["active_session_id"]
    next_session = get_session(next_id) if next_id else None
    if next_session is None and not index["order"]:
        next_session = create_session()
        next_id = next_session.id
    elif next_session is None and index["order"]:
        next_id = index["order"][0]
        index["active_session_id"] = next_id
        _write_index(next_id, index["order"])
        next_session = get_session(next_id)
    try:
        from friday.artifacts import on_session_deleted, run_gc

        on_session_deleted(session_id)
        run_gc()
    except Exception:
        _log.exception("会话删除后生成物回收失败 | id=%s", session_id)
    return next_session, next_id or ""


def display_messages_from_agent(agent_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 agent 内部消息格式转换为前端可展示的对话消息。"""
    display: list[dict[str, Any]] = []
    for msg in agent_messages:
        role = msg.get("role", "")
        if role == "system":
            continue
        content = msg.get("content", "")
        if role == "assistant" and not content and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_name = tc.get("function", {}).get("name", "unknown")
                display.append({
                    "role": "assistant",
                    "content": f"🛠️ 正在使用工具 **{tool_name}** …",
                })
            continue
        if role == "tool":
            name = msg.get("name", "")
            result = (content or "")[:500]
            display.append({
                "role": "tool",
                "name": name,
                "content": result,
            })
            continue
        if content:
            visible = _user_message_for_display(content) if role == "user" else str(content).strip()
            if visible:
                display.append({"role": role, "content": visible})
    return display


def session_display_messages(session: ChatSession) -> list[dict[str, Any]]:
    """优先从 agent 历史重建展示消息（含生图路径），兼容旧落盘数据。"""
    if session.agent_messages:
        return build_display_messages(session.agent_messages)
    if session.display_messages:
        return session.display_messages
    return []


def fork_session(
    session_id: str,
    *,
    title_suffix: str = " (分支)",
    activate: bool = True,
) -> ChatSession | None:
    """从 checkpoint + plan 种子新建会话。"""
    source = get_session(session_id)
    if source is None:
        return None

    title = (source.title or "新对话").strip()
    if title_suffix and not title.endswith(title_suffix.strip()):
        title = f"{title}{title_suffix}"[:64]

    child = create_session(title=title, title_pinned=True, activate=activate, source="fork")
    child.plan_markdown = source.plan_markdown
    child.todos = list(source.todos)
    child.checkpoint_version = 0
    child.workspace_id = source.workspace_id or _workspace_id_for_session()

    seed: list[dict[str, Any]] = []
    from friday.checkpoint_writer import checkpoint_path, format_checkpoint_for_prompt

    ck_prompt = format_checkpoint_for_prompt(session_id)
    if ck_prompt:
        seed.append({"role": "user", "content": ck_prompt})
    elif checkpoint_path(session_id).exists():
        seed.append({
            "role": "user",
            "content": checkpoint_path(session_id).read_text(encoding="utf-8")[:4000],
        })

    from friday.plan import plan_prompt_block

    plan_block = plan_prompt_block(source)
    if plan_block:
        seed.append({"role": "user", "content": plan_block})

    if seed:
        child.agent_messages = seed
        child.display_messages = _slim_display_messages(seed)

    _save_session(child)

    src_sidecar = get_appdata_dir() / "sessions" / session_id
    dst_sidecar = get_appdata_dir() / "sessions" / child.id
    if src_sidecar.is_dir():
        import shutil

        dst_sidecar.mkdir(parents=True, exist_ok=True)
        for name in ("checkpoint.md", "checkpoint_meta.json"):
            src = src_sidecar / name
            if src.exists():
                shutil.copy2(src, dst_sidecar / name)

    return child


def ensure_default_session() -> ChatSession:
    """确保至少有一个会话存在，没有则创建。"""
    index = _read_index()
    if index["order"]:
        sid = index["active_session_id"] or index["order"][0]
        session = get_session(sid)
        if session:
            return session
    return create_session()


def migrate_local_storage(
    sessions: list[dict[str, Any]] | None = None,
    active_session_id: str = "",
) -> dict[str, Any]:
    """导入浏览器 localStorage 中的旧会话。"""
    imported = 0
    skipped = 0
    if not sessions:
        return {"imported": 0, "skipped": 0, "active_session_id": ""}

    index = _read_index()
    known_ids = set(index["order"])

    for item in sessions:
        if not isinstance(item, dict):
            skipped += 1
            continue
        sid = str(item.get("id", "")).strip()
        if not sid or sid in known_ids or _session_path(sid).exists():
            skipped += 1
            continue

        agent_messages: list[dict[str, Any]] = []
        for msg in item.get("messages", []):
            if not isinstance(msg, dict):
                continue
            kind = str(msg.get("kind", msg.get("role", "user")))
            text = str(msg.get("text", msg.get("content", "")))
            if not text:
                continue
            role = "user" if kind == "user" else "assistant"
            agent_messages.append({"role": role, "content": text})

        now = time.time()
        session = ChatSession(
            id=sid,
            title=str(item.get("title", "导入的对话")),
            created_at=float(item.get("createdAt", item.get("created_at", now))),
            updated_at=float(item.get("updatedAt", item.get("updated_at", now))),
            agent_messages=agent_messages,
            display_messages=_slim_display_messages(agent_messages),
        )
        _save_session(session)
        index["order"].insert(0, sid)
        known_ids.add(sid)
        imported += 1

    if imported:
        if active_session_id and active_session_id in known_ids:
            index["active_session_id"] = active_session_id
        elif not index["active_session_id"] and index["order"]:
            index["active_session_id"] = index["order"][0]
        _write_index(index["active_session_id"], index["order"])

    return {
        "imported": imported,
        "skipped": skipped,
        "active_session_id": index["active_session_id"],
    }


def ensure_sessions_index_after_import() -> bool:
    """导入配置包后：index 缺失或与磁盘会话不一致时重建。"""
    on_disk = sorted(
        _sessions_dir().glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not on_disk:
        return False

    disk_ids = [path.stem for path in on_disk]
    index = _read_index()
    order = [sid for sid in index["order"] if sid in disk_ids]
    for sid in disk_ids:
        if sid not in order:
            order.append(sid)

    active = index["active_session_id"]
    if active not in disk_ids:
        active = order[0] if order else ""

    if order == index["order"] and active == index["active_session_id"]:
        return False

    _write_index(active, order)
    _log.info("已重建 sessions_index | count=%d active=%s", len(order), active)
    return True


def migrate_legacy_data_dir() -> None:
    """将旧版项目 data/ 目录迁移到 %APPDATA%/Friday/。"""
    import shutil

    old_data_dir = Path(__file__).resolve().parents[1] / "data"
    if not old_data_dir.is_dir():
        return

    appdata_dir = get_appdata_dir()
    old_sessions = old_data_dir / "sessions"
    if old_sessions.is_dir():
        new_sessions = appdata_dir / "sessions"
        if not new_sessions.exists():
            shutil.copytree(old_sessions, new_sessions)
            _log.info("已从旧路径迁移 sessions | %s -> %s", old_sessions, new_sessions)

    old_settings = old_data_dir / "settings.json"
    old_fernet = old_data_dir / ".fernet_key"
    if old_settings.exists():
        new_settings = appdata_dir / "settings.json"
        if not new_settings.exists():
            shutil.copy2(old_settings, new_settings)
            if old_fernet.exists():
                shutil.copy2(old_fernet, appdata_dir / ".fernet_key")
                _log.info("已迁移 .fernet_key | %s -> %s", old_fernet, appdata_dir / ".fernet_key")
