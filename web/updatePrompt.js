/* ================================================================= *
 *  updatePrompt.js — 启动时自动检查更新并弹出更新建议
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) {
    console.error("updatePrompt.js: window.Friday 未初始化");
    return;
  }

  const DISMISS_KEY = "friday_dismissed_update_version";
  const modal = document.getElementById("updatePromptModal");
  const titleEl = document.getElementById("updatePromptTitle");
  const summaryEl = document.getElementById("updatePromptSummary");
  const hintEl = document.getElementById("updatePromptHint");
  const applyBtn = document.getElementById("updatePromptApplyBtn");
  const laterBtn = document.getElementById("updatePromptLaterBtn");
  const downloadLink = document.getElementById("updatePromptDownloadLink");

  let pendingInfo = null;

  function t(key, vars) {
    return F.t?.(key, vars) || key;
  }

  function isVisible() {
    return modal && !modal.classList.contains("hidden");
  }

  function getDismissedVersion() {
    try {
      return localStorage.getItem(DISMISS_KEY) || "";
    } catch {
      return "";
    }
  }

  function setDismissedVersion(version) {
    if (!version) return;
    try {
      localStorage.setItem(DISMISS_KEY, version);
    } catch {
      /* ignore */
    }
  }

  function onboardingVisible() {
    const el = F.onboardingModal || document.getElementById("onboardingModal");
    return el && !el.classList.contains("hidden");
  }

  function showModal(info) {
    if (!modal || !info?.update_available) return;
    pendingInfo = info;
    const latest = info.latest || "";
    const current = info.current || "";
    if (titleEl) {
      titleEl.textContent = t("updates.prompt.title", { latest }) || `发现新版本 v${latest}`;
    }
    if (summaryEl) {
      summaryEl.textContent = t("updates.prompt.summary", { latest, current })
        || `当前版本 v${current}，最新版本 v${latest}。建议尽快更新以获得最新修复与改进。`;
    }
    if (hintEl) {
      const hint = info.can_auto_update
        ? (t("updates.prompt.hintAuto") || "可一键下载安装并自动重启，无需手动解压。")
        : (info.auto_update_hint || t("updates.prompt.hintManual") || "请手动下载安装包后覆盖安装。");
      hintEl.textContent = hint;
    }
    if (applyBtn) {
      const canApply = Boolean(info.can_auto_update && info.download_url);
      applyBtn.classList.toggle("hidden", !canApply);
      applyBtn.disabled = false;
    }
    if (downloadLink) {
      if (info.download_url) {
        downloadLink.href = info.download_url;
        downloadLink.classList.remove("hidden");
      } else {
        downloadLink.classList.add("hidden");
      }
    }
    modal.classList.remove("hidden");
  }

  function hideModal() {
    modal?.classList.add("hidden");
    pendingInfo = null;
  }

  async function checkStartupUpdate() {
    if (onboardingVisible()) return;
    try {
      const res = await F.apiFetchWithTimeout("/api/updates/check", {}, 12000);
      const data = await res.json();
      if (data.last_apply_failed && data.last_apply_hint) {
        window.alert(data.last_apply_hint);
      }
      if (!data.checked || !data.update_available) return;
      if (getDismissedVersion() === data.latest) return;
      showModal(data);
    } catch (err) {
      console.warn("checkStartupUpdate", err);
    }
  }

  laterBtn?.addEventListener("click", () => {
    if (pendingInfo?.latest) setDismissedVersion(pendingInfo.latest);
    hideModal();
  });

  applyBtn?.addEventListener("click", async () => {
    const info = pendingInfo;
    if (!info?.can_auto_update || !info.download_url) return;
    hideModal();
    F.openSettings?.("about");
    await F.startApplyUpdate?.(info, { requireConfirm: false });
  });

  modal?.addEventListener("click", (event) => {
    if (event.target === modal) {
      laterBtn?.click();
    }
  });

  F.checkStartupUpdate = checkStartupUpdate;
  F.isUpdatePromptVisible = isVisible;
})();
