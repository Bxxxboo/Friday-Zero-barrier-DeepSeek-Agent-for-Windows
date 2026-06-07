/* ================================================================= *
 *  settings.js — Friday 设置页：API / 文件夹 / 外观 / 日志 / 安全与更新 + 主题
 *  依赖 utils.js
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) { console.error("settings.js: window.Friday 未初始化"); return; }

  /* ── 主题 / UI 偏好 ── */

  function cacheUiPrefs(theme, fontSize) {
    localStorage.setItem(
      "friday_ui_prefs",
      JSON.stringify({ theme, font_size: fontSize })
    );
  }

  function resolveTheme(mode) {
    if (mode === "system") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    return mode === "light" ? "light" : "dark";
  }

  function applyTheme(mode) {
    const themeMode = mode || "dark";
    document.documentElement.dataset.themeMode = themeMode;
    document.documentElement.dataset.theme = resolveTheme(themeMode);
  }

  function applyFontSize(size) {
    document.documentElement.dataset.fontSize = size || "medium";
  }

  function initThemeWatcher() {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (document.documentElement.dataset.themeMode === "system") {
        applyTheme("system");
      }
    };
    if (media.addEventListener) media.addEventListener("change", handler);
    else media.addListener(handler);
  }

  function applyUiSettings(data) {
    applyTheme(data.theme || "dark");
    applyFontSize(data.font_size || "medium");
    cacheUiPrefs(data.theme || "dark", data.font_size || "medium");
  }

  /* ── 安全表单 ── */

  function fillSecurityForm(data) {
    document.getElementById("restrictToWorkspace").checked = data.restrict_to_workspace;
    document.getElementById("requireApprovalWrites").checked = data.require_approval_writes;
    document.getElementById("requireApprovalExec").checked = data.require_approval_exec;
    document.getElementById("approveOncePerTurn").checked = data.approve_once_per_turn !== false;
    document.getElementById("allowWriteFiles").checked = data.allow_write_files;
    document.getElementById("allowMoveFiles").checked = data.allow_move_files;
    document.getElementById("allowOrganize").checked = data.allow_organize;
    document.getElementById("allowCreateDocuments").checked = data.allow_create_documents;
    document.getElementById("allowPowershell").checked = data.allow_powershell;
    document.getElementById("allowPython").checked = data.allow_python !== false;
    document.getElementById("allowWebBrowse").checked = data.allow_web_browse;
    document.getElementById("allowDownloads").checked = data.allow_downloads;
    document.getElementById("requireTrustedDownloads").checked = data.require_trusted_downloads;
  }

  function collectSecuritySettings() {
    return {
      restrict_to_workspace: document.getElementById("restrictToWorkspace").checked,
      require_approval_writes: document.getElementById("requireApprovalWrites").checked,
      require_approval_exec: document.getElementById("requireApprovalExec").checked,
      approve_once_per_turn: document.getElementById("approveOncePerTurn").checked,
      allow_write_files: document.getElementById("allowWriteFiles").checked,
      allow_move_files: document.getElementById("allowMoveFiles").checked,
      allow_organize: document.getElementById("allowOrganize").checked,
      allow_create_documents: document.getElementById("allowCreateDocuments").checked,
      allow_powershell: document.getElementById("allowPowershell").checked,
      allow_python: document.getElementById("allowPython").checked,
      allow_web_browse: document.getElementById("allowWebBrowse").checked,
      allow_downloads: document.getElementById("allowDownloads").checked,
      require_trusted_downloads: document.getElementById("requireTrustedDownloads").checked,
    };
  }

  function applyStrictSecurityPreset() {
    document.getElementById("restrictToWorkspace").checked = true;
    document.getElementById("requireApprovalWrites").checked = true;
    document.getElementById("requireApprovalExec").checked = true;
    document.getElementById("allowWriteFiles").checked = true;
    document.getElementById("allowMoveFiles").checked = false;
    document.getElementById("allowOrganize").checked = false;
    document.getElementById("allowCreateDocuments").checked = true;
    document.getElementById("allowPowershell").checked = false;
    document.getElementById("allowPython").checked = true;
    document.getElementById("allowWebBrowse").checked = true;
    document.getElementById("allowDownloads").checked = false;
    document.getElementById("requireTrustedDownloads").checked = true;
  }

  /* ── 加载设置 ── */

  async function loadSettings() {
    const res = await F.apiFetchWithTimeout("/api/settings", {}, 15000);
    if (!res.ok) throw new Error(`加载设置失败 (${res.status})`);
    const data = await res.json();
    document.getElementById("baseUrl").value = data.base_url;
    document.getElementById("model").value = data.model;
    document.getElementById("workspace").value = data.workspace;
    document.getElementById("apiKeyHint").textContent = data.api_key_masked
      ? `当前已保存: ${data.api_key_masked}`
      : "尚未保存 API Key";
    const visionEnabled = document.getElementById("visionEnabled");
    if (visionEnabled) visionEnabled.checked = !!data.vision_enabled;
    const visionBaseUrl = document.getElementById("visionBaseUrl");
    if (visionBaseUrl) {
      visionBaseUrl.value = data.vision_base_url || "https://ark.cn-beijing.volces.com/api/v3";
    }
    const visionModel = document.getElementById("visionModel");
    if (visionModel) visionModel.value = data.vision_model || "";
    const visionHint = document.getElementById("visionApiKeyHint");
    if (visionHint) {
      visionHint.textContent = data.vision_api_key_masked
        ? `当前已保存: ${data.vision_api_key_masked}`
        : "尚未保存视觉 API Key";
    }
    if (visionEnabled) updateVisionStatus(data.vision_ready, data.vision_enabled);
    document.getElementById("themeMode").value = data.theme || "dark";
    document.getElementById("fontSize").value = data.font_size || "medium";
    const modeDefault = document.getElementById("interactionModeDefault");
    if (modeDefault) modeDefault.value = data.interaction_mode || "agent";
    F.setInteractionMode?.(data.interaction_mode || "agent", { persist: false, skipYoloGate: true });
    void F.refreshYoloUnlockState?.();
    fillSecurityForm(data);
    applyUiSettings(data);
    F.apiReady = data.api_ready;
    F.updateApiStatus(data.api_ready);
    F.applyStatusFromSettings?.(data);
    F.updateInputState();
    void refreshPythonEnvStatus();
    void F.refreshStatusBar?.();
  }

  /* ── 保存 ── */

  function collectSettings() {
    return {
      api_key: document.getElementById("apiKey").value.trim(),
      base_url: document.getElementById("baseUrl").value.trim(),
      model: document.getElementById("model").value,
      workspace: document.getElementById("workspace").value.trim(),
    };
  }

  function collectVisionSettings() {
    return {
      vision_enabled: document.getElementById("visionEnabled").checked,
      vision_api_key: document.getElementById("visionApiKey").value.trim(),
      vision_base_url: document.getElementById("visionBaseUrl").value.trim(),
      vision_model: document.getElementById("visionModel").value.trim(),
    };
  }

  function updateVisionStatus(ready, enabled) {
    const pill = document.getElementById("visionStatus");
    if (!pill) return;
    if (!enabled) {
      pill.textContent = "视觉辅助未启用";
      pill.classList.remove("ready");
      window.Friday?.refreshStatusBar?.();
      return;
    }
    if (ready) {
      pill.textContent = "视觉 API 已就绪";
      pill.classList.add("ready");
    } else {
      pill.textContent = "视觉 API 未配置";
      pill.classList.remove("ready");
    }
    window.Friday?.refreshStatusBar?.();
  }

  async function saveSettings(event) {
    event.preventDefault();
    F.settingsResult.className = "settings-result";
    F.settingsResult.textContent = "保存中...";
    const payload = collectSettings();
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    document.getElementById("apiKey").value = "";
    document.getElementById("apiKeyHint").textContent = `当前已保存: ${data.api_key_masked}`;
    F.apiReady = data.api_ready;
    F.updateApiStatus(data.api_ready);
    F.settingsResult.className = "settings-result ok";
    F.settingsResult.textContent = "设置已保存。";
    F.updateInputState();
  }

  async function pickWorkspaceFolder() {
    const input = document.getElementById("workspace");
    F.workspaceResult.className = "settings-result";
    F.workspaceResult.textContent = "";

    if (!window.pywebview?.api?.pick_folder) {
      F.workspaceResult.className = "settings-result error";
      F.workspaceResult.textContent = "文件夹选择仅在桌面客户端中可用。";
      return;
    }

    try {
      const path = await window.pywebview.api.pick_folder(input.value.trim());
      if (path) {
        input.value = path;
        F.workspaceResult.className = "settings-result ok";
        F.workspaceResult.textContent = "已选择目录，请点击保存。";
      }
    } catch {
      F.workspaceResult.className = "settings-result error";
      F.workspaceResult.textContent = "打开文件夹选择器失败，请重试。";
    }
  }

  async function saveWorkspace(event) {
    event.preventDefault();
    F.workspaceResult.className = "settings-result";
    F.workspaceResult.textContent = "保存中...";
    const payload = {
      workspace: document.getElementById("workspace").value.trim(),
    };
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    document.getElementById("workspace").value = data.workspace;
    F.workspaceResult.className = "settings-result ok";
    F.workspaceResult.textContent = "默认文件夹已保存。";
  }

  async function saveAppearanceSettings(event) {
    event.preventDefault();
    F.appearanceResult.className = "settings-result";
    F.appearanceResult.textContent = "保存中...";
    const payload = {
      theme: document.getElementById("themeMode").value,
      font_size: document.getElementById("fontSize").value,
      interaction_mode: document.getElementById("interactionModeDefault")?.value || "agent",
    };
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    applyUiSettings(data);
    F.setInteractionMode?.(data.interaction_mode || payload.interaction_mode, { persist: false });
    F.appearanceResult.className = "settings-result ok";
    F.appearanceResult.textContent = "外观设置已保存。";
  }

  async function saveSecuritySettings(event) {
    event.preventDefault();
    F.securityResult.className = "settings-result";
    F.securityResult.textContent = "保存中...";
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectSecuritySettings()),
    });
    if (!res.ok) {
      F.securityResult.className = "settings-result error";
      F.securityResult.textContent = "保存失败，请重试。";
      return;
    }
    const data = await res.json();
    fillSecurityForm(data);
    F.securityResult.className = "settings-result ok";
    F.securityResult.textContent = "安全设置已保存。";
  }

  async function testSettings() {
    F.settingsResult.className = "settings-result";
    F.settingsResult.textContent = "测试连接中...";
    const payload = collectSettings();
    const res = await F.apiFetch("/api/settings/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    F.settingsResult.className = data.ok ? "settings-result ok" : "settings-result error";
    F.settingsResult.textContent = data.message;
    if (data.ok) F.updateApiStatus(true);
  }

  async function saveVisionSettings(event) {
    event.preventDefault();
    const resultEl = document.getElementById("visionResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "保存中...";
    }
    const payload = collectVisionSettings();
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    document.getElementById("visionApiKey").value = "";
    document.getElementById("visionApiKeyHint").textContent = `当前已保存: ${data.vision_api_key_masked}`;
    updateVisionStatus(data.vision_ready, data.vision_enabled);
    if (resultEl) {
      resultEl.className = "settings-result ok";
      resultEl.textContent = "视觉设置已保存。";
    }
  }

  async function testVisionSettings() {
    const resultEl = document.getElementById("visionResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "测试视觉 API 中...";
    }
    const payload = collectVisionSettings();
    if (!payload.vision_enabled) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "请先勾选「启用视觉辅助」。";
      }
      updateVisionStatus(false, false);
      return;
    }
    const res = await F.apiFetch("/api/settings/test-vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = data.message;
      }
      updateVisionStatus(false, payload.vision_enabled);
      void F.refreshStatusBar?.();
      return;
    }

    const saveRes = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const saved = await saveRes.json();
    document.getElementById("visionApiKey").value = "";
    document.getElementById("visionApiKeyHint").textContent = saved.vision_api_key_masked
      ? `当前已保存: ${saved.vision_api_key_masked}`
      : "尚未保存视觉 API Key";
    updateVisionStatus(saved.vision_ready, saved.vision_enabled);
    if (resultEl) {
      resultEl.className = "settings-result ok";
      resultEl.textContent = `${data.message}（已自动保存，对话中可识图）`;
    }
    void F.refreshStatusBar?.();
  }

  /* ── 设置面板切换 ── */

  function openSettings(panel = "api") {
    switchSettingsPanel(panel);
    F.settingsModal.classList.remove("hidden");
  }

  function closeSettings() {
    F.settingsModal.classList.add("hidden");
  }

  function switchSettingsPanel(panel) {
    document.querySelectorAll(".settings-nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.panel === panel);
    });
    document.querySelectorAll(".settings-section").forEach((section) => {
      section.classList.toggle("active", section.id === `panel-${panel}`);
    });
    if (panel === "logs") {
      void refreshLogPreview();
    }
  }

  /* ── 诊断 / 日志 ── */

  async function refreshLogPreview() {
    const preview = document.getElementById("logPreview");
    const pathHint = document.getElementById("appdataPathHint");
    if (!preview) return;
    try {
      const res = await F.apiFetch("/api/diagnostics/logs?lines=20");
      const data = await res.json();
      if (pathHint && data.path) {
        pathHint.textContent = data.path.replace(/[/\\]friday\.log$/i, "");
      }
      const lines = data.lines || [];
      preview.textContent = lines.length ? lines.join("\n") : "（暂无日志）";
    } catch {
      preview.textContent = "无法读取日志，请稍后重试。";
    }
  }

  async function openLogFolder() {
    const resultEl = F.logsResult;
    if (window.pywebview?.api?.open_appdata_folder) {
      await window.pywebview.api.open_appdata_folder();
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "已打开日志文件夹。";
      }
      return;
    }
    try {
      const res = await F.apiFetch("/api/diagnostics/appdata");
      const data = await res.json();
      if (resultEl) {
        resultEl.className = "settings-result";
        resultEl.textContent = `日志目录：${data.path}`;
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "无法获取日志目录。";
      }
    }
  }

  /* ── 挂载 ── */

  F.cacheUiPrefs = cacheUiPrefs;
  F.resolveTheme = resolveTheme;
  F.applyTheme = applyTheme;
  F.applyFontSize = applyFontSize;
  F.initThemeWatcher = initThemeWatcher;
  F.applyUiSettings = applyUiSettings;
  F.fillSecurityForm = fillSecurityForm;
  F.collectSecuritySettings = collectSecuritySettings;
  F.applyStrictSecurityPreset = applyStrictSecurityPreset;
  F.loadSettings = loadSettings;
  F.collectSettings = collectSettings;
  F.saveSettings = saveSettings;
  F.pickWorkspaceFolder = pickWorkspaceFolder;
  F.saveWorkspace = saveWorkspace;
  F.saveAppearanceSettings = saveAppearanceSettings;
  F.saveSecuritySettings = saveSecuritySettings;
  F.testSettings = testSettings;
  F.saveVisionSettings = saveVisionSettings;
  F.testVisionSettings = testVisionSettings;
  F.openSettings = openSettings;
  F.closeSettings = closeSettings;
  F.switchSettingsPanel = switchSettingsPanel;
  F.refreshLogPreview = refreshLogPreview;
  F.openLogFolder = openLogFolder;

  async function refreshPythonEnvStatus() {
    const statusEl = document.getElementById("pythonEnvStatus");
    const resultEl = document.getElementById("pythonEnvResult");
    if (!statusEl) return;
    statusEl.textContent = "加载中…";
    try {
      const res = await F.apiFetchWithTimeout("/api/python-env", {}, 8000);
      const data = await res.json();
      const lines = [
        data.ready ? "✓ 已就绪" : "○ 未就绪",
        data.version ? `版本：${data.version}` : "",
        data.python_exe ? `解释器：${data.python_exe}` : "",
        `目录：${data.env_dir || "—"}`,
        data.message || "",
      ].filter(Boolean);
      statusEl.textContent = lines.join("\n");
      if (resultEl && !resultEl.classList.contains("ok") && !resultEl.classList.contains("error")) {
        resultEl.textContent = "";
        resultEl.className = "settings-result";
      }
    } catch {
      statusEl.textContent = "无法读取 Python 环境状态。";
    }
  }

  async function setupPythonEnv() {
    const btn = document.getElementById("setupPythonEnvBtn");
    const resultEl = document.getElementById("pythonEnvResult");
    if (btn) btn.disabled = true;
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "正在初始化（首次可能需几分钟下载依赖）…";
    }
    try {
      const res = await F.apiFetch("/api/python-env/setup", { method: "POST" });
      const data = await res.json();
      if (resultEl) {
        resultEl.className = data.ok ? "settings-result ok" : "settings-result error";
        resultEl.textContent = data.setup_message || data.message || (data.ok ? "完成" : "失败");
      }
      await refreshPythonEnvStatus();
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "初始化失败，请检查网络或系统是否已安装 Python 3.11+。";
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  F.refreshPythonEnvStatus = refreshPythonEnvStatus;
  F.setupPythonEnv = setupPythonEnv;

  document.getElementById("openLogFolderBtn")?.addEventListener("click", openLogFolder);
  document.getElementById("refreshLogPreviewBtn")?.addEventListener("click", refreshLogPreview);
  document.getElementById("refreshPythonEnvBtn")?.addEventListener("click", () => void refreshPythonEnvStatus());
  document.getElementById("setupPythonEnvBtn")?.addEventListener("click", () => void setupPythonEnv());

  async function loadAppVersion() {
    const label = document.getElementById("appVersionLabel");
    if (!label) return;
    try {
      const res = await F.apiFetch("/api/version");
      const data = await res.json();
      label.textContent = data.version || "—";
    } catch {
      label.textContent = "—";
    }
  }

  async function checkForUpdates() {
    const resultEl = document.getElementById("updateResult");
    const downloadLink = document.getElementById("downloadUpdateLink");
    const sourceLink = document.getElementById("updateSourceLink");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "正在检查…";
    }
    try {
      const res = await F.apiFetch("/api/updates/check");
      const data = await res.json();
      if (!data.checked) {
        if (resultEl) resultEl.textContent = "无法读取更新源配置";
        downloadLink?.classList.add("hidden");
        return;
      }
      if (data.update_available) {
        if (resultEl) {
          resultEl.className = "settings-result ok";
          resultEl.textContent = `发现新版本 ${data.latest}（当前 ${data.current}）`;
        }
        if (downloadLink && data.download_url) {
          downloadLink.href = data.download_url;
          downloadLink.classList.remove("hidden");
        }
      } else if (data.release_notes && data.latest === data.current && !data.download_url) {
        if (resultEl) {
          const isError = /无法|暂无|不可达|失败/.test(data.release_notes);
          resultEl.className = isError ? "settings-result error" : "settings-result ok";
          resultEl.textContent = isError ? data.release_notes : `已是最新版本 ${data.current}`;
        }
        downloadLink?.classList.add("hidden");
      } else {
        if (resultEl) {
          resultEl.className = "settings-result ok";
          resultEl.textContent = `已是最新版本 ${data.current}`;
        }
        downloadLink?.classList.add("hidden");
      }
      if (sourceLink && data.source_url) {
        const kind = data.source_kind === "github" ? "GitHub Releases" : "Gitee Releases";
        sourceLink.href = data.source_kind === "github"
          ? `${data.source_url}/releases`
          : `${data.source_url}/releases`;
        sourceLink.textContent = kind;
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "检查更新失败";
      }
    }
  }

  document.getElementById("checkUpdateBtn")?.addEventListener("click", checkForUpdates);
  loadAppVersion();
})();
