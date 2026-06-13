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

  const BOOT_MIN_MS = 1600;
  const bootStarted = performance.now();
  const bootSeamless = document.documentElement.classList.contains("boot-seamless");
  if (!document.documentElement.classList.contains("boot-active")) {
    document.documentElement.classList.add("boot-active");
  }

  async function bootstrap() {
    window.__FRIDAY_MARK_BOOT__?.();
    const overlay = document.getElementById("appBootOverlay");
    const setBootText = (text) => {
      const hint = overlay?.querySelector(".app-boot-status") || overlay?.querySelector("p");
      if (!hint || hint.textContent === text) return;
      if (bootSeamless) {
        hint.textContent = text;
        return;
      }
      hint.classList.add("is-swapping");
      setTimeout(() => {
        hint.textContent = text;
        hint.classList.remove("is-swapping");
      }, 180);
    };
    const hideOverlay = () => {
      if (!overlay || overlay.classList.contains("hidden")) return;
      const finish = () => {
        overlay.classList.add("hidden");
        overlay.classList.remove("is-leaving");
        document.documentElement.classList.remove("boot-active");
        document.documentElement.classList.add("app-ready");
      };
      if (window.FridayMotion?.ready) {
        window.FridayMotion.animateBootExit(overlay, finish);
        return;
      }
      overlay.classList.add("is-leaving");
      overlay.addEventListener("transitionend", finish, { once: true });
      setTimeout(finish, 560);
    };

    const bootWork = async () => {
      setBootText("正在同步数据…");
      await F.ensureApiToken?.();
      await F.migrateLocalStorageSessions();
      setBootText("正在加载对话…");
      await F.fetchSessions();
      setBootText("正在连接服务…");
      try {
        await F.loadSettings?.({ skipStartupTests: true });
      } catch (err) {
        console.warn("loadSettings", err);
      }
      const health = await F.apiFetchWithTimeout("/api/health", {}, 8000);
      if (!health.ok) throw new Error(`服务未就绪 (${health.status})`);
      let healthBody = null;
      try {
        healthBody = await health.json();
      } catch {
        throw new Error("服务未就绪 (invalid health response)");
      }
      const healthDeadline = Date.now() + 8000;
      while (healthBody?.status !== "ok" && Date.now() < healthDeadline) {
        await new Promise((resolve) => setTimeout(resolve, 200));
        const retry = await F.apiFetchWithTimeout("/api/health", {}, 3000);
        if (!retry.ok) continue;
        try {
          healthBody = await retry.json();
        } catch {
          /* keep polling */
        }
      }
      if (healthBody?.status !== "ok") {
        throw new Error("服务未就绪 (starting)");
      }
    };

    const waitBootMinimum = async () => {
      if (bootSeamless) return;
      const remain = BOOT_MIN_MS - (performance.now() - bootStarted);
      if (remain > 0) {
        await new Promise((resolve) => setTimeout(resolve, remain));
      }
    };

    try {
      F.setConnectionStatus("正在加载...", false);
      await Promise.race([
        bootWork(),
        new Promise((_, reject) => {
          setTimeout(() => reject(new Error("加载超时，请关闭后重新打开")), 30000);
        }),
      ]);
      await waitBootMinimum();
      setBootText("即将进入…");
      await new Promise((resolve) => setTimeout(resolve, 340));
      hideOverlay();
      F.connectWs();
      F.updateInputState();
      void F.runStartupApiTests?.();
      void F.checkOnboarding?.().catch((err) => console.warn("checkOnboarding", err)).finally(() => {
        void F.checkStartupUpdate?.().catch((err) => console.warn("checkStartupUpdate", err)).finally(() => {
          setTimeout(() => void F.checkReleaseNotes?.(), 400);
        });
      });
    } catch (err) {
      console.error(err);
      const detail = err?.message || String(err);
      F.setConnectionStatus("加载失败，请重启应用", false);
      const hint = overlay?.querySelector(".app-boot-status") || overlay?.querySelector("p");
      if (hint) {
        const isAuth = detail.includes("401") || detail.includes("Unauthorized");
        const isTimeout =
          detail.includes("超时")
          || detail.includes("timeout")
          || err?.name === "AbortError"
          || detail.includes("aborted");
        hint.textContent = isAuth
          ? "加载失败：认证未通过，请完全关闭后重新打开"
          : isTimeout
            ? "加载超时，请完全关闭后重新打开"
            : detail.slice(0, 100);
      }
    }
  }

  bootstrap();

  F.bindModeSwitch?.();

  /* ── 事件绑定 ── */

  F.sendBtn?.addEventListener("click", () => {
    void F.sendChat(F.chatInput?.value || "");
    if (F.chatInput) {
      F.chatInput.value = "";
      F.updateInputState();
    }
  });

  F.chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void F.sendChat(F.chatInput.value);
      F.chatInput.value = "";
      F.updateInputState();
    }
  });

  F.chatInput?.addEventListener("input", () => {
    F.syncComposerInputHeight?.();
    F.updateInputState();
  });
  F.chatInput?.addEventListener("paste", () => {
    requestAnimationFrame(() => F.syncComposerInputHeight?.());
  });

  document.getElementById("clearQuoteBtn")?.addEventListener("click", () => {
    F.clearComposerQuote?.();
    F.chatInput?.focus();
  });

  document.getElementById("newChatBtn")?.addEventListener("click", () => F.createSession(true));
  document.getElementById("openSettingsBtn")?.addEventListener("click", () => F.openSettings("llm"));
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
  document.getElementById("diagnoseBtn")?.addEventListener("click", F.diagnoseNetworkSettings);
  document.getElementById("testVisionBtn")?.addEventListener("click", F.testVisionSettings);

  F.settingsForm?.addEventListener("submit", F.saveSettings);
  document.getElementById("visionForm")?.addEventListener("submit", F.saveVisionSettings);
  document.getElementById("testImageGenBtn")?.addEventListener("click", F.testImageGenSettings);
  document.getElementById("imageGenForm")?.addEventListener("submit", F.saveImageGenSettings);
  document.getElementById("imageGenBaseUrl")?.addEventListener("input", (e) => {
    e.target.dataset.userEdited = e.target.value.trim() ? "1" : "";
  });
  document.getElementById("llmProvider")?.addEventListener("change", () => F.onLlmProviderChange?.());
  document.getElementById("visionProvider")?.addEventListener("change", () => F.onVisionProviderChange?.());
  document.getElementById("imageGenProvider")?.addEventListener("change", () => F.onImageGenProviderChange?.());
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
      document.documentElement.classList.toggle("window-maximized", windowMaximized);
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
    const theme = document.documentElement.dataset.theme || "light";
    const bg = theme === "light" ? "#f0ebe3" : "#0a0d12";
    api.sync_window_chrome(bg, theme === "dark");
  }

  function isFridayInternalUrl(href) {
    try {
      const url = new URL(href, window.location.origin);
      if (url.protocol !== "http:" && url.protocol !== "https:") return true;
      return url.hostname === "localhost" || url.hostname === "127.0.0.1";
    } catch {
      return true;
    }
  }

  function isExternalHttpUrl(href) {
    try {
      const url = new URL(href, window.location.origin);
      return (url.protocol === "http:" || url.protocol === "https:") && !isFridayInternalUrl(href);
    } catch {
      return false;
    }
  }

  function openExternalLink(href) {
    const api = window.pywebview?.api;
    if (api?.open_external_url) {
      return Promise.resolve(api.open_external_url(href)).catch(() => {
        window.open(href, "_blank", "noopener,noreferrer");
      });
    }
    window.open(href, "_blank", "noopener,noreferrer");
    return Promise.resolve();
  }

  function initExternalLinkGuard() {
    if (document.documentElement.dataset.externalLinkGuard === "1") return;
    document.documentElement.dataset.externalLinkGuard = "1";
    document.addEventListener("click", (event) => {
      const anchor = event.target.closest?.("a[href]");
      if (!anchor) return;
      const href = anchor.getAttribute("href")?.trim();
      if (!href || href.startsWith("#") || /^javascript:/i.test(href)) return;
      if (!isExternalHttpUrl(href)) return;
      event.preventDefault();
      event.stopPropagation();
      void openExternalLink(href);
    }, true);
  }

  initExternalLinkGuard();

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

  function initWindowActivation() {
    if (!document.documentElement.classList.contains("desktop")) return;
    let activating = false;
    const requestActivate = () => {
      const api = window.pywebview?.api;
      if (!api?.activate_window || activating) return;
      const runActivate = () => {
        activating = true;
        Promise.resolve(api.activate_window()).finally(() => {
          activating = false;
        });
      };
      if (api.is_window_foreground) {
        Promise.resolve(api.is_window_foreground())
          .then((foreground) => {
            if (!foreground) runActivate();
          })
          .catch(runActivate);
        return;
      }
      runActivate();
    };
    document.addEventListener("pointerdown", requestActivate, true);
    document.addEventListener("mousedown", requestActivate, true);
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
      document.documentElement.classList.toggle("window-maximized", windowMaximized);
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
    initWindowActivation();
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
