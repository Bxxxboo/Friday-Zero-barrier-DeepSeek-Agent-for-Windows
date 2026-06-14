"""微信 iLink CDN 媒体上传（AES-128-ECB）。"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from friday.logging_config import get_logger
from friday.weixin.client import (
    CDN_BASE_URL,
    UPLOAD_MEDIA_TYPE_FILE,
    UPLOAD_MEDIA_TYPE_IMAGE,
    WeixinAccount,
    _ilink_post_json,
)

_log = get_logger("weixin.media")

UPLOAD_MAX_RETRIES = 3


def cdn_upload_timeout_sec(byte_size: int) -> int:
    """按文件大小放宽 CDN 上传超时（大 docx 等）。"""
    if byte_size <= 2 * 1024 * 1024:
        return 30
    if byte_size <= 10 * 1024 * 1024:
        return 90
    return 120


def aes_ecb_padded_size(plaintext_size: int) -> int:
    return ((plaintext_size + 1) + 15) // 16 * 16


def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def build_cdn_upload_url(*, cdn_base_url: str, upload_param: str, filekey: str) -> str:
    base = cdn_base_url.rstrip("/")
    query = urllib.parse.urlencode(
        {"encrypted_query_param": upload_param, "filekey": filekey},
    )
    return f"{base}/upload?{query}"


@dataclass(frozen=True)
class UploadedMedia:
    filekey: str
    download_encrypted_query_param: str
    aeskey_hex: str
    file_size: int
    file_size_ciphertext: int


def aes_key_b64_for_image(aeskey_hex: str) -> str:
    """图片：base64(raw 16 bytes)。"""
    return base64.b64encode(bytes.fromhex(aeskey_hex)).decode("ascii")


def aes_key_b64_for_file(aeskey_hex: str) -> str:
    """文件/语音/视频：base64(hex ASCII)，与 openclaw-weixin 一致。"""
    return base64.b64encode(aeskey_hex.encode("ascii")).decode("ascii")


# 兼容旧名
UploadedImage = UploadedMedia


def _upload_buffer_to_cdn(
    *,
    plaintext: bytes,
    upload_full_url: str,
    upload_param: str,
    filekey: str,
    cdn_base_url: str,
    aeskey: bytes,
    label: str,
) -> str:
    ciphertext = encrypt_aes_ecb(plaintext, aeskey)
    trimmed_full = (upload_full_url or "").strip()
    if trimmed_full:
        cdn_url = trimmed_full
    elif upload_param:
        cdn_url = build_cdn_upload_url(
            cdn_base_url=cdn_base_url,
            upload_param=upload_param,
            filekey=filekey,
        )
    else:
        raise RuntimeError(f"{label}: CDN 上传地址缺失")

    last_error: BaseException | None = None
    upload_timeout = cdn_upload_timeout_sec(len(plaintext))
    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        req = urllib.request.Request(
            cdn_url,
            data=ciphertext,
            method="POST",
            headers={"Content-Type": "application/octet-stream"},
        )
        try:
            with urllib.request.urlopen(req, timeout=upload_timeout) as resp:
                status = resp.status
                download_param = resp.headers.get("x-encrypted-param", "").strip()
                err_msg = resp.headers.get("x-error-message", "")
            if 400 <= status < 500:
                raise RuntimeError(f"CDN 上传客户端错误 {status}: {err_msg or status}")
            if status != 200:
                raise RuntimeError(f"CDN 上传服务端错误: {err_msg or status}")
            if not download_param:
                raise RuntimeError("CDN 响应缺少 x-encrypted-param")
            return download_param
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            err_msg = exc.headers.get("x-error-message", detail[:200] if detail else str(exc))
            if 400 <= exc.code < 500:
                raise RuntimeError(f"CDN 上传客户端错误 {exc.code}: {err_msg}") from exc
            last_error = RuntimeError(f"CDN 上传服务端错误: {err_msg}")
            _log.warning("%s 第 %d 次失败 | %s", label, attempt, err_msg)
        except OSError as exc:
            last_error = exc
            _log.warning("%s 第 %d 次失败 | %s", label, attempt, exc)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{label}: CDN 上传失败")


def get_upload_url(
    account: WeixinAccount,
    *,
    to_user_id: str,
    filekey: str,
    rawsize: int,
    rawfilemd5: str,
    filesize: int,
    aeskey_hex: str,
    media_type: int = UPLOAD_MEDIA_TYPE_IMAGE,
) -> dict[str, Any]:
    body = {
        "filekey": filekey,
        "media_type": media_type,
        "to_user_id": to_user_id,
        "rawsize": rawsize,
        "rawfilemd5": rawfilemd5,
        "filesize": filesize,
        "no_need_thumb": True,
        "aeskey": aeskey_hex,
    }
    url = f"{account.base_url}/ilink/bot/getuploadurl"
    raw = _ilink_post_json(account, url, body)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("getUploadUrl 响应无效") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("getUploadUrl 响应无效")
    return parsed


def _upload_file_bytes(
    account: WeixinAccount,
    *,
    plaintext: bytes,
    to_user_id: str,
    cdn_base_url: str,
    media_type: int,
    label: str,
) -> UploadedMedia:
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    filesize = aes_ecb_padded_size(rawsize)
    filekey = secrets.token_hex(16)
    aeskey = secrets.token_bytes(16)
    aeskey_hex = aeskey.hex()

    upload_resp = get_upload_url(
        account,
        to_user_id=to_user_id,
        filekey=filekey,
        rawsize=rawsize,
        rawfilemd5=rawfilemd5,
        filesize=filesize,
        aeskey_hex=aeskey_hex,
        media_type=media_type,
    )
    upload_full_url = str(upload_resp.get("upload_full_url") or "").strip()
    upload_param = str(upload_resp.get("upload_param") or "").strip()
    if not upload_full_url and not upload_param:
        raise RuntimeError("getUploadUrl 未返回上传地址")

    download_param = _upload_buffer_to_cdn(
        plaintext=plaintext,
        upload_full_url=upload_full_url,
        upload_param=upload_param,
        filekey=filekey,
        cdn_base_url=cdn_base_url,
        aeskey=aeskey,
        label=label,
    )
    return UploadedMedia(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey_hex=aeskey_hex,
        file_size=rawsize,
        file_size_ciphertext=filesize,
    )


def upload_image_file(
    account: WeixinAccount,
    *,
    file_path: str,
    to_user_id: str,
    cdn_base_url: str = CDN_BASE_URL,
) -> UploadedMedia:
    path = Path(file_path)
    return _upload_file_bytes(
        account,
        plaintext=path.read_bytes(),
        to_user_id=to_user_id,
        cdn_base_url=cdn_base_url,
        media_type=UPLOAD_MEDIA_TYPE_IMAGE,
        label="upload_image_file",
    )


def upload_attachment_file(
    account: WeixinAccount,
    *,
    file_path: str,
    to_user_id: str,
    cdn_base_url: str = CDN_BASE_URL,
) -> UploadedMedia:
    path = Path(file_path)
    return _upload_file_bytes(
        account,
        plaintext=path.read_bytes(),
        to_user_id=to_user_id,
        cdn_base_url=cdn_base_url,
        media_type=UPLOAD_MEDIA_TYPE_FILE,
        label="upload_attachment_file",
    )
