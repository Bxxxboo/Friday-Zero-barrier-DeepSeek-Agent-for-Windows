"""MCP 工具桥接（execute_tool 委托 + 工具 schema 合并）。"""

from __future__ import annotations

import re
from typing import Any

from friday.logging_config import get_logger
from friday.mcp_client import get_mcp_client, list_enabled_servers

_log = get_logger("mcp.tools")

_TOOL_PREFIX = "mcp_"


def _safe_suffix(server_id: str, tool_name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", f"{server_id}_{tool_name}").strip("_")
    return base[:48] or "tool"


def mcp_tool_definitions() -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    for server in list_enabled_servers():
        client = get_mcp_client(server.id)
        if client is None:
            continue
        try:
            tools = client.list_tools()
        except Exception as exc:  # noqa: BLE001
            _log.warning("MCP 列举工具失败 | server=%s | %s", server.name, exc)
            continue
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            friday_name = f"{_TOOL_PREFIX}{_safe_suffix(server.id, name)}"
            schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {
                "type": "object",
                "properties": {},
            }
            defs.append({
                "type": "function",
                "function": {
                    "name": friday_name,
                    "description": f"[MCP:{server.name}] {tool.get('description', name)}",
                    "parameters": schema,
                },
            })
    return defs


def execute_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str | None:
    if not tool_name.startswith(_TOOL_PREFIX):
        return None
    for server in list_enabled_servers():
        client = get_mcp_client(server.id)
        if client is None:
            continue
        try:
            tools = client.list_tools()
        except Exception:
            continue
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            remote = str(tool.get("name", ""))
            friday_name = f"{_TOOL_PREFIX}{_safe_suffix(server.id, remote)}"
            if friday_name != tool_name:
                continue
            try:
                return client.call_tool(remote, arguments)
            except Exception as exc:  # noqa: BLE001
                return f"MCP 调用失败 ({server.name}/{remote}): {exc}"
    return f"未找到 MCP 工具: {tool_name}"
