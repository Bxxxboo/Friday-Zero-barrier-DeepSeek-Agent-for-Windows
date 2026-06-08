/* ================================================================= *
 *  i18n.js — 界面语言（zh / en），默认简体中文
 * ================================================================= */

(function () {
  "use strict";

  const STRINGS = {
    zh: {
      "app.name": "星期五",
      "app.icon": "五",
      "app.title": "星期五",
      "boot.loading": "正在加载界面…",
      "boot.timeout": "加载超时，请完全关闭后重新打开",
      "win.minimize": "最小化",
      "win.maximize": "最大化",
      "win.close": "关闭",
      "chat.new": "新对话",
      "chat.title.default": "新对话",
      "chat.rename.title": "重命名对话",
      "chat.rename.action": "重命名",
      "chat.delete.action": "删除",
      "common.cancel": "取消",
      "common.confirm": "确定",
      "history.title": "操作历史",
      "settings.title": "设置",
      "welcome.kicker": "AI 电脑管家",
      "welcome.hello": "你好，我是",
      "welcome.sub": "整理文件、查看系统、生成文档——说一句话，我来动手。",
      "mode.ask": "Ask",
      "mode.agent": "Agent",
      "mode.yolo": "Yolo",
      "mode.ask.title": "只读问答",
      "mode.agent.title": "确认后执行",
      "mode.yolo.title": "工作区自动执行",
      "mode.hint.ask": "仅查阅与分析，不会修改文件",
      "mode.hint.agent": "修改与执行前需你确认",
      "mode.hint.yolo": "已授权：工作区内自动执行，不再反复确认",
      "mode.hint.yolo_pending": "请先完成开启确认，否则与 Agent 相同",
      "composer.placeholder": "说说想让我帮你做什么… 可 Ctrl+V 粘贴截图 · 输入 / 选技能",
      "composer.attachment": "已附加截图",
      "composer.removeAttachment": "移除截图",
      "composer.send": "发送",
      "composer.stop": "停止生成",
      "composer.queue.one": "1 条指令待执行",
      "composer.queue.many": "{n} 条指令待执行",
      "composer.queue.badge": "排队中",
      "composer.queue.running": "执行中…",
      "message.copy": "复制",
      "message.copied": "已复制",
      "message.copyFailed": "复制失败",
      "message.quote": "引用",
      "message.quoteLabel": "引用星期五",
      "message.clearQuote": "移除引用",
      "status.api.online": "API 在线",
      "status.api.offline": "API 离线",
      "status.vision.on": "视觉 在线",
      "status.vision.off": "视觉 离线",
      "status.vision.disabled": "视觉 关",
      "status.imageGen.on": "生图 在线",
      "status.imageGen.off": "生图 离线",
      "status.imageGen.disabled": "生图 关",
      "status.tokens": "tokens",
      "status.cache": "缓存",
      "status.tasks": "定时",
      "status.services": "服务连接状态",
      "status.tokenUsage": "当前会话 Token 用量",
      "status.taskCount": "定时任务数量",
      "status.workspace": "默认操作文件夹",
      "status.model": "当前模型",
      "settings.nav.api": "API 连接",
      "settings.nav.workspace": "文件夹",
      "settings.nav.appearance": "外观",
      "settings.nav.logs": "数据移植与日志",
      "settings.nav.security": "安全与更新",
      "settings.nav.extensions": "扩展",
      "settings.nav.schedules": "定时任务",
      "appearance.title": "外观",
      "appearance.desc": "界面语言、主题与字号，保存后立即生效。",
      "appearance.language": "界面语言",
      "appearance.theme": "主题",
      "appearance.fontSize": "字体大小",
      "lang.zh": "简体中文",
      "lang.en": "English",
      "theme.dark": "深色（夜间）",
      "theme.light": "浅色（日间）",
      "theme.system": "跟随系统",
      "font.small": "小",
      "font.medium": "标准",
      "font.large": "大",
      "mode.default.ask": "Ask · 只读问答",
      "mode.default.agent": "Agent · 确认后执行",
      "mode.default.yolo": "Yolo · 确认一次后自动",
      "btn.save": "保存",
      "appearance.saved": "外观设置已保存。",
      "appearance.saving": "保存中...",
      "logs.title": "数据移植与日志",
      "logs.desc": "导出/导入配置包，并查看运行日志与诊断信息。",
      "logs.openFolder": "打开日志文件夹",
      "logs.refresh": "刷新日志摘要",
      "logs.empty": "（暂无日志）",
      "logs.opened": "已打开日志文件夹。",
      "updates.title": "安全与更新",
      "updates.desc": "检查版本更新，并限制 AI 访问与修改文件的范围与方式。",
      "updates.version": "版本与更新",
      "updates.check": "检查更新",
      "updates.download": "下载新版本",
      "updates.checking": "正在检查…",
      "updates.latest": "已是最新版本 {version}",
      "updates.found": "发现新版本 {latest}（当前 {current}）",
      "updates.fail": "检查更新失败",
      "autostart.title": "启动",
      "autostart.label": "登录 Windows 时自动启动星期五",
      "autostart.enabled": "已开启开机自启",
      "autostart.disabled": "已关闭开机自启",
      "autostart.failed": "配置失败，请重试",
      "updates.sourceHint": "（国内免 VPN；GitHub 作备用）",
      "yolo.title": "开启 Yolo 模式",
      "yolo.cancel": "取消",
      "yolo.confirm": "确认开启",
    },
    en: {
      "app.name": "Friday",
      "app.icon": "F",
      "app.title": "Friday",
      "boot.loading": "Loading interface…",
      "boot.timeout": "Load timed out. Please close and reopen the app.",
      "win.minimize": "Minimize",
      "win.maximize": "Maximize",
      "win.close": "Close",
      "chat.new": "New chat",
      "chat.title.default": "New chat",
      "chat.rename.title": "Rename chat",
      "chat.rename.action": "Rename",
      "chat.delete.action": "Delete",
      "common.cancel": "Cancel",
      "common.confirm": "Confirm",
      "history.title": "Activity history",
      "settings.title": "Settings",
      "welcome.kicker": "AI desktop assistant",
      "welcome.hello": "Hi, I'm ",
      "welcome.sub": "Organize files, check your system, create documents—just tell me what you need.",
      "mode.ask": "Ask",
      "mode.agent": "Agent",
      "mode.yolo": "Yolo",
      "mode.ask.title": "Read-only Q&A",
      "mode.agent.title": "Confirm before actions",
      "mode.yolo.title": "Auto-run in workspace",
      "mode.hint.ask": "Read and analyze only—no file changes",
      "mode.hint.agent": "Writes, runs, and downloads need your approval",
      "mode.hint.yolo": "Authorized: auto-run in workspace without repeated prompts",
      "mode.hint.yolo_pending": "Complete unlock confirmation first (same as Agent until then)",
      "composer.placeholder": "What should I help with… Ctrl+V to paste screenshots · type / for skills",
      "composer.attachment": "Screenshot attached",
      "composer.removeAttachment": "Remove screenshot",
      "composer.send": "Send",
      "composer.stop": "Stop generating",
      "composer.queue.one": "1 message queued",
      "composer.queue.many": "{n} messages queued",
      "composer.queue.badge": "Queued",
      "composer.queue.running": "Running…",
      "message.copy": "Copy",
      "message.copied": "Copied",
      "message.copyFailed": "Copy failed",
      "message.quote": "Quote",
      "message.quoteLabel": "Quoted reply",
      "message.clearQuote": "Remove quote",
      "status.api.online": "API online",
      "status.api.offline": "API offline",
      "status.vision.on": "Vision online",
      "status.vision.off": "Vision offline",
      "status.vision.disabled": "Vision off",
      "status.imageGen.on": "Image gen on",
      "status.imageGen.off": "Image gen off",
      "status.imageGen.disabled": "Image gen off",
      "status.tokens": "tokens",
      "status.cache": "cache",
      "status.tasks": "Schedules",
      "status.services": "Service connectivity",
      "status.tokenUsage": "Session token usage",
      "status.taskCount": "Scheduled tasks",
      "status.workspace": "Default workspace folder",
      "status.model": "Current model",
      "settings.nav.api": "API",
      "settings.nav.workspace": "Folders",
      "settings.nav.appearance": "Appearance",
      "settings.nav.logs": "Migration & Logs",
      "settings.nav.security": "Security & updates",
      "settings.nav.extensions": "Extensions",
      "settings.nav.schedules": "Schedules",
      "appearance.title": "Appearance",
      "appearance.desc": "Language, theme, and font size. Takes effect after save.",
      "appearance.language": "Language",
      "appearance.theme": "Theme",
      "appearance.fontSize": "Font size",
      "lang.zh": "简体中文",
      "lang.en": "English",
      "theme.dark": "Dark",
      "theme.light": "Light",
      "theme.system": "Follow system",
      "font.small": "Small",
      "font.medium": "Medium",
      "font.large": "Large",
      "mode.default.ask": "Ask · read-only",
      "mode.default.agent": "Agent · confirm actions",
      "mode.default.yolo": "Yolo · confirm once",
      "btn.save": "Save",
      "appearance.saved": "Appearance settings saved.",
      "appearance.saving": "Saving…",
      "logs.title": "Migration & Logs",
      "logs.desc": "Export/import config bundles and view runtime logs.",
      "logs.openFolder": "Open log folder",
      "logs.refresh": "Refresh log summary",
      "logs.empty": "(No logs yet)",
      "logs.opened": "Log folder opened.",
      "updates.title": "Security & updates",
      "updates.desc": "Check for updates and control what the AI can access or modify.",
      "updates.version": "Version & updates",
      "updates.check": "Check for updates",
      "updates.download": "Download new version",
      "updates.checking": "Checking…",
      "updates.latest": "You're on the latest version {version}",
      "updates.found": "Update {latest} available (current {current})",
      "updates.fail": "Update check failed",
      "autostart.title": "Startup",
      "autostart.label": "Launch Friday when I sign in to Windows",
      "autostart.enabled": "Autostart enabled",
      "autostart.disabled": "Autostart disabled",
      "autostart.failed": "Could not update autostart",
      "updates.sourceHint": "(Gitee first, no VPN; GitHub fallback)",
      "yolo.title": "Enable Yolo mode",
      "yolo.cancel": "Cancel",
      "yolo.confirm": "Confirm",
    },
  };

  let currentLang = "zh";

  function normalizeLang(value) {
    const v = String(value || "zh").trim().toLowerCase();
    return v === "en" ? "en" : "zh";
  }

  function readStoredLang() {
    try {
      const prefs = JSON.parse(localStorage.getItem("friday_ui_prefs") || "{}");
      if (prefs.ui_language) return normalizeLang(prefs.ui_language);
    } catch {
      /* ignore */
    }
    return "zh";
  }

  function t(key, params) {
    const table = STRINGS[currentLang] || STRINGS.zh;
    let text = table[key] ?? STRINGS.zh[key] ?? key;
    if (params && typeof params === "object") {
      Object.entries(params).forEach(([k, v]) => {
        text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      });
    }
    return text;
  }

  function applyLanguage(lang) {
    currentLang = normalizeLang(lang);
    const root = document.documentElement;
    root.lang = currentLang === "en" ? "en" : "zh-CN";
    root.dataset.uiLang = currentLang;

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (key) el.textContent = t(key);
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      if (key) el.placeholder = t(key);
    });

    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      if (key) {
        el.title = t(key);
        if (el.hasAttribute("aria-label")) el.setAttribute("aria-label", t(key));
      }
    });

    document.querySelectorAll("option[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (key) el.textContent = t(key);
    });

    document.title = t("app.title");

    try {
      const prefs = JSON.parse(localStorage.getItem("friday_ui_prefs") || "{}");
      prefs.ui_language = currentLang;
      localStorage.setItem("friday_ui_prefs", JSON.stringify(prefs));
    } catch {
      /* ignore */
    }

    window.dispatchEvent(new CustomEvent("friday:languagechange", { detail: { lang: currentLang } }));
  }

  function getLanguage() {
    return currentLang;
  }

  function setLanguage(lang) {
    applyLanguage(lang);
  }

  currentLang = readStoredLang();

  window.FridayI18n = {
    t,
    applyLanguage,
    getLanguage,
    setLanguage,
    normalizeLang,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => applyLanguage(currentLang));
  } else {
    applyLanguage(currentLang);
  }
})();
