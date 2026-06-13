/* ================================================================= *
 *  settings.js — Friday 设置页：API / 文件夹 / 外观 / 数据移植与日志 / 安全与更新 + 主题
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
    const themeMode = mode || "light";
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
    applyTheme(data.theme || "light");
    applyFontSize(data.font_size || "medium");
    const lang = data.ui_language || "zh";
    window.FridayI18n?.setLanguage?.(lang);
    cacheUiPrefs(data.theme || "light", data.font_size || "medium", lang);
    F.refreshProviderLabels?.();
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

  let autostartBusy = false;

  function applyAutostartUi(data) {
    const checkbox = document.getElementById("launchAtLogon");
    const hint = document.getElementById("launchAtLogonHint");
    if (!checkbox) return;
    checkbox.disabled = data.launch_at_logon_available === false;
    checkbox.checked = !!data.launch_at_logon;
    if (hint) {
      hint.textContent = data.launch_at_logon_detail || "";
    }
  }

  async function toggleAutostart(enabled) {
    if (autostartBusy) return;
    autostartBusy = true;
    const checkbox = document.getElementById("launchAtLogon");
    const resultEl = document.getElementById("autostartResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = enabled ? "正在开启…" : "正在关闭…";
    }
    try {
      const res = await F.apiFetch("/api/autostart", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !!enabled }),
      });
      const data = await res.json();
      applyAutostartUi({
        launch_at_logon: !!data.enabled,
        launch_at_logon_available: data.available !== false,
        launch_at_logon_detail: data.detail || data.message || "",
      });
      if (resultEl) {
        resultEl.className = data.ok ? "settings-result ok" : "settings-result error";
        if (data.ok) {
          resultEl.textContent = data.enabled ? t("autostart.enabled") : t("autostart.disabled");
        } else {
          resultEl.textContent = data.message || t("autostart.failed");
          if (checkbox) checkbox.checked = !enabled;
        }
      } else if (!data.ok && checkbox) {
        checkbox.checked = !enabled;
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = t("autostart.failed");
      }
      if (checkbox) checkbox.checked = !enabled;
    } finally {
      autostartBusy = false;
    }
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

  async function loadSettings(options = {}) {
    const skipStartupTests = Boolean(options.skipStartupTests);
    const res = await F.apiFetchWithTimeout("/api/settings", {}, 15000);
    if (!res.ok) throw new Error(`加载设置失败 (${res.status})`);
    const data = await res.json();
    F.apiReady = data.api_ready;
    try {
      await F.initProviders?.(data);
    } catch (err) {
      console.warn("initProviders", err);
    }
    document.getElementById("baseUrl").value = data.base_url || "https://api.deepseek.com";
    const apiProxy = document.getElementById("apiProxy");
    if (apiProxy) apiProxy.value = data.api_proxy || "";
    const apiTrustEnv = document.getElementById("apiTrustEnv");
    if (apiTrustEnv) apiTrustEnv.checked = data.api_trust_env !== false;
    document.getElementById("workspace").value = data.workspace;
    document.getElementById("apiKeyHint").textContent = data.api_key_masked
      ? `当前已保存: ${data.api_key_masked}`
      : "尚未保存 API Key";
    const visionEnabled = document.getElementById("visionEnabled");
    if (visionEnabled) visionEnabled.checked = !!data.vision_enabled;
    applyVisionKeyHint(data);
    if (visionEnabled) {
      updateVisionStatus(data.vision_ready, data.vision_enabled, data.vision_status_hint);
    }
    const imageGenEnabled = document.getElementById("imageGenEnabled");
    if (imageGenEnabled) imageGenEnabled.checked = !!data.image_gen_enabled;
    const imageGenFallback = document.getElementById("imageGenFallbackUrls");
    if (imageGenFallback) imageGenFallback.value = data.image_gen_fallback_urls || "";
    const imageGenHint = document.getElementById("imageGenApiKeyHint");
    if (imageGenHint) {
      imageGenHint.textContent = data.image_gen_api_key_masked
        ? `当前已保存: ${data.image_gen_api_key_masked}`
        : "尚未保存生图 API Key";
    }
    if (imageGenEnabled) {
      updateImageGenStatus(
        data.image_gen_ready,
        data.image_gen_enabled,
        data.image_gen_status_hint || "",
      );
    }
    document.getElementById("themeMode").value = data.theme || "light";
    document.getElementById("fontSize").value = data.font_size || "medium";
    const langEl = document.getElementById("uiLanguage");
    if (langEl) langEl.value = data.ui_language || "zh";
    F.setInteractionMode?.(data.interaction_mode || "agent", { persist: false, skipYoloGate: true });
    void F.refreshYoloUnlockState?.();
    fillSecurityForm(data);
    applyAutostartUi(data);
    fillArtifactForm(data);
    fillContextSmartForm(data);
    void loadWorkspaceMemoryEditor();
    applyUiSettings(data);
    F.updateApiStatus(data.api_ready);
    F.bootSettingsSnapshot = data;
    F.applyStatusFromSettings?.(data);
    F.updateInputState();
    if (!skipStartupTests) {
      void F.runStartupApiTests?.();
    }
    if (Array.isArray(data.portability_notices) && data.portability_notices.length && F.settingsResult) {
      F.settingsResult.className = "settings-result error";
      F.settingsResult.textContent = data.portability_notices.join("\n");
    }
    return data;
  }

  /* ── 保存 ── */

  function collectNetworkSettings() {
    return {
      api_proxy: document.getElementById("apiProxy")?.value.trim() || "",
      api_trust_env: document.getElementById("apiTrustEnv")?.checked !== false,
    };
  }

  function collectSettings() {
    return {
      ...collectNetworkSettings(),
      ...F.collectCustomPayload?.("llm"),
      llm_provider: document.getElementById("llmProvider")?.value || "deepseek",
      api_key: document.getElementById("apiKey").value.trim(),
      base_url: document.getElementById("baseUrl").value.trim(),
      model: F.collectLlmModel?.() || document.getElementById("model")?.value || "",
      workspace: document.getElementById("workspace").value.trim(),
    };
  }

  function collectVisionSettings() {
    return {
      ...collectNetworkSettings(),
      ...F.collectCustomPayload?.("vision"),
      vision_enabled: document.getElementById("visionEnabled").checked,
      vision_provider: document.getElementById("visionProvider")?.value || "ark",
      vision_api_key: document.getElementById("visionApiKey").value.trim(),
      vision_base_url: document.getElementById("visionBaseUrl").value.trim(),
      vision_model: F.collectVisionModel?.() || "",
    };
  }

  function collectImageGenSettings() {
    return {
      ...collectNetworkSettings(),
      ...F.collectCustomPayload?.("image_gen"),
      image_gen_enabled: document.getElementById("imageGenEnabled").checked,
      image_gen_provider: document.getElementById("imageGenProvider").value,
      image_gen_api_key: document.getElementById("imageGenApiKey").value.trim(),
      image_gen_base_url: document.getElementById("imageGenBaseUrl").value.trim(),
      image_gen_fallback_urls: document.getElementById("imageGenFallbackUrls").value.trim(),
      image_gen_model: F.collectImageGenModel?.() || document.getElementById("imageGenModel")?.value.trim() || "",
    };
  }

  function updateImageGenStatus(ready, enabled, statusHint = "", verified = false) {
    const pill = document.getElementById("imageGenStatus");
    if (!pill) return;
    if (!enabled) {
      pill.textContent = "生图未启用";
      pill.classList.remove("ready");
      return;
    }
    if (verified) {
      pill.textContent = "生图 API 已验证";
      pill.classList.add("ready");
      return;
    }
    if (ready) {
      pill.textContent = "已配置 · 待测试";
      pill.classList.add("ready");
    } else {
      pill.textContent = statusHint || "生图 API 未配置";
      pill.classList.remove("ready");
    }
  }

  function onImageGenProviderChangeLegacy() {
    /* providers.js 已接管生图服务商切换 */
  }

  function updateVisionStatus(ready, enabled, statusHint = "", verified = false) {
    const pill = document.getElementById("visionStatus");
    if (!pill) return;
    if (!enabled) {
      pill.textContent = "视觉辅助未启用";
      pill.classList.remove("ready");
      window.Friday?.refreshStatusBar?.();
      return;
    }
    if (verified) {
      pill.textContent = "视觉 API 已验证";
      pill.classList.add("ready");
      window.Friday?.refreshStatusBar?.();
      return;
    }
    if (ready) {
      pill.textContent = "已配置 · 待测试";
      pill.classList.add("ready");
    } else {
      pill.textContent = statusHint || "视觉 API 未配置";
      pill.classList.remove("ready");
    }
    window.Friday?.refreshStatusBar?.();
  }

  function applyVisionKeyHint(data) {
    const hint = document.getElementById("visionApiKeyHint");
    if (!hint) return;
    const masked = data?.vision_api_key_masked;
    const base = masked ? `当前已保存: ${masked}` : "尚未保存视觉 API Key";
    const statusHint = data?.vision_status_hint || "";
    if (statusHint.includes("Key 格式不匹配")) {
      hint.textContent = `${base} · 火山方舟请改用 ark- 开头的 Key`;
      hint.classList.add("settings-hint-warn");
      return;
    }
    hint.classList.remove("settings-hint-warn");
    hint.textContent = base;
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
    await F.initProviders?.(data);
    F.settingsResult.className = "settings-result ok";
    F.settingsResult.textContent = "设置已保存。";
    F.updateInputState();
    F.applyStatusFromSettings?.(data);
    void F.refreshStatusBar?.();
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
    };
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    applyUiSettings(data);
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
    const res = await F.apiFetchWithTimeout("/api/settings/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, 60000);
    const data = await res.json();
    F.applyApiTestResult?.(F.settingsResult, data);
    if (data.ok) F.updateApiStatus(true);
    void F.refreshStatusBar?.();
  }

  function formatDiagnoseReport(report) {
    const sections = [
      ["对话大模型", report.llm],
      ["视觉 API", report.vision],
      ["生图 API", report.image_gen],
    ];
    const lines = [];
    for (const [title, block] of sections) {
      if (!block || !Array.isArray(block.steps) || !block.steps.length) continue;
      lines.push(`【${title}】${block.ok ? " ✓" : " ✗"}`);
      for (const step of block.steps) {
        const mark = step.ok ? "✓" : "✗";
        lines.push(`  ${mark} ${step.name}: ${step.detail}`);
        if (!step.ok && step.hint) lines.push(`     → ${step.hint}`);
      }
      lines.push("");
    }
    return lines.join("\n").trim();
  }

  async function diagnoseNetworkSettings() {
    F.settingsResult.className = "settings-result";
    F.settingsResult.textContent = "正在诊断网络（DNS / TCP / SSL）…";
    const payload = {
      ...collectSettings(),
      ...collectVisionSettings(),
      ...collectImageGenSettings(),
    };
    try {
      const res = await F.apiFetchWithTimeout("/api/settings/diagnose?full_api=false", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }, 90000);
      const data = await res.json();
      const text = formatDiagnoseReport(data);
      const allOk = data.llm?.ok && (!payload.vision_enabled || data.vision?.ok) && (!payload.image_gen_enabled || data.image_gen?.ok);
      F.settingsResult.className = allOk ? "settings-result ok" : "settings-result error";
      F.settingsResult.textContent = text || "诊断完成，无可用结果";
      void F.refreshStatusBar?.();
    } catch (err) {
      F.settingsResult.className = "settings-result error";
      F.settingsResult.textContent = `诊断请求失败：${err?.message || err}`;
    }
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
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = F.formatApiErrorResponse?.(res, data) || "保存失败，请重试。";
      }
      return;
    }
    document.getElementById("visionApiKey").value = "";
    applyVisionKeyHint(data);
    updateVisionStatus(data.vision_ready, data.vision_enabled, data.vision_status_hint);
    await F.initProviders?.(data);
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
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      if (res.status === 401) {
        await F.ensureApiToken?.();
      }
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = F.formatApiErrorResponse?.(res, data, { service: "视觉 API", context: "vision" })
          || F.formatErrorResult?.(data)
          || data.message
          || "视觉 API 测试失败";
      }
      const hint = payload.vision_provider === "ark" && payload.vision_api_key?.startsWith("sk-")
        ? "Key 格式不匹配：火山方舟需 ark- 开头"
        : (data.message || "");
      updateVisionStatus(false, payload.vision_enabled, hint);
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
    applyVisionKeyHint(saved);
    updateVisionStatus(saved.vision_ready, saved.vision_enabled, saved.vision_status_hint, true);
    await F.initProviders?.(saved);
    if (resultEl) {
      resultEl.className = "settings-result ok";
      resultEl.textContent = `${data.message}（已自动保存，对话中可识图）`;
    }
    void F.refreshStatusBar?.();
  }

  function markImageGenStatusBarOnline(detail = "") {
    F.patchImageGenStatus?.({
      image_gen_enabled: true,
      image_gen_configured: true,
      image_gen_online: true,
      image_gen_reach_detail: detail || "生图 API 已就绪",
    });
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
    updateImageGenStatus(
      data.image_gen_ready,
      data.image_gen_enabled,
      data.image_gen_status_hint || "",
    );
    if (data.image_gen_ready && data.image_gen_enabled) {
      markImageGenStatusBarOnline("生图 API 已就绪");
    }
    await F.initProviders?.(data);
    if (resultEl) {
      resultEl.className = "settings-result ok";
      resultEl.textContent = "生图设置已保存。";
    }
    void F.refreshStatusBar?.();
  }

  async function testImageGenSettings() {
    const resultEl = document.getElementById("imageGenResult");
    const btn = document.getElementById("testImageGenBtn");
    if (btn) btn.disabled = true;
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "正在验证生图端点与模型（约需半分钟至 2 分钟）…";
    }
    const payload = collectImageGenSettings();
    if (!payload.image_gen_enabled) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "请先勾选「启用生图」。";
      }
      updateImageGenStatus(false, false);
      if (btn) btn.disabled = false;
      return;
    }
    if (!payload.image_gen_model) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "请先填写生图模型名称。";
      }
      updateImageGenStatus(false, payload.image_gen_enabled, "请填写生图模型名称");
      if (btn) btn.disabled = false;
      return;
    }
    try {
      const res = await F.apiFetchWithTimeout("/api/settings/test-image-gen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }, 180000);
      const data = await res.json();
      if (!data.ok) {
        F.applyApiTestResult?.(resultEl, data);
        updateImageGenStatus(false, payload.image_gen_enabled, "测试未通过");
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
      updateImageGenStatus(saved.image_gen_ready, saved.image_gen_enabled, "", true);
      await F.initProviders?.(saved);
      if (saved.image_gen_ready && saved.image_gen_enabled) {
        markImageGenStatusBarOnline(data.message || "生图 API 已就绪");
      }
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = `${data.message}（已自动保存）`;
      }
      await F.refreshStatusBar?.({ force: true });
      if (saved.image_gen_ready && saved.image_gen_enabled) {
        markImageGenStatusBarOnline(data.message || "生图 API 已就绪");
      }
    } catch (err) {
      const timedOut = err?.name === "AbortError";
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = timedOut
          ? "生图测试超时（3 分钟）。端点可能响应过慢或不可达，请检查 Base URL 与模型名。"
          : "生图测试失败，请确认星期五后端已启动并重试。";
      }
      updateImageGenStatus(false, payload.image_gen_enabled, timedOut ? "测试超时" : "测试失败");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  /* ── 设置面板切换 ── */

  let settingsReturnFocus = null;

  const SETTINGS_FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function getSettingsNavTabs() {
    return Array.from(document.querySelectorAll(".settings-nav-item:not(:disabled)"));
  }

  function getVisibleSettingsFocusables() {
    const modal = F.settingsModal;
    if (!modal) return [];
    return Array.from(modal.querySelectorAll(SETTINGS_FOCUSABLE)).filter(
      (el) => el.offsetParent !== null
    );
  }

  function syncSettingsTabA11y(panel) {
    getSettingsNavTabs().forEach((btn) => {
      const selected = btn.dataset.panel === panel;
      btn.setAttribute("aria-selected", selected ? "true" : "false");
      btn.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll(".settings-section").forEach((section) => {
      const active = section.id === `panel-${panel}`;
      section.setAttribute("aria-hidden", active ? "false" : "true");
    });
  }

  function initSettingsA11y() {
    const modal = F.settingsModal;
    if (!modal || modal.dataset.a11yBound === "1") return;
    modal.dataset.a11yBound = "1";

    getSettingsNavTabs().forEach((btn) => {
      const panel = btn.dataset.panel;
      btn.setAttribute("role", "tab");
      btn.setAttribute("id", `settings-tab-${panel}`);
      btn.setAttribute("aria-controls", `panel-${panel}`);
      btn.addEventListener("keydown", (event) => {
        const tabs = getSettingsNavTabs();
        const idx = tabs.indexOf(btn);
        if (idx < 0) return;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") {
          event.preventDefault();
          const next = tabs[(idx + 1) % tabs.length];
          F.switchSettingsPanel(next.dataset.panel);
          next.focus();
        } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
          event.preventDefault();
          const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
          F.switchSettingsPanel(prev.dataset.panel);
          prev.focus();
        } else if (event.key === "Home") {
          event.preventDefault();
          F.switchSettingsPanel(tabs[0].dataset.panel);
          tabs[0].focus();
        } else if (event.key === "End") {
          event.preventDefault();
          const last = tabs[tabs.length - 1];
          F.switchSettingsPanel(last.dataset.panel);
          last.focus();
        }
      });
    });

    document.querySelectorAll(".settings-section").forEach((section) => {
      section.setAttribute("role", "tabpanel");
      const panelId = section.id.replace(/^panel-/, "");
      section.setAttribute("aria-labelledby", `settings-tab-${panelId}`);
    });

    modal.addEventListener("keydown", (event) => {
      if (event.key !== "Tab" || modal.classList.contains("hidden")) return;
      const nodes = getVisibleSettingsFocusables();
      if (nodes.length < 2) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

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

  function normalizeSettingsPanel(panel) {
    const aliases = {
      api: "llm",
      app: "about",
      logs: "about",
      "security-updates": "about",
      migration: "data",
    };
    return aliases[panel] || panel || "llm";
  }

  function openSettings(panel = "llm") {
    settingsReturnFocus = document.activeElement;
    initSettingsInputFocus();
    initSettingsA11y();
    switchSettingsPanel(normalizeSettingsPanel(panel));
    F.settingsModal.classList.remove("hidden");
    F.settingsModal.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => {
      document.querySelector(".settings-nav-item.active")?.focus();
    });
  }

  function closeSettings() {
    F.settingsModal.classList.add("hidden");
    F.settingsModal.setAttribute("aria-hidden", "true");
    const restore = settingsReturnFocus;
    settingsReturnFocus = null;
    if (restore && typeof restore.focus === "function") {
      restore.focus();
    }
  }

  function switchSettingsPanel(panel) {
    panel = normalizeSettingsPanel(panel);
    document.querySelectorAll(".settings-nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.panel === panel);
    });
    document.querySelectorAll(".settings-section").forEach((section) => {
      section.classList.toggle("active", section.id === `panel-${panel}`);
    });
    if (panel === "about") {
      void refreshLogPreview();
      void loadAppVersion();
    }
    if (panel === "data") {
      void refreshArtifactSummary();
    }
    if (panel === "agent") {
      void F.refreshPythonEnvStatus?.();
    }
    if (panel === "weixin") {
      void F.refreshWeixinSetup?.();
    }
    syncSettingsTabA11y(panel);
  }

  /* ── 数据移植 / 日志 ── */

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

  function initModelStatusPreview() {
    const modelEl = document.getElementById("model");
    const customEl = document.getElementById("llmModelCustom");
    const bind = (el) => {
      if (!el || el.dataset.statusBound === "1") return;
      el.dataset.statusBound = "1";
      el.addEventListener("change", () => {
        const model = (F.collectLlmModel?.() || el.value || "").trim();
        if (!model) return;
        F.patchStatusBar?.({ model, api_checking: true });
      });
      el.addEventListener("input", () => {
        const model = (F.collectLlmModel?.() || el.value || "").trim();
        if (!model) return;
        F.patchStatusBar?.({ model, api_checking: true });
      });
    };
    bind(modelEl);
    bind(customEl);
  }

  initModelStatusPreview();

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
  F.diagnoseNetworkSettings = diagnoseNetworkSettings;
  F.saveVisionSettings = saveVisionSettings;
  F.testVisionSettings = testVisionSettings;
  F.updateVisionStatus = updateVisionStatus;
  F.applyVisionKeyHint = applyVisionKeyHint;
  F.saveImageGenSettings = saveImageGenSettings;
  F.testImageGenSettings = testImageGenSettings;
  F.onImageGenProviderChangeLegacy = onImageGenProviderChangeLegacy;
  F.openSettings = openSettings;
  F.closeSettings = closeSettings;
  F.switchSettingsPanel = switchSettingsPanel;
  F.refreshLogPreview = refreshLogPreview;
  F.openLogFolder = openLogFolder;

  function formatBytes(n) {
    const num = Number(n) || 0;
    if (num < 1024) return `${num} B`;
    if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
    if (num < 1024 * 1024 * 1024) return `${(num / (1024 * 1024)).toFixed(1)} MB`;
    return `${(num / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  function fillArtifactForm(data) {
    const scratch = document.getElementById("artifactScratchTtlHours");
    const session = document.getElementById("artifactSessionTtlDays");
    const trash = document.getElementById("artifactTrashTtlDays");
    const autoGc = document.getElementById("artifactAutoGcEnabled");
    if (scratch) scratch.value = String(data.artifact_scratch_ttl_hours ?? 24);
    if (session) session.value = String(data.artifact_session_ttl_days ?? 30);
    if (trash) trash.value = String(data.artifact_trash_ttl_days ?? 7);
    if (autoGc) autoGc.checked = data.artifact_auto_gc_enabled !== false;
    void refreshArtifactSummary();
  }

  function artifactIsEmpty(data) {
    if (!data) return false;
    const active = Number(data.indexed_active_count) || 0;
    const trashed = Number(data.indexed_trashed_count) || 0;
    const dirBytes = Number(data.artifacts_dir_bytes) || 0;
    return active === 0 && trashed === 0 && dirBytes === 0;
  }

  function renderArtifactSummary(data) {
    const el = document.getElementById("artifactStorageSummary");
    const emptyEl = document.getElementById("artifactStorageEmpty");
    if (!el || !data) return;

    if (artifactIsEmpty(data)) {
      el.classList.add("hidden");
      emptyEl?.classList.remove("hidden");
      return;
    }

    el.classList.remove("hidden");
    emptyEl?.classList.add("hidden");
    el.textContent =
      `登记中 ${data.indexed_active_count} 个（${formatBytes(data.indexed_active_bytes)}）` +
      ` · 回收站 ${data.indexed_trashed_count} 个（${formatBytes(data.indexed_trashed_bytes)}）` +
      ` · artifacts 目录 ${formatBytes(data.artifacts_dir_bytes)}` +
      ` · trash 目录 ${formatBytes(data.trash_dir_bytes)}`;
  }

  async function refreshArtifactSummary() {
    const el = document.getElementById("artifactStorageSummary");
    const emptyEl = document.getElementById("artifactStorageEmpty");
    if (el) {
      el.classList.remove("hidden");
      el.textContent = t("settings.data.artifactsLoading") || "正在加载占用信息…";
    }
    emptyEl?.classList.add("hidden");
    try {
      const res = await F.apiFetch("/api/artifacts/summary");
      if (!res.ok) throw new Error("summary failed");
      const data = await res.json();
      renderArtifactSummary(data);
      return data;
    } catch {
      if (el) {
        el.classList.remove("hidden");
        el.textContent = t("settings.data.artifactsLoadError") || "无法加载占用信息。";
      }
      emptyEl?.classList.add("hidden");
      return null;
    }
  }

  async function saveArtifactPolicy() {
    const resultEl = document.getElementById("artifactStorageResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "保存中…";
    }
    const payload = {
      artifact_scratch_ttl_hours: Number(document.getElementById("artifactScratchTtlHours")?.value || 24),
      artifact_session_ttl_days: Number(document.getElementById("artifactSessionTtlDays")?.value || 30),
      artifact_trash_ttl_days: Number(document.getElementById("artifactTrashTtlDays")?.value || 7),
      artifact_auto_gc_enabled: document.getElementById("artifactAutoGcEnabled")?.checked !== false,
    };
    try {
      const res = await F.apiFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("save failed");
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "回收策略已保存。";
      }
      void refreshArtifactSummary();
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "保存失败。";
      }
    }
  }

  async function runArtifactGc() {
    const resultEl = document.getElementById("artifactStorageResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "正在回收…";
    }
    try {
      const res = await F.apiFetch("/api/artifacts/gc", { method: "POST" });
      const data = await res.json();
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent =
          `已移入回收站 ${data.trashed || 0} 个，永久删除 ${data.purged || 0} 个，释放约 ${formatBytes(data.bytes_freed || 0)}。`;
      }
      void refreshArtifactSummary();
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "回收失败。";
      }
    }
  }

  document.getElementById("openLogFolderBtn")?.addEventListener("click", openLogFolder);
  document.getElementById("refreshLogPreviewBtn")?.addEventListener("click", refreshLogPreview);
  document.getElementById("diagnosticsExportBtn")?.addEventListener("click", () => void exportDiagnosticBundle());
  document.getElementById("artifactRefreshSummaryBtn")?.addEventListener("click", () => {
    void refreshArtifactSummary();
  });
  document.getElementById("artifactRunGcBtn")?.addEventListener("click", () => {
    void runArtifactGc();
  });
  document.getElementById("artifactSavePolicyBtn")?.addEventListener("click", () => {
    void saveArtifactPolicy();
  });

  function fillContextSmartForm(data) {
    const smart = document.getElementById("contextSmartEnabled");
    const goal = document.getElementById("goalVerifierEnabled");
    const dream = document.getElementById("dreamMemoryEnabled");
    if (smart) smart.checked = data.context_smart_enabled !== false;
    if (goal) goal.checked = data.goal_verifier_enabled !== false;
    if (dream) dream.checked = !!data.dream_memory_enabled;
  }

  async function loadWorkspaceMemoryEditor() {
    const editor = document.getElementById("workspaceMemoryEditor");
    if (!editor) return;
    try {
      const res = await F.apiFetch("/api/workspace-memory");
      editor.value = res.content || "";
    } catch {
      editor.value = "";
    }
  }

  async function saveWorkspaceMemory() {
    const editor = document.getElementById("workspaceMemoryEditor");
    const resultEl = document.getElementById("workspaceMemoryResult");
    if (!editor) return;
    if (resultEl) resultEl.textContent = "保存中…";
    try {
      const res = await F.apiFetch("/api/workspace-memory", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editor.value }),
      });
      if (!res.ok) throw new Error("save failed");
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "工作区记忆已保存。";
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "保存失败。";
      }
    }
  }

  async function saveContextSmartSettings() {
    const resultEl = document.getElementById("contextSmartResult");
    const payload = {
      context_smart_enabled: document.getElementById("contextSmartEnabled")?.checked !== false,
      goal_verifier_enabled: document.getElementById("goalVerifierEnabled")?.checked !== false,
      dream_memory_enabled: document.getElementById("dreamMemoryEnabled")?.checked === true,
    };
    try {
      const res = await F.apiFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(String(res.status));
      if (resultEl) {
        resultEl.className = "settings-result success";
        resultEl.textContent = "上下文智能设置已保存。";
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "保存失败。";
      }
    }
  }

  document.getElementById("workspaceMemoryReloadBtn")?.addEventListener("click", () => {
    void loadWorkspaceMemoryEditor();
  });
  document.getElementById("workspaceMemorySaveBtn")?.addEventListener("click", () => {
    void saveWorkspaceMemory();
  });
  ["contextSmartEnabled", "goalVerifierEnabled", "dreamMemoryEnabled"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", () => {
      void saveContextSmartSettings();
    });
  });

  async function exportDiagnosticBundle() {
    const btn = document.getElementById("diagnosticsExportBtn");
    const resultEl = document.getElementById("logsResult");
    if (btn) btn.disabled = true;
    if (resultEl) resultEl.textContent = "正在打包诊断信息…";
    try {
      const res = await F.apiFetch("/api/diagnostics/export", { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^";]+)"?/i);
      const filename = match?.[1] || "Friday-diagnostic.zip";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      if (resultEl) {
        resultEl.className = "settings-result ok";
        resultEl.textContent = "诊断包已下载";
      }
    } catch {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = "导出诊断包失败";
      }
    } finally {
      if (btn) btn.disabled = false;
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

  document.getElementById("portableExportBtn")?.addEventListener("click", () => void exportPortableBundle());
  document.getElementById("portableImportBtn")?.addEventListener("click", () => {
    document.getElementById("portableImportInput")?.click();
  });
  document.getElementById("portableImportInput")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    void importPortableBundle(file);
  });

  document.querySelectorAll(".settings-goto-panel").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = btn.dataset.gotoPanel;
      if (panel) switchSettingsPanel(panel);
    });
  });

  document.getElementById("refreshPythonEnvBtn")?.addEventListener("click", () => void F.refreshPythonEnvStatus?.());
  document.getElementById("setupPythonEnvBtn")?.addEventListener("click", () => void F.setupPythonEnv?.());

  function renderRuntimeAbout(data) {
    const statusEl = document.getElementById("runtimeAboutStatus");
    const hintEl = document.getElementById("runtimeAboutHint");
    if (!statusEl) return;
    if (!data) {
      statusEl.textContent = "无法加载运行信息。";
      if (hintEl) hintEl.classList.add("hidden");
      return;
    }
    const lines = [
      data.run_mode_label ? `运行模式：${data.run_mode_label}` : "",
      data.main_process_name ? `主进程：${data.main_process_name}` : "",
      data.main_executable ? `路径：${data.main_executable}` : "",
      data.pid != null ? `PID：${data.pid}` : "",
      data.agent_runner_name ? `Agent 解释器：${data.agent_runner_name}` : "",
      data.agent_runner && data.agent_runner !== data.main_executable
        ? `Agent 路径：${data.agent_runner}`
        : "",
    ].filter(Boolean);
    statusEl.textContent = lines.join("\n") || "—";
    if (!hintEl) return;
    const hint = data.task_manager_hint || "";
    if (!hint) {
      hintEl.classList.add("hidden");
      hintEl.textContent = "";
      return;
    }
    hintEl.textContent = hint;
    hintEl.classList.remove("hidden");
    hintEl.classList.toggle("settings-hint-warn", data.run_mode === "dev");
  }

  async function loadAppVersion() {
    const label = document.getElementById("appVersionLabel");
    const sourceLink = document.getElementById("updateSourceLink");
    const statusEl = document.getElementById("runtimeAboutStatus");
    if (statusEl && !statusEl.dataset.loaded) {
      statusEl.textContent = "加载中…";
    }
    try {
      const res = await F.apiFetch("/api/version");
      const data = await res.json();
      if (label) label.textContent = data.version || "—";
      if (sourceLink) {
        if (data.gitee_pages_home) {
          sourceLink.href = data.gitee_pages_home;
          sourceLink.textContent = "官网（国内）";
        } else if (data.website_home) {
          sourceLink.href = data.website_home;
          sourceLink.textContent = "官网下载";
        } else if (data.gitee_home) {
          sourceLink.href = `${data.gitee_home}/releases`;
          sourceLink.textContent = "Gitee Releases";
        }
      }
      renderRuntimeAbout(data);
      if (statusEl) statusEl.dataset.loaded = "1";
    } catch {
      if (label) label.textContent = "—";
      renderRuntimeAbout(null);
    }
  }

  let lastUpdateInfo = null;
  let updatePollTimer = null;

  function formatUpdateFailure(data) {
    if (!data) return "更新失败，请稍后重试或使用「手动下载」。";
    if (F.formatErrorResult) {
      const merged = {
        message: data.result_message || data.message || data.detail || "",
        hint: data.hint || "",
        detail: data.detail || "",
      };
      const text = F.formatErrorResult(merged);
      if (text && text !== "未知错误") return text;
    }
    const parts = [];
    const main = data.result_message || data.message || "";
    const detail = data.detail || "";
    const hint = data.hint || "";
    if (main) parts.push(main);
    if (detail && detail !== main) parts.push(detail);
    if (hint && !parts.join("\n").includes(hint)) parts.push(hint);
    const log = Array.isArray(data.log) ? data.log.filter(Boolean) : [];
    if (log.length) {
      const tail = log[log.length - 1];
      if (tail && !parts.join("\n").includes(tail)) parts.push(`最近步骤：${tail}`);
    }
    return parts.filter(Boolean).join("\n") || "更新失败，请稍后重试或使用「手动下载」。";
  }

  /** 当前阶段进度（与 detail 文案一致）；percent 为全链路权重，下载时会对不上 MB。 */
  function resolveUpdateDisplayPercent(data) {
    const phase = data?.phase;
    const detail = String(data?.detail || "");
    if (phase === "downloading") {
      const mb = detail.match(/([\d.]+)\s*\/\s*([\d.]+)\s*MB/i);
      if (mb) {
        const read = parseFloat(mb[1]);
        const total = parseFloat(mb[2]);
        if (total > 0 && Number.isFinite(read)) {
          return Math.max(0, Math.min(100, Math.round((read / total) * 100)));
        }
      }
    }
    if (phase === "extracting") {
      const parts = detail.match(/(\d+)\s*\/\s*(\d+)/);
      if (parts) {
        const cur = parseInt(parts[1], 10);
        const total = parseInt(parts[2], 10);
        if (total > 0) {
          return Math.max(0, Math.min(100, Math.round((cur / total) * 100)));
        }
      }
    }
    return Math.max(0, Math.min(100, Number(data?.percent) || 0));
  }

  function renderUpdateProgress(data) {
    const wrap = document.getElementById("updateProgress");
    const fill = document.getElementById("updateProgressFill");
    const pctEl = document.getElementById("updateProgressPct");
    const msgEl = document.getElementById("updateProgressMsg");
    const detailEl = document.getElementById("updateProgressDetail");
    if (!wrap || !fill || !pctEl || !msgEl) return;
    const running = !!data?.running;
    if (!running && data?.ok === true) {
      wrap.classList.add("hidden");
      return;
    }
    const pct = resolveUpdateDisplayPercent(data);
    wrap.classList.remove("hidden");
    fill.style.width = `${pct}%`;
    fill.style.setProperty("--progress", `${pct}%`);
    pctEl.textContent = `${pct}%`;
    msgEl.textContent = data?.message || (running ? "正在更新…" : "");
    if (detailEl) {
      detailEl.textContent = data?.detail || "";
      detailEl.style.display = data?.detail ? "block" : "none";
    }
  }

  function stopUpdatePoll() {
    if (updatePollTimer) {
      clearInterval(updatePollTimer);
      updatePollTimer = null;
    }
  }

  async function pollUpdateApplyProgress() {
    try {
      const res = await F.apiFetchWithTimeout("/api/updates/apply/progress", {}, 15000);
      const data = await res.json();
      renderUpdateProgress(data);
      const resultEl = document.getElementById("updateResult");
      if (data.running && resultEl) {
        resultEl.className = "settings-result";
        resultEl.textContent = [data.message, data.detail].filter(Boolean).join(" · ");
      }
      if (!data.running) {
        stopUpdatePoll();
        const applyBtn = document.getElementById("applyUpdateBtn");
        const checkBtn = document.getElementById("checkUpdateBtn");
        if (applyBtn) applyBtn.disabled = false;
        if (checkBtn) checkBtn.disabled = false;
        if (data.ok === true) {
          if (resultEl) {
            resultEl.className = "settings-result ok";
            resultEl.textContent = data.result_message || data.message || "更新完成，正在重启…";
          }
          window.setTimeout(() => {
            try {
              window.pywebview?.api?.close_window?.();
            } catch {
              /* 后端 force exit 为主；此处仅作 UI 兜底 */
            }
          }, 400);
          return false;
        }
        if (data.ok === false && resultEl) {
          resultEl.className = "settings-result error";
          resultEl.textContent = formatUpdateFailure(data);
        }
        document.getElementById("updateProgress")?.classList.add("hidden");
        return false;
      }
      return true;
    } catch (err) {
      const resultEl = document.getElementById("updateResult");
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = err?.name === "AbortError"
          ? "读取更新进度超时，请查看是否已在后台下载；若长时间无响应请重试。"
          : `无法获取更新进度：${err?.message || "网络异常"}`;
      }
      return false;
    }
  }

  function startUpdatePoll() {
    stopUpdatePoll();
    void pollUpdateApplyProgress();
    updatePollTimer = setInterval(() => {
      void pollUpdateApplyProgress();
    }, 800);
  }

  async function startApplyUpdate(info, options = {}) {
    const requireConfirm = options.requireConfirm !== false;
    if (!info?.update_available || !info.download_url) return false;
    if (!info.can_auto_update) {
      const resultEl = document.getElementById("updateResult");
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = info.auto_update_hint || "当前环境不支持一键更新，请使用手动下载。";
      }
      return false;
    }
    if (requireConfirm) {
      const confirmed = window.confirm(
        `即将下载并安装版本 ${info.latest}，完成后会自动重启星期五。\n\n更新过程中请勿关闭电脑，是否继续？`,
      );
      if (!confirmed) return false;
    }
    lastUpdateInfo = info;

    const applyBtn = document.getElementById("applyUpdateBtn");
    const checkBtn = document.getElementById("checkUpdateBtn");
    const resultEl = document.getElementById("updateResult");
    if (applyBtn) applyBtn.disabled = true;
    if (checkBtn) checkBtn.disabled = true;
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = "正在准备更新…";
    }
    renderUpdateProgress({
      running: true,
      phase: "starting",
      percent: 0,
      message: "正在启动更新…",
      detail: "下载完成后将自动替换程序并重启",
    });
    try {
      const res = await F.apiFetchWithTimeout("/api/updates/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          download_url: info.download_url,
          version: info.latest,
          expected_sha256: info.download_sha256 || "",
        }),
      }, 30000);
      const data = await res.json().catch(() => ({}));
      if (!data.started) {
        if (resultEl) {
          resultEl.className = "settings-result error";
          resultEl.textContent = formatUpdateFailure(data);
        }
        document.getElementById("updateProgress")?.classList.add("hidden");
        if (applyBtn) applyBtn.disabled = false;
        if (checkBtn) checkBtn.disabled = false;
        return false;
      }
      if (data.already_running) {
        if (resultEl) resultEl.textContent = "更新已在进行中…";
      }
      startUpdatePoll();
    } catch (err) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = err?.name === "AbortError"
          ? "启动更新超时，请检查网络后重试。"
          : `无法启动更新：${err?.message || "请确认星期五后端正在运行"}`;
      }
      document.getElementById("updateProgress")?.classList.add("hidden");
      if (applyBtn) applyBtn.disabled = false;
      if (checkBtn) checkBtn.disabled = false;
      return false;
    }
    return true;
  }

  async function applyUpdate() {
    const info = lastUpdateInfo;
    if (!info?.update_available || !info.download_url) {
      await checkForUpdates();
      return;
    }
    await startApplyUpdate(info);
  }

  async function checkForUpdates() {
    const resultEl = document.getElementById("updateResult");
    const downloadLink = document.getElementById("downloadUpdateLink");
    const applyBtn = document.getElementById("applyUpdateBtn");
    const sourceLink = document.getElementById("updateSourceLink");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = t("updates.checking");
    }
    applyBtn?.classList.add("hidden");
    try {
      const res = await F.apiFetch("/api/updates/check");
      const data = await res.json();
      lastUpdateInfo = data;
      if (data.last_apply_failed && data.last_apply_hint && resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = data.last_apply_hint;
      }
      if (!data.checked) {
        if (resultEl) resultEl.textContent = "无法读取更新源配置";
        downloadLink?.classList.add("hidden");
        return;
      }
      if (data.update_available) {
        if (resultEl) {
          resultEl.className = "settings-result ok";
          const hint = data.can_auto_update
            ? "可点「一键更新并重启」自动完成，无需手动解压。"
            : (data.auto_update_hint || "请下载 zip 后覆盖解压。");
          resultEl.textContent = `${t("updates.found", { latest: data.latest, current: data.current })}\n${hint}`;
        }
        if (applyBtn && data.can_auto_update && data.download_url) {
          applyBtn.classList.remove("hidden");
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
    } catch (err) {
      if (resultEl) {
        resultEl.className = "settings-result error";
        resultEl.textContent = err?.name === "AbortError"
          ? "检查更新超时，请检查网络后重试。"
          : t("updates.fail");
      }
    }
  }

  F.checkForUpdates = checkForUpdates;
  F.startApplyUpdate = startApplyUpdate;

  document.getElementById("checkUpdateBtn")?.addEventListener("click", checkForUpdates);
  document.getElementById("applyUpdateBtn")?.addEventListener("click", () => void applyUpdate());
  document.getElementById("launchAtLogon")?.addEventListener("change", (event) => {
    void toggleAutostart(event.target.checked);
  });
  document.getElementById("viewChangelogBtn")?.addEventListener("click", () => {
    void F.showChangelogHistory?.();
  });
  loadAppVersion();
})();
