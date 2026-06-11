(function () {
  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setHref(id, href) {
    const el = document.getElementById(id);
    if (el) el.href = href;
  }

  function setDownloadLinks(href) {
    document.querySelectorAll(".js-download-btn").forEach((el) => {
      el.href = href || "#";
    });
  }

  function renderChangelog(entry) {
    const root = document.getElementById("changelogRoot");
    if (!root || !entry) {
      if (root) root.innerHTML = '<p class="muted">暂无更新说明。</p>';
      return;
    }

    const sections = (entry.sections || [])
      .map((sec) => {
        const items = (sec.items || [])
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("");
        return `
          <div class="changelog-section">
            <h4>${escapeHtml(sec.label || "")}</h4>
            <ul>${items}</ul>
          </div>`;
      })
      .join("");

    const title = entry.title ? `：${escapeHtml(entry.title)}` : "";
    root.innerHTML = `
      <h3>v${escapeHtml(entry.version || "")}${title}</h3>
      <p class="changelog-meta">${escapeHtml(entry.date || "")}</p>
      ${sections}`;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadDownloadInfo() {
    const res = await fetch("download.json", { cache: "no-cache" });
    if (!res.ok) throw new Error("download.json");
    return res.json();
  }

  async function loadChangelog() {
    try {
      const res = await fetch("changelog.json", { cache: "no-cache" });
      if (!res.ok) return null;
      const data = await res.json();
      return data.entries && data.entries[0] ? data.entries[0] : null;
    } catch {
      return null;
    }
  }

  function applyDownloadInfo(info) {
    const version = info.version || "…";
    const date = info.date || "";
    const versionLabel = date ? `v${version}（${date}）` : `v${version}`;
    setText("footerVersion", versionLabel);
    setText("downloadVersion", versionLabel);
    setText("year", String(new Date().getFullYear()));

    setDownloadLinks(info.download_url || info.zip_url || info.setup_url || "#");
    setHref("allReleasesLink", info.releases_page || info.gitee_home || "#");
  }

  async function init() {
    try {
      const [info, changelog] = await Promise.all([loadDownloadInfo(), loadChangelog()]);
      applyDownloadInfo(info);
      renderChangelog(changelog);
    } catch {
      setText("footerVersion", "加载失败");
      setText("downloadVersion", "加载失败");
      const root = document.getElementById("changelogRoot");
      if (root) root.innerHTML = '<p class="muted">无法加载下载信息，请稍后再试。</p>';
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
