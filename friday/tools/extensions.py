"""扩展工具 —— 从 GitHub 安装 skill / rule 插件包。"""

from __future__ import annotations

from friday.plugins import (
    format_plugin_catalog,
    get_plugin,
    install_plugin,
    list_plugins,
    resolve_plugin_source,
    uninstall_plugin,
)
from friday.tools._decorators import register_tool


def _catalog_plugin_id(source: str) -> str | None:
    from friday.plugins import plugin_catalog

    for item in plugin_catalog():
        if item.get("source") == source:
            return item.get("id")
    if source.startswith("skill:"):
        tail = source.split("/")[-1]
        return tail or None
    return None


@register_tool(
    name="install_friday_plugin",
    description=(
        "安装星期五扩展插件（技能+规则）。安装前先 list_friday_plugins 检查是否已存在。"
        "source 格式："
        "① skill:owner/repo/skill目录（GitHub 上的 Agent Skill）；"
        "② owner/repo 或 owner/repo@分支（仓库根目录需 friday-plugin.json）；"
        "③ local:插件id（非内置扩展目录）。"
        "图片视觉桥接、storage-analyzer 已内置，无需安装。"
        "失败时不要猜测编造仓库名连续重试，应 list_plugin_catalog 查看说明。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "插件来源，如 skill:owner/repo/skill目录 或 owner/repo",
            },
        },
        "required": ["source"],
    },
)
def install_friday_plugin(source: str) -> str:
    from friday.bundled import bundled_already_message, resolve_bundled_source

    raw = source.strip()
    bundled_id = resolve_bundled_source(raw)
    if bundled_id:
        return bundled_already_message(bundled_id)

    resolved = resolve_plugin_source(raw)
    plugin_id = _catalog_plugin_id(resolved)
    if plugin_id:
        existing = get_plugin(plugin_id)
        if existing:
            return (
                f"插件「{existing['name']}」已安装（v{existing['version']}，"
                f"{existing['skill_count']} 技能 / {existing['rule_count']} 规则）。"
                f"来源 {existing.get('source', '未知')}。无需重复安装，可直接使用欢迎页技能。"
            )
    try:
        entry = install_plugin(resolved)
    except ValueError as exc:
        hint = ""
        if "friday-plugin.json" in str(exc):
            hint = (
                " 若这是 GitHub 上的 Agent Skill 目录，请用 skill:owner/repo/目录名 格式，"
                "或 list_plugin_catalog 查看推荐来源。"
            )
        return f"插件安装失败: {exc}{hint}"
    if resolved != raw:
        via = f"（已从「{raw}」解析为 {resolved}）"
    else:
        via = ""
    return (
        f"已安装插件「{entry['name']}」v{entry['version']}{via}："
        f"{entry['skill_count']} 个技能、{entry['rule_count']} 条规则。"
        f"技能会出现在欢迎页与 / 补全，规则将在下一轮对话生效。"
    )


@register_tool(
    name="list_friday_plugins",
    description=(
        "列出已安装的星期五扩展插件。"
        "用户问插件/技能/规则时，须与 list_plugin_catalog 在同一轮一并调用，不要单独调用后再开下一轮。"
    ),
    parameters={"type": "object", "properties": {}},
)
def list_friday_plugins() -> str:
    plugins = list_plugins()
    if not plugins:
        return "尚未安装任何插件。可先 list_plugin_catalog 查看推荐，或在设置 → 扩展 → 插件 安装。"
    lines = [f"共 {len(plugins)} 个插件："]
    for item in plugins:
        lines.append(
            f"- {item['name']} v{item['version']} ({item['id']})："
            f"{item['skill_count']} 技能 / {item['rule_count']} 规则，来源 {item.get('source', '未知')}"
        )
    return "\n".join(lines)


@register_tool(
    name="list_plugin_catalog",
    description=(
        "列出星期五内置推荐的扩展插件及正确安装来源。"
        "用户问插件/技能/规则/GitHub skill 时，须与 list_friday_plugins 在同一轮一并调用。"
    ),
    parameters={"type": "object", "properties": {}},
)
def list_plugin_catalog() -> str:
    return format_plugin_catalog()


@register_tool(
    name="uninstall_friday_plugin",
    description="卸载已安装的星期五扩展插件（会移除其技能与规则）",
    parameters={
        "type": "object",
        "properties": {
            "plugin_id": {
                "type": "string",
                "description": "插件 ID，如 demo-office",
            },
        },
        "required": ["plugin_id"],
    },
)
def uninstall_friday_plugin(plugin_id: str) -> str:
    if uninstall_plugin(plugin_id.strip()):
        return f"已卸载插件「{plugin_id}」。"
    return f"未找到插件「{plugin_id}」。"
