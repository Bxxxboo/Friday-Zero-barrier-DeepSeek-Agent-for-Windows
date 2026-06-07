from __future__ import annotations

import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from friday.logging_config import get_logger
from friday.safety import (
    PendingAction,
    TurnApprovalState,
    describe_approval_detail,
    describe_approval_plain,
    mark_turn_approved,
    should_request_approval,
)
from friday.safety import ToolDecision
from friday.sessions import save_agent_state
from friday.storage import UserSettings, load_settings
from friday.weixin.approval import format_approval_prompt, parse_approval_text
from friday.weixin.client import (
    WeixinAccount,
    resolve_account,
    save_context_token,
    send_peer_text,
)
from friday.weixin.sessions import resolve_session_id

_log = get_logger("weixin.bridge")

MAX_REPLY_CHARS = 3500
APPROVAL_TIMEOUT_SEC = 300

_peer_locks: dict[str, threading.Lock] = {}
_approval_waiters: dict[str, Future[bool]] = {}
_approval_meta: dict[str, dict[str, str]] = {}


@dataclass
class InboundRequest:
    text: str
    sender_id: str
    account_id: str
    context_token: str = ""
    peer_id: str = ""


def _resolve_peer_id(req: InboundRequest) -> str:
    return (req.sender_id or req.peer_id or "").strip()


@dataclass
class InboundResponse:
    handled: bool
    reply: str = ""


def _peer_lock(peer: str) -> threading.Lock:
    lock = _peer_locks.get(peer)
    if lock is None:
        lock = threading.Lock()
        _peer_locks[peer] = lock
    return lock


def _truncate_reply(text: str) -> str:
    body = (text or "").strip()
    if len(body) <= MAX_REPLY_CHARS:
        return body or "（已完成，无文字回复）"
    return body[: MAX_REPLY_CHARS - 20] + "\n\n…（内容过长已截断）"


def _make_weixin_approval_bridge(
    *,
    peer_id: str,
    account: WeixinAccount,
) -> Any:
    def approval_bridge(action: PendingAction) -> bool:
        from friday.interaction_modes import normalize_mode, tool_allowed_in_mode

        settings = load_settings()
        mode = normalize_mode(getattr(settings, "interaction_mode", "agent"))
        if not tool_allowed_in_mode(action.tool_name, mode):
            return False

        pseudo = ToolDecision(
            allowed=True,
            needs_approval=True,
            large_download=action.large_download,
            untrusted_download=action.untrusted_download,
        )
        state = TurnApprovalState()
        if not should_request_approval(settings, pseudo, state):
            return True

        prompt = format_approval_prompt(
            describe_approval_plain(action.tool_name, action.arguments),
            preview=describe_approval_detail(action.tool_name, action.arguments),
        )
        try:
            send_peer_text(account, peer_id=peer_id, text=prompt)
        except RuntimeError as exc:
            _log.warning("审批消息发送失败 | peer=%s err=%s", peer_id, exc)
            return False

        future: Future[bool] = Future()
        _approval_waiters[peer_id] = future
        _approval_meta[peer_id] = {
            "account_id": account.account_id,
        }
        _log.info(
            "等待微信审批 | peer=%s summary=%s",
            peer_id,
            describe_approval_plain(action.tool_name, action.arguments)[:80],
        )
        approved = False
        try:
            approved = future.result(timeout=APPROVAL_TIMEOUT_SEC)
        except TimeoutError:
            try:
                send_peer_text(
                    account,
                    peer_id=peer_id,
                    text="审批已超时，本次操作已取消。",
                )
            except RuntimeError:
                pass
            return False
        finally:
            _approval_waiters.pop(peer_id, None)
            _approval_meta.pop(peer_id, None)

        if approved:
            mark_turn_approved(state, pseudo)
        return approved

    return approval_bridge


def _run_agent(
    *,
    session_id: str,
    text: str,
    peer_id: str,
    account: WeixinAccount,
    context_token: str,
) -> str:
    from friday.agent import FridayAgent
    from friday.sessions import get_session

    settings = load_settings()
    if not settings.api_ready:
        return "请先在星期五桌面版「设置」中配置 DeepSeek API Key。"

    approval_bridge = _make_weixin_approval_bridge(
        peer_id=peer_id,
        account=account,
    )
    session = get_session(session_id)
    agent = FridayAgent(settings, approval_bridge)
    if session:
        agent.load_history(session.agent_messages)
    agent.operation_meta = {
        "session_id": session_id,
        "trigger": "weixin",
        "schedule_id": "",
    }

    user_message = f"[来自微信 remote]\n{text.strip()}"
    result = agent.run(user_message)
    save_agent_state(session_id, agent.messages, user_text=user_message)
    return _truncate_reply(result)


def _resolve_pending_approval(peer_id: str, text: str, account: WeixinAccount) -> InboundResponse | None:
    future = _approval_waiters.get(peer_id)
    if future is None or future.done():
        return None

    decision = parse_approval_text(text)
    if decision is None:
        try:
            send_peer_text(
                account,
                peer_id=peer_id,
                text="请回复「同意」或「拒绝」。",
            )
        except RuntimeError:
            pass
        return InboundResponse(handled=True, reply="")

    future.set_result(decision)
    ack = "好的，已同意，继续执行。" if decision else "好的，已拒绝该操作。"
    _log.info("微信审批已回复 | peer=%s approved=%s", peer_id, decision)
    try:
        send_peer_text(account, peer_id=peer_id, text=ack)
    except RuntimeError as exc:
        _log.warning("审批确认发送失败 | peer=%s err=%s", peer_id, exc)
    return InboundResponse(handled=True, reply="")


def _run_agent_job(
    *,
    session_id: str,
    text: str,
    peer_id: str,
    account: WeixinAccount,
    lock: threading.Lock,
) -> None:
    try:
        reply = _run_agent(
            session_id=session_id,
            text=text,
            peer_id=peer_id,
            account=account,
            context_token="",
        )
        _log.info("微信任务完成 | peer=%s chars=%d", peer_id, len(reply))
        try:
            # 审批后 context_token 会更新，发送结果前必须重新读取
            send_peer_text(account, peer_id=peer_id, text=reply)
        except RuntimeError as exc:
            _log.warning("任务结果发送失败 | peer=%s err=%s", peer_id, exc)
    except Exception:  # noqa: BLE001
        _log.exception("微信任务执行失败 | peer=%s", peer_id)
        try:
            send_peer_text(
                account,
                peer_id=peer_id,
                text="执行出错，请稍后重试或查看星期五日志。",
            )
        except RuntimeError:
            pass
    finally:
        lock.release()
        _log.debug("微信 peer 锁已释放 | peer=%s", peer_id)


def handle_inbound(req: InboundRequest) -> InboundResponse:
    text = (req.text or "").strip()
    peer_id = _resolve_peer_id(req)
    if not peer_id:
        return InboundResponse(handled=True, reply="无法识别发送者。")
    if not text:
        return InboundResponse(handled=True, reply="请发送文字指令。")

    settings = load_settings()
    if not getattr(settings, "weixin_bridge_enabled", True):
        return InboundResponse(handled=False, reply="")

    account = resolve_account(req.account_id)
    if account is None:
        return InboundResponse(
            handled=True,
            reply="微信通道未登录。请先在 OpenClaw 执行：openclaw channels login --channel openclaw-weixin",
        )

    if req.context_token:
        save_context_token(account.account_id, peer_id, req.context_token)

    approval_hit = _resolve_pending_approval(peer_id, text, account)
    if approval_hit is not None:
        return approval_hit

    if parse_approval_text(text) is not None:
        try:
            send_peer_text(
                account,
                peer_id=peer_id,
                text="当前没有待审批的操作。",
            )
        except RuntimeError:
            pass
        return InboundResponse(handled=True, reply="")

    lock = _peer_lock(peer_id)
    if not lock.acquire(blocking=False):
        return InboundResponse(handled=True, reply="正在处理上一条指令，请稍候再发。")

    session_id = resolve_session_id(account.account_id, peer_id)
    try:
        send_peer_text(account, peer_id=peer_id, text="收到，正在处理…")
    except RuntimeError as exc:
        _log.warning("收到确认发送失败 | peer=%s err=%s", peer_id, exc)

    _log.info("微信任务已入队（后台执行）| peer=%s session=%s", peer_id, session_id)
    worker = threading.Thread(
        target=_run_agent_job,
        kwargs={
            "session_id": session_id,
            "text": text,
            "peer_id": peer_id,
            "account": account,
            "lock": lock,
        },
        daemon=True,
        name=f"weixin-agent-{peer_id[:8]}",
    )
    worker.start()
    return InboundResponse(handled=True, reply="")
