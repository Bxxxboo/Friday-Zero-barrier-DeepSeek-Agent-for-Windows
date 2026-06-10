/* ================================================================= *
 *  weixin.js — 设置 · 微信桥接 一条龙向导
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) return;

  const STEP_ACTIONS = {
    install_openclaw: "install_openclaw",
    install_weixin: "install_weixin",
    install_bridge: "install_bridge",
    configure: "configure",
    login: "login",
    start_gateway: "start_gateway",
    sync_bridge: "sync_bridge",
  };

  const OPENCLAW_INSTALL_URL = "https://docs.openclaw.ai/install";

  function $(id) {
    return document.getElementById(id);
  }

  function statusIcon(status) {
    if (status === "ok") return "✓";
    if (status === "error") return "✗";
    if (status === "warn") return "!";
    return "○";
  }

  function renderSteps(steps) {
    const list = $("weixinSetupSteps");
    if (!list) return;
    list.innerHTML = "";
    (steps || []).forEach((step) => {
      const li = document.createElement("li");
      li.className = `weixin-setup-step weixin-setup-step--${step.status || "pending"}`;
      li.dataset.stepId = step.id;

      const head = document.createElement("div");
      head.className = "weixin-setup-step-head";

      const icon = document.createElement("span");
      icon.className = "weixin-setup-step-icon";
      icon.textContent = statusIcon(step.status);

      const titleWrap = document.createElement("div");
      titleWrap.className = "weixin-setup-step-title-wrap";
      const title = document.createElement("strong");
      title.textContent = step.title;
      const desc = document.createElement("span");
      desc.className = "weixin-setup-step-desc";
      desc.textContent = step.description;
      titleWrap.append(title, desc);

      head.append(icon, titleWrap);

      const msg = document.createElement("p");
      msg.className = "weixin-setup-step-msg";
      msg.textContent = step.message || "";

      li.append(head, msg);

      const action = STEP_ACTIONS[step.action] || step.action;
      if (step.action && step.status !== "ok") {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ghost-btn weixin-setup-step-btn";
        if (step.action === "open_api_settings") {
          btn.textContent = "去设置大模型";
          btn.addEventListener("click", () => F.openSettings?.("llm"));
        } else if (step.action === "open_install_docs") {
          btn.textContent = "查看 OpenClaw 安装说明";
          btn.addEventListener("click", () => {
            window.open(OPENCLAW_INSTALL_URL, "_blank", "noopener");
          });
        } else if (STEP_ACTIONS[step.action]) {
          btn.textContent = actionLabel(step.action);
          btn.addEventListener("click", () => void runSetup(STEP_ACTIONS[step.action], btn));
        }
        li.append(btn);
      }

      list.appendChild(li);
    });
  }

  function actionLabel(action) {
    const map = {
      install_openclaw: "安装 OpenClaw",
      install_weixin: "安装微信通道",
      install_bridge: "安装桥接插件",
      configure: "写入配置",
      login: "扫码登录",
      start_gateway: "启动 Gateway",
      sync_bridge: "连接星期五",
    };
    return map[action] || "执行";
  }

  function updateBanner(data) {
    const badge = $("weixinSetupBadge");
    const text = $("weixinSetupBannerText");
    if (!badge || !text) return;
    if (data.ready) {
      badge.className = "weixin-setup-badge ok";
      badge.textContent = "已就绪";
      text.textContent = "微信桥接已配置完成，可以直接用手机发指令测试。";
      return;
    }
    const pending = (data.steps || []).filter((s) => s.status !== "ok");
    badge.className = "weixin-setup-badge warn";
    badge.textContent = "待完成";
    text.textContent = pending.length
      ? `还有 ${pending.length} 项待处理。点「一键配置」可自动完成安装与桥接（需联网，约 3～5 分钟），并弹出扫码窗口。`
      : "请刷新状态或检查 OpenClaw 是否已安装。";
  }

  function splitResultLines(message) {
    return String(message || "")
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function summarizeSetupMessage(ok, message, data) {
    const lines = splitResultLines(message);
    if (lines.length <= 1) return message || (ok ? "操作完成" : "操作未完成");
    if (data?.ready) return "已全部就绪，可以直接用手机微信发消息测试。";
    const failLine = lines.find((line) => line.startsWith("✗"));
    if (failLine) return failLine.replace(/^✗\s*/, "失败：");
    if (lines.some((line) => /扫码|登录窗口|浏览器/.test(line))) {
      return "扫码窗口已打开。请优先扫描终端里的二维码；若无法扫描，再点「浏览器打开扫码页」。完成后点「刷新状态」。";
    }
    if (ok) return "配置已完成。请查看下方各步骤状态。";
    const last = lines[lines.length - 1] || "";
    return last.replace(/^[✓✗→]\s*/, "");
  }

  function renderResultSummary(el, ok, summary) {
    el.replaceChildren();
    el.className = `settings-result weixin-setup-result weixin-setup-result--summary ${ok ? "ok" : "error"}`;
    const icon = document.createElement("span");
    icon.className = `weixin-result-icon ${ok ? "ok" : "error"}`;
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = ok ? "✓" : "!";
    const text = document.createElement("span");
    text.className = "weixin-result-text";
    text.textContent = summary;
    el.append(icon, text);
  }

  function setResult(ok, message, data) {
    const el = $("weixinSetupResult");
    if (!el) return;
    el.replaceChildren();
    const text = (message || "").trim();

    if (ok === null) {
      el.className = "settings-result weixin-setup-result weixin-setup-result--progress";
      if (!text) return;
      el.textContent = text;
      return;
    }

    if (!text) {
      el.className = "settings-result weixin-setup-result";
      return;
    }

    const lines = splitResultLines(text);
    if (lines.length > 1 && Array.isArray(data?.steps) && data.steps.length > 0) {
      renderResultSummary(el, !!ok, summarizeSetupMessage(!!ok, text, data));
      return;
    }

    if (lines.length === 1) {
      el.className = `settings-result weixin-setup-result ${ok ? "ok" : "error"}`;
      el.textContent = text;
      return;
    }

    el.className = `settings-result weixin-setup-result weixin-setup-result--log ${ok ? "ok" : "error"}`;
    const list = document.createElement("ul");
    list.className = "weixin-setup-log";
    lines.forEach((line) => {
      const item = document.createElement("li");
      let kind = "neutral";
      let label = line;
      if (line.startsWith("✓")) {
        kind = "ok";
        label = line.slice(1).trim();
      } else if (line.startsWith("✗")) {
        kind = "error";
        label = line.slice(1).trim();
      } else if (line.startsWith("→")) {
        kind = "action";
        label = line.slice(1).trim();
      }
      item.className = `weixin-setup-log-item weixin-setup-log-item--${kind}`;
      item.textContent = label;
      list.appendChild(item);
    });
    el.appendChild(list);
  }

  function setProgress(message) {
    const badge = $("weixinSetupBadge");
    const text = $("weixinSetupBannerText");
    if (badge) {
      badge.className = "weixin-setup-badge";
      badge.textContent = "进行中";
    }
    if (text) text.textContent = message || "正在执行…";
    setResult(null, message || "正在执行…");
  }

  function setBusy(busy) {
    ["weixinSetupFullBtn", "weixinSetupRefreshBtn", "weixinSetupLoginBtn", "weixinSetupBrowserBtn"].forEach((id) => {
      const btn = $(id);
      if (btn) btn.disabled = busy;
    });
  }

  let loginUrlPollTimer = null;

  function stopLoginUrlPoll() {
    if (loginUrlPollTimer) {
      clearInterval(loginUrlPollTimer);
      loginUrlPollTimer = null;
    }
  }

  async function pollLoginUrlAndOpen() {
    stopLoginUrlPoll();
    let attempts = 0;
    loginUrlPollTimer = setInterval(async () => {
      attempts += 1;
      if (attempts > 30) {
        stopLoginUrlPoll();
        return;
      }
      try {
        const res = await F.apiFetch("/api/weixin/setup/login-url");
        const data = await res.json();
        const url = String(data?.url || "").trim();
        if (!url) return;
        stopLoginUrlPoll();
        window.open(url, "_blank", "noopener");
      } catch {
        /* ignore transient errors while login starts */
      }
    }, 2000);
  }

  async function openLoginUrlInBrowser() {
    try {
      const res = await F.apiFetch("/api/weixin/setup/open-login-url", { method: "POST" });
      const data = await res.json();
      setResult(!!data.ok, data.message || (data.ok ? "已打开浏览器" : "打开失败"));
    } catch {
      setResult(false, "无法打开扫码页，请先点「打开微信扫码登录」并等待约 30 秒。");
    }
  }

  async function refreshWeixinSetup() {
    setResult(null, "");
    const badge = $("weixinSetupBadge");
    if (badge) {
      badge.className = "weixin-setup-badge";
      badge.textContent = "检测中…";
    }
    try {
      const res = await F.apiFetchWithTimeout("/api/weixin/setup/status", {}, 20000);
      const data = await res.json();
      renderSteps(data.steps);
      updateBanner(data);
      const toggle = $("weixinBridgeEnabled");
      if (toggle) toggle.checked = data.bridge_enabled !== false;
      return data;
    } catch {
      if (badge) {
        badge.className = "weixin-setup-badge error";
        badge.textContent = "失败";
      }
      const text = $("weixinSetupBannerText");
      if (text) {
        text.textContent = "无法连接后端。若正在「初始化 Python 环境」，请等待完成后再点刷新。";
      }
      setResult(false, "无法读取微信配置状态，请确认星期五后端已启动。");
      return null;
    }
  }

  const PROGRESS_HINTS = {
    install_weixin: "正在安装微信通道插件（npm 下载约 1～2 分钟，请稍候）…",
    install_openclaw: "正在安装 OpenClaw（需联网，约 1～3 分钟）…",
    install_bridge: "正在安装星期五桥接插件…",
    full: "正在一键配置（含 OpenClaw/插件，约 3～5 分钟）…",
  };

  async function runSetup(action, triggerBtn) {
    const prevLabel = triggerBtn?.textContent || "";
    setBusy(true);
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.textContent = "执行中…";
    }
    setProgress(PROGRESS_HINTS[action] || "正在执行，请稍候…");
    try {
      const timeoutMs = action === "full" ? 600_000 : 180_000;
      const res = await F.apiFetchWithTimeout(
        "/api/weixin/setup/run",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        },
        timeoutMs,
      );
      let data = {};
      try {
        data = await res.json();
      } catch {
        setResult(false, `服务器返回异常（HTTP ${res.status}）`);
        return;
      }
      if (!res.ok) {
        const detail = data.detail || data.message || `HTTP ${res.status}`;
        setResult(false, typeof detail === "string" ? detail : "安装失败");
        if (Array.isArray(data.steps)) {
          renderSteps(data.steps);
          updateBanner(data);
        }
        return;
      }
      renderSteps(data.steps);
      updateBanner(data);
      setResult(
        data.ok || data.ready,
        (data.message || "").trim() || (data.ok ? "完成" : "未完成"),
        data,
      );
      if (action === "login" || action === "full") {
        pollLoginUrlAndOpen();
      }
      void refreshOpenclawAutostart();
    } catch (err) {
      const aborted = err?.name === "AbortError";
      setResult(
        false,
        aborted
          ? "操作超时，请检查网络后重试，或改用「一键配置」。"
          : "请求失败，请确认星期五后端已启动后重试。",
      );
    } finally {
      setBusy(false);
      if (triggerBtn) {
        triggerBtn.disabled = false;
        if (prevLabel) triggerBtn.textContent = prevLabel;
      }
    }
  }

  async function toggleBridge(enabled) {
    try {
      await F.apiFetch("/api/weixin/setup/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
    } catch {
      setResult(false, "切换桥接开关失败。");
      void refreshWeixinSetup();
    }
  }

  F.refreshWeixinSetup = refreshWeixinSetup;

  let openclawAutostartBusy = false;

  async function refreshOpenclawAutostart() {
    const checkbox = $("openclawGatewayAutostart");
    const hint = $("openclawAutostartResult");
    if (!checkbox) return;
    try {
      const res = await F.apiFetch("/api/weixin/gateway/autostart");
      const data = await res.json();
      checkbox.disabled = data.available === false;
      checkbox.checked = !!data.enabled;
      if (hint) {
        hint.className = "settings-result ok";
        hint.textContent = data.detail || "";
      }
    } catch {
      if (hint) {
        hint.className = "settings-result error";
        hint.textContent = "无法读取 Gateway 自启状态";
      }
    }
  }

  async function setOpenclawAutostart(enabled) {
    if (openclawAutostartBusy) return;
    openclawAutostartBusy = true;
    const hint = $("openclawAutostartResult");
    try {
      const res = await F.apiFetch("/api/weixin/gateway/autostart", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const data = await res.json();
      await refreshOpenclawAutostart();
      if (hint) {
        hint.className = data.ok ? "settings-result ok" : "settings-result error";
        hint.textContent = data.message || data.detail || "";
      }
    } catch {
      if (hint) {
        hint.className = "settings-result error";
        hint.textContent = "设置失败";
      }
    } finally {
      openclawAutostartBusy = false;
    }
  }

  $("weixinSetupFullBtn")?.addEventListener("click", () => void runSetup("full"));
  $("weixinSetupRefreshBtn")?.addEventListener("click", () => void refreshWeixinSetup());
  $("weixinSetupLoginBtn")?.addEventListener("click", () => void runSetup("login"));
  $("weixinSetupBrowserBtn")?.addEventListener("click", () => void openLoginUrlInBrowser());
  $("weixinBridgeEnabled")?.addEventListener("change", (e) => {
    void toggleBridge(!!e.target.checked);
  });
  $("openclawGatewayAutostart")?.addEventListener("change", (e) => {
    void setOpenclawAutostart(!!e.target.checked);
  });
  void refreshOpenclawAutostart();
})();
