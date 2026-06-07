from __future__ import annotations

from friday.changelog import (
    changelog_payload,
    has_unseen,
    load_entries,
    parse_version,
    unseen_entries,
)


def test_load_entries_has_110():
    entries = load_entries()
    versions = [e["version"] for e in entries]
    assert "1.1.0" in versions


def test_parse_version():
    assert parse_version("1.1.0") == (1, 1, 0)
    assert parse_version("v1.0.4.0") == (1, 0, 4, 0)


def test_unseen_after_upgrade():
    unseen = unseen_entries("1.0.4", "1.1.0")
    assert len(unseen) == 1
    assert unseen[0]["version"] == "1.1.0"


def test_unseen_none_when_ack_current():
    assert not has_unseen("1.1.0", "1.1.0")
    assert unseen_entries("1.1.0", "1.1.0") == []


def test_unseen_first_install():
    unseen = unseen_entries("", "1.1.0")
    assert any(e["version"] == "1.1.0" for e in unseen)


def test_changelog_payload():
    payload = changelog_payload("1.0.4", "1.1.0")
    assert payload["current"] == "1.1.0"
    assert payload["has_unseen"] is True
    assert payload["unseen"][0]["version"] == "1.1.0"
    assert len(payload["entries"]) >= 1
