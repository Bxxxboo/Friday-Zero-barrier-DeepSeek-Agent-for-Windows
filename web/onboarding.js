/* ================================================================= *
 *  onboarding.js — 首次启动向导（欢迎 → API Key → 文件夹 → 完成）
 *  依赖 utils.js + settings.js
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) { console.error("onboarding.js: window.Friday 未初始化"); return; }

  const ONBOARDING_KEY = "friday_onboarding_done";
  let currentStep = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function showStep(step) {
    currentStep = step;
    document.querySelectorAll(".onboarding-step").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.step) === step);
    });
    document.querySelectorAll(".onboarding-dot").forEach((dot) => {
      dot.classList.toggle("active", Number(dot.dataset.step) <= step);
    });
  }

  function openOnboarding(step = 0) {
    showStep(step);
    F.onboardingModal?.classList.remove("hidden");
  }

  function closeOnboarding() {
    F.onboardingModal?.classList.add("hidden");
  }

  async function loadSuggestedFolder() {
    try {
      const res = await F.apiFetch("/api/folders");
      const data = await res.json();
      const input = $("onboardingWorkspace");
      if (input && data.suggested_workspace) {
        input.value = data.suggested_workspace;
      }
    } catch {
      // 忽略，用户可手动输入
    }
  }

  async function pickOnboardingFolder() {
    const input = $("onboardingWorkspace");
    const result = $("onboardingFolderResult");
    if (!input || !result) return;

    result.className = "settings-result";
    result.textContent = "";

    if (!window.pywebview?.api?.pick_folder) {
      result.className = "settings-result error";
      result.textContent =
        "请直接在输入框填写路径，例如 D:/Documents/星期五（文件夹选择需使用桌面客户端）。";
      return;
    }

    try {
      result.className = "settings-result";
      result.textContent = "正在打开文件夹选择…";
      const path = await window.pywebview.api.pick_folder(input.value.trim());
      if (path) {
        input.value = path;
        result.className = "settings-result ok";
        result.textContent = "已选择文件夹。";
      } else {
        result.className = "settings-result";
        result.textContent =
          "未选择文件夹。请手动输入路径，例如 D:/Documents/星期五。";
      }
    } catch {
      result.className = "settings-result error";
      result.textContent = "打开文件夹选择器失败，请手动输入路径。";
    }
  }

  async function testOnboardingApi() {
    const result = $("onboardingApiResult");
    const key = $("onboardingApiKey")?.value.trim() || "";
    if (!key) {
      result.className = "settings-result error";
      result.textContent = "请先填写 API Key。";
      return false;
    }

    result.className = "settings-result";
    result.textContent = "测试连接中...";

    try {
      const res = await F.apiFetchWithTimeout(
        "/api/settings/test",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: key }),
        },
        60000
      );
      let data = {};
      try {
        data = await res.json();
      } catch {
        result.className = "settings-result error";
        result.textContent = `服务响应异常 (${res.status})，请重启应用后重试。`;
        return false;
      }
      if (!res.ok) {
        const detail = data.detail || data.message || `HTTP ${res.status}`;
        result.className = "settings-result error";
        result.textContent =
          res.status === 401
            ? "本地认证失败，请完全关闭后重新打开应用。"
            : String(detail);
        return false;
      }
      result.className = data.ok ? "settings-result ok" : "settings-result error";
      result.textContent = data.message || (data.ok ? "连接成功" : "连接失败");
      return !!data.ok;
    } catch (err) {
      result.className = "settings-result error";
      if (err?.name === "AbortError") {
        result.textContent = "测试超时（60 秒）。请检查网络或 API Key 是否正确。";
      } else {
        result.textContent =
          "无法连接本地服务。请确认应用未被杀毒软件拦截，并查看 %APPDATA%\\Friday\\friday.log。";
      }
      return false;
    }
  }

  async function saveOnboardingApi() {
    const key = $("onboardingApiKey")?.value.trim() || "";
    if (!key) return false;

    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    if (!res.ok) return false;

    const data = await res.json();
    F.apiReady = data.api_ready;
    F.updateApiStatus(data.api_ready);
    document.getElementById("apiKeyHint").textContent = `当前已保存: ${data.api_key_masked}`;
    F.updateInputState();
    return data.api_ready;
  }

  async function saveOnboardingFolder() {
    const workspace = $("onboardingWorkspace")?.value.trim() || "";
    if (!workspace) return false;

    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace }),
    });
    if (!res.ok) return false;

    const data = await res.json();
    document.getElementById("workspace").value = data.workspace;
    return true;
  }

  async function finishOnboarding() {
    localStorage.setItem(ONBOARDING_KEY, "1");
    closeOnboarding();
    F.updateInputState();
  }

  async function checkOnboarding() {
    await F.loadSettings();
    if (F.apiReady) {
      if (!localStorage.getItem(ONBOARDING_KEY)) {
        localStorage.setItem(ONBOARDING_KEY, "1");
      }
      return;
    }
    openOnboarding(0);
  }

  function bindEvents() {
    $("onboardingStartBtn")?.addEventListener("click", () => showStep(1));
    $("onboardingTestBtn")?.addEventListener("click", testOnboardingApi);

    $("onboardingApiNextBtn")?.addEventListener("click", async () => {
      const result = $("onboardingApiResult");
      const ok = await testOnboardingApi();
      if (!ok) return;
      const saved = await saveOnboardingApi();
      if (!saved) {
        result.className = "settings-result error";
        result.textContent = "保存失败，请重试。";
        return;
      }
      await loadSuggestedFolder();
      showStep(2);
    });

    $("onboardingPickFolderBtn")?.addEventListener("click", pickOnboardingFolder);

    $("onboardingFolderNextBtn")?.addEventListener("click", async () => {
      const result = $("onboardingFolderResult");
      const workspace = $("onboardingWorkspace")?.value.trim() || "";
      if (!workspace) {
        result.className = "settings-result error";
        result.textContent = "请选择或输入一个文件夹。";
        return;
      }
      result.className = "settings-result";
      result.textContent = "保存中...";
      const saved = await saveOnboardingFolder();
      if (!saved) {
        result.className = "settings-result error";
        result.textContent = "保存失败，请重试。";
        return;
      }
      showStep(3);
    });

    $("onboardingFinishBtn")?.addEventListener("click", finishOnboarding);

    $("onboardingBackBtn1")?.addEventListener("click", () => showStep(0));
    $("onboardingBackBtn2")?.addEventListener("click", () => showStep(1));
  }

  F.openOnboarding = openOnboarding;
  F.checkOnboarding = checkOnboarding;
  bindEvents();
})();
