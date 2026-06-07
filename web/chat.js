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

    F.ws = new WebSocket(
      `${protocol}://${location.host}/ws/chat${F.resolveApiToken() ? `?token=${encodeURIComponent(F.resolveApiToken())}` : ""}`
    );

    F.ws.onopen = () => {
      F.wsRetryCount = 0;
      F.wsConnected = true;
      F.setConnectionStatus("就绪", true);
      F.refreshStatusBar?.();
      flushQueue();
    };

    F.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "connected") return;
      handleEvent(data);
    };

    F.ws.onerror = () => {
      F.wsConnected = false;
      F.setBusy(false);
      F.removeThinking();
      removeProgress();
    };

    F.ws.onclose = () => {
      F.wsConnected = false;
      F.setBusy(false);
      F.removeThinking();
      removeProgress();
      F.setConnectionStatus("连接断开，重连中...");
      setTimeout(connectWs, 1500);
    };
  }

  /* ── 进度指示器 ── */

  let progressNode = null;
  let pendingGeneratedImages = [];
  let progressTimer = null;

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

  function startProgressTimer(baseText) {
    stopProgressTimer();
    const started = Date.now();
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
    const tools = data.tools || [];
    const isImageGen = tools.includes("generate_image");
    // 生图由前端 1s 计时器更新，忽略后端重复 progress，避免进度条被重建、计时归零
    if (data.heartbeat && progressNode && isImageGen) return;

    removeProgress();
    const msg = formatProgressMessage(data);
    progressNode = document.createElement("div");
    progressNode.className = "message progress";
    progressNode.innerHTML = `<div class="progress-bar"><div class="progress-fill"></div></div><span class="progress-text">${msg}</span>`;
    F.chatLog.appendChild(progressNode);
    F.scrollToBottom();
    F.removeThinking();
    if (isImageGen) {
      startProgressTimer(msg.replace(/…$/, ""));
    }
  }

  function removeProgress() {
    stopProgressTimer();
    if (progressNode) {
      progressNode.remove();
      progressNode = null;
    }
  }

  /* ── 流式消息 ── */

  function startStreamingMessage() {
    F.removeThinking();
    F.welcomePanel.classList.add("hidden");
    F.chatScroll.classList.remove("hidden");
    F.streamingNode = document.createElement("div");
    F.streamingNode.className = "message assistant streaming";
    F.streamingText = "";
    F.streamingNode.textContent = "";
    F.chatLog.appendChild(F.streamingNode);
    F.scrollToBottom();
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

  function handleEvent(data) {
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
      case "assistant":
        removeProgress();
        F.removeThinking();
        finalizeStreamingMessage(data.content || "");
        F.applySessionMeta(data.session);
        F.setBusy(false);
        F.setConnectionStatus("就绪", true);
        if (data.usage) F.applyStatusUsage?.(data.usage);
        F.refreshStatusBar?.();
        flushQueue();
        break;
      case "busy":
        F.removeThinking();
        appendMessage("error", data.message || "请等待当前任务完成", false);
        if (F.wsConnected) {
          F.setConnectionStatus("就绪", true);
        }
        break;
      case "error":
        clearStreamingMessage(false);
        F.removeThinking();
        appendMessage("error", data.message, false);
        F.setBusy(false);
        F.setConnectionStatus("就绪", true);
        F.refreshStatusBar?.();
        flushQueue();
        break;
      case "status":
        if (data.message && data.message.includes("思考")) {
          F.showThinking();
        } else if (data.message === "就绪") {
          F.removeThinking();
          F.setBusy(false);
        }
        if (F.wsConnected) {
          F.setConnectionStatus(data.message || "就绪", true);
        }
        break;
      case "progress":
        showProgress(data);
        break;
      case "tool_start":
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
        F.removeThinking();
        showApprovalInChat(data);
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
      case "operation_logged":
        F.onOperationLogged?.();
        break;
    }
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
    if (extra.imagePreviewUrl) {
      const img = document.createElement("img");
      img.className = "message-image";
      img.src = extra.imagePreviewUrl;
      img.alt = "粘贴的截图";
      node.appendChild(img);
    }
    F.appendGeneratedImages(node, extra.generatedImages);
    F.chatLog.appendChild(node);
    F.scrollToBottom();

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

  let pendingImage = null;

  function hasComposerAttachment() {
    return Boolean(pendingImage?.path);
  }

  function hideComposerAttachment() {
    document.getElementById("composerAttachment")?.classList.add("hidden");
  }

  function clearPendingImage(revokePreview = true) {
    if (revokePreview && pendingImage?.previewUrl) {
      URL.revokeObjectURL(pendingImage.previewUrl);
    }
    pendingImage = null;
    hideComposerAttachment();
    const img = document.getElementById("composerAttachmentPreview");
    if (img) img.removeAttribute("src");
    F.updateInputState();
  }

  function showPendingImage(data, previewUrl) {
    if (pendingImage?.previewUrl && pendingImage.previewUrl !== previewUrl) {
      URL.revokeObjectURL(pendingImage.previewUrl);
    }
    pendingImage = { path: data.path, filename: data.filename, previewUrl };
    const bar = document.getElementById("composerAttachment");
    const img = document.getElementById("composerAttachmentPreview");
    const name = document.getElementById("composerAttachmentName");
    if (bar && img) {
      img.src = previewUrl;
      if (name) name.textContent = data.filename || "截图";
      bar.classList.remove("hidden");
    }
    F.updateInputState();
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

  async function handlePasteImage(file) {
    if (!file?.type?.startsWith("image/")) return;
    if (!F.apiReady) {
      if (F.openOnboarding) F.openOnboarding(1);
      else if (F.openSettings) F.openSettings("api");
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    try {
      F.setConnectionStatus("正在保存截图...", false);
      const data = await uploadPastedFile(file);
      showPendingImage(data, previewUrl);
      F.setConnectionStatus("就绪", true);
      F.chatInput?.focus();
    } catch (err) {
      URL.revokeObjectURL(previewUrl);
      F.setConnectionStatus(`截图保存失败: ${(err.message || "未知错误").slice(0, 48)}`, false);
    }
  }

  function normalizeQueueItem(item) {
    if (typeof item === "string") return { text: item, imagePath: "", previewUrl: "" };
    return {
      text: item.text || "",
      imagePath: item.imagePath || "",
      previewUrl: item.previewUrl || "",
    };
  }

  function enqueueChat(item) {
    const normalized = normalizeQueueItem(item);
    F.pendingQueue.push(normalized);
    const displayText = normalized.text || "请分析我粘贴的这张截图";
    appendMessage("user", displayText, true, {
      imagePreviewUrl: normalized.previewUrl || undefined,
      queued: true,
    });
    F.updateQueueIndicator?.();
    F.setConnectionStatus(
      F.pendingQueue.length === 1
        ? "已加入队列，当前任务完成后自动执行"
        : `已加入队列（${F.pendingQueue.length} 条待执行）`,
      true
    );
    F.updateInputState();
  }

  function bindPasteHandlers() {
    F.chatInput?.addEventListener("paste", (event) => {
      const items = event.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.type.startsWith("image/")) {
          event.preventDefault();
          const file = item.getAsFile();
          if (file) void handlePasteImage(file);
          return;
        }
      }
    });

    document.getElementById("clearAttachmentBtn")?.addEventListener("click", () => {
      clearPendingImage(true);
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
    if (F.busy || F.pendingQueue.length === 0) return;
    const item = normalizeQueueItem(F.pendingQueue.shift());
    F.updateQueueIndicator?.();
    void sendChat(item.text, true, {
      imagePath: item.imagePath,
      previewUrl: item.previewUrl,
    });
  }

  async function sendChat(message, fromQueue = false, options = {}) {
    const text = message.trim();
    const imagePath = options.imagePath || pendingImage?.path || "";
    const previewUrl = options.previewUrl || pendingImage?.previewUrl || "";
    if (!text && !imagePath) return;

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
      else if (F.openSettings) F.openSettings("api");
      return;
    }

    if (F.busy && !fromQueue) {
      enqueueChat({ text, imagePath, previewUrl });
      pendingImage = null;
      hideComposerAttachment();
      return;
    }

    if (!F.wsConnected) {
      enqueueChat({ text, imagePath, previewUrl });
      if (!fromQueue) F.setConnectionStatus("正在连接，消息已排队...");
      return;
    }

    const displayText = text || "请分析我粘贴的这张截图";
    if (!fromQueue) {
      appendMessage("user", displayText, true, { imagePreviewUrl: previewUrl || undefined });
    } else {
      const nextQueued = document.querySelector(".message.user.queued");
      if (nextQueued) {
        nextQueued.classList.remove("queued");
        const badge = nextQueued.querySelector(".message-queue-badge");
        if (badge) badge.textContent = F.t?.("composer.queue.running") || "执行中…";
      }
    }
    pendingImage = null;
    hideComposerAttachment();
    F.updateInputState();
    F.setBusy(true);
    resetPendingGeneratedImages();
    F.showThinking();

    if (!F.ws || F.ws.readyState !== WebSocket.OPEN) {
      enqueueChat({ text, imagePath, previewUrl });
      const session = F.getActiveSession();
      if (session && session.messages.length) session.messages.pop();
      F.chatLog.lastElementChild?.remove();
      F.removeThinking();
      F.setBusy(false);
      F.setConnectionStatus("连接未就绪，正在重连...");
      return;
    }

    F.ws.send(
      JSON.stringify({
        type: "chat",
        message: text,
        session_id: F.activeSessionId,
        image_path: imagePath,
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
      const detailNode = document.createElement("p");
      detailNode.className = "approval-detail";
      detailNode.textContent = detail;
      node.append(title, text, detailNode, actions);
    } else {
      node.append(title, text, actions);
    }
    F.chatLog.appendChild(node);
    pendingApprovalNode = node;
    F.scrollToBottom();
  }

  async function resolveApproval(approved) {
    const id = F.pendingApprovalId;
    if (!id) return;

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
      if (buttons) {
        buttons.querySelectorAll("button").forEach((btn) => {
          btn.disabled = false;
        });
      }
      return;
    }

    F.pendingApprovalId = null;
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

  async function stopChat() {
    if (!F.busy) return;
    removeProgress();
    F.removeThinking();
    clearStreamingMessage(false);
    F.setBusy(false);
    F.setConnectionStatus("正在停止...", false);
    try {
      await F.apiFetch("/api/chat/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: F.activeSessionId || "" }),
      });
    } catch {
      // 忽略网络错误，UI 由助手返回的结果恢复
    }
    flushQueue();
  }

  /* ── 挂载 ── */

  F.connectWs = connectWs;
  F.handleEvent = handleEvent;
  F.appendMessage = appendMessage;
  F.flushQueue = flushQueue;
  F.sendChat = sendChat;
  F.showApprovalInChat = showApprovalInChat;
  F.resolveApproval = resolveApproval;
  F.stopChat = stopChat;
  F.hasComposerAttachment = hasComposerAttachment;
  F.clearComposerAttachment = clearPendingImage;
  bindPasteHandlers();
})();
