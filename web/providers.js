/* ================================================================= *
 *  providers.js — 大模型 / 视觉 / 生图服务商预设 UI
 *  内置服务商 + 用户自定义条目合并显示在下拉列表
 * ================================================================= */

(function () {
  "use strict";

  const F = window.Friday;
  if (!F) return;

  const CUSTOM_PREFIX = "c:";
  const ADD_CUSTOM_VALUE = "__add_custom__";

  const KIND_META = {
    llm: {
      category: "llm",
      select: "llmProvider",
      nameWrap: "llmCustomNameWrap",
      nameInput: "llmCustomName",
      deleteBtn: "llmCustomDelete",
      endpointsKey: "llm_custom_endpoints",
      providerField: "llm_provider",
      switchFlag: "switch_llm_profile",
      hint: "llmProviderHint",
      profileHint: "llmProfileHint",
      keyHint: "apiKeyHint",
      keyMasked: "api_key_masked",
      defaultId: "deepseek",
    },
    vision: {
      category: "vision",
      select: "visionProvider",
      nameWrap: "visionCustomNameWrap",
      nameInput: "visionCustomName",
      deleteBtn: "visionCustomDelete",
      endpointsKey: "vision_custom_endpoints",
      providerField: "vision_provider",
      switchFlag: "switch_vision_profile",
      hint: "visionProviderHint",
      keyHint: "visionApiKeyHint",
      keyMasked: "vision_api_key_masked",
      defaultId: "ark",
    },
    image_gen: {
      category: "image_gen",
      select: "imageGenProvider",
      nameWrap: "imageGenCustomNameWrap",
      nameInput: "imageGenCustomName",
      deleteBtn: "imageGenCustomDelete",
      endpointsKey: "image_gen_custom_endpoints",
      providerField: "image_gen_provider",
      switchFlag: "switch_image_gen_profile",
      hint: "imageGenProviderHint",
      keyHint: "imageGenApiKeyHint",
      keyMasked: "image_gen_api_key_masked",
      defaultId: "openai_compat",
    },
  };

  let catalog = null;
  let settingsSnapshot = null;
  let lastProvider = { llm: null, vision: null, image_gen: null };
  let switching = false;

  function currentLang() {
    return window.FridayI18n?.getLanguage?.() || "zh";
  }

  function isZh() {
    return currentLang() !== "en";
  }

  function label(item) {
    if (!item) return "";
    return isZh() ? item.label_zh || item.label_en : item.label_en || item.label_zh;
  }

  function modelLabel(item) {
    if (!item) return "";
    return isZh() ? item.label_zh || item.id : item.label_en || item.label_zh || item.id;
  }

  function isCustomProviderId(id) {
    return String(id || "").startsWith(CUSTOM_PREFIX);
  }

  function endpointIdFromProvider(id) {
    return isCustomProviderId(id) ? id.slice(CUSTOM_PREFIX.length) : "";
  }

  function customEndpointsFromData(kind, data) {
    const key = KIND_META[kind]?.endpointsKey;
    return data?.[key] || [];
  }

  function customAsProviders(kind, data) {
    return customEndpointsFromData(kind, data).map((ep) => ({
      id: `${CUSTOM_PREFIX}${ep.id}`,
      label_zh: ep.name || ep.model || "未命名",
      label_en: ep.name || ep.model || "Unnamed",
      default_base_url: ep.base_url || "",
      key_placeholder: "sk-... / 任意 Key",
      model_kind: "text",
      user_custom: true,
    }));
  }

  function buildProviderList(kind, data) {
    const builtins = (catalog?.[kind] || []).filter((p) => p.id !== "custom");
    const customs = customAsProviders(kind, data);
    const addOpt = {
      id: ADD_CUSTOM_VALUE,
      label_zh: "＋ 添加自定义…",
      label_en: "+ Add custom…",
      model_kind: "action",
    };
    return [...builtins, ...customs, addOpt];
  }

  function findProvider(kind, id, data) {
    const list = buildProviderList(kind, data || settingsSnapshot || {});
    return list.find((p) => p.id === id) || list.find((p) => p.id === KIND_META[kind].defaultId) || list[0];
  }

  function fillProviderSelect(kind, data, selectedId) {
    const meta = KIND_META[kind];
    const select = document.getElementById(meta.select);
    if (!select) return;
    const providers = buildProviderList(kind, data);
    select.innerHTML = "";
    for (const p of providers) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = label(p);
      if (p.id === ADD_CUSTOM_VALUE) opt.dataset.action = "add";
      select.appendChild(opt);
    }
    const valid = providers.some((p) => p.id === selectedId);
    if (valid && selectedId !== ADD_CUSTOM_VALUE) select.value = selectedId;
    else if (selectedId && isCustomProviderId(selectedId)) select.value = selectedId;
  }

  function populateModelSelect(select, provider, currentModel) {
    if (!select) return;
    select.innerHTML = "";
    const models = provider?.models || [];
    const seen = new Set();
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = modelLabel(m);
      select.appendChild(opt);
      seen.add(m.id);
    }
    const model = (currentModel || "").trim();
    if (model && !seen.has(model)) {
      const opt = document.createElement("option");
      opt.value = model;
      opt.textContent = model;
      select.appendChild(opt);
    }
    if (model) select.value = model;
    else if (models.length) select.value = models[0].id;
  }

  function setHint(el, provider) {
    if (!el) return;
    const text = isZh() ? provider?.hint_zh : provider?.hint_en;
    el.textContent = text || "";
    el.classList.toggle("hidden", !text);
  }

  function setKeyLink(el, provider) {
    if (!el) return;
    const href = provider?.key_link || "";
    if (!href) {
      el.classList.add("hidden");
      return;
    }
    el.href = href;
    el.classList.remove("hidden");
  }

  function applyBaseUrl(input, url, force) {
    if (!input) return;
    if (!force && input.dataset.userEdited === "1") return;
    input.value = url || "";
  }

  function bindUserEdited(input) {
    if (!input || input.dataset.editBound === "1") return;
    input.dataset.editBound = "1";
    input.addEventListener("input", () => {
      input.dataset.userEdited = "1";
    });
  }

  function toggleModelFields(kind, provider) {
    const isCustom = isCustomProviderId(provider?.id) || provider?.user_custom;
    const modelKind = isCustom ? "text" : provider?.model_kind || "select";
    document.getElementById(`${kind}ModelSelectWrap`)?.classList.toggle("hidden", modelKind !== "select");
    document.getElementById(`${kind}ModelCustomWrap`)?.classList.toggle("hidden", modelKind !== "text");
    document.getElementById(`${kind}ModelEndpointWrap`)?.classList.toggle("hidden", modelKind !== "endpoint");
    if (kind === "image_gen") {
      const hasModels = !isCustom && Boolean(provider?.models?.length);
      document.getElementById("imageGenModelSelectWrap")?.classList.toggle("hidden", !hasModels);
      document.getElementById("imageGenModelTextWrap")?.classList.toggle("hidden", hasModels);
    }
    const meta = KIND_META[kind];
    document.getElementById(meta.nameWrap)?.classList.toggle("hidden", !isCustom);
    document.getElementById(meta.deleteBtn)?.classList.toggle("hidden", !isCustom);
  }

  function syncCustomName(kind, providerId, data) {
    const meta = KIND_META[kind];
    const nameInput = document.getElementById(meta.nameInput);
    if (!nameInput || !isCustomProviderId(providerId)) return;
    const eid = endpointIdFromProvider(providerId);
    const ep = customEndpointsFromData(kind, data).find((e) => e.id === eid);
    if (ep) nameInput.value = ep.name || "";
  }

  function readModelValue(kind, provider) {
    const isCustom = isCustomProviderId(provider?.id) || provider?.user_custom;
    const modelKind = isCustom ? "text" : provider?.model_kind || "select";
    if (modelKind === "text") {
      if (kind === "llm") return document.getElementById("llmModelCustom")?.value.trim() || "";
      if (kind === "vision") return document.getElementById("visionModelCustom")?.value.trim() || "";
      return document.getElementById("imageGenModel")?.value.trim() || "";
    }
    if (modelKind === "endpoint") {
      return document.getElementById(`${kind}ModelEndpoint`)?.value.trim() || "";
    }
    if (kind === "image_gen" && provider?.models?.length) {
      return document.getElementById("imageGenModelSelect")?.value.trim() || "";
    }
    return document.getElementById(`${kind}Model`)?.value.trim() || document.getElementById("model")?.value.trim() || "";
  }

  function updateLlmProfileHint(providerId, data) {
    const hint = document.getElementById("llmProfileHint");
    if (!hint) return;
    if (isCustomProviderId(providerId)) {
      hint.classList.add("hidden");
      return;
    }
    const profile = data?.llm_profiles_summary?.[providerId];
    if (profile?.configured) {
      hint.textContent = `已记忆 · Key: ${profile.api_key_masked}`;
      hint.classList.remove("hidden");
      return;
    }
    hint.textContent = isZh()
      ? "此服务商尚未保存配置，填写 Key 后点「保存」即可记忆"
      : "No saved profile yet — save after entering your API key";
    hint.classList.remove("hidden");
  }

  function applyLlmProvider(providerId, data, { forceUrl = false } = {}) {
    const provider = findProvider("llm", providerId, data);
    if (!provider) return;
    const isCustom = isCustomProviderId(providerId);
    const baseInput = document.getElementById("baseUrl");
    const keyInput = document.getElementById("apiKey");
    const profile = data?.llm_profiles_summary?.[providerId];
    const isActive = providerId === (data?.llm_provider || providerId);
    const model = (isActive ? data?.model : "") || profile?.model || "";
    const baseUrl = isCustom
      ? data?.base_url || provider.default_base_url || ""
      : (isActive ? data?.base_url : "") || profile?.base_url || provider.default_base_url || "";
    applyBaseUrl(baseInput, baseUrl, forceUrl || isCustom || Boolean(baseUrl));
    if (keyInput && provider.key_placeholder) keyInput.placeholder = provider.key_placeholder;
    populateModelSelect(document.getElementById("model"), provider, model);
    const custom = document.getElementById("llmModelCustom");
    if (custom && (provider.model_kind === "text" || isCustom)) custom.value = model;
    toggleModelFields("llm", { ...provider, id: providerId });
    setHint(document.getElementById("llmProviderHint"), isCustom ? null : provider);
    setKeyLink(document.getElementById("llmKeyLink"), isCustom ? null : provider);
    syncCustomName("llm", providerId, data);
    updateLlmProfileHint(providerId, data);
  }

  function resolveVisionModel(provider, savedModel) {
    const model = (savedModel || "").trim();
    const isCustom = isCustomProviderId(provider?.id) || provider?.user_custom;
    if (isCustom) return model;
    const modelKind = provider?.model_kind || "select";
    if (modelKind === "endpoint") {
      return model.startsWith("ep-") ? model : "";
    }
    const valid = new Set((provider?.models || []).map((m) => m.id));
    if (model && valid.has(model)) return model;
    if (model) return model;
    const first = provider?.models?.[0]?.id;
    return first || "";
  }

  function applyVisionProvider(providerId, data, { forceUrl = false } = {}) {
    const provider = findProvider("vision", providerId, data);
    if (!provider) return;
    const isCustom = isCustomProviderId(providerId);
    const isActive = providerId === (data?.vision_provider || providerId);
    const profile = data?.vision_profiles_summary?.[providerId];
    const baseUrl = isCustom
      ? data?.vision_base_url || ""
      : (isActive ? data?.vision_base_url : "") || profile?.base_url || provider.default_base_url || "";
    applyBaseUrl(document.getElementById("visionBaseUrl"), baseUrl, forceUrl || isCustom);
    const keyInput = document.getElementById("visionApiKey");
    if (keyInput && provider.key_placeholder) keyInput.placeholder = provider.key_placeholder;
    const model = resolveVisionModel(
      { ...provider, id: providerId },
      (isActive ? data?.vision_model : "") || profile?.model || "",
    );
    if (provider.model_kind === "select" && !isCustom) {
      populateModelSelect(document.getElementById("visionModel"), provider, model);
    } else if (provider.model_kind === "endpoint" && !isCustom) {
      const ep = document.getElementById("visionModelEndpoint");
      if (ep) ep.value = model;
    } else {
      const custom = document.getElementById("visionModelCustom");
      if (custom) custom.value = model;
    }
    toggleModelFields("vision", { ...provider, id: providerId });
    setHint(document.getElementById("visionProviderHint"), isCustom ? null : provider);
    setKeyLink(document.getElementById("visionKeyLink"), isCustom ? null : provider);
    syncCustomName("vision", providerId, data);
  }

  function resolveImageGenModel(provider, savedModel) {
    const model = (savedModel || "").trim();
    const isCustom = isCustomProviderId(provider?.id) || provider?.user_custom;
    if (isCustom) return model;
    if (provider?.models?.length) {
      const valid = new Set(provider.models.map((m) => m.id));
      if (model && valid.has(model)) return model;
      if (model) return model;
      return provider.models[0]?.id || "";
    }
    if (provider?.id === "ark") {
      return model.startsWith("ep-") ? model : "";
    }
    if (model.startsWith("ep-")) return "";
    if (["mimo-v2.5", "mimo-v2-omni", "mimo-v2.5-pro"].includes(model)) return "";
    return model;
  }

  function applyImageGenProvider(providerId, data, { forceUrl = false } = {}) {
    const provider = findProvider("image_gen", providerId, data);
    if (!provider) return;
    const isCustom = isCustomProviderId(providerId);
    const isActive = providerId === (data?.image_gen_provider || providerId);
    const profile = data?.image_gen_profiles_summary?.[providerId];
    const baseUrl = isCustom
      ? data?.image_gen_base_url || ""
      : (isActive ? data?.image_gen_base_url : "") || profile?.base_url || provider.default_base_url || "";
    applyBaseUrl(document.getElementById("imageGenBaseUrl"), baseUrl, forceUrl || isCustom);
    const fallbackInput = document.getElementById("imageGenFallbackUrls");
    if (fallbackInput && (forceUrl || isCustom || isActive)) {
      fallbackInput.value = (isActive ? data?.image_gen_fallback_urls : "") || profile?.fallback_urls || "";
    }
    const keyInput = document.getElementById("imageGenApiKey");
    if (keyInput && provider.key_placeholder) keyInput.placeholder = provider.key_placeholder;
    const model = resolveImageGenModel(
      provider,
      (isActive ? data?.image_gen_model : "") || profile?.model || "",
    );
    if (!isCustom && provider?.models?.length) {
      populateModelSelect(document.getElementById("imageGenModelSelect"), provider, model);
    } else {
      const custom = document.getElementById("imageGenModel");
      if (custom) custom.value = model;
    }
    toggleModelFields("image_gen", { ...provider, id: providerId });
    setHint(document.getElementById("imageGenProviderHint"), isCustom ? null : provider);
    setKeyLink(document.getElementById("imageGenKeyLink"), isCustom ? null : provider);
    syncCustomName("image_gen", providerId, data);
  }

  async function apiSettings(body) {
    const res = await F.apiFetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || String(res.status));
    return data;
  }

  async function promptCustomName(kind) {
    const defaultName = isZh() ? "我的自定义模型" : "My custom model";
    const name = window.prompt(
      isZh() ? "自定义模型名称（将显示在列表中）" : "Display name (shown in the list)",
      defaultName,
    );
    if (!name || !name.trim()) return null;
    return name.trim();
  }

  async function addCustomProvider(kind) {
    const meta = KIND_META[kind];
    const name = await promptCustomName(kind);
    if (!name) return null;
    const data = await apiSettings({
      custom_endpoint_category: meta.category,
      add_custom_endpoint: true,
      custom_endpoint_name: name,
    });
    settingsSnapshot = data;
    const newId = data[meta.providerField];
    fillProviderSelect(kind, data, newId);
    lastProvider[kind] = newId;
    if (kind === "llm") applyLlmProvider(newId, data, { forceUrl: true });
    else if (kind === "vision") applyVisionProvider(newId, data, { forceUrl: true });
    else applyImageGenProvider(newId, data, { forceUrl: true });
    if (kind === "llm") {
      syncVisionFieldsFromData(data);
      syncImageGenFieldsFromData(data);
    }
    return data;
  }

  async function deleteCustomProvider(kind) {
    const meta = KIND_META[kind];
    const select = document.getElementById(meta.select);
    const id = select?.value;
    if (!isCustomProviderId(id)) {
      const msg = isZh()
        ? "请先在列表中选中要删除的自定义模型，再点「删除」。"
        : "Select the custom model to delete, then click Delete.";
      window.alert(msg);
      return;
    }
    const confirmMsg = isZh() ? "确定删除这条自定义模型？" : "Delete this custom model?";
    if (!window.confirm(confirmMsg)) return;
    try {
      const data = await apiSettings({
        custom_endpoint_category: meta.category,
        delete_custom_endpoint: true,
        custom_endpoint_id: endpointIdFromProvider(id),
      });
      settingsSnapshot = data;
      const newId = data[meta.providerField];
      fillProviderSelect(kind, data, newId);
      lastProvider[kind] = newId;
      if (kind === "llm") {
        applyLlmProvider(newId, data, { forceUrl: true });
        syncVisionFieldsFromData(data);
        syncImageGenFieldsFromData(data);
      } else if (kind === "vision") {
        syncVisionFieldsFromData(data);
      } else applyImageGenProvider(newId, data, { forceUrl: true });
    } catch (err) {
      console.warn("deleteCustomProvider", err);
      window.alert(isZh() ? `删除失败：${err.message || err}` : `Delete failed: ${err.message || err}`);
    }
  }

  function listSavedLlmProviders(data) {
    if (!data) return [];
    const items = [];
    const seen = new Set();
    const builtins = catalog?.llm || [];

    const add = (providerId, displayName, model) => {
      if (!providerId || seen.has(providerId)) return;
      seen.add(providerId);
      const modelText = (model || "").trim() || "—";
      items.push({
        id: providerId,
        provider: displayName,
        model: modelText,
        label: `${displayName} · ${modelText}`,
      });
    };

    for (const [pid, profile] of Object.entries(data.llm_profiles_summary || {})) {
      if (!profile?.configured) continue;
      const preset = builtins.find((p) => p.id === pid);
      add(pid, preset ? label(preset) : pid, profile.model);
    }

    for (const ep of data.llm_custom_endpoints || []) {
      if (!ep?.configured) continue;
      const pid = ep.provider_id || `${CUSTOM_PREFIX}${ep.id}`;
      add(pid, ep.name || ep.model || (isZh() ? "自定义" : "Custom"), ep.model);
    }

    const active = data.llm_provider;
    if (active && !seen.has(active)) {
      const masked = data.api_key_masked || "";
      const hasKey = masked && masked !== "未设置" && masked !== "Not set";
      if (hasKey) {
        if (isCustomProviderId(active)) {
          const eid = endpointIdFromProvider(active);
          const ep = (data.llm_custom_endpoints || []).find((entry) => entry.id === eid);
          add(active, ep?.name || ep?.model || (isZh() ? "自定义" : "Custom"), data.model);
        } else {
          const preset = builtins.find((p) => p.id === active);
          add(active, preset ? label(preset) : active, data.model);
        }
      }
    }

    return items;
  }

  function setComposerModelTrigger(providerName, modelName, disabled) {
    const trigger = document.getElementById("composerModelTrigger");
    const providerEl = document.getElementById("composerModelProvider");
    const modelEl = document.getElementById("composerModelId");
    if (providerEl) providerEl.textContent = providerName || "—";
    if (modelEl) modelEl.textContent = modelName || "—";
    if (trigger) trigger.disabled = Boolean(disabled);
  }

  function closeComposerModelMenu() {
    const menu = document.getElementById("composerModelMenu");
    const trigger = document.getElementById("composerModelTrigger");
    menu?.classList.add("hidden");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function positionComposerModelMenu() {
    const menu = document.getElementById("composerModelMenu");
    const trigger = document.getElementById("composerModelTrigger");
    if (!menu || !trigger || menu.classList.contains("hidden")) return;
    const rect = trigger.getBoundingClientRect();
    menu.style.left = `${Math.max(8, rect.right - menu.offsetWidth)}px`;
    menu.style.top = `${rect.bottom + 6}px`;
    const overflow = rect.bottom + 6 + menu.offsetHeight - window.innerHeight + 8;
    if (overflow > 0) {
      menu.style.top = `${Math.max(8, rect.top - menu.offsetHeight - 6)}px`;
    }
  }

  function openComposerModelMenu() {
    const menu = document.getElementById("composerModelMenu");
    const trigger = document.getElementById("composerModelTrigger");
    const picker = document.getElementById("composerModelPicker");
    if (!menu || !trigger || trigger.disabled) return;
    if (menu.parentElement !== document.body) {
      document.body.appendChild(menu);
    }
    menu.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
    positionComposerModelMenu();
  }

  function refreshComposerModelSwitch(data) {
    const select = document.getElementById("composerModelSwitch");
    const menu = document.getElementById("composerModelMenu");
    if (!select || !menu) return;
    const snap = data || settingsSnapshot;
    const items = listSavedLlmProviders(snap);
    const active = snap?.llm_provider || "";
    const emptyLabel = F.t?.("composer.modelSwitch.empty") || (isZh() ? "请先在设置中配置大模型" : "Configure a model in Settings first");

    select.replaceChildren();
    menu.replaceChildren();

    if (!items.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = emptyLabel;
      select.appendChild(opt);
      const empty = document.createElement("p");
      empty.className = "composer-model-empty";
      empty.textContent = emptyLabel;
      menu.appendChild(empty);
      setComposerModelTrigger(emptyLabel, "", true);
      closeComposerModelMenu();
      return;
    }

    let activeItem = items[0];
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = item.label;
      select.appendChild(opt);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "composer-model-option";
      btn.role = "option";
      btn.dataset.providerId = item.id;
      btn.setAttribute("aria-selected", item.id === active ? "true" : "false");
      btn.innerHTML = `
        <span class="composer-model-option-copy">
          <span class="composer-model-option-provider"></span>
          <span class="composer-model-option-model"></span>
        </span>
        <svg class="composer-model-option-check" viewBox="0 0 16 16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" d="M3.5 8.2 6.4 11 12.5 5"/></svg>
      `;
      btn.querySelector(".composer-model-option-provider").textContent = item.provider;
      btn.querySelector(".composer-model-option-model").textContent = item.model;
      btn.addEventListener("click", () => {
        if (switching || item.id === lastProvider.llm) {
          closeComposerModelMenu();
          return;
        }
        void switchProvider("llm", item.id, { forceUrl: true }).finally(() => closeComposerModelMenu());
      });
      menu.appendChild(btn);

      if (item.id === active) activeItem = item;
    }

    select.disabled = false;
    select.value = activeItem.id;
    setComposerModelTrigger(activeItem.provider, activeItem.model, false);
    closeComposerModelMenu();
  }

  function syncImageGenFieldsFromData(data) {
    if (!data) return;
    fillProviderSelect("image_gen", data, data.image_gen_provider);
    lastProvider.image_gen = data.image_gen_provider || null;
    const imageGenEnabled = document.getElementById("imageGenEnabled");
    if (imageGenEnabled) imageGenEnabled.checked = !!data.image_gen_enabled;
    document.getElementById("imageGenApiKey").value = "";
    document.getElementById("imageGenBaseUrl").value = data.image_gen_base_url || "";
    const fallback = document.getElementById("imageGenFallbackUrls");
    if (fallback) fallback.value = data.image_gen_fallback_urls || "";
    const hint = document.getElementById("imageGenApiKeyHint");
    if (hint) {
      hint.textContent = data.image_gen_api_key_masked
        ? `当前已保存: ${data.image_gen_api_key_masked}`
        : "尚未保存 API Key";
    }
    applyImageGenProvider(data.image_gen_provider || "openai_compat", data, { forceUrl: true });
  }

  function syncVisionFieldsFromData(data) {
    if (!data) return;
    fillProviderSelect("vision", data, data.vision_provider);
    lastProvider.vision = data.vision_provider || null;
    const visionEnabled = document.getElementById("visionEnabled");
    if (visionEnabled) visionEnabled.checked = !!data.vision_enabled;
    document.getElementById("visionBaseUrl").value = data.vision_base_url || "";
    document.getElementById("visionApiKey").value = "";
    F.applyVisionKeyHint?.(data);
    F.updateVisionStatus?.(data.vision_ready, data.vision_enabled, data.vision_status_hint);
    applyVisionProvider(data.vision_provider || "ark", data, { forceUrl: true });
  }

  async function switchProvider(kind, id, { forceUrl = true } = {}) {
    const meta = KIND_META[kind];
    if (!id || id === ADD_CUSTOM_VALUE || switching) return;
    if (lastProvider[kind] && lastProvider[kind] !== id) {
      switching = true;
      try {
        const body = { [meta.providerField]: id, [meta.switchFlag]: true };
        const data = await apiSettings(body);
        settingsSnapshot = data;
        lastProvider[kind] = id;
        fillProviderSelect(kind, data, id);
        if (kind === "llm") {
          document.getElementById("baseUrl").value = data.base_url || "";
          document.getElementById("apiKey").value = "";
          document.getElementById("apiKeyHint").textContent = data.api_key_masked
            ? `当前已保存: ${data.api_key_masked}`
            : "尚未保存 API Key";
          applyLlmProvider(id, data, { forceUrl: true });
          F.apiReady = data.api_ready;
          F.updateApiStatus?.(data.api_ready);
          F.applyStatusFromSettings?.(data);
          F.patchStatusBar?.({ model: data.model, api_checking: true });
          void F.refreshStatusBar?.({ force: true });
          refreshComposerModelSwitch(data);
          syncVisionFieldsFromData(data);
        } else if (kind === "vision") {
          document.getElementById("visionApiKey").value = "";
          document.getElementById("visionBaseUrl").value = data.vision_base_url || "";
          F.applyVisionKeyHint?.(data);
          F.updateVisionStatus?.(data.vision_ready, data.vision_enabled, data.vision_status_hint);
          applyVisionProvider(id, data, { forceUrl: true });
        } else {
          document.getElementById("imageGenApiKey").value = "";
          document.getElementById("imageGenBaseUrl").value = data.image_gen_base_url || "";
          const fallback = document.getElementById("imageGenFallbackUrls");
          if (fallback) fallback.value = data.image_gen_fallback_urls || "";
          document.getElementById("imageGenApiKeyHint").textContent = data.image_gen_api_key_masked
            ? `当前已保存: ${data.image_gen_api_key_masked}`
            : "尚未保存 API Key";
          applyImageGenProvider(id, data, { forceUrl: true });
          F.onImageGenProviderChangeLegacy?.();
        }
      } catch (err) {
        console.warn("switchProvider", err);
        if (lastProvider[kind]) document.getElementById(meta.select).value = lastProvider[kind];
      } finally {
        switching = false;
      }
      return;
    }
    lastProvider[kind] = id;
    const snap = settingsSnapshot || {};
    if (kind === "llm") applyLlmProvider(id, snap, { forceUrl });
    else if (kind === "vision") applyVisionProvider(id, snap, { forceUrl });
    else applyImageGenProvider(id, snap, { forceUrl });
  }

  async function onProviderChange(kind, forceUrl = true) {
    const meta = KIND_META[kind];
    const id = document.getElementById(meta.select)?.value;
    if (id === ADD_CUSTOM_VALUE) {
      const prev = lastProvider[kind] || meta.defaultId;
      document.getElementById(meta.select).value = prev;
      await addCustomProvider(kind);
      return;
    }
    await switchProvider(kind, id, { forceUrl });
  }

  function collectCustomPayload(kind) {
    const meta = KIND_META[kind];
    const providerId = document.getElementById(meta.select)?.value || "";
    if (!isCustomProviderId(providerId)) return {};
    return {
      custom_endpoint_category: meta.category,
      custom_endpoint_id: endpointIdFromProvider(providerId),
      custom_endpoint_name: document.getElementById(meta.nameInput)?.value.trim() || "",
    };
  }

  function collectLlmModel() {
    return readModelValue("llm", findProvider("llm", document.getElementById("llmProvider")?.value, settingsSnapshot));
  }

  function collectVisionModel() {
    return readModelValue("vision", findProvider("vision", document.getElementById("visionProvider")?.value, settingsSnapshot));
  }

  function collectImageGenModel() {
    return readModelValue("image_gen", findProvider("image_gen", document.getElementById("imageGenProvider")?.value, settingsSnapshot));
  }

  async function loadCatalog() {
    if (catalog) return catalog;
    try {
      const res = await F.apiFetch("/api/model-providers");
      if (!res.ok) throw new Error(String(res.status));
      catalog = await res.json();
    } catch (err) {
      console.warn("loadCatalog", err);
      catalog = { llm: [], vision: [], image_gen: [] };
    }
    return catalog;
  }

  let composerModelBound = false;
  function bindComposerModelSwitch() {
    if (composerModelBound) return;
    const trigger = document.getElementById("composerModelTrigger");
    const picker = document.getElementById("composerModelPicker");
    if (!trigger || !picker) return;
    composerModelBound = true;

    trigger.addEventListener("click", () => {
      const menu = document.getElementById("composerModelMenu");
      if (!menu || trigger.disabled) return;
      if (menu.classList.contains("hidden")) openComposerModelMenu();
      else closeComposerModelMenu();
    });

    document.addEventListener("click", (event) => {
      const menu = document.getElementById("composerModelMenu");
      const target = event.target;
      if (picker.contains(target) || menu?.contains(target)) return;
      closeComposerModelMenu();
    });

    window.addEventListener("resize", closeComposerModelMenu);
    window.addEventListener("scroll", closeComposerModelMenu, true);
  }

  let bindingsReady = false;
  function bindControls() {
    if (bindingsReady) return;
    bindingsReady = true;
    bindComposerModelSwitch();
    document.getElementById("llmProvider")?.addEventListener("change", () => void onProviderChange("llm"));
    document.getElementById("visionProvider")?.addEventListener("change", () => void onProviderChange("vision"));
    document.getElementById("imageGenProvider")?.addEventListener("change", () => void onProviderChange("image_gen"));
    document.getElementById("llmCustomDelete")?.addEventListener("click", () => void deleteCustomProvider("llm"));
    document.getElementById("visionCustomDelete")?.addEventListener("click", () => void deleteCustomProvider("vision"));
    document.getElementById("imageGenCustomDelete")?.addEventListener("click", () => void deleteCustomProvider("image_gen"));
  }

  async function initProviders(data) {
    await loadCatalog();
    settingsSnapshot = data || null;
    lastProvider.llm = data?.llm_provider || null;
    lastProvider.vision = data?.vision_provider || null;
    lastProvider.image_gen = data?.image_gen_provider || null;
    fillProviderSelect("llm", data, data?.llm_provider);
    fillProviderSelect("vision", data, data?.vision_provider);
    fillProviderSelect("image_gen", data, data?.image_gen_provider);
    applyLlmProvider(data?.llm_provider || "deepseek", data, { forceUrl: false });
    applyVisionProvider(data?.vision_provider || "ark", data, { forceUrl: false });
    applyImageGenProvider(data?.image_gen_provider || "openai_compat", data, { forceUrl: false });
    bindUserEdited(document.getElementById("baseUrl"));
    bindUserEdited(document.getElementById("visionBaseUrl"));
    bindUserEdited(document.getElementById("imageGenBaseUrl"));
    bindControls();
    refreshComposerModelSwitch(data);
  }

  function refreshProviderLabels() {
    if (!catalog || !settingsSnapshot) return;
    for (const kind of ["llm", "vision", "image_gen"]) {
      const id = document.getElementById(KIND_META[kind].select)?.value;
      fillProviderSelect(kind, settingsSnapshot, id);
    }
    applyLlmProvider(document.getElementById("llmProvider")?.value, settingsSnapshot, { forceUrl: false });
    applyVisionProvider(document.getElementById("visionProvider")?.value, settingsSnapshot, { forceUrl: false });
    applyImageGenProvider(document.getElementById("imageGenProvider")?.value, settingsSnapshot, { forceUrl: false });
    refreshComposerModelSwitch(settingsSnapshot);
  }

  F.collectCustomPayload = collectCustomPayload;
  F.initProviders = initProviders;
  F.refreshProviderLabels = refreshProviderLabels;
  F.onLlmProviderChange = () => void onProviderChange("llm");
  F.onVisionProviderChange = () => void onProviderChange("vision");
  F.onImageGenProviderChange = () => void onProviderChange("image_gen");
  F.collectLlmModel = collectLlmModel;
  F.collectVisionModel = collectVisionModel;
  F.collectImageGenModel = collectImageGenModel;
  F.refreshComposerModelSwitch = refreshComposerModelSwitch;
})();
