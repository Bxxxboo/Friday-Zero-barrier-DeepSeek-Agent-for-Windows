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

from friday.config import (
    IMAGE_GEN_HTTP_TIMEOUT,
    IMAGE_GEN_HTTP_TIMEOUT_MAX,
    IMAGE_GEN_HTTP_TIMEOUT_MIN,
    IMAGE_GEN_PROBE_TIMEOUT,
    IMAGE_GEN_TOOL_TIMEOUT_MAX,
    IMAGE_GEN_TOOL_TIMEOUT_MIN,
)
from friday.logging_config import get_logger
from friday.storage import UserSettings, resolved_workspace

_log = get_logger("image_gen")

OPENAI_COMPAT_DEFAULT_BASE = "https://next.zhima.world"
ARK_DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_PLACEHOLDER_KEYS = frozenset({"sk-your-key-here", "ark-your-key-here"})
_SAVE_DIR_NAME = "生成的图片"
_IMAGE_GEN_BASE_DEFAULT = "1024x1024"
_SIZE_RE = re.compile(r"^\d{2,5}x\d{2,5}$")
_HIGH_RES_MIN_PIXELS = 3_686_400  # 1920×1920、2560×1440 等
_DEFAULT_MIN_PIXELS = 1024 * 1024
_GPT_IMAGE2_MIN_PIXELS = 655_360
_GPT_IMAGE2_MAX_PIXELS = 8_294_400  # 官方上限 3840×2160
_GPT_IMAGE2_MAX_EDGE = 3840
_ARK_MAX_PIXELS = 16_777_216  # 火山方舟常见上限 4096×4096
_ARK_MAX_EDGE = 4096
_SIZE_ALIGN = 16

_SIZE_LABEL_MAP: dict[str, str] = {
    "8k": "7680x4320",
    "4k": "3840x2160",
    "2k": "2560x1440",
    "1080p": "1920x1080",
    "1k": "1024x1024",
}

_SIZE_CATALOG: tuple[tuple[str, int], ...] = (
    ("768x1024", 768 * 1024),
    ("1280x720", 1280 * 720),
    ("1024x1024", 1024 * 1024),
    ("1920x1080", 1920 * 1080),
    ("1920x1920", 1920 * 1920),
    ("2560x1440", 2560 * 1440),
    ("2048x2048", 2048 * 2048),
    ("3840x2160", 3840 * 2160),
    ("4096x4096", 4096 * 4096),
    ("5120x2880", 5120 * 2880),
    ("7680x4320", 7680 * 4320),
)


def _parse_size_str(size: str) -> tuple[int, int]:
    raw = (size or "").strip().lower()
    if "x" not in raw:
        return 0, 0
    w, h = raw.split("x", 1)
    try:
        return max(0, int(w)), max(0, int(h))
    except ValueError:
        return 0, 0


def _pixel_count(size: str) -> int:
    w, h = _parse_size_str(size)
    return w * h if w and h else 0


def _model_id(settings: UserSettings) -> str:
    return (settings.image_gen_model or "").strip().lower()


def _is_gpt_image2_model(model: str) -> bool:
    m = (model or "").strip().lower()
    return m in {"image2", "gpt-image-2", "gpt-image-1.5", "gpt-image-1"} or m.startswith("gpt-image-2")


def _size_limits(settings: UserSettings) -> tuple[int, int, int]:
    """返回 (min_pixels, max_pixels, max_edge)；0 表示不限制。"""
    provider = (settings.image_gen_provider or "").strip()
    model = _model_id(settings)
    base = default_base_url(settings).lower()

    if _is_gpt_image2_model(model):
        return _GPT_IMAGE2_MIN_PIXELS, _GPT_IMAGE2_MAX_PIXELS, _GPT_IMAGE2_MAX_EDGE
    if provider == "mimo" or "xiaomimimo" in base:
        return _HIGH_RES_MIN_PIXELS, 0, 0
    if model in {"dall-e-3", "dall-e-2"}:
        return _DEFAULT_MIN_PIXELS, _GPT_IMAGE2_MAX_PIXELS, _GPT_IMAGE2_MAX_EDGE
    if any(token in model for token in ("seedream", "flux-pro", "mimo-v2.5", "mimo-v2-omni")):
        return _HIGH_RES_MIN_PIXELS, 0, 0
    if provider == "ark" or "volces.com" in base or model.startswith("ep-"):
        return _HIGH_RES_MIN_PIXELS, _ARK_MAX_PIXELS, _ARK_MAX_EDGE
    return _DEFAULT_MIN_PIXELS, 0, 0


def _minimum_pixels(settings: UserSettings) -> int:
    return _size_limits(settings)[0]


def _maximum_pixels(settings: UserSettings) -> int:
    return _size_limits(settings)[1]


def _maximum_edge(settings: UserSettings) -> int:
    return _size_limits(settings)[2]


def _snap_dimension(value: int) -> int:
    if value <= 0:
        return 0
    snapped = max(_SIZE_ALIGN, (value // _SIZE_ALIGN) * _SIZE_ALIGN)
    return snapped


def _clamp_size_to_limits(size: str, settings: UserSettings) -> str:
    max_px = _maximum_pixels(settings)
    max_edge = _maximum_edge(settings)
    if not max_px and not max_edge:
        return size
    w, h = _parse_size_str(size)
    if not w or not h:
        return size
    if _is_gpt_image2_model(_model_id(settings)):
        valid = _catalog_for_limits(_minimum_pixels(settings), max_px, max_edge)
        if valid and (w * h > max_px or (max_edge and max(w, h) > max_edge)):
            return max(valid, key=lambda item: item[1])[0]
        w, h = _snap_dimension(w), _snap_dimension(h)
        if w and h:
            return f"{w}x{h}"
    w, h = _snap_dimension(w), _snap_dimension(h)
    if max_edge and max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        w = _snap_dimension(int(w * scale))
        h = _snap_dimension(int(h * scale))
    if max_px:
        while w * h > max_px and w > _SIZE_ALIGN and h > _SIZE_ALIGN:
            if w >= h:
                w -= _SIZE_ALIGN
            else:
                h -= _SIZE_ALIGN
    if w < _SIZE_ALIGN or h < _SIZE_ALIGN:
        return "3840x2160" if _is_gpt_image2_model(_model_id(settings)) else size
    return f"{w}x{h}"


def _catalog_for_limits(min_pixels: int, max_pixels: int, max_edge: int) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    for spec, px in _SIZE_CATALOG:
        w, h = _parse_size_str(spec)
        if px < min_pixels:
            continue
        if max_pixels and px > max_pixels:
            continue
        if max_edge and max(w, h) > max_edge:
            continue
        items.append((spec, px))
    return items


def _pick_size_for_pixels(min_pixels: int, prefer: str = "", *, settings: UserSettings | None = None) -> str:
    max_px = _maximum_pixels(settings) if settings else 0
    max_edge = _maximum_edge(settings) if settings else 0
    candidates = _catalog_for_limits(min_pixels, max_px, max_edge)
    if not candidates:
        if settings and _is_gpt_image2_model(_model_id(settings)):
            return "3840x2160"
        return "1920x1920"
    if not candidates:
        return "1920x1920"

    pw, ph = _parse_size_str(prefer)
    if pw and ph:
        aspect = pw / ph
        return min(
            candidates,
            key=lambda item: abs((_parse_size_str(item[0])[0] / _parse_size_str(item[0])[1]) - aspect),
        )[0]
    return min(candidates, key=lambda item: item[1])[0]


def _parse_min_pixels_from_error(msg: str) -> int | None:
    text = msg or ""
    for match in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{6,})", text):
        value = int(match.group(1).replace(",", ""))
        if value >= 500_000:
            return value
    dim = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", text)
    if dim:
        return int(dim.group(1)) * int(dim.group(2))
    lower = text.lower()
    if "at least" in lower and "1920" in text:
        return _HIGH_RES_MIN_PIXELS
    return None


def _parse_size_label(raw: str, *, model: str = "") -> str:
    key = re.sub(r"\s+", "", (raw or "").lower())
    if key == "8k" and _is_gpt_image2_model(model):
        return "3840x2160"
    return _SIZE_LABEL_MAP.get(key, "")


def _infer_size_from_prompt(prompt: str, *, model: str = "") -> str:
    text = prompt or ""
    lower = text.lower()
    if re.search(r"8\s*k|8k|八\s*k|八千|8k分辨率|8k画质", lower):
        return "3840x2160" if _is_gpt_image2_model(model) else "7680x4320"
    if re.search(r"4\s*k|4k|四\s*k|4k分辨率|4k画质", lower):
        return "3840x2160"
    if re.search(r"2\s*k|2k|2k分辨率|2k画质", lower):
        return "2560x1440"
    match = re.search(r"(\d{3,5})\s*[x×]\s*(\d{3,5})", text)
    if match:
        w, h = int(match.group(1)), int(match.group(2))
        if 256 <= w <= 8192 and 256 <= h <= 8192:
            return f"{w}x{h}"
    return ""


def _user_explicit_size(size: str, *, prompt: str, model: str) -> str | None:
    """用户明确要求的分辨率（工具 size 参数或 prompt 中的 4K/8K/具体像素）。"""
    explicit: list[str] = []
    label = _parse_size_label(size, model=model)
    if label:
        explicit.append(label)
    dims = (size or "").strip().lower() if _SIZE_RE.match((size or "").strip()) else ""
    if dims:
        explicit.append(dims)
    inferred = _infer_size_from_prompt(prompt, model=model)
    if inferred:
        explicit.append(inferred)
    if not explicit:
        return None
    return max(explicit, key=_pixel_count)


def resolve_image_gen_size(size: str, settings: UserSettings, *, prompt: str = "") -> str:
    """解析实际生图尺寸：默认 1K；用户明确要求时采用，超出模型上限则收敛。"""
    model = _model_id(settings)
    explicit = _user_explicit_size(size, prompt=prompt, model=model)
    raw = explicit if explicit else _IMAGE_GEN_BASE_DEFAULT
    raw = _clamp_size_to_limits(raw, settings)

    min_pixels = _minimum_pixels(settings)
    if _pixel_count(raw) < min_pixels:
        upgraded = _pick_size_for_pixels(min_pixels, raw, settings=settings)
        _log.info("生图尺寸已自动提升 | %s -> %s (min=%d)", raw, upgraded, min_pixels)
        raw = upgraded
    max_px = _maximum_pixels(settings)
    if max_px and _pixel_count(raw) > max_px:
        raw = _clamp_size_to_limits(raw, settings)
        _log.info("生图尺寸已按模型上限收敛 | model=%s size=%s", model, raw)
    return raw


def _normalize_size(size: str, settings: UserSettings, *, prompt: str = "") -> str:
    return resolve_image_gen_size(size, settings, prompt=prompt)


def _is_max_size_error(msg: str) -> bool:
    lower = (msg or "").lower()
    return any(
        token in lower
        for token in (
            "maximum",
            "too large",
            "exceed",
            "max size",
            "max dimension",
            "at most",
            "not support",
            "invalid size",
            "out of range",
            "16777216",
            "过大",
            "超出",
        )
    )


def _step_down_size(current: str, *, settings: UserSettings | None = None) -> str | None:
    px = _pixel_count(current)
    if not px:
        return None
    min_px = _minimum_pixels(settings) if settings else 0
    max_px = _maximum_pixels(settings) if settings else 0
    max_edge = _maximum_edge(settings) if settings else 0
    smaller = _catalog_for_limits(min_px, max_px, max_edge)
    smaller = [s for s, p in smaller if p < px]
    if not smaller:
        return None
    return max(smaller, key=_pixel_count)


def _image_gen_quality(model: str, size: str, *, force_high: bool = False) -> str | None:
    if not _is_gpt_image2_model(model):
        return None
    if force_high or _pixel_count(size) >= 1920 * 1080:
        return "high"
    return "medium"


def resolve_image_gen_timeouts(
    settings: UserSettings,
    size: str = "",
    *,
    prompt: str = "",
) -> tuple[int, int, int]:
    """按分辨率与画质估算生图等待时长（秒）。

    返回 (tool_timeout, http_read_timeout, per_url_timeout)。
    tool_timeout：整次 generate_image 工具上限；
    per_url_timeout：单个 Base URL 单次请求上限，便于在预算内切换备用端点。
    """
    resolved = resolve_image_gen_size(size, settings, prompt=prompt)
    px = _pixel_count(resolved)
    model = _model_id(settings)
    uses_high = _image_gen_quality(model, resolved) == "high"

    if px <= 1024 * 1024:
        tool, http = 120, 90
    elif px <= 1920 * 1080:
        tool, http = 180, 150
    elif px <= 2048 * 2048:
        tool, http = 300, 240
    elif px <= 2560 * 1440:
        tool, http = 360, 300
    else:
        tool, http = 480, 420

    if uses_high:
        tool = int(tool * 1.25)
        http = int(http * 1.15)

    tool = min(IMAGE_GEN_TOOL_TIMEOUT_MAX, max(IMAGE_GEN_TOOL_TIMEOUT_MIN, tool))
    http = min(IMAGE_GEN_HTTP_TIMEOUT_MAX, max(IMAGE_GEN_HTTP_TIMEOUT_MIN, http))

    url_count = len(_candidate_base_urls(settings))
    if url_count > 1:
        attempts = min(url_count, 3)
        per_url = min(http, max(90, (tool - 30) // attempts))
    else:
        per_url = http

    per_url = min(http, max(60, per_url))
    return tool, http, per_url


def _decode_image_dimensions(data: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return int(img.size[0]), int(img.size[1])


def _actual_size_too_small(actual_w: int, actual_h: int, requested_size: str, *, ratio: float = 0.85) -> bool:
    req_px = _pixel_count(requested_size)
    if not req_px or actual_w <= 0 or actual_h <= 0:
        return False
    return actual_w * actual_h < int(req_px * ratio)


def image_gen_ready(settings: UserSettings) -> bool:
    if not settings.image_gen_enabled:
        return False
    key = settings.image_gen_api_key.strip()
    if not key or key in _PLACEHOLDER_KEYS:
        return False
    if not settings.image_gen_model.strip():
        return False
    return not image_gen_config_hint(settings)


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
    from friday.model_providers import default_image_gen_base_url

    return default_image_gen_base_url(settings.image_gen_provider or "openai_compat")


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


def _images_client(
    api_key: str,
    base_url: str,
    settings: UserSettings | None = None,
    *,
    read_timeout: float | None = None,
):
    from friday.api_connect import build_openai_client

    return build_openai_client(
        api_key,
        base_url,
        settings,
        read_timeout=float(read_timeout if read_timeout is not None else IMAGE_GEN_HTTP_TIMEOUT),
    )


def _download_url(url: str, *, timeout: float | None = None) -> bytes:
    from friday.api_connect import urlopen_request

    req = urllib.request.Request(url, headers={"User-Agent": "Friday-Desktop/1.0"})
    with urlopen_request(req, timeout=float(timeout if timeout is not None else IMAGE_GEN_HTTP_TIMEOUT)) as resp:
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
    settings: UserSettings | None = None,
    force_quality_high: bool = False,
    per_url_timeout: float | None = None,
) -> bytes:
    last_exc: Exception | None = None
    read_timeout = float(per_url_timeout if per_url_timeout is not None else IMAGE_GEN_HTTP_TIMEOUT)
    for base in base_urls:
        try:
            client = _images_client(api_key, base, settings, read_timeout=read_timeout)
            kwargs: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "size": size,
                "response_format": "b64_json",
                "n": 1,
            }
            quality = _image_gen_quality(model, size, force_high=force_quality_high)
            if quality:
                kwargs["quality"] = quality
            response = client.images.generate(**kwargs)
            if not response.data:
                raise ValueError("API 未返回图片")
            item = response.data[0]
            if getattr(item, "b64_json", None):
                return base64.b64decode(item.b64_json)
            url = getattr(item, "url", None)
            if url:
                return _download_url(str(url), timeout=read_timeout)
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
        image_size = _normalize_size(size, settings, prompt=full_prompt)
        model = settings.image_gen_model.strip()
        api_key = settings.image_gen_api_key.strip()
        base_urls = _candidate_base_urls(settings)
        out_path = _resolve_output_path(settings, filename)
        tool_timeout, http_timeout, per_url_timeout = resolve_image_gen_timeouts(
            settings,
            size,
            prompt=full_prompt,
        )

        _log.info(
            "开始生图 | model=%s size=%s provider=%s timeouts tool=%ds per_url=%ds quality=%s",
            model,
            image_size,
            settings.image_gen_provider,
            tool_timeout,
            per_url_timeout,
            _image_gen_quality(model, image_size) or "default",
        )
        t0 = time.perf_counter()
        data = None
        size_warning = ""
        force_quality_high = False
        last_exc: Exception | None = None
        for _ in range(8):
            try:
                data = _call_images_api(
                    api_key=api_key,
                    base_urls=base_urls,
                    model=model,
                    prompt=full_prompt,
                    size=image_size,
                    settings=settings,
                    force_quality_high=force_quality_high,
                    per_url_timeout=float(per_url_timeout),
                )
                actual_w, actual_h = _decode_image_dimensions(data)
                if _actual_size_too_small(actual_w, actual_h, image_size):
                    if not force_quality_high and _is_gpt_image2_model(model):
                        _log.info(
                            "生图实际尺寸偏低，以 quality=high 重试 | requested=%s actual=%dx%d",
                            image_size,
                            actual_w,
                            actual_h,
                        )
                        force_quality_high = True
                        continue
                    size_warning = (
                        f"上游实际输出 {actual_w}×{actual_h}，低于请求的 {image_size}。"
                        "可能是中转站或模型未按 size 参数出图，请确认 image2 是否支持 4K。"
                    )
                    _log.warning(size_warning)
                break
            except RuntimeError as exc:
                last_exc = exc
                msg = str(exc)
                min_pixels = _parse_min_pixels_from_error(msg)
                if min_pixels and _pixel_count(image_size) < min_pixels:
                    upgraded = _pick_size_for_pixels(min_pixels, image_size, settings=settings)
                    if upgraded != image_size:
                        _log.info("生图 API 要求更大尺寸，自动重试 | %s -> %s", image_size, upgraded)
                        image_size = upgraded
                        continue
                if _is_max_size_error(msg):
                    smaller = _step_down_size(image_size, settings=settings)
                    if smaller and smaller != image_size:
                        _log.info("生图尺寸过大，自动降级 | %s -> %s", image_size, smaller)
                        image_size = smaller
                        continue
                raise
        if data is None:
            raise last_exc or RuntimeError("生图 API 调用失败")
        out_path.write_bytes(data)
        actual_w, actual_h = _decode_image_dimensions(data)
        actual_size = f"{actual_w}x{actual_h}"
        elapsed = time.perf_counter() - t0
        _log.info(
            "生图完成 | %.1fs path=%s bytes=%d requested=%s actual=%s",
            elapsed,
            out_path.name,
            len(data),
            image_size,
            actual_size,
        )
        try:
            from friday.artifacts import register_generated_image

            register_generated_image(out_path)
        except Exception:
            _log.exception("登记生图文件失败")
        return {
            "ok": True,
            "path": str(out_path).replace("\\", "/"),
            "filename": out_path.name,
            "width": str(actual_w),
            "height": str(actual_h),
            "model": model,
            "prompt": prompt.strip(),
            "size": actual_size,
            "requested_size": image_size,
            "size_warning": size_warning,
            "bytes": len(data),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        _log.warning("生图失败 | %s", exc)
        return {"ok": False, "error": _format_error(exc)}


def _format_error(exc: Exception) -> str:
    from friday.api_connect import format_api_error

    msg = str(exc)
    lower = msg.lower()
    headline = format_api_error(exc, context="image_gen", service="生图 API").split("\n")[0]
    if "pixel" in lower or "3686400" in msg.replace(",", "") or "1920" in msg:
        return f"{headline}。请提高分辨率或更换支持该尺寸的生图模型"
    if "image input" in lower:
        return f"{headline}。当前模型可能不支持生图，请改用专用生图 model ID"
    return headline or f"生图失败：{msg[:240]}"


def format_generate_result(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return str(result.get("error", "生图失败"))
    path = result.get("path", "")
    size = result.get("size", "")
    requested = str(result.get("requested_size", "") or "").strip()
    warning = str(result.get("size_warning", "") or "").strip()
    model = str(result.get("model", "") or "")
    lines = [f"已生成图片并保存：{path}", f"实际尺寸：{size}，模型：{model}。"]
    if requested and requested != size:
        lines.append(f"请求尺寸：{requested}。")
    if warning:
        lines.append(warning)
    elif _is_gpt_image2_model(model) and requested == "3840x2160" and size == "3840x2160":
        lines.append("（image2/GPT Image 2 最高支持 4K，不支持真 8K）")
    return "\n".join(lines)


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


def _is_ark_image_gen_endpoint(settings: UserSettings, base_url: str = "") -> bool:
    """火山方舟生图：模型为 ep 接入点，/models 列表通常不包含该 id。"""
    provider = (settings.image_gen_provider or "").strip()
    model = settings.image_gen_model.strip()
    base = (base_url or settings.image_gen_base_url or "").strip().lower()
    return (
        provider == "ark"
        or model.startswith("ep-")
        or "volces.com" in base
        or "/ark" in base
    )


def image_gen_config_hint(settings: UserSettings) -> str:
    """生图配置未完成或明显不匹配时的简短原因。"""
    if not settings.image_gen_enabled:
        return ""
    if not settings.image_gen_api_key.strip():
        return "请填写生图 API Key"
    if not settings.image_gen_model.strip():
        return "请填写生图模型或推理接入点"
    provider = (settings.image_gen_provider or "").strip()
    key = settings.image_gen_api_key.strip()
    model = settings.image_gen_model.strip()
    if provider == "ark":
        if key.startswith("sk-"):
            return "Key 格式不匹配：火山方舟需 ark- 开头（请重新粘贴 ark- Key，或切回 OpenAI 兼容中转）"
        if model and not model.startswith("ep-"):
            return "火山方舟请填写 ep- 开头的推理接入点"
    if _is_ark_image_gen_endpoint(settings) and key.startswith("sk-"):
        return "Key 格式不匹配：火山方舟需 ark- 开头的 Key"
    return ""


def _extract_api_error_message(body: str) -> str:
    import json

    text = (body or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:240]
    if not isinstance(payload, dict):
        return text[:240]
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "").strip()
    if isinstance(err, str):
        return err.strip()
    return str(payload.get("message") or "").strip()


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _humanize_image_gen_size_error(body: str, *, settings: UserSettings | None = None) -> str | None:
    detail = _extract_api_error_message(body)
    combined = f"{detail} {body}"
    lower = combined.lower()
    if not ("size" in lower and ("pixel" in lower or "not valid" in lower)):
        return None
    px = _parse_min_pixels_from_error(combined)
    if "at most" in lower or "too large" in lower or "maximum" in lower:
        max_px = px or _ARK_MAX_PIXELS
        if settings:
            valid = _catalog_for_limits(
                _minimum_pixels(settings),
                _maximum_pixels(settings),
                _maximum_edge(settings),
            )
            recommended = max(valid, key=lambda item: item[1])[0] if valid else "4096x4096"
        else:
            recommended = "4096x4096"
        rw, rh = _parse_size_str(recommended)
        size_label = f"{rw}×{rh}" if rw and rh else recommended
        return (
            f"生图尺寸过大：该模型最多支持 {max_px:,} 像素"
            f"（建议使用 {size_label}，即 {recommended}）"
        )
    if not px:
        return None
    recommended = _pick_size_for_pixels(px, settings=settings)
    rw, rh = _parse_size_str(recommended)
    size_label = f"{rw}×{rh}" if rw and rh else recommended
    return (
        f"生图尺寸过小：该模型要求至少 {px:,} 像素"
        f"（建议使用 {size_label}，即 {recommended}）"
    )


def _humanize_image_gen_http_error(
    code: int,
    body: str,
    *,
    base_url: str,
    model: str,
    settings: UserSettings | None = None,
) -> str:
    detail = _extract_api_error_message(body)
    lower = f"{detail} {body}".lower()
    host = base_url.lower()
    size_hint = _humanize_image_gen_size_error(body, settings=settings)

    if code in {401, 403}:
        if "volces" in host:
            return "火山方舟 API Key 无效或已过期（请使用 ark- 开头的 Key）"
        return "生图 API Key 无效或已过期，请检查 Key 是否与当前服务商匹配"

    if code == 404:
        if model.startswith("ep-"):
            return (
                f"推理接入点「{model}」不存在或当前 Key 无权访问。"
                "请在火山方舟控制台确认 ep ID 是否正确、是否已开通图像生成"
            )
        return (
            "生图接口地址不正确（HTTP 404）。"
            "请确认 Base URL 形如 https://ark.cn-beijing.volces.com/api/v3"
        )

    if code in {400, 422}:
        if size_hint:
            return size_hint
        if any(k in lower for k in ("model", "endpoint", "inference", "接入点")) and any(
            k in lower for k in ("not found", "invalid", "does not exist", "unknown", "不存在", "无效", "未找到")
        ):
            return f"模型/接入点「{model}」无效或无法用于生图，请核对名称与服务商"
        if "authentication" in lower or "api key" in lower or "invalid_api_key" in lower:
            return "API Key 无效或无权调用生图"
        if detail:
            return f"生图请求被拒绝：{detail}"
        return "生图请求参数有误，请检查模型名、Key 与 Base URL 是否匹配"

    if code >= 500:
        return f"生图服务端暂时异常，请稍后重试" + (f"（{detail}）" if detail else "")

    if detail:
        return f"生图 API 异常：{detail}"
    return f"生图 API 返回 HTTP {code}，请检查 Base URL、Key 与模型名"


def verify_image_gen_api(
    settings: UserSettings,
    *,
    timeout: float | None = None,
    primary_only: bool = False,
    strict: bool = False,
    deadline: float | None = None,
) -> tuple[bool, str]:
    """认证探测。strict=True 用于设置页测试：校验模型并探测 /images/generations。"""
    import time as _time

    from friday.config import (
        IMAGE_GEN_IMAGES_PROBE_TIMEOUT,
        IMAGE_GEN_PROBE_TIMEOUT,
        STATUS_BAR_IMAGE_GEN_PROBE_TIMEOUT,
    )

    def _past_deadline() -> bool:
        return deadline is not None and _time.monotonic() >= deadline

    if not image_gen_ready(settings):
        return False, "Key 或模型未配置"

    hint = image_gen_config_hint(settings)
    if strict and hint:
        return False, hint

    default_timeout = STATUS_BAR_IMAGE_GEN_PROBE_TIMEOUT if primary_only else IMAGE_GEN_PROBE_TIMEOUT
    if strict:
        default_timeout = max(default_timeout, 25.0)
    probe_timeout = float(timeout if timeout is not None else default_timeout)
    api_key = settings.image_gen_api_key.strip()
    model = settings.image_gen_model.strip()
    last_msg = ""
    bases = _candidate_base_urls(settings)
    if primary_only:
        bases = bases[:1]

    for base in bases:
        if _past_deadline():
            break
        http_ok, http_msg = _verify_image_gen_models_http(
            api_key,
            base,
            settings,
            timeout=min(probe_timeout, 8.0),
            strict=strict,
        )
        if http_ok is False:
            last_msg = http_msg
        elif http_ok is True and strict:
            last_msg = http_msg

        ark_endpoint = _is_ark_image_gen_endpoint(settings, base)
        skip_images = _should_skip_images_probe(base, settings, strict=strict) or (
            primary_only and not strict
        )
        if not strict and ark_endpoint and http_ok is not True:
            skip_images = False
        if not skip_images:
            if _past_deadline():
                break
            images_timeout = probe_timeout if strict else min(probe_timeout, IMAGE_GEN_IMAGES_PROBE_TIMEOUT)
            if deadline is not None:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    break
                images_timeout = min(images_timeout, max(3.0, remaining))
            images_ok, images_msg = _verify_image_gen_images_auth(
                api_key,
                base,
                settings,
                timeout=images_timeout,
                strict=strict,
                max_retries=2 if strict else 4,
            )
            if images_ok is True:
                return True, images_msg
            if images_ok is False:
                last_msg = images_msg
            elif images_ok is None:
                last_msg = images_msg or "生图探测超时（端点响应较慢）"
                if not strict and ark_endpoint and http_ok is not False:
                    return True, last_msg

        elif http_ok is True and not strict:
            return True, http_msg

        if not strict and not primary_only:
            try:
                from friday.api_connect import build_openai_client, format_api_error

                client = build_openai_client(
                    api_key,
                    base,
                    settings,
                    read_timeout=min(probe_timeout, 6.0),
                    max_retries=0,
                )
                response = client.models.list()
                ids = {getattr(item, "id", "") for item in (getattr(response, "data", None) or [])}
                ids.discard("")
                if ids and model not in ids:
                    last_msg = f"models 列表未含 {model}，生图可能失败"
                    continue
                return True, "API 认证通过"
            except Exception as exc:  # noqa: BLE001
                from friday.api_connect import format_api_error

                last_msg = format_api_error(exc, context="api_test", service="生图 API").split("\n")[0][:200]

    return False, last_msg or "所有端点均无法用于生图，请检查 Key、Base URL 与模型名"


def _settings_test_timed_out(last_msg: str) -> tuple[bool, str]:
    hint = (
        "生图测试超时（端点响应过慢）。"
        "请检查 Base URL 与模型名是否正确；主 URL 失败时对话生图会自动尝试备用 URL。"
    )
    if last_msg.strip():
        return False, f"{last_msg}\n{hint}"
    return False, hint


def _should_skip_images_probe(base_url: str, settings: UserSettings, *, strict: bool = False) -> bool:
    """状态栏轻量探测可跳过慢速 POST；设置页 strict 测试必须走 images。"""
    if strict:
        return False
    provider = (settings.image_gen_provider or "").strip()
    if provider == "ark":
        return True
    host = base_url.lower()
    return "volces.com" in host or "/ark" in host


def _probe_error_inconclusive(exc: BaseException) -> bool:
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return True
    reason = getattr(exc, "reason", None)
    return isinstance(reason, TimeoutError)


def _verify_image_gen_models_http(
    api_key: str,
    base_url: str,
    settings: UserSettings,
    *,
    timeout: float,
    strict: bool = False,
) -> tuple[bool | None, str]:
    """GET /v1/models；None 表示端点不支持，应尝试其它方式。"""
    import json
    import urllib.error
    import urllib.request

    from friday.api_connect import apply_network_environment, urlopen_request

    apply_network_environment(settings)
    url = f"{base_url.rstrip('/')}/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Friday-Desktop/1.0",
        },
    )
    try:
        with urlopen_request(req, timeout=timeout) as resp:
            if resp.status != 200:
                body = resp.read(65536).decode("utf-8", errors="replace")
                return False, _humanize_image_gen_http_error(
                    resp.status,
                    body,
                    base_url=base_url,
                    model=settings.image_gen_model.strip(),
                )
            body = resp.read(65536)
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return (True, "生图 API 可达") if strict else (True, "API 认证通过")
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            ids = {str(item.get("id", "")) for item in data if isinstance(item, dict)}
            ids.discard("")
            model = settings.image_gen_model.strip()
            if ids and model and model not in ids:
                if strict and _is_ark_image_gen_endpoint(settings, base_url):
                    return None, ""
                if strict:
                    return (
                        False,
                        f"模型「{model}」不在该地址的可用列表中。"
                        "火山方舟请确认 ep 接入点是否正确，或改用 /images 探测结果",
                    )
                return None, ""
        return (True, "生图 API 可达（models）") if strict else (True, "API 认证通过")
    except urllib.error.HTTPError as exc:
        body = _read_http_error_body(exc)
        if exc.code in {401, 403}:
            return False, _humanize_image_gen_http_error(
                exc.code, body, base_url=base_url, model=settings.image_gen_model.strip()
            )
        if exc.code == 404:
            return None, ""
        return False, _humanize_image_gen_http_error(
            exc.code, body, base_url=base_url, model=settings.image_gen_model.strip()
        )
    except urllib.error.URLError as exc:
        if _probe_error_inconclusive(exc):
            return None, ""
        return False, str(exc.reason or exc)[:200]
    except Exception as exc:  # noqa: BLE001
        if _probe_error_inconclusive(exc):
            return None, ""
        text = str(exc).lower()
        if "404" in text or "not found" in text:
            return None, ""
        return False, str(exc)[:200]


def _post_images_generation_probe(
    api_key: str,
    base_url: str,
    settings: UserSettings,
    *,
    size: str,
    timeout: float,
    strict: bool,
) -> tuple[bool | None, str]:
    """单次 POST /images/generations 探测。"""
    import json
    import urllib.error
    import urllib.request

    from friday.api_connect import apply_network_environment, urlopen_request

    apply_network_environment(settings)
    url = f"{base_url.rstrip('/')}/images/generations"
    model = settings.image_gen_model.strip()
    payload: dict[str, Any] = {
        "model": model,
        "prompt": "Friday connectivity test",
        "n": 1,
        "size": size,
        "response_format": "b64_json",
    }
    if strict and _is_gpt_image2_model(model):
        payload["quality"] = "low"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Friday-Desktop/1.0",
        },
    )
    try:
        with urlopen_request(req, timeout=timeout) as resp:
            if resp.status < 400:
                if strict:
                    return True, f"生图端点可用，模型「{model}」可正常调用（探测尺寸 {size}）"
                return True, "生图 API 认证通过"
            raw = resp.read(4096).decode("utf-8", errors="replace")
            return False, _humanize_image_gen_http_error(
                resp.status,
                raw,
                base_url=base_url,
                model=model,
                settings=settings,
            )
    except urllib.error.HTTPError as exc:
        raw = _read_http_error_body(exc)
        if exc.code in {400, 422} and not strict:
            return True, "生图 API 认证通过"
        if exc.code in {401, 403, 404, 400, 422}:
            return False, _humanize_image_gen_http_error(
                exc.code,
                raw,
                base_url=base_url,
                model=model,
                settings=settings,
            )
        return False, _humanize_image_gen_http_error(
            exc.code,
            raw,
            base_url=base_url,
            model=model,
            settings=settings,
        )
    except urllib.error.URLError as exc:
        if _probe_error_inconclusive(exc):
            return None, ""
        return False, str(exc.reason or exc)[:200]
    except Exception as exc:  # noqa: BLE001
        if _probe_error_inconclusive(exc):
            return None, ""
        text = str(exc).lower()
        if "404" in text or "not found" in text:
            return None, ""
        return False, str(exc)[:200]


def _verify_image_gen_images_auth(
    api_key: str,
    base_url: str,
    settings: UserSettings,
    *,
    timeout: float,
    strict: bool = False,
    max_retries: int = 4,
) -> tuple[bool | None, str]:
    """POST /images/generations 探测；尺寸不足时自动提升并重试。"""
    size = resolve_image_gen_size("", settings)
    last_msg = ""
    for _ in range(max(1, max_retries)):
        ok, msg = _post_images_generation_probe(
            api_key,
            base_url,
            settings,
            size=size,
            timeout=timeout,
            strict=strict,
        )
        if ok is True:
            return True, msg
        if ok is None:
            last_msg = msg or "生图探测超时（端点响应较慢）"
            if strict:
                return None, last_msg
            continue
        last_msg = msg
        min_px = _parse_min_pixels_from_error(msg)
        if not min_px and "尺寸过小" in msg:
            min_px = _HIGH_RES_MIN_PIXELS
        if not min_px:
            break
        upgraded = _pick_size_for_pixels(min_px, size, settings=settings)
        if upgraded == size:
            break
        _log.info("生图探测尺寸自动提升 | %s -> %s", size, upgraded)
        size = upgraded
    return False, last_msg


def _strict_test_via_images_client(
    settings: UserSettings,
    *,
    timeout: float,
) -> tuple[bool, str]:
    """设置页严格测试：与实际生图同路径，避免短 POST 探测超时误判。"""
    from friday.api_connect import format_api_error

    model = settings.image_gen_model.strip()
    size = resolve_image_gen_size("", settings)
    try:
        data = _call_images_api(
            api_key=settings.image_gen_api_key.strip(),
            base_urls=_candidate_base_urls(settings)[:1],
            model=model,
            prompt="Friday connectivity test",
            size=size,
            settings=settings,
            per_url_timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return False, format_api_error(exc, context="api_test", service="生图 API").split("\n")[0][:240]
    if len(data) < 64:
        return False, "生图 API 返回的图片数据过小"
    return True, f"生图测试通过，模型「{model}」可正常调用（探测尺寸 {size}）"


def test_image_gen_connection(settings: UserSettings) -> tuple[bool, str]:
    import time

    from friday.config import IMAGE_GEN_HTTP_TIMEOUT_MIN

    if not settings.image_gen_enabled:
        return False, "请先勾选「启用生图」"
    if not settings.image_gen_api_key.strip():
        return False, "请填写生图 API Key"
    if not settings.image_gen_model.strip():
        return False, "请填写生图模型名称（测试时可向 API 提供商确认）"

    hint = image_gen_config_hint(settings)
    if hint:
        from friday.category_profiles import repair_category_settings

        repaired = repair_category_settings(settings, "image_gen")
        if repaired is not settings:
            settings = repaired
            hint = image_gen_config_hint(settings)
    if hint:
        return False, hint

    if _is_ark_image_gen_endpoint(settings):
        client_timeout = max(90.0, float(IMAGE_GEN_HTTP_TIMEOUT_MIN))
        deadline = time.monotonic() + client_timeout + 15.0
        ok, message = _strict_test_via_images_client(settings, timeout=client_timeout)
        if ok:
            return True, message
        if time.monotonic() >= deadline:
            return _settings_test_timed_out(message)
        return ok, message

    deadline = time.monotonic() + 45.0
    ok, message = verify_image_gen_api(
        settings,
        strict=True,
        primary_only=True,
        timeout=25.0,
        deadline=deadline,
    )
    if ok:
        return True, message
    if message and message != "所有端点均无法用于生图，请检查 Key、Base URL 与模型名":
        if time.monotonic() >= deadline:
            return _settings_test_timed_out(message)
        return ok, message

    client_timeout = max(60.0, float(IMAGE_GEN_HTTP_TIMEOUT_MIN))
    ok, message = _strict_test_via_images_client(settings, timeout=client_timeout)
    if ok:
        return True, message
    if time.monotonic() >= deadline + client_timeout:
        return _settings_test_timed_out(message)
    return ok, message or "生图 API 不可用，请检查 Key、Base URL 与模型/接入点"
