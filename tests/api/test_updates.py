from __future__ import annotations

from unittest.mock import patch

from friday.updates import _pick_download_url, check_for_updates, gitee_repo, github_repo
from friday.version import GITEE_REPO, GITHUB_REPO, __version__, release_update_zip_name, release_zip_name


def test_github_repo_default():
    assert github_repo() == GITHUB_REPO
    assert "/" in github_repo()
    assert "Friday-WeChat-Windows-AI-Butler" in GITHUB_REPO
    assert "Zero-barrier" not in GITHUB_REPO


def test_gitee_repo_default():
    assert gitee_repo() == GITEE_REPO


def test_release_zip_name_matches_version():
    assert release_zip_name() == f"Friday-Windows-{__version__}.zip"
    assert release_zip_name("1.0.0") == "Friday-Windows-1.0.0.zip"
    assert release_update_zip_name() == f"Friday-Update-{__version__}.zip"
    assert release_update_zip_name("1.0.0") == "Friday-Update-1.0.0.zip"


def test_pick_download_prefers_update_zip_over_windows_zip():
    url = _pick_download_url(
        {
            "html_url": "https://gitee.com/o/r/releases/tag/v1",
            "assets": [
                {"name": "Friday-Windows-1.2.4.zip", "browser_download_url": "https://x/win.zip"},
                {"name": "Friday-Update-1.2.4.zip", "browser_download_url": "https://x/update.zip"},
            ],
        }
    )
    assert url == "https://x/update.zip"


def test_pick_download_prefers_windows_zip():
    url = _pick_download_url(
        {
            "html_url": "https://github.com/o/r/releases/tag/v1",
            "assets": [
                {"name": "notes.txt", "browser_download_url": "https://x/notes.txt"},
                {"name": "other.zip", "browser_download_url": "https://x/other.zip"},
                {"name": "Friday-Windows-1.2.4.zip", "browser_download_url": "https://x/win.zip"},
            ],
        }
    )
    assert url == "https://x/win.zip"


def test_check_updates_github_only(monkeypatch):
    monkeypatch.setenv("FRIDAY_UPDATE_SOURCE", "github")
    monkeypatch.delenv("FRIDAY_GITHUB_REPO", raising=False)
    payload = {
        "tag_name": "v9.9.9",
        "body": "fix",
        "html_url": "https://github.com/o/r/releases/tag/v9.9.9",
        "assets": [{"name": "Friday-Windows-9.9.9.zip", "browser_download_url": "https://x/a.zip"}],
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
    assert info.latest == "9.9.9"
    assert info.download_url == "https://x/a.zip"


def test_check_updates_prefers_gitee(monkeypatch):
    monkeypatch.setenv("FRIDAY_UPDATE_SOURCE", "auto")
    gitee_payload = {
        "tag_name": "v1.0.4",
        "body": "gitee",
        "html_url": "https://gitee.com/o/r/releases/tag/v1.0.3",
        "assets": [{"name": "Friday-Windows-1.0.4.zip", "browser_download_url": "https://gitee/x.zip"}],
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
