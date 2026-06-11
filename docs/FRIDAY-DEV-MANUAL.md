# 星期五系统开发手册

> 版本：2026-06-08 · 对应应用 `friday/version.py` **1.2.0**  
> 适用：Reasonix / Cursor 维护者 · 源码路径建议 **`E:\Friday`**

---

## 1. 产品概览

**星期五** 是 Windows 桌面 AI 电脑管家：用户用自然语言对话，大模型理解意图，本地工具真正执行（整理文件、系统体检、生文档、下载软件、Python 脚本等）。

| 维度 | 说明 |
|------|------|
| 平台 | Windows 10/11 |
| 界面 | WebView2 内嵌 `web/`（Vanilla JS） |
| 后端 | FastAPI @ 127.0.0.1 动态端口（默认从 8765 起） |
| 数据 | `%APPDATA%\Friday\` + 用户工作区文件夹 |
| 更新源 | Gitee `Bxxxboo/friday`（国内默认） |
| 镜像 | GitHub `Bxxxboo/Friday-Zero-barrier-DeepSeek-Agent-for-Windows` |

---

## 2. 仓库结构

```
E:\Friday/
├── run.py                 # 入口：单实例锁 → desktop.main()
├── setup.ps1              # 创建 .python-env + pip install
├── requirements.txt       # 运行时依赖
├── friday/                # Python 包（核心）
├── web/                   # 前端静态资源
├── tests/                 # pytest
├── scripts/               # 构建、发布、图标、Reasonix 安装
├── docs/                  # 计划、手册、Reasonix 合集
├── assets/                # friday.ico 等
├── extensions/            # 内置扩展 manifest
├── .cursor/               # Cursor rules + UI skills
├── .reasonix/             # Reasonix skills + vision_bridge 脚本
├── DESIGN.md              # UI 设计 token（必读）
├── PRODUCT.md             # 产品定位
└── README.md              # 用户向说明
```

### 2.1 `friday/` 核心模块

| 模块 | 职责 |
|------|------|
| `desktop.py` | WebView2 窗口、Splash、后台启 Uvicorn |
| `server.py` | REST + WebSocket + 静态文件 |
| `agent.py` | 多轮工具调用、审批、取消、操作日志 |
| `brain.py` | System prompt、OpenAI SDK、前缀缓存 |
| `storage.py` | settings 读写、Fernet 加密 API Key |
| `sessions.py` | 会话 CRUD、消息持久化 |
| `tools/registry.py` | 工具注册、超时、懒加载 |
| `safety.py` | 工具风险分级、用户审批 |
| `portability.py` | 可移植性 audit / 修复 |
| `portable_bundle.py` | 配置包 zip 导入导出 |
| `vision.py` / `image_gen.py` | 视觉 / 生图 API 封装 |
| `weixin/` | OpenClaw 微信桥接 |
| `scheduler.py` / `schedules.py` | 定时任务 |

### 2.2 `friday/tools/` 工具模块

| 模块 | 工具示例 |
|------|----------|
| `filesystem.py` | list/read/write/move/copy/delete |
| `shell.py` | run_powershell, open_app, open_url |
| `python_runner.py` | run_python, run_python_script |
| `system.py` | CPU/内存/磁盘/进程/网络 |
| `documents.py` | create_docx, create_pptx |
| `media.py` | read_pdf, screenshot, clipboard |
| `web.py` | browse_webpage, download_file |
| `vision.py` | describe_image |
| `image_gen.py` | generate_image |
| `extensions.py` | 插件安装/列表 |
| `plan_tools.py` | Plan/Todo 面板 |

新增工具：装饰器 + 注册模块名 + `safety.py` + 测试。

---

## 3. 运行时架构

```
用户
  │
  ▼
[WebView2 窗口]  web/index.html + *.js
  │  HTTP/WS
  ▼
[FastAPI server.py]  :8765 (或 find_free_port)
  │
  ├─► FridayAgent ──► DeepSeekBrain ──► OpenAI 兼容 API
  │         │
  │         └─► tools/registry.execute_tool()
  │
  ├─► sessions / storage / plugins / schedules
  └─► weixin bridge (可选)
```

**单实例：** `127.0.0.1:58765`（`instance_lock.py`）。重复启动会 `focus_existing_window()` 并 exit 0。

**配置热读：** 多数 API 每次读 `storage.load_settings()`；改 settings 后无需重启（部分项如模型列表除外）。

---

## 4. 数据与路径

### 4.1 AppData（`%APPDATA%\Friday\`）

| 文件/目录 | 内容 |
|-----------|------|
| `settings.json` | 模型、Key、文件夹、主题、MCP… |
| `.fernet_key` | API Key 加密密钥 |
| `sessions/` | 各会话 JSON |
| `operations.json` | 操作历史 |
| `schedules.json` | 定时任务 |
| `plugins/` | 用户安装的插件 |
| `skills/` / `rules/` | 用户自定义技能与规则 |
| `friday.log` | 应用日志 |
| `webview2/` | WebView2 用户数据目录 |
| `icons/` | 快捷方式图标缓存 |

### 4.2 工作区

用户设置的「默认操作文件夹」（如 `Documents/星期五`）：

- Agent 文件操作默认 cwd
- `.python-env/`：Agent 用 Python 虚拟环境（**可移植性：换机需重建**）

### 4.3 配置包（可移植性）

见 `docs/archive/PORTABILITY-PLAN.md`（归档）与 `friday/portability.py`。导出 zip 含 settings 子集、MCP、插件 manifest 等；**默认不含**完整会话（P0 起逐步补齐 sessions_index）。

---

## 5. 开发环境搭建

### 5.1 前置

- Windows 10/11
- Python 3.11+（推荐 3.12）
- [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)
- Git（双远端发布）

### 5.2 首次安装

```powershell
cd E:\Friday
powershell -ExecutionPolicy Bypass -File setup.ps1
# 或使用已有 .python-env：
.\.python-env\Scripts\pip install -r requirements.txt
```

### 5.3 启动

```powershell
# 开发（无控制台黑框）
.\.python-env\Scripts\pythonw.exe run.py

# 调试（可看 stderr）
.\.python-env\Scripts\python.exe run.py
```

### 5.4 测试

```powershell
.\.python-env\Scripts\pip install -r requirements-dev.txt
.\.python-env\Scripts\python.exe -m pytest tests/ -q
```

### 5.5 打包

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
# 产物：dist\星期五\星期五.exe
```

### 5.6 桌面快捷方式

```powershell
.\.python-env\Scripts\python.exe scripts\create_icon.py
# 或运行 release\create-shortcut.ps1 生成桌面「星期五」快捷方式
```

---

## 6. 前端开发

### 6.1 约束

- **Vanilla JS**，无 React/Vue
- 设计 token：`web/styles.css` + `DESIGN.md`
- 双主题必测
- WebView2：`-webkit-app-region: no-drag` 于可交互元素

### 6.2 主要文件

| 文件 | 说明 |
|------|------|
| `web/index.html` | 布局、设置模态、Onboarding |
| `web/styles.css` | 全局样式 |
| `web/app.js` | 主逻辑、聊天流 |
| `web/chat.js` | 消息渲染、Markdown |
| `web/settings.js` | 设置各 section、可移植性 UI |
| `web/onboarding.js` | 首次引导 |
| `web/weixin.js` | 微信配置向导 |
| `web/errorHints.js` | API 错误 → 用户文案 |

### 6.3 缓存

静态资源 URL 带 `?v=<version>`（来自 `/api/health` 或内联版本），改 JS/CSS 后 bump 版本或改 query。

---

## 7. 后端 API 概要

完整路由见 `friday/server.py`。常用：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 版本、就绪状态 |
| GET/PUT | `/api/settings` | 读写设置 |
| POST | `/api/chat/stream` | 流式对话（SSE/WS） |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/portable/audit` | 可移植性自检 |
| POST | `/api/portable/export` | 导出配置包 |
| POST | `/api/portable/import` | 导入配置包 |
| WS | `/ws` | 推送（微信消息等） |

本地 API 可选 token：`friday/auth.py`（`FRIDAY_API_TOKEN`）。

---

## 8. Agent 与工具体系

### 8.1 调用链

1. 用户消息 → `server` → `FridayAgent.run_turn()`
2. `brain.chat()` 带 `tools` schema
3. 模型返回 `tool_calls` → `registry.execute_tool()`
4. 高风险工具 → `safety` 审批 UI → 用户确认
5. 工具结果回填 messages，循环至 `MAX_TOOL_ROUNDS`

### 8.2 超时

`friday/config.py`：`TOOL_TIMEOUT_*` 按工具类型区分（读文件、下载、视觉、生图等）。

### 8.3 System Prompt

`brain.py` 内 `_SYSTEM_PROMPT_BASE` + 动态文件夹路径 + skills/rules 注入。改 persona 或工具说明在此文件。

---

## 9. 视觉与生图

| 能力 | 配置位置 | 说明 |
|------|----------|------|
| 视觉辅助 | settings: vision_* | 豆包/Ark 多模态；Base URL 为 API 根 |
| 生图 | settings: image_gen_* | OpenAI 兼容 / 方舟 |
| Reasonix 看图 | `.reasonix/scripts/vision_bridge.py` | 与星期五共用 settings |

**常见错误：** 把 MiMo 的 `/chat/completions` 完整 URL 填入视觉 Base URL → 400/404。

---

## 10. Agent 执行安全

Yolo 模式、PowerShell/Python 黑名单、已知绕过限制见 **[docs/AGENT-SAFETY.md](AGENT-SAFETY.md)**。改 `friday/safety.py` 或 `friday/tools/shell.py` 时须跑 `tests/tools/test_shell.py` 与 `tests/agent/test_interaction_modes.py`。

---

## 11. 微信 / OpenClaw

- 配置：`friday/weixin/`，桥接端口写入 `weixin-bridge.json`
- 依赖本机 OpenClaw runtime（`~/.openclaw`），**配置包无法带走登录态**
- 开机自启：`scripts/install-openclaw-autostart.ps1`

---

## 12. 可移植性（维护重点）

长期计划：`docs/archive/PORTABILITY-PLAN.md`（归档）

| 里程碑 | 内容 |
|--------|------|
| M1 P0 | sessions_index、schedules/operations 导出、原子 import |
| M1 P1 | 自检 UI、换机迁移向导 |
| M1 P3 | error_hints、Composer 待配置态 |

关键代码：`friday/portability.py`、`friday/portable_bundle.py`、`web/settings.js`。

---

## 13. 发布流程

1. 改代码 + pytest 通过
2. bump `friday/version.py` + `scripts/version_info.py`
3. `scripts\sync-remotes.cmd` 或 `publish-release.cmd`
4. Gitee Release 必发；GitHub 可选

详见 `docs/reasonix/rules/version-and-github.md`。

---

## 14. Reasonix 开发配置

### 13.1 安装 AI 合集

```powershell
cd E:\Friday
powershell -ExecutionPolicy Bypass -File scripts\install-reasonix-bundle.ps1
```

### 13.2 文档索引

| 文档 | 用途 |
|------|------|
| `docs/reasonix/INSTALL.md` | Rules/Skills 安装说明 |
| `docs/reasonix/user-rules.md` | 用户级偏好 → 粘贴到 Reasonix |
| `docs/reasonix/rules/` | 项目 Rules |
| `docs/reasonix/skills/` | friday-dev / friday-ui |
| `.cursor/skills/` | UI 设计重型 Skills |
| `.reasonix/skills/vision-bridge.md` | Reasonix 识图 |

### 13.3 推荐工作流

1. Reasonix 打开 **`E:\Friday`** 为工作区
2. 后端任务：读 `friday-dev` skill + karpathy rules
3. 前端任务：读 `friday-ui` + `DESIGN.md`
4. 发版：读 `version-and-github` rule

---

## 15. 故障排查

| 现象 | 排查 |
|------|------|
| 启动即退出 | 是否已有实例（58765）；查 `friday.log` |
| ModuleNotFoundError tools.* | 源码不完整，对照 GitHub `main` 补文件 |
| WebView2 失败 | 安装 WebView2 Runtime；`win10_runtime.py` |
| API Key 解密失败 | `.python-env` 缺 `cryptography` |
| 工具不加载 | `registry._EAGER_MODULES` import 链 |
| 视觉 400/404 | Base URL / endpoint ID / 勿混用 MiMo URL |
| 快捷方式无图标 | 跑 `scripts/create_icon.py`，图标在 `%APPDATA%\Friday\icons\` |

---

## 16. 相关文档

- `README.md` — 用户快速开始
- `docs/AGENT-SAFETY.md` — Yolo 与 PowerShell/Python 黑名单
- `PRODUCT.md` / `DESIGN.md` — 产品与 UI
- `docs/archive/PORTABILITY-PLAN.md` — 可移植性路线图（归档）
- `CHANGELOG.md` — 版本变更
- `windows.md` — Windows 专项说明

---

## 17. 维护者备忘

- **不要**把 API Key、`.fernet_key` 提交进 Git
- **不要**拷贝 `.venv/` / `.python-env/` 到新机器（在工作区重建）
- 改 `web/` 必看双主题；改 API 必跑 pytest
- 双远端：Gitee 为国内用户更新源，不可只 push GitHub

---

*本手册随仓库维护；重大架构变更请同步更新本节与 `friday/portability.py`。*
