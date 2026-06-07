from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from friday.interaction_modes import (
    ASK_BLOCK_REASON,
    effective_settings,
    normalize_mode,
    tool_allowed_in_mode,
)
from friday.storage import UserSettings, resolved_workspace


class RiskLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    EXEC = "exec"


@dataclass
class PendingAction:
    tool_name: str
    arguments: dict
    summary: str
    risk: RiskLevel
    large_download: bool = False
    download_size_bytes: int | None = None
    untrusted_download: bool = False
    trust_label: str = ""


@dataclass
class ToolDecision:
    allowed: bool
    needs_approval: bool
    reason: str = ""
    large_download: bool = False
    download_size_bytes: int | None = None
    untrusted_download: bool = False
    trust_label: str = ""
    always_require_approval: bool = False


@dataclass
class TurnApprovalState:
    """当前对话中已获得的审批授权（跨多条用户消息保留，直到新建对话或拒绝操作）。"""

    general: bool = False
    large_download: bool = False
    untrusted_download: bool = False


def should_request_approval(
    settings: UserSettings,
    decision: ToolDecision,
    state: TurnApprovalState,
) -> bool:
    """判断本次工具调用是否仍需弹出审批。"""
    if not decision.needs_approval:
        return False
    if decision.always_require_approval:
        return True
    if not settings.approve_once_per_turn:
        return True
    if decision.large_download and not state.large_download:
        return True
    if decision.untrusted_download and not state.untrusted_download:
        return True
    return not state.general


def mark_turn_approved(state: TurnApprovalState, decision: ToolDecision) -> None:
    state.general = True
    if decision.large_download:
        state.large_download = True
    if decision.untrusted_download:
        state.untrusted_download = True


WRITE_TOOLS = {
    "write_text_file",
    "move_file",
    "organize_directory",
    "create_docx",
    "create_pptx",
    "batch_rename",
    "zip_files",
    "unzip_file",
    "delete_file",
    "delete_directory",
    "copy_file",
    "clipboard_write",
    "download_file",
    "download_software",
}

READ_ONLY_TOOLS = {
    "list_directory",
    "search_files",
    "read_text_file",
    "read_pdf",
    "read_excel",
    "find_duplicates",
    "get_system_status",
    "get_disk_usage",
    "get_top_processes",
    "get_file_info",
    "screenshot",
    "clipboard_read",
    "get_network_info",
    "browse_webpage",
    "verify_download_source",
    "list_friday_plugins",
    "list_plugin_catalog",
    "describe_image",
    "vision_status",
    "image_gen_status",
    "python_env_info",
}

# 所有接受路径参数的工具（读 + 写），用于工作区限制
PATH_TOOLS = WRITE_TOOLS | {
    "list_directory",
    "search_files",
    "read_text_file",
    "read_pdf",
    "read_excel",
    "find_duplicates",
    "get_file_info",
    "screenshot",
    "download_file",
    "describe_image",
}

PYTHON_PATH_TOOLS = {
    "run_python",
    "run_python_script",
}


def classify_tool(tool_name: str) -> RiskLevel:
    exec_tools = {
        "run_powershell",
        "run_python",
        "run_python_script",
        "open_url",
        "open_app",
        "install_friday_plugin",
        "uninstall_friday_plugin",
    }
    if tool_name in READ_ONLY_TOOLS:
        return RiskLevel.READ
    if tool_name in exec_tools:
        return RiskLevel.EXEC
    return RiskLevel.WRITE


def _resolve_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def path_in_workspace(path: str, workspace: str) -> bool:
    try:
        target = _resolve_path(path)
        root = _resolve_path(workspace)
        target.relative_to(root)
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _extract_paths(tool_name: str, arguments: dict) -> list[str]:
    if tool_name in {"list_directory", "read_text_file", "write_text_file", "organize_directory",
                      "read_pdf", "read_excel", "find_duplicates", "batch_rename",
                      "delete_file", "delete_directory", "get_file_info"}:
        path = arguments.get("path")
        return [str(path)] if path else []
    if tool_name in {"search_files"}:
        root = arguments.get("root")
        return [str(root)] if root else []
    if tool_name in {"move_file", "copy_file"}:
        paths = []
        if arguments.get("source"):
            paths.append(str(arguments["source"]))
        if arguments.get("destination"):
            paths.append(str(arguments["destination"]))
        return paths
    if tool_name in {"create_docx", "create_pptx", "zip_files", "screenshot"}:
        output = arguments.get("output_path") or arguments.get("output")
        paths = [str(output)] if output else []
        sources = arguments.get("sources")
        if isinstance(sources, list):
            paths.extend(str(s) for s in sources)
        return paths
    if tool_name == "unzip_file":
        return [str(arguments.get(k)) for k in ("source", "output_dir") if arguments.get(k)]
    if tool_name == "download_file":
        dest = arguments.get("destination")
        return [str(dest)] if dest else []
    if tool_name == "download_software":
        dest = arguments.get("destination")
        return [str(dest)] if dest else []
    if tool_name == "generate_image":
        fname = arguments.get("filename")
        return [str(fname)] if fname else []
    if tool_name == "run_python_script":
        path = arguments.get("path")
        paths = [str(path)] if path else []
        if arguments.get("cwd"):
            paths.append(str(arguments["cwd"]))
        return paths
    if tool_name == "run_python":
        cwd = arguments.get("cwd")
        return [str(cwd)] if cwd else []
    return []


def _tool_enabled(settings: UserSettings, tool_name: str) -> tuple[bool, str]:
    if tool_name == "write_text_file" and not settings.allow_write_files:
        return False, "已在安全设置中禁用「写入文件」"
    if tool_name == "move_file" and not settings.allow_move_files:
        return False, "已在安全设置中禁用「移动/重命名文件」"
    if tool_name == "organize_directory" and not settings.allow_organize:
        return False, "已在安全设置中禁用「整理目录」"
    if tool_name in {"create_docx", "create_pptx"} and not settings.allow_create_documents:
        return False, "已在安全设置中禁用「创建 Word/PPT 文档」"
    if tool_name == "run_powershell" and not settings.allow_powershell:
        return False, "已在安全设置中禁用「PowerShell 命令」"
    if tool_name in {"run_python", "run_python_script"} and not settings.allow_python:
        return False, "已在安全设置中禁用「Python 代码执行」"
    if tool_name == "browse_webpage" and not settings.allow_web_browse:
        return False, "已在安全设置中禁用「浏览网页」"
    if tool_name == "download_file" and not settings.allow_downloads:
        return False, "已在安全设置中禁用「联网下载」"
    return True, ""


def evaluate_tool(
    settings: UserSettings,
    tool_name: str,
    arguments: dict,
    *,
    yolo_unlocked: bool = False,
) -> ToolDecision:
    mode = normalize_mode(getattr(settings, "interaction_mode", "agent"))
    if not tool_allowed_in_mode(tool_name, mode):
        return ToolDecision(False, False, ASK_BLOCK_REASON)

    cfg = effective_settings(settings, yolo_unlocked=yolo_unlocked)
    enabled, reason = _tool_enabled(cfg, tool_name)
    if not enabled:
        return ToolDecision(False, False, reason)

    risk = classify_tool(tool_name)

    if cfg.restrict_to_workspace and tool_name in (PATH_TOOLS | PYTHON_PATH_TOOLS):
        # 用户指定路径的联网下载不受工作区限制（如保存到 E 盘）
        if tool_name != "download_file":
            root = resolved_workspace(cfg)
            for path in _extract_paths(tool_name, arguments):
                if path and not path_in_workspace(path, root):
                    return ToolDecision(
                        False,
                        False,
                        f"路径超出默认操作文件夹范围（{root}）: {path}",
                    )

    if tool_name == "download_file":
        return _evaluate_download(cfg, arguments, yolo_unlocked=yolo_unlocked)

    if tool_name == "download_software":
        enabled, reason = _tool_enabled(cfg, "download_file")
        if not enabled:
            return ToolDecision(False, False, reason)
        return ToolDecision(True, cfg.require_approval_writes)

    if tool_name == "generate_image":
        if not cfg.image_gen_enabled:
            return ToolDecision(False, False, "已在设置中关闭生图功能")
        return ToolDecision(True, True, always_require_approval=True)

    if tool_name == "run_powershell":
        blocked = _powershell_download_block_reason(str(arguments.get("command", "")))
        if blocked:
            return ToolDecision(False, False, blocked)

    if risk == RiskLevel.READ:
        return ToolDecision(True, False)

    if risk == RiskLevel.EXEC:
        return ToolDecision(True, cfg.require_approval_exec)

    return ToolDecision(True, cfg.require_approval_writes)


def _powershell_download_block_reason(command: str) -> str:
    """禁止用 PowerShell 下载/探测 URL，引导使用专用下载工具。"""
    normalized = re.sub(r"\s+", " ", command.replace("`", "")).strip().lower()
    if not normalized:
        return ""

    if re.search(r"https?://", normalized):
        return (
            "禁止用 PowerShell 访问或下载 URL。请改用 download_software（推荐）或 browse_webpage + download_file。"
        )

    download_hints = (
        r"\b(iwr|invoke-webrequest|invoke-restmethod|wget|curl|start-bitstransfer)\b",
        r"\b(webclient|downloadfile|downloadstring)\b",
        r"\b-uri\b",
        r"\bout-file\b",
        r"\busebasicparsing\b",
    )
    for pattern in download_hints:
        if re.search(pattern, normalized):
            return (
                "禁止用 PowerShell 下载文件。请改用 download_software 或 download_file 工具，"
                "它们会验证官方来源且不会反复弹窗。"
            )
    return ""


def _format_bytes(num: int) -> str:
    if num >= 1024 ** 3:
        return f"{num / (1024 ** 3):.2f} GB"
    if num >= 1024 ** 2:
        return f"{num / (1024 ** 2):.1f} MB"
    if num >= 1024:
        return f"{num / 1024:.1f} KB"
    return f"{num} B"


def _evaluate_download(
    settings: UserSettings,
    arguments: dict,
    *,
    yolo_unlocked: bool = False,
) -> ToolDecision:
    from friday.config import (
        DOWNLOAD_LARGE_MAX_BYTES,
        DOWNLOAD_LARGE_THRESHOLD_BYTES,
    )
    from friday.tools.web import probe_download
    from friday.tools.web_trust import assess_download_trust

    url = str(arguments.get("url", "")).strip()
    expected = str(arguments.get("expected_software", "")).strip()
    confirm_large = bool(arguments.get("confirm_large_download"))
    confirm_untrusted = bool(arguments.get("confirm_untrusted_source"))
    allow_large = bool(arguments.get("_allow_large"))
    approved_untrusted = bool(arguments.get("_untrusted_approved"))

    trust = assess_download_trust(url, expected_software=expected)
    if trust.is_blocked:
        return ToolDecision(
            False,
            False,
            f"下载源不安全（{trust.label}）：{' '.join(trust.reasons[:2])}",
            trust_label=trust.label,
        )

    if (
        trust.needs_untrusted_confirm
        and settings.require_trusted_downloads
        and not confirm_untrusted
        and not approved_untrusted
        and not yolo_unlocked
    ):
        hint = "；若用户仍同意非官方来源，请先 verify_download_source 并设置 confirm_untrusted_source=true"
        return ToolDecision(
            False,
            False,
            f"下载源未通过安全验证（{trust.label}）：{' '.join(trust.reasons[:2])}{hint}",
            trust_label=trust.label,
        )

    probe = probe_download(url)
    size = probe.content_length

    if size is not None and size > DOWNLOAD_LARGE_MAX_BYTES:
        return ToolDecision(
            False,
            False,
            f"文件过大（{_format_bytes(size)}），超过系统上限 {_format_bytes(DOWNLOAD_LARGE_MAX_BYTES)}",
            trust_label=trust.label,
        )

    large = allow_large or confirm_large
    if size is not None and size > DOWNLOAD_LARGE_THRESHOLD_BYTES:
        large = True

    untrusted = trust.needs_untrusted_confirm and not approved_untrusted and not yolo_unlocked
    if yolo_unlocked:
        needs = False
    else:
        needs = settings.require_approval_writes or large or untrusted
        if large and not allow_large:
            needs = True

    return ToolDecision(
        True,
        needs,
        large_download=large and not allow_large,
        download_size_bytes=size,
        untrusted_download=untrusted,
        trust_label=trust.label,
    )


def needs_approval(tool_name: str) -> bool:
    return classify_tool(tool_name) != RiskLevel.READ


_KNOWN_FOLDER_LABELS: tuple[tuple[str, str], ...] = (
    ("/desktop", "桌面"),
    ("/downloads", "下载文件夹"),
    ("/documents", "文档"),
    ("/pictures", "图片"),
    ("/videos", "视频"),
    ("/music", "音乐"),
)


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
        if re.match(r"^[A-Za-z]:\\", val) or val.startswith(("~/", "/")) or "\\" in val or "/" in val:
            paths.append(val)
    return paths


def _sanitize_command_preview(text: str, *, max_len: int = 120) -> str:
    one = " ".join((text or "").split())
    if not one:
        return ""
    home = str(Path.home()).replace("\\", "/")
    if home:
        one = re.sub(re.escape(home), "~", one, flags=re.I)
    if len(one) > max_len:
        return one[: max_len - 1].rstrip() + "…"
    return one


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
                return f"查看「{targets}」里的文件和软件快捷方式"
            if "desktop" in lower or "桌面" in cmd:
                return "查看你电脑「桌面」上有哪些文件和软件快捷方式"
        if targets:
            return f"查看「{targets}」文件夹里有哪些文件"
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
    if "download" in lower or "urllib" in lower or "requests.get" in lower:
        return "用脚本从互联网下载文件到这台电脑"
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
        prompt = str(args.get("prompt", "")).strip()
        preview = prompt[:48] + ("…" if len(prompt) > 48 else "")
        size = str(args.get("size", "")).strip() or "默认尺寸"
        return f"调用生图 API 生成图片（{size}）并保存到「生成的图片」文件夹：{preview or '（无描述）'}"
    return "在这台电脑上执行一项需要你确认的操作"


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
        paths = _extract_quoted_paths(code)
        locs = []
        for raw in paths:
            loc = _friendly_location(raw)
            if loc and loc not in plain and loc not in locs:
                locs.append(loc)
        if locs:
            lines.append("目标位置：" + "、".join(locs[:3]))
        snippet = _sanitize_command_preview(code.replace("\n", " "), max_len=180)
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


def summarize_action(tool_name: str, arguments: dict) -> str:
    if tool_name == "move_file":
        return f"移动文件: {arguments.get('source')} -> {arguments.get('destination')}"
    if tool_name == "organize_directory":
        return f"整理目录: {arguments.get('path')} (按 {arguments.get('by', 'extension')})"
    if tool_name == "create_docx":
        return f"创建 Word: {arguments.get('output_path')}"
    if tool_name == "create_pptx":
        return f"创建 PPT: {arguments.get('output_path')}"
    if tool_name == "run_powershell":
        cmd = str(arguments.get("command", ""))[:120]
        return f"执行 PowerShell: {cmd}"
    if tool_name == "run_python":
        preview = str(arguments.get("code", "")).replace("\n", " ")[:120]
        return f"执行 Python: {preview}"
    if tool_name == "run_python_script":
        return f"运行 Python 脚本: {arguments.get('path')}"
    if tool_name == "write_text_file":
        return f"写入文件: {arguments.get('path')}"
    if tool_name == "clipboard_write":
        preview = str(arguments.get("text", ""))[:80]
        return f"写入剪贴板: {preview}{'…' if len(str(arguments.get('text', ''))) > 80 else ''}"
    if tool_name == "batch_rename":
        return f"批量重命名: {arguments.get('path')} (模式: {arguments.get('mode')})"
    if tool_name == "zip_files":
        return f"压缩文件: {len(arguments.get('sources', []))} 个 -> {arguments.get('output')}"
    if tool_name == "unzip_file":
        return f"解压文件: {arguments.get('source')} -> {arguments.get('output_dir')}"
    if tool_name == "download_file":
        return f"下载文件: {arguments.get('url')} -> {arguments.get('destination')}"
    if tool_name == "download_software":
        return f"下载软件: {arguments.get('software_name')} -> {arguments.get('destination')}"
    if tool_name == "browse_webpage":
        return f"浏览网页: {arguments.get('url')}"
    if tool_name == "install_friday_plugin":
        return f"安装扩展插件: {arguments.get('source')}"
    if tool_name == "uninstall_friday_plugin":
        return f"卸载扩展插件: {arguments.get('plugin_id')}"
    if tool_name == "find_duplicates":
        return f"查找重复文件: {arguments.get('path')}"
    return f"{tool_name}({arguments})"

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
        size_text = _format_bytes(size)
        if size > DOWNLOAD_LARGE_THRESHOLD_BYTES or arguments.get("confirm_large_download"):
            return (
                f"大文件下载（约 {size_text}）\n"
                f"{header}\n"
                f"链接: {url}\n"
                f"保存至: {dest}\n"
                f"{trust_summary}\n"
                f"确认后将允许下载，最高 {_format_bytes(DOWNLOAD_LARGE_MAX_BYTES)}"
            )
        return f"下载文件（约 {size_text}）\n{header}\n链接: {url}\n保存至: {dest}\n{trust_summary}"
    if arguments.get("confirm_large_download"):
        return f"大文件下载（大小未知）\n{header}\n链接: {url}\n保存至: {dest}\n{trust_summary}"
    return f"下载文件\n{header}\n链接: {url}\n保存至: {dest}\n{trust_summary}"
