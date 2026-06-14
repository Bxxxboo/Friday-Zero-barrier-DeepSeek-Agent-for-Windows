"""微信出站产出物：路径提取、校验与摘要。"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from friday.storage import UserSettings, resolved_workspace

MAX_DELIVERABLE_BYTES = 15 * 1024 * 1024

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
ATTACHMENT_SUFFIXES = frozenset({
    ".docx",
    ".pptx",
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xlsx",
    ".zip",
})
TEXT_FILE_SUFFIXES = frozenset({".txt", ".md", ".csv", ".json"})

_REQUESTED_FILE_RE = re.compile(
    r"([\w\u4e00-\u9fff\-\.（）()《》]+\.(?:docx|pptx|pdf|txt|md|csv|json|xlsx|zip))",
    re.I,
)
_SEND_INTENT_RE = re.compile(r"发送|发过来|发我|发一下|发来|传给我|给我发", re.I)
_FILENAME_NOISE_RE = re.compile(
    r"^(?:帮我把|把|请把)?(?:桌面上的?|文档里的?|下载文件夹里的?|.*?(?:文件夹|目录)(?:中|里)?的?)?",
)

_PATH_PREFIXES: dict[str, str] = {
    "generate_image": "已生成图片并保存：",
    "create_docx": "已创建 Word 文档:",
    "create_pptx": "已创建 PPT 文档:",
    "write_text_file": "已写入:",
    "screenshot": "截图已保存:",
}

_SCREENSHOT_SIZE_RE = re.compile(r"\s+\(\d+x\d+\)\s*$")
_COPY_RESULT_RE = re.compile(r"^已复制:\s*.+?\s*->\s*(.+?)\s*$", re.MULTILINE)
_MOVE_RESULT_RE = re.compile(r"^已移动:\s*.+?\s*->\s*(.+?)\s*$", re.MULTILINE)


def extract_deliverable_path(tool_name: str, result: str) -> str | None:
    """从工具返回文本提取产出物路径。"""
    prefix = _PATH_PREFIXES.get(tool_name)
    if not prefix or prefix not in (result or ""):
        return None
    first_line = (result or "").split("\n", 1)[0].strip()
    if not first_line.startswith(prefix):
        return None
    path = first_line[len(prefix):].strip()
    if tool_name == "screenshot":
        path = _SCREENSHOT_SIZE_RE.sub("", path).strip()
    return path or None


def is_text_file_deliverable(path: str | Path) -> bool:
    return Path(path).suffix.lower() in TEXT_FILE_SUFFIXES


def is_image_deliverable(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def is_attachment_deliverable(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in ATTACHMENT_SUFFIXES or suffix in IMAGE_SUFFIXES


def format_deliverable_caption(path: str | Path) -> str:
    return f"已生成：{Path(path).name}"


def extract_copy_file_destination(result: str) -> str | None:
    """从 copy_file 工具返回解析目标路径。"""
    match = _COPY_RESULT_RE.match((result or "").strip())
    if not match:
        return None
    return match.group(1).strip() or None


def extract_move_file_destination(result: str) -> str | None:
    """从 move_file 工具返回解析目标路径。"""
    match = _MOVE_RESULT_RE.match((result or "").strip())
    if not match:
        return None
    return match.group(1).strip() or None


def list_deliverables_in_delivered(
    settings: UserSettings,
    *,
    min_mtime: float | None = None,
) -> list[Path]:
    """扫描 delivered 目录，返回 min_mtime 之后所有可发送附件（按 mtime 升序）。"""
    from friday.artifacts import delivered_dir

    delivered = delivered_dir(settings)
    if not delivered.is_dir():
        return []
    cutoff = time.time() - 1.0 if min_mtime is None else min_mtime
    found: list[tuple[float, Path]] = []
    for candidate in delivered.iterdir():
        if not candidate.is_file():
            continue
        if file_generated_kind_for_path(candidate) is None:
            continue
        try:
            mtime = candidate.stat().st_mtime
        except OSError:
            continue
        if mtime <= cutoff:
            continue
        found.append((mtime, candidate))
    found.sort(key=lambda item: item[0])
    return [path for _, path in found]


def newest_deliverable_in_delivered(
    settings: UserSettings,
    *,
    min_mtime: float | None = None,
) -> Path | None:
    """扫描 delivered 目录，返回 min_mtime 之后最新的可发送附件。"""
    items = list_deliverables_in_delivered(settings, min_mtime=min_mtime)
    return items[-1] if items else None


def list_deliverables_in_workspace_root(
    settings: UserSettings,
    *,
    min_mtime: float | None = None,
) -> list[Path]:
    """扫描工作区根目录（非递归），返回 min_mtime 之后所有可发送附件（按 mtime 升序）。"""
    workspace = Path(resolved_workspace(settings)).resolve()
    if not workspace.is_dir():
        return []
    cutoff = time.time() - 1.0 if min_mtime is None else min_mtime
    found: list[tuple[float, Path]] = []
    try:
        for candidate in workspace.iterdir():
            if not candidate.is_file():
                continue
            if file_generated_kind_for_path(candidate) is None:
                continue
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime <= cutoff:
                continue
            found.append((mtime, candidate))
    except OSError:
        return []
    found.sort(key=lambda item: item[0])
    return [path for _, path in found]


def list_turn_new_deliverables(
    settings: UserSettings,
    *,
    min_mtime: float | None = None,
) -> list[Path]:
    """delivered/ 与工作区根目录本轮新增的可发送附件（去重，按 mtime 升序）。"""
    merged: list[tuple[float, Path]] = []
    seen: set[str] = set()
    for path in list_deliverables_in_delivered(settings, min_mtime=min_mtime):
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            merged.append((path.stat().st_mtime, path))
        except OSError:
            continue
    for path in list_deliverables_in_workspace_root(settings, min_mtime=min_mtime):
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            merged.append((path.stat().st_mtime, path))
        except OSError:
            continue
    merged.sort(key=lambda item: item[0])
    return [path for _, path in merged]


def snapshot_deliverable_path_keys(settings: UserSettings) -> set[str]:
    """delivered/ 与工作区根目录当前所有可发送附件路径（用于回合前后 diff）。"""
    keys: set[str] = set()
    from friday.artifacts import delivered_dir

    workspace = Path(resolved_workspace(settings)).resolve()
    for directory in (delivered_dir(settings), workspace):
        if not directory.is_dir():
            continue
        try:
            for candidate in directory.iterdir():
                if not candidate.is_file():
                    continue
                if file_generated_kind_for_path(candidate) is None:
                    continue
                keys.add(str(candidate.resolve()))
        except OSError:
            continue
    return keys


def list_deliverables_since_path_snapshot(
    settings: UserSettings,
    *,
    before_keys: set[str],
) -> list[Path]:
    """快照之后新增的可发送附件（不依赖 mtime，Copy-Item 保留源时间戳时仍有效）。"""
    found: list[tuple[float, Path]] = []
    from friday.artifacts import delivered_dir

    workspace = Path(resolved_workspace(settings)).resolve()
    for directory in (delivered_dir(settings), workspace):
        if not directory.is_dir():
            continue
        try:
            for candidate in directory.iterdir():
                if not candidate.is_file():
                    continue
                if file_generated_kind_for_path(candidate) is None:
                    continue
                key = str(candidate.resolve())
                if key in before_keys:
                    continue
                try:
                    found.append((candidate.stat().st_mtime, candidate))
                except OSError:
                    continue
        except OSError:
            continue
    found.sort(key=lambda item: item[0])
    return [path for _, path in found]


def list_turn_deliverable_candidates(
    settings: UserSettings,
    *,
    min_mtime: float,
    before_path_keys: set[str] | None,
    already_sent: set[str],
) -> list[Path]:
    """回合末待发送附件：delivered/ 中未发的全补；其余目录新增或本轮有写入的。"""
    from friday.artifacts import delivered_dir

    workspace = Path(resolved_workspace(settings)).resolve()
    delivered = delivered_dir(settings)
    found: dict[str, tuple[float, Path]] = {}

    def _consider(candidate: Path, *, force_unsent_delivered: bool) -> None:
        key = str(candidate.resolve())
        if key in already_sent:
            return
        if file_generated_kind_for_path(candidate) is None:
            return
        if not should_emit_weixin_copy_deliverable(key, settings=settings):
            return
        try:
            mtime = candidate.stat().st_mtime
        except OSError:
            return
        if force_unsent_delivered:
            found[key] = (mtime, candidate)
            return
        if before_path_keys is not None:
            if key not in before_path_keys or mtime >= min_mtime:
                found[key] = (mtime, candidate)
            return
        if mtime >= min_mtime:
            found[key] = (mtime, candidate)

    for directory, force_unsent in (
        (delivered, True),
        (workspace, False),
    ):
        if not directory.is_dir():
            continue
        try:
            for candidate in directory.iterdir():
                if not candidate.is_file():
                    continue
                _consider(candidate, force_unsent_delivered=force_unsent)
        except OSError:
            continue

    ordered = sorted(found.values(), key=lambda item: item[0])
    return [path for _, path in ordered]


def deliver_turn_new_attachments(
    *,
    settings: UserSettings,
    on_event: Any,
    min_mtime: float,
    already_sent: set[str] | None = None,
    before_path_keys: set[str] | None = None,
) -> int:
    """本轮结束时补发 delivered/ 与工作区根目录中尚未发送的附件（如多套试卷）。"""
    sent = already_sent or set()
    candidates = list_turn_deliverable_candidates(
        settings,
        min_mtime=min_mtime,
        before_path_keys=before_path_keys,
        already_sent=sent,
    )
    count = 0
    for path in candidates:
        key = str(path.resolve())
        if key in sent:
            continue
        if not should_emit_weixin_copy_deliverable(key, settings=settings):
            continue
        kind = file_generated_kind_for_path(path)
        if not kind:
            continue
        on_event("file_generated", {"path": key, "kind": kind})
        count += 1
    return count


def file_generated_kind_for_path(path: str | Path) -> str | None:
    """微信 file_generated 事件的 kind 字段。"""
    target = Path(path)
    if is_text_file_deliverable(target):
        return "text"
    suffix = target.suffix.lower()
    if suffix in {".docx", ".pptx", ".pdf", ".xlsx", ".zip"}:
        return "document"
    return None


def deliverable_roots(settings: UserSettings) -> list[Path]:
    """允许作为微信附件发送的路径根（工作区 + 本机常用文件夹）。"""
    workspace = Path(resolved_workspace(settings)).resolve()
    roots: list[Path] = [workspace]
    from friday.paths import known_folders

    for path_str in known_folders(str(workspace)).values():
        roots.append(Path(path_str).expanduser().resolve())
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def is_within_deliverable_roots(path: Path, settings: UserSettings) -> bool:
    resolved = path.expanduser().resolve()
    for root in deliverable_roots(settings):
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def should_emit_weixin_copy_deliverable(
    destination: str,
    *,
    settings: UserSettings,
) -> bool:
    """微信会话中 copy_file 是否应触发 file_generated。"""
    from friday.artifacts import delivered_dir

    target = Path(destination).expanduser().resolve()
    if not target.is_file() or file_generated_kind_for_path(target) is None:
        return False
    if not is_within_deliverable_roots(target, settings):
        return False
    delivered = delivered_dir(settings).resolve()
    try:
        target.resolve().relative_to(delivered)
        return True
    except ValueError:
        pass
    return is_attachment_deliverable(target)


def exceeds_max_deliverable_size(path: Path) -> bool:
    try:
        return path.stat().st_size > MAX_DELIVERABLE_BYTES
    except OSError:
        return True


def resolve_image_path(path: str, settings: UserSettings) -> Path:
    from friday.image_gen import resolve_generated_image_path

    return resolve_generated_image_path(path, settings)


def resolve_attachment_path(path: str, settings: UserSettings) -> Path:
    from friday.portability import resolve_portable_path

    workspace = Path(resolved_workspace(settings)).resolve()
    target = resolve_portable_path(path, str(workspace))
    if not target.is_file():
        raise FileNotFoundError(f"找不到文件: {target}")
    if not is_within_deliverable_roots(target, settings):
        raise PermissionError("路径超出可发送范围（工作区或本机常用文件夹）")
    suffix = target.suffix.lower()
    if suffix not in ATTACHMENT_SUFFIXES:
        raise ValueError(f"不支持的附件格式: {suffix or '(无后缀)'}")
    if exceeds_max_deliverable_size(target):
        raise ValueError("文件过大，无法通过微信发送")
    return target


def extract_requested_filename(user_text: str) -> str | None:
    """从微信用户消息提取请求发送的文件名（basename）。"""
    text = re.sub(r"\*+", "", (user_text or "").strip())
    candidates = _REQUESTED_FILE_RE.findall(text)
    if not candidates:
        return None
    best: str | None = None
    for raw in candidates:
        name = Path(raw.strip()).name
        name = _FILENAME_NOISE_RE.sub("", name).strip()
        name = re.sub(r"^(?:给我)?(?:发送|发|传给我|发来)", "", name).strip()
        if "的" in name and not name.startswith("."):
            name = name.split("的")[-1].strip()
        if not name or "." not in name:
            continue
        if best is None or len(name) < len(best):
            best = name
    return best


def user_requests_weixin_file_delivery(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not extract_requested_filename(text):
        return False
    return bool(_SEND_INTENT_RE.search(text))


def find_deliverable_for_weixin_request(user_text: str, settings: UserSettings) -> Path | None:
    """按用户消息中的文件名，在 delivered/ 与可发送根目录查找附件。"""
    filename = extract_requested_filename(user_text)
    if not filename:
        return None
    target_lower = filename.lower()

    from friday.artifacts import delivered_dir

    delivered = delivered_dir(settings)
    if delivered.is_dir():
        found = _find_named_attachment_in_dir(delivered, filename, target_lower)
        if found is not None:
            return found

    for root in deliverable_roots(settings):
        found = _find_named_attachment_under_root(root, filename, target_lower)
        if found is not None:
            return found
    return None


def _find_named_attachment_in_dir(
    directory: Path,
    filename: str,
    target_lower: str,
) -> Path | None:
    exact = directory / filename
    if exact.is_file() and file_generated_kind_for_path(exact):
        return exact.resolve()
    try:
        for candidate in directory.iterdir():
            if not candidate.is_file():
                continue
            if candidate.name.lower() == target_lower and file_generated_kind_for_path(candidate):
                return candidate.resolve()
            if target_lower in candidate.name.lower() and file_generated_kind_for_path(candidate):
                return candidate.resolve()
    except OSError:
        return None
    return None


def _find_named_attachment_under_root(
    root: Path,
    filename: str,
    target_lower: str,
) -> Path | None:
    if not root.is_dir():
        return None
    found = _find_named_attachment_in_dir(root, filename, target_lower)
    if found is not None:
        return found
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            nested = _find_named_attachment_in_dir(child, filename, target_lower)
            if nested is not None:
                return nested
    except OSError:
        return None
    return None


def try_deliver_existing_weixin_file(
    user_text: str,
    *,
    settings: UserSettings,
    on_event: Any,
    skip_if_sent: dict[str, bool] | None = None,
) -> bool:
    """用户要求发送已有文件，但本轮未触发 file_generated 时的补发。"""
    if skip_if_sent and skip_if_sent.get("file"):
        return False
    if not user_requests_weixin_file_delivery(user_text):
        return False
    path = find_deliverable_for_weixin_request(user_text, settings)
    if path is None:
        return False
    if not should_emit_weixin_copy_deliverable(str(path), settings=settings):
        return False
    kind = file_generated_kind_for_path(path)
    if not kind:
        return False
    on_event("file_generated", {"path": str(path), "kind": kind})
    return True
