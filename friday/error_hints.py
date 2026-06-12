"""已知异常 → 用户可见文案与修复指引（P3-1）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorHint:
    code: str
    detail: str
    hint: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "hint": self.hint}


_USER_FACING_MARKERS = (
    "请先",
    "请填写",
    "未启用",
    "未配置",
    "已就绪",
    "生图",
    "视觉",
    "API Key",
    "推理接入点",
    "测试通过",
    "超时",
    "无法",
    "请检查",
    "请确认",
    "连接测试",
    "端点",
    "模型",
)


def _looks_like_hint(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    return text.startswith(("请", "在 ", "打开 ", "可", "若", "检查", "确认", "从 ", "已尝试"))


def _is_user_facing(text: str) -> bool:
    raw = text.strip()
    if not raw:
        return False
    if raw.startswith(("Error code:", "Traceback", "HTTPError", "httpx.", "urllib.")):
        return False
    if any(m in raw for m in _USER_FACING_MARKERS):
        return True
    return bool(re.search(r"[\u4e00-\u9fff]", raw[:48]))


def _is_balance_error(text: str, lower: str) -> bool:
    return any(
        token in lower
        for token in (
            "insufficient_balance",
            "insufficient balance",
            "insufficient account balance",
            "accountoverdue",
            "余额不足",
            "余额不够",
            "欠费",
        )
    )


def _remote_api_auth_failure(text: str, lower: str) -> bool:
    if _is_balance_error(text, lower):
        return False
    if text == "401":
        return True
    if any(k in lower for k in ("401", "403")):
        return any(
            k in lower
            for k in ("api", "key", "error code", "http", "openai", "invalid", "authentication")
        )
    return any(
        k in lower
        for k in (
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "invalid_api_key",
            "authentication",
        )
    )


def _infer_context_from_text(text: str) -> str:
    head = text[:32]
    if "生图" in head:
        return "image_gen"
    if "视觉" in head:
        return "vision"
    return ""


def resolve_error_context(*, service: str = "", context: str = "") -> str:
    svc = (service or "").strip()
    if "生图" in svc:
        return "image_gen"
    if "视觉" in svc:
        return "vision"
    ctx = (context or "").strip().lower()
    if ctx in {"image_gen", "vision", "llm", "auth_401", "local_auth"}:
        return ctx
    if svc and svc not in {"API"}:
        return "llm"
    return ctx or "api_test"


def _image_gen_auth_hint() -> ErrorHint:
    return ErrorHint(
        "image_gen_auth",
        "生图 API Key 无效",
        "请在 设置 → 生图 检查 Key、Base URL 与模型是否与当前服务商匹配",
    )


def _vision_auth_hint() -> ErrorHint:
    return ErrorHint(
        "vision_auth",
        "视觉 API Key 无效",
        "请在 设置 → 视觉 检查 Key、Base URL 与 ep- 推理接入点是否正确",
    )


def _llm_auth_hint(text: str, lower: str) -> ErrorHint:
    hint = "请在 设置 → 大模型 检查当前服务商与 Key 是否匹配（MiMo / DeepSeek 等需分别配置）"
    if "xiaomimimo.com/v1" in lower and "token-plan" not in lower:
        hint += "；MiMo 订阅套餐 Key（tp- 开头）需用 Base URL https://token-plan-cn.xiaomimimo.com/v1"
    elif "token-plan-cn.xiaomimimo.com" in lower:
        hint += "；Token Plan 请用 tp- 开头 Key，按量付费请用 sk- Key 与 https://api.xiaomimimo.com/v1"
    detail = "大模型 API Key 无效" if "llm" in lower or "大模型" in text else "API Key 无效或已失效"
    return ErrorHint("api_auth", detail, hint)


def classify_error(raw: Any = "", *, context: str = "") -> ErrorHint:
    """将异常或日志片段映射为面向用户的 detail + hint。"""
    text = str(raw or "").strip()
    lower = text.lower()
    ctx = (context or "").strip().lower()
    text_ctx = _infer_context_from_text(text)
    if text_ctx:
        ctx = text_ctx

    if ctx in {"backend_starting", "health_starting"}:
        return ErrorHint(
            "backend_starting",
            "后端仍在启动，请稍候",
            "就绪后再测试 API 连接",
        )

    if ctx in {"health_timeout", "startup_timeout"} or "启动超时" in text:
        return ErrorHint(
            "health_timeout",
            "后端仍在启动，请稍候",
            "若长时间无响应，请重启应用；仍失败请打开 AppData 下的 friday.log",
        )

    if ctx in {"auth_401", "local_auth"}:
        return ErrorHint(
            "auth_401",
            "本地认证已过期",
            "已尝试自动恢复；若仍失败，请完全退出星期五后重新打开",
        )

    if _is_balance_error(text, lower):
        detail = "生图账户余额不足" if ctx == "image_gen" or "生图" in text else "API 账户余额不足"
        return ErrorHint(
            "api_balance",
            detail,
            "请在中转站控制台充值，或更换有余额的 API Key；主地址与备用地址可能余额不同",
        )

    if _remote_api_auth_failure(text, lower):
        if ctx == "image_gen" or "生图" in text:
            return _image_gen_auth_hint()
        if ctx == "vision" or "视觉" in text:
            return _vision_auth_hint()
        if ctx in {"llm", "api_test", "api"}:
            return _llm_auth_hint(text, lower)

    if "python.runtime" in lower or "pythonnet" in lower:
        return ErrorHint(
            "runtime_lib",
            "运行库异常，请安装 VC++ 运行库或重新安装星期五",
            "可安装 Microsoft Visual C++ 2015–2022 运行库；若安装路径含中文，请改到英文目录后重装",
        )

    if "multipart" in lower or "python-multipart" in lower:
        return ErrorHint(
            "missing_multipart",
            "安装包组件缺失，请下载最新版覆盖安装",
            "从 Gitee Releases 下载最新 Friday-Windows.zip 覆盖安装",
        )

    if (
        "jsondecodeerror" in lower
        or ("settings" in lower and "json" in lower)
        or "配置文件损坏" in text
        or ctx == "settings_json"
    ):
        return ErrorHint(
            "settings_corrupt",
            "配置文件损坏，已尝试从 .bak 恢复",
            "打开 %APPDATA%\\Friday，检查 settings.json 与 settings.json.bak",
        )

    if ctx == "api_key_missing" or text == "请先填写 API Key":
        return ErrorHint(
            "api_key_missing",
            "请先在设置中填写大模型 API Key",
            "打开 设置 → 大模型，选择服务商并保存 Key",
        )

    if "推理接入点" in text or ("ep-" in lower and "不存在" in text):
        return ErrorHint(
            "image_gen_endpoint",
            text.split("\n")[0][:240],
            "请在火山方舟控制台确认 ep ID 是否正确、是否已开通图像生成能力",
        )

    if "http 404" in lower or ("404" in text and "接口" in text):
        detail = "接口地址或模型不存在"
        hint = "请检查 Base URL 是否为服务商文档中的 /api/v3；火山方舟需填写 ep- 推理接入点而非裸模型名"
        if ctx == "vision" or "视觉" in text:
            hint = "请检查视觉 Base URL 与 ep- 接入点 ID 是否在火山引擎控制台已创建并授权"
        elif ctx == "image_gen" or "生图" in text:
            hint = "请检查生图 Base URL 与模型/接入点 ID 是否与服务商文档一致"
        return ErrorHint("api_not_found", detail, hint)

    if "尺寸过小" in text or "3686400" in text.replace(",", ""):
        return ErrorHint(
            "image_gen_size",
            text.split("\n")[0][:240],
            "该模型最低约 1920×1920（368 万像素）；对话生图会自动提升尺寸，测试也会自动重试",
        )

    if "http 400" in lower or ("请求被拒绝" in text) or ("参数无效" in text):
        detail = text.split("\n")[0][:240] or "API 请求被拒绝"
        hint = "请核对模型名、Key 与服务商是否一致；中转站需使用其文档中的 model ID"
        if ctx == "vision" or "视觉" in text:
            hint = "请核对视觉 ep- 接入点 ID 与 Key 是否匹配，并确认已开通视觉理解能力"
        elif ctx == "image_gen" or "生图" in text:
            hint = "请核对生图 model ID、Key 与 Base URL 是否与服务商一致"
        return ErrorHint("api_bad_request", detail, hint)

    if any(
        k in lower
        for k in (
            "readtimeout",
            "read timeout",
            "read timed out",
            "response timed out",
            "waiting for response",
            "apitimeouterror",
        )
    ):
        detail = "API 响应超时"
        hint = "服务器可能繁忙或网络较慢，请稍后重试；若仅偶发可忽略，反复出现请点「网络诊断」"
        if ctx == "image_gen" or "生图" in text:
            detail = "生图 API 响应超时"
            hint = "生图端点可能较慢，请检查 Base URL 与模型名；可在设置页重试或换备用 URL"
        return ErrorHint("api_timeout", detail, hint)

    if "429" in text or "too many requests" in lower or "rate limit" in lower:
        return ErrorHint(
            "api_rate_limit",
            "API 请求过于频繁（429 Too Many Requests）",
            "请稍等 1–2 分钟后重试；若持续出现，请检查当前服务商的配额/并发限制，或降低对话频率",
        )

    if any(k in lower for k in ("connection", "timeout", "timed out", "network", "connect", "refused", "unreachable")):
        if "proxy" in lower or "407" in lower:
            return ErrorHint(
                "api_proxy",
                "无法通过代理连接 API",
                "在 设置 → API 连接 → 网络代理 填写公司代理地址（如 http://127.0.0.1:7890），或取消系统代理后重试",
            )
        if any(k in lower for k in ("ssl", "certificate", "cert verify", "tls")):
            return ErrorHint(
                "api_ssl",
                "SSL 证书验证失败",
                "检查系统时间是否正确；企业网络需导入代理根证书，或配置正确的 HTTPS 代理",
            )
        if "getaddrinfo" in lower or "name or service not known" in lower or "nodename nor servname" in lower:
            return ErrorHint(
                "api_dns",
                "无法解析 API 服务器地址",
                "检查 DNS 与网络；若 Base URL 填错请改回官方地址；公司网络可能需要代理",
            )
        if ctx in {"api_test", "llm", "vision", "image_gen", "api"} or any(
            k in lower for k in ("deepseek", "openai", "ark", "api")
        ):
            detail = "无法连接 API 服务器"
            hint = "请检查网络与防火墙；公司/校园网请在设置中配置 HTTP 代理，并点击「网络诊断」查看详情"
            if ctx == "vision" or "视觉" in text:
                detail = "无法连接视觉 API 服务器"
            elif ctx == "image_gen" or "生图" in text:
                detail = "无法连接生图 API 服务器"
            return ErrorHint("api_network", detail, hint)

    if text:
        return ErrorHint(
            "unknown",
            text[:240],
            "可打开 设置 → 数据与日志 → 打开日志文件夹 查看详情",
        )

    return ErrorHint(
        "unknown",
        "操作失败",
        "可打开 设置 → 数据与日志 → 打开日志文件夹 查看详情",
    )


def format_error_hint(raw: Any, *, context: str = "", service: str = "") -> ErrorHint:
    text = str(raw or "").strip()
    if not text and raw is not None:
        text = type(raw).__name__
    ctx = resolve_error_context(service=service, context=context)
    hint = classify_error(text, context=ctx)
    if hint.code == "unknown" and service:
        hint = classify_error(f"{service}: {text}", context=ctx)
    return hint


def format_user_message(hint: ErrorHint, *, include_detail: bool = True) -> str:
    """合并 detail 与 hint 为单行/多行展示文案。"""
    if include_detail and hint.hint:
        return f"{hint.detail}\n{hint.hint}"
    return hint.detail or hint.hint


def build_test_response(
    ok: bool,
    message: str,
    *,
    service: str = "",
    context: str = "api_test",
) -> dict[str, str | bool]:
    """设置页 API 测试统一响应：detail + hint + code。"""
    if ok:
        return {"ok": True, "message": message, "code": "ok", "hint": ""}

    text = str(message or "").strip()
    if text.startswith("所有生图地址均不可用"):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        hint_line = lines[-1] if lines and _looks_like_hint(lines[-1]) else ""
        body = "\n".join(lines[:-1] if hint_line else lines)
        return {
            "ok": False,
            "message": body,
            "hint": hint_line,
            "code": "image_gen_endpoints",
        }

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 2 and _looks_like_hint(lines[-1]):
        head = lines[0]
        tail = lines[-1]
        hint = format_error_hint(head, context=context, service=service)
        return {
            "ok": False,
            "message": head,
            "hint": tail,
            "code": hint.code if hint.code != "unknown" else classify_error(head, context=resolve_error_context(service=service, context=context)).code,
        }

    hint = format_error_hint(text, context=context, service=service)
    if hint.code == "unknown" and _is_user_facing(text):
        return {
            "ok": False,
            "message": text.split("\n")[0][:240],
            "hint": hint.hint,
            "code": "unknown",
        }

    return {
        "ok": False,
        "message": hint.detail,
        "hint": hint.hint,
        "code": hint.code,
    }
