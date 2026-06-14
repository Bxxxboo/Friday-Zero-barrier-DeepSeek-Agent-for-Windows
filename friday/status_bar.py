"""状态栏快照 — 从 server 拆出。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from friday.storage import load_settings, resolved_workspace


SessionContextLoader = Callable[
    [str],
    tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None],
]


async def build_status_bar_snapshot(
    *,
    session_id: str = "",
    cached_only: bool = False,
    session_usage: Callable[[str], dict[str, Any]] | None = None,
    session_context: SessionContextLoader | None = None,
) -> dict[str, object]:
    from friday.image_gen import image_gen_ready
    from friday.python_env import python_ready_light
    from friday.schedules import list_schedules
    from friday.vision import vision_ready

    cfg = load_settings()
    workspace = resolved_workspace(cfg)
    ws_path = Path(workspace)
    ws_label = ws_path.name or str(ws_path)

    usage = (session_usage or (lambda _sid: {}))(session_id.strip())
    prompt_tokens = int(usage.get("tokens_prompt", 0) or 0)
    completion_tokens = int(usage.get("tokens_completion", 0) or 0)

    vision_on = bool(cfg.vision_enabled)
    image_gen_on = bool(cfg.image_gen_enabled)

    from friday.api_connect import (
        read_cached_service_status,
        test_image_gen_service,
        test_llm_service,
        test_vision_service,
    )

    llm_configured = cfg.api_ready
    vision_configured = bool(vision_on and vision_ready(cfg))
    image_gen_configured = bool(image_gen_on and image_gen_ready(cfg))

    async def _resolve_llm() -> tuple[bool, str, bool]:
        if not llm_configured:
            return False, "未配置 API Key", False
        if cached_only:
            cached = read_cached_service_status("llm", cfg)
            if cached is not None:
                return cached[0], cached[1], False
            return False, "", True
        cached = read_cached_service_status("llm", cfg)
        if cached is not None:
            return cached[0], cached[1], False
        online, detail = await asyncio.to_thread(test_llm_service, cfg)
        short = (detail or "").split("\n")[0].strip() or detail
        return online, short, False

    async def _resolve_vision() -> tuple[bool, str, bool]:
        if not vision_on:
            return False, "未启用", False
        if not vision_configured:
            return False, "未配置", False
        if cached_only:
            cached = read_cached_service_status("vision", cfg)
            if cached is not None:
                return cached[0], cached[1], False
            return False, "", True
        cached = read_cached_service_status("vision", cfg)
        if cached is not None:
            return cached[0], cached[1], False
        result = await asyncio.to_thread(test_vision_service, cfg)
        if result is None:
            return False, "未配置", False
        online, detail = result
        short = (detail or "").split("\n")[0].strip() or detail
        return online, short, False

    async def _resolve_image_gen() -> tuple[bool, str, bool]:
        if not image_gen_on:
            return False, "未启用", False
        if not image_gen_configured:
            return False, "未配置", False
        if cached_only:
            cached = read_cached_service_status("image_gen", cfg)
            if cached is not None:
                return cached[0], cached[1], False
            return False, "", True
        cached = read_cached_service_status("image_gen", cfg)
        if cached is not None:
            return cached[0], cached[1], False
        result = await asyncio.to_thread(test_image_gen_service, cfg)
        if result is None:
            return False, "未配置", False
        online, detail = result
        short = (detail or "").split("\n")[0].strip() or detail
        return online, short, False

    def _resolve_gateway_sync() -> tuple[bool, bool, bool, str, bool]:
        bridge_on = bool(getattr(cfg, "weixin_bridge_enabled", True))
        if not bridge_on:
            return False, False, False, "微信桥接已关闭", False

        from friday.health_check import _gateway_port
        from friday.weixin.client import discover_account
        from friday.weixin.gateway import cli_available, probe_gateway
        from friday.weixin.sessions import has_weixin_mappings

        port = _gateway_port()
        cli_ok = cli_available()
        account_ready = discover_account() is not None
        remote_active = has_weixin_mappings()
        channel_ready = account_ready or remote_active
        running = probe_gateway(port=port, timeout_sec=1.5)

        if not cli_ok and not channel_ready:
            return True, False, False, "OpenClaw 未安装，请到 设置 → 微信桥接 一键配置", False

        if channel_ready:
            if running:
                return True, True, True, "Gateway 运行中", False
            if account_ready:
                return True, True, True, "微信通道已登录", False
            return True, True, True, "微信 remote 通道", False

        if not running:
            suffix = f"（端口 {port}）" if port else ""
            return True, True, False, f"Gateway 未响应{suffix}，请到 设置 → 微信桥接 启动", False
        return True, True, True, "Gateway 运行中", False

    async def _resolve_gateway() -> tuple[bool, bool, bool, str, bool]:
        return await asyncio.to_thread(_resolve_gateway_sync)

    (llm_online, llm_reach_detail, llm_checking), (vision_online, vision_reach_detail, vision_checking), (
        image_gen_online,
        image_gen_reach_detail,
        image_gen_checking,
    ), (gateway_enabled, gateway_configured, gateway_online, gateway_reach_detail, gateway_checking) = await asyncio.gather(
        _resolve_llm(),
        _resolve_vision(),
        _resolve_image_gen(),
        _resolve_gateway(),
    )

    from friday.brain import compute_context_meter

    sid = session_id.strip()

    def _compute_meter() -> dict[str, int | float]:
        ctx_messages: list[dict[str, Any]] | None = None
        ctx_tools: list[dict[str, Any]] | None = None
        if sid and session_context is not None:
            ctx_messages, ctx_tools = session_context(sid)
        return compute_context_meter(
            cfg,
            ctx_messages,
            tool_definitions=ctx_tools,
            session_id=sid,
        )

    context_meter = await asyncio.to_thread(_compute_meter)

    return {
        "api_online": llm_online,
        "api_configured": llm_configured,
        "api_reach_detail": llm_reach_detail,
        "api_checking": llm_checking,
        "vision_online": vision_online,
        "vision_configured": vision_configured,
        "vision_reach_detail": vision_reach_detail,
        "vision_checking": vision_checking,
        "vision_enabled": vision_on,
        "image_gen_online": image_gen_online,
        "image_gen_configured": image_gen_configured,
        "image_gen_reach_detail": image_gen_reach_detail,
        "image_gen_checking": image_gen_checking,
        "image_gen_enabled": image_gen_on,
        "gateway_enabled": gateway_enabled,
        "gateway_configured": gateway_configured,
        "gateway_online": gateway_online,
        "gateway_reach_detail": gateway_reach_detail,
        "gateway_checking": gateway_checking,
        "model": cfg.model or "—",
        "workspace": ws_label.replace("\\", "/"),
        "workspace_path": workspace.replace("\\", "/"),
        "tokens_prompt": prompt_tokens,
        "tokens_completion": completion_tokens,
        "tokens_total": prompt_tokens + completion_tokens,
        "context_tokens": context_meter["context_tokens"],
        "max_context": context_meter["max_context"],
        "context_budget": context_meter["context_budget"],
        "compact_threshold": context_meter["compact_threshold"],
        "budget_ratio": context_meter["budget_ratio"],
        "tasks": len(list_schedules()),
        "interaction_mode": getattr(cfg, "interaction_mode", "agent"),
        "python_ready": python_ready_light(workspace),
    }
