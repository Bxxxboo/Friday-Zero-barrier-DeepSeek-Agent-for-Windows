/* ================================================================= *
 *  app.js — Friday 入口：事件绑定 / 桌面窗 / 视口修复 / 启动
 *  所有子模块通过 window.Friday 命名空间通信
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) {
    console.error("app.js: window.Friday 未初始化");
    return;
  }

  /* ── 启动（优先执行，避免后续绑定异常导致永远卡在加载页） ── */

  async function bootstrap() {
    const overlay = document.getElementById("appBootOverlay");
    const setBootText = (text) => {
      const hint = overlay?.querySelector("p");
      if (hint) hint.textContent = text;
    };
    const hideOverlay = () => overlay?.classList.add("hidden");

    const bootWork = async () => {
      setBootText("正在同步数据…");
      await F.migrateLocalStorageSessions();
      setBootText("正在加载对话…");
      await F.fetchSessions();
      setBootText("正在检查服务…");
      try {
        await F.loadSettings?.();
      } catch (err) {
        console.warn("loadSettings", err);
      }
      const health = await F.apiFetchWithTimeout("/api/health", {}, 8000);
      if (!health.ok) throw new Error(`服务未就绪 (${health.status})`);
    };

    try {
      F.setConnectionStatus("正在加载...", false);
      await Promise.race([
        bootWork(),
        new Promise((_, reject) => {
          setTimeout(() => reject(new Error("加载超时，请关闭后重新打开")), 30000);
        }),
      ]);
      hideOverlay();
      F.connectWs();
      F.updateInputState();
      void F.checkOnboarding?.().catch((err) => console.warn("checkOnboarding", err)).finally(() => {
        setTimeout(() => void F.checkReleaseNotes?.(), 400);
      });
      void F.refreshStatusBar?.();
    } catch (err) {
      console.error(err);
      const detail = err?.message || String(err);
      F.setConnectionStatus("加载失败，请重启应用", false);
      const hint = overlay?.querySelector("p");
      if (hint) {
        hint.textContent =
          detail.includes("401") || detail.includes("Unauthorized")
            ? "加载失败：认证未通过，请完全关闭后重新打开"
            : detail.slice(0, 100);
      }
    }
  }

  bootstrap();

  F.bindModeSwitch?.();

  /* ── 事件绑定 ── */

  F.sendBtn?.addEventListener("click", () => {
    void F.sendChat(F.chatInput?.value || "");
    if (F.chatInput) F.chatInput.value = "";
  });

  F.chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void F.sendChat(F.chatInput.value);
      F.chatInput.value = "";
    }
  });

  F.chatInput?.addEventListener("input", () => F.updateInputState());

  F.stopBtn?.addEventListener("click", () => F.stopChat());

  document.getElementById("newChatBtn")?.addEventListener("click", () => F.createSession(true));
  document.getElementById("openSettingsBtn")?.addEventListener("click", () => F.openSettings("api"));
  document.getElementById("closeSettingsBtn")?.addEventListener("click", () => F.closeSettings());

  F.settingsModal?.addEventListener("click", (event) => {
    if (event.target === F.settingsModal) F.closeSettings();
  });

  document.querySelectorAll(".settings-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => F.switchSettingsPanel(btn.dataset.panel));
  });

  F.welcomePanel?.addEventListener("click", (event) => {
    const actionBtn = event.target.closest("[data-action]");
    if (actionBtn?.dataset.action === "schedules") {
      F.openSchedulesSettings?.();
      return;
    }
    if (actionBtn?.dataset.action === "extensions") {
      F.openExtensionsSettings?.();
      return;
    }
    const chip = event.target.closest(".chip");
    if (!chip) return;
    const prompt = chip.dataset.prompt;
    if (prompt) void F.sendChat(prompt);
  });

  document.getElementById("testBtn")?.addEventListener("click", F.testSettings);
  document.getElementById("testVisionBtn")?.addEventListener("click", F.testVisionSettings);

  F.settingsForm?.addEventListener("submit", F.saveSettings);
  document.getElementById("visionForm")?.addEventListener("submit", F.saveVisionSettings);
  document.getElementById("testImageGenBtn")?.addEventListener("click", F.testImageGenSettings);
  document.getElementById("imageGenForm")?.addEventListener("submit", F.saveImageGenSettings);
  document.getElementById("imageGenBaseUrl")?.addEventListener("input", (e) => {
    e.target.dataset.userEdited = e.target.value.trim() ? "1" : "";
  });
  document.getElementById("imageGenProvider")?.addEventListener("change", F.onImageGenProviderChange);
  F.workspaceForm?.addEventListener("submit", F.saveWorkspace);
  document.getElementById("pickWorkspaceBtn")?.addEventListener("click", F.pickWorkspaceFolder);
  F.appearanceForm?.addEventListener("submit", F.saveAppearanceSettings);
  F.securityForm?.addEventListener("submit", F.saveSecuritySettings);

  document.getElementById("applyStrictPresetBtn")?.addEventListener("click", F.applyStrictSecurityPreset);

  F.initThemeWatcher?.();

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (!F.onboardingModal?.classList.contains("hidden")) return;
      const historyDrawer = document.getElementById("historyDrawer");
      if (historyDrawer && !historyDrawer.classList.contains("hidden")) {
        F.closeHistory?.();
        return;
      }
      if (F.settingsModal && !F.settingsModal.classList.contains("hidden")) F.closeSettings();
    }
  });

  /* ── 桌面窗（frameless） ── */

  let windowMaximized = false;
  let framelessReady = false;
  let framelessAttempts = 0;

  function syncMaximizeButton() {
    const btn = document.getElementById("winMaximize");
    if (!btn || !window.pywebview?.api?.is_maximized) return;
    window.pywebview.api.is_maximized().then((maximized) => {
      windowMaximized = Boolean(maximized);
      btn.classList.toggle("is-maximized", windowMaximized);
    });
  }

  function refreshDesktopSurface() {
    const root = document.documentElement;
    root.style.willChange = "transform";
    requestAnimationFrame(() => {
      root.style.willChange = "";
    });
  }

  function syncWindowChrome() {
    const api = window.pywebview?.api;
    if (!api?.sync_window_chrome) return;
    const theme = document.documentElement.dataset.theme || "dark";
    const bg = theme === "light" ? "#f0ebe3" : "#0a0d12";
    api.sync_window_chrome(bg, theme === "dark");
  }

  function initDesktopSurfaceRefresh() {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        refreshDesktopSurface();
        syncWindowChrome();
      }
    });
    window.addEventListener("focus", () => {
      refreshDesktopSurface();
      syncWindowChrome();
    });
  }

  function bindTitlebarBtn(id, handler) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.setAttribute("tabindex", "-1");
    btn.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      handler();
    });
  }

  function initFramelessWindow() {
    if (framelessReady) return;
    if (!window.pywebview?.api) return;

    framelessReady = true;
    document.body.classList.add("frameless");
    document.documentElement.classList.add("desktop");
    document.activeElement?.blur?.();

    bindTitlebarBtn("winMinimize", () => {
      refreshDesktopSurface();
      syncWindowChrome();
      const api = window.pywebview.api;
      const doMinimize = () => api.minimize_window();
      if (api.prepare_minimize) {
        Promise.resolve(api.prepare_minimize()).finally(doMinimize);
      } else {
        requestAnimationFrame(doMinimize);
      }
    });

    bindTitlebarBtn("winMaximize", () => {
      if (windowMaximized) {
        window.pywebview.api.restore_window();
        windowMaximized = false;
      } else {
        window.pywebview.api.maximize_window();
        windowMaximized = true;
      }
      document.getElementById("winMaximize")?.classList.toggle("is-maximized", windowMaximized);
    });

    bindTitlebarBtn("winClose", () => {
      window.pywebview.api.close_window();
    });

    syncMaximizeButton();
    window.addEventListener("resize", syncMaximizeButton);
    syncWindowChrome();
  }

  function tryInitFrameless() {
    initFramelessWindow();
    if (!framelessReady && framelessAttempts < 50) {
      framelessAttempts += 1;
      setTimeout(tryInitFrameless, 100);
    }
  }

  if (document.documentElement.classList.contains("desktop")) {
    initDesktopSurfaceRefresh();
    window.addEventListener("pywebviewready", initFramelessWindow);
    tryInitFrameless();
  } else {
    document.getElementById("titlebar")?.remove();
  }

  /* ── 视口修复 ── */

  const isDesktopApp = document.documentElement.classList.contains("desktop");

  function fixViewportHeight() {
    if (isDesktopApp) {
      document.documentElement.style.setProperty("--app-height", "100%");
      document.documentElement.style.height = "100%";
      document.body.style.height = "100%";
      document.body.style.width = "100%";
      return;
    }
    const h = window.visualViewport?.height || window.innerHeight;
    document.documentElement.style.setProperty("--app-height", `${Math.round(h)}px`);
  }

  fixViewportHeight();
  if (!isDesktopApp) {
    window.addEventListener("resize", fixViewportHeight);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", fixViewportHeight);
    }
  } else {
    window.addEventListener("resize", () => {
      fixViewportHeight();
      syncWindowChrome?.();
    });
  }

  /* ── 聊天区滚动 ── */

  if (F.chatScroll) {
    F.chatScroll.addEventListener(
      "wheel",
      (event) => {
        const maxScroll = F.chatScroll.scrollHeight - F.chatScroll.clientHeight;
        if (maxScroll <= 0) return;
        F.chatScroll.scrollTop = Math.max(
          0,
          Math.min(maxScroll, F.chatScroll.scrollTop + event.deltaY)
        );
        event.preventDefault();
      },
      { passive: false }
    );
  }
})();
