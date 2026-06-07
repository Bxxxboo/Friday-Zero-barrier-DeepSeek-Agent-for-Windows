from __future__ import annotations

from unittest.mock import patch

from friday.updates import _pick_download_url, check_for_updates, gitee_repo, github_repo
from friday.version import GITEE_REPO, GITHUB_REPO


def test_github_repo_default():
    assert github_repo() == GITHUB_REPO
    assert "/" in github_repo()


def test_gitee_repo_default():
    assert gitee_repo() == GITEE_REPO


def test_pick_download_prefers_windows_zip():
    url = _pick_download_url(
        {
            "html_url": "https://github.com/o/r/releases/tag/v1",
            "assets": [
                {"name": "notes.txt", "browser_download_url": "https://x/notes.txt"},
                {"name": "other.zip", "browser_download_url": "https://x/other.zip"},
                {"name": "Friday-Windows.zip", "browser_download_url": "https://x/win.zip"},
            ],
        }
    )
    assert url == "https://x/win.zip"


def test_check_updates_github_only(monkeypatch):
    monkeypatch.setenv("FRIDAY_UPDATE_SOURCE", "github")
    monkeypatch.delenv("FRIDAY_GITHUB_REPO", raising=False)
    payload = {
        "tag_name": "v1.2.0",
        "body": "fix",
        "html_url": "https://github.com/o/r/releases/tag/v1.2.0",
        "assets": [{"name": "Friday-Windows.zip", "browser_download_url": "https://x/a.zip"}],
    }

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            import json

            return json.dumps(payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        info = check_for_updates()

    assert info.checked is True
    assert info.source_repo == GITHUB_REPO
    assert info.source_kind == "github"
    assert info.update_available is True
    assert info.latest == "1.2.0"
    assert info.download_url == "https://x/a.zip"


def test_check_updates_prefers_gitee(monkeypatch):
    monkeypatch.setenv("FRIDAY_UPDATE_SOURCE", "auto")
    gitee_payload = {
        "tag_name": "v1.0.4",
        "body": "gitee",
        "html_url": "https://gitee.com/o/r/releases/tag/v1.0.3",
        "assets": [{"name": "Friday-Windows.zip", "browser_download_url": "https://gitee/x.zip"}],
    }

    def fake_urlopen(request, timeout=12.0):
        url = request.full_url
        payload = gitee_payload if "gitee.com" in url else {"tag_name": "v9.9.9"}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                import json

                return json.dumps(payload).encode("utf-8")

        return FakeResp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        info = check_for_updates()

    assert info.source_kind == "gitee"
    assert info.latest == "1.0.4"
    assert info.download_url == "https://gitee/x.zip"
