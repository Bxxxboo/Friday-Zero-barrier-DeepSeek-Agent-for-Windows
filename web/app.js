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
      void F.checkOnboarding?.().catch((err) => console.warn("checkOnboarding", err));
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

  function initFramelessWindow() {
    if (framelessReady) return;
    if (!window.pywebview?.api) return;

    framelessReady = true;
    document.body.classList.add("frameless");
    document.documentElement.classList.add("desktop");

    document.getElementById("winMinimize")?.addEventListener("click", () => {
      window.pywebview.api.minimize_window();
    });

    document.getElementById("winMaximize")?.addEventListener("click", () => {
      if (windowMaximized) {
        window.pywebview.api.restore_window();
        windowMaximized = false;
      } else {
        window.pywebview.api.maximize_window();
        windowMaximized = true;
      }
      document.getElementById("winMaximize")?.classList.toggle("is-maximized", windowMaximized);
    });

    document.getElementById("winClose")?.addEventListener("click", () => {
      window.pywebview.api.close_window();
    });

    syncMaximizeButton();
    window.addEventListener("resize", syncMaximizeButton);
  }

  function tryInitFrameless() {
    initFramelessWindow();
    if (!framelessReady && framelessAttempts < 50) {
      framelessAttempts += 1;
      setTimeout(tryInitFrameless, 100);
    }
  }

  if (document.documentElement.classList.contains("desktop")) {
    window.addEventListener("pywebviewready", initFramelessWindow);
    tryInitFrameless();
  } else {
    document.getElementById("titlebar")?.remove();
  }

  /* ── 视口修复 ── */

  function fixViewportHeight() {
    const h = window.visualViewport?.height || window.innerHeight;
    document.documentElement.style.setProperty("--app-height", `${Math.round(h)}px`);
  }

  fixViewportHeight();
  window.addEventListener("resize", fixViewportHeight);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", fixViewportHeight);
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
