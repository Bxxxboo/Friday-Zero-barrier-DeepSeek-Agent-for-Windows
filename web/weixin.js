/* ================================================================= *
 *  weixin.js — 设置 · 微信端 AI 一条龙向导
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
          btn.textContent = "去配置 API";
          btn.addEventListener("click", () => F.openSettings?.("api"));
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
      text.textContent = "微信端 AI 已配置完成，可以直接用手机发指令测试。";
      return;
    }
    const pending = (data.steps || []).filter((s) => s.status !== "ok");
    badge.className = "weixin-setup-badge warn";
    badge.textContent = "待完成";
    text.textContent = pending.length
      ? `还有 ${pending.length} 项待处理。点「一键配置」可自动安装 Node.js、OpenClaw 与插件（需联网，约 3～5 分钟）；完成后会弹出扫码窗口。`
      : "请刷新状态或检查 OpenClaw 是否已安装。";
  }

  function setResult(ok, message) {
    const el = $("weixinSetupResult");
    if (!el) return;
    el.className = ok ? "settings-result ok" : "settings-result error";
    el.textContent = message || "";
  }

  function setBusy(busy) {
    ["weixinSetupFullBtn", "weixinSetupRefreshBtn", "weixinSetupLoginBtn"].forEach((id) => {
      const btn = $(id);
      if (btn) btn.disabled = busy;
    });
  }

  async function refreshWeixinSetup() {
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
      setResult(false, "无法读取微信配置状态，请确认星期五后端已启动。");
      return null;
    }
  }

  async function runSetup(action, triggerBtn) {
    setBusy(true);
    if (triggerBtn) triggerBtn.disabled = true;
    const resultEl = $("weixinSetupResult");
    if (resultEl) {
      resultEl.className = "settings-result";
      resultEl.textContent = action === "full" ? "正在一键配置（含 OpenClaw/插件，可能需要 3～5 分钟）…" : "执行中…";
    }
    try {
      const timeoutMs = action === "full" ? 600_000 : 120_000;
      const res = await F.apiFetchWithTimeout(
        "/api/weixin/setup/run",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        },
        timeoutMs,
      );
      const data = await res.json();
      renderSteps(data.steps);
      updateBanner(data);
      setResult(data.ok || data.ready, (data.message || "").replace(/\n/g, " · ") || (data.ok ? "完成" : "未完成"));
      void refreshOpenclawAutostart();
    } catch {
      setResult(false, "请求失败，请稍后重试。");
    } finally {
      setBusy(false);
      if (triggerBtn) triggerBtn.disabled = false;
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
  $("weixinBridgeEnabled")?.addEventListener("change", (e) => {
    void toggleBridge(!!e.target.checked);
  });
  $("openclawGatewayAutostart")?.addEventListener("change", (e) => {
    void setOpenclawAutostart(!!e.target.checked);
  });
  void refreshOpenclawAutostart();
})();
