/* ================================================================= *
 *  releaseNotes.js — 更新公告弹窗与历史查看
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) {
    console.error("releaseNotes.js: window.Friday 未初始化");
    return;
  }

  const modal = document.getElementById("releaseNotesModal");
  const titleEl = document.getElementById("releaseNotesTitle");
  const bodyEl = document.getElementById("releaseNotesBody");
  const dismissBtn = document.getElementById("releaseNotesDismissBtn");
  const historyLink = document.getElementById("releaseNotesHistoryLink");

  let pendingAckVersion = "";
  let skipAck = false;

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderEntry(entry) {
    const version = escapeHtml(entry.version);
    const date = entry.date ? `<span class="release-notes-date">${escapeHtml(entry.date)}</span>` : "";
    const title = entry.title ? `<p class="release-notes-subtitle">${escapeHtml(entry.title)}</p>` : "";
    const sections = (entry.sections || [])
      .map((sec) => {
        const items = (sec.items || [])
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("");
        if (!items) return "";
        return `<div class="release-notes-section"><h5>${escapeHtml(sec.label || "更新")}</h5><ul>${items}</ul></div>`;
      })
      .join("");
    return `<article class="release-notes-entry"><header class="release-notes-entry-head"><strong>v${version}</strong>${date}</header>${title}${sections}</article>`;
  }

  function renderEntries(entries) {
    if (!bodyEl) return;
    if (!entries?.length) {
      bodyEl.innerHTML = '<p class="release-notes-empty">暂无更新说明。</p>';
      return;
    }
    bodyEl.innerHTML = entries.map(renderEntry).join("");
  }

  function showModal(entries, options = {}) {
    if (!modal) return;
    pendingAckVersion = options.ackVersion || "";
    skipAck = Boolean(options.skipAck);
    if (titleEl) {
      titleEl.textContent = options.title || "更新说明";
    }
    if (historyLink) {
      historyLink.classList.toggle("hidden", !options.showHistoryLink);
    }
    renderEntries(entries);
    modal.classList.remove("hidden");
  }

  function hideModal() {
    modal?.classList.add("hidden");
  }

  async function ackChangelog(version) {
    if (!version) return;
    await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged_changelog_version: version }),
    });
  }

  function onboardingVisible() {
    const el = F.onboardingModal || document.getElementById("onboardingModal");
    return el && !el.classList.contains("hidden");
  }

  async function checkReleaseNotes() {
    if (onboardingVisible()) return;
    try {
      const res = await F.apiFetch("/api/changelog");
      const data = await res.json();
      if (data.has_unseen && data.unseen?.length) {
        showModal(data.unseen, {
          ackVersion: data.current,
          title: `星期五 v${data.current} 更新说明`,
          showHistoryLink: true,
        });
      }
    } catch (err) {
      console.warn("checkReleaseNotes", err);
    }
  }

  async function showChangelogHistory() {
    try {
      const res = await F.apiFetch("/api/changelog");
      const data = await res.json();
      showModal(data.entries || [], {
        skipAck: true,
        title: "更新历史",
        showHistoryLink: false,
      });
    } catch (err) {
      console.warn("showChangelogHistory", err);
    }
  }

  dismissBtn?.addEventListener("click", async () => {
    hideModal();
    if (!skipAck && pendingAckVersion) {
      try {
        await ackChangelog(pendingAckVersion);
      } catch (err) {
        console.warn("ackChangelog", err);
      }
    }
    pendingAckVersion = "";
    skipAck = false;
  });

  historyLink?.addEventListener("click", (event) => {
    event.preventDefault();
    hideModal();
    F.openSettings?.("about");
    void showChangelogHistory();
  });

  modal?.addEventListener("click", (event) => {
    if (event.target === modal) {
      dismissBtn?.click();
    }
  });

  F.checkReleaseNotes = checkReleaseNotes;
  F.showChangelogHistory = showChangelogHistory;
})();
