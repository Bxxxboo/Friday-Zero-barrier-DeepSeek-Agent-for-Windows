/* ================================================================= *
 *  schedules.js — 定时任务设置页
 *  依赖 utils.js / settings.js
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) { console.error("schedules.js: window.Friday 未初始化"); return; }

  const listEl = document.getElementById("scheduleList");
  const emptyEl = document.getElementById("scheduleEmpty");
  const formWrap = document.getElementById("scheduleFormWrap");
  const formEl = document.getElementById("scheduleForm");
  const formTitle = document.getElementById("scheduleFormTitle");
  const resultEl = document.getElementById("scheduleResult");
  const autoApproveEl = document.getElementById("autoApproveScheduledWrites");

  let editingId = null;

  function formatRunTime(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function statusLabel(task) {
    if (!task.last_run_at) return "尚未运行";
    if (task.last_run_status === "ok") return "上次成功";
    if (task.last_run_status === "error") return "上次失败";
    return "已运行";
  }

  function showResult(text, ok) {
    if (!resultEl) return;
    resultEl.className = ok ? "settings-result ok" : "settings-result error";
    resultEl.textContent = text;
  }

  function syncFrequencyFields() {
    const freq = document.getElementById("scheduleFrequency")?.value;
    document.getElementById("scheduleDayRow")?.classList.toggle("hidden", freq !== "weekly");
    document.getElementById("scheduleTimeRow")?.classList.toggle("hidden", freq === "interval" || freq === "cron");
    document.getElementById("scheduleCronRow")?.classList.toggle("hidden", freq !== "cron");
    document.getElementById("scheduleIntervalRow")?.classList.toggle("hidden", freq !== "interval");
  }

  function clearForm() {
    editingId = null;
    if (!formEl) return;
    formEl.reset();
    document.getElementById("scheduleEnabled").checked = true;
    document.getElementById("scheduleRetryOnFailure").checked = true;
    document.getElementById("scheduleMaxRetries").value = "1";
    document.getElementById("scheduleFrequency").value = "weekly";
    document.getElementById("scheduleDayOfWeek").value = "4";
    document.getElementById("scheduleHour").value = "9";
    document.getElementById("scheduleMinute").value = "0";
    document.getElementById("scheduleIntervalHours").value = "6";
    document.getElementById("scheduleCronExpr").value = "";
    syncFrequencyFields();
    if (formTitle) formTitle.textContent = "新建定时任务";
  }

  function showForm(task) {
    clearForm();
    if (task) {
      editingId = task.id;
      if (formTitle) formTitle.textContent = "编辑定时任务";
      document.getElementById("scheduleTitle").value = task.title;
      document.getElementById("schedulePrompt").value = task.prompt;
      document.getElementById("scheduleFrequency").value = task.frequency;
      document.getElementById("scheduleDayOfWeek").value = String(task.day_of_week);
      document.getElementById("scheduleHour").value = String(task.hour);
      document.getElementById("scheduleMinute").value = String(task.minute);
      document.getElementById("scheduleCronExpr").value = task.cron_expr || "";
      document.getElementById("scheduleIntervalHours").value = String(task.interval_hours || 6);
      document.getElementById("scheduleEnabled").checked = task.enabled;
      document.getElementById("scheduleRetryOnFailure").checked = task.retry_on_failure !== false;
      document.getElementById("scheduleMaxRetries").value = String(task.max_retries ?? 1);
    }
    syncFrequencyFields();
    formWrap?.classList.remove("hidden");
    formWrap?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideForm() {
    formWrap?.classList.add("hidden");
    clearForm();
    showResult("", true);
  }

  function collectFormPayload() {
    return {
      title: document.getElementById("scheduleTitle").value.trim(),
      prompt: document.getElementById("schedulePrompt").value.trim(),
      frequency: document.getElementById("scheduleFrequency").value,
      day_of_week: parseInt(document.getElementById("scheduleDayOfWeek").value, 10),
      hour: parseInt(document.getElementById("scheduleHour").value, 10),
      minute: parseInt(document.getElementById("scheduleMinute").value, 10),
      cron_expr: document.getElementById("scheduleCronExpr").value.trim(),
      interval_hours: parseInt(document.getElementById("scheduleIntervalHours").value, 10) || 6,
      enabled: document.getElementById("scheduleEnabled").checked,
      retry_on_failure: document.getElementById("scheduleRetryOnFailure").checked,
      max_retries: parseInt(document.getElementById("scheduleMaxRetries").value, 10) || 0,
    };
  }

  async function loadAutoApproveSetting() {
    if (!autoApproveEl) return;
    try {
      const res = await F.apiFetch("/api/settings");
      const data = await res.json();
      autoApproveEl.checked = Boolean(data.auto_approve_scheduled_writes);
    } catch {
      autoApproveEl.checked = false;
    }
  }

  async function saveAutoApproveSetting() {
    if (!autoApproveEl) return;
    try {
      await F.apiFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_approve_scheduled_writes: autoApproveEl.checked }),
      });
    } catch (err) {
      console.error(err);
    }
  }

  async function loadRunLog(scheduleId, container) {
    container.textContent = "加载中…";
    try {
      const res = await F.apiFetch(`/api/schedules/${scheduleId}/runs?limit=10`);
      const data = await res.json();
      const ops = data.operations || [];
      if (ops.length === 0) {
        container.textContent = "暂无执行记录";
        return;
      }
      const ul = document.createElement("ul");
      ul.className = "schedule-run-log";
      ops.forEach((op) => {
        const li = document.createElement("li");
        const ok = op.success ? "成功" : "失败";
        li.textContent = `${formatRunTime(op.ts)} · ${ok} · ${op.summary || op.tool}`;
        ul.appendChild(li);
      });
      container.innerHTML = "";
      container.appendChild(ul);
    } catch {
      container.textContent = "加载失败";
    }
  }

  function renderScheduleCard(task) {
    const card = document.createElement("article");
    card.className = "schedule-card" + (task.enabled ? "" : " schedule-card-off");
    card.dataset.id = task.id;

    const head = document.createElement("div");
    head.className = "schedule-card-head";

    const title = document.createElement("h5");
    title.className = "schedule-card-title";
    title.textContent = task.title;

    const toggle = document.createElement("label");
    toggle.className = "schedule-toggle";
    toggle.title = task.enabled ? "点击暂停" : "点击启用";
    toggle.innerHTML = `<input type="checkbox" ${task.enabled ? "checked" : ""} /><span class="schedule-toggle-ui"></span>`;
    toggle.querySelector("input").addEventListener("change", async () => {
      await F.apiFetch(`/api/schedules/${task.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: toggle.querySelector("input").checked }),
      });
      loadSchedules();
    });

    head.appendChild(title);
    head.appendChild(toggle);

    const meta = document.createElement("p");
    meta.className = "schedule-card-meta";
    const retryHint = task.retry_count > 0 ? ` · 重试 ${task.retry_count}/${task.max_retries}` : "";
    meta.textContent = `${task.schedule_label} · 下次 ${formatRunTime(task.next_run_at)}${retryHint}`;

    const status = document.createElement("p");
    status.className = "schedule-card-status schedule-status-" + (task.last_run_status || "none");
    const msg = task.last_run_message ? `：${task.last_run_message.slice(0, 80)}` : "";
    status.textContent = `${statusLabel(task)}${msg}`;

    const prompt = document.createElement("p");
    prompt.className = "schedule-card-prompt";
    prompt.textContent = task.prompt;

    const runLogWrap = document.createElement("div");
    runLogWrap.className = "schedule-run-log-wrap hidden";
    const runLog = document.createElement("div");
    runLog.className = "schedule-run-log-body";
    runLogWrap.appendChild(runLog);

    const actions = document.createElement("div");
    actions.className = "schedule-card-actions";

    const runBtn = document.createElement("button");
    runBtn.type = "button";
    runBtn.className = "ghost-btn schedule-run-btn";
    runBtn.textContent = "立即运行";
    runBtn.addEventListener("click", () => runNow(task.id, runBtn));

    const logBtn = document.createElement("button");
    logBtn.type = "button";
    logBtn.className = "ghost-btn";
    logBtn.textContent = "执行记录";
    logBtn.addEventListener("click", () => {
      const hidden = runLogWrap.classList.toggle("hidden");
      if (!hidden) loadRunLog(task.id, runLog);
    });

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "ghost-btn";
    editBtn.textContent = "编辑";
    editBtn.addEventListener("click", () => showForm(task));

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "ghost-btn schedule-del-btn";
    delBtn.textContent = "删除";
    delBtn.addEventListener("click", async () => {
      if (!confirm(`确定删除「${task.title}」？`)) return;
      await F.apiFetch(`/api/schedules/${task.id}`, { method: "DELETE" });
      loadSchedules();
    });

    actions.append(runBtn, logBtn, editBtn, delBtn);
    card.append(head, meta, status, prompt, runLogWrap, actions);
    return card;
  }

  async function runNow(id, btn) {
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "运行中…";
    showResult("正在执行任务…", true);
    try {
      const res = await F.apiFetch(`/api/schedules/${id}/run-now`, { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        showResult(data.message || "任务已完成", true);
      } else {
        showResult(data.message || "任务执行失败", false);
      }
      loadSchedules();
      F.onOperationLogged?.();
    } catch {
      showResult("请求失败，请重试", false);
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  async function loadSchedules() {
    if (!listEl) return;
    listEl.innerHTML = "";
    emptyEl?.classList.add("hidden");
    await loadAutoApproveSetting();

    try {
      const res = await F.apiFetch("/api/schedules");
      const data = await res.json();
      const tasks = data.schedules || [];
      if (tasks.length === 0) {
        emptyEl?.classList.remove("hidden");
        return;
      }
      tasks.forEach((task) => listEl.appendChild(renderScheduleCard(task)));
    } catch (err) {
      console.error(err);
      if (emptyEl) {
        emptyEl.textContent = "加载失败，请稍后重试";
        emptyEl.classList.remove("hidden");
      }
    }
  }

  async function saveSchedule(event) {
    event.preventDefault();
    const payload = collectFormPayload();
    if (!payload.title) {
      showResult("请填写任务名称", false);
      return;
    }
    if (!payload.prompt) {
      showResult("请填写任务指令", false);
      return;
    }
    if (payload.frequency === "cron" && !payload.cron_expr) {
      showResult("请填写 Cron 表达式", false);
      return;
    }

    showResult("保存中…", true);
    try {
      const url = editingId ? `/api/schedules/${editingId}` : "/api/schedules";
      const method = editingId ? "PUT" : "POST";
      const res = await F.apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showResult(err.detail || "保存失败", false);
        return;
      }
      showResult(editingId ? "任务已更新" : "任务已创建", true);
      hideForm();
      loadSchedules();
    } catch {
      showResult("保存失败，请重试", false);
    }
  }

  function fillFridayDownloadsPreset() {
    showForm(null);
    document.getElementById("scheduleTitle").value = "每周五整理下载文件夹";
    document.getElementById("schedulePrompt").value =
      "查看我的下载文件夹，按文件类型整理。先列出整理计划，确认后执行移动。";
    document.getElementById("scheduleFrequency").value = "weekly";
    document.getElementById("scheduleDayOfWeek").value = "4";
    document.getElementById("scheduleHour").value = "9";
    document.getElementById("scheduleMinute").value = "0";
    document.getElementById("scheduleEnabled").checked = true;
    syncFrequencyFields();
  }

  document.getElementById("scheduleNewBtn")?.addEventListener("click", () => showForm(null));
  document.getElementById("schedulePresetBtn")?.addEventListener("click", fillFridayDownloadsPreset);
  document.getElementById("scheduleCancelBtn")?.addEventListener("click", hideForm);
  formEl?.addEventListener("submit", saveSchedule);
  document.getElementById("scheduleFrequency")?.addEventListener("change", syncFrequencyFields);
  autoApproveEl?.addEventListener("change", saveAutoApproveSetting);

  const origSwitch = F.switchSettingsPanel;
  F.switchSettingsPanel = (panel) => {
    origSwitch(panel);
    if (panel === "schedules") loadSchedules();
  };

  F.loadSchedules = loadSchedules;
  F.openSchedulesSettings = () => F.openSettings("schedules");

  F.onScheduleCompleted = (data) => {
    if (!data) return;
    const ok = data.status === "ok";
    const title = data.title || "定时任务";
    showResult(ok ? `「${title}」已完成，可在侧栏打开会话查看结果` : `「${title}」失败：${data.message || ""}`, ok);
    void loadSchedules();
  };
})();
