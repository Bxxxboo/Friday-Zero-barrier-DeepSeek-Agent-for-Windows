"""首次引导完成状态测试。"""

from friday.portability import CURRENT_SETTINGS_SCHEMA_VERSION
from friday.storage import UserSettings, _migrate_settings_schema


def test_migrate_v6_marks_onboarding_completed_for_configured_user():
    settings = UserSettings(
        api_key="sk-test-key-123456",
        workspace="D:/Documents/Friday",
        onboarding_completed=False,
    )
    migrated = _migrate_settings_schema(settings, 5)
    assert migrated.onboarding_completed is True
    assert CURRENT_SETTINGS_SCHEMA_VERSION == 7


def test_migrate_v6_leaves_fresh_user_unmarked():
    settings = UserSettings(onboarding_completed=False)
    migrated = _migrate_settings_schema(settings, 5)
    assert migrated.onboarding_completed is False
