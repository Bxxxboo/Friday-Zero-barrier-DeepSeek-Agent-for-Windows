from __future__ import annotations

from friday.edition import (
    appdata_folder_name,
    default_workspace_name,
    display_version,
    instance_port,
    openclaw_gateway_port,
    window_title,
)
from friday.paths import get_appdata_dir
from friday.version import __dev_version__, __version__


def test_edition_constants():
    assert window_title() == "星期五"
    assert appdata_folder_name() == "Friday"
    assert default_workspace_name() == "星期五"
    assert openclaw_gateway_port() == 18789
    assert instance_port() == 58765
    assert display_version(__version__) == __version__
    path = get_appdata_dir()
    assert path.name == "Friday"


def test_edition_dev_mode(monkeypatch):
    monkeypatch.setenv("FRIDAY_DEV", "1")
    assert window_title() == "星期五（测试版）"
    assert instance_port() == 58766
    assert display_version(__version__) == __dev_version__


def test_dev_version_tracks_release():
    assert __dev_version__ == f"{__version__}-dev"
