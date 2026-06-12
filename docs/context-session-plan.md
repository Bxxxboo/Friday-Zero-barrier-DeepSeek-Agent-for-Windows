# 星期五 · 上下文与会话智能优化计划

> 生成：2026-06-11 · 审查：`/plan-ceo-review`（A 渐进增强 + SELECTIVE EXPANSION）  
> 参考：[MiMo Code](https://github.com/XiaomiMiMo/MiMo-Code) · [Sessions & Context](https://mimo.xiaomi.com/mimocode/sessions)  
> 长期计划编号：**M6.2**（子任务见 `long-term-plan.md`）  
> 详细设计主文档：本文件

---

## 1. 问题与目标

**用户体感：** 功能齐全，但长聊后「变笨」、忘路径、重复试探、跨天接不上。

**根因：** 运行时缺 MiMo 式**分层持久记忆 + 提前 checkpoint + rebuild 注入**；压缩触发太晚；主 Agent 兼管记忆。

**目标（可验收）：**

- 200+ 轮工具对话后，仍能答对当前任务、涉及路径、未完成项（抽检 ≥90%）
- 跨天恢复同会话无需用户重复背景
- 状态栏可见上下文健康度（token 占用 / 最近 checkpoint）
- 微信「我的微信」与桌面走同一套 context 管线

---

## 2. 已拍板决策

| 项 | 结论 |
|----|------|
| 实现路径 | **A 渐进增强**（三期做到 MiMo 核心 ~80%） |
| 审查模式 | **SELECTIVE EXPANSION** |
| E1 Goal 完成校验 | ✅ 纳入本期 |
| E2 会话 fork | ✅ 纳入本期 |
| E3 FTS 全文检索 | ✅ 纳入（跳过关键词 v1） |
| E4 Dream 定期蒸馏 | ✅ 纳入（默认关闭，设置 opt-in） |
| E5 Max 采样 | ⏸ **DEFER** → `TODOS.md`（未逐条确认，按推荐默认 defer） |

---

## 3. 架构总览

```text
用户入口 (Web / 微信 / WS)
        │
        ▼
   agent.py 主循环
        │
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
assembler  checkpoint_writer  sessions.py
(rebuild)  (20/45/70%)      + sidecar 文件
   │              │              │
   └──────┬───────┴──────────────┘
          ▼
   分层 prompt 注入 → brain.prepare_messages → LLM
```

**存储布局：**

```text
%APPDATA%/Friday/
  sessions/{id}.json
  sessions/{id}/checkpoint.md    # writer 独占写
  sessions/{id}/notes.md         # 主 Agent append-only
  memory/user_memory.json        # 全局偏好（已有）
  workspaces/{hash}/MEMORY.md    # 项目级记忆
  history.db                     # FTS5 全文索引
```

**单写者：** 仅 `checkpoint_writer` 写 `checkpoint.md` 与 `MEMORY.md`；主 Agent 只写 `notes.md`。

---

## 4. 大计划与子计划

四个 **Phase** 对应四个大计划；每个 Phase 拆 **子计划**（实现时可单独 PR / 发 patch）。

---

### 大计划 P0 — 可观测与压缩前移（v1.4.0）

**用户可感知：** 状态栏能看到「上下文 62%」；长聊更早稳住，少突然变糊。

| 子计划 | 编号 | 工作量 | 内容 | 涉及文件 | 验证 |
|--------|------|--------|------|----------|------|
| **P0.1 上下文仪表 API** | M6.2.1 | 0.5d | `context_tokens`、`budget_ratio`、`max_context` 写入 status-bar API | `friday/brain.py`, `friday/status_bar.py`, `friday/api/schemas.py` | pytest + `/api/status-bar` JSON 含新字段 |
| **P0.2 状态栏 UI** | M6.2.2 | 0.5d | 百分比/颜色徽章；hover 显示最近 compact 时间 | `web/statusbar.js`, `web/styles.css`, `web/i18n.js` | 手工：长聊后百分比上升 |
| **P0.3 压缩双触发** | M6.2.3 | 1d | 除 `CONTEXT_COMPACT_RATIO` 外，每 N 轮工具调用触发折叠；阈值可配置 | `friday/config.py`, `friday/brain.py`, `friday/agent.py` | `tests/` 模拟超限 → 出现 `COMPACT_SUMMARY_MARKER` |
| **P0.4 plan 注入优先** | M6.2.4 | 0.5d | rebuild/折叠时 plan+todos 块优先于旧摘要 | `friday/plan.py`, `friday/agent.py` | 有 plan 的长 fixture 折叠后 plan 仍在 prompt 前部 |
| **P0.5 回归矩阵** | M6.2.5 | 0.5d | 微信桌面同步、多会话 WS、问候路径 persist | `tests/weixin/`, `web/chat.js` | 现有 weixin + session 测试全绿 |

**Phase 0 发版建议：** patch **v1.4.0**，可独立于 P1。

---

### 大计划 P1 — Checkpoint Writer（v1.4.x）

**用户可感知：** 会话详情可展开「工作记忆」；长任务中途不易丢关键路径。

| 子计划 | 编号 | 工作量 | 内容 | 涉及文件 | 验证 |
|--------|------|--------|------|----------|------|
| **P1.1 writer 模块骨架** | M6.2.6 | 1d | 异步任务队列；与主循环并发；文件锁 | 新建 `friday/checkpoint_writer.py` | 并发写不损坏 checkpoint |
| **P1.2 checkpoint  schema** | M6.2.7 | 0.5d | 11 字段中文版 markdown 模板 + metadata JSON | `friday/checkpoint_writer.py`, `friday/config.py` | 样例 checkpoint 可解析 |
| **P1.3 触发 20/45/70%** | M6.2.8 | 1d | token 比例触发 + 增量更新（非一次性摘要） | `friday/brain.py`, `friday/agent.py`, `checkpoint_writer.py` | 3 次触发 → version 递增 |
| **P1.4 LLM 摘要 + fallback** | M6.2.9 | 0.5d | API 失败 → `deterministic_summary` | `friday/brain.py`, `prefix_cache.py` | mock API 失败仍写出 checkpoint |
| **P1.5 notes.md 通道** | M6.2.10 | 0.5d | 主 Agent append；writer 归档进结构化字段后清空 | `friday/tools/` 或 agent 钩子, `sessions.py` | notes 写入 → 下次 checkpoint 吸收 |
| **P1.6 UI 工作记忆面板** | M6.2.11 | 1d | 只读展示 checkpoint.md；loading/empty/error | `web/chat.js` 或侧栏, `server.py` GET API, `styles.css` | 无 checkpoint 时空状态 |
| **P1.7 单元测试** | M6.2.12 | 1d | writer 增量、锁、失败降级 | `tests/brain/test_checkpoint_writer.py` | pytest -q 新增全过 |

**Phase 1 发版建议：** minor **v1.4.1～1.4.2**（与 P0 间隔不超过 2 周）。

---

### 大计划 P2 — Rebuild 注入 + Goal + Fork（v1.5.0）

**用户可感知：** 超长对话「无缝续聊」；复杂任务少「以为做完了」；可从当前状态分叉新会话。

| 子计划 | 编号 | 工作量 | 内容 | 涉及文件 | 验证 |
|--------|------|--------|------|----------|------|
| **P2.1 context_assembler** | M6.2.13 | 1.5d | 分层预算：plan → checkpoint → 近期用户原文 → MEMORY → user_memory → tail | 新建 `friday/context_assembler.py` | 各层 cap 单元测试 |
| **P2.2 rebuild 管线** | M6.2.14 | 1.5d | 85% 触发 rebuild；cut 旧 agent_messages；注入 assembler 输出 | `friday/brain.py`, `context_assembler.py`, `agent.py` | 300 轮 fixture rebuild 后不 500 |
| **P2.3 tool 结果 prune** | M6.2.15 | 1d | checkpoint 后旧 tool 输出可丢弃（display 保留） | `friday/context.py`, `sessions.py` | display 完整、agent 瘦身 |
| **P2.4 微信统一管线** | M6.2.16 | 1d | `weixin/bridge.py` 调用同一 assembler | `friday/weixin/bridge.py` | weixin 测试 + 桌面一致 |
| **P2.5 Goal 完成校验** | M6.2.17 | 1.5d | 独立 verifier；触发：有 plan 或复杂任务；可设置关闭 | 新建 `friday/goal_verifier.py`, `agent.py`, `settings` | 未完成 plan 时拦截「收尾」 |
| **P2.6 会话 fork** | M6.2.18 | 1d | 从 checkpoint+plan 种子新建 session；可选复制标题后缀 | `friday/sessions.py`, `server.py`, `web/sessions.js` | fork 后新会话含 checkpoint 种子 |
| **P2.7 上下文健康 UI** | M6.2.19 | 0.5d | rebuild 后顶部一次性提示（可关） | `web/chat.js`, `i18n.js` | rebuild 后出现说明条 |
| **P2.8 集成测试** | M6.2.20 | 1.5d | 200 轮 chaos；writer 慢 30s；路径回忆 | `tests/brain/` | 2am 置信测试用例 |

**Phase 2 发版建议：** minor **v1.5.0**。

---

### 大计划 P3 — 项目记忆 + FTS + Dream（v1.5.x～v1.6.0）

**用户可感知：** 工作区「规矩」跨天记得住；能搜旧对话；记忆可审阅、可清理。

| 子计划 | 编号 | 工作量 | 内容 | 涉及文件 | 验证 |
|--------|------|--------|------|----------|------|
| **P3.1 MEMORY.md 存储** | M6.2.21 | 1d | 按 `resolved_workspace` 落盘；writer 晋升规则 | `friday/workspace_memory.py`, `checkpoint_writer.py` | 重复事实 2 次 checkpoint 后晋升 |
| **P3.2 MEMORY 设置 UI** | M6.2.22 | 1.5d | 数据面板：查看/编辑/删除；空状态 | `web/settings.js`, `server.py`, `index.html` | 编辑后下轮 prompt 生效 |
| **P3.3 history.db  schema** | M6.2.23 | 1d | SQLite + FTS5；会话消息双写 | 新建 `friday/history_index.py` | 迁移脚本 + 空库启动 |
| **P3.4 索引同步** | M6.2.24 | 1d | 新消息/折叠/rebuild 时增量索引 | `sessions.py`, `history_index.py` | 重启后会话仍可搜 |
| **P3.5 历史搜索 API+UI** | M6.2.25 | 1.5d | 侧栏或设置内搜索；高亮命中会话 | `server.py`, `web/sessions.js` | 中文+路径关键词可命中 |
| **P3.6 Dream 任务** | M6.2.26 | 1.5d | 每周空闲触发；合并去重 MEMORY；写前备份 | 新建 `friday/dream_task.py`, `storage.py` 开关 | opt-in 开启后生成 diff 日志 |
| **P3.7 ChatSession 扩展字段** | M6.2.27 | 0.5d | `checkpoint_version`, `context_cycle`, `workspace_id`, `source` | `friday/sessions.py` | 旧 JSON 向后兼容加载 |
| **P3.8 全量回归** | M6.2.28 | 1d | credentials/settings 回归矩阵 + 新域测试 | `tests/api/`, `tests/brain/` | 见 long-term-plan 高风险模块 pytest |

**Phase 3 发版建议：** **v1.5.1～v1.6.0** 可分两次发（先 MEMORY+FTS，后 Dream）。

---

## 5. 依赖与顺序

```text
P0 ──► P1 ──► P2 ──► P3
         │      │
         │      ├── Goal (P2.5) 依赖 checkpoint (P1)
         │      └── Fork (P2.6)  依赖 checkpoint (P1)
         └── 可与 M3 签名并行，不硬依赖
```

**建议下一刀：** M6.2.1（P0.1 上下文仪表 API）。

---

## 6. 明确不做（本期）

- Max 采样 / judge（→ TODOS）
- Dynamic Workflow / 子 Agent 编排
- 云端同步记忆
- 重写 Electron / OpenCode 底座
- 动 `credentials_store` / settings merge（除非 MEMORY 只读路径必需）

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| writer 与主循环竞态 | 文件锁 + 单写者 |
| rebuild 后仍超限 | 硬截断 tail + 用户提示新开会话 |
| FTS 双写不一致 | 以 JSON 为准，DB 可重建索引 |
| Dream 误合并 | 写前备份；设置页可回滚 |
| Goal 误拦 | 默认仅 plan/复杂任务；可一键「标记完成」 |

功能开关建议：`settings.context_smart_enabled`（默认 true，可关回旧行为）。

---

## 8. 成功指标

| 指标 | 目标 |
|------|------|
| 长对话路径回忆 | 抽检 ≥90% |
| rebuild 成功率 | 无 500；日志可追踪 |
| FTS 查询 p95 | <200ms（本地 1 万条消息级） |
| Dream 后 MEMORY 体积 | 合并后 ≤ 原 70%（或条目数下降） |

---

*子计划共 28 项（M6.2.1～M6.2.28）。进度以 `long-term-plan.md` 勾选为准。*
