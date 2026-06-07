"""生图 —— OpenAI 兼容中转 / 火山方舟 Images API。"""

from __future__ import annotations

import base64
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from friday.config import IMAGE_GEN_HTTP_TIMEOUT
from friday.logging_config import get_logger
from friday.storage import UserSettings, resolved_workspace

_log = get_logger("image_gen")

OPENAI_COMPAT_DEFAULT_BASE = "https://next.zhima.world"
ARK_DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_PLACEHOLDER_KEYS = frozenset({"sk-your-key-here", "ark-your-key-here"})
_SAVE_DIR_NAME = "生成的图片"
_SIZE_RE = re.compile(r"^\d{2,4}x\d{2,4}$")


def image_gen_ready(settings: UserSettings) -> bool:
    if not settings.image_gen_enabled:
        return False
    key = settings.image_gen_api_key.strip()
    if not key or key in _PLACEHOLDER_KEYS:
        return False
    return bool(settings.image_gen_model.strip())


def masked_image_gen_key(settings: UserSettings) -> str:
    key = settings.image_gen_api_key.strip()
    if not key:
        return "未设置"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def default_base_url(settings: UserSettings) -> str:
    custom = settings.image_gen_base_url.strip()
    if custom:
        return custom.rstrip("/")
    if (settings.image_gen_provider or "openai_compat").strip() == "ark":
        return ARK_DEFAULT_BASE
    return OPENAI_COMPAT_DEFAULT_BASE


def _parse_fallback_urls(settings: UserSettings) -> list[str]:
    raw = (settings.image_gen_fallback_urls or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", raw)
    return [p.strip().rstrip("/") for p in parts if p.strip()]


def _candidate_base_urls(settings: UserSettings) -> list[str]:
    urls: list[str] = []
    for candidate in (default_base_url(settings), *_parse_fallback_urls(settings)):
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def _save_dir(settings: UserSettings) -> Path:
    custom = (settings.image_gen_save_dir or "").strip()
    if custom:
        target = Path(custom).expanduser()
    else:
        target = Path(resolved_workspace(settings)) / _SAVE_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _normalize_size(size: str, settings: UserSettings) -> str:
    raw = (size or settings.image_gen_default_size or "1024x1024").strip()
    if not _SIZE_RE.match(raw):
        return settings.image_gen_default_size or "1024x1024"
    return raw


def _build_prompt(prompt: str, style: str = "", negative_prompt: str = "") -> str:
    text = (prompt or "").strip()
    if not text:
        raise ValueError("请提供图片描述（prompt）")
    style_text = (style or "").strip()
    if style_text:
        text = f"{text}\n风格：{style_text}"
    neg = (negative_prompt or "").strip()
    if neg:
        text = f"{text}\n请避免：{neg}"
    return text


def _images_client(api_key: str, base_url: str):
    import httpx
    from openai import OpenAI

    timeout = httpx.Timeout(
        connect=15.0,
        read=float(IMAGE_GEN_HTTP_TIMEOUT),
        write=30.0,
        pool=10.0,
    )
    return OpenAI(api_key=api_key, base_url=base_url.rstrip("/"), timeout=timeout)


def _download_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Friday-Desktop/1.0"})
    with urllib.request.urlopen(req, timeout=IMAGE_GEN_HTTP_TIMEOUT) as resp:
        data = resp.read()
    if len(data) < 128:
        raise ValueError("下载的图片数据过小或无效")
    return data


def _call_images_api(
    *,
    api_key: str,
    base_urls: list[str],
    model: str,
    prompt: str,
    size: str,
) -> bytes:
    last_exc: Exception | None = None
    for base in base_urls:
        try:
            client = _images_client(api_key, base)
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                response_format="b64_json",
                n=1,
            )
            if not response.data:
                raise ValueError("API 未返回图片")
            item = response.data[0]
            if getattr(item, "b64_json", None):
                return base64.b64decode(item.b64_json)
            url = getattr(item, "url", None)
            if url:
                return _download_url(str(url))
            raise ValueError("API 响应缺少 b64_json 或 url")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _log.warning("生图 API 失败 | base=%s err=%s", base, exc)
            continue
    msg = str(last_exc) if last_exc else "所有端点均失败"
    raise RuntimeError(msg) from last_exc


def _safe_filename(name: str) -> str:
    stem = Path(name).name.strip()
    if not stem:
        return ""
    stem = re.sub(r'[<>:"/\\|?*]', "_", stem)
    if not stem.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        stem += ".png"
    return stem


def _resolve_output_path(settings: UserSettings, filename: str) -> Path:
    root = _save_dir(settings)
    workspace = Path(resolved_workspace(settings)).resolve()
    if filename.strip():
        out = (root / _safe_filename(filename)).resolve()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        token = secrets.token_hex(3)
        out = (root / f"image-{stamp}-{token}.png").resolve()
    try:
        out.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"保存路径须位于默认操作文件夹内：{workspace}") from exc
    return out


def generate_image(
    settings: UserSettings,
    prompt: str,
    *,
    size: str = "",
    filename: str = "",
    style: str = "",
    negative_prompt: str = "",
) -> dict[str, Any]:
    """调用生图 API 并保存到工作区，返回元数据。"""
    if not image_gen_ready(settings):
        return {
            "ok": False,
            "error": (
                "生图 API 未配置。请在「设置 → API 连接 → 生图」中启用，"
                "填写 API Key 与模型名称后保存。"
            ),
        }

    try:
        full_prompt = _build_prompt(prompt, style, negative_prompt)
        image_size = _normalize_size(size, settings)
        model = settings.image_gen_model.strip()
        api_key = settings.image_gen_api_key.strip()
        base_urls = _candidate_base_urls(settings)
        out_path = _resolve_output_path(settings, filename)

        _log.info(
            "开始生图 | model=%s size=%s provider=%s",
            model,
            image_size,
            settings.image_gen_provider,
        )
        t0 = time.perf_counter()
        data = _call_images_api(
            api_key=api_key,
            base_urls=base_urls,
            model=model,
            prompt=full_prompt,
            size=image_size,
        )
        out_path.write_bytes(data)
        elapsed = time.perf_counter() - t0
        w, h = (image_size.split("x") + ["", ""])[:2]
        _log.info("生图完成 | %.1fs path=%s bytes=%d", elapsed, out_path.name, len(data))
        return {
            "ok": True,
            "path": str(out_path).replace("\\", "/"),
            "filename": out_path.name,
            "width": w,
            "height": h,
            "model": model,
            "prompt": prompt.strip(),
            "size": image_size,
            "bytes": len(data),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        _log.warning("生图失败 | %s", exc)
        return {"ok": False, "error": _format_error(exc)}


def _format_error(exc: Exception) -> str:
    msg = str(exc)
    hint = ""
    lower = msg.lower()
    if "401" in msg or "403" in msg or "authentication" in lower:
        hint = "。请检查 API Key 是否有效"
    elif "404" in msg or "not found" in lower:
        hint = "。请确认模型名称正确"
    elif "timeout" in lower or "timed out" in lower:
        hint = "。生图耗时较长，请稍后重试或更换端点"
    elif "content" in lower or "policy" in lower or "safety" in lower:
        hint = "。描述可能触发内容策略，请改写 prompt"
    return f"生图 API 调用失败: {msg[:240]}{hint}"


def format_generate_result(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return str(result.get("error", "生图失败"))
    path = result.get("path", "")
    size = result.get("size", "")
    return (
        f"已生成图片并保存：{path}\n"
        f"尺寸：{size}，模型：{result.get('model', '')}。"
    )


def extract_path_from_tool_result(text: str) -> str | None:
    """从 generate_image 工具返回文本中提取保存路径。"""
    prefix = "已生成图片并保存："
    if prefix not in (text or ""):
        return None
    first_line = text.split("\n", 1)[0].strip()
    if not first_line.startswith(prefix):
        return None
    path = first_line[len(prefix):].strip()
    return path or None


def resolve_generated_image_path(path: str, settings: UserSettings) -> Path:
    """校验生图路径位于工作区内（支持相对路径）。"""
    from friday.portability import resolve_portable_path

    workspace = Path(resolved_workspace(settings)).resolve()
    target = resolve_portable_path(path, str(workspace))
    if not target.is_file():
        raise FileNotFoundError(f"找不到图片: {target}")
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise PermissionError("路径超出默认操作文件夹范围") from exc
    suffix = target.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise ValueError("不支持的图片格式")
    return target


def guess_image_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")


def render_preview_bytes(path: Path, *, max_width: int = 720) -> tuple[bytes, str]:
    """生成聊天预览用缩略图，避免 WebView 加载超大原图卡死。"""
    try:
        from PIL import Image
    except ImportError:
        return path.read_bytes(), guess_image_media_type(path)

    with Image.open(path) as img:
        img = img.convert("RGB")
        width = max(1, int(max_width))
        if img.width > width:
            ratio = width / img.width
            height = max(1, int(img.height * ratio))
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        import io

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue(), "image/jpeg"


def test_image_gen_connection(settings: UserSettings) -> tuple[bool, str]:
    if not settings.image_gen_enabled:
        return False, "请先勾选「启用生图」"
    if not settings.image_gen_api_key.strip():
        return False, "请填写生图 API Key"
    if not settings.image_gen_model.strip():
        return False, "请填写生图模型名称（测试时可向 API 提供商确认）"

    test_settings = settings
    result = generate_image(
        test_settings,
        "a minimal flat icon, red circle on white background",
        size="1024x1024",
        filename=f"friday-test-{secrets.token_hex(4)}.png",
    )
    if result.get("ok"):
        return True, f"生图测试通过，已保存：{result.get('path', '')}"
    return False, str(result.get("error", "生图测试失败"))
