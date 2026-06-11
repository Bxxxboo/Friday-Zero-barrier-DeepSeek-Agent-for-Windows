# 无障碍基线（M5.6）

对照 WCAG 2.1 AA 的轻量基线，覆盖设置页与全局交互。

## Token 与样式（`web/styles.css`）

| 项 | 实现 |
|----|------|
| 焦点环 | `--focus-ring`；`html.desktop button:focus-visible`、`.icon-btn`、`.settings-nav-item`、表单 `:focus-visible` |
| 触屏目标 | `--touch-target: 44px`；设置侧栏项、关闭按钮、保存/次要按钮 `min-height` |
| 对比度 | 侧栏分组标题仅用 `var(--muted)`，去掉额外 `opacity` 叠加以满足 ≥4.5:1 |
| 减少动效 | 全局 `@media (prefers-reduced-motion: reduce)` 已覆盖动画/过渡 |

## 设置模态（`web/settings.js` + `web/index.html`）

| 项 | 实现 |
|----|------|
| 语义 | `role="dialog"`、`aria-modal`、`aria-labelledby`；侧栏 `tablist` / `tab` / `tabpanel` |
| Tab 顺序 | 关闭 → 侧栏 Tab → 当前面板表单（`display:none` 面板不参与 Tab） |
| 键盘 | 侧栏 ↑↓←→ / Home / End 切换面板；Escape 关闭（`app.js`）；打开时焦点陷阱 |
| 保存 | 各面板 `type="submit"` 主按钮，Tab 可达 |

## 手工验收（3 条主流程）

1. **大模型保存**：打开设置 → Tab 到 API Key → 填写 → Tab 到「保存」→ Enter → 见成功提示。
2. **侧栏键盘**：焦点在侧栏时按 ↓ 切换面板，Enter/Space 可点当前项；Escape 关闭并回到「设置」按钮。
3. **减少动效**：系统开启「显示动画」关闭后，启动与状态点脉冲无长时间动画。

可选：`axe DevTools` 对设置模态跑一次，无 critical 即可。
