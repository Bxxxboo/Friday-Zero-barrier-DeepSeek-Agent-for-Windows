/* ================================================================= *
 *  chat.js — Friday 通信层：WebSocket / 流式渲染 / 审批 / 取消
 *  依赖 utils.js + sessions.js
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) { console.error("chat.js: window.Friday 未初始化"); return; }

  /* ── WebSocket ── */

  function connectWs() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    F.wsConnected = false;
    F.setConnectionStatus("正在连接...");

    if (F.ws) {
      try {
        F.ws.close();
      } catch {
        /* ignore */
      }
    }

    const wsUrl = `${protocol}://${location.host}/ws/chat`;
    F.ws = new WebSocket(wsUrl);

    let connectTimer = null;
    const clearConnectTimer = () => {
      if (connectTimer) {
        clearTimeout(connectTimer);
        connectTimer = null;
      }
    };

    connectTimer = setTimeout(() => {
      if (F.wsConnected) return;
      if (F.ws?.readyState === WebSocket.CONNECTING) {
        try {
          F.ws.close();
        } catch {
          /* ignore */
        }
        F.setConnectionStatus(
          "连接超时：请关闭杀毒/VPN 后重开，或查看 %APPDATA%\\Friday\\friday.log",
          false
        );
      }
    }, 15000);

    F.ws.onopen = () => {
      clearConnectTimer();
      const token = F.resolveApiToken();
      try {
        F.ws.send(JSON.stringify({ type: "auth", token: token || "" }));
      } catch {
        /* ignore */
      }
    };

    F.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "connected") {
        F.wsRetryCount = 0;
        F.wsConnected = true;
        F.setConnectionStatus("就绪", true);
        if (!F.isStatusBarBooting?.()) {
          F.refreshStatusBar?.();
        }
        flushQueue();
        return;
      }
      handleEvent(data);
    };

    F.ws.onerror = () => {
      F.wsConnected = false;
      F.setBusy(false);
      F.removeThinking();
      removeProgress();
    };

    F.ws.onclose = (event) => {
      clearConnectTimer();
      F.wsConnected = false;
      F.setBusy(false);
      F.removeThinking();
      removeProgress();
      if (event.code === 4401) {
        void F.refreshApiToken?.().then((ok) => {
          if (ok) {
            F.wsRetryCount = 0;
            F.setConnectionStatus("认证已恢复，正在重连...", false);
            setTimeout(connectWs, 300);
          } else {
            F.setConnectionStatus("认证失败，请完全退出后重新打开", false);
          }
        });
        return;
      }
      F.setConnectionStatus("连接断开，重连中...");
      const delay = Math.min(1500 * (1 + (F.wsRetryCount || 0)), 8000);
      F.wsRetryCount = (F.wsRetryCount || 0) + 1;
      setTimeout(connectWs, delay);
    };
  }

  /* ── 进度指示器 ── */

  let progressNode = null;
  let pendingGeneratedImages = [];
  let progressTimer = null;
  let progressStartedAt = null;

  function isLongRunningVisualProgress(data) {
    const tools = data.tools || [];
    return tools.includes("generate_image") || tools.includes("describe_image");
  }

  function resetPendingGeneratedImages() {
    pendingGeneratedImages = [];
  }

  function collectPendingGeneratedImages() {
    const copy = pendingGeneratedImages.slice();
    resetPendingGeneratedImages();
    return copy;
  }

  function stopProgressTimer() {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  function startProgressTimer(baseText, startedAt) {
    stopProgressTimer();
    const started = startedAt || progressStartedAt || Date.now();
    progressStartedAt = started;
    progressTimer = setInterval(() => {
      if (!progressNode) return;
      const elapsed = Math.floor((Date.now() - started) / 1000);
      const textEl = progressNode.querySelector(".progress-text");
      if (textEl) textEl.textContent = `${baseText}（已 ${elapsed}s）`;
    }, 1000);
  }

  function formatProgressMessage(data) {
    const tools = data.tools || [];
    const toolLabels = tools.map((t) => F.nameToLabel(t));
    const label = toolLabels.join("、");

    if (tools.length === 1) {
      const stepHint =
        data.step && data.tool_count && data.tool_count > 1
          ? `（${data.step}/${data.tool_count}）`
          : "";
      const label = toolLabels[0];
      if (tools[0] === "describe_image") {
        return `正在识别截图${stepHint}…`;
      }
      if (tools[0] === "generate_image") {
        return `正在生成图片${stepHint}…`;
      }
      return `正在${label}${stepHint}…`;
    }

    if (label && data.round) {
      return `正在${label}（第 ${data.round} 轮）`;
    }
    if (label) {
      return `正在${label}…`;
    }
    if (data.round) {
      return `正在处理（第 ${data.round} 轮）`;
    }
    return "正在处理…";
  }

  function showProgress(data) {
    const isLongRun = isLongRunningVisualProgress(data);
    // 生图/识图由前端 1s 计时器更新；重复 progress 或 tool_start 不重建 DOM，避免计时归零
    if (progressNode && progressStartedAt != null && (isLongRun || data.heartbeat)) return;

    removeProgress();
    const msg = formatProgressMessage(data);
    progressNode = document.createElement("div");
    progressNode.className = "message progress";
    progressNode.innerHTML = `<div class="progress-bar"><div class="progress-fill"></div></div><span class="progress-text">${msg}</span>`;
    F.chatLog.appendChild(progressNode);
    F.appendActivityStep?.(msg.replace(/…$/, ""));
    F.scrollToBottom();
    if (isLongRun) {
      progressStartedAt = Date.now();
      startProgressTimer(msg.replace(/…$/, ""), progressStartedAt);
    }
  }

  function removeProgress() {
    stopProgressTimer();
    progressStartedAt = null;
    if (progressNode) {
      progressNode.remove();
      progressNode = null;
    }
  }

  /* ── 流式消息 ── */

  function startStreamingMessage() {
    F.completeActivitySteps?.();
    F.removeThinking();
    F.welcomePanel.classList.add("hidden");
    F.chatScroll.classList.remove("hidden");
    F.streamingNode = document.createElement("div");
    F.streamingNode.className = "message assistant streaming";
    F.streamingText = "";
    F.streamingNode.textContent = "";
    F.chatLog.appendChild(F.streamingNode);
    F.scrollToBottom(true);
  }

  function appendStreamingDelta(delta) {
    if (!delta) return;
    if (!F.streamingNode) startStreamingMessage();
    F.streamingText += delta;
    F.streamingNode.textContent = F.streamingText;
    F.scrollToBottom();
  }

  function clearStreamingMessage(showThinkingAgain = true) {
    if (F.streamingNode) {
      F.streamingNode.remove();
      F.streamingNode = null;
      F.streamingText = "";
    }
    if (showThinkingAgain) F.showThinking();
  }

  function finalizeStreamingMessage(text) {
    const generatedImages = collectPendingGeneratedImages();
    if (F.streamingNode) {
      F.streamingNode.classList.remove("streaming");
      F.streamingNode.replaceChildren();
      F.renderMessageBody(F.streamingNode, "assistant", text);
      F.appendGeneratedImages(F.streamingNode, generatedImages);
      F.attachAssistantMessageActions(F.streamingNode, text);
      const session = F.getActiveSession();
      if (session) {
        const entry = { kind: "assistant", text };
        if (generatedImages.length) entry.generatedImages = generatedImages;
        session.messages.push(entry);
        F.updateEmptyState(session.messages);
      }
      F.streamingNode = null;
      F.streamingText = "";
      F.scrollToBottom();
      return;
    }
    appendMessage("assistant", text, false, { generatedImages });
  }

  /* ── 事件分发 ── */

  const runningChatSessions = new Set();
  const runningUserTextBySession = new Map();

  let stopConfirmResolver = null;

  function resolveStopConfirm(choice) {
    const modal = document.getElementById("stopConfirmModal");
    modal?.classList.add("hidden");
    const resolve = stopConfirmResolver;
    stopConfirmResolver = null;
    resolve?.(choice);
  }

  function showStopConfirmModal() {
    const modal = document.getElementById("stopConfirmModal");
    if (!modal) return Promise.resolve("continue");
    return new Promise((resolve) => {
      stopConfirmResolver = resolve;
      modal.classList.remove("hidden");
      document.getElementById("stopConfirmContinue")?.focus();
    });
  }

  function activeRunningSessionId() {
    return [...runningChatSessions][runningChatSessions.size - 1] || F.activeSessionId || "";
  }

  function restoreRunningMessageToComposer(sessionId, textOverride = "") {
    const savedText = String(textOverride || runningUserTextBySession.get(sessionId) || "").trim();
    if (!savedText) return;
    if (F.chatInput) {
      F.chatInput.value = savedText;
      F.syncComposerInputHeight?.();
      F.updateInputState();
      F.chatInput.focus();
    }
    const session = F.getActiveSession?.();
    if (session?.messages?.length && sessionId === F.activeSessionId) {
      const last = session.messages[session.messages.length - 1];
      if (last?.kind === "user" && String(last.text || "").trim() === savedText.trim()) {
        session.messages.pop();
        const nodes = F.chatLog?.querySelectorAll(".message.user");
        const lastNode = nodes?.[nodes.length - 1];
        lastNode?.remove();
      }
    }
  }

  function clearRunningUserText(sessionId) {
    if (sessionId) runningUserTextBySession.delete(sessionId);
  }

  const BACKGROUND_CHAT_EVENTS = new Set([
    "assistant_start",
    "assistant_delta",
    "assistant_clear",
    "agent_step",
    "reasoning_delta",
    "progress",
    "tool_start",
    "image_generated",
    "approval_request",
    "approval_summary_update",
    "approval_wait",
    "approval_auto",
    "status",
  ]);

  function hasBackgroundChatTurn() {
    return [...runningChatSessions].some((id) => id !== F.activeSessionId);
  }

  function isBackgroundChatEvent() {
    return hasBackgroundChatTurn();
  }

  function detachChatUiForSessionSwitch() {
    removeProgress();
    F.removeThinking();
    clearStreamingMessage(false);
    if (pendingApprovalNode) {
      pendingApprovalNode.remove();
      pendingApprovalNode = null;
    }
  }

  async function syncBackgroundSessionMessages(sessionId) {
    if (!sessionId) return;
    try {
      const res = await F.apiFetch(`/api/sessions/${sessionId}`);
      if (!res.ok) return;
      const detail = await res.json();
      const session = F.sessions.find((s) => s.id === sessionId);
      if (session) {
        session.title = detail.title;
        session.updatedAt = detail.updated_at;
        session.messages = F.toUiMessages(detail.messages);
      }
      F.renderSessionList?.();
    } catch {
      /* 后台完成时拉取失败可忽略 */
    }
  }

  function handleEvent(data) {
    const background = isBackgroundChatEvent();
    if (background && BACKGROUND_CHAT_EVENTS.has(data.type)) {
      return;
    }

    switch (data.type) {
      case "assistant_start":
        startStreamingMessage();
        break;
      case "assistant_delta":
        appendStreamingDelta(data.delta || "");
        break;
      case "assistant_clear":
        clearStreamingMessage();
        break;
      case "assistant": {
        const doneSessionId = data.session?.id;
        if (doneSessionId) {
          runningChatSessions.delete(doneSessionId);
          clearRunningUserText(doneSessionId);
        }
        if (background) {
          void syncBackgroundSessionMessages(doneSessionId);
          if (data.usage) F.applyStatusUsage?.(data.usage);
          F.refreshStatusBar?.();
          return;
        }
        removeProgress();
        F.removeThinking();
        finalizeStreamingMessage(data.content || "");
        F.applySessionMeta(data.session);
        F.setBusy(false);
        F.setConnectionStatus("就绪", true);
        if (data.usage) F.applyStatusUsage?.(data.usage);
        F.refreshStatusBar?.();
        {
          const todoId = F.getExecutingTodoId?.();
          if (todoId) {
            F.markTodoDoneById?.(todoId);
            void F.saveSessionPlan?.({ silent: true });
          }
        }
        flushQueue();
        break;
      }
      case "busy":
        removeProgress();
        F.removeThinking();
        appendMessage("error", data.message || "请等待当前任务完成", false);
        F.setBusy(false);
        if (F.wsConnected) {
          F.setConnectionStatus("就绪", true);
        }
        break;
      case "error":
        if (background) {
          if (runningChatSessions.size === 1) {
            runningChatSessions.clear();
          }
          F.refreshStatusBar?.();
          return;
        }
        removeProgress();
        clearStreamingMessage(false);
        F.removeThinking();
        appendMessage("error", data.message, false);
        clearRunningUserText(F.activeSessionId);
        runningChatSessions.delete(F.activeSessionId);
        F.setBusy(false);
        F.setConnectionStatus("就绪", true);
        F.refreshStatusBar?.();
        F.clearTodoRunningState?.();
        flushQueue();
        break;
      case "status":
        if (data.message && data.message.includes("思考")) {
          F.appendActivityStep?.("正在思考…");
        } else if (data.message === "就绪") {
          F.removeThinking();
          F.setBusy(false);
        }
        if (F.wsConnected) {
          F.setConnectionStatus(data.message || "就绪", true);
        }
        break;
      case "agent_step":
        F.appendActivityStep?.(data.message || "正在处理…");
        break;
      case "reasoning_delta":
        F.appendReasoningDelta?.(data.delta || "");
        break;
      case "progress":
        showProgress(data);
        break;
      case "tool_start":
        if (
          (data.tool === "generate_image" || data.tool === "describe_image") &&
          progressNode &&
          progressStartedAt != null
        ) {
          break;
        }
        showProgress({
          round: data.round,
          step: data.step,
          tool_count: data.tool_count,
          tools: [data.tool],
        });
        break;
      case "image_generated":
        if (data.path) {
          pendingGeneratedImages.push({ path: data.path });
        }
        break;
      case "approval_request":
        F.appendActivityStep?.("等待你确认操作…");
        showApprovalInChat(data);
        break;
      case "approval_summary_update":
        updateApprovalSummary(data);
        break;
      case "approval_wait":
        break;
      case "approval_auto":
        showAutoApprovalNote(data);
        break;
      case "ask_blocked":
        F.removeThinking();
        appendMessage("system", data.message || "Ask 模式下不能执行此操作，请切换到 Agent 或 Yolo。", false);
        break;
      case "file_change":
        showFileChangeCard(data);
        break;
      case "plan_updated":
        F.applySessionPlan?.(data);
        break;
      case "context_rebuild":
        showContextRebuildNotice();
        break;
      case "session_updated": {
        const sid = data.session_id;
        void (async () => {
          await F.refreshSessionList?.();
          if (sid && sid === F.activeSessionId) {
            await F.loadSessionDetail?.(sid, false);
          }
        })();
        break;
      }
      case "schedule_completed":
        F.onScheduleCompleted?.(data);
        if (data?.status === "ok") {
          F.setConnectionStatus?.(`定时任务「${data.title || ""}」已完成`, true);
        } else if (data?.status === "error") {
          F.setConnectionStatus?.(`定时任务「${data.title || ""}」失败`, false);
        }
        break;
      case "sessions_updated":
        void F.refreshSessionList?.();
        break;
      case "operation_logged":
        F.onOperationLogged?.();
        break;
    }
  }

  /* ── 文件变更 diff ── */

  function showFileChangeCard(data) {
    if (!data?.path) return;
    F.welcomePanel.classList.add("hidden");
    F.chatScroll.classList.remove("hidden");

    const node = document.createElement("div");
    node.className = "message file-change";

    const head = document.createElement("div");
    head.className = "file-change-head";
    head.textContent = data.is_new
      ? `📝 新建文件：${data.path}`
      : `📝 已修改：${data.path}`;

    const meta = document.createElement("div");
    meta.className = "file-change-meta";
    meta.textContent = `${data.old_chars || 0} → ${data.new_chars || 0} 字符`;

    const pre = document.createElement("pre");
    pre.className = "file-change-diff";
    pre.textContent = data.diff || "";

    const actions = document.createElement("div");
    actions.className = "file-change-actions";
    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "ghost-btn";
    openBtn.textContent = "在文件夹中打开";
    openBtn.addEventListener("click", () => {
      void F.apiFetch("/api/open-path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: data.path }),
      });
    });
    actions.appendChild(openBtn);

    node.append(head, meta, pre, actions);
    F.chatMessages.appendChild(node);
    F.scrollToBottom();
  }

  function appendMessage(kind, text, trackLocal = true, extra = {}) {
    F.welcomePanel.classList.add("hidden");
    F.chatScroll.classList.remove("hidden");

    const node = document.createElement("div");
    node.className = `message ${kind}` + (extra.queued ? " queued" : "");
    F.renderMessageBody(node, kind, text);
    if (extra.queued) {
      const badge = document.createElement("span");
      badge.className = "message-queue-badge";
      badge.textContent = F.t?.("composer.queue.badge") || "排队中";
      node.appendChild(badge);
    }
    const previewUrls = extra.imagePreviewUrls?.length
      ? extra.imagePreviewUrls
      : extra.imagePreviewUrl
        ? [extra.imagePreviewUrl]
        : [];
    if (previewUrls.length) {
      const wrap = document.createElement("div");
      wrap.className = previewUrls.length > 1 ? "message-images" : "";
      previewUrls.forEach((url, index) => {
        const img = document.createElement("img");
        img.className = "message-image";
        img.src = url;
        img.alt = previewUrls.length > 1 ? `粘贴的截图 ${index + 1}` : "粘贴的截图";
        wrap.appendChild(img);
      });
      node.appendChild(wrap);
    }
    F.appendGeneratedImages(node, extra.generatedImages);
    if (kind === "assistant") {
      F.attachAssistantMessageActions(node, text);
    }
    F.chatLog.appendChild(node);
    F.scrollToBottom(true);

    if (!trackLocal) return;
    const session = F.getActiveSession();
    if (session) {
      const entry = { kind, text };
      if (extra.generatedImages?.length) entry.generatedImages = extra.generatedImages;
      session.messages.push(entry);
      F.updateEmptyState(session.messages);
    }
  }

  /* ── 粘贴截图 ── */

  const MAX_PENDING_IMAGES = 10;
  let pendingImages = [];

  function i18nText(key, params, fallback) {
    const text = window.FridayI18n?.t?.(key, params);
    return text && text !== key ? text : fallback;
  }

  function attachmentSummary(count) {
    if (count === 1) {
      return i18nText("composer.attachment.one", null, "已附加 1 张图片");
    }
    return i18nText("composer.attachment.many", { n: count }, `已附加 ${count} 张图片`);
  }

  function hasComposerAttachment() {
    return pendingImages.some((item) => Boolean(item.path) && !item.uploading);
  }

  function hasComposerAttachmentPreview() {
    return pendingImages.length > 0;
  }

  function hideComposerAttachments() {
    document.getElementById("composerAttachments")?.classList.add("hidden");
  }

  function revokePreview(url) {
    if (url) URL.revokeObjectURL(url);
  }

  function clearPendingImages(revokePreviews = true) {
    if (revokePreviews) {
      pendingImages.forEach((item) => revokePreview(item.previewUrl));
    }
    pendingImages = [];
    hideComposerAttachments();
    const list = document.getElementById("composerAttachmentsList");
    if (list) list.replaceChildren();
    F.updateInputState();
  }

  function removePendingImageAt(index) {
    const item = pendingImages[index];
    if (!item) return;
    revokePreview(item.previewUrl);
    pendingImages.splice(index, 1);
    renderPendingImages();
    F.updateInputState();
  }

  function renderPendingImages() {
    const bar = document.getElementById("composerAttachments");
    const list = document.getElementById("composerAttachmentsList");
    const label = document.getElementById("composerAttachmentsLabel");
    if (!bar || !list) return;

    if (!pendingImages.length) {
      hideComposerAttachments();
      list.replaceChildren();
      return;
    }

    bar.classList.remove("hidden");
    const count = pendingImages.length;
    if (label) {
      label.textContent = attachmentSummary(count);
    }
    const clearBtn = document.getElementById("clearAttachmentsBtn");
    if (clearBtn) {
      clearBtn.textContent = i18nText("composer.removeAllAttachments", null, "全部移除");
    }

    list.replaceChildren();
    pendingImages.forEach((item, index) => {
      const chip = document.createElement("div");
      chip.className = "composer-attachment-chip";
      if (item.uploading) chip.classList.add("is-uploading");

      const img = document.createElement("img");
      img.src = item.previewUrl;
      img.alt = item.filename || "截图";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "icon-btn composer-attachment-remove";
      btn.title = i18nText("composer.removeAttachment", null, "移除截图");
      btn.setAttribute("aria-label", btn.title);
      btn.innerHTML =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>';
      btn.addEventListener("click", () => removePendingImageAt(index));

      chip.append(img, btn);
      list.appendChild(chip);
    });
  }

  async function uploadPastedFile(file) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("读取图片失败"));
      reader.readAsDataURL(file);
    });
    const res = await F.apiFetch("/api/chat/paste-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data_url: dataUrl,
        mime_type: file.type || "image/png",
      }),
    });
    if (!res.ok) {
      let detail = `上传失败 (${res.status})`;
      try {
        const err = await res.json();
        detail = err.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json();
  }

  function collectClipboardImages(event) {
    const cd = event.clipboardData;
    if (!cd) return [];

    const files = [];
    const seen = new Set();

    const push = (file) => {
      if (!file) return;
      const type = file.type || "";
      if (type && !type.startsWith("image/")) return;
      const sig = `${type || "image/*"}:${file.size}`;
      if (seen.has(sig)) return;
      seen.add(sig);
      files.push(file);
    };

    for (const item of cd.items || []) {
      if (item.kind !== "file") continue;
      if (item.type && !item.type.startsWith("image/")) continue;
      push(item.getAsFile());
    }
    if (files.length) return files;

    for (const file of cd.files || []) {
      push(file);
    }
    return files;
  }

  let lastPasteAt = 0;
  let lastPasteSig = "";

  function isComposerPasteTarget(target) {
    return Boolean(target?.closest?.(".composer-shell, .composer-input-wrap, #chatInput"));
  }

  async function handlePasteImage(file) {
    if (!file) return;
    const mime = file.type || "";
    if (mime && !mime.startsWith("image/")) return;
    if (!F.apiReady) {
      F.setConnectionStatus?.("请先完成 API 配置后再粘贴截图", false);
      if (F.openOnboarding) F.openOnboarding(1);
      else if (F.openSettings) F.openSettings("llm");
      return;
    }
    if (pendingImages.length >= MAX_PENDING_IMAGES) {
      F.setConnectionStatus(
        i18nText(
          "composer.attachmentLimit",
          { n: MAX_PENDING_IMAGES },
          `最多附加 ${MAX_PENDING_IMAGES} 张图片`
        ),
        false
      );
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    const slot = {
      path: "",
      filename: file.name || "截图.png",
      previewUrl,
      uploading: true,
    };
    pendingImages.push(slot);
    renderPendingImages();
    F.updateInputState();
    try {
      F.setConnectionStatus("正在保存截图...", false);
      const data = await uploadPastedFile(file);
      slot.path = data.path;
      slot.filename = data.filename || slot.filename;
      slot.uploading = false;
      renderPendingImages();
      F.setConnectionStatus("就绪", true);
      F.chatInput?.focus();
    } catch (err) {
      const idx = pendingImages.indexOf(slot);
      if (idx >= 0) pendingImages.splice(idx, 1);
      revokePreview(previewUrl);
      renderPendingImages();
      F.updateInputState();
      F.setConnectionStatus(`截图保存失败: ${(err.message || "未知错误").slice(0, 48)}`, false);
    }
  }

  function normalizeQueueItem(item) {
    if (typeof item === "string") {
      return { text: item, imagePaths: [], previewUrls: [] };
    }
    const imagePaths = Array.isArray(item.imagePaths)
      ? item.imagePaths.filter(Boolean)
      : item.imagePath
        ? [item.imagePath]
        : [];
    const previewUrls = Array.isArray(item.previewUrls)
      ? item.previewUrls.filter(Boolean)
      : item.previewUrl
        ? [item.previewUrl]
        : [];
    return {
      text: item.text || "",
      imagePaths,
      previewUrls,
    };
  }

  function defaultImagePrompt(count) {
    if (count > 1) return `请分析我粘贴的这 ${count} 张截图`;
    return "请分析我粘贴的这张截图";
  }

  function enqueueChat(item) {
    const normalized = normalizeQueueItem(item);
    void F.addInstructionTodo?.(normalized).then(() => {
      const displayText = normalized.text || defaultImagePrompt(normalized.imagePaths.length);
      appendMessage("user", displayText, true, {
        imagePreviewUrls: normalized.previewUrls.length ? normalized.previewUrls : undefined,
      });
      const pending = F.getPendingRunnableTodoCount?.() || 0;
      F.setConnectionStatus(
        pending === 1
          ? "已加入待办，当前任务完成后自动执行"
          : `已加入待办（${pending} 条待执行）`,
        true
      );
      F.updateInputState();
    });
  }

  function bindPasteHandlers() {
    document.addEventListener("paste", (event) => {
      if (!isComposerPasteTarget(event.target)) return;
      const files = collectClipboardImages(event);
      if (!files.length) return;
      const sig = files.map((file) => `${file.type || "image/*"}:${file.size}`).join("|");
      const now = Date.now();
      if (sig && sig === lastPasteSig && now - lastPasteAt < 400) return;
      lastPasteAt = now;
      lastPasteSig = sig;
      event.preventDefault();
      for (const file of files) {
        void handlePasteImage(file);
      }
    });

    document.getElementById("clearAttachmentsBtn")?.addEventListener("click", () => {
      clearPendingImages(true);
    });

    window.addEventListener("friday:languagechange", () => {
      if (pendingImages.length) renderPendingImages();
    });
  }

  /* ── 发送 ── */

  let sessionReadyPromise = null;

  async function ensureActiveSession() {
    if (F.activeSessionId) return true;
    if (sessionReadyPromise) {
      await sessionReadyPromise;
      return Boolean(F.activeSessionId);
    }
    sessionReadyPromise = F.createSession(true)
      .then(() => Boolean(F.activeSessionId))
      .catch(() => false)
      .finally(() => {
        sessionReadyPromise = null;
      });
    return sessionReadyPromise;
  }

  function flushQueue() {
    void F.processNextTodo?.();
  }

  async function sendChat(message, fromQueue = false, options = {}) {
    const composed = F.composeMessageWithQuote(message.trim());
    const text = composed.trim();
    const imagePaths = Array.isArray(options.imagePaths)
      ? options.imagePaths.filter(Boolean)
      : pendingImages.map((item) => item.path).filter(Boolean);
    const previewUrls = Array.isArray(options.previewUrls)
      ? options.previewUrls.filter(Boolean)
      : pendingImages.map((item) => item.previewUrl).filter(Boolean);
    if (!text && !imagePaths.length) return;
    if (!fromQueue && pendingImages.some((item) => item.uploading)) {
      F.setConnectionStatus("截图仍在保存，请稍候…", false);
      return;
    }

    if (!F.activeSessionId) {
      if (!fromQueue) F.setConnectionStatus("正在准备对话...", false);
      const ready = await ensureActiveSession();
      if (!ready) {
        F.setConnectionStatus("无法创建对话，请重试", false);
        return;
      }
      if (F.wsConnected) F.setConnectionStatus("就绪", true);
    }

    if (!F.apiReady) {
      if (F.openOnboarding) F.openOnboarding(1);
      else if (F.openSettings) F.openSettings("llm");
      return;
    }

    if (hasBackgroundChatTurn() && !fromQueue) {
      F.setConnectionStatus("另一会话仍在处理，请稍候…", false);
      return;
    }

    if (F.busy && !fromQueue) {
      enqueueChat({ text, imagePaths, previewUrls });
      clearPendingImages(true);
      F.clearComposerQuote?.();
      return;
    }

    if (!F.wsConnected) {
      enqueueChat({ text, imagePaths, previewUrls });
      if (!fromQueue) F.setConnectionStatus("正在连接，消息已排队...");
      if (!fromQueue) F.clearComposerQuote?.();
      return;
    }

    const displayText = text || defaultImagePrompt(imagePaths.length);
    if (!fromQueue) {
      appendMessage("user", displayText, true, {
        imagePreviewUrls: previewUrls.length ? previewUrls : undefined,
      });
    } else if (options.showUserMessage) {
      appendMessage("user", displayText, true, {
        imagePreviewUrls: previewUrls.length ? previewUrls : undefined,
      });
      if (options.todoId) F.setExecutingTodoId?.(options.todoId);
    } else if (options.todoId) {
      F.setExecutingTodoId?.(options.todoId);
    }
    clearPendingImages(true);
    F.clearComposerQuote?.();
    F.updateInputState();
    F.setBusy(true);
    resetPendingGeneratedImages();
    F.showThinking();

    if (!F.ws || F.ws.readyState !== WebSocket.OPEN) {
      if (!fromQueue) {
        enqueueChat({ text, imagePaths, previewUrls });
        const session = F.getActiveSession();
        if (session && session.messages.length) session.messages.pop();
        F.chatLog.lastElementChild?.remove();
      } else {
        F.clearTodoRunningState?.();
      }
      F.removeThinking();
      F.setBusy(false);
      F.setConnectionStatus("连接未就绪，正在重连...");
      return;
    }

    try {
      await F.saveSessionPlan?.();
    } catch (_err) {
      /* 保存失败不阻断对话 */
    }

    runningUserTextBySession.set(F.activeSessionId, text || displayText);
    runningChatSessions.add(F.activeSessionId);
    F.ws.send(
      JSON.stringify({
        type: "chat",
        message: text,
        session_id: F.activeSessionId,
        image_paths: imagePaths,
        interaction_mode: F.getInteractionMode?.() || "agent",
      })
    );
  }

  /* ── 审批（对话内确认） ── */

  let pendingApprovalNode = null;

  function formatBytes(num) {
    if (!num || num <= 0) return "0 B";
    if (num >= 1024 ** 3) return `${(num / (1024 ** 3)).toFixed(2)} GB`;
    if (num >= 1024 ** 2) return `${(num / (1024 ** 2)).toFixed(1)} MB`;
    if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`;
    return `${num} B`;
  }

  let contextRebuildNoticeEl = null;

  function showContextRebuildNotice() {
    if (contextRebuildNoticeEl) return;
    const bar = document.createElement("div");
    bar.className = "context-rebuild-notice";
    bar.setAttribute("role", "status");
    bar.innerHTML =
      '<span>上下文已自动整理以继续长对话。</span>' +
      '<button type="button" class="context-rebuild-dismiss" aria-label="关闭">×</button>';
    bar.querySelector(".context-rebuild-dismiss")?.addEventListener("click", () => {
      bar.remove();
      contextRebuildNoticeEl = null;
    });
    const main = document.querySelector(".main");
    if (main) main.insertBefore(bar, main.firstChild?.nextSibling || null);
    contextRebuildNoticeEl = bar;
  }

  function showAutoApprovalNote(_data) {
    // 同轮次已确认的操作不再插入命令/脚本详情，避免刷屏；进度见上方指示条。
    F.setConnectionStatus("已确认，继续执行…", true);
  }

  function approvalTitle(data) {
    if (data.untrusted_download) return "非官方来源下载确认";
    if (data.large_download) return "大文件下载确认";
    const titles = {
      run_powershell: "PowerShell 命令确认",
      run_python: "Python 脚本确认",
      run_python_script: "运行脚本文件确认",
      write_text_file: "写入文件确认",
      move_file: "移动文件确认",
      copy_file: "复制文件确认",
      delete_file: "删除文件确认",
      delete_directory: "删除文件夹确认",
      organize_directory: "整理文件夹确认",
      download_file: "下载文件确认",
      download_software: "下载软件确认",
      generate_image: "生图确认",
    };
    return titles[data.tool_name] || "需要你确认一下";
  }

  function showApprovalInChat(data) {
    F.pendingApprovalId = data.approval_id;
    F.welcomePanel.classList.add("hidden");
    F.chatScroll.classList.remove("hidden");
    removeProgress();

    if (pendingApprovalNode) {
      pendingApprovalNode.remove();
      pendingApprovalNode = null;
    }

    const node = document.createElement("div");
    node.className = "message approval";
    node.dataset.approvalId = data.approval_id;

    const title = document.createElement("p");
    title.className = "approval-title";
    title.textContent = approvalTitle(data);

    const summary = (data.summary || "即将在这台电脑上执行一项操作").trim();
    let detail = (data.preview || "").trim();
    if (detail === summary) {
      detail = "";
    }

    const lead = document.createElement("p");
    lead.className = "approval-lead";
    lead.textContent = "准备做什么";

    const text = document.createElement("p");
    text.className = "approval-text";
    text.textContent = summary;

    if (data.untrusted_download) {
      const trust = data.trust_label || "未验证";
      detail = detail
        ? `${detail}\n\n⚠ 该下载来源未通过官方认证（${trust}）。仅在你确认信任该网站时才继续。`
        : `⚠ 该下载来源未通过官方认证（${trust}）。仅在你确认信任该网站时才继续。`;
    } else if (data.large_download) {
      const sizeHint = data.download_size_bytes
        ? `约 ${formatBytes(data.download_size_bytes)}`
        : "大小未知";
      const sizeNote = `这将从互联网下载一个大文件（${sizeHint}，最高允许 10 GB）。请确认来源可信后再继续。`;
      detail = detail ? `${detail}\n\n${sizeNote}` : sizeNote;
    }

    const actions = document.createElement("div");
    actions.className = "approval-actions";

    const rejectBtn = document.createElement("button");
    rejectBtn.type = "button";
    rejectBtn.className = "ghost-btn";
    rejectBtn.textContent = "拒绝";
    rejectBtn.addEventListener("click", () => resolveApproval(false));

    const approveBtn = document.createElement("button");
    approveBtn.type = "button";
    approveBtn.className = "primary-btn";
    approveBtn.textContent = "同意";
    approveBtn.addEventListener("click", () => resolveApproval(true));

    actions.append(rejectBtn, approveBtn);
    if (detail) {
      const detailLead = document.createElement("p");
      detailLead.className = "approval-lead";
      detailLead.textContent = "补充说明";
      const detailNode = document.createElement("p");
      detailNode.className = "approval-detail";
      detailNode.textContent = detail;
      node.append(title, lead, text, detailLead, detailNode, actions);
    } else {
      node.append(title, lead, text, actions);
    }
    F.chatLog.appendChild(node);
    pendingApprovalNode = node;
    F.scrollToBottom(true);
  }

  function updateApprovalSummary(data) {
    if (!data?.approval_id || F.pendingApprovalId !== data.approval_id) return;
    const summary = (data.summary || "").trim();
    if (!summary) return;
    const node = pendingApprovalNode;
    if (!node || node.dataset.approvalId !== data.approval_id) return;
    const text = node.querySelector(".approval-text");
    if (text) {
      text.textContent = summary;
    }
  }

  async function resolveApproval(approved) {
    const id = F.pendingApprovalId;
    if (!id) return;
    F.pendingApprovalId = null;

    const node = pendingApprovalNode;
    const buttons = node?.querySelector(".approval-actions");
    if (buttons) {
      buttons.querySelectorAll("button").forEach((btn) => {
        btn.disabled = true;
      });
    }

    try {
      await F.apiFetch("/api/chat/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval_id: id, approved }),
      });
    } catch {
      F.pendingApprovalId = id;
      if (buttons) {
        buttons.querySelectorAll("button").forEach((btn) => {
          btn.disabled = false;
        });
      }
      return;
    }

    if (node) {
      node.classList.add(approved ? "approved" : "rejected");
      buttons?.remove();
      const status = document.createElement("p");
      status.className = "approval-status";
      status.textContent = approved ? "已允许，继续执行…" : "已取消";
      node.appendChild(status);
      pendingApprovalNode = null;
    }

    if (approved) {
      F.showThinking();
    }
    F.scrollToBottom();
  }

  /* ── 停止生成 ── */

  async function executeStopChat() {
    if (!F.busy && !hasBackgroundChatTurn()) return;
    const sessionId = activeRunningSessionId();
    removeProgress();
    F.removeThinking();
    clearStreamingMessage(false);
    F.setBusy(false);
    F.setConnectionStatus("正在停止...", false);
    try {
      await F.apiFetch("/api/chat/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      // 忽略网络错误，UI 由助手返回的结果恢复
    }
    runningChatSessions.delete(sessionId);
    clearRunningUserText(sessionId);
    flushQueue();
  }

  async function requestStopChat() {
    if (!F.busy && !hasBackgroundChatTurn()) return;
    if (stopConfirmResolver) return;
    const choice = await showStopConfirmModal();
    if (choice === "continue") return;
    const sessionId = activeRunningSessionId();
    if (choice === "modify") {
      const savedText = runningUserTextBySession.get(sessionId) || "";
      await executeStopChat();
      restoreRunningMessageToComposer(sessionId, savedText);
      return;
    }
    if (choice === "abort") {
      await executeStopChat();
    }
  }

  function bindStopButton() {
    const btn = F.stopBtn || document.getElementById("stopBtn");
    if (!btn || btn.dataset.stopBound === "1") return;
    btn.dataset.stopBound = "1";
    btn.addEventListener("click", () => {
      void requestStopChat();
    });
  }

  function bindStopConfirmModal() {
    const modal = document.getElementById("stopConfirmModal");
    if (!modal || modal.dataset.bound === "1") return;
    modal.dataset.bound = "1";
    document.getElementById("stopConfirmContinue")?.addEventListener("click", () => {
      resolveStopConfirm("continue");
    });
    document.getElementById("stopConfirmAbort")?.addEventListener("click", () => {
      resolveStopConfirm("abort");
    });
    document.getElementById("stopConfirmModify")?.addEventListener("click", () => {
      resolveStopConfirm("modify");
    });
    modal.addEventListener("click", (event) => {
      if (event.target === modal) resolveStopConfirm("continue");
    });
    document.addEventListener("keydown", (event) => {
      if (modal.classList.contains("hidden")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        resolveStopConfirm("continue");
      }
    });
  }

  /* ── 挂载 ── */

  F.connectWs = connectWs;
  F.detachChatUiForSessionSwitch = detachChatUiForSessionSwitch;
  F.hasBackgroundChatTurn = hasBackgroundChatTurn;
  F.handleEvent = handleEvent;
  F.appendMessage = appendMessage;
  F.flushQueue = flushQueue;
  F.sendChat = sendChat;
  F.showApprovalInChat = showApprovalInChat;
  F.resolveApproval = resolveApproval;
  // 旧版 app.js 缓存仍调用 F.stopChat()，统一走确认弹窗
  F.stopChat = requestStopChat;
  F.requestStopChat = requestStopChat;
  bindStopConfirmModal();
  bindStopButton();
  F.hasComposerAttachment = hasComposerAttachment;
  F.hasComposerAttachmentPreview = hasComposerAttachmentPreview;
  F.clearComposerAttachment = clearPendingImages;
  bindPasteHandlers();
})();
