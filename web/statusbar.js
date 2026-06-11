/* ================================================================= *
 *  statusbar.js — 底部状态栏（参考 Reasonix）
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) {
    console.error("statusbar.js: window.Friday 未初始化");
    return;
  }

  const POLL_MS = 30000;
  const REFRESH_TIMEOUT_MS = 12000;
  let pollTimer = null;
  let refreshInFlight = null;
  let bootPhase = true;
  let startupTestsStarted = false;
  const startupTestPending = {
    api: false,
    vision: false,
    imageGen: false,
  };

  const SERVICE_LABELS = {
    api: {
      unconfigured: () => F.t?.("status.api.unconfigured") || "API 未配置",
      online: () => F.t?.("status.api.online") || "API 在线",
      offline: () => F.t?.("status.api.offline") || "API 离线",
      checking: () => F.t?.("status.api.checking") || "API 检测中",
      checkingHint: () => F.t?.("status.api.checkingHint") || "正在检测连接…",
      disabled: () => F.t?.("status.api.offline") || "API 离线",
    },
    vision: {
      disabled: () => F.t?.("status.vision.disabled") || "视觉 关",
      unconfigured: () => F.t?.("status.vision.unconfigured") || "视觉 未配置",
      online: () => F.t?.("status.vision.on") || "视觉 在线",
      offline: () => F.t?.("status.vision.off") || "视觉 离线",
      checking: () => F.t?.("status.vision.checking") || "视觉 检测中",
      checkingHint: () => F.t?.("status.vision.checkingHint") || "正在检测视觉 API…",
    },
    imageGen: {
      disabled: () => F.t?.("status.imageGen.disabled") || "生图 关",
      unconfigured: () => F.t?.("status.imageGen.unconfigured") || "生图 未配置",
      online: () => F.t?.("status.imageGen.on") || "生图 在线",
      offline: () => F.t?.("status.imageGen.off") || "生图 离线",
      checking: () => F.t?.("status.imageGen.checking") || "生图 检测中",
      checkingHint: () => F.t?.("status.imageGen.checkingHint") || "正在检测生图 API…",
    },
    gateway: {
      disabled: () => F.t?.("status.gateway.disabled") || "微信 关",
      unconfigured: () => F.t?.("status.gateway.unconfigured") || "微信 未配置",
      online: () => F.t?.("status.gateway.on") || "Gateway 在线",
      offline: () => F.t?.("status.gateway.off") || "Gateway 离线",
      checking: () => F.t?.("status.gateway.checking") || "Gateway 检测中",
      checkingHint: () => F.t?.("status.gateway.checkingHint") || "正在检测 OpenClaw Gateway…",
    },
  };

  function resolveLabels(labels) {
    const out = {};
    Object.entries(labels).forEach(([key, value]) => {
      out[key] = typeof value === "function" ? value() : value;
    });
    return out;
  }

  const els = {
    apiDot: document.getElementById("statusApiDot"),
    apiText: document.getElementById("statusApiText"),
    visionDot: document.getElementById("statusVisionDot"),
    visionText: document.getElementById("statusVisionText"),
    imageGenDot: document.getElementById("statusImageGenDot"),
    imageGenText: document.getElementById("statusImageGenText"),
    gatewayDot: document.getElementById("statusGatewayDot"),
    gatewayText: document.getElementById("statusGatewayText"),
    tokens: document.getElementById("statusTokens"),
    tasks: document.getElementById("statusTasks"),
    workspace: document.getElementById("statusWorkspace"),
    model: document.getElementById("statusModel"),
  };

  function formatTokens(n) {
    const num = Number(n) || 0;
    if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
    return String(num);
  }

  function workspaceLabel(path) {
    if (!path) return "workspace";
    const parts = String(path).replace(/\\/g, "/").split("/").filter(Boolean);
    return parts[parts.length - 1] || path;
  }

  function setDot(el, state) {
    if (!el) return;
    el.dataset.state = state;
  }

  function applyUsage(usage) {
    if (!usage || els.tokens == null) return;
    if (usage.tokens_total != null) {
      els.tokens.textContent = formatTokens(usage.tokens_total);
    }
  }

  function applyServiceState({
    enabled,
    configured,
    online,
    checking,
    detail,
    dotEl,
    textEl,
    labels,
  }) {
    if (!dotEl || !textEl) return;
    dotEl.title = detail || "";

    if (!enabled) {
      setDot(dotEl, "disabled");
      textEl.textContent = labels.disabled;
      return;
    }
    if (!configured) {
      setDot(dotEl, "disabled");
      textEl.textContent = labels.unconfigured;
      return;
    }
    if (checking) {
      setDot(dotEl, "checking");
      textEl.textContent = labels.checking || labels.offline;
      return;
    }
    setDot(dotEl, online ? "online" : "offline");
    textEl.textContent = online ? labels.online : labels.offline;
  }

  function shouldSkipServiceRefresh() {
    return bootPhase
      || startupTestPending.api
      || startupTestPending.vision
      || startupTestPending.imageGen;
  }

  function finishBootIfIdle() {
    if (!startupTestPending.api && !startupTestPending.vision && !startupTestPending.imageGen) {
      bootPhase = false;
      void refreshStatusBar({ force: true });
    }
  }

  function setBootCheckingState() {
    const checkingLabels = resolveLabels(SERVICE_LABELS.api);
    applyServiceState({
      enabled: true,
      configured: true,
      online: false,
      checking: true,
      detail: checkingLabels.checkingHint,
      dotEl: els.apiDot,
      textEl: els.apiText,
      labels: checkingLabels,
    });
    applyServiceState({
      enabled: true,
      configured: true,
      online: false,
      checking: true,
      detail: resolveLabels(SERVICE_LABELS.vision).checkingHint,
      dotEl: els.visionDot,
      textEl: els.visionText,
      labels: resolveLabels(SERVICE_LABELS.vision),
    });
    applyServiceState({
      enabled: true,
      configured: true,
      online: false,
      checking: true,
      detail: resolveLabels(SERVICE_LABELS.imageGen).checkingHint,
      dotEl: els.imageGenDot,
      textEl: els.imageGenText,
      labels: resolveLabels(SERVICE_LABELS.imageGen),
    });
  }

  function applyPayload(data) {
    if (!data) return;

    if (!shouldSkipServiceRefresh()) {
      applyServiceState({
        enabled: true,
        configured: Boolean(data.api_configured),
        online: Boolean(data.api_online),
        checking: Boolean(data.api_checking),
        detail: data.api_reach_detail || "",
        dotEl: els.apiDot,
        textEl: els.apiText,
        labels: resolveLabels(SERVICE_LABELS.api),
      });

      applyServiceState({
        enabled: Boolean(data.vision_enabled),
        configured: Boolean(data.vision_configured),
        online: Boolean(data.vision_online),
        checking: Boolean(data.vision_checking),
        detail: data.vision_reach_detail || "",
        dotEl: els.visionDot,
        textEl: els.visionText,
        labels: resolveLabels(SERVICE_LABELS.vision),
      });

      applyServiceState({
        enabled: Boolean(data.image_gen_enabled),
        configured: Boolean(data.image_gen_configured),
        online: Boolean(data.image_gen_online),
        checking: Boolean(data.image_gen_checking),
        detail: data.image_gen_reach_detail || "",
        dotEl: els.imageGenDot,
        textEl: els.imageGenText,
        labels: resolveLabels(SERVICE_LABELS.imageGen),
      });

      applyServiceState({
        enabled: Boolean(data.gateway_enabled),
        configured: Boolean(data.gateway_configured),
        online: Boolean(data.gateway_online),
        checking: Boolean(data.gateway_checking),
        detail: data.gateway_reach_detail || "",
        dotEl: els.gatewayDot,
        textEl: els.gatewayText,
        labels: resolveLabels(SERVICE_LABELS.gateway),
      });
    }

    refreshStatusBarMeta(data);
  }

  function patchImageGenStatus(partial = {}) {
    if (!partial) return;
    const enabled = partial.image_gen_enabled ?? Boolean(
      document.getElementById("imageGenEnabled")?.checked
    );
    const configured = partial.image_gen_configured ?? (
      enabled && Boolean(partial.image_gen_ready ?? partial.image_gen_configured)
    );
    if (partial.image_gen_checking) {
      applyServiceState({
        enabled,
        configured: configured || enabled,
        online: false,
        checking: true,
        detail: partial.image_gen_reach_detail || F.t?.("status.imageGen.checkingHint") || "正在检测生图 API…",
        dotEl: els.imageGenDot,
        textEl: els.imageGenText,
        labels: {
          disabled: F.t?.("status.imageGen.disabled") || "生图 关",
          unconfigured: F.t?.("status.imageGen.unconfigured") || "生图 未配置",
          online: F.t?.("status.imageGen.on") || "生图 在线",
          offline: F.t?.("status.imageGen.checking") || "生图 检测中",
        },
      });
      return;
    }
    if (partial.image_gen_online != null || partial.image_gen_configured != null) {
      applyServiceState({
        enabled,
        configured: partial.image_gen_configured ?? configured,
        online: Boolean(partial.image_gen_online),
        detail: partial.image_gen_reach_detail || "",
        dotEl: els.imageGenDot,
        textEl: els.imageGenText,
        labels: {
          disabled: F.t?.("status.imageGen.disabled") || "生图 关",
          unconfigured: F.t?.("status.imageGen.unconfigured") || "生图 未配置",
          online: F.t?.("status.imageGen.on") || "生图 在线",
          offline: F.t?.("status.imageGen.off") || "生图 离线",
        },
      });
    }
  }

  function patchStatusBar(partial) {
    if (!partial) return;
    if (partial.model && els.model) {
      els.model.textContent = partial.model;
    }
    if (partial.workspace && els.workspace) {
      els.workspace.textContent = partial.workspace;
    }
    if (partial.api_reach_detail && els.apiDot) {
      els.apiDot.title = partial.api_reach_detail;
    }
    if (partial.api_checking && els.apiDot && els.apiText) {
      setDot(els.apiDot, "checking");
      els.apiText.textContent = F.t?.("status.api.checking") || "API 检测中";
      els.apiDot.title = F.t?.("status.api.checkingHint") || "正在检测新模型连接…";
    }
    if (partial.tokens_total != null && els.tokens) {
      els.tokens.textContent = formatTokens(partial.tokens_total);
    }
  }

  function statusBarQuery(sessionId, extra = {}) {
    const params = new URLSearchParams();
    if (sessionId) params.set("session_id", sessionId);
    Object.entries(extra).forEach(([key, value]) => {
      if (value != null && value !== false) params.set(key, "1");
    });
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }

  function applyFromSettings(data) {
    if (!data) return;
    const imageGenEnabled = Boolean(data.image_gen_enabled);
    const imageGenReady = Boolean(data.image_gen_enabled && data.image_gen_ready);
    const apiReady = Boolean(data.api_ready);
    const visionOn = Boolean(data.vision_enabled);
    const visionReady = Boolean(data.vision_enabled && data.vision_ready);

    applyServiceState({
      enabled: true,
      configured: apiReady,
      online: false,
      checking: apiReady,
      detail: apiReady ? "正在检测连接…" : "",
      dotEl: els.apiDot,
      textEl: els.apiText,
      labels: resolveLabels(SERVICE_LABELS.api),
    });

    applyServiceState({
      enabled: visionOn,
      configured: visionReady,
      online: false,
      checking: visionOn && visionReady,
      detail: visionOn && visionReady ? "正在检测视觉 API…" : "",
      dotEl: els.visionDot,
      textEl: els.visionText,
      labels: resolveLabels(SERVICE_LABELS.vision),
    });

    applyServiceState({
      enabled: imageGenEnabled,
      configured: imageGenReady,
      online: false,
      checking: imageGenReady,
      detail: imageGenReady ? "正在检测生图 API…" : "",
      dotEl: els.imageGenDot,
      textEl: els.imageGenText,
      labels: resolveLabels(SERVICE_LABELS.imageGen),
    });

    if (els.workspace) {
      els.workspace.textContent = workspaceLabel(data.workspace);
      if (data.workspace) els.workspace.title = data.workspace;
    }
    if (els.model) {
      els.model.textContent = data.model || "—";
    }
  }

  function refreshStatusBarMeta(data) {
    if (!data) return;
    if (els.tokens && data.tokens_total != null) {
      els.tokens.textContent = formatTokens(data.tokens_total);
    }
    if (els.tasks && data.tasks != null) {
      els.tasks.textContent = String(data.tasks);
    }
    if (els.workspace) {
      const label = data.workspace || workspaceLabel(data.workspace_path);
      els.workspace.textContent = label;
      if (data.workspace_path) els.workspace.title = data.workspace_path;
    }
    if (els.model && data.model) {
      els.model.textContent = data.model;
    }
  }

  async function runServiceStartupTest({
    pendingKey,
    enabled,
    configured,
    url,
    timeoutMs,
    dotEl,
    textEl,
    labels,
  }) {
    if (!enabled) {
      applyServiceState({
        enabled: false,
        configured: false,
        online: false,
        checking: false,
        detail: "",
        dotEl,
        textEl,
        labels,
      });
      return;
    }
    if (!configured) {
      applyServiceState({
        enabled: true,
        configured: false,
        online: false,
        checking: false,
        detail: "",
        dotEl,
        textEl,
        labels,
      });
      return;
    }

    startupTestPending[pendingKey] = true;
    applyServiceState({
      enabled: true,
      configured: true,
      online: false,
      checking: true,
      detail: labels.checkingHint || "",
      dotEl,
      textEl,
      labels,
    });

    try {
      const res = await F.apiFetchWithTimeout(
        url,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        },
        timeoutMs,
      );
      const data = await res.json().catch(() => ({}));
      const detail = F.formatErrorResult?.(data) || String(data.message || "").split("\n")[0] || "";
      applyServiceState({
        enabled: true,
        configured: true,
        online: Boolean(data.ok),
        checking: false,
        detail,
        dotEl,
        textEl,
        labels,
      });
    } catch (err) {
      applyServiceState({
        enabled: true,
        configured: true,
        online: false,
        checking: false,
        detail: err?.message || "检测失败",
        dotEl,
        textEl,
        labels,
      });
    } finally {
      startupTestPending[pendingKey] = false;
      finishBootIfIdle();
    }
  }

  async function refreshStatusBarMetaOnly() {
    const sessionId = F.activeSessionId || "";
    try {
      const res = await F.apiFetchWithTimeout(
        `/api/status-bar${statusBarQuery(sessionId, { cached_only: true })}`,
        {},
        3000,
      );
      if (res.ok) refreshStatusBarMeta(await res.json());
    } catch {
      // 保留已有状态
    }
  }

  async function runStartupApiTests() {
    if (!F.resolveApiToken?.()) return;
    if (startupTestsStarted) return;
    startupTestsStarted = true;

    const snap = F.bootSettingsSnapshot || {};
    const apiReady = Boolean(snap.api_ready);
    const visionOn = Boolean(snap.vision_enabled);
    const visionReady = Boolean(snap.vision_enabled && snap.vision_ready);
    const imageGenOn = Boolean(snap.image_gen_enabled);
    const imageGenReady = Boolean(snap.image_gen_enabled && snap.image_gen_ready);

    if (apiReady) startupTestPending.api = true;
    if (visionOn && visionReady) startupTestPending.vision = true;
    if (imageGenOn && imageGenReady) startupTestPending.imageGen = true;

    void refreshStatusBarMetaOnly();

    void runServiceStartupTest({
      pendingKey: "api",
      enabled: true,
      configured: apiReady,
      url: "/api/settings/test",
      timeoutMs: 60000,
      dotEl: els.apiDot,
      textEl: els.apiText,
      labels: resolveLabels(SERVICE_LABELS.api),
    });

    void runServiceStartupTest({
      pendingKey: "vision",
      enabled: visionOn,
      configured: visionReady,
      url: "/api/settings/test-vision",
      timeoutMs: 60000,
      dotEl: els.visionDot,
      textEl: els.visionText,
      labels: resolveLabels(SERVICE_LABELS.vision),
    });

    void runServiceStartupTest({
      pendingKey: "imageGen",
      enabled: imageGenOn,
      configured: imageGenReady,
      url: "/api/settings/test-image-gen",
      timeoutMs: 120000,
      dotEl: els.imageGenDot,
      textEl: els.imageGenText,
      labels: resolveLabels(SERVICE_LABELS.imageGen),
    });

    if (!startupTestPending.api && !startupTestPending.vision && !startupTestPending.imageGen) {
      bootPhase = false;
    }
  }

  async function refreshStatusBar(options = {}) {
    if (!F.resolveApiToken?.()) return;
    if (refreshInFlight && !options.force) return refreshInFlight;
    refreshInFlight = (async () => {
      const sessionId = F.activeSessionId || "";
      const baseQs = statusBarQuery(sessionId);
      const skipServices = shouldSkipServiceRefresh();

      if (!options.skipQuick) {
        try {
          const quickRes = await F.apiFetchWithTimeout(
            `/api/status-bar${statusBarQuery(sessionId, { cached_only: true })}`,
            {},
            3000,
          );
          if (quickRes.ok) {
            const data = await quickRes.json();
            if (skipServices) refreshStatusBarMeta(data);
            else applyPayload(data);
          }
        } catch {
          // 保留已有状态
        }
      }
      if (skipServices) return;
      try {
        const res = await F.apiFetchWithTimeout(`/api/status-bar${baseQs}`, {}, REFRESH_TIMEOUT_MS);
        if (!res.ok) return;
        applyPayload(await res.json());
      } catch {
        // 保留已有状态
      }
    })();
    try {
      await refreshInFlight;
    } finally {
      refreshInFlight = null;
    }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => void refreshStatusBar(), POLL_MS);
  }

  F.applyStatusFromSettings = applyFromSettings;
  F.applyStatusUsage = applyUsage;
  F.patchStatusBar = patchStatusBar;
  F.patchImageGenStatus = patchImageGenStatus;
  F.refreshStatusBar = refreshStatusBar;
  F.runStartupApiTests = runStartupApiTests;
  F.isStatusBarBooting = shouldSkipServiceRefresh;

  setBootCheckingState();
  startPolling();
  window.addEventListener("friday:languagechange", () => void refreshStatusBar());
})();
