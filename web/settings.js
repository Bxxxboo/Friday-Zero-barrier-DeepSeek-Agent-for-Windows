/* ================================================================= *
 *  settings.js — Friday 设置页：API / 文件夹 / 外观 / 日志 / 安全与更新 + 主题
 *  依赖 utils.js
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) { console.error("settings.js: window.Friday 未初始化"); return; }

  /* ── 主题 / UI 偏好 ── */

  function cacheUiPrefs(theme, fontSize, uiLanguage) {
    localStorage.setItem(
      "friday_ui_prefs",
      JSON.stringify({
        theme,
        font_size: fontSize,
        ui_language: uiLanguage || window.FridayI18n?.getLanguage?.() || "zh",
      })
    );
  }

  function t(key, params) {
    return window.FridayI18n?.t?.(key, params) ?? key;
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
    const resolved = resolveTheme(themeMode);
    document.documentElement.style.backgroundColor = resolved === "light" ? "#f0ebe3" : "#0a0d12";
    if (document.documentElement.classList.contains("desktop")) {
      window.pywebview?.api?.sync_window_chrome?.(
        resolved === "light" ? "#f0ebe3" : "#0a0d12",
        resolved === "dark"
      );
    }
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
    const lang = data.ui_language || "zh";
    window.FridayI18n?.setLanguage?.(lang);
    cacheUiPrefs(data.theme || "dark", data.font_size || "medium", lang);
  }

  /* ── 安全表单 ── */

  function fillSecurityForm(data) {
    document.getElementById("restrictToWorkspace").checked = data.restrict_to_workspace;
    const allowRead = document.getElementById("allowReadUserFolders");
    if (allowRead) allowRead.checked = data.allow_read_user_folders !== false;
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
      allow_read_user_folders: document.getElementById("allowReadUserFolders")?.checked !== false,
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
    const allowRead = document.getElementById("allowReadUserFolders");
    if (allowRead) allowRead.checked = false;
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
    const imageGenEnabled = document.getElementById("imageGenEnabled");
    if (imageGenEnabled) imageGenEnabled.checked = !!data.image_gen_enabled;
    const imageGenProvider = document.getElementById("imageGenProvider");
    if (imageGenProvider) {
      imageGenProvider.value = data.image_gen_provider || "openai_compat";
    }
    const imageGenBaseUrl = document.getElementById("imageGenBaseUrl");
    if (imageGenBaseUrl) {
      imageGenBaseUrl.value = data.image_gen_base_url || "https://next.zhima.world";
    }
    const imageGenFallback = document.getElementById("imageGenFallbackUrls");
    if (imageGenFallback) imageGenFallback.value = data.image_gen_fallback_urls || "";
    const imageGenModel = document.getElementById("imageGenModel");
    if (imageGenModel) imageGenModel.value = data.image_gen_model || "";
    const imageGenSize = document.getElementById("imageGenDefaultSize");
    if (imageGenSize) {
      imageGenSize.value = data.image_gen_default_size || "1024x1024";
    }
    const imageGenHint = document.getElementById("imageGenApiKeyHint");
    if (imageGenHint) {
      imageGenHint.textContent = data.image_gen_api_key_masked
        ? `当前已保存: ${data.image_gen_api_key_masked}`
        : "尚未保存生图 API Key";
    }
    if (imageGenEnabled) updateImageGenStatus(data.image_gen_ready, data.image_gen_enabled);
    document.getElementById("themeMode").value = data.theme || "dark";
    document.getElementById("fontSize").value = data.font_size || "medium";
    const langEl = document.getElementById("uiLanguage");
    if (langEl) langEl.value = data.ui_language || "zh";
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
    if (Array.isArray(data.portability_notices) && data.portability_notices.length && F.settingsResult) {
      F.settingsResult.className = "settings-result error";
      F.settingsResult.textContent = data.portability_notices.join("\n");
    }
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

  function collectImageGenSettings() {
    return {
      image_gen_enabled: document.getElementById("imageGenEnabled").checked,
      image_gen_provider: document.getElementById("imageGenProvider").value,
      image_gen_api_key: document.getElementById("imageGenApiKey").value.trim(),
      image_gen_base_url: document.getElementById("imageGenBaseUrl").value.trim(),
      image_gen_fallback_urls: document.getElementById("imageGenFallbackUrls").value.trim(),
      image_gen_model: document.getElementById("imageGenModel").value.trim(),
      image_gen_default_size: document.getElementById("imageGenDefaultSize").value,
    };
  }

  function updateImageGenStatus(ready, enabled) {
    const pill = document.getElementById("imageGenStatus");
    if (!pill) return;
    if (!enabled) {
      pill.textContent = "生图未启用";
      pill.classList.remove("ready");
      return;
    }
    if (ready) {
      pill.textContent = "生图 API 已就绪";
      pill.classList.add("ready");
    } else {
      pill.textContent = "生图 API 未配置";
      pill.classList.remove("ready");
    }
  }

  function onImageGenProviderChange() {
    const provider = document.getElementById("imageGenProvider")?.value;
    const baseInput = document.getElementById("imageGenBaseUrl");
    if (!baseInput || baseInput.dataset.userEdited === "1") return;
    if (provider === "ark") {
      baseInput.value = "https://ark.cn-beijing.volces.com/api/v3";
    } else {
      baseInput.value = "https://next.zhima.world";
    }
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
    const btn = document.getElementById("pickWorkspaceBtn");
    F.workspaceResult.className = "settings-result";
    F.workspaceResult.textContent = "";

    if (!window.pywebview?.api?.pick_folder) {
      F.workspaceResult.className = "settings-result error";
      F.workspaceResult.textContent =
        "文件夹选择仅在桌面客户端（星期五.exe 或 python run.py）中可用。请直接在输入框填写路径，例如 D:/Documents/星期五，再点「保存」。";
      return;
    }

    if (btn) btn.disabled = true;
    F.workspaceResult.textContent = "正在打开文件夹选择…";

    try {
      const path = await window.pywebview.api.pick_folder(input.value.trim());
      if (path) {
        input.value = path;
        F.workspaceResult.className = "settings-result ok";
        F.workspaceResult.textContent = "已选择目录，请点击「保存」。";
      } else {
        F.workspaceResult.className = "settings-result";
        F.workspaceResult.textContent =
          "未选择文件夹（可能已取消）。也可直接在输入框填写路径，例如 D:/Documents/星期五，再点「保存」。";
      }
    } catch {
      F.workspaceResult.className = "settings-result error";
      F.workspaceResult.textContent =
        "打开文件夹选择器失败。请直接在输入框填写路径，例如 D:/Documents/星期五，再点「保存」。";
    } finally {
      if (btn) btn.disabled = false;
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
    F.appearanceResult.textContent = t("appearance.saving");
    const payload = {
      ui_language: document.getElementById("uiLanguage")?.value || "zh",
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
    F.appearanceResult.textContent = t("appearance.saved");
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

  async function saveImageGenSettings(event) {
    event.preventDefault();
    const resultEl = document.getElementById("imageGenResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "保存中...";
    }
    const payload = collectImageGenSettings();
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    document.getElementById("imageGenApiKey").value = "";
    document.getElementById("imageGenApiKeyHint").textContent = data.image_gen_api_key_masked
      ? `当前已保存: ${data.image_gen_api_key_masked}`
      : "尚未保存生图 API Key";
    updateImageGenStatus(data.image_gen_ready, data.image_gen_enabled);
    if (resultEl) {
      resultEl.className = "settings-result ok";
      resultEl.textContent = "生图设置已保存。";
    }
    void F.refreshStatusBar?.();
  }

  async function testImageGenSettings() {
    const resultEl = document.getElementById("imageGenResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "测试生图 API 中（可能需要 1～2 分钟）…";
    }
    const payload = collectImageGenSettings();
    if (!payload.image_gen_enabled) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "请先勾选「启用生图」。";
      }
      updateImageGenStatus(false, false);
      return;
    }
    if (!payload.image_gen_model) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "请先填写生图模型名称。";
      }
      updateImageGenStatus(false, payload.image_gen_enabled);
      return;
    }
    const res = await F.apiFetch("/api/settings/test-image-gen", {
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
      updateImageGenStatus(false, payload.image_gen_enabled);
      return;
    }

    const saveRes = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const saved = await saveRes.json();
    document.getElementById("imageGenApiKey").value = "";
    document.getElementById("imageGenApiKeyHint").textContent = saved.image_gen_api_key_masked
      ? `当前已保存: ${saved.image_gen_api_key_masked}`
      : "尚未保存生图 API Key";
    updateImageGenStatus(saved.image_gen_ready, saved.image_gen_enabled);
    if (resultEl) {
      resultEl.className = "settings-result ok";
      resultEl.textContent = `${data.message}（已自动保存）`;
    }
    void F.refreshStatusBar?.();
  }

  /* ── 设置面板切换 ── */

  function initSettingsInputFocus() {
    const modal = F.settingsModal;
    if (!modal || modal.dataset.focusBound === "1") return;
    modal.dataset.focusBound = "1";

    modal.addEventListener(
      "mousedown",
      (event) => {
        const input = event.target.closest?.(
          "input:not([type=checkbox]):not([type=radio]), textarea, select"
        );
        if (!input || !modal.contains(input)) return;
        event.stopPropagation();
        if (document.activeElement !== input) {
          input.focus({ preventScroll: true });
        }
      },
      true
    );
  }

  function openSettings(panel = "api") {
    initSettingsInputFocus();
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
    if (panel === "weixin") {
      void F.refreshWeixinSetup?.();
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
      preview.textContent = lines.length ? lines.join("\n") : t("logs.empty");
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
        resultEl.textContent = t("logs.opened");
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

  F.t = t;
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
  F.saveImageGenSettings = saveImageGenSettings;
  F.testImageGenSettings = testImageGenSettings;
  F.onImageGenProviderChange = onImageGenProviderChange;
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

  async function runPortableAudit() {
    const reportEl = document.getElementById("portableReport");
    const resultEl = document.getElementById("logsResult");
    if (reportEl) reportEl.textContent = "正在自检…";
    try {
      const res = await F.apiFetch("/api/portable/audit");
      const data = await res.json();
      const lines = (data.items || []).map((item) => {
        const mark = item.ok ? "✓" : "✗";
        return `${mark} ${item.label}${item.detail ? ` — ${item.detail}` : ""}`;
      });
      if (reportEl) reportEl.textContent = lines.join("\n") || "（无检查项）";
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "自检完成";
      }
    } catch {
      if (reportEl) reportEl.textContent = "自检失败，请稍后重试。";
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "自检失败";
      }
    }
  }

  async function exportPortableBundle() {
    const btn = document.getElementById("portableExportBtn");
    const resultEl = document.getElementById("logsResult");
    const includeSessions = document.getElementById("portableIncludeSessions")?.checked;
    if (btn) btn.disabled = true;
    if (resultEl) resultEl.textContent = "正在打包…";
    try {
      const res = await F.apiFetch("/api/portable/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ include_sessions: !!includeSessions }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "Friday-portable.zip";
      a.click();
      URL.revokeObjectURL(url);
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "配置包已下载";
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "导出失败";
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function importPortableBundle(file) {
    const resultEl = document.getElementById("logsResult");
    const reportEl = document.getElementById("portableReport");
    if (!file) return;
    if (resultEl) resultEl.textContent = "正在导入…";
    try {
      const zipBase64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const dataUrl = String(reader.result || "");
          resolve(dataUrl.split(",", 2)[1] || "");
        };
        reader.onerror = () => reject(new Error("读取文件失败"));
        reader.readAsDataURL(file);
      });
      const res = await F.apiFetch("/api/portable/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          zip_base64: zipBase64,
          filename: file.name || "Friday-portable.zip",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || String(res.status));
      const lines = [
        `已导入 ${(data.imported || []).length} 项`,
        data.backup_dir ? `备份：${data.backup_dir}` : "",
        ...(data.warnings || []),
      ].filter(Boolean);
      if (reportEl) reportEl.textContent = lines.join("\n");
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "导入完成，建议重启应用";
      }
      await loadSettings();
    } catch (err) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = err.message || "导入失败";
      }
    }
  }

  document.getElementById("portableAuditBtn")?.addEventListener("click", () => void runPortableAudit());
  document.getElementById("portableExportBtn")?.addEventListener("click", () => void exportPortableBundle());
  document.getElementById("portableImportBtn")?.addEventListener("click", () => {
    document.getElementById("portableImportInput")?.click();
  });
  document.getElementById("portableImportInput")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    void importPortableBundle(file);
  });

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
      resultEl.textContent = t("updates.checking");
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
          resultEl.textContent = t("updates.found", { latest: data.latest, current: data.current });
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
          resultEl.textContent = t("updates.latest", { version: data.current });
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
        resultEl.textContent = t("updates.fail");
      }
    }
  }

  document.getElementById("checkUpdateBtn")?.addEventListener("click", checkForUpdates);
  document.getElementById("viewChangelogBtn")?.addEventListener("click", () => {
    void F.showChangelogHistory?.();
  });
  loadAppVersion();
})();
