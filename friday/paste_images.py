"""聊天粘贴截图 —— 保存到工作区供 describe_image 使用。"""

from __future__ import annotations

import base64
import re
import secrets
import time
from pathlib import Path

from friday.logging_config import get_logger
from friday.storage import UserSettings, resolved_workspace

_log = get_logger("paste_images")

_MAX_BYTES = 10 * 1024 * 1024
_SUPPORTED_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.DOTALL)


def _paste_dir(settings: UserSettings) -> Path:
    root = Path(resolved_workspace(settings))
    target = root / "粘贴的截图"
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_pasted_image(
    settings: UserSettings,
    *,
    image_base64: str = "",
    data_url: str = "",
    mime_type: str = "image/png",
) -> tuple[str, str]:
    """解码并保存粘贴图片，返回 (绝对路径, 文件名)。"""
    raw_b64 = image_base64.strip()
    ext = _SUPPORTED_MIME.get(mime_type.lower())

    if data_url.strip():
        match = _DATA_URL_RE.match(data_url.strip())
        if not match:
            raise ValueError("无效的图片 data URL")
        mime_type = match.group(1).lower()
        raw_b64 = match.group(2).strip()
        ext = _SUPPORTED_MIME.get(mime_type)

    if not ext:
        raise ValueError(f"不支持的图片格式: {mime_type}")

    try:
        data = base64.b64decode(raw_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("图片数据解码失败") from exc

    if not data:
        raise ValueError("图片内容为空")
    if len(data) > _MAX_BYTES:
        raise ValueError(f"图片过大（最大 {_MAX_BYTES // (1024 * 1024)}MB）")

    try:
        from friday.vision import optimize_image_bytes

        data, out_mime = optimize_image_bytes(data)
        ext = ".jpg" if out_mime == "image/jpeg" else ext
    except Exception:
        pass

    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(2)
    filename = f"paste-{stamp}-{suffix}{ext}"
    path = _paste_dir(settings) / filename
    path.write_bytes(data)
    normalized = str(path.resolve()).replace("\\", "/")
    _log.info("保存粘贴截图 | path=%s bytes=%d", normalized, len(data))
    try:
        from friday.artifacts import register_pasted_image

        register_pasted_image(path)
    except Exception:
        _log.exception("登记粘贴截图失败")
    return normalized, filename
