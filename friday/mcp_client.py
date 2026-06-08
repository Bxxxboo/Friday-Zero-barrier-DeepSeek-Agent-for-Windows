"""MCP stdio 服务器配置与 JSON-RPC 客户端。"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir
from friday.portability import expand_config_path

_log = get_logger("mcp")

_CONFIG_FILE = "mcp_servers.json"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def mcp_config_path() -> Path:
    return get_appdata_dir() / _CONFIG_FILE


def default_mcp_config() -> dict[str, Any]:
    return {"version": 1, "servers": []}


def load_mcp_config() -> dict[str, Any]:
    data = load_json(mcp_config_path())
    if not isinstance(data, dict):
        return default_mcp_config()
    servers = data.get("servers")
    if not isinstance(servers, list):
        data["servers"] = []
    return data


def save_mcp_config(config: dict[str, Any]) -> None:
    atomic_write_json(mcp_config_path(), config)


@dataclass
class MCPServerConfig:
    id: str
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    cwd: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:10]),
            name=str(data.get("name") or "MCP Server"),
            command=str(data.get("command") or ""),
            args=[str(a) for a in (data.get("args") or [])],
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
            enabled=bool(data.get("enabled", True)),
            cwd=str(data.get("cwd") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "enabled": self.enabled,
            "cwd": self.cwd,
        }

    def resolved_command(self) -> str:
        return expand_config_path(self.command)


class MCPStdioClient:
    """最小 MCP JSON-RPC stdio 客户端（initialize + tools/list + tools/call）。"""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._initialized = False

    def _start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        cmd = self.config.resolved_command()
        if not cmd:
            raise RuntimeError("MCP command 为空")
        args = [cmd, *self.config.args]
        cwd = expand_config_path(self.config.cwd) if self.config.cwd else None
        cwd_path = Path(cwd) if cwd else None
        env = {**dict(**__import__("os").environ), **self.config.env}
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd_path) if cwd_path and cwd_path.is_dir() else None,
            creationflags=_CREATE_NO_WINDOW if __import__("os").name == "nt" else 0,
        )

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            self._start()
            assert self._proc and self._proc.stdin and self._proc.stdout
            req_id = self._next_id
            self._next_id += 1
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
            if params is not None:
                payload["params"] = params
            line = json.dumps(payload, ensure_ascii=False)
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            while True:
                raw = self._proc.stdout.readline()
                if not raw:
                    raise RuntimeError("MCP 进程无响应")
                data = json.loads(raw)
                if data.get("id") != req_id:
                    continue
                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(str(err.get("message") or err))
                return data.get("result")

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        assert self._proc and self._proc.stdin
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def initialize(self) -> None:
        if self._initialized:
            return
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "friday", "version": "1.2.0"},
            },
        )
        self._notify("notifications/initialized")
        self._initialized = True

    def list_tools(self) -> list[dict[str, Any]]:
        self.initialize()
        result = self._request("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else []
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self.initialize()
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        if not isinstance(result, dict):
            return str(result)
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "\n".join(parts).strip() or json.dumps(result, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass
        self._proc = None
        self._initialized = False


_clients: dict[str, MCPStdioClient] = {}


def get_mcp_client(server_id: str) -> MCPStdioClient | None:
    config = load_mcp_config()
    for raw in config.get("servers") or []:
        if not isinstance(raw, dict):
            continue
        item = MCPServerConfig.from_dict(raw)
        if item.id == server_id and item.enabled:
            if server_id not in _clients:
                _clients[server_id] = MCPStdioClient(item)
            return _clients[server_id]
    return None


def list_enabled_servers() -> list[MCPServerConfig]:
    config = load_mcp_config()
    out: list[MCPServerConfig] = []
    for raw in config.get("servers") or []:
        if not isinstance(raw, dict):
            continue
        item = MCPServerConfig.from_dict(raw)
        if item.enabled and item.command.strip():
            out.append(item)
    return out
