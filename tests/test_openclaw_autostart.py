from __future__ import annotations

import sys
from unittest.mock import patch

from friday.openclaw_autostart import openclaw_autostart_status, set_openclaw_autostart_enabled


def test_openclaw_autostart_non_windows():
    with patch.object(sys, "platform", "linux"):
        status = openclaw_autostart_status()
        assert status["available"] is False


def test_set_openclaw_autostart_disable():
    with patch("friday.openclaw_autostart._remove_autostart_files"), patch(
        "friday.openclaw_autostart.openclaw_autostart_status",
        return_value={"ok": True, "enabled": False, "available": True, "detail": ""},
    ):
        result = set_openclaw_autostart_enabled(False)
        assert result["enabled"] is False
