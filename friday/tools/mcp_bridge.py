"""MCP 工具桥接（execute_tool 委托 + 工具 schema 合并）。"""

from __future__ import annotations

import re
import time
from typing import Any

from friday.logging_config import get_logger
from friday.mcp_client import get_mcp_client, list_enabled_servers

_log = get_logger("mcp.tools")

_TOOL_PREFIX = "mcp_"
_MCP_TOOLS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_MCP_CACHE_TTL_OK = 300.0
_MCP_CACHE_TTL_FAIL = 60.0


def _safe_suffix(server_id: str, tool_name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", f"{server_id}_{tool_name}").strip("_")
    return base[:48] or "tool"


def _list_server_tools(server) -> list[dict[str, Any]]:
    now = time.time()
    cached = _MCP_TOOLS_CACHE.get(server.id)
    if cached is not None:
        age = now - cached[0]
        ttl = _MCP_CACHE_TTL_OK if cached[1] else _MCP_CACHE_TTL_FAIL
        if age < ttl:
            return list(cached[1])

    client = get_mcp_client(server.id)
    if client is None:
        _MCP_TOOLS_CACHE[server.id] = (now, [])
        return []
    try:
        tools = client.list_tools()
    except Exception as exc:  # noqa: BLE001
        _log.warning("MCP 列举工具失败 | server=%s | %s", server.name, exc)
        _MCP_TOOLS_CACHE[server.id] = (now, [])
        return []
    out = [t for t in tools if isinstance(t, dict)]
    _MCP_TOOLS_CACHE[server.id] = (now, out)
    return out


def mcp_tool_definitions() -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    for server in list_enabled_servers():
        tools = _list_server_tools(server)
        for tool in tools:
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
