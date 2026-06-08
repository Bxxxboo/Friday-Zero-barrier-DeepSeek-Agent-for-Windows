/* plan.js — 会话 Plan / Todo 面板 */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) return;

  const els = {
    panel: document.getElementById("planPanel"),
    toggle: document.getElementById("planPanelToggle"),
    body: document.getElementById("planPanelBody"),
    planInput: document.getElementById("planMarkdownInput"),
    todoList: document.getElementById("planTodoList"),
    saveBtn: document.getElementById("planSaveBtn"),
    addTodoBtn: document.getElementById("planAddTodoBtn"),
  };

  let todos = [];

  function renderTodos() {
    if (!els.todoList) return;
    els.todoList.innerHTML = "";
    todos.forEach((item, idx) => {
      const row = document.createElement("label");
      row.className = "plan-todo-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!item.done;
      cb.addEventListener("change", () => {
        todos[idx].done = cb.checked;
      });
      const input = document.createElement("input");
      input.type = "text";
      input.className = "plan-todo-text";
      input.value = item.text || "";
      input.addEventListener("input", () => {
        todos[idx].text = input.value;
      });
      row.append(cb, input);
      els.todoList.appendChild(row);
    });
  }

  async function loadPlan(sessionId) {
    if (!sessionId || !els.planInput) return;
    try {
      const res = await F.apiFetch(`/api/sessions/${sessionId}/plan`);
      if (!res.ok) return;
      const data = await res.json();
      els.planInput.value = data.plan_markdown || "";
      todos = Array.isArray(data.todos) ? data.todos.map((t) => ({ ...t })) : [];
      renderTodos();
    } catch (_err) {
      /* ignore */
    }
  }

  async function savePlan() {
    if (!F.activeSessionId) return;
    todos = todos.filter((t) => String(t.text || "").trim());
    const res = await F.apiFetch(`/api/sessions/${F.activeSessionId}/plan`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plan_markdown: els.planInput?.value || "",
        todos,
      }),
    });
    if (res.ok && els.body) {
      els.body.dataset.saved = "1";
      setTimeout(() => {
        if (els.body) delete els.body.dataset.saved;
      }, 1200);
    }
  }

  function togglePanel(force) {
    if (!els.panel || !els.body) return;
    const open = force != null ? force : els.panel.classList.contains("collapsed");
    els.panel.classList.toggle("collapsed", !open);
    if (els.toggle) els.toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (els.toggle) {
    els.toggle.addEventListener("click", () => togglePanel());
  }
  if (els.saveBtn) {
    els.saveBtn.addEventListener("click", () => void savePlan());
  }
  if (els.addTodoBtn) {
    els.addTodoBtn.addEventListener("click", () => {
      todos.push({ id: String(Date.now()), text: "", done: false });
      renderTodos();
    });
  }

  F.applySessionPlan = (data) => {
    if (els.planInput) els.planInput.value = data?.plan_markdown || "";
    todos = Array.isArray(data?.todos) ? data.todos.map((t) => ({ ...t })) : [];
    renderTodos();
  };
  F.loadSessionPlan = loadPlan;
  F.saveSessionPlan = savePlan;
})();
