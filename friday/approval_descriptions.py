"""审批说明文案 — 从 safety 拆出，供 UI / 微信审批复用。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

GENERIC_APPROVAL_PLAIN = "在这台电脑上执行一项需要你确认的操作"

_TOOL_NAME_LABELS: dict[str, str] = {
    "run_powershell": "运行 PowerShell 命令",
    "run_python": "运行 Python 脚本",
    "run_python_script": "运行 Python 脚本文件",
    "write_text_file": "写入或覆盖文件",
    "delete_file": "删除文件",
    "delete_directory": "删除文件夹",
    "move_file": "移动文件或文件夹",
    "copy_file": "复制文件或文件夹",
    "organize_directory": "整理文件夹",
    "batch_rename": "批量重命名",
    "download_file": "从互联网下载文件",
    "download_software": "下载软件",
    "generate_image": "生成图片",
    "browse_webpage": "浏览网页",
    "open_url": "打开网页",
    "open_app": "启动程序",
    "clipboard_write": "写入剪贴板",
    "create_docx": "创建 Word 文档",
    "create_pptx": "创建 PPT",
    "zip_files": "打包压缩文件",
    "unzip_file": "解压文件",
    "install_friday_plugin": "安装扩展插件",
    "uninstall_friday_plugin": "卸载扩展插件",
}


def humanize_tool_name(tool_name: str) -> str:
    return _TOOL_NAME_LABELS.get(tool_name, tool_name.replace("_", " "))


def format_bytes(num: int) -> str:
    if num >= 1024 ** 3:
        return f"{num / (1024 ** 3):.2f} GB"
    if num >= 1024 ** 2:
        return f"{num / (1024 ** 2):.1f} MB"
    if num >= 1024:
        return f"{num / 1024:.1f} KB"
    return f"{num} B"


_KNOWN_FOLDER_LABELS: tuple[tuple[str, str], ...] = (
    ("/desktop", "桌面"),
    ("/downloads", "下载文件夹"),
    ("/documents", "文档"),
    ("/pictures", "图片"),
    ("/videos", "视频"),
    ("/music", "音乐"),
)


def _is_plausible_shell_path(val: str) -> bool:
    """过滤 PowerShell 格式化字符串，只保留像真实路径的引号内容。"""
    text = (val or "").strip()
    if not text or len(text) > 260:
        return False
    if any(token in text for token in ("$", "@{", "|", "{0:", "{1:", "-f ", " -f ")):
        return False
    if re.search(r"\$\(|\.LastWriteTime|Format-Table|Select-Object", text, re.I):
        return False
    if re.search(r"\{[^}]*:?\.?\d*f\}|:\.2f\}|1024\s*\*\*|/\s*1024", text, re.I):
        return False
    if re.match(r"^[A-Za-z]:\\", text):
        return True
    if text.startswith(("~/", "/")):
        return True
    if "\\" in text or "/" in text:
        if re.search(r"[\d)]\s*/\s*1\s*kb", text, re.I):
            return False
        return True
    return False


def _friendly_location(path: str) -> str:
    """把路径翻译成用户能看懂的文件夹名称。"""
    raw = (path or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    lower = normalized.lower()
    for suffix, label in _KNOWN_FOLDER_LABELS:
        if lower.endswith(suffix) or f"{suffix}/" in lower or lower == suffix.strip("/"):
            return label
    for segment, label in (
        ("desktop", "桌面"),
        ("downloads", "下载文件夹"),
        ("documents", "文档"),
        ("pictures", "图片"),
        ("videos", "视频"),
        ("music", "音乐"),
    ):
        if f"/{segment}" in lower or lower.endswith(segment):
            return label
    name = Path(raw).name
    if any(token in name for token in ("$", "|", "(", ")", "KB", "LastWriteTime", ".2f}")):
        return ""
    if name.lower() in {"desktop", "downloads", "documents", "pictures", "videos", "music"}:
        mapping = {
            "desktop": "桌面",
            "downloads": "下载文件夹",
            "documents": "文档",
            "pictures": "图片",
            "videos": "视频",
            "music": "音乐",
        }
        return mapping.get(name.lower(), name)
    if name:
        return f"「{name}」"
    return raw


def _extract_quoted_paths(text: str) -> list[str]:
    paths: list[str] = []
    for match in re.finditer(r"""['"]([^'"]+)['"]""", text or ""):
        val = match.group(1).strip()
        if not val:
            continue
        if val.startswith(("http://", "https://")):
            continue
        if _is_plausible_shell_path(val):
            paths.append(val)
    return paths


def _extract_http_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"""https?://[^\s'"]+""", text or ""):
        val = match.group(0).strip().rstrip(".,;)\"'")
        if val and val not in urls:
            urls.append(val)
    return urls


def _describe_url_purpose(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    tail = raw.rstrip("/").rsplit("/", 1)[-1].upper()
    if "er-api.com" in lower or "exchangerate" in lower or "/latest/" in lower:
        if len(tail) <= 4 and tail.isalpha():
            return f"查询 {tail} 的公开汇率"
        return "查询公开汇率数据"
    if any(token in lower for token in ("weather", "forecast")):
        return "查询天气信息"
    if any(token in lower for token in ("api.", "/v1/", "/v2/")):
        host = urlparse(raw).netloc or raw
        return f"从 {host} 获取公开数据"
    host = urlparse(raw).netloc
    return f"访问 {host}" if host else ""


def _describe_python_impact(code: str) -> str:
    lower = (code or "").lower()
    lines: list[str] = []
    has_network = any(token in lower for token in ("requests.", "urllib", "httpx.", "aiohttp"))
    writes_local = any(
        token in lower
        for token in (
            "open(",
            ".write(",
            "shutil.move",
            "shutil.copy",
            "os.remove",
            "os.unlink",
            "rmdir",
            "unlink(",
        )
    )
    downloads_file = has_network and (
        "'wb'" in lower or '"wb"' in lower or "content" in lower and "write" in lower
    )
    has_delete = any(token in lower for token in ("os.remove", "os.unlink", "rmtree", ".unlink("))
    if has_network and not downloads_file:
        lines.append("· 会访问互联网读取数据")
    elif has_network:
        lines.append("· 会从互联网下载内容到电脑")
    if writes_local:
        lines.append("· 会在电脑上创建或修改文件")
    if has_delete:
        lines.append("· 会删除电脑上的文件（删除后通常难以恢复）")
    if not writes_local and not downloads_file and not has_delete:
        lines.append("· 不会修改或删除你电脑上的文件")
    return "\n".join(lines)


def _sanitize_command_preview(text: str, *, max_len: int = 120) -> str:
    one = " ".join((text or "").split())
    if not one:
        return ""
    home = str(Path.home()).replace("\\", "/")
    if home:
        one = re.sub(re.escape(home), "~", one, flags=re.I)
    if len(one) > max_len:
        cut = one[: max_len - 1]
        space = cut.rfind(" ")
        if space > max_len // 2:
            cut = cut[:space]
        return cut.rstrip() + "…"
    return one


def _format_target_phrase(targets: str, *, suffix: str) -> str:
    """targets 已含「」时不再套一层引号。"""
    if not targets:
        return ""
    if "「" in targets:
        return f"查看{targets}{suffix}"
    return f"查看「{targets}」{suffix}"


def _describe_shell_targets(paths: list[str], *, max_items: int = 2) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        loc = _friendly_location(raw)
        if not loc or loc in seen:
            continue
        seen.add(loc)
        labels.append(loc)
        if len(labels) >= max_items:
            break
    if not labels:
        return ""
    return "、".join(labels)


_POWERSHELL_ACTIONS: tuple[tuple[str, str], ...] = (
    (r"\b(get-childitem|gci)\b", "列出文件夹里的文件"),
    (r"\b(get-content|gc)\b", "读取文件内容"),
    (r"\b(set-content|out-file|add-content)\b", "写入或修改文件"),
    (r"\b(remove-item|del\s)\b", "删除文件或文件夹"),
    (r"\b(move-item)\b", "移动文件或文件夹"),
    (r"\b(copy-item)\b", "复制文件或文件夹"),
    (r"\b(rename-item)\b", "重命名文件或文件夹"),
    (r"\b(get-process)\b", "查看正在运行的程序"),
    (r"\b(get-computerinfo|systeminfo)\b", "查看系统信息"),
    (r"\b(invoke-webrequest|curl\s|wget\s)\b", "从互联网下载内容"),
    (r"\bstart-process\b|\bstart\s+\S", "启动程序"),
    (r"new-object\b.*\bwscript\.shell\b", "解析快捷方式或启动程序"),
    (r"\bpip\s+install\b", "安装 Python 依赖包"),
    (r"\bopenclaw\b|\bgateway\b", "管理 OpenClaw / 微信通道服务"),
)


def _powershell_action_label(command: str) -> str | None:
    lower = (command or "").lower()
    for pattern, label in _POWERSHELL_ACTIONS:
        if re.search(pattern, lower, re.I):
            return label
    return None


def _infer_powershell_intent(command: str) -> str | None:
    cmd = (command or "").strip()
    if not cmd:
        return None
    lower = cmd.lower()
    paths = _extract_quoted_paths(cmd)
    targets = _describe_shell_targets(paths)

    if re.search(r"\b(get-childitem|gci)\b", lower):
        if "wscript.shell" in lower or "createshortcut" in lower:
            if targets:
                return _format_target_phrase(targets, suffix="里的文件和软件快捷方式")
            if "desktop" in lower or "桌面" in cmd:
                return "查看你电脑「桌面」上有哪些文件和软件快捷方式"
        if targets:
            return _format_target_phrase(targets, suffix="文件夹里有哪些文件")
        if "desktop" in lower or "桌面" in cmd:
            return "查看你电脑「桌面」上有哪些文件和软件快捷方式"

    if "desktop" in lower or "桌面" in cmd:
        if any(token in lower for token in ("get-childitem", "dir ", "listdir", "os.listdir")):
            return "查看你电脑「桌面」上有哪些文件和软件快捷方式"
    if "get-process" in lower or "tasklist" in lower:
        return "查看当前正在运行的程序"
    if "get-computerinfo" in lower or "systeminfo" in lower:
        return "查看这台电脑的基本系统信息"
    if any(token in lower for token in ("remove-item", "del ", "rm ", "delete")):
        if targets:
            return f"删除「{targets}」里的文件或文件夹（请确认后再同意）"
        return "删除电脑上的文件或文件夹（请确认后再同意）"
    if any(token in lower for token in ("move-item", "copy-item", "rename-item")):
        if targets:
            return f"移动、复制或重命名「{targets}」里的文件"
        return "移动、复制或重命名电脑上的文件"
    if "set-content" in lower or "out-file" in lower or "add-content" in lower:
        if targets:
            return f"写入或修改「{targets}」相关文件"
        return "写入或修改电脑上的文件内容"
    if "invoke-webrequest" in lower or "curl " in lower or "wget " in lower:
        return "从互联网下载内容到这台电脑"
    if "start-process" in lower or re.search(r"\bstart\s", lower):
        return "启动电脑上的某个程序"
    if "openclaw" in lower or "gateway" in lower:
        return "管理或重启 OpenClaw / 微信通道相关服务"
    return None


def _describe_powershell_plain(command: str) -> str:
    intent = _infer_powershell_intent(command)
    if intent:
        return intent
    cmd = (command or "").strip()
    if not cmd:
        return "执行一条空的 PowerShell 命令"
    action = _powershell_action_label(cmd)
    targets = _describe_shell_targets(_extract_quoted_paths(cmd))
    if action and targets:
        return f"{action}：{targets}"
    if action:
        return action
    if targets:
        return f"在「{targets}」上执行 PowerShell 操作"
    snippet = _sanitize_command_preview(cmd, max_len=96)
    return f"将执行 PowerShell：{snippet}" if snippet else "将执行一条 PowerShell 命令"


def _infer_python_intent(code: str) -> str | None:
    text = (code or "").strip()
    if not text:
        return None
    lower = text.lower()
    if "desktop" in lower or "桌面" in text:
        if "listdir" in lower or "scandir" in lower or "glob" in lower:
            return "用脚本读取你电脑「桌面」上的文件和快捷方式"
    if any(token in lower for token in ("requests.", "urllib", "httpx.")):
        urls = _extract_http_urls(text)
        read_only = ".json(" in lower and not any(
            token in lower for token in ("open(", "'wb'", '"wb"', ".write(")
        )
        if read_only:
            purpose = _describe_url_purpose(urls[0]) if urls else "联网查询公开数据"
            return f"{purpose}（只读，不会改本地文件）"
        if any(token in lower for token in ("open(", "'wb'", '"wb"', "download")):
            return "从互联网下载文件并保存到这台电脑"
        purpose = _describe_url_purpose(urls[0]) if urls else "访问互联网获取数据"
        return purpose
    if "download" in lower:
        return "从互联网下载文件到这台电脑"
    if "subprocess" in lower or "os.system" in lower:
        return "用脚本执行系统命令（可能访问文件或安装依赖）"
    if "open(" in lower and ("w" in lower or "a" in lower):
        return "用脚本创建或修改电脑上的文件"
    if "shutil.move" in lower or "shutil.copy" in lower or "os.remove" in lower:
        return "用脚本移动、复制或删除电脑上的文件"
    return None


def _describe_python_plain(code: str) -> str:
    intent = _infer_python_intent(code)
    if intent:
        return intent
    text = (code or "").strip()
    if not text:
        return "运行一段空的 Python 脚本"
    paths = _extract_quoted_paths(text)
    targets = _describe_shell_targets(paths)
    lower = text.lower()
    if "listdir" in lower or "scandir" in lower or "glob(" in lower:
        if targets:
            return f"用脚本查看「{targets}」文件夹里的内容"
        return "用脚本列出某个文件夹里的文件"
    if targets:
        return f"用脚本处理「{targets}」相关文件"
    snippet = _sanitize_command_preview(text.replace("\n", " "), max_len=96)
    return f"将运行 Python 脚本：{snippet}" if snippet else "将运行一段 Python 脚本"


def describe_approval_plain(tool_name: str, arguments: dict) -> str:
    """面向普通用户的审批说明（不含命令原文）。"""
    args = arguments or {}
    if tool_name == "run_powershell":
        return _describe_powershell_plain(str(args.get("command", "")))
    if tool_name == "run_python":
        return _describe_python_plain(str(args.get("code", "")))
    if tool_name == "run_python_script":
        loc = _friendly_location(str(args.get("path", "")))
        if loc:
            return f"运行脚本文件 {loc}，可能会访问文件或网络"
        return "运行电脑上的一个 Python 脚本文件"
    if tool_name == "write_text_file":
        loc = _friendly_location(str(args.get("path", "")))
        return f"创建或覆盖写入文件{('：' + loc) if loc else ''}"
    if tool_name == "move_file":
        src = _friendly_location(str(args.get("source", "")))
        dst = _friendly_location(str(args.get("destination", "")))
        if src and dst:
            return f"把 {src} 移动到 {dst}"
        return "移动电脑上的文件或文件夹"
    if tool_name == "copy_file":
        src = _friendly_location(str(args.get("source", "")))
        dst = _friendly_location(str(args.get("destination", "")))
        if src and dst:
            return f"复制 {src} 到 {dst}"
        return "复制电脑上的文件或文件夹"
    if tool_name == "delete_file":
        loc = _friendly_location(str(args.get("path", "")))
        return f"删除文件{('：' + loc) if loc else ''}（删除后通常难以恢复）"
    if tool_name == "delete_directory":
        loc = _friendly_location(str(args.get("path", "")))
        return f"删除整个文件夹{('：' + loc) if loc else ''}（删除后通常难以恢复）"
    if tool_name == "organize_directory":
        loc = _friendly_location(str(args.get("path", "")))
        by = str(args.get("by", "extension"))
        by_label = {"extension": "文件类型", "date": "日期", "size": "大小"}.get(by, by)
        return f"整理{('「' + loc + '」' if loc else '文件夹')}，按{by_label}自动分类"
    if tool_name == "batch_rename":
        loc = _friendly_location(str(args.get("path", "")))
        return f"批量重命名{('「' + loc + '」' if loc else '文件夹')}里的多个文件"
    if tool_name == "create_docx":
        loc = _friendly_location(str(args.get("output_path", "")))
        return f"创建 Word 文档{('：' + loc) if loc else ''}"
    if tool_name == "create_pptx":
        loc = _friendly_location(str(args.get("output_path", "")))
        return f"创建 PPT 演示文稿{('：' + loc) if loc else ''}"
    if tool_name == "zip_files":
        count = len(args.get("sources", []) or [])
        return f"把 {count or '若干'} 个文件/文件夹打包成压缩包"
    if tool_name == "unzip_file":
        return "解压压缩包到指定文件夹"
    if tool_name == "download_file":
        name = str(args.get("expected_software", "") or args.get("url", "")).strip()
        if name:
            return f"从互联网下载文件到这台电脑（与 {name[:40]} 相关）"
        return "从互联网下载文件到这台电脑"
    if tool_name == "download_software":
        software = str(args.get("software_name", "软件")).strip() or "软件"
        return f"帮你下载并准备安装「{software}」"
    if tool_name == "clipboard_write":
        return "把一段文字写入系统剪贴板"
    if tool_name == "open_url":
        return f"用浏览器打开网页：{str(args.get('url', ''))[:60]}"
    if tool_name == "open_app":
        return f"启动程序：{str(args.get('name', '') or args.get('path', ''))[:60]}"
    if tool_name == "install_friday_plugin":
        return "为星期五安装一个扩展插件（会下载并写入本地文件）"
    if tool_name == "uninstall_friday_plugin":
        plugin = str(args.get("plugin_id", "插件")).strip() or "插件"
        return f"卸载星期五扩展：{plugin}"
    if tool_name == "browse_webpage":
        return f"联网浏览网页以查找信息：{str(args.get('url', ''))[:60]}"
    if tool_name == "generate_image":
        from friday.image_gen import resolve_image_gen_size
        from friday.storage import load_settings

        prompt = str(args.get("prompt", "")).strip()
        preview = prompt[:48] + ("…" if len(prompt) > 48 else "")
        size = resolve_image_gen_size(
            str(args.get("size", "")).strip(),
            load_settings(),
            prompt=prompt,
        )
        return f"调用生图 API 生成图片（{size}）并保存到「生成的图片」文件夹：{preview or '（无描述）'}"
    return GENERIC_APPROVAL_PLAIN


def describe_approval_detail(tool_name: str, arguments: dict) -> str:
    """审批补充说明：位置信息与命令/脚本摘要。"""
    args = arguments or {}
    if tool_name == "run_powershell":
        cmd = str(args.get("command", ""))
        plain = describe_approval_plain(tool_name, args)
        lines: list[str] = []
        paths = _extract_quoted_paths(cmd)
        locs = []
        for raw in paths:
            loc = _friendly_location(raw)
            if loc and loc not in plain and loc not in locs:
                locs.append(loc)
        if locs:
            lines.append("目标位置：" + "、".join(locs[:3]))
        snippet = _sanitize_command_preview(cmd, max_len=180)
        if snippet:
            lines.append(f"命令摘要：{snippet}")
        return "\n".join(lines)
    if tool_name == "run_python":
        code = str(args.get("code", ""))
        plain = describe_approval_plain(tool_name, args)
        lines: list[str] = []
        urls = _extract_http_urls(code)
        if urls:
            purpose = _describe_url_purpose(urls[0])
            if purpose and purpose not in plain:
                lines.append(f"数据来源：{purpose}")
            elif urlparse(urls[0]).netloc:
                lines.append(f"访问网站：{urlparse(urls[0]).netloc}")
        paths = _extract_quoted_paths(code)
        locs = []
        for raw in paths:
            loc = _friendly_location(raw)
            if loc and loc not in plain and loc not in locs:
                locs.append(loc)
        if locs:
            lines.append("本地位置：" + "、".join(locs[:3]))
        impact = _describe_python_impact(code)
        if impact:
            lines.append(impact)
        if not urls and not locs and not _infer_python_intent(code):
            snippet = _sanitize_command_preview(code.replace("\n", " "), max_len=120)
            if snippet:
                lines.append(f"脚本摘要：{snippet}")
        return "\n".join(lines)
    if tool_name == "download_file":
        dest = _friendly_location(str(args.get("destination", "")))
        return f"保存位置：{dest}" if dest else ""
    if tool_name == "download_software":
        dest = _friendly_location(str(args.get("destination", "")))
        return f"保存位置：{dest}" if dest else ""
    path = (
        args.get("path")
        or args.get("output_path")
        or args.get("destination")
        or args.get("source")
        or args.get("root")
    )
    if path:
        loc = _friendly_location(str(path))
        if loc and loc not in describe_approval_plain(tool_name, args):
            return f"涉及位置：{loc}"
    return ""


def summarize_preview(tool_name: str, arguments: dict) -> str:
    """为审批界面生成用户可读的说明（优先自然语言，下载类保留详情）。"""
    if tool_name in {"download_file", "download_software"}:
        return _summarize_download(arguments) if tool_name == "download_file" else describe_approval_plain(
            tool_name, arguments
        )
    detail = describe_approval_detail(tool_name, arguments)
    if detail:
        return detail
    return describe_approval_plain(tool_name, arguments)


def _summarize_download(arguments: dict) -> str:
    from friday.config import DOWNLOAD_LARGE_MAX_BYTES, DOWNLOAD_LARGE_THRESHOLD_BYTES
    from friday.tools.web import probe_download
    from friday.tools.web_trust import assess_download_trust, format_trust_report

    url = str(arguments.get("url", ""))
    dest = arguments.get("destination", "")
    expected = str(arguments.get("expected_software", "")).strip()
    trust = assess_download_trust(url, expected_software=expected)
    trust_block = format_trust_report(trust).split("\n")
    trust_summary = "\n".join(trust_block[:6])

    if trust.is_blocked:
        return f"下载被拒绝\n来源: {trust.label}\n链接: {url}\n保存至: {dest}\n{trust_summary}"

    probe = probe_download(url)
    size = probe.content_length
    header = f"来源: {trust.label}"
    if size is not None:
        size_text = format_bytes(size)
        if size > DOWNLOAD_LARGE_THRESHOLD_BYTES or arguments.get("confirm_large_download"):
            return (
                f"大文件下载（约 {size_text}）\n"
                f"{header}\n"
                f"链接: {url}\n"
                f"保存至: {dest}\n"
                f"{trust_summary}\n"
                f"确认后将允许下载，最高 {format_bytes(DOWNLOAD_LARGE_MAX_BYTES)}"
            )
        return f"下载文件（约 {size_text}）\n{header}\n链接: {url}\n保存至: {dest}\n{trust_summary}"
    if arguments.get("confirm_large_download"):
        return f"大文件下载（大小未知）\n{header}\n链接: {url}\n保存至: {dest}\n{trust_summary}"
    return f"下载文件\n{header}\n链接: {url}\n保存至: {dest}\n{trust_summary}"

