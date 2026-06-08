/* ================================================================= *
 *  utils.js — Friday 共享状态 / DOM 引用 / 工具函数
 *  被 sessions.js / chat.js / settings.js / app.js 依赖，必须最先加载
 * ================================================================= */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ── DOM 引用 ── */
  const chatLog = $("chatLog");
  const chatScroll = $("chatScroll");
  const welcomePanel = $("welcomePanel");
  const chatTitle = $("chatTitle");
  const sessionList = $("sessionList");
  const chatInput = $("chatInput");
  const sendBtn = $("sendBtn");
  const stopBtn = $("stopBtn");
  const runtimeStatus = $("runtimeStatus");
  const apiStatus = $("apiStatus");
  const settingsForm = $("settingsForm");
  const workspaceForm = $("workspaceForm");
  const appearanceForm = $("appearanceForm");
  const securityForm = $("securityForm");
  const settingsResult = $("settingsResult");
  const workspaceResult = $("workspaceResult");
  const appearanceResult = $("appearanceResult");
  const logsResult = $("logsResult");
  const securityResult = $("securityResult");
  const settingsModal = $("settingsModal");
  const onboardingModal = $("onboardingModal");

  /* ── 全局状态 ── */
  let ws = null;
  let busy = false;
  let pendingApprovalId = null;
  let wsConnected = false;
  let wsRetryCount = 0;
  let pendingQueue = [];
  let apiReady = false;
  let thinkingNode = null;
  let sessions = [];
  let activeSessionId = null;
  let streamingNode = null;
  let streamingText = "";
  let composerQuoteText = "";
  let stickToBottom = true;

  const SCROLL_STICK_THRESHOLD = 72;

  const MIGRATION_KEY = "friday_migrated_v1";
  const LEGACY_SESSIONS_KEY = "friday_sessions";
  const LEGACY_ACTIVE_KEY = "friday_active_session";

  function resolveApiToken() {
    // 优先用服务端注入的 token（与校验端一致）；URL 参数仅作兜底
    if (window.__FRIDAY_TOKEN__) return window.__FRIDAY_TOKEN__;
    const params = new URLSearchParams(location.search);
    return params.get("token") || "";
  }

  function apiHeaders(extra = {}) {
    const headers = { ...(extra || {}) };
    const token = resolveApiToken();
    if (token) headers["X-Friday-Token"] = token;
    return headers;
  }

  function apiFetch(url, options = {}) {
    return fetch(url, {
      ...options,
      headers: apiHeaders(options.headers),
    });
  }

  function buildGeneratedImageUrl(path, { preview = true } = {}) {
    const token = resolveApiToken();
    const qs = new URLSearchParams({ path: path || "" });
    if (token) qs.set("token", token);
    if (preview) qs.set("preview", "1");
    return `/api/chat/generated-image?${qs.toString()}`;
  }

  function appendGeneratedImages(node, images) {
    if (!node || !images?.length) return;
    const wrap = document.createElement("div");
    wrap.className = "message-generated-images";
    images.forEach((item) => {
      const path = typeof item === "string" ? item : item?.path;
      if (!path) return;
      const img = document.createElement("img");
      img.className = "message-image";
      img.src = buildGeneratedImageUrl(path);
      img.alt = "生成的图片";
      img.loading = "lazy";
      img.decoding = "async";
      img.title = "点击查看大图";
      img.addEventListener("click", () => {
        const full = buildGeneratedImageUrl(path, { preview: false });
        window.open(full, "_blank", "noopener");
      });
      img.addEventListener("error", () => {
        img.replaceWith(Object.assign(document.createElement("p"), {
          className: "message-image-error",
          textContent: `图片预览加载失败（文件仍在：${path}）`,
        }));
      });
      wrap.appendChild(img);
    });
    if (wrap.childElementCount > 0) node.appendChild(wrap);
  }

  function apiFetchWithTimeout(url, options = {}, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    return apiFetch(url, { ...options, signal: controller.signal }).finally(() => {
      clearTimeout(timer);
    });
  }

  /* ── 工具函数 ── */

  function renderMessageBody(node, kind, text) {
    if (kind === "assistant" && window.marked && window.DOMPurify) {
      const html = marked.parse(text, { breaks: true, gfm: true });
      const safe = DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
      const content = document.createElement("div");
      content.className = "md-content";
      content.innerHTML = safe;
      node.appendChild(content);
      return;
    }
    node.textContent = text;
  }

  function formatQuoteBlock(text) {
    const lines = (text || "").trim().split(/\r?\n/);
    if (!lines.length || !lines[0]) return "";
    return lines.map((line) => `> ${line}`).join("\n");
  }

  function composeMessageWithQuote(userText) {
    const quote = composerQuoteText.trim();
    const body = (userText || "").trim();
    if (!quote) return body;
    const block = formatQuoteBlock(quote);
    if (!body) return block;
    return `${block}\n\n${body}`;
  }

  function hasComposerQuote() {
    return Boolean(composerQuoteText.trim());
  }

  function setComposerQuote(text) {
    composerQuoteText = (text || "").trim();
    const bar = document.getElementById("composerQuote");
    const preview = document.getElementById("composerQuotePreview");
    if (!bar || !preview) return;
    if (!composerQuoteText) {
      bar.classList.add("hidden");
      preview.textContent = "";
      updateInputState();
      return;
    }
    preview.textContent = composerQuoteText.length > 160
      ? `${composerQuoteText.slice(0, 160)}…`
      : composerQuoteText;
    bar.classList.remove("hidden");
    updateInputState();
  }

  function clearComposerQuote() {
    setComposerQuote("");
  }

  async function copyTextToClipboard(text) {
    const value = (text || "").trim();
    if (!value) return false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch {
      /* fallback below */
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }

  function flashActionButton(btn, label) {
    if (!btn) return;
    const original = btn.textContent;
    btn.textContent = label;
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, 1400);
  }

  function attachAssistantMessageActions(node, plainText) {
    if (!node || node.classList.contains("streaming")) return;
    const text = (plainText || "").trim();
    if (!text || node.querySelector(".message-actions")) return;

    node._fridayPlainText = text;

    const actions = document.createElement("div");
    actions.className = "message-actions";

    const t = (key, fallback) => window.FridayI18n?.t?.(key) || fallback;

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "message-action-btn";
    copyBtn.title = t("message.copy", "复制回答");
    copyBtn.textContent = t("message.copy", "复制");
    copyBtn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const ok = await copyTextToClipboard(node._fridayPlainText || text);
      flashActionButton(
        copyBtn,
        ok ? t("message.copied", "已复制") : t("message.copyFailed", "复制失败"),
      );
    });

    const quoteBtn = document.createElement("button");
    quoteBtn.type = "button";
    quoteBtn.className = "message-action-btn";
    quoteBtn.title = t("message.quote", "引用到输入框");
    quoteBtn.textContent = t("message.quote", "引用");
    quoteBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      setComposerQuote(node._fridayPlainText || text);
      chatInput?.focus();
    });

    actions.append(copyBtn, quoteBtn);
    node.appendChild(actions);
  }

  async function migrateLocalStorageSessions() {
    if (localStorage.getItem(MIGRATION_KEY)) return;

    let legacySessions = [];
    try {
      legacySessions = JSON.parse(localStorage.getItem(LEGACY_SESSIONS_KEY) || "[]");
    } catch {
      legacySessions = [];
    }
    const legacyActiveId = localStorage.getItem(LEGACY_ACTIVE_KEY) || "";

    if (!Array.isArray(legacySessions) || legacySessions.length === 0) {
      localStorage.setItem(MIGRATION_KEY, "1");
      localStorage.removeItem(LEGACY_SESSIONS_KEY);
      localStorage.removeItem(LEGACY_ACTIVE_KEY);
      return;
    }

    try {
      const res = await apiFetchWithTimeout(
        "/api/sessions/migrate-local",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessions: legacySessions,
            active_session_id: legacyActiveId,
          }),
        },
        15000
      );
      if (!res.ok) return;
      localStorage.setItem(MIGRATION_KEY, "1");
      localStorage.removeItem(LEGACY_SESSIONS_KEY);
      localStorage.removeItem(LEGACY_ACTIVE_KEY);
    } catch {
      // 下次启动重试
    }
  }

  function setConnectionStatus(text, ok = false) {
    if (!runtimeStatus) return;
    const hideWhenReady = ok && text === "就绪";
    runtimeStatus.textContent = hideWhenReady ? "" : text;
    runtimeStatus.classList.toggle("ready", ok);
    runtimeStatus.classList.toggle("visible", !hideWhenReady && Boolean(text));
    updateInputState();
  }

  function updateApiStatus(ready) {
    apiReady = ready;
    if (apiStatus) {
      apiStatus.textContent = ready ? "API 已就绪" : "API 未配置";
      apiStatus.classList.toggle("ready", ready);
    }
    window.Friday?.refreshStatusBar?.();
  }

  function updateQueueIndicator(count = pendingQueue.length) {
    const bar = document.getElementById("composerQueue");
    const text = document.getElementById("composerQueueText");
    if (!bar || !text) return;
    const n = Math.max(0, Number(count) || 0);
    if (n > 0) {
      bar.classList.remove("hidden");
      const t = window.Friday?.t;
      text.textContent =
        n === 1
          ? t?.("composer.queue.one") || "1 条指令待执行"
          : (t?.("composer.queue.many") || "{n} 条指令待执行").replace("{n}", String(n));
    } else {
      bar.classList.add("hidden");
      text.textContent = "";
    }
  }

  function updateInputState() {
    const friday = window.Friday;
    const hasAttachment = Boolean(friday?.hasComposerAttachment?.());
    const hasQuote = hasComposerQuote();
    const hasText = Boolean(chatInput?.value.trim());
    const canSend = apiReady && activeSessionId && (hasText || hasAttachment || hasQuote);
    const canInteract = apiReady && activeSessionId;

    if (stopBtn) {
      stopBtn.classList.toggle("hidden", !busy);
      stopBtn.disabled = !busy;
    }
    if (sendBtn) {
      sendBtn.disabled = !canSend;
    }
    if (chatInput) {
      chatInput.disabled = !canInteract;
      chatInput.classList.toggle("composer-idle", !canSend);
      chatInput.classList.toggle("composer-busy", busy);
    }
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.classList.toggle("chip-muted", !canInteract);
    });
    updateQueueIndicator();
  }

  function isNearBottom(el = chatScroll) {
    if (!el) return true;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    return distance <= SCROLL_STICK_THRESHOLD;
  }

  function updateScrollStick() {
    if (!chatScroll || chatScroll.classList.contains("hidden")) return;
    stickToBottom = isNearBottom(chatScroll);
  }

  function resetScrollStick(stick = true) {
    stickToBottom = stick;
  }

  /** 滚到底部。force=true 时无视用户上滑；流式输出默认仅在贴底时跟随。 */
  function scrollToBottom(force = false) {
    if (!chatScroll || chatScroll.classList.contains("hidden")) return;
    if (!force && !stickToBottom) return;
    chatScroll.scrollTop = chatScroll.scrollHeight;
    if (force) stickToBottom = true;
  }

  if (chatScroll) {
    chatScroll.addEventListener("scroll", updateScrollStick, { passive: true });
  }

  function showThinking() {
    removeThinking();
    thinkingNode = document.createElement("div");
    thinkingNode.className = "message thinking";
    thinkingNode.innerHTML =
      '<span class="dot"></span><span class="dot"></span><span class="dot"></span> 正在思考...';
    chatLog.appendChild(thinkingNode);
    scrollToBottom();
  }

  function removeThinking() {
    if (thinkingNode) {
      thinkingNode.remove();
      thinkingNode = null;
    }
  }

  function getActiveSession() {
    return sessions.find((s) => s.id === activeSessionId) || null;
  }

  function toUiMessages(apiMessages) {
    return apiMessages.map((msg) => {
      const item = {
        kind: msg.role === "user" ? "user" : msg.role === "error" ? "error" : "assistant",
        text: msg.content,
      };
      const images = msg.generated_images || msg.generatedImages;
      if (images?.length) {
        item.generatedImages = images
          .map((img) => ({ path: typeof img === "string" ? img : img?.path }))
          .filter((img) => img.path);
      }
      return item;
    });
  }

  function setBusy(value) {
    busy = value;
    updateInputState();
  }

  function nameToLabel(name) {
    const labels = {
      list_directory: "扫描目录",
      search_files: "搜索文件",
      read_text_file: "读取文件",
      read_pdf: "读取 PDF",
      read_excel: "读取 Excel",
      write_text_file: "写入文件",
      move_file: "移动文件",
      organize_directory: "整理目录",
      batch_rename: "批量重命名",
      find_duplicates: "查找重复",
      zip_files: "压缩文件",
      unzip_file: "解压文件",
      create_docx: "生成 Word",
      create_pptx: "生成 PPT",
      get_system_status: "查看系统",
      get_disk_usage: "查看磁盘",
      get_top_processes: "查看进程",
      run_powershell: "整理信息",
      run_python: "分析数据",
      run_python_script: "运行任务",
      python_env_info: "Python 环境",
      delete_file: "删除文件",
      delete_directory: "删除目录",
      copy_file: "复制",
      get_file_info: "查看详情",
      open_url: "打开网页",
      open_app: "启动应用",
      screenshot: "截屏",
      clipboard_read: "读剪贴板",
      clipboard_write: "写剪贴板",
      get_network_info: "网络信息",
      browse_webpage: "浏览网页",
      verify_download_source: "验证下载源",
      download_file: "下载文件",
      download_software: "下载软件",
      describe_image: "识别截图",
      vision_status: "检查视觉",
      generate_image: "生成图片",
      image_gen_status: "检查生图",
    };
    return labels[name] || name;
  }

  /* ── 挂载到全局命名空间 ── */
  window.Friday = {
    // DOM
    chatLog,
    chatScroll,
    welcomePanel,
    chatTitle,
    sessionList,
    chatInput,
    sendBtn,
    stopBtn,
    runtimeStatus,
    apiStatus,
    settingsForm,
    workspaceForm,
    appearanceForm,
    securityForm,
    settingsResult,
    workspaceResult,
    appearanceResult,
    logsResult,
    securityResult,
    settingsModal,
    onboardingModal,

    // 状态读写
    get ws() { return ws; },
    set ws(v) { ws = v; },
    get busy() { return busy; },
    set busy(v) { busy = v; },
    get pendingApprovalId() { return pendingApprovalId; },
    set pendingApprovalId(v) { pendingApprovalId = v; },
    get wsConnected() { return wsConnected; },
    set wsConnected(v) { wsConnected = v; },
    get wsRetryCount() { return wsRetryCount; },
    set wsRetryCount(v) { wsRetryCount = v; },
    get pendingQueue() { return pendingQueue; },
    set pendingQueue(v) { pendingQueue = v; },
    get apiReady() { return apiReady; },
    set apiReady(v) { apiReady = v; },
    get thinkingNode() { return thinkingNode; },
    set thinkingNode(v) { thinkingNode = v; },
    get sessions() { return sessions; },
    set sessions(v) { sessions = v; },
    get activeSessionId() { return activeSessionId; },
    set activeSessionId(v) { activeSessionId = v; },
    get streamingNode() { return streamingNode; },
    set streamingNode(v) { streamingNode = v; },
    get streamingText() { return streamingText; },
    set streamingText(v) { streamingText = v; },

    // 工具函数
    resolveApiToken,
    apiFetch,
    apiFetchWithTimeout,
    apiHeaders,
    buildGeneratedImageUrl,
    appendGeneratedImages,
    renderMessageBody,
    attachAssistantMessageActions,
    composeMessageWithQuote,
    setComposerQuote,
    clearComposerQuote,
    hasComposerQuote,
    copyTextToClipboard,
    migrateLocalStorageSessions,
    setConnectionStatus,
    updateApiStatus,
    updateInputState,
    updateQueueIndicator,
    scrollToBottom,
    resetScrollStick,
    isNearBottom,
    showThinking,
    removeThinking,
    getActiveSession,
    toUiMessages,
    setBusy,
    nameToLabel,
  };
})();
