from __future__ import annotations

import base64
import json
import random
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from friday.logging_config import get_logger
from friday.weixin.config import openclaw_state_dir

_log = get_logger("weixin.client")

WEIXIN_CHUNK_CHARS = 1800

ILINK_APP_ID = "bot"
# openclaw-weixin 2.4.4 -> 0x00020404
ILINK_APP_CLIENT_VERSION = 132100
CHANNEL_VERSION = "2.4.4"
from friday.version import __version__

BOT_AGENT = f"Friday/{__version__}"
MESSAGE_ITEM_TEXT = 1
MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_FINISH = 2


@dataclass(frozen=True)
class WeixinAccount:
    account_id: str
    token: str
    base_url: str
    user_id: str = ""


def _weixin_state_dir() -> Path:
    return openclaw_state_dir() / "openclaw-weixin"


def list_account_ids() -> list[str]:
    index = _weixin_state_dir() / "accounts.json"
    if not index.is_file():
        return []
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()]
    except (OSError, json.JSONDecodeError):
        return []


def load_account(account_id: str) -> WeixinAccount | None:
    account_id = account_id.strip()
    if not account_id:
        return None
    path = _weixin_state_dir() / "accounts" / f"{account_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    token = str(data.get("token", "")).strip()
    base_url = str(data.get("baseUrl", "https://ilinkai.weixin.qq.com")).strip().rstrip("/")
    if not token:
        return None
    return WeixinAccount(
        account_id=account_id,
        token=token,
        base_url=base_url,
        user_id=str(data.get("userId", "")).strip(),
    )


def resolve_account(account_id: str = "") -> WeixinAccount | None:
    if account_id.strip():
        return load_account(account_id)
    ids = list_account_ids()
    if len(ids) == 1:
        return load_account(ids[0])
    for candidate in ids:
        account = load_account(candidate)
        if account:
            return account
    return None


def load_context_token(account_id: str, peer_id: str) -> str:
    path = _weixin_state_dir() / "accounts" / f"{account_id}.context-tokens.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get(peer_id, "")).strip()


def save_context_token(account_id: str, peer_id: str, token: str) -> None:
    if not account_id or not peer_id or not token:
        return
    path = _weixin_state_dir() / "accounts" / f"{account_id}.context-tokens.json"
    data: dict[str, str] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = {str(k): str(v) for k, v in raw.items() if str(v).strip()}
        except (OSError, json.JSONDecodeError):
            data = {}
    data[peer_id] = token
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _random_wechat_uin() -> str:
    value = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _build_headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }


def fresh_context_token(account_id: str, peer_id: str, *, fallback: str = "") -> str:
    """每次发送前从 OpenClaw 持久化文件读取最新 context_token。"""
    return load_context_token(account_id, peer_id) or (fallback or "").strip()


def send_text(
    account: WeixinAccount,
    *,
    to_user_id: str,
    text: str,
    context_token: str = "",
) -> None:
    body = {
        "base_info": {
            "channel_version": CHANNEL_VERSION,
            "bot_agent": BOT_AGENT,
        },
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": f"friday-{secrets.token_hex(8)}",
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": [{"type": MESSAGE_ITEM_TEXT, "text_item": {"text": text}}],
            "context_token": context_token or None,
        },
    }
    url = f"{account.base_url}/ilink/bot/sendmessage"
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers=_build_headers(account.token))
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and parsed.get("ret") not in (None, 0):
                    detail = str(parsed.get("errmsg") or raw)[:200]
                    _log.warning(
                        "微信发送被拒 | peer=%s ret=%s detail=%s",
                        to_user_id,
                        parsed.get("ret"),
                        detail,
                    )
                    raise RuntimeError(f"微信发送失败 ({parsed.get('ret')})")
            except json.JSONDecodeError:
                pass
        _log.info(
            "微信消息已发送 | peer=%s chars=%d token=%s",
            to_user_id,
            len(text),
            "yes" if context_token else "no",
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        _log.warning("微信发送失败 | status=%s detail=%.200s", exc.code, detail)
        raise RuntimeError(f"微信发送失败 ({exc.code})") from exc
    except OSError as exc:
        _log.warning("微信发送异常 | %s", exc)
        raise RuntimeError("微信发送失败") from exc


def send_peer_text(
    account: WeixinAccount,
    *,
    peer_id: str,
    text: str,
    fallback_token: str = "",
) -> None:
    """向微信用户发消息，自动刷新 context_token；过长时分段发送。"""
    body = (text or "").strip()
    if not body:
        return
    token = fresh_context_token(account.account_id, peer_id, fallback=fallback_token)
    if not token:
        _log.warning("微信发送缺少 context_token | peer=%s", peer_id)

    if len(body) <= WEIXIN_CHUNK_CHARS:
        send_text(account, to_user_id=peer_id, text=body, context_token=token)
        return

    chunks: list[str] = []
    start = 0
    while start < len(body):
        chunks.append(body[start : start + WEIXIN_CHUNK_CHARS])
        start += WEIXIN_CHUNK_CHARS
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        token = fresh_context_token(account.account_id, peer_id, fallback=fallback_token)
        prefix = f"({index}/{total})\n" if total > 1 else ""
        send_text(account, to_user_id=peer_id, text=prefix + chunk, context_token=token)
