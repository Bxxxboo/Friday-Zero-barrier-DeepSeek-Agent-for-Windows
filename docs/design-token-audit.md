# DESIGN.md Token 审计 — M5.5

> 日期：2026-06-11  
> 范围：`web/styles.css`（不含 `web/vendor/`）  
> 对照：`DESIGN.md` §2–§5

## 结论

| 项 | 结果 |
|----|------|
| 核心色板（bg / accent / primary） | ✅ `:root` 与 DESIGN.md 一致 |
| 紫渐变 / Indigo slop | ✅ 已移除 `rgba(99,102,241)`（activity 步骤环） |
| 未定义 token 滥用 | ✅ 补全 `--text-secondary`、`--surface-2`、`--status-checking`、`--space-*` |
| 错误 fallback | ✅ 移除 `#22c55e`、`#c44`、`#d4a056` 作 primary 等误用 |
| 硬编码 hex（组件区） | ✅ 浅色 nav label `#6b6560` → `var(--muted)` |
| Inter / Roboto 栈 | ✅ 无引入 |
| 三列 feature grid | ✅ 无新增 |

## 本轮修复清单

| 位置 | 问题 | 修复 |
|------|------|------|
| `.activity-steps li.current::before` | Indigo 光晕 `rgb(99,102,241)` | `var(--accent-soft)` |
| `.activity-steps li.done::before` | Tailwind 绿 `#22c55e` fallback | `var(--cat-daily)` |
| `.ghost-btn.danger-text` | 缩写色 `#c44` fallback | `var(--danger)` |
| `.weixin-setup-log-item--action::before` | primary fallback 写成金色 | `var(--accent)` |
| `.session-list-empty*` | 未定义 token + 硬编码 fallback | 正式 token |
| `.log-preview` | `border-radius: 8px`、surface fallback | `var(--radius-sm)`、`var(--surface-2)` |
| `html[data-theme="light"] .settings-nav-label` | `#6b6560` | `var(--muted)` |
| `.status-dot[data-state="checking"]` | 孤立 `#c9a227` | `var(--status-checking)` |
| M5.3/M5.4 新增块 | `--surface-2` / `--text-secondary` 无定义 | 写入 `:root` + light 覆盖 |

## 保留（合理）

- `:root` / `html[data-theme="light"]` 内的 hex 定义 — token 源
- `rgba(0,0,0,*)` 浅色主题 hover — 语义透明层，未抽 token
- `--user-msg-bg` primary 渐变 — DESIGN.md §6 允许
- `web/vendor/*` — 第三方，不审计

## 后续（非 M5.5 阻塞）

- 将零散 `padding: 10px 12px` 逐步改为 `var(--space-*)`（全文件约 200+ 处，单独 PR）
- M5.6：`prefers-reduced-motion`、触屏 44px、Tab 顺序

## 验证

```powershell
# 无紫 slop
rg "99,\s*102,\s*241|8b5cf6|6366f1" web/styles.css
# 应无匹配

# 无组件区裸 hex（除 :root 块）
rg "#[0-9a-fA-F]{3,8}" web/styles.css
# 仅 :root / light 覆盖行
```
