"""技能、规则、插件、定时任务、操作记录、更新与状态栏路由。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from friday.api.chat_runtime import _agent_cache, clear_agent_cache
from friday.api.schemas import (
    ChangelogEntryResponse,
    ChangelogResponse,
    ChangelogSectionResponse,
    OperationListResponse,
    OperationResponse,
    PluginInstallPayload,
    PluginResponse,
    RulePayload,
    RuleResponse,
    RuleUpdatePayload,
    ScheduleListResponse,
    SchedulePayload,
    ScheduleResponse,
    ScheduleUpdatePayload,
    SkillPayload,
    SkillResponse,
    SkillUpdatePayload,
    UpdateApplyPayload,
    UpdateApplyProgressResponse,
    UpdateApplyResponse,
    UpdateCheckResponse,
)
from friday.changelog import changelog_payload
from friday.operations import (
    clear_operations,
    export_operations,
    list_operations,
    replay_prompt,
)
from friday.plugins import (
    install_plugin,
    list_plugins,
    plugin_catalog,
    refresh_plugin,
    uninstall_plugin,
)
from friday.rules import create_rule, delete_rule, get_rule, list_rules, update_rule
from friday.schedules import (
    ScheduledTask,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)
from friday.sessions import get_session
from friday.skills import create_skill, delete_skill, get_skill, list_skills, list_skills_grouped, update_skill
from friday.storage import load_settings
from friday.updates import check_for_updates
from friday.version import __version__


def _operation_to_response(item: dict[str, Any]) -> OperationResponse:
    return OperationResponse(
        id=str(item.get("id", "")),
        ts=float(item.get("ts", 0)),
        tool=str(item.get("tool", "")),
        risk=str(item.get("risk", "")),
        summary=str(item.get("summary", "")),
        args=item.get("args") or {},
        result=str(item.get("result", "")),
        success=bool(item.get("success", True)),
        session_id=str(item.get("session_id", "")),
        trigger=str(item.get("trigger", "chat")),
        schedule_id=str(item.get("schedule_id", "")),
        approved=item.get("approved"),
    )


def _schedule_to_response(task: ScheduledTask) -> ScheduleResponse:
    return ScheduleResponse(
        id=task.id,
        title=task.title,
        prompt=task.prompt,
        frequency=task.frequency,
        day_of_week=task.day_of_week,
        hour=task.hour,
        minute=task.minute,
        cron_expr=task.cron_expr,
        interval_hours=task.interval_hours,
        enabled=task.enabled,
        retry_on_failure=task.retry_on_failure,
        max_retries=task.max_retries,
        retry_count=task.retry_count,
        schedule_label=task.schedule_label(),
        last_run_at=task.last_run_at,
        next_run_at=task.next_run_at,
        last_run_status=task.last_run_status,
        last_run_message=task.last_run_message,
        created_at=task.created_at,
    )


def _skill_to_response(item: dict[str, Any]) -> SkillResponse:
    return SkillResponse(
        id=str(item.get("id", "")),
        label=str(item.get("label", "")),
        icon=str(item.get("icon", "✨")),
        category=str(item.get("category", "custom")),
        prompt=str(item.get("prompt", "")),
        builtin=bool(item.get("builtin")),
        enabled=bool(item.get("enabled", True)),
        source=str(item.get("source", "custom")),
        plugin_id=str(item.get("plugin_id", "")),
        created_at=float(item.get("created_at", 0)),
    )


def _rule_to_response(item: dict[str, Any]) -> RuleResponse:
    return RuleResponse(
        id=str(item.get("id", "")),
        title=str(item.get("title", "")),
        content=str(item.get("content", "")),
        enabled=bool(item.get("enabled", True)),
        always_apply=bool(item.get("always_apply", True)),
        source=str(item.get("source", "custom")),
        plugin_id=str(item.get("plugin_id", "")),
        created_at=float(item.get("created_at", 0)),
    )


def _plugin_to_response(item: dict[str, Any]) -> PluginResponse:
    return PluginResponse(
        id=str(item.get("id", "")),
        name=str(item.get("name", "")),
        version=str(item.get("version", "")),
        description=str(item.get("description", "")),
        author=str(item.get("author", "")),
        source=str(item.get("source", "")),
        installed_at=float(item.get("installed_at", 0)),
        updated_at=float(item.get("updated_at", 0)),
        skill_count=int(item.get("skill_count", 0)),
        rule_count=int(item.get("rule_count", 0)),
    )


def _changelog_to_response(data: dict[str, Any]) -> ChangelogResponse:
    def _map_entry(raw: dict[str, Any]) -> ChangelogEntryResponse:
        sections = []
        for sec in raw.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            items = sec.get("items") or []
            sections.append(
                ChangelogSectionResponse(
                    label=str(sec.get("label", "")),
                    items=[str(x) for x in items if x],
                )
            )
        return ChangelogEntryResponse(
            version=str(raw.get("version", "")),
            date=str(raw.get("date", "")),
            title=str(raw.get("title", "")),
            sections=sections,
        )

    return ChangelogResponse(
        current=str(data.get("current", "")),
        acknowledged=str(data.get("acknowledged", "")),
        has_unseen=bool(data.get("has_unseen")),
        entries=[_map_entry(e) for e in data.get("entries") or [] if isinstance(e, dict)],
        unseen=[_map_entry(e) for e in data.get("unseen") or [] if isinstance(e, dict)],
    )


async def get_status_bar(session_id: str = "", cached_only: bool = False) -> dict[str, object]:
    from friday.status_bar import build_status_bar_snapshot

    def _usage(sid: str) -> dict[str, object]:
        if sid and sid in _agent_cache:
            return _agent_cache[sid].usage_snapshot()
        return {}

    def _session_context(sid: str) -> tuple[list[dict[str, object]] | None, list[dict[str, object]] | None]:
        if not sid:
            return None, None
        agent = _agent_cache.get(sid)
        if agent is not None:
            frozen = getattr(agent, "_frozen_prefix", None)
            tools = list(frozen.tool_definitions) if frozen is not None else None
            return list(agent.messages), tools
        session = get_session(sid)
        if session is not None:
            return list(session.agent_messages), None
        return None, None

    return await build_status_bar_snapshot(
        session_id=session_id,
        cached_only=cached_only,
        session_usage=_usage,
        session_context=_session_context,
    )


def register_plugins_routes(app: FastAPI) -> None:
    @app.get("/api/runtime/status")
    async def runtime_status() -> dict[str, object]:
        from friday.win10_runtime import runtime_status_payload

        return await asyncio.to_thread(runtime_status_payload)

    @app.get("/api/operations", response_model=OperationListResponse)
    async def api_list_operations(
        limit: int = 50,
        session_id: str = "",
        schedule_id: str = "",
        writes_only: bool = False,
        tool: str = "",
        risk: str = "",
        trigger: str = "",
    ) -> OperationListResponse:
        items = list_operations(
            limit=limit,
            session_id=session_id.strip(),
            schedule_id=schedule_id.strip(),
            writes_only=writes_only,
            tool=tool.strip(),
            risk=risk.strip(),
            trigger=trigger.strip(),
        )
        return OperationListResponse(
            operations=[_operation_to_response(item) for item in items]
        )

    @app.get("/api/operations/export")
    async def api_export_operations(
        format: str = "json",
        writes_only: bool = False,
        tool: str = "",
        risk: str = "",
        trigger: str = "",
        limit: int = 500,
    ) -> Response:
        fmt = "csv" if format.lower() == "csv" else "json"
        content, media_type, filename = export_operations(
            format=fmt,
            writes_only=writes_only,
            tool=tool.strip(),
            risk=risk.strip(),
            trigger=trigger.strip(),
            limit=limit,
        )
        return Response(
            content=content.encode("utf-8"),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/operations/{operation_id}/replay")
    async def api_replay_operation(operation_id: str) -> dict[str, Any]:
        prompt = replay_prompt(operation_id)
        if prompt is None:
            raise HTTPException(status_code=404, detail="操作记录不存在")
        return {"ok": True, "prompt": prompt}

    @app.delete("/api/operations")
    async def api_clear_operations() -> dict[str, Any]:
        removed = clear_operations()
        return {"ok": True, "removed": removed}

    @app.get("/api/schedules", response_model=ScheduleListResponse)
    async def api_list_schedules() -> ScheduleListResponse:
        tasks = list_schedules()
        return ScheduleListResponse(
            schedules=[_schedule_to_response(task) for task in tasks]
        )

    @app.post("/api/schedules", response_model=ScheduleResponse)
    async def api_create_schedule(payload: SchedulePayload) -> ScheduleResponse:
        title = payload.title.strip() or "未命名任务"
        prompt = payload.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="请填写任务指令")
        task = create_schedule({
            "title": title,
            "prompt": prompt,
            "frequency": payload.frequency,
            "day_of_week": payload.day_of_week,
            "hour": payload.hour,
            "minute": payload.minute,
            "cron_expr": payload.cron_expr,
            "interval_hours": payload.interval_hours,
            "enabled": payload.enabled,
            "retry_on_failure": payload.retry_on_failure,
            "max_retries": payload.max_retries,
        })
        return _schedule_to_response(task)

    @app.put("/api/schedules/{schedule_id}", response_model=ScheduleResponse)
    async def api_update_schedule(
        schedule_id: str,
        payload: ScheduleUpdatePayload,
    ) -> ScheduleResponse:
        task = update_schedule(schedule_id, payload.model_dump(exclude_unset=True))
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return _schedule_to_response(task)

    @app.delete("/api/schedules/{schedule_id}")
    async def api_delete_schedule(schedule_id: str) -> dict[str, bool]:
        if not delete_schedule(schedule_id):
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"ok": True}

    @app.post("/api/schedules/{schedule_id}/run-now")
    async def api_run_schedule_now(schedule_id: str) -> dict[str, Any]:
        from friday.scheduler import run_schedule_now

        if get_schedule(schedule_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        status, message = await asyncio.to_thread(run_schedule_now, schedule_id)
        task = get_schedule(schedule_id)
        return {
            "ok": status == "ok",
            "status": status,
            "message": message,
            "schedule": _schedule_to_response(task).model_dump() if task else None,
        }

    @app.get("/api/schedules/{schedule_id}/runs", response_model=OperationListResponse)
    async def api_schedule_runs(schedule_id: str, limit: int = 30) -> OperationListResponse:
        if get_schedule(schedule_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        items = list_operations(limit=limit, schedule_id=schedule_id)
        return OperationListResponse(
            operations=[_operation_to_response(item) for item in items]
        )

    @app.get("/api/skills")
    async def api_list_skills(
        grouped: bool = False,
        include_disabled: bool = False,
        manage: bool = False,
    ) -> dict[str, Any]:
        if grouped:
            groups = list_skills_grouped(include_disabled=include_disabled, for_ui=manage)
            return {
                "groups": [
                    {
                        "category": g["category"],
                        "label": g["label"],
                        "skills": [_skill_to_response(s).model_dump() for s in g["skills"]],
                    }
                    for g in groups
                ]
            }
        return {
            "skills": [
                _skill_to_response(s).model_dump()
                for s in list_skills(include_disabled=include_disabled, for_ui=manage)
            ]
        }

    @app.post("/api/skills", response_model=SkillResponse)
    async def api_create_skill(payload: SkillPayload) -> SkillResponse:
        label = payload.label.strip()
        prompt = payload.prompt.strip()
        if not label:
            raise HTTPException(status_code=400, detail="请填写技能名称")
        if not prompt:
            raise HTTPException(status_code=400, detail="请填写技能指令")
        skill = create_skill(payload.model_dump())
        return _skill_to_response(skill)

    @app.delete("/api/skills/{skill_id}")
    async def api_delete_skill(skill_id: str) -> dict[str, bool]:
        skill = get_skill(skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="技能不存在")
        if skill.get("builtin"):
            raise HTTPException(status_code=400, detail="内置技能不可删除")
        if not delete_skill(skill_id):
            raise HTTPException(status_code=404, detail="技能不存在")
        clear_agent_cache()
        return {"ok": True}

    @app.put("/api/skills/{skill_id}", response_model=SkillResponse)
    async def api_update_skill(skill_id: str, payload: SkillUpdatePayload) -> SkillResponse:
        skill = get_skill(skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="技能不存在")
        if skill.get("builtin"):
            raise HTTPException(status_code=400, detail="内置技能不可修改")
        updated = update_skill(skill_id, payload.model_dump(exclude_unset=True))
        if updated is None:
            raise HTTPException(status_code=404, detail="技能不存在")
        clear_agent_cache()
        return _skill_to_response(updated)

    @app.get("/api/rules")
    async def api_list_rules(manage: bool = False) -> dict[str, Any]:
        return {"rules": [_rule_to_response(r).model_dump() for r in list_rules(for_ui=manage)]}

    @app.post("/api/rules", response_model=RuleResponse)
    async def api_create_rule(payload: RulePayload) -> RuleResponse:
        title = payload.title.strip()
        content = payload.content.strip()
        if not title:
            raise HTTPException(status_code=400, detail="请填写规则标题")
        if not content:
            raise HTTPException(status_code=400, detail="请填写规则内容")
        rule = create_rule(payload.model_dump())
        clear_agent_cache()
        return _rule_to_response(rule)

    @app.put("/api/rules/{rule_id}", response_model=RuleResponse)
    async def api_update_rule(rule_id: str, payload: RuleUpdatePayload) -> RuleResponse:
        rule = update_rule(rule_id, payload.model_dump(exclude_unset=True))
        if rule is None:
            raise HTTPException(status_code=404, detail="规则不存在或不可编辑")
        clear_agent_cache()
        return _rule_to_response(rule)

    @app.delete("/api/rules/{rule_id}")
    async def api_delete_rule(rule_id: str) -> dict[str, bool]:
        rule = get_rule(rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="规则不存在")
        if rule.get("source") == "builtin":
            raise HTTPException(status_code=400, detail="内置规则不可删除")
        if not delete_rule(rule_id):
            raise HTTPException(status_code=404, detail="规则不存在")
        clear_agent_cache()
        return {"ok": True}

    @app.get("/api/plugins/catalog")
    async def api_plugin_catalog() -> dict[str, Any]:
        return {"catalog": plugin_catalog()}

    @app.get("/api/plugins")
    async def api_list_plugins() -> dict[str, Any]:
        return {"plugins": [_plugin_to_response(p).model_dump() for p in list_plugins()]}

    @app.post("/api/plugins/install", response_model=PluginResponse)
    async def api_install_plugin(payload: PluginInstallPayload) -> PluginResponse:
        source = payload.source.strip()
        if not source:
            raise HTTPException(status_code=400, detail="请填写 GitHub 仓库地址")
        try:
            entry = await asyncio.to_thread(install_plugin, source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        clear_agent_cache()
        return _plugin_to_response(entry)

    @app.post("/api/plugins/{plugin_id}/refresh", response_model=PluginResponse)
    async def api_refresh_plugin(plugin_id: str) -> PluginResponse:
        try:
            entry = await asyncio.to_thread(refresh_plugin, plugin_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        clear_agent_cache()
        return _plugin_to_response(entry)

    @app.delete("/api/plugins/{plugin_id}")
    async def api_uninstall_plugin(plugin_id: str) -> dict[str, bool]:
        if not uninstall_plugin(plugin_id):
            raise HTTPException(status_code=404, detail="插件不存在")
        clear_agent_cache()
        return {"ok": True}

    @app.get("/api/updates/check", response_model=UpdateCheckResponse)
    async def api_check_updates() -> UpdateCheckResponse:
        from friday.update_installer import can_auto_update

        info = await asyncio.to_thread(check_for_updates)
        auto_ok, auto_hint = can_auto_update()
        from friday.update_installer import format_last_apply_failure

        last_hint = format_last_apply_failure(current=info.current)
        return UpdateCheckResponse(
            current=info.current,
            latest=info.latest,
            update_available=info.update_available,
            download_url=info.download_url,
            download_sha256=info.download_sha256,
            release_notes=info.release_notes,
            checked=info.checked,
            source_repo=info.source_repo,
            source_url=info.source_url,
            source_kind=info.source_kind,
            can_auto_update=auto_ok,
            auto_update_hint=auto_hint,
            last_apply_failed=bool(last_hint),
            last_apply_hint=last_hint,
        )

    @app.post("/api/updates/apply", response_model=UpdateApplyResponse)
    async def api_apply_update(payload: UpdateApplyPayload) -> UpdateApplyResponse:
        from friday.update_installer import start_apply_update

        result = await asyncio.to_thread(
            start_apply_update,
            download_url=payload.download_url,
            version=payload.version,
            expected_sha256=payload.expected_sha256,
        )
        return UpdateApplyResponse(
            started=bool(result.get("started")),
            already_running=bool(result.get("already_running")),
            message=str(result.get("message") or ""),
            hint=str(result.get("hint") or ""),
        )

    @app.get("/api/updates/apply/progress", response_model=UpdateApplyProgressResponse)
    async def api_apply_update_progress() -> UpdateApplyProgressResponse:
        from friday.update_installer import get_apply_progress_dict

        data = await asyncio.to_thread(get_apply_progress_dict)
        return UpdateApplyProgressResponse(
            running=bool(data.get("running")),
            phase=str(data.get("phase") or "idle"),
            percent=int(data.get("percent") or 0),
            message=str(data.get("message") or ""),
            detail=str(data.get("detail") or ""),
            ok=data.get("ok") if data.get("ok") is not None else None,
            version=str(data.get("version") or ""),
            result_message=str(data.get("result_message") or ""),
            hint=str(data.get("hint") or ""),
            log=[str(x) for x in (data.get("log") or [])],
        )

    @app.get("/api/changelog", response_model=ChangelogResponse)
    async def api_changelog() -> ChangelogResponse:
        cfg = load_settings()
        ack = getattr(cfg, "acknowledged_changelog_version", "") or ""
        payload = await asyncio.to_thread(changelog_payload, ack, __version__)
        return _changelog_to_response(payload)

    @app.get("/api/status-bar")
    async def api_status_bar(session_id: str = "", cached_only: bool = False) -> dict[str, object]:
        return await get_status_bar(session_id=session_id, cached_only=cached_only)

    @app.get("/api/version")
    async def api_version() -> dict[str, object]:
        from friday.edition import display_version
        from friday.runtime_info import runtime_info_payload
        from friday.version import GITEE_HOME, GITEE_PAGES_HOME, GITEE_REPO, GITHUB_HOME, GITHUB_REPO, WEBSITE_HOME

        return {
            "version": display_version(__version__),
            "gitee_home": GITEE_HOME,
            "github_home": GITHUB_HOME,
            "gitee_repo": GITEE_REPO,
            "github_repo": GITHUB_REPO,
            "website_home": WEBSITE_HOME or None,
            "gitee_pages_home": GITEE_PAGES_HOME or None,
            **await asyncio.to_thread(runtime_info_payload),
        }
