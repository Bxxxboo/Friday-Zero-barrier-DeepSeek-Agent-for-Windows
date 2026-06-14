/* ================================================================= *
 *  extensions.js — 设置页：技能 / 规则 / 插件
 *  依赖 utils.js / skills.js
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) { console.error("extensions.js: window.Friday 未初始化"); return; }

  const skillListEl = document.getElementById("skillManageList");
  const skillFormEl = document.getElementById("skillForm");
  const skillResultEl = document.getElementById("skillResult");
  const ruleListEl = document.getElementById("ruleManageList");
  const ruleFormEl = document.getElementById("ruleForm");
  const ruleResultEl = document.getElementById("ruleResult");
  const pluginListEl = document.getElementById("pluginList");
  const pluginCatalogEl = document.getElementById("pluginCatalog");
  const pluginResultEl = document.getElementById("pluginResult");
  const pluginSourceEl = document.getElementById("pluginSourceInput");

  function showResult(el, text, ok) {
    if (!el) return;
    el.className = ok ? "settings-result ok" : "settings-result error";
    el.textContent = text;
  }

  function sourceBadge(source) {
    if (source === "plugin") return "插件";
    if (source === "custom") return "自定义";
    if (source === "builtin") return "内置";
    return source || "";
  }

  function switchExtTab(tab) {
    document.querySelectorAll("[data-ext-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.extTab === tab);
    });
    document.querySelectorAll(".ext-panel").forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.extPanel !== tab);
    });
    if (tab === "skills") loadSkillsPanel();
    if (tab === "rules") loadRulesPanel();
    if (tab === "plugins") loadPluginsPanel();
    if (tab === "mcp") loadMcpPanel();
  }

  /* ── 技能 ── */

  function canDeleteSkill(skill) {
    return !skill.builtin;
  }

  function canDeleteRule(rule) {
    return rule.source !== "builtin";
  }

  function deleteConfirmMessage(kind, item) {
    const name = kind === "skill" ? item.label : item.title;
    if (item.source === "plugin") {
      return (
        `确定删除${kind === "skill" ? "技能" : "规则"}「${name}」？\n` +
        "不会卸载整个插件；重新安装或更新该插件时可恢复。"
      );
    }
    return `确定删除${kind === "skill" ? "技能" : "规则"}「${name}」？此操作不可撤销。`;
  }

  async function deleteSkill(skill) {
    if (!confirm(deleteConfirmMessage("skill", skill))) return;
    try {
      const res = await F.apiFetch(`/api/skills/${skill.id}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showResult(skillResultEl, err.detail || "删除失败", false);
        return;
      }
      showResult(skillResultEl, `已删除技能「${skill.label}」`, true);
      await loadSkillsPanel();
      F.loadWelcomeChips?.();
    } catch {
      showResult(skillResultEl, "删除失败", false);
    }
  }

  async function deleteRule(rule) {
    if (!confirm(deleteConfirmMessage("rule", rule))) return;
    try {
      const res = await F.apiFetch(`/api/rules/${rule.id}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showResult(ruleResultEl, err.detail || "删除失败", false);
        return;
      }
      showResult(ruleResultEl, `已删除规则「${rule.title}」`, true);
      await loadRulesPanel();
    } catch {
      showResult(ruleResultEl, "删除失败", false);
    }
  }

  function renderSkillManageList(skills) {
    if (!skillListEl) return;
    skillListEl.innerHTML = "";
    const rows = skills.filter((s) => !s.builtin);
    if (rows.length === 0) {
      skillListEl.innerHTML = '<p class="settings-hint">还没有自定义或插件技能。可在下方添加，或从「插件」标签安装 GitHub 扩展包。</p>';
      return;
    }
    rows.forEach((skill) => {
      const row = document.createElement("div");
      row.className = "skill-manage-row";
      const badge = sourceBadge(skill.source);
      const deletable = canDeleteSkill(skill);
      row.innerHTML = `
        <label class="ext-enable-toggle">
          <input type="checkbox" ${skill.enabled ? "checked" : ""} />
          <span>${skill.icon || "✨"} ${skill.label}</span>
          <small class="ext-badge">${badge}</small>
        </label>
        ${deletable ? '<button type="button" class="ghost-btn ext-del-btn skill-del-btn">删除</button>' : ""}`;
      row.querySelector("input")?.addEventListener("change", async (e) => {
        await F.apiFetch(`/api/skills/${skill.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: e.target.checked }),
        });
        F.loadWelcomeChips?.();
      });
      row.querySelector(".skill-del-btn")?.addEventListener("click", () => {
        void deleteSkill(skill);
      });
      skillListEl.appendChild(row);
    });
  }

  async function loadSkillsPanel() {
    try {
      const res = await F.apiFetch("/api/skills?include_disabled=true&manage=true");
      const data = await res.json();
      renderSkillManageList(data.skills || []);
    } catch {
      showResult(skillResultEl, "加载技能失败", false);
    }
  }

  async function saveSkill(event) {
    event.preventDefault();
    const payload = {
      label: document.getElementById("skillLabel")?.value.trim(),
      icon: document.getElementById("skillIcon")?.value.trim() || "✨",
      prompt: document.getElementById("skillPrompt")?.value.trim(),
    };
    if (!payload.label || !payload.prompt) {
      showResult(skillResultEl, "请填写名称和指令", false);
      return;
    }
    showResult(skillResultEl, "保存中…", true);
    try {
      const res = await F.apiFetch("/api/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showResult(skillResultEl, err.detail || "保存失败", false);
        return;
      }
      skillFormEl?.reset();
      document.getElementById("skillIcon").value = "✨";
      showResult(skillResultEl, "技能已添加", true);
      await loadSkillsPanel();
      F.loadWelcomeChips?.();
    } catch {
      showResult(skillResultEl, "保存失败", false);
    }
  }

  /* ── 规则 ── */

  function renderRuleList(rules) {
    if (!ruleListEl) return;
    ruleListEl.innerHTML = "";
    if (rules.length === 0) {
      ruleListEl.innerHTML = '<p class="settings-hint">还没有规则。规则会注入到 AI 系统提示中，用于定制星期五的行为风格。</p>';
      return;
    }
    rules.forEach((rule) => {
      const row = document.createElement("article");
      row.className = "rule-manage-row";
      const deletable = canDeleteRule(rule);
      row.innerHTML = `
        <div class="rule-manage-head">
          <label class="ext-enable-toggle">
            <input type="checkbox" ${rule.enabled ? "checked" : ""} />
            <strong>${rule.title}</strong>
          </label>
          <div class="rule-manage-head-actions">
            <small class="ext-badge">${sourceBadge(rule.source)}</small>
            ${deletable ? '<button type="button" class="ghost-btn ext-del-btn rule-del-btn">删除</button>' : ""}
          </div>
        </div>
        <p class="rule-manage-content">${rule.content}</p>`;
      row.querySelector("input")?.addEventListener("change", async (e) => {
        await F.apiFetch(`/api/rules/${rule.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: e.target.checked }),
        });
      });
      row.querySelector(".rule-del-btn")?.addEventListener("click", () => {
        void deleteRule(rule);
      });
      ruleListEl.appendChild(row);
    });
  }

  async function loadRulesPanel() {
    try {
      const res = await F.apiFetch("/api/rules?manage=true");
      const data = await res.json();
      renderRuleList(data.rules || []);
    } catch {
      showResult(ruleResultEl, "加载规则失败", false);
    }
  }

  async function saveRule(event) {
    event.preventDefault();
    const payload = {
      title: document.getElementById("ruleTitle")?.value.trim(),
      content: document.getElementById("ruleContent")?.value.trim(),
      always_apply: document.getElementById("ruleAlwaysApply")?.checked ?? true,
    };
    if (!payload.title || !payload.content) {
      showResult(ruleResultEl, "请填写标题和内容", false);
      return;
    }
    showResult(ruleResultEl, "保存中…", true);
    try {
      const res = await F.apiFetch("/api/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showResult(ruleResultEl, err.detail || "保存失败", false);
        return;
      }
      ruleFormEl?.reset();
      document.getElementById("ruleAlwaysApply").checked = true;
      showResult(ruleResultEl, "规则已添加", true);
      loadRulesPanel();
    } catch {
      showResult(ruleResultEl, "保存失败", false);
    }
  }

  /* ── 插件 ── */

  function renderPluginList(plugins) {
    if (!pluginListEl) return;
    pluginListEl.innerHTML = "";
    if (plugins.length === 0) {
      pluginListEl.innerHTML = '<p class="settings-hint">尚未安装插件。可从上方推荐列表一键安装，或输入 GitHub 仓库地址。</p>';
      return;
    }

    const heading = document.createElement("h5");
    heading.className = "plugin-section-title";
    heading.textContent = "已安装";
    pluginListEl.appendChild(heading);

    const list = document.createElement("div");
    list.className = "plugin-list-inner";

    plugins.forEach((plugin) => {
      const card = document.createElement("article");
      card.className = "plugin-card";
      card.innerHTML = `
        <div class="plugin-card-head">
          <h5>${plugin.name} <small>v${plugin.version}</small></h5>
          <span class="ext-badge">${plugin.source}</span>
        </div>
        <p class="plugin-card-desc">${plugin.description || "无描述"}</p>
        <p class="plugin-card-meta">${plugin.skill_count} 技能 · ${plugin.rule_count} 规则</p>
        <div class="plugin-card-actions">
          <button type="button" class="ghost-btn plugin-refresh-btn">更新</button>
          <button type="button" class="ghost-btn plugin-uninstall-btn">卸载</button>
        </div>`;
      card.querySelector(".plugin-refresh-btn").addEventListener("click", async () => {
        showResult(pluginResultEl, "正在从 GitHub 更新…", true);
        try {
          const res = await F.apiFetch(`/api/plugins/${plugin.id}/refresh`, { method: "POST" });
          if (!res.ok) throw new Error("更新失败");
          showResult(pluginResultEl, "插件已更新", true);
          loadPluginsPanel();
          F.loadWelcomeChips?.();
          loadRulesPanel();
        } catch {
          showResult(pluginResultEl, "更新失败", false);
        }
      });
      card.querySelector(".plugin-uninstall-btn").addEventListener("click", async () => {
        if (!confirm(`确定卸载插件「${plugin.name}」？相关技能与规则将一并移除。`)) return;
        await F.apiFetch(`/api/plugins/${plugin.id}`, { method: "DELETE" });
        loadPluginsPanel();
        F.loadWelcomeChips?.();
        loadSkillsPanel();
        loadRulesPanel();
      });
      list.appendChild(card);
    });

    pluginListEl.appendChild(list);
  }

  function renderPluginCatalog(items, installed = []) {
    if (!pluginCatalogEl) return;
    pluginCatalogEl.innerHTML = "";
    if (!items.length) {
      pluginCatalogEl.innerHTML =
        '<p class="settings-hint">图片识别、存储分析等能力已内置于星期五，无需安装。下方可从 GitHub 安装其他扩展包。</p>';
      return;
    }

    const installedIds = new Set((installed || []).map((p) => p.id));

    const heading = document.createElement("h5");
    heading.className = "plugin-section-title";
    heading.textContent = "推荐插件";
    pluginCatalogEl.appendChild(heading);

    const list = document.createElement("div");
    list.className = "plugin-catalog-list";

    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "plugin-catalog-row";
      const isInstalled = installedIds.has(item.id);
      row.innerHTML = `
        <div class="plugin-catalog-info">
          <strong>${item.name}</strong>
          <p class="plugin-catalog-desc">${item.description || ""}</p>
          ${item.capabilities ? `<p class="plugin-catalog-caps">能做什么：${item.capabilities}</p>` : ""}
        </div>
        <div class="plugin-catalog-action">
          ${
            isInstalled
              ? '<span class="ext-badge plugin-installed-badge">已安装</span>'
              : '<button type="button" class="ghost-btn plugin-install-btn">安装</button>'
          }
        </div>`;
      const btn = row.querySelector(".plugin-install-btn");
      btn?.addEventListener("click", () => installPlugin(item.source));
      list.appendChild(row);
    });

    pluginCatalogEl.appendChild(list);
  }

  async function loadPluginsPanel() {
    try {
      const [pluginsRes, catalogRes] = await Promise.all([
        F.apiFetch("/api/plugins"),
        F.apiFetch("/api/plugins/catalog"),
      ]);
      const pluginsData = await pluginsRes.json();
      const catalogData = await catalogRes.json();
      renderPluginList(pluginsData.plugins || []);
      renderPluginCatalog(catalogData.catalog || [], pluginsData.plugins || []);
    } catch {
      showResult(pluginResultEl, "加载插件失败", false);
    }
  }

  async function installPlugin(source) {
    const src = (source || pluginSourceEl?.value || "").trim();
    if (!src) {
      showResult(pluginResultEl, "请填写 GitHub 仓库", false);
      return;
    }
    showResult(pluginResultEl, "正在从 GitHub 下载并应用…", true);
    try {
      const res = await F.apiFetch("/api/plugins/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: src }),
      });
      const data = await res.json();
      if (!res.ok) {
        showResult(pluginResultEl, data.detail || "安装失败", false);
        return;
      }
      showResult(pluginResultEl, `已安装「${data.name}」：${data.skill_count} 技能、${data.rule_count} 规则`, true);
      if (pluginSourceEl) pluginSourceEl.value = "";
      loadPluginsPanel();
      loadSkillsPanel();
      loadRulesPanel();
      F.loadWelcomeChips?.();
    } catch {
      showResult(pluginResultEl, "安装失败", false);
    }
  }

  document.querySelectorAll("[data-ext-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchExtTab(btn.dataset.extTab));
  });
  document.getElementById("pluginInstallBtn")?.addEventListener("click", () => installPlugin());
  skillFormEl?.addEventListener("submit", saveSkill);
  ruleFormEl?.addEventListener("submit", saveRule);

  const origSwitch = F.switchSettingsPanel;
  F.switchSettingsPanel = (panel) => {
    origSwitch(panel);
    if (panel === "extensions") {
      switchExtTab("skills");
    }
  };

  F.openExtensionsSettings = (tab) => {
    F.openSettings("extensions");
    if (tab) switchExtTab(tab);
  };

  F.loadSkillsPanel = loadSkillsPanel;
  F.loadRulesPanel = loadRulesPanel;
  F.loadPluginsPanel = loadPluginsPanel;

  /* ── MCP ── */

  const mcpListEl = document.getElementById("mcpServerList");
  const mcpEmptyEl = document.getElementById("mcpEmpty");
  const mcpResultEl = document.getElementById("mcpResult");
  let mcpServers = [];

  function escapeMcpAttr(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function renderMcpServers() {
    if (!mcpListEl) return;
    mcpListEl.innerHTML = "";

    if (!mcpServers.length) {
      mcpEmptyEl?.classList.remove("hidden");
      return;
    }
    mcpEmptyEl?.classList.add("hidden");

    mcpServers.forEach((srv, idx) => {
      const card = document.createElement("article");
      card.className = "mcp-server-card" + (srv.enabled ? "" : " mcp-server-card-off");
      const displayName = srv.name?.trim() || "MCP Server";
      const argsStr = (srv.args || []).join(" ");
      const commandHint = srv.command?.trim() || "未设置命令";

      card.innerHTML = `
        <div class="mcp-card-head">
          <div class="mcp-card-head-main">
            <span class="mcp-card-badge">${idx + 1}</span>
            <div class="mcp-card-head-text">
              <h5 class="mcp-card-title" data-mcp-title="${idx}">${escapeMcpAttr(displayName)}</h5>
              <p class="mcp-card-sub" data-mcp-sub="${idx}">${escapeMcpAttr(commandHint)}</p>
            </div>
          </div>
          <div class="mcp-card-head-actions">
            <label class="schedule-toggle mcp-card-toggle" title="${srv.enabled ? "启用中" : "已停用"}">
              <input type="checkbox" data-mcp-enabled="${idx}" ${srv.enabled ? "checked" : ""}/>
              <span class="schedule-toggle-ui"></span>
            </label>
            <button type="button" class="ghost-btn mcp-card-remove danger-text" data-mcp-remove="${idx}">删除</button>
          </div>
        </div>
        <div class="mcp-card-body">
          <div class="settings-form mcp-card-form">
            <label>
              <span>名称</span>
              <input type="text" data-mcp-name="${idx}" value="${escapeMcpAttr(srv.name || "")}" placeholder="例如：Better Icons"/>
            </label>
            <label>
              <span>命令</span>
              <input type="text" data-mcp-command="${idx}" value="${escapeMcpAttr(srv.command || "")}" placeholder="npx 或 python 可执行文件路径"/>
            </label>
            <div class="mcp-form-row">
              <label>
                <span>参数</span>
                <input type="text" data-mcp-args="${idx}" value="${escapeMcpAttr(argsStr)}" placeholder="空格分隔"/>
              </label>
              <label>
                <span>工作目录</span>
                <input type="text" data-mcp-cwd="${idx}" value="${escapeMcpAttr(srv.cwd || "")}" placeholder="可选"/>
              </label>
            </div>
          </div>
        </div>
      `;

      const enabledInput = card.querySelector(`[data-mcp-enabled="${idx}"]`);
      enabledInput?.addEventListener("change", () => {
        card.classList.toggle("mcp-server-card-off", !enabledInput.checked);
        enabledInput.closest(".mcp-card-toggle")?.setAttribute(
          "title",
          enabledInput.checked ? "启用中" : "已停用",
        );
      });

      const nameInput = card.querySelector(`[data-mcp-name="${idx}"]`);
      const cmdInput = card.querySelector(`[data-mcp-command="${idx}"]`);
      const titleEl = card.querySelector(`[data-mcp-title="${idx}"]`);
      const subEl = card.querySelector(`[data-mcp-sub="${idx}"]`);
      const syncPreview = () => {
        if (titleEl) titleEl.textContent = nameInput?.value?.trim() || "MCP Server";
        if (subEl) subEl.textContent = cmdInput?.value?.trim() || "未设置命令";
      };
      nameInput?.addEventListener("input", syncPreview);
      cmdInput?.addEventListener("input", syncPreview);

      mcpListEl.appendChild(card);
    });

    mcpListEl.querySelectorAll("[data-mcp-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        mcpServers.splice(Number(btn.dataset.mcpRemove), 1);
        renderMcpServers();
      });
    });
  }

  function collectMcpServersFromDom() {
    return mcpServers.map((srv, idx) => {
      const enabled = mcpListEl?.querySelector(`[data-mcp-enabled="${idx}"]`);
      const name = mcpListEl?.querySelector(`[data-mcp-name="${idx}"]`);
      const command = mcpListEl?.querySelector(`[data-mcp-command="${idx}"]`);
      const args = mcpListEl?.querySelector(`[data-mcp-args="${idx}"]`);
      const cwd = mcpListEl?.querySelector(`[data-mcp-cwd="${idx}"]`);
      return {
        id: srv.id || "",
        name: name?.value?.trim() || srv.name || "MCP",
        command: command?.value?.trim() || "",
        args: (args?.value || "").trim().split(/\s+/).filter(Boolean),
        env: srv.env || {},
        enabled: enabled?.checked !== false,
        cwd: cwd?.value?.trim() || "",
      };
    });
  }

  async function loadMcpPanel() {
    try {
      const res = await F.apiFetch("/api/mcp/servers");
      const data = await res.json();
      mcpServers = Array.isArray(data.servers) ? data.servers : [];
      renderMcpServers();
    } catch {
      showResult(mcpResultEl, "加载 MCP 配置失败", false);
    }
  }

  async function saveMcpPanel() {
    mcpServers = collectMcpServersFromDom();
    try {
      const res = await F.apiFetch("/api/mcp/servers", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servers: mcpServers }),
      });
      const data = await res.json();
      if (!res.ok) {
        showResult(mcpResultEl, "保存失败", false);
        return;
      }
      mcpServers = data.servers || mcpServers;
      showResult(mcpResultEl, "MCP 配置已保存（新会话生效）", true);
    } catch {
      showResult(mcpResultEl, "保存失败", false);
    }
  }

  document.getElementById("mcpAddServerBtn")?.addEventListener("click", () => {
    mcpServers.push({
      id: "",
      name: "MCP Server",
      command: "",
      args: [],
      env: {},
      enabled: true,
      cwd: "",
    });
    renderMcpServers();
  });
  document.getElementById("mcpSaveBtn")?.addEventListener("click", () => void saveMcpPanel());
  F.loadMcpPanel = loadMcpPanel;
})();
