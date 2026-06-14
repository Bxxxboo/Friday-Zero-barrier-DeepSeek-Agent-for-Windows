from __future__ import annotations

from pathlib import Path

import pytest

from friday.weixin.bridge import (
    DESKTOP_CONTINUE_HINT,
    FILE_SEND_FAIL_HINT,
    IMAGE_SEND_FAIL_HINT,
    MAX_REPLY_CHARS,
    _make_weixin_progress_handler,
    _truncate_reply,
)
from friday.weixin.client import WeixinAccount
from friday.weixin.media import aes_ecb_padded_size, encrypt_aes_ecb
from friday.storage import UserSettings


def test_truncate_reply_short_unchanged():
    assert _truncate_reply("你好") == "你好"


def test_truncate_reply_empty_default():
    assert _truncate_reply("") == "（已完成，无文字回复）"


def test_truncate_reply_includes_desktop_hint():
    body = "x" * (MAX_REPLY_CHARS + 500)
    result = _truncate_reply(body)
    assert len(result) <= MAX_REPLY_CHARS
    assert result.endswith(DESKTOP_CONTINUE_HINT)
    assert DESKTOP_CONTINUE_HINT in result


def test_aes_ecb_padded_size():
    assert aes_ecb_padded_size(0) == 16
    assert aes_ecb_padded_size(16) == 32
    assert aes_ecb_padded_size(17) == 32


def test_encrypt_aes_ecb_length():
    key = b"\x00" * 16
    ct = encrypt_aes_ecb(b"hello world 1234", key)
    assert len(ct) == 32


def test_image_generated_handler_sends_image(monkeypatch, tmp_path: Path):
    sent_images: list[str] = []

    def fake_send_image(account, *, peer_id, file_path, fallback_token="", cdn_base_url=None, caption=""):
        sent_images.append(file_path)

    monkeypatch.setattr("friday.weixin.bridge.send_peer_image", fake_send_image)
    monkeypatch.setattr(
        "friday.weixin.deliverables.resolve_image_path",
        lambda path, settings: tmp_path / "out.png",
    )
    (tmp_path / "out.png").write_bytes(b"png")
    ws = str(tmp_path).replace("\\", "/")
    settings = UserSettings(workspace=ws)
    monkeypatch.setattr("friday.artifacts.load_settings", lambda: settings)

    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=settings,
        initial_done_keys=set(),
    )
    handler("image_generated", {"path": "生成的图片/demo.png"})
    assert len(sent_images) == 1
    assert sent_images[0].endswith("out.png")

    from friday.artifacts import _load_index

    items = _load_index(settings)
    row = next(i for i in items if i["path"].endswith("out.png"))
    assert row.get("weixin_sent_at")


def test_image_generated_handler_fallback_on_failure(monkeypatch):
    sent_text: list[str] = []

    def fail_send_image(*_a, **_k):
        raise RuntimeError("cdn down")

    def fake_send_text(account, *, peer_id, text, fallback_token=""):
        sent_text.append(text)

    monkeypatch.setattr("friday.weixin.bridge.send_peer_image", fail_send_image)
    monkeypatch.setattr("friday.weixin.bridge.send_peer_text", fake_send_text)
    monkeypatch.setattr(
        "friday.weixin.deliverables.resolve_image_path",
        lambda path, settings: Path(path),
    )

    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=UserSettings(),
        initial_done_keys=set(),
    )
    handler("image_generated", {"path": "x.png"})
    assert sent_text == [IMAGE_SEND_FAIL_HINT]


def test_image_generated_handler_ignores_empty_path(monkeypatch):
    called = {"image": False, "text": False}

    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_image",
        lambda *_a, **_k: called.__setitem__("image", True),
    )
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda *_a, **_k: called.__setitem__("text", True),
    )

    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=UserSettings(),
        initial_done_keys=set(),
    )
    handler("image_generated", {"path": ""})
    assert called == {"image": False, "text": False}


def test_file_generated_handler_sends_file(monkeypatch, tmp_path: Path):
    sent: list[tuple[str, str]] = []

    def fake_send_file(account, *, peer_id, file_path, fallback_token="", cdn_base_url=None, caption=""):
        sent.append((file_path, caption))

    monkeypatch.setattr("friday.weixin.bridge.send_peer_file", fake_send_file)
    monkeypatch.setattr(
        "friday.weixin.deliverables.resolve_attachment_path",
        lambda path, settings: tmp_path / "report.docx",
    )
    (tmp_path / "report.docx").write_bytes(b"doc")
    ws = str(tmp_path).replace("\\", "/")
    settings = UserSettings(workspace=ws)
    monkeypatch.setattr("friday.artifacts.load_settings", lambda: settings)

    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=settings,
        initial_done_keys=set(),
    )
    handler("file_generated", {"path": "report.docx", "kind": "document"})
    assert len(sent) == 1
    assert sent[0][0].endswith("report.docx")
    assert "report.docx" in sent[0][1]

    from friday.artifacts import _load_index

    items = _load_index(settings)
    row = next(i for i in items if i["path"].endswith("report.docx"))
    assert row.get("weixin_sent_at")


def test_file_generated_respects_disabled_setting(monkeypatch):
    sent: list[str] = []

    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_file",
        lambda *_a, **_k: sent.append("file"),
    )
    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=UserSettings(weixin_deliver_files_enabled=False),
        initial_done_keys=set(),
    )
    handler("file_generated", {"path": "a.docx"})
    assert sent == []


def test_file_generated_handler_fallback_on_failure(monkeypatch, tmp_path: Path):
    sent_text: list[str] = []

    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_file",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("cdn")),
    )
    monkeypatch.setattr(
        "friday.weixin.bridge.send_peer_text",
        lambda account, *, peer_id, text, fallback_token="": sent_text.append(text),
    )
    monkeypatch.setattr(
        "friday.weixin.deliverables.resolve_attachment_path",
        lambda path, settings: tmp_path / "a.docx",
    )
    (tmp_path / "a.docx").write_bytes(b"x")
    ws = str(tmp_path).replace("\\", "/")
    settings = UserSettings(workspace=ws)
    monkeypatch.setattr("friday.artifacts.load_settings", lambda: settings)

    account = WeixinAccount(account_id="a1", token="t", base_url="http://127.0.0.1")
    handler = _make_weixin_progress_handler(
        peer_id="peer1",
        account=account,
        settings=settings,
        initial_done_keys=set(),
    )
    handler("file_generated", {"path": "a.docx"})
    assert sent_text == [FILE_SEND_FAIL_HINT]

    from friday.artifacts import _load_index

    assert not _load_index(settings)
