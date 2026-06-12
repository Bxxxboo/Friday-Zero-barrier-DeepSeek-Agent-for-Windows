/* checkpoint.js — 工作记忆只读面板 */
(function () {
  const F = window.Friday;
  if (!F) return;

  const els = {
    panel: document.getElementById("checkpointPanel"),
    toggle: document.getElementById("checkpointPanelToggle"),
    content: document.getElementById("checkpointPanelContent"),
    meta: document.getElementById("checkpointPanelMeta"),
    empty: document.getElementById("checkpointPanelEmpty"),
    error: document.getElementById("checkpointPanelError"),
    badge: document.getElementById("checkpointPanelBadge"),
    loading: document.querySelector("#checkpointPanelBody .checkpoint-panel-loading"),
  };

  if (!els.panel) return;

  let currentSessionId = "";

  function setExpanded(open) {
    els.panel.classList.toggle("collapsed", !open);
    if (els.toggle) els.toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function showState(which) {
    if (els.loading) els.loading.classList.toggle("hidden", which !== "loading");
    if (els.empty) els.empty.classList.toggle("hidden", which !== "empty");
    if (els.error) els.error.classList.toggle("hidden", which !== "error");
    if (els.content) els.content.classList.toggle("hidden", which !== "content");
    if (els.meta) els.meta.classList.toggle("hidden", which !== "content");
  }

  async function loadCheckpoint(sessionId) {
    currentSessionId = sessionId || "";
    if (!currentSessionId) {
      showState("empty");
      if (els.empty) els.empty.textContent = "选择会话后可查看工作记忆。";
      if (els.badge) els.badge.classList.add("hidden");
      return;
    }
    showState("loading");
    try {
      const res = await F.apiFetch(`/api/sessions/${encodeURIComponent(currentSessionId)}/checkpoint`);
      if (!res.exists) {
        showState("empty");
        if (els.empty) {
          els.empty.textContent = "尚无检查点。长任务在上下文达到 20%/45%/70% 时会自动更新。";
        }
        if (els.badge) els.badge.classList.add("hidden");
        return;
      }
      if (els.content) els.content.textContent = res.markdown || "";
      if (els.meta) {
        const ts = res.updated_at ? new Date(res.updated_at * 1000).toLocaleString() : "—";
        els.meta.textContent = `版本 v${res.version || 0} · 更新于 ${ts}`;
      }
      if (els.badge) {
        els.badge.textContent = `v${res.version || 0}`;
        els.badge.classList.remove("hidden");
      }
      showState("content");
    } catch (err) {
      showState("error");
      if (els.error) els.error.textContent = err?.message || "加载失败";
    }
  }

  els.toggle?.addEventListener("click", () => {
    const open = els.panel.classList.contains("collapsed");
    setExpanded(open);
    if (open && currentSessionId) void loadCheckpoint(currentSessionId);
  });

  F.loadSessionCheckpoint = loadCheckpoint;
})();
