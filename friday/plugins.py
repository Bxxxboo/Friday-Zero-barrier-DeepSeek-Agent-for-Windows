"""插件 —— 从 GitHub 安装 skill / rule 扩展包。"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from friday.io_utils import atomic_write_json, load_json
from friday.logging_config import get_logger
from friday.paths import get_appdata_dir
from friday.rules import remove_plugin_rules, upsert_plugin_rules
from friday.skills import remove_plugin_skills, upsert_plugin_skills

_log = get_logger("plugins")

_MANIFEST = "friday-plugin.json"
_USER_AGENT = "Friday-Desktop/1.0"

# 推荐插件目录（内置 vision-bridge / storage-analyzer 见 friday.bundled，不在此列出）
_PLUGIN_CATALOG: list[dict[str, str]] = [
    {
        "id": "scipilot-figure-skill",
        "name": "SciPilot 科研数据可视化",
        "description": "先做数据剖析与选图判断，再产出出版级科研图表（Nature/Science/IEEE 等规范）。",
        "source": "local:scipilot-figure-skill",
    },
    {
        "id": "karpathy-guidelines",
        "name": "Karpathy 编码准则",
        "description": "先思考再写码、保持简单、精准改动、目标可验证（forrestchang/andrej-karpathy-skills）。",
        "source": "local:karpathy-guidelines",
    },
]

_CATALOG_CACHE_TTL_SEC = 300.0
_catalog_text_cache: tuple[float, str] | None = None

_GITHUB_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:/(?:tree|blob)/(?P<ref>[\w./-]+))?(?:\.git)?/?$",
    re.I,
)


def _registry_path() -> Path:
    return get_appdata_dir() / "plugins.json"


def _plugin_dir(plugin_id: str) -> Path:
    return get_appdata_dir() / "plugins" / plugin_id


def substitute_plugin_text(text: str, plugin_id: str) -> str:
    """运行时将 manifest / 技能 / 规则中的 {plugin_dir} 替换为本机路径。"""
    root = str(_plugin_dir(plugin_id)).replace("\\", "/")
    return (text or "").replace("{plugin_dir}", root)


def _portabilize_text(text: str, plugin_id: str) -> str:
    """将 manifest 文本中的本机绝对 plugin 路径改回 {plugin_dir} 占位符。"""
    raw = text or ""
    root = str(_plugin_dir(plugin_id))
    candidates = {root, root.replace("\\", "/"), root.replace("/", "\\")}
    for candidate in candidates:
        if candidate and candidate in raw:
            raw = raw.replace(candidate, "{plugin_dir}")
    return raw


def _ensure_portable_manifest(manifest: dict[str, Any], plugin_id: str) -> dict[str, Any]:
    """确保 manifest 落盘时使用 {plugin_dir} 而非绝对路径。"""
    result = dict(manifest)
    skills: list[dict[str, Any]] = []
    for skill in result.get("skills", []):
        if not isinstance(skill, dict):
            continue
        item = dict(skill)
        if "prompt" in item:
            item["prompt"] = _portabilize_text(str(item["prompt"]), plugin_id)
        skills.append(item)
    rules: list[dict[str, Any]] = []
    for rule in result.get("rules", []):
        if not isinstance(rule, dict):
            continue
        item = dict(rule)
        if "content" in item:
            item["content"] = _portabilize_text(str(item["content"]), plugin_id)
        rules.append(item)
    result["skills"] = skills
    result["rules"] = rules
    return result


def _manifest_has_absolute_plugin_dir(manifest: dict[str, Any], plugin_id: str) -> bool:
    root = str(_plugin_dir(plugin_id)).replace("\\", "/")
    for skill in manifest.get("skills", []):
        if isinstance(skill, dict):
            prompt = str(skill.get("prompt", "")).replace("\\", "/")
            if root in prompt and "{plugin_dir}" not in prompt:
                return True
    for rule in manifest.get("rules", []):
        if isinstance(rule, dict):
            content = str(rule.get("content", "")).replace("\\", "/")
            if root in content and "{plugin_dir}" not in content:
                return True
    return False


def migrate_installed_plugin_manifests() -> int:
    """启动时将旧版绝对路径 manifest 迁移为 {plugin_dir} 占位符。"""
    marker = get_appdata_dir() / ".plugin_manifest_portable_v1"
    if marker.is_file():
        return 0

    updated = 0
    for entry in list_plugins():
        plugin_id = str(entry.get("id", "")).strip()
        if not plugin_id:
            continue
        manifest_path = _plugin_dir(plugin_id) / _MANIFEST
        if not manifest_path.is_file():
            continue
        try:
            manifest = _validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        portable = _ensure_portable_manifest(manifest, plugin_id)
        if _manifest_has_absolute_plugin_dir(manifest, plugin_id):
            atomic_write_json(manifest_path, portable)
            upsert_plugin_skills(plugin_id, portable["skills"])
            upsert_plugin_rules(plugin_id, portable["rules"])
            updated += 1
            _log.info("已迁移插件 manifest 为可移植格式 | id=%s", plugin_id)
    try:
        marker.write_text(str(updated), encoding="utf-8")
    except OSError:
        pass
    return updated


def audit_plugin_portability() -> list[dict[str, Any]]:
    """可移植性自检：插件 manifest 是否仍含绝对路径。"""
    items: list[dict[str, Any]] = []
    for entry in list_plugins():
        plugin_id = str(entry.get("id", "")).strip()
        if not plugin_id:
            continue
        manifest_path = _plugin_dir(plugin_id) / _MANIFEST
        label = str(entry.get("name") or plugin_id)
        if not manifest_path.is_file():
            items.append({
                "id": f"plugin-{plugin_id}",
                "ok": False,
                "label": f"插件：{label}",
                "detail": "缺少 friday-plugin.json",
            })
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            items.append({
                "id": f"plugin-{plugin_id}",
                "ok": False,
                "label": f"插件：{label}",
                "detail": "manifest 无法读取",
            })
            continue
        if _manifest_has_absolute_plugin_dir(manifest, plugin_id):
            items.append({
                "id": f"plugin-{plugin_id}",
                "ok": False,
                "label": f"插件：{label}",
                "detail": "manifest 仍含本机绝对路径，请运行迁移或重新安装",
            })
        else:
            items.append({
                "id": f"plugin-{plugin_id}",
                "ok": True,
                "label": f"插件：{label}",
                "detail": "manifest 使用 {plugin_dir} 占位符",
            })
    return items


def _copy_tree(src: Path, dest: Path) -> None:
    import shutil

    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _extract_skill_source(raw: str) -> str | None:
    text = (raw or "").strip()
    if text.startswith("skill:"):
        return text[6:].strip()
    cleaned = text.replace("https://github.com/", "").strip("/")
    parts = cleaned.split("/")
    if len(parts) >= 5 and parts[2] == "tree":
        return f"{parts[0]}/{parts[1]}@{parts[3]}/{'/'.join(parts[4:])}"
    if len(parts) >= 3 and parts[2] not in {"tree", "blob"}:
        return cleaned
    return None


def parse_github_skill_source(source: str) -> tuple[str, str, str, str]:
    """解析 owner/repo@ref/skill-path，返回 owner, repo, ref, skill_path。"""
    raw = (source or "").strip().replace("https://github.com/", "").strip("/")
    if not raw:
        raise ValueError("请填写 GitHub skill 地址")

    owner = raw.split("/", 1)[0]
    rest = raw.split("/", 1)[1]

    if "@" in rest and "/" in rest.split("@", 1)[1]:
        repo_ref, skill_path = rest.split("/", 1)
        repo, ref = repo_ref.split("@", 1)
    elif "@" in rest:
        repo, ref = rest.split("@", 1)
        skill_path = ""
    elif "/" in rest:
        repo, skill_path = rest.split("/", 1)
        ref = "main"
    else:
        raise ValueError("格式应为 owner/repo/skill 或 owner/repo@ref/skill")

    skill_path = skill_path.strip("/")
    if skill_path == ".":
        skill_path = "."
    if not owner or not repo or not skill_path:
        raise ValueError("格式应为 owner/repo/skill 或 owner/repo@ref/skill（整仓 Skill 用 owner/repo/.）")
    return owner, repo.replace(".git", ""), ref.strip() or "main", skill_path


def _fetch_github_tree(owner: str, repo: str, ref: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"无法读取 GitHub 目录树 HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 GitHub 目录树: {exc}") from exc
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise ValueError("GitHub 目录树响应无效")
    return tree


def _download_github_skill_folder(
    owner: str,
    repo: str,
    ref: str,
    skill_path: str,
    dest: Path,
) -> None:
    tree = _fetch_github_tree(owner, repo, ref)
    root_skill = skill_path.strip("/") == "."
    if root_skill:
        blobs = [item for item in tree if item.get("type") == "blob"]
    else:
        prefix = skill_path.strip("/") + "/"
        blobs = [
            item for item in tree
            if item.get("type") == "blob" and str(item.get("path", "")).startswith(prefix)
        ]
    if not blobs:
        label = "仓库根目录" if root_skill else skill_path
        raise ValueError(f"仓库中未找到 skill 目录「{label}」")

    import shutil

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    for item in blobs:
        full_path = str(item["path"])
        if root_skill:
            rel = full_path
        else:
            prefix = skill_path.strip("/") + "/"
            rel = full_path[len(prefix):]
        if not rel:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        url = _raw_url(owner, repo, ref, str(item["path"]))
        target.write_text(_fetch_text(url), encoding="utf-8")

    _log.info(
        "已下载 GitHub skill | %s/%s@%s/%s files=%d",
        owner, repo, ref, skill_path, len(blobs),
    )


def install_github_skill(source: str) -> dict[str, Any]:
    """从 GitHub 仓库子目录安装 Agent Skill（含脚本与 SKILL.md）。"""
    owner, repo, ref, skill_path = parse_github_skill_source(source)
    plugin_id = skill_path.split("/")[-1].strip()
    if plugin_id == "." or not plugin_id or not re.match(r"^[\w-]+$", plugin_id):
        plugin_id = repo.replace(".git", "")
    if not plugin_id or not re.match(r"^[\w-]+$", plugin_id):
        raise ValueError("skill 目录名无法作为插件 ID")

    from friday.bundled import bundled_already_message, is_bundled_plugin

    if is_bundled_plugin(plugin_id):
        raise ValueError(bundled_already_message(plugin_id))

    dest = _plugin_dir(plugin_id)
    _download_github_skill_folder(owner, repo, ref, skill_path, dest)

    from friday.paths import extensions_dir

    bundle_manifest = extensions_dir() / plugin_id / _MANIFEST
    manifest_path = dest / _MANIFEST
    if bundle_manifest.is_file():
        manifest = _validate_manifest(json.loads(bundle_manifest.read_text(encoding="utf-8")))
    elif manifest_path.is_file():
        manifest = _validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    else:
        manifest = _validate_manifest({
            "id": plugin_id,
            "name": plugin_id.replace("-", " ").title(),
            "version": "1.0.0",
            "description": f"来自 {owner}/{repo}/{skill_path}",
            "author": f"{owner}/{repo}",
            "skills": [{
                "id": plugin_id,
                "label": plugin_id.replace("-", " ").title(),
                "icon": "✨",
                "category": "plugin",
                "prompt": (
                    f"请 read_text_file 读取 {{plugin_dir}}/SKILL.md，"
                    f"严格按 storage-analyzer 流程执行。脚本在 {{plugin_dir}}/scripts。"
                ),
            }],
            "rules": [],
        })

    manifest = _ensure_portable_manifest(manifest, plugin_id)
    atomic_write_json(dest / _MANIFEST, manifest)

    now = time.time()
    entry = {
        "id": plugin_id,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "source": f"skill:{owner}/{repo}@{ref}/{skill_path}",
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "installed_at": now,
        "updated_at": now,
        "skill_count": len(manifest["skills"]),
        "rule_count": len(manifest["rules"]),
    }
    registry = [p for p in _load_registry() if p.get("id") != plugin_id]
    registry.append(entry)
    _save_registry(registry)
    upsert_plugin_skills(plugin_id, manifest["skills"])
    upsert_plugin_rules(plugin_id, manifest["rules"])
    _log.info("GitHub skill 已安装 | id=%s source=%s", plugin_id, entry["source"])
    return entry


def parse_github_source(source: str) -> tuple[str, str, str]:
    """解析 owner/repo、owner/repo@ref 或 GitHub URL。"""
    raw = (source or "").strip()
    if not raw:
        raise ValueError("请填写 GitHub 仓库地址")

    if "@" in raw and not raw.startswith("http"):
        repo_part, ref = raw.rsplit("@", 1)
        owner, repo = _split_owner_repo(repo_part)
        return owner, repo, ref.strip() or "main"

    match = _GITHUB_RE.match(raw)
    if match:
        owner = match.group("owner")
        repo = match.group("repo")
        ref = (match.group("ref") or "main").split("/")[0]
        return owner, repo, ref

    owner, repo = _split_owner_repo(raw)
    return owner, repo, "main"


def _split_owner_repo(text: str) -> tuple[str, str]:
    parts = text.strip().strip("/").split("/")
    if len(parts) < 2:
        raise ValueError("格式应为 owner/repo 或 owner/repo@分支")
    return parts[0], parts[1].replace(".git", "")


def _raw_url(owner: str, repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"


def _fetch_text(url: str, *, timeout: float = 20.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}: {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"无法访问: {exc}") from exc


def _load_registry() -> list[dict[str, Any]]:
    raw = load_json(_registry_path())
    if not isinstance(raw, list):
        return []
    return raw


def _save_registry(items: list[dict[str, Any]]) -> None:
    atomic_write_json(_registry_path(), items)


def list_plugins() -> list[dict[str, Any]]:
    return sorted(_load_registry(), key=lambda p: p.get("installed_at", 0), reverse=True)


def get_plugin(plugin_id: str) -> dict[str, Any] | None:
    for item in _load_registry():
        if item.get("id") == plugin_id:
            return item
    return None


def plugin_catalog() -> list[dict[str, str]]:
    return list(_PLUGIN_CATALOG)


def resolve_plugin_source(source: str) -> str:
    """将插件 ID / 简称解析为可安装的 source（含推荐目录匹配）。"""
    raw = (source or "").strip()
    if not raw:
        return raw
    if raw.startswith("local:") or raw.startswith("skill:"):
        return raw
    lowered = raw.lower().replace("https://github.com/", "").strip("/")
    for item in _PLUGIN_CATALOG:
        pid = item.get("id", "")
        name = item.get("name", "")
        catalog_source = item.get("source", "")
        if lowered == pid.lower() or lowered == name.lower():
            return catalog_source
        if pid and lowered.endswith(f"/{pid.lower()}"):
            return catalog_source
    if "/" not in lowered and "@" not in lowered:
        for item in _PLUGIN_CATALOG:
            if item.get("id", "").lower() == lowered:
                return item["source"]
    return raw


def format_plugin_catalog(*, force_refresh: bool = False) -> str:
    global _catalog_text_cache
    now = time.time()
    if (
        not force_refresh
        and _catalog_text_cache is not None
        and now - _catalog_text_cache[0] < _CATALOG_CACHE_TTL_SEC
    ):
        return _catalog_text_cache[1]

    if not _PLUGIN_CATALOG:
        text = (
            "图片视觉桥接、存储分析等能力已内置于星期五，无需安装。"
            "可在设置 → 扩展 → 插件 从 GitHub 安装其他 friday-plugin.json 扩展包。"
            "\nGitHub Agent Skill 用 skill:owner/repo/目录 格式；整仓即 Skill 示例："
            " skill:Haojae/scipilot-figure-skill/. （仓库根目录有 SKILL.md 时用 /. 作路径）"
        )
    else:
        lines = ["推荐插件（设置 → 扩展 → 插件 也可一键安装）："]
        for item in _PLUGIN_CATALOG:
            lines.append(f"- {item['name']}（id: {item['id']}）→ {item['source']}")
            lines.append(f"  {item.get('description', '')}")
        text = "\n".join(lines)

    _catalog_text_cache = (now, text)
    return text


def invalidate_plugin_catalog_cache() -> None:
    global _catalog_text_cache
    _catalog_text_cache = None


def _validate_manifest(data: dict[str, Any]) -> dict[str, Any]:
    pid = str(data.get("id", "")).strip()
    name = str(data.get("name", "")).strip()
    if not pid or not re.match(r"^[\w-]+$", pid):
        raise ValueError("插件 manifest 缺少合法 id（字母数字与连字符）")
    if not name:
        raise ValueError("插件 manifest 缺少 name")
    skills = data.get("skills")
    rules = data.get("rules")
    if not isinstance(skills, list):
        skills = []
    if not isinstance(rules, list):
        rules = []
    return {
        "id": pid,
        "name": name,
        "version": str(data.get("version", "1.0.0")),
        "description": str(data.get("description", "")),
        "author": str(data.get("author", "")),
        "skills": skills,
        "rules": rules,
    }


def install_plugin_from_manifest(manifest: dict[str, Any], *, source: str = "local") -> dict[str, Any]:
    """从 manifest 字典安装（测试 / 本地示例）。"""
    from friday.bundled import bundled_already_message, is_bundled_plugin

    manifest = _validate_manifest(manifest)
    plugin_id = manifest["id"]
    if is_bundled_plugin(plugin_id):
        raise ValueError(bundled_already_message(plugin_id))
    now = time.time()
    entry = {
        "id": plugin_id,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "source": source,
        "owner": "",
        "repo": "",
        "ref": "",
        "installed_at": now,
        "updated_at": now,
        "skill_count": len(manifest["skills"]),
        "rule_count": len(manifest["rules"]),
    }
    registry = [p for p in _load_registry() if p.get("id") != plugin_id]
    registry.append(entry)
    _save_registry(registry)
    dest = _plugin_dir(plugin_id)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = _ensure_portable_manifest(manifest, plugin_id)
    atomic_write_json(dest / _MANIFEST, manifest)
    upsert_plugin_skills(plugin_id, manifest["skills"])
    upsert_plugin_rules(plugin_id, manifest["rules"])
    return entry


def install_local_plugin(plugin_id: str) -> dict[str, Any]:
    """从内置 extensions/ 目录安装插件。"""
    from friday.bundled import bundled_already_message, is_bundled_plugin
    from friday.paths import extensions_dir

    pid = (plugin_id or "").strip()
    if is_bundled_plugin(pid):
        raise ValueError(bundled_already_message(pid))
    if not pid or not re.match(r"^[\w-]+$", pid):
        raise ValueError("插件 ID 无效")

    manifest_path = extensions_dir() / pid / _MANIFEST
    if not manifest_path.is_file():
        raise ValueError(f"未找到内置插件「{pid}」（{manifest_path}）")

    manifest = _validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    entry = install_plugin_from_manifest(manifest, source=f"local:{pid}")
    bundle = extensions_dir() / pid
    if bundle.is_dir():
        _copy_tree(bundle, _plugin_dir(pid))
        manifest = _ensure_portable_manifest(
            json.loads(manifest_path.read_text(encoding="utf-8")),
            pid,
        )
        atomic_write_json(_plugin_dir(pid) / _MANIFEST, manifest)
        upsert_plugin_skills(pid, manifest["skills"])
        upsert_plugin_rules(pid, manifest["rules"])
    return entry


def install_plugin(source: str) -> dict[str, Any]:
    from friday.bundled import bundled_already_message, is_bundled_plugin, resolve_bundled_source

    bundled_id = resolve_bundled_source(source)
    if bundled_id:
        raise ValueError(bundled_already_message(bundled_id))

    raw = resolve_plugin_source((source or "").strip())
    if raw.startswith("local:"):
        pid = raw.split(":", 1)[1]
        if is_bundled_plugin(pid):
            raise ValueError(bundled_already_message(pid))
        return install_local_plugin(pid)
    skill_source = _extract_skill_source(raw)
    if skill_source:
        return install_github_skill(skill_source)
    owner, repo, ref = parse_github_source(source)
    manifest_url = _raw_url(owner, repo, ref, _MANIFEST)
    _log.info("安装插件 | source=%s url=%s", source, manifest_url)

    try:
        manifest_text = _fetch_text(manifest_url)
    except ValueError as exc:
        raise ValueError(
            f"未找到 {_MANIFEST}（{exc}）。"
            f"请确认仓库根目录包含该文件，格式见文档。"
        ) from exc

    try:
        manifest = _validate_manifest(json.loads(manifest_text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"插件 manifest JSON 无效: {exc}") from exc

    plugin_id = manifest["id"]
    registry = _load_registry()
    now = time.time()

    entry = {
        "id": plugin_id,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "source": f"{owner}/{repo}@{ref}",
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "installed_at": now,
        "updated_at": now,
        "skill_count": len(manifest["skills"]),
        "rule_count": len(manifest["rules"]),
    }

    registry = [p for p in registry if p.get("id") != plugin_id]
    registry.append(entry)
    _save_registry(registry)

    dest = _plugin_dir(plugin_id)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = _ensure_portable_manifest(manifest, plugin_id)
    atomic_write_json(dest / _MANIFEST, manifest)

    upsert_plugin_skills(plugin_id, manifest["skills"])
    upsert_plugin_rules(plugin_id, manifest["rules"])

    _log.info("插件已安装 | id=%s skills=%d rules=%d", plugin_id, entry["skill_count"], entry["rule_count"])
    return entry


def refresh_plugin(plugin_id: str) -> dict[str, Any]:
    entry = get_plugin(plugin_id)
    if entry is None:
        raise ValueError("插件未安装")
    source = str(entry.get("source", ""))
    if source.startswith("local:"):
        return install_local_plugin(source.split(":", 1)[1])
    if source.startswith("skill:"):
        return install_github_skill(source[6:])
    result = install_plugin(source)
    return result


def uninstall_plugin(plugin_id: str) -> bool:
    from friday.bundled import bundled_already_message, is_bundled_plugin

    pid = (plugin_id or "").strip()
    if is_bundled_plugin(pid):
        raise ValueError(bundled_already_message(pid))

    entry = get_plugin(pid)
    if entry is None:
        return False

    registry = [p for p in _load_registry() if p.get("id") != plugin_id]
    _save_registry(registry)

    remove_plugin_skills(plugin_id)
    remove_plugin_rules(plugin_id)

    dest = _plugin_dir(plugin_id)
    if dest.exists():
        import shutil
        shutil.rmtree(dest, ignore_errors=True)

    _log.info("插件已卸载 | id=%s", plugin_id)
    return True
