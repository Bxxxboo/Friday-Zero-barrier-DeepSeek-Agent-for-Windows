# DESIGN.md — 星期五 (Friday)

> 遵循 [Google Stitch DESIGN.md](https://stitch.withgoogle.com/docs/design-md/format/) 格式。  
> AI 修改 `web/` 时必须以本文 + `web/styles.css` 为准，保持视觉一致。

---

## 1. Visual Theme & Atmosphere

**Mood:** 温暖可靠的桌面 AI 管家；深色默认，浅色为纸感暖白。  
**Density:** 中等 — 侧边栏紧凑，聊天区留白充足，设置表单清晰分组。  
**Philosophy:** 工具型产品 UI；accent 金琥珀传达「星期五」品牌，primary 蓝用于行动与链接。避免 generic AI slop（紫渐变、Inter、三列卡片英雄）。

---

## 2. Color Palette & Roles

### Dark (`html[data-theme="dark"]` 或默认)

| Token | Hex / value | Role |
|-------|-------------|------|
| `--bg` | `#0a0d12` | 应用背景 |
| `--bg-elevated` | `#111620` | 抬升表面 |
| `--sidebar-bg` | `rgba(12,16,24,0.94)` | 侧栏 |
| `--panel` | `rgba(20,26,40,0.78)` | 面板/卡片 |
| `--panel-solid` | `#161c2c` | 实心面板 |
| `--text` | `#e8eaef` | 正文 |
| `--muted` | `#8b95a8` | 次要文字（须满足对比度） |
| `--accent` | `#d4a056` | 品牌金、强调、logo 渐变 |
| `--primary` | `#5b8fd9` | 主按钮、链接、用户消息 |
| `--primary-2` | `#4070b8` | primary 深色态 |
| `--border` | `rgba(212,160,86,0.14)` |  accent 调边框 |
| `--border-subtle` | `rgba(255,255,255,0.07)` | 分隔线 |
| `--code-bg` | `#0c1018` | 代码块 |
| `--text-secondary` | `#c5cdd8` | 次级标题（空状态标题等） |
| `--text-muted` | `#8b95a8` | 辅助说明（`--muted` 别名） |
| `--surface-2` | `var(--panel-2)` | 嵌套面板 / 空状态底 |
| `--status-checking` | `var(--warn)` | 状态栏检测中 |
| `--space-1`…`--space-8` | 4–32px | 间距刻度（4px 基准） |

### Light (`html[data-theme="light"]`)

| Token | Hex | Role |
|-------|-----|------|
| `--bg` | `#f0ebe3` | 暖纸色背景 |
| `--text` | `#1a1f2e` | 正文 |
| `--accent` | `#b8862e` | 品牌金（略深） |
| `--primary` | `#3d6db5` | 主色 |
| `--text-secondary` | `#4a5366` | 次级标题 |
| `--text-muted` | `#5c6578` | 辅助说明 |

### Category accents（工具/标签）

- `--cat-system`: `#56b4d4`
- `--cat-files`: `#d4a056`
- `--cat-docs`: `#c9786a`
- `--cat-daily`: `#7cb87a`

**Do:** 新组件只用 CSS 变量。  
**Don't:** 引入紫色渐变主色、灰色正文放在彩色底上、硬编码 `#fff` 文字。

---

## 3. Typography

| Role | Stack | Notes |
|------|-------|------|
| Display / 标题 | `--font-display`: Segoe UI, Microsoft YaHei UI, Noto Serif SC | 品牌标题、侧栏 logo |
| Body | `--font-body`: Segoe UI, Microsoft YaHei UI, Microsoft YaHei | 正文、按钮、表单 |
| Scale | `--font-scale`: 0.92 / 1 / 1.12（small/medium/large） | 根 `font-size: calc(16px * var(--font-scale))` |

| Element | Size / weight |
|---------|----------------|
| 页面标题 | 1.25–1.5rem, semibold |
| 设置 section 标题 | 1rem–1.125rem |
| 正文 | 1rem (scaled) |
| 辅助说明 | 0.875rem, `--muted` |
| 按钮 | 0.9375rem, medium |

---

## 4. Component Stylings

### Buttons

- **Primary** (`.primary-btn`): `--primary` 背景，白字，hover 略深，`border-radius: var(--radius-md)`
- **Ghost** (`.ghost-btn`): 透明/浅底，边框 `--border-subtle`，hover 背景 `--accent-soft`
- **Danger**: 仅破坏性操作用红系，与 primary 区分

### Inputs

- 背景 `--panel-solid` 或 `--panel-2`，边框 `--border-subtle`
- Focus: 边框/环 `--primary`，桌面 WebView2 须 `-webkit-app-region: no-drag`
- 设置页、 onboarding、模态内输入框必须可聚焦

### Cards / Panels

- `border-radius: var(--radius-lg)` (16px) 或 `--radius-md` (12px)
- 阴影 `--shadow`；避免多层嵌套卡片

### Sidebar & chrome

- 桌面无边框：`html.desktop` 自定义标题栏
- Logo：金琥珀渐变圆角块 + 「星期五」display 字体

### Modals

- `.modal` / `.onboarding-window` / `.settings-window`：居中，backdrop 半透明
- 桌面模式所有交互区 `no-drag`

### Status badges

- ok / warn / error 用语义色 + 小圆角 pill，与 `--cat-*` 一致时复用 category 色

---

## 5. Layout Principles

- **Spacing scale:** 4px 基准 — 8, 12, 16, 20, 24, 32px
- **App shell:** 侧栏固定宽 + 主区 flex；`--app-height: 100dvh`（桌面 `100%`）
- **Settings:** 左侧 nav + 右侧 content；section 间 24–32px
- **Whitespace:** 聊天区消息间距 12–16px；表单 field 间距 16px

---

## 6. Depth & Elevation

- 侧栏/标题栏：轻微 blur + `--sidebar-bg`
- 浮层：`--shadow`；不用过重多层 shadow
- 用户消息：`--user-msg-bg` 渐变；助手消息 `--panel` 或透明

---

## 7. Do's and Don'ts

**Do**

- 双主题同步测试 dark + light
- 图标用 SVG 或 better-icons skill 检索 Iconify
- 动效：`transition` 150–250ms；尊重 `prefers-reduced-motion`
- 中文文案简短、口语化

**Don't**

- Inter / Roboto / 系统默认无个性栈作为「升级」
- 三列等宽 feature grid 当默认布局
- 在 `web/` 引入 React/Vue 除非用户明确要求重构
- 破坏现有 JS 模块边界（`window.Friday` 命名空间）

---

## 8. Responsive Behavior

- 主目标：桌面 820–1200px 宽窗口
- 小宽：侧栏可折叠逻辑若已存在则保持，不新增复杂断点
- Touch：非主要场景；按钮 min-height 36px+

---

## 9. Agent Prompt Guide

**Quick tokens:** bg `#0a0d12`, accent `#d4a056`, primary `#5b8fd9`, radius 12/16px

**Example prompts:**

- 「在设置页增加 XX 区块，遵循 DESIGN.md，复用 ghost-btn / settings-section 样式」
- 「优化 onboarding 第三步布局，保持暖色深色主题一致」
- 「给微信向导步骤列表加 subtle 动效，用 CSS only」

**Skills to invoke:**

| 任务 | Skill |
|------|--------|
| 整体审计/抛光 | `/impeccable` → audit, polish, normalize |
| 反 AI 模板审美 | `/design-taste-frontend` |
| 组件结构 | `/ui-design-brain` |
| 微交互/动效 | `/micro-interactions` 或 `/motion-dev-animations` |
| 图标 | `/better-icons` + MCP |

**Files to read first:** `DESIGN.md`, `web/styles.css`, `PRODUCT.md`
