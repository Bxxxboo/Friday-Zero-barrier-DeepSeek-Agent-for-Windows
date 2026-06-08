from __future__ import annotations

from unittest.mock import patch

import pytest


def test_autostart_status_non_windows():
    with patch("friday.autostart.sys.platform", "linux"):
        from friday.autostart import autostart_status

        status = autostart_status()
        assert status["available"] is False
        assert status["enabled"] is False


def test_resolve_launch_spec_dev_layout():
    with patch("friday.autostart.sys.platform", "win32"):
        with patch("friday.autostart.is_frozen", return_value=False):
            from friday.autostart import resolve_launch_spec

            exe, args, mode, err = resolve_launch_spec()
            if err:
                pytest.skip(err)
            assert mode == "dev"
            assert exe.endswith("pythonw.exe")
            assert args.endswith('run.py"')
