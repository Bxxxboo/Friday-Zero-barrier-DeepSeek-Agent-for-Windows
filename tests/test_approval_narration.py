from unittest.mock import patch

from friday.approval_descriptions import GENERIC_APPROVAL_PLAIN
from friday.approval_narration import (
    build_approval_preview,
    build_approval_template_copy,
    build_approval_user_copy,
    enrich_approval_summary_async,
    is_generic_approval_plain,
    narrate_approval,
)
from friday.safety import PendingAction, RiskLevel


def test_is_generic_approval_plain():
    assert is_generic_approval_plain(GENERIC_APPROVAL_PLAIN)
    assert not is_generic_approval_plain("删除桌面上的 test.txt")


def test_build_approval_user_copy_returns_template_immediately():
    action = PendingAction(
        tool_name="run_powershell",
        arguments={"command": "Remove-Item C:\\Users\\me\\Desktop\\test.txt"},
        summary="",
        risk=RiskLevel.EXEC,
    )
    narrated = "准备删除你桌面上的 test.txt 文件。"
    with patch("friday.approval_narration.narrate_approval", return_value=narrated):
        plain, preview = build_approval_user_copy(action)
    assert plain != narrated
    assert plain != GENERIC_APPROVAL_PLAIN
    assert preview


def test_build_approval_preview_uses_download_summary():
    action = PendingAction(
        tool_name="download_file",
        arguments={
            "url": "https://example.com/app.exe",
            "destination": "C:/Users/me/Downloads/app.exe",
        },
        summary="",
        risk=RiskLevel.WRITE,
    )
    with patch(
        "friday.approval_narration.summarize_preview",
        return_value="下载文件\n来源: example.com\n链接: https://example.com/app.exe",
    ):
        preview = build_approval_preview(action)
    assert "example.com" in preview


def test_build_approval_template_copy_falls_back_to_generic():
    action = PendingAction(
        tool_name="unknown_tool",
        arguments={},
        summary="",
        risk=RiskLevel.EXEC,
    )
    plain, preview = build_approval_template_copy(action)
    assert plain == GENERIC_APPROVAL_PLAIN
    assert preview == ""


def test_enrich_approval_summary_async_calls_back_when_narrated_differs():
    action = PendingAction(
        tool_name="run_powershell",
        arguments={"command": "echo hi"},
        summary="",
        risk=RiskLevel.EXEC,
        user_goal="测试一下",
        assistant_note="",
    )
    narrated = "准备在你电脑上运行一条简单命令，输出 hello 做连通性测试。"
    received: list[str] = []

    class _Settings:
        api_ready = True
        api_key = "sk-test"
        base_url = "https://api.example.com/v1"
        model = "test"

    with patch("friday.approval_narration.narrate_approval", return_value=narrated):
        enrich_approval_summary_async(
            action,
            settings=_Settings(),
            on_narrated=received.append,
        )
        import time

        deadline = time.monotonic() + 2.0
        while not received and time.monotonic() < deadline:
            time.sleep(0.02)

    assert received == [narrated]


def test_narrate_approval_returns_model_text(monkeypatch):
    action = PendingAction(
        tool_name="run_powershell",
        arguments={"command": "Get-ChildItem $env:USERPROFILE\\Downloads"},
        summary="",
        risk=RiskLevel.EXEC,
        user_goal="看看下载文件夹有什么",
        assistant_note="",
    )

    class _Msg:
        content = "准备列出你「下载」文件夹里的文件清单，供你确认后再删除。"

    class _Choice:
        message = _Msg()

    class _Response:
        choices = [_Choice()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _Response()

    monkeypatch.setattr(
        "friday.api_connect.build_openai_client",
        lambda *a, **k: _Client(),
    )

    class _Settings:
        api_ready = True
        api_key = "k"
        base_url = "https://example.com"
        model = "test"

    text = narrate_approval(action, settings=_Settings())
    assert "下载" in text
    assert not is_generic_approval_plain(text)
