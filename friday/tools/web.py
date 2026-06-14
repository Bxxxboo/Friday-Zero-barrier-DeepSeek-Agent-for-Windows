"""联网工具 —— 浏览网页、发现下载链接、下载文件到本地。"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from friday.logging_config import get_logger
from friday.tools._decorators import register_tool
from friday.config import (
    DOWNLOAD_LARGE_MAX_BYTES,
    DOWNLOAD_LARGE_THRESHOLD_BYTES,
    DOWNLOAD_MAX_BYTES,
    WEB_PAGE_MAX_BYTES,
)
from friday.tools.web_limits import DownloadProbe, download_byte_limit, format_bytes
from friday.tools.web_security import normalize_url, validate_public_url
from friday.tools.web_trust import (
    TrustLevel,
    assess_download_trust,
    format_trust_report,
    pick_best_download_link,
)

_log = get_logger("web")

_USER_AGENT = "Friday-Desktop/1.0 (+https://github.com; Windows assistant)"
_CHUNK_SIZE = 256 * 1024
_PROBE_CACHE: dict[str, tuple[float, DownloadProbe]] = {}
_PROBE_TTL_SEC = 120.0
_DOWNLOAD_EXTENSIONS = (
    ".exe", ".msi", ".msix", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".iso", ".msu", ".cab",
)
_DOWNLOAD_HINTS = ("download", "release", "assets", "attachment", "installer")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = attrs_dict.get("href", "").strip()
            label = attrs_dict.get("title", "").strip()
            if href:
                self.links.append((href, label))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.text_parts.append(text)


def _request_headers() -> dict[str, str]:
    return {"User-Agent": _USER_AGENT, "Accept": "*/*"}


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        ok, err = validate_public_url(newurl)
        if not ok:
            raise urllib.error.HTTPError(newurl, code, f"重定向被拦截: {err}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_SafeRedirectHandler())


def _parse_content_length(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def probe_download(url: str, *, use_cache: bool = True) -> DownloadProbe:
    """探测远程文件大小（HEAD，失败则尝试 Range GET）。"""
    raw = (url or "").strip()
    if not raw:
        return DownloadProbe(url=raw, error="URL 不能为空")

    now = time.time()
    if use_cache and raw in _PROBE_CACHE:
        cached_at, cached = _PROBE_CACHE[raw]
        if now - cached_at < _PROBE_TTL_SEC:
            return cached

    ok, err = validate_public_url(raw)
    if not ok:
        probe = DownloadProbe(url=raw, error=err)
        _PROBE_CACHE[raw] = (now, probe)
        return probe

    request = urllib.request.Request(raw, headers={**_request_headers(), "Accept": "*/*"})
    opener = _build_opener()
    probe = DownloadProbe(url=raw)

    for method in ("HEAD", "GET"):
        try:
            req = request
            if method == "GET":
                req = urllib.request.Request(
                    raw,
                    headers={**_request_headers(), "Accept": "*/*", "Range": "bytes=0-0"},
                )
            with opener.open(req, timeout=12.0) as resp:
                probe.final_url = resp.geturl()
                probe.content_length = _parse_content_length(resp.headers.get("Content-Length"))
                if probe.content_length is None and method == "GET":
                    content_range = resp.headers.get("Content-Range", "")
                    match = re.search(r"/(\d+)\s*$", content_range)
                    if match:
                        probe.content_length = int(match.group(1))
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            probe.error = str(exc)
        except urllib.error.HTTPError as exc:
            if exc.code in {405, 501} and method == "HEAD":
                continue
            probe.error = f"HTTP {exc.code}"
            break

    _PROBE_CACHE[raw] = (now, probe)
    return probe


def _fetch_bytes(url: str, *, max_bytes: int, timeout: float) -> tuple[bytes, dict[str, Any]]:
    ok, err = validate_public_url(url)
    if not ok:
        raise ValueError(err)

    request = urllib.request.Request(url, headers=_request_headers())
    opener = _build_opener()
    with opener.open(request, timeout=timeout) as resp:
        info = {
            "final_url": resp.geturl(),
            "content_type": resp.headers.get("Content-Type", ""),
            "content_length": resp.headers.get("Content-Length", ""),
        }
        chunks: list[bytes] = []
        total = 0
        while True:
            block = resp.read(min(_CHUNK_SIZE, max_bytes - total + 1))
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise ValueError(f"响应过大（>{max_bytes // (1024 * 1024)} MB）")
            chunks.append(block)
        return b"".join(chunks), info


def _decode_html(data: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    for enc in (charset, "utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _looks_like_download(url: str, label: str = "") -> bool:
    lower = f"{url} {label}".lower()
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _DOWNLOAD_EXTENSIONS):
        return True
    return any(hint in lower for hint in _DOWNLOAD_HINTS)


def _extract_page(html: str, base_url: str) -> dict[str, Any]:
    parser = _PageParser()
    parser.feed(html)
    parser.close()

    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    if len(text) > 4000:
        text = text[:4000] + "…"

    seen: set[str] = set()
    download_links: list[dict[str, str]] = []
    other_links: list[dict[str, str]] = []

    for href, label in parser.links:
        absolute = normalize_url(base_url, href)
        if not absolute or absolute in seen:
            continue
        seen.add(absolute)
        ok, _ = validate_public_url(absolute)
        if not ok:
            continue
        item = {"url": absolute, "label": label or absolute}
        if _looks_like_download(absolute, label):
            download_links.append(item)
        elif len(other_links) < 40:
            other_links.append(item)

    return {
        "title": parser.title.strip() or "(无标题)",
        "text": text or "(页面无可读正文)",
        "download_links": download_links[:30],
        "other_links": other_links[:20],
    }


def _format_link_lines(links: list[dict[str, object]], *, header: str) -> list[str]:
    if not links:
        return []
    lines = [header]
    for item in links:
        label = item.get("label") or item.get("url")
        trust = item.get("trust_label", "")
        tag = f"[{trust}] " if trust else ""
        extra = f" ({label})" if label != item.get("url") else ""
        reasons = item.get("trust_reasons") or []
        hint = f" — {reasons[0]}" if reasons else ""
        rec = " ★推荐" if item.get("recommended") else ""
        lines.append(f"- {tag}{item.get('url')}{extra}{rec}{hint}")
    return lines


@register_tool(
    name="verify_download_source",
    description=(
        "验证软件下载链接是否来自官方或可信发布商。"
        "检查 HTTPS/TLS 证书、域名是否与软件官方渠道匹配，并识别可疑第三方下载站。"
        "下载前应优先调用此工具确认来源安全。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "待验证的下载链接"},
            "expected_software": {
                "type": "string",
                "description": "可选。软件名称，如 chrome、微信、vscode，用于核对是否官方域名",
            },
        },
        "required": ["url"],
    },
)
def verify_download_source(url: str, expected_software: str = "") -> str:
    ok, err = validate_public_url(url)
    if not ok:
        return f"无法验证: {err}"
    report = assess_download_trust(url, expected_software=expected_software.strip())
    return format_trust_report(report)


def _filename_from_response(url: str, headers: dict[str, Any]) -> str:
    disposition = str(headers.get("content-disposition") or headers.get("Content-Disposition") or "")
    match = re.search(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?", disposition, re.I)
    if match:
        name = match.group(1) or match.group(2) or ""
        name = unquote(name.strip())
        if name:
            return Path(name).name

    path_name = Path(unquote(urlparse(url).path)).name
    if path_name and "." in path_name:
        return path_name
    return "download.bin"


@register_tool(
    name="browse_webpage",
    description=(
        "浏览指定网页，返回页面标题、正文摘要，以及页面上的下载链接和其他链接。"
        "用于帮用户查找软件官方下载地址、资源页等。仅读取公开网页，不能登录或绕过验证。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要浏览的网页地址（http/https）",
            },
            "expected_software": {
                "type": "string",
                "description": "可选。软件名称，用于对页面内下载链接做官方来源排序",
            },
        },
        "required": ["url"],
    },
)
def browse_webpage(url: str, expected_software: str = "") -> str:
    _log.info("浏览网页 | url=%s software=%s", url[:200], expected_software)
    try:
        data, info = _fetch_bytes(url, max_bytes=WEB_PAGE_MAX_BYTES, timeout=20.0)
    except ValueError as exc:
        return f"无法访问: {exc}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"网络请求失败: {exc}"

    final_url = str(info.get("final_url") or url)
    page_report = assess_download_trust(final_url, expected_software=expected_software.strip())

    html = _decode_html(data, str(info.get("content_type", "")))
    parsed = _extract_page(html, final_url)

    ranked = pick_best_download_link(
        parsed["download_links"],
        expected_software=expected_software.strip(),
    )
    recommended = [item for item in ranked if item.get("recommended")]
    others = [item for item in ranked if not item.get("recommended")]

    lines = [
        f"标题: {parsed['title']}",
        f"地址: {final_url}",
        f"页面来源: {page_report.label} — {'; '.join(page_report.reasons[:2]) or '已检查'}",
        "",
        "正文摘要:",
        parsed["text"],
        "",
    ]
    if recommended:
        lines.extend(_format_link_lines(recommended, header="推荐下载链接（官方/可信）:"))
    elif ranked:
        lines.extend(_format_link_lines(ranked[:10], header="下载链接（按可信度排序，请优先选高评级）:"))
    else:
        lines.append("未发现明显的下载链接，可查看下方其他链接或让用户指定下载地址。")

    if others and recommended:
        lines.append("")
        lines.extend(_format_link_lines(others[:8], header="其他下载链接（可信度较低，慎用）:"))

    if parsed["other_links"]:
        lines.append("")
        lines.append("其他链接:")
        for item in parsed["other_links"][:12]:
            lines.append(f"- {item['url']}")

    lines.append("")
    lines.append("提示: 下载前请用 verify_download_source 再次确认链接；优先选择「官方来源」或「可信发布商」。")
    return "\n".join(lines)


@register_tool(
    name="download_file",
    description=(
        "从 http/https 链接下载文件到本地指定路径或目录。"
        "适用于下载安装包（exe/msi/zip 等）到用户指定的文件夹。"
        "destination 可以是完整文件路径，也可以是目录（将自动推断文件名）。"
        "超过 1 GB 的文件会自动触发大文件下载确认；若大小未知但用户已明确同意下载大文件，"
        "可设置 confirm_large_download=true。"
        "下载前应用 verify_download_source 验证；请填写 expected_software 以提高官方链接识别准确率。"
        "非官方来源需用户确认并设置 confirm_untrusted_source=true。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "文件下载地址",
            },
            "destination": {
                "type": "string",
                "description": "保存路径：完整文件路径，或目标目录",
            },
            "filename": {
                "type": "string",
                "description": "可选。当 destination 为目录时指定文件名",
            },
            "expected_software": {
                "type": "string",
                "description": "可选。软件名称（如 chrome、微信），用于验证是否官方下载源",
            },
            "confirm_large_download": {
                "type": "boolean",
                "description": "可选。仅当用户已明确同意下载超过 1 GB 的大文件，且服务器未返回大小时设为 true",
            },
            "confirm_untrusted_source": {
                "type": "boolean",
                "description": "可选。仅当 verify_download_source 显示非官方来源且用户仍同意下载时设为 true",
            },
        },
        "required": ["url", "destination"],
    },
)
def download_file(
    url: str,
    destination: str,
    filename: str = "",
    expected_software: str = "",
    confirm_large_download: bool = False,
    confirm_untrusted_source: bool = False,
    *,
    _allow_large: bool = False,
) -> str:
    allow_large = _allow_large or confirm_large_download
    max_bytes = download_byte_limit(allow_large=allow_large)
    dest = Path(destination).expanduser()

    ok, err = validate_public_url(url)
    if not ok:
        return f"无法下载: {err}"

    trust = assess_download_trust(url, expected_software=expected_software.strip())
    if trust.is_blocked:
        return (
            f"下载已拒绝：来源不安全（{trust.label}）。"
            f"{' '.join(trust.reasons[:2])}。"
            f"请改用官方站点或通过 browse_webpage 查找官方链接。"
        )
    if trust.needs_untrusted_confirm and not confirm_untrusted_source:
        return (
            f"下载已暂停：来源未通过安全验证（{trust.label}）。"
            f"{' '.join(trust.reasons[:2])}。"
            f"请先向用户说明风险；若用户仍同意，使用 verify_download_source 确认后"
            f"设置 confirm_untrusted_source=true 再下载。"
        )

    _log.info(
        "下载文件 | url=%s dest=%s trust=%s allow_large=%s",
        url[:200], dest, trust.label, allow_large,
    )

    request = urllib.request.Request(url, headers=_request_headers())
    opener = _build_opener()

    try:
        with opener.open(request, timeout=60.0) as resp:
            final_url = resp.geturl()
            headers = dict(resp.headers.items())
            content_length = _parse_content_length(headers.get("Content-Length"))
            if content_length is not None and content_length > max_bytes:
                return (
                    f"文件过大（{format_bytes(content_length)}），"
                    f"超过当前允许上限 {format_bytes(max_bytes)}"
                )

            if (
                content_length is not None
                and content_length > DOWNLOAD_LARGE_THRESHOLD_BYTES
                and not allow_large
            ):
                return (
                    f"该文件约 {format_bytes(content_length)}，超过常规下载上限 "
                    f"{format_bytes(DOWNLOAD_LARGE_THRESHOLD_BYTES)}。"
                    f"请向用户说明大小并确认后，再次发起大文件下载。"
                )

            if dest.suffix:
                target = dest
            else:
                name = filename.strip() or _filename_from_response(final_url, headers)
                target = dest / name

            target.parent.mkdir(parents=True, exist_ok=True)

            total = 0
            with open(target, "wb") as fh:
                while True:
                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if not allow_large and total > DOWNLOAD_LARGE_THRESHOLD_BYTES:
                        fh.close()
                        target.unlink(missing_ok=True)
                        return (
                            f"下载已中止：已接收 {format_bytes(total)}，超过常规上限 "
                            f"{format_bytes(DOWNLOAD_LARGE_THRESHOLD_BYTES)}。"
                            f"如需继续，请确认大文件下载后重试。"
                        )
                    if total > max_bytes:
                        fh.close()
                        target.unlink(missing_ok=True)
                        return f"下载中止：文件超过 {format_bytes(max_bytes)} 限制"
                    fh.write(chunk)
    except ValueError as exc:
        return f"无法下载: {exc}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"下载失败: {exc}"

    size_mb = total / (1024 * 1024)
    trust_note = f"来源认证: {trust.label}"
    if trust.tls_valid and trust.tls_issuer:
        trust_note += f"（TLS: {trust.tls_issuer}）"
    return (
        f"下载完成\n"
        f"来源: {final_url}\n"
        f"{trust_note}\n"
        f"保存至: {target.resolve()}\n"
        f"大小: {size_mb:.2f} MB ({total} 字节)"
    )


def _download_software_failure(category: str, detail: str) -> str:
    _log.info("download_software 失败 | category=%s detail=%s", category, detail[:160])
    return f"【下载失败·{category}】{detail}"


# 常见软件官网下载页（用于 download_software 一键下载）
_SOFTWARE_PAGES: dict[str, str] = {
    "netease_music": "https://music.163.com/#/download",
    "kugou": "https://www.kugou.com/download/",
    "kugou_music": "https://www.kugou.com/download/",
    "chrome": "https://www.google.com/chrome/",
    "firefox": "https://www.mozilla.org/firefox/new/",
    "wechat": "https://weixin.qq.com/",
    "vscode": "https://code.visualstudio.com/Download",
    "7zip": "https://www.7-zip.org/download.html",
}


@register_tool(
    name="download_software",
    description=(
        "一键下载软件安装包到指定路径（推荐）。"
        "内部会自动浏览官网、挑选可信下载链接并下载，无需 PowerShell。"
        "software_name 填中文或英文（如 网易云音乐、netease_music、chrome）。"
        "destination 为完整文件路径或目录（如 E:/NeteaseSetup.exe 或 E:/）。"
        "用户要求下载软件时优先使用本工具，不要用 run_powershell。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "software_name": {
                "type": "string",
                "description": "软件名称，如 网易云音乐、chrome、微信",
            },
            "destination": {
                "type": "string",
                "description": "保存路径（文件或目录）",
            },
            "open_after": {
                "type": "boolean",
                "description": "下载完成后是否打开安装包，默认 false",
            },
        },
        "required": ["software_name", "destination"],
    },
)
def download_software(
    software_name: str,
    destination: str,
    open_after: bool = False,
) -> str:
    from friday.tools.web_trust import resolve_software_key

    name = (software_name or "").strip()
    dest = (destination or "").strip()
    if not name or not dest:
        return _download_software_failure("参数缺失", "请提供 software_name 和 destination。")

    key = resolve_software_key(name) or name.lower().replace(" ", "_")
    page_url = _SOFTWARE_PAGES.get(key, "")

    if not page_url:
        return _download_software_failure(
            "未收录",
            f"暂无「{software_name}」的预设下载页。请用 browse_webpage 打开官网，"
            f"找到下载链接后用 download_file 下载；不要用 PowerShell。",
        )

    _log.info("一键下载软件 | name=%s key=%s page=%s dest=%s", name, key, page_url, dest)

    try:
        data, info = _fetch_bytes(page_url, max_bytes=WEB_PAGE_MAX_BYTES, timeout=25.0)
    except ValueError as exc:
        return _download_software_failure("页面访问", f"无法访问官网: {exc}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _download_software_failure("网络", f"网络请求失败: {exc}")

    final_url = str(info.get("final_url") or page_url)
    html = _decode_html(data, str(info.get("content_type", "")))
    parsed = _extract_page(html, final_url)
    ranked = pick_best_download_link(parsed["download_links"], expected_software=key)

    if not ranked:
        return _download_software_failure(
            "未找到链接",
            f"在 {final_url} 未找到下载链接。"
            f"请用 browse_webpage 查看页面后手动指定 download_file。",
        )

    url = str(ranked[0].get("url", "")).strip()
    if not url:
        return _download_software_failure("解析失败", "未能解析下载地址。")

    verify_text = verify_download_source(url, expected_software=key)
    dl_result = download_file(
        url,
        dest,
        expected_software=key,
        _allow_large=True,
    )
    if not dl_result.startswith("下载完成"):
        return _download_software_failure("文件下载", f"{verify_text}\n\n{dl_result}".strip())
    if open_after:
        from friday.tools.system import open_app

        path_line = [ln for ln in dl_result.splitlines() if ln.startswith("保存至:")]
        if path_line:
            installer = path_line[0].split(":", 1)[1].strip()
            open_note = open_app(installer)
            return f"{verify_text}\n\n{dl_result}\n\n{open_note}"

    return f"{verify_text}\n\n{dl_result}"
