from __future__ import annotations

import json
from pathlib import Path

import pytest

from friday.bundled import BUNDLED_PLUGIN_IDS, migrate_legacy_bundled_plugins
from friday.plugins import (
    format_plugin_catalog,
    install_github_skill,
    install_local_plugin,
    install_plugin,
    install_plugin_from_manifest,
    list_plugins,
    parse_github_skill_source,
    parse_github_source,
    plugin_catalog,
    resolve_plugin_source,
    uninstall_plugin,
)
from friday.rules import active_rules_prompt, create_rule, delete_rule, get_rule, list_rules, update_rule
from friday.skills import delete_skill, get_skill, list_skills, update_skill


_DEMO_MANIFEST = {
    "id": "my-custom-plugin",
    "name": "自定义测试插件",
    "version": "1.0.0",
    "description": "测试插件",
    "skills": [
        {
            "id": "standup",
            "label": "站会摘要",
            "icon": "🗣️",
            "category": "plugin",
            "prompt": "写站会摘要",
        }
    ],
    "rules": [
        {
            "id": "concise",
            "title": "简洁回复",
            "content": "回答要简洁。",
            "enabled": True,
            "always_apply": True,
        }
    ],
}


def test_parse_github_source_variants():
    assert parse_github_source("octocat/repo") == ("octocat", "repo", "main")
    assert parse_github_source("octocat/repo@dev") == ("octocat", "repo", "dev")
    assert parse_github_source("https://github.com/octocat/repo") == ("octocat", "repo", "main")
    assert parse_github_source("https://github.com/octocat/repo/tree/main") == ("octocat", "repo", "main")


def test_create_rule_and_prompt(tmp_appdata):
    create_rule({"title": "测试规则", "content": "始终用列表回答。"})
    rules = list_rules(for_ui=True)
    assert any(r["title"] == "测试规则" for r in rules)
    prompt = active_rules_prompt()
    assert "回复习惯" in prompt
    assert "测试规则" in prompt
    assert "始终用列表回答" in prompt


def test_builtin_rule_cannot_be_deleted(tmp_appdata):
    active_rules_prompt()
    builtin = next(r for r in list_rules(for_ui=True) if r.get("source") == "builtin")
    assert delete_rule(builtin["id"]) is False


def test_delete_plugin_rule(tmp_appdata):
    install_plugin_from_manifest(_DEMO_MANIFEST, source="local")
    rule = next(r for r in list_rules(for_ui=True) if r.get("source") == "plugin")
    assert delete_rule(rule["id"]) is True
    assert get_rule(rule["id"]) is None


def test_delete_plugin_skill(tmp_appdata):
    install_plugin_from_manifest(_DEMO_MANIFEST, source="local")
    skill = next(s for s in list_skills(include_disabled=True, for_ui=True) if s.get("source") == "plugin")
    assert delete_skill(skill["id"]) is True
    assert get_skill(skill["id"]) is None


def test_disable_rule_excludes_from_prompt(tmp_appdata):
    rule = create_rule({"title": "临时", "content": "内容", "always_apply": True})
    update_rule(rule["id"], {"enabled": False})
    assert "临时" not in active_rules_prompt()


def test_install_plugin_from_manifest(tmp_appdata):
    entry = install_plugin_from_manifest(_DEMO_MANIFEST, source="local")
    assert entry["id"] == "my-custom-plugin"
    assert entry["skill_count"] == 1
    assert entry["rule_count"] == 1

    plugins = list_plugins()
    assert len(plugins) == 1

    skills = list_skills(include_disabled=True, for_ui=True)
    assert any(s["id"] == "my-custom-plugin:standup" and s["source"] == "plugin" for s in skills)

    rules = list_rules(for_ui=True)
    assert any(r["id"] == "my-custom-plugin:concise" and r["source"] == "plugin" for r in rules)

    prompt = active_rules_prompt()
    assert "简洁回复" in prompt


def test_toggle_plugin_skill(tmp_appdata):
    install_plugin_from_manifest(_DEMO_MANIFEST, source="local")
    skill_id = "my-custom-plugin:standup"
    update_skill(skill_id, {"enabled": False})
    enabled = [s for s in list_skills(include_disabled=False, for_ui=True) if s["id"] == skill_id]
    assert enabled == []


def test_uninstall_plugin(tmp_appdata):
    install_plugin_from_manifest(_DEMO_MANIFEST, source="local")
    assert uninstall_plugin("my-custom-plugin")
    assert list_plugins() == []
    assert not any(s.get("plugin_id") == "my-custom-plugin" for s in list_skills(include_disabled=True, for_ui=True))
    assert not any(r.get("plugin_id") == "my-custom-plugin" for r in list_rules(for_ui=True))


def test_bundled_plugins_not_installable(tmp_appdata):
    for pid in BUNDLED_PLUGIN_IDS:
        with pytest.raises(ValueError, match="内置"):
            install_plugin(f"local:{pid}")
        with pytest.raises(ValueError, match="内置"):
            install_plugin(pid)


def test_bundled_plugins_hidden_from_ui(tmp_appdata):
    migrate_legacy_bundled_plugins()
    ui_rules = list_rules(for_ui=True)
    assert not any("图片必走视觉桥接" in r.get("title", "") for r in ui_rules)
    assert not any("存储分析只读" in r.get("title", "") for r in ui_rules)

    ui_skills = list_skills(include_disabled=True, for_ui=True)
    assert not any(s.get("label") == "存储分析" for s in ui_skills)
    assert not any(s.get("label") == "看懂截图" for s in ui_skills)


def test_bundled_rules_in_prompt(tmp_appdata):
    migrate_legacy_bundled_plugins()
    prompt = active_rules_prompt()
    assert "图片必走视觉桥接" in prompt
    assert "存储分析只读" in prompt
    assert "简洁回复" not in prompt
    assert "回复习惯" in prompt


def test_retired_concise_rule_removed(tmp_appdata):
    create_rule({"title": "简洁回复", "content": "旧规则", "always_apply": True})
    migrate_legacy_bundled_plugins()
    assert "简洁回复" not in active_rules_prompt()
    assert not any(r.get("title") == "简洁回复" for r in list_rules(for_ui=True))


def test_migrate_legacy_bundled_plugin_install(tmp_appdata):
    legacy = {
        "id": "other-pack",
        "name": "Other Pack",
        "version": "1.0.0",
        "description": "legacy",
        "skills": [{"id": "x", "label": "看懂截图", "icon": "👁️", "category": "plugin", "prompt": "test"}],
        "rules": [{"id": "r", "title": "图片必走视觉桥接", "content": "test", "enabled": True, "always_apply": True}],
    }
    install_plugin_from_manifest(legacy, source="local")
    assert any(s.get("plugin_id") == "other-pack" for s in list_skills(include_disabled=True, for_ui=True))

    # 模拟旧版 vision-bridge 插件残留
    from friday.plugins import _load_registry, _save_registry
    from friday.skills import upsert_plugin_skills

    registry = _load_registry()
    registry.append({
        "id": "vision-bridge",
        "name": "Vision Bridge",
        "version": "1.0.0",
        "description": "legacy",
        "source": "local:vision-bridge",
        "installed_at": 1.0,
        "updated_at": 1.0,
        "skill_count": 1,
        "rule_count": 1,
    })
    _save_registry(registry)
    upsert_plugin_skills("vision-bridge", legacy["skills"])

    migrate_legacy_bundled_plugins()

    assert not any(p.get("id") == "vision-bridge" for p in list_plugins())
    assert not any(s.get("plugin_id") == "vision-bridge" for s in list_skills(include_disabled=True, for_ui=True))
    assert "图片必走视觉桥接" in active_rules_prompt()


def test_plugin_catalog_empty():
    assert plugin_catalog() == []
    assert "已内置" in format_plugin_catalog()


def test_parse_github_skill_source():
    assert parse_github_skill_source("octocat/repo/my-skill") == (
        "octocat", "repo", "main", "my-skill",
    )
    assert parse_github_skill_source("octocat/repo@dev/my-skill") == (
        "octocat", "repo", "dev", "my-skill",
    )


def test_resolve_plugin_source_no_builtin_mapping():
    assert resolve_plugin_source("storage-analyzer") == "storage-analyzer"
    assert resolve_plugin_source("friday-ai/storage-analyzer") == "friday-ai/storage-analyzer"


def test_install_github_skill_storage_analyzer_blocked(tmp_appdata):
    """storage-analyzer 已内置，禁止再作为插件安装。"""
    with pytest.raises(ValueError, match="内置"):
        install_github_skill("KKKKhazix/khazix-skills/storage-analyzer")
