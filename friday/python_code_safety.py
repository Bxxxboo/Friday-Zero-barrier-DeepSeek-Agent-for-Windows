"""run_python / run_python_script 静态安全分析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from friday.os_path_guard import OS_DELETE_BLOCK_REASON
from friday.paths import get_appdata_dir

_WINDOWS_C_OS_CODE_MARKERS: tuple[str, ...] = (
    "c:/windows",
    "c:\\windows",
    "c:/program files (x86)",
    "c:\\program files (x86)",
    "c:/program files",
    "c:\\program files",
    "c:/programdata",
    "c:\\programdata",
    "c:/boot",
    "c:\\boot",
    "c:/recovery",
    "c:\\recovery",
)


@dataclass(frozen=True)
class PythonCodeSafety:
    blocked: bool = False
    block_reason: str = ""
    always_require_approval: bool = False
    approval_note: str = ""


_DELETE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bos\.remove\s*\(", "删除文件"),
    (r"\bos\.unlink\s*\(", "删除文件"),
    (r"\bPath\s*\([^)]*\)\s*\.\s*unlink\s*\(", "删除文件"),
    (r"\.unlink\s*\(\s*(?:missing_ok\s*=\s*True\s*)?\)", "删除文件"),
    (r"\bshutil\.rmtree\s*\(", "删除文件夹"),
    (r"\brmtree\s*\(", "删除文件夹"),
)

# 移动/复制/重命名等会覆盖或替换已有路径，每次须单独审批。
_OVERWRITE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bshutil\.move\s*\(", "移动/覆盖文件"),
    (r"\bshutil\.copy2?\s*\(", "复制/覆盖文件"),
    (r"\bos\.rename\s*\(", "重命名/覆盖文件"),
    (r"\bos\.replace\s*\(", "覆盖文件"),
)

# 新建/写入（open write 等）；工作区内新建走普通 run_python 审批（同轮确认一次）。
_CREATE_WRITE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"open\s*\([^)]*['\"]w", "写入文件"),
    (r"open\s*\([^)]*['\"]a", "追加写入文件"),
    (r"open\s*\([^)]*['\"]x", "创建文件"),
    (r"\.write_text\s*\(", "写入文件"),
    (r"\.write_bytes\s*\(", "写入文件"),
    (r"\bjson\.dump\s*\(", "写入 JSON 文件"),
)

_FRIDAY_APP_MARKERS: tuple[str, ...] = (
    "appdata/roaming/friday",
    "operations.json",
    "settings.json",
    "settings.json.bak",
    "operations.json.bak",
    "operations.json.tmp",
    ".fernet_key",
    "friday.log",
)


def _normalize(code: str) -> str:
    return re.sub(r"\s+", " ", (code or "").replace("\\", "/").lower()).strip()


def _friday_appdata_needles() -> tuple[str, ...]:
    root = str(get_appdata_dir()).replace("\\", "/").lower()
    needles = [_FRIDAY_APP_MARKERS[0]]
    if root and root not in needles:
        needles = (root, *_FRIDAY_APP_MARKERS)
    return needles


def _touches_friday_app_data(code: str) -> bool:
    norm = _normalize(code)
    return any(marker in norm for marker in _friday_appdata_needles())


def _match_patterns(code: str, patterns: tuple[tuple[str, str], ...]) -> list[str]:
    hits: list[str] = []
    for pattern, label in patterns:
        if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
            if label not in hits:
                hits.append(label)
    return hits


def analyze_python_code(code: str) -> PythonCodeSafety:
    """分析 Python 源码中的删写风险。"""
    text = code or ""
    if not text.strip():
        return PythonCodeSafety()

    deletes = _match_patterns(text, _DELETE_PATTERNS)
    overwrites = _match_patterns(text, _OVERWRITE_PATTERNS)
    creates = _match_patterns(text, _CREATE_WRITE_PATTERNS)
    any_file_io = bool(deletes or overwrites or creates)

    if any_file_io and _touches_friday_app_data(text):
        return PythonCodeSafety(
            blocked=True,
            block_reason=(
                "禁止用 Python 直接修改或删除「星期五」应用数据"
                "（如 operations.json、settings.json）。"
                "请改用专用文件工具，或请用户在设置/日志界面手动处理。"
            ),
        )

    norm = _normalize(text)
    if (deletes or overwrites) and any(marker in norm for marker in _WINDOWS_C_OS_CODE_MARKERS):
        return PythonCodeSafety(blocked=True, block_reason=OS_DELETE_BLOCK_REASON)

    force_approval = deletes + [w for w in overwrites if w not in deletes]
    if force_approval:
        parts = "、".join(force_approval[:3])
        return PythonCodeSafety(
            always_require_approval=True,
            approval_note=f"脚本会{parts}，每次执行都需单独确认",
        )

    return PythonCodeSafety()


def analyze_python_script_file(path: str) -> PythonCodeSafety:
    """读取脚本文件并分析（仅小文件）。"""
    script = Path(path).expanduser()
    try:
        if not script.is_file():
            return PythonCodeSafety()
        if script.stat().st_size > 256_000:
            return PythonCodeSafety(
                always_require_approval=True,
                approval_note="脚本较大，可能包含文件删写操作，需单独确认",
            )
        return analyze_python_code(script.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return PythonCodeSafety()
