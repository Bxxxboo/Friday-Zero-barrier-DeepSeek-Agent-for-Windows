"""统一 API 网络层：SSL 证书、代理、超时、连通性诊断。"""

from __future__ import annotations

import asyncio
import os
import socket
import ssl
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from friday.config import API_CONNECT_TIMEOUT, API_MAX_RETRIES, API_READ_TIMEOUT
from friday.logging_config import get_logger
from friday.storage import UserSettings

_log = get_logger("api_connect")

_SSL_BOOTSTRAPPED = False
_PROBE_CACHE: dict[str, tuple[float, bool, str]] = {}
_AUTH_STATUS_CACHE: dict[str, tuple[float, bool, str]] = {}
_PROBE_LOCK = threading.Lock()
_PROBE_TTL = 90.0
_AUTH_STATUS_TTL = 120.0
_AUTH_STATUS_TTL_OK = 3600.0


def ensure_ssl_environment() -> str | None:
    """设置 SSL_CERT_FILE / REQUESTS_CA_BUNDLE，返回 CA 路径。"""
    global _SSL_BOOTSTRAPPED
    if _SSL_BOOTSTRAPPED:
        return os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")

    ca_path: str | None = None
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidate = os.path.join(meipass, "certifi", "cacert.pem")
            if os.path.isfile(candidate):
                ca_path = candidate
    if ca_path is None:
        try:
            import certifi

            ca_path = certifi.where()
        except ImportError:
            ca_path = None

    if ca_path and os.path.isfile(ca_path):
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)

    _SSL_BOOTSTRAPPED = True
    return ca_path


def ssl_context() -> ssl.SSLContext:
    ensure_ssl_environment()
    return ssl.create_default_context()


def apply_network_environment(settings: UserSettings | None = None) -> None:
    """启动时应用 NO_PROXY 与用户配置的 HTTP(S) 代理。"""
    ensure_ssl_environment()

    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    for item in ("127.0.0.1", "localhost", "<loopback>"):
        if item not in parts:
            parts.append(item)
    merged = ",".join(parts)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged

    if settings is None:
        return
    proxy = (getattr(settings, "api_proxy", "") or "").strip()
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy


def resolve_httpx_proxy(settings: UserSettings | None) -> str | None:
    if settings is None:
        return None
    explicit = (getattr(settings, "api_proxy", "") or "").strip()
    return explicit or None


def build_httpx_client(
    settings: UserSettings | None = None,
    *,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
    write_timeout: float = 30.0,
):
    import httpx

    if settings is not None:
        apply_network_environment(settings)
    else:
        ensure_ssl_environment()

    trust_env = True if settings is None else bool(getattr(settings, "api_trust_env", True))
    proxy = resolve_httpx_proxy(settings)
    timeout = httpx.Timeout(
        connect=float(connect_timeout or API_CONNECT_TIMEOUT),
        read=float(read_timeout or API_READ_TIMEOUT),
        write=write_timeout,
        pool=10.0,
    )
    return httpx.Client(
        timeout=timeout,
        proxy=proxy,
        trust_env=trust_env,
        follow_redirects=True,
    )


def build_openai_client(
    api_key: str,
    base_url: str,
    settings: UserSettings | None = None,
    *,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
    max_retries: int | None = None,
):
    from openai import OpenAI

    http_client = build_httpx_client(
        settings,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )
    url = (base_url or "").strip().rstrip("/")
    return OpenAI(
        api_key=api_key,
        base_url=url,
        http_client=http_client,
        max_retries=max_retries if max_retries is not None else API_MAX_RETRIES,
    )


def parse_host_port(url: str) -> tuple[str, int, str]:
    parsed = urlparse((url or "").strip())
    host = parsed.hostname or ""
    if not host:
        raise ValueError("无效的 API Base URL")
    if parsed.port:
        port = int(parsed.port)
    else:
        port = 443 if parsed.scheme != "http" else 80
    return host, port, parsed.scheme or "https"


@dataclass(frozen=True)
class ConnectivityStep:
    name: str
    ok: bool
    detail: str
    hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "hint": self.hint,
        }


def _probe_dns(host: str, port: int) -> ConnectivityStep:
    try:
        addrs = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = sorted({item[4][0] for item in addrs})[:4]
        return ConnectivityStep("DNS 解析", True, f"{host} → {', '.join(ips)}")
    except socket.gaierror as exc:
        return ConnectivityStep(
            "DNS 解析",
            False,
            f"{host} 无法解析: {exc}",
            "检查网络/DNS；公司网络可尝试配置代理（设置 → API 连接 → 网络代理）",
        )


def _probe_tcp(host: str, port: int) -> ConnectivityStep:
    try:
        with socket.create_connection((host, port), timeout=min(API_CONNECT_TIMEOUT, 12.0)):
            pass
        return ConnectivityStep("TCP 连接", True, f"{host}:{port} 可达")
    except (TimeoutError, socket.timeout) as exc:
        return ConnectivityStep(
            "TCP 连接",
            False,
            f"{host}:{port} 连接超时: {exc}",
            "可能被防火墙拦截；请配置 HTTP/HTTPS 代理或检查 VPN",
        )
    except OSError as exc:
        return ConnectivityStep(
            "TCP 连接",
            False,
            f"{host}:{port} 连接失败: {exc}",
            "检查网络、防火墙或代理设置",
        )


def _probe_ssl(host: str, port: int) -> ConnectivityStep:
    if port == 80:
        return ConnectivityStep("SSL/TLS", True, "HTTP 明文，跳过 TLS")
    try:
        ctx = ssl_context()
        with socket.create_connection((host, port), timeout=min(API_CONNECT_TIMEOUT, 12.0)) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert() or {}
        subject = ""
        for field in cert.get("subject", ()):
            if field and field[0][0] == "commonName":
                subject = str(field[0][1])
                break
        not_after = cert.get("notAfter", "")
        detail = f"证书 {subject or host}" + (f"，到期 {not_after}" if not_after else "")
        return ConnectivityStep("SSL/TLS", True, detail)
    except ssl.SSLError as exc:
        return ConnectivityStep(
            "SSL/TLS",
            False,
            f"证书验证失败: {exc}",
            "检查系统时间；企业代理需导入根证书或配置正确代理",
        )
    except Exception as exc:  # noqa: BLE001
        return ConnectivityStep("SSL/TLS", False, str(exc)[:200], "检查网络与代理")


def _probe_chat_api(
    *,
    base_url: str,
    api_key: str,
    model: str,
    settings: UserSettings | None,
    read_timeout: float | None = None,
) -> ConnectivityStep:
    if not api_key.strip():
        return ConnectivityStep(
            "API 认证",
            False,
            "API Key 为空",
            "在设置中填写并保存 API Key",
        )
    try:
        client = build_openai_client(
            api_key.strip(),
            base_url,
            settings,
            read_timeout=read_timeout if read_timeout is not None else min(API_READ_TIMEOUT, 45.0),
        )
        response = client.chat.completions.create(
            model=model or "deepseek-chat",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
        text = (response.choices[0].message.content or "ok").strip()
        return ConnectivityStep("API 认证", True, f"模型响应: {text[:80]}")
    except Exception as exc:  # noqa: BLE001
        msg = format_api_error(exc, context="api_test", service="大模型 API")
        return ConnectivityStep("API 认证", False, msg.split("\n")[0][:200], _extract_hint(msg))


def _extract_hint(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines[-1]
    return ""


def diagnose_llm(settings: UserSettings, *, include_api: bool = True) -> list[ConnectivityStep]:
    base_url = (settings.base_url or UserSettings.base_url).strip()
    steps: list[ConnectivityStep] = []
    try:
        host, port, _scheme = parse_host_port(base_url)
    except ValueError as exc:
        return [ConnectivityStep("Base URL", False, str(exc), "请填写完整 https:// 地址")]

    steps.append(ConnectivityStep("Base URL", True, base_url))
    for fn in (_probe_dns, _probe_tcp, _probe_ssl):
        step = fn(host, port)
        steps.append(step)
        if not step.ok:
            return steps

    if include_api:
        steps.append(
            _probe_chat_api(
                base_url=base_url,
                api_key=settings.api_key,
                model=settings.model,
                settings=settings,
            )
        )
    return steps


def diagnose_vision(settings: UserSettings, *, include_api: bool = True) -> list[ConnectivityStep]:
    from friday.vision import _TEST_PNG_B64, vision_ready

    base_url = (settings.vision_base_url or UserSettings.vision_base_url).strip()
    steps: list[ConnectivityStep] = []
    if not settings.vision_enabled:
        return [ConnectivityStep("视觉辅助", False, "未启用", "勾选「启用视觉辅助」")]
    if not vision_ready(settings):
        return [ConnectivityStep("视觉辅助", False, "Key 未配置", "填写视觉 API Key 并保存")]

    try:
        host, port, _ = parse_host_port(base_url)
    except ValueError as exc:
        return [ConnectivityStep("Base URL", False, str(exc), "请填写火山引擎 API 地址")]

    steps.append(ConnectivityStep("Base URL", True, base_url))
    for fn in (_probe_dns, _probe_tcp, _probe_ssl):
        step = fn(host, port)
        steps.append(step)
        if not step.ok:
            return steps

    if not include_api:
        return steps

    if not settings.vision_model.strip():
        steps.append(ConnectivityStep(
            "视觉端点",
            False,
            "未填写 ep- 端点 ID",
            "在火山引擎控制台创建「视觉理解」接入点",
        ))
        return steps

    try:
        client = build_openai_client(
            settings.vision_api_key.strip(),
            base_url,
            settings,
            read_timeout=min(API_READ_TIMEOUT, 60.0),
        )
        client.chat.completions.create(
            model=settings.vision_model.strip(),
            max_tokens=8,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "ok"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{_TEST_PNG_B64}",
                            "detail": "low",
                        },
                    },
                ],
            }],
        )
        steps.append(ConnectivityStep("视觉 API", True, f"端点 {settings.vision_model.strip()} 可用"))
    except Exception as exc:  # noqa: BLE001
        msg = format_api_error(exc, context="api_test", service="视觉 API")
        steps.append(ConnectivityStep("视觉 API", False, msg.split("\n")[0][:200], _extract_hint(msg)))
    return steps


def diagnose_image_gen(settings: UserSettings, *, include_api: bool = False) -> list[ConnectivityStep]:
    from friday.image_gen import _candidate_base_urls, image_gen_ready

    if not settings.image_gen_enabled:
        return [ConnectivityStep("生图", False, "未启用", "勾选「启用生图」")]
    if not image_gen_ready(settings):
        return [ConnectivityStep("生图", False, "Key 或模型未配置", "填写生图 Key 与模型名")]

    urls = _candidate_base_urls(settings)
    if not urls:
        return [ConnectivityStep("生图", False, "无可用 Base URL", "填写生图 API 地址")]

    all_steps: list[ConnectivityStep] = []
    any_host_ok = False
    for idx, base_url in enumerate(urls[:3]):
        label = "主地址" if idx == 0 else f"备用 {idx}"
        try:
            host, port, _ = parse_host_port(base_url)
        except ValueError as exc:
            all_steps.append(ConnectivityStep(label, False, str(exc)))
            continue
        all_steps.append(ConnectivityStep(f"{label} URL", True, base_url))
        host_ok = True
        for fn in (_probe_dns, _probe_tcp, _probe_ssl):
            step = fn(host, port)
            all_steps.append(ConnectivityStep(f"{label} · {step.name}", step.ok, step.detail, step.hint))
            if not step.ok:
                host_ok = False
                break
        if host_ok:
            any_host_ok = True

    if not any_host_ok:
        all_steps.append(ConnectivityStep(
            "生图网络",
            False,
            "所有 Base URL 均不可达",
            "检查网络/代理，或更换备用中转地址",
        ))
    elif include_api:
        from friday.image_gen import verify_image_gen_api

        ok, message = verify_image_gen_api(settings)
        all_steps.append(ConnectivityStep(
            "生图 API",
            ok,
            message[:240],
            "" if ok else "确认模型名与 Key 是否匹配当前 Provider",
        ))
    else:
        all_steps.append(ConnectivityStep("生图网络", True, "至少一个地址网络可达"))
    return all_steps


def diagnose_all(settings: UserSettings, *, full_api: bool = False) -> dict[str, Any]:
    llm = diagnose_llm(settings, include_api=full_api)
    vision = diagnose_vision(settings, include_api=full_api)
    image_gen = diagnose_image_gen(settings, include_api=full_api)
    return {
        "llm": {"ok": bool(llm) and llm[-1].ok, "steps": [s.as_dict() for s in llm]},
        "vision": {"ok": bool(vision) and vision[-1].ok, "steps": [s.as_dict() for s in vision]},
        "image_gen": {"ok": bool(image_gen) and image_gen[-1].ok, "steps": [s.as_dict() for s in image_gen]},
    }


def quick_reachability(base_url: str, settings: UserSettings | None = None) -> tuple[bool, str]:
    """轻量探测（DNS+TCP+SSL），带缓存。"""
    url = (base_url or "").strip()
    if not url:
        return False, "未配置地址"
    cache_key = f"{url}|{(getattr(settings, 'api_proxy', '') or '').strip()}"
    now = time.time()
    with _PROBE_LOCK:
        cached = _PROBE_CACHE.get(cache_key)
        if cached:
            ok, detail = cached[1], cached[2]
            ttl = _PROBE_TTL if ok else min(_PROBE_TTL, 30.0)
            if now - cached[0] < ttl:
                return ok, detail

    if settings is not None:
        apply_network_environment(settings)

    try:
        host, port, _ = parse_host_port(url)
        for step in (_probe_dns(host, port), _probe_tcp(host, port), _probe_ssl(host, port)):
            if not step.ok:
                with _PROBE_LOCK:
                    _PROBE_CACHE[cache_key] = (now, False, step.detail)
                return False, step.detail
        detail = f"{host} 网络可达"
        with _PROBE_LOCK:
            _PROBE_CACHE[cache_key] = (now, True, detail)
        return True, detail
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)[:200]
        with _PROBE_LOCK:
            _PROBE_CACHE[cache_key] = (now, False, detail)
        return False, detail


def invalidate_probe_cache(*, clear_auth: bool = True) -> None:
    with _PROBE_LOCK:
        _PROBE_CACHE.clear()
        if clear_auth:
            _AUTH_STATUS_CACHE.clear()


def _drop_auth_status_key(cache_key: str) -> None:
    with _PROBE_LOCK:
        _AUTH_STATUS_CACHE.pop(cache_key, None)


def invalidate_auth_status_for_settings_change(before: UserSettings, after: UserSettings) -> None:
    """仅当对应服务的 Key/模型/地址变更时清除认证缓存，避免保存设置抹掉刚通过的测试结果。"""
    proxy_before = (getattr(before, "api_proxy", "") or "").strip()
    proxy_after = (getattr(after, "api_proxy", "") or "").strip()
    if proxy_before != proxy_after:
        invalidate_probe_cache(clear_auth=True)
        return

    llm_before = (
        (before.api_key or "")[-6:],
        (before.base_url or UserSettings.base_url).strip(),
        (before.model or "").strip(),
    )
    llm_after = (
        (after.api_key or "")[-6:],
        (after.base_url or UserSettings.base_url).strip(),
        (after.model or "").strip(),
    )
    if llm_before != llm_after:
        _drop_auth_status_key(_auth_status_key("llm", before))

    vision_before = (
        (before.vision_api_key or "")[-6:],
        (before.vision_base_url or UserSettings.vision_base_url).strip(),
        (before.vision_model or "").strip(),
        bool(before.vision_enabled),
    )
    vision_after = (
        (after.vision_api_key or "")[-6:],
        (after.vision_base_url or UserSettings.vision_base_url).strip(),
        (after.vision_model or "").strip(),
        bool(after.vision_enabled),
    )
    if vision_before != vision_after:
        _drop_auth_status_key(_auth_status_key("vision", before))

    from friday.image_gen import default_base_url

    image_before = (
        (before.image_gen_api_key or "")[-6:],
        default_base_url(before),
        (before.image_gen_model or "").strip(),
        (before.image_gen_provider or "").strip(),
        bool(before.image_gen_enabled),
    )
    image_after = (
        (after.image_gen_api_key or "")[-6:],
        default_base_url(after),
        (after.image_gen_model or "").strip(),
        (after.image_gen_provider or "").strip(),
        bool(after.image_gen_enabled),
    )
    if image_before != image_after:
        _drop_auth_status_key(_auth_status_key("image_gen", before))


def _auth_status_key(service: str, settings: UserSettings) -> str:
    proxy = (getattr(settings, "api_proxy", "") or "").strip()
    if service == "llm":
        fp = (settings.api_key or "")[-6:]
        return f"llm|{settings.base_url}|{settings.model}|{fp}|{proxy}"
    if service == "vision":
        fp = (settings.vision_api_key or "")[-6:]
        return f"vision|{settings.vision_base_url}|{settings.vision_model}|{fp}|{proxy}"
    from friday.image_gen import default_base_url

    fp = (settings.image_gen_api_key or "")[-6:]
    base = default_base_url(settings)
    return f"image_gen|{base}|{settings.image_gen_model}|{fp}|{proxy}"


def _read_auth_status(cache_key: str, *, service: str = "") -> tuple[bool, str] | None:
    now = time.time()
    with _PROBE_LOCK:
        cached = _AUTH_STATUS_CACHE.get(cache_key)
        if not cached:
            return None
        ok, detail = cached[1], cached[2]
        ttl = _AUTH_STATUS_TTL_OK if ok else _AUTH_STATUS_TTL
        if now - cached[0] < ttl:
            return ok, detail
    return None


def read_cached_service_status(service: str, settings: UserSettings) -> tuple[bool, str] | None:
    """读取最近一次测试/探测缓存，不发起网络请求。"""
    if service == "llm":
        if not settings.api_ready:
            return None
    elif service == "vision":
        from friday.vision import vision_ready

        if not settings.vision_enabled or not vision_ready(settings):
            return None
    elif service == "image_gen":
        from friday.image_gen import image_gen_ready

        if not settings.image_gen_enabled or not image_gen_ready(settings):
            return None
    else:
        return None
    cache_key = _auth_status_key(service, settings)
    return _read_auth_status(cache_key, service=service)


def is_transient_api_error(raw: Any) -> bool:
    """瞬态失败（超时、限流、网关抖动）——不应长期污染「API 离线」状态。"""
    text = str(raw or "").strip().lower()
    if not text and raw is not None:
        text = type(raw).__name__.lower()
    if not text:
        return False
    transient_tokens = (
        "readtimeout",
        "read timeout",
        "read timed out",
        "response timed out",
        "waiting for response",
        "apitimeouterror",
        "429",
        "rate limit",
        "too many requests",
        "502",
        "503",
        "504",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "connection reset",
        "connection aborted",
        "remote disconnected",
        "temporarily unavailable",
        "overloaded",
        "server overloaded",
    )
    if any(token in text for token in transient_tokens):
        return True
    if "timeout" in text or "timed out" in text:
        return "connect" not in text and "connection refused" not in text
    return False


def _peek_service_ok_cache(service: str, settings: UserSettings) -> tuple[bool, str] | None:
    cache_key = _auth_status_key(service, settings)
    cached = _read_auth_status(cache_key, service=service)
    if cached and cached[0]:
        return cached
    return None


def _is_hard_auth_failure(detail: str) -> bool:
    """明确配置/鉴权错误：应覆盖此前的「在线」缓存。"""
    lower = (detail or "").strip().lower()
    if not lower:
        return False
    if any(
        token in lower
        for token in (
            "invalid_api_key",
            "invalid api key",
            "api key 为空",
            "模型未配置",
            "未配置",
            "请填写",
            "请先勾选",
            "key 无效",
            "key 对此中转无效",
            "401",
            "403",
            "余额不足",
            "insufficient_balance",
            "unauthorized",
        )
    ):
        return True
    return lower.startswith("请") and any(k in lower for k in ("填写", "勾选", "配置"))


def _should_preserve_service_ok_cache(service: str, settings: UserSettings, detail: str) -> bool:
    prev = _peek_service_ok_cache(service, settings)
    if not prev:
        return False
    if is_transient_api_error(detail):
        return True
    return not _is_hard_auth_failure(detail)


def record_service_status(
    service: str,
    settings: UserSettings,
    ok: bool,
    detail: str = "",
    *,
    transient: bool = False,
) -> None:
    """记录一次真实 API 调用结果（测试连接 / 对话成功或失败）。"""
    if not ok and transient:
        return
    cache_key = _auth_status_key(service, settings)
    if not ok and _should_preserve_service_ok_cache(service, settings, detail):
        return
    with _PROBE_LOCK:
        _AUTH_STATUS_CACHE[cache_key] = (time.time(), bool(ok), (detail or "")[:240])


def test_llm_service(settings: UserSettings) -> tuple[bool, str]:
    """与设置页「测试连接」相同逻辑，并写入状态缓存。"""
    from friday.brain import DeepSeekBrain
    from friday.error_hints import classify_error
    from friday.llm_profiles import llm_config_hint

    config_hint = llm_config_hint(settings)
    if config_hint:
        return False, config_hint
    if not settings.api_ready:
        hint = classify_error("", context="api_key_missing")
        return False, f"{hint.detail}\n{hint.hint}"
    ok, message = DeepSeekBrain(settings).test_connection()
    detail = message if ok else message.split("\n")[0]
    if ok:
        record_service_status("llm", settings, True, detail)
        return True, message
    if _should_preserve_service_ok_cache("llm", settings, detail):
        prev = _peek_service_ok_cache("llm", settings)
        if prev:
            return True, prev[1]
    record_service_status(
        "llm",
        settings,
        False,
        detail,
        transient=is_transient_api_error(detail),
    )
    return False, message


def test_vision_service(settings: UserSettings) -> tuple[bool, str] | None:
    """与设置页「测试视觉」相同；未启用或未配置时返回 None（跳过）。"""
    from friday.vision import test_vision_connection, vision_ready

    if not settings.vision_enabled or not vision_ready(settings):
        return None
    ok, message = test_vision_connection(settings)
    detail = message if ok else message.split("\n")[0]
    if ok:
        record_service_status("vision", settings, True, detail)
        return True, message
    if _should_preserve_service_ok_cache("vision", settings, detail):
        prev = _peek_service_ok_cache("vision", settings)
        if prev:
            return True, prev[1]
    record_service_status(
        "vision",
        settings,
        False,
        detail,
        transient=is_transient_api_error(detail),
    )
    return False, message


def test_image_gen_service(settings: UserSettings) -> tuple[bool, str] | None:
    """与设置页「测试生图」相同；未启用或未配置时返回 None（跳过）。"""
    from friday.image_gen import image_gen_ready, test_image_gen_connection

    if not settings.image_gen_enabled or not image_gen_ready(settings):
        return None
    ok, message = test_image_gen_connection(settings)
    detail = message if ok else message.split("\n")[0]
    if ok:
        record_service_status("image_gen", settings, True, detail)
        return True, message
    if _should_preserve_service_ok_cache("image_gen", settings, detail):
        prev = _peek_service_ok_cache("image_gen", settings)
        if prev:
            return True, prev[1]
    record_service_status("image_gen", settings, False, detail)
    return False, message


async def run_startup_service_tests(settings: UserSettings | None = None) -> dict[str, object]:
    """并行运行与设置页相同的 API 检测，供开机状态栏刷新。"""
    from friday.storage import load_settings

    cfg = settings or load_settings()

    async def _llm() -> tuple[bool, str] | None:
        if not cfg.api_ready:
            return None
        return await asyncio.to_thread(test_llm_service, cfg)

    async def _vision() -> tuple[bool, str] | None:
        return await asyncio.to_thread(test_vision_service, cfg)

    async def _image_gen() -> tuple[bool, str] | None:
        return await asyncio.to_thread(test_image_gen_service, cfg)

    llm_result, vision_result, image_gen_result = await asyncio.gather(_llm(), _vision(), _image_gen())

    def _pack(result: tuple[bool, str] | None) -> dict[str, object] | None:
        if result is None:
            return None
        ok, message = result
        return {"ok": ok, "message": message}

    return {
        "llm": _pack(llm_result),
        "vision": _pack(vision_result),
        "image_gen": _pack(image_gen_result),
    }



def probe_llm_status(
    settings: UserSettings,
    *,
    force: bool = False,
    read_timeout: float | None = None,
) -> tuple[bool, str]:
    if not settings.api_ready:
        return False, "未配置 API Key"
    cache_key = _auth_status_key("llm", settings)
    if not force:
        cached = _read_auth_status(cache_key, service="llm")
        if cached is not None:
            return cached

    base_url = (settings.base_url or UserSettings.base_url).strip()
    host_ok, host_detail = quick_reachability(base_url, settings)
    if not host_ok:
        prev = _peek_service_ok_cache("llm", settings)
        if prev and _should_preserve_service_ok_cache("llm", settings, host_detail):
            return prev
        record_service_status("llm", settings, False, host_detail)
        return False, host_detail

    step = _probe_chat_api(
        base_url=base_url,
        api_key=settings.api_key,
        model=settings.model,
        settings=settings,
        read_timeout=read_timeout,
    )
    detail = step.detail if step.ok else (f"{step.detail} {step.hint}".strip())
    if step.ok:
        record_service_status("llm", settings, True, detail)
        return True, detail
    prev = _peek_service_ok_cache("llm", settings)
    if prev and _should_preserve_service_ok_cache("llm", settings, detail):
        return prev
    record_service_status("llm", settings, False, detail)
    return False, detail


def probe_vision_status(settings: UserSettings, *, force: bool = False) -> tuple[bool, str]:
    from friday.vision import vision_ready

    if not settings.vision_enabled:
        return False, "未启用"
    if not vision_ready(settings):
        return False, "未配置视觉 API Key"
    if not settings.vision_model.strip():
        return False, "未配置 ep- 端点"

    cache_key = _auth_status_key("vision", settings)
    if not force:
        cached = _read_auth_status(cache_key, service="vision")
        if cached is not None:
            return cached

    base_url = (settings.vision_base_url or UserSettings.vision_base_url).strip()
    host_ok, host_detail = quick_reachability(base_url, settings)
    if not host_ok:
        prev = _peek_service_ok_cache("vision", settings)
        if prev and _should_preserve_service_ok_cache("vision", settings, host_detail):
            return prev
        record_service_status("vision", settings, False, host_detail)
        return False, host_detail

    steps = diagnose_vision(settings, include_api=True)
    failed = next((s for s in reversed(steps) if not s.ok), None)
    if failed is not None:
        detail = failed.detail if failed.hint is None else f"{failed.detail} {failed.hint}".strip()
        prev = _peek_service_ok_cache("vision", settings)
        if prev and _should_preserve_service_ok_cache("vision", settings, detail):
            return prev
        record_service_status("vision", settings, False, detail)
        return False, detail
    ok_step = steps[-1] if steps else None
    detail = ok_step.detail if ok_step else "视觉 API 可用"
    record_service_status("vision", settings, True, detail)
    return True, detail


def _image_gen_probe_inconclusive(message: str) -> bool:
    text = (message or "").strip().lower()
    return any(
        token in text
        for token in (
            "超时",
            "timeout",
            "timed out",
            "响应较慢",
            "响应过慢",
            "probe timed out",
            "inconclusive",
            "无法连接",
            "connection",
            "network",
            "所有端点均无法",
            "所有生图地址均不可用",
            "测试未通过",
        )
    )


def _probe_image_gen_api(
    *,
    api_key: str,
    model: str,
    settings: UserSettings,
    quick: bool = False,
) -> ConnectivityStep:
    from friday.config import STATUS_BAR_IMAGE_GEN_PROBE_TIMEOUT
    from friday.image_gen import _is_ark_image_gen_endpoint, verify_image_gen_api

    if not api_key.strip():
        return ConnectivityStep(
            "生图 API",
            False,
            "API Key 为空",
            "在设置中填写并保存生图 API Key",
        )
    if not model.strip():
        return ConnectivityStep(
            "生图 API",
            False,
            "模型未配置",
            "填写生图模型名称",
        )
    probe_timeout = STATUS_BAR_IMAGE_GEN_PROBE_TIMEOUT if quick else None
    if quick and _is_ark_image_gen_endpoint(settings):
        probe_timeout = max(float(probe_timeout or 0), 20.0)
    ok, message = verify_image_gen_api(
        settings,
        timeout=probe_timeout,
        primary_only=quick,
    )
    if ok:
        return ConnectivityStep("生图 API", True, message[:240])
    return ConnectivityStep(
        "生图 API",
        False,
        message[:200],
        "确认 Key、模型与 Provider 是否匹配",
    )


def probe_image_gen_status(settings: UserSettings, *, force: bool = False, quick: bool = True) -> tuple[bool, str]:
    from friday.image_gen import default_base_url, image_gen_ready

    if not settings.image_gen_enabled:
        return False, "未启用"
    if not image_gen_ready(settings):
        return False, "未配置生图 Key 或模型"

    cache_key = _auth_status_key("image_gen", settings)
    if not force:
        cached = _read_auth_status(cache_key, service="image_gen")
        if cached is not None:
            return cached

    prev_ok = _peek_service_ok_cache("image_gen", settings) if quick else None

    base_url = default_base_url(settings)
    host_ok, host_detail = quick_reachability(base_url, settings)
    if not host_ok:
        if quick and prev_ok:
            return prev_ok
        if quick and _image_gen_probe_inconclusive(host_detail):
            return False, host_detail
        record_service_status("image_gen", settings, False, host_detail)
        return False, host_detail

    step = _probe_image_gen_api(
        api_key=settings.image_gen_api_key,
        model=settings.image_gen_model,
        settings=settings,
        quick=quick,
    )
    detail = step.detail if step.ok else (f"{step.detail} {step.hint}".strip())

    if step.ok:
        record_service_status("image_gen", settings, True, detail)
        return True, detail

    if quick and prev_ok:
        return prev_ok

    if _image_gen_probe_inconclusive(step.detail):
        return False, detail

    record_service_status("image_gen", settings, False, detail)
    return False, detail


def format_api_error(
    exc: Any,
    *,
    context: str = "api_test",
    service: str = "API",
) -> str:
    from friday.error_hints import format_error_hint, format_user_message

    hint = format_error_hint(exc, context=context, service=service)
    return format_user_message(hint)


def urlopen_request(req: urllib.request.Request, *, timeout: float = 30.0):
    """带 certifi 的 urllib 请求（下载等场景）。"""
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
