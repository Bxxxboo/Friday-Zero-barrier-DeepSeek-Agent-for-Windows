# 星期五 (Friday) — Product Context

## Register

**product** — 桌面 AI 电脑管家应用（Win10/11），非营销落地页。设计服务于效率、信任与长期使用的工具型 UI。

## Target users

- 中国 Windows 用户，希望用自然语言管理文件、系统、文档
- 技术程度：普通用户为主，部分进阶用户（Python、微信桥接）
- 使用场景：每日打开的对话客户端 + 设置面板，非一次性网页

## Product purpose

本地 FastAPI 后端 + WebView2 壳（`web/` 静态 UI）。核心：对话、工具执行、设置、历史、微信端 AI 向导。

## Brand personality

- 温暖、可靠、略复古的「管家」气质（金琥珀 accent + 深蓝 primary）
- 中文优先，Segoe UI / 微软雅黑
- 深色默认，浅色可选；桌面无边框窗口

## Anti-references

- 紫渐变 SaaS 模板、Inter 默认栈、三列等宽卡片英雄区
- 过度动效、玻璃拟态泛滥、emoji 当图标
- 与现有 `web/styles.css` token 体系冲突的新配色

## Strategic design principles

1. **Token 优先**：改 UI 必须复用 `:root` / `html[data-theme]` CSS 变量，不硬编码色值
2. **桌面优先**：WebView2 内嵌；注意 `-webkit-app-region`、输入框 focus、无拖拽区域
3. **信息密度适中**：侧边栏 + 主聊天 + 设置模态；设置页分 section，不堆卡片
4. **可访问性**：对比度、键盘、焦点环；`prefers-reduced-motion` 尊重
5. **渐进增强**：动效用 CSS transition；复杂动效参考 `micro-interactions` / `motion-dev-animations` skill

## Key surfaces

| 路径 | 说明 |
|------|------|
| `web/index.html` | 主壳：侧栏、聊天、设置入口 |
| `web/styles.css` | 设计 token 与组件样式（单一事实来源） |
| `web/*.js` | 模块化前端逻辑 |
| `web/settings.js` / `onboarding.js` / `weixin.js` | 设置、向导、微信配置 |

## Tech stack (frontend)

Vanilla HTML/CSS/JS，无 React。静态资源由 FastAPI 挂载。版本 query `?v=` 用于缓存 bust。
