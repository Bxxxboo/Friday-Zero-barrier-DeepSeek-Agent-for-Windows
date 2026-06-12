# 星期五 (Friday) 商业级成熟化 — 长期计划

> 版本基准：v1.3.2（M1～M2 已发版；M4/M5 代码合入本版）；M2 人工验收已完成（2026-06-11）  
> 更新日期：2026-06-11（M6.2 上下文/会话智能计划已写入）  
> 目标：从「功能稳定的 Python 工具」升级为「用户感知的成熟商业桌面应用」

---

## 如何使用本计划

1. **从上往下做**：大任务有依赖顺序（M1 → M2 → …），不要跳级。
2. **一次只开一个子任务**：每个子任务预估 **0.5～2 天**，带「涉及文件」和「验证」。
3. **做完打勾**：`[x]` 表示已完成；`[~]` 表示进行中。
4. **发版单独决策**：子任务做完 ≠ 自动 bump 版本；发版等你指令。

**编号规则**

| 层级 | 格式 | 含义 |
|------|------|------|
| 大任务 | **M1～M6** | 一个版本主题或里程碑 |
| 子任务 | **M1.1、M1.2…** | 单次可交付、可验证的工作单元 |

---

## 当前进度（一眼看懂）

| 大任务 | 版本 | 进度 | 下一步 |
|--------|------|------|--------|
| **M1** 桌面进程身份 | v1.3.0 | ✅ 已随 v1.3.0 发版 | — |
| **M2** 分发与安装 | v1.3.0 | ✅ 已完成（含人工验收） | — |
| M3 信任与安全 | v1.4.x | 2/5 进行中 | **M3.1 采购 IV 证书**（阻塞签名）；M3.3/M3.4 代码已就绪 |
| M4 可靠性与可观测 | v1.5.0 | ✅ 已完成 | — |
| M5 产品体验抛光 | v1.6.0 | ✅ 已完成 | — |
| M6 架构与智能 | v1.4～v1.6 | **28/28 M6.2 已完成** | 等你指令 bump 发 v1.4.x～v1.6（可分批发） |
| M6.1 打包调研 | v2.0 | 未开始 | 可选，不阻塞 M6.2 |

---

## 路线图总览

| 大任务 | 版本 | 主题 | 子任务数 | 周期（估） |
|--------|------|------|----------|-----------|
| **M1** | v1.3.0 | 桌面进程身份 | 5 | ✅ 基本完成 |
| **M2** | v1.3.0 | 分发与安装体验 | 9 | ✅ 已发 + 人工验收通过 |
| **M3** | v1.3.x | 信任与安全（签名） | 5 | 4～6 周 |
| **M4** | v1.5.0 | 可靠性与可观测 | 5 | 3～4 周 |
| **M5** | v1.6.0 | 产品体验抛光 | 6 | 4～6 周 |
| **M6.2** | v1.4～v1.6 | 上下文与会话智能 | 28 | 6～10 周 |
| **M6.1** | v2.0 | 打包方案调研（文档） | 1 | 按需 |

---

# 大任务清单

---

## M1 — 桌面进程身份（v1.3.0）

**用户可感知：** 任务管理器主进程显示「星期五」；Agent 跑脚本显示 FridayAgent，不再裸 Python。

**依赖：** 无（可立即开工，已基本完成）

### M1.1 主 exe 统一为 Friday.exe

- [x] **工作量：** 1 天  
- **涉及文件：** `friday.spec`, `scripts/version_info.py`, `scripts/friday-dist.ps1`, `release/*`  
- **验证：**
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/build.ps1
  # dist/Friday/Friday.exe 存在；任务管理器显示「星期五 - AI 电脑管家」
  pytest tests/platform/ tests/api/test_update_installer.py -q
  ```

### M1.2 Agent 子进程品牌化（FridayAgent.exe）

- [x] **工作量：** 1 天  
- **涉及文件：** `friday/python_env.py`, `friday/tools/python_runner.py`, `scripts/brand-agent-python.ps1`, `scripts/brand_agent_runner.py`  
- **验证：**
  ```powershell
  pytest tests/tools/test_python_env.py -q
  powershell -File scripts/brand-agent-python.ps1 -Workspace "e:\Friday"
  # Agent 跑脚本后任务管理器出现 FridayAgent
  ```

### M1.3 启动路径审计（打包环境禁止 pythonw）

- [x] **工作量：** 1 天  
- **涉及文件：** `friday/autostart.py`, `friday/update_installer.py`, `friday/paths.py`, `scripts/install-friday-autostart.ps1`  
- **验证：**
  ```powershell
  pytest tests/api/test_autostart.py tests/api/test_update_installer.py -q
  # 自启 + 更新重启均只启动 Friday.exe
  ```

### M1.4 设置页「关于」显示运行模式

- [x] **工作量：** 0.5 天  
- **涉及文件：** `friday/runtime_info.py`, `friday/server.py`, `web/index.html`, `web/settings.js`  
- **验证：**
  ```powershell
  pytest tests/api/test_runtime_info.py -q
  # 设置 → 应用与数据 → 开发模式显示「任务管理器将显示 Python」
  ```

### M1.5 v1.3.0 打包验证与发布

- [x] **工作量：** 0.5 天  
- **前置：** M1.1～M1.4 全部完成  
- **涉及文件：** `friday/version.py`, `scripts/version_info.py`, `scripts/publish-release.cmd`（发版时）  
- **验证：**
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/build.ps1
  # 本机安装 dist 包，走一遍：启动 / 自启 / Agent 跑脚本 / 关于页
  pytest tests/ -q -k "not e2e"
  ```
- **发版：** 等你指令再 bump + 双端 push + Gitee Release
- **2026-06-11 进度：**
  - [x] `build.ps1` → `dist/Friday/Friday.exe`（25 MB）
  - [x] `pytest -k "not e2e"` → 471 passed
  - [ ] 本机：解压/安装 dist，任务管理器主进程 = `Friday.exe`；Agent = `FridayAgent.exe`；关于页运行模式正确
  - [x] bump `1.3.0` + `publish-release`（2026-06-11）

**M1 整体验收：**

```powershell
Get-Process Friday -ErrorAction SilentlyContinue | Select-Object Name, Id
# 主进程 = Friday；Agent = FridayAgent
```

---

## M2 — 分发与安装体验（v1.3.0，与 M1 同版发布）

**用户可感知：** 官网下载安装包 → 向导安装 → 开始菜单/卸载入口；少碰 ZIP 和 `解除锁定.ps1`。

**依赖：** M1.5 发版后开工（exe 名与路径已稳定）

### M2.1 安装路径与目录规范

- [x] **工作量：** 0.5 天  
- **内容：** 约定默认安装目录 `%LOCALAPPDATA%\Programs\Friday\`；用户数据仍在 `%APPDATA%\Friday\`；文档写清与 ZIP 绿色版差异  
- **涉及文件：** 新建 `docs/INSTALL-LAYOUT.md`；必要时 `friday/paths.py` 注释对齐  
- **验证：** 文档评审通过；`update_installer` / `autostart` 路径与文档一致

### M2.2 Inno Setup 脚本骨架

- [x] **工作量：** 1 天  
- **内容：** 新建 `installer/friday.iss`；能打出空壳安装包；版本号从 `friday/version.py` 读取  
- **涉及文件：** `installer/friday.iss`, `scripts/build-installer.ps1`（新建）  
- **验证：**
  ```powershell
  # 本地安装 Inno Setup 6 后
  powershell -File scripts/build-installer.ps1
  # 产出 installer/Friday-Setup-{version}.exe
  ```

### M2.3 安装向导：复制 dist + 内嵌 Unblock

- [x] **工作量：** 1～2 天  
- **内容：** 安装器解压/复制 `dist/Friday/` 到目标目录；安装结束时对 exe 执行 Unblock（替代手动 `解除锁定.ps1`）  
- **涉及文件：** `installer/friday.iss`, `release/解除锁定.ps1`（逻辑迁入或复用）  
- **验证：** 干净 Windows 虚拟机：下载安装 → 双击 Friday.exe 无「已阻止」提示

### M2.4 开始菜单 + 桌面快捷方式

- [x] **工作量：** 1 天  
- **内容：** 安装器创建开始菜单项与可选桌面快捷方式；显示名中文「星期五」，Target 指向 `Friday.exe`  
- **涉及文件：** `installer/friday.iss`；对齐 `release/创建桌面快捷方式.ps1` 逻辑  
- **验证：** 安装后开始菜单可启动；快捷方式图标正确

### M2.5 卸载程序

- [x] **工作量：** 1 天  
- **内容：** Inno 卸载入口；控制面板 / 设置 → 应用 可卸载；**不删** `%APPDATA%\Friday\` 用户数据（或卸载时询问）  
- **涉及文件：** `installer/friday.iss`  
- **验证：** 安装 → 卸载 → 程序目录消失；用户设置与会话保留（若选保留）

### M2.6 发布流程集成

- [x] **工作量：** 1 天  
- **内容：** `make-release.ps1` / `publish-release` 同时产出 ZIP（进阶）+ Setup（默认）；Gitee Release 附两种包  
- **涉及文件：** `scripts/make-release.ps1`, `scripts/publish-release.cmd`, `.github/workflows/release.yml`  
- **验证：** 本地跑通发布脚本；Release 页有 Setup + ZIP

### M2.7 一键更新：更新前自动备份

- [x] **工作量：** 1 天  
- **内容：** `update_installer.py` 覆盖前把当前安装目录复制到 `Friday.bak/`  
- **涉及文件：** `friday/update_installer.py`, `tests/api/test_update_installer.py`  
- **验证：**
  ```powershell
  pytest tests/api/test_update_installer.py -q
  # 模拟更新失败时 Friday.bak 存在且可手动恢复
  ```

### M2.8 一键更新：失败自动回滚

- [x] **工作量：** 1～2 天  
- **内容：** 更新后首次启动自检失败 → 从 `Friday.bak/` 恢复；设置页提示回滚原因  
- **涉及文件：** `friday/update_installer.py`, `friday/desktop.py` 或启动入口  
- **验证：** 故意损坏新包 → 启动后自动回到旧版

### M2.9 官网 MVP（Vercel 页面 + Gitee 下载）

- [x] **工作量：** 0.5～1 天  
- **前置：** v1.3.0 已含 Setup Release；发版后再上线官网  
- **用户可感知：** 打开官网（Vercel）→ 了解产品 → 点下载 → Gitee Release 上的 Setup（不必自己去 Releases 翻找）  
- **已拍板：阶段 1 — Vercel 托管页面 + Gitee 托管安装包**（零云存储成本；下载速度接受 Gitee 常见区间约 0.5～2 分钟/64MB）

#### 架构（阶段 1）

| 角色 | 托管位置 | 用途 |
|------|----------|------|
| 官网 HTML | **Vercel**（`website/` 或独立部署） | 介绍、截图、changelog、SEO 基础 |
| **Setup 下载** | **Gitee Release** 直链 | 官网「下载 Windows 版」按钮 |
| ZIP 进阶包 | 同页链到 Gitee Releases 页 | 绿色版用户 |
| 应用内一键更新 | Gitee Releases API（`friday/updates.py`） | **不改** |

#### 下载 URL 约定（示例）

```
https://gitee.com/Bxxxboo/friday/releases/download/v{version}/Friday-Setup-{version}.exe
```

发版后更新 `website/download.json`（或构建时注入）中的 `version` + `setup_url`。

#### 发版流程（阶段 1）

```powershell
# 与现有 publish-release 一致，无 OSS 上传步骤
# 1. build-installer → Friday-Setup-{version}.exe
# 2. publish-release → Gitee/GitHub Release 附 Setup + ZIP
# 3. 更新 website 中的下载链接 → git push → Vercel 自动部署
```

- **内容：**
  - 静态站：`website/`（对齐 `DESIGN.md` 品牌色）
  - Vercel：连 GitHub/Gitee 镜像仓库或 CLI 部署；`vercel.json` 路由（可选）
  - 应用内：设置页「更新源 / 手动下载」→ 官网首页或 Gitee Release
  - 文档：`docs/WEBSITE.md`（Vercel 部署与发版改链说明）
- **涉及文件：** `website/*`；`docs/WEBSITE.md`；`web/settings.js`；`friday/version.py`（`WEBSITE_HOME` 常量，可选）  
- **验证：**
  - 浏览器打开 Vercel 地址 → 下载得到正确 Setup
  - 发版后仅改链接 + push，Vercel 预览/production 更新
- **明确不做（阶段 1）：** 阿里云 OSS、备案域名、一键更新改 CDN、账号系统

#### 后续升级路径（非 M2.9 阻塞，按需）

当下载变慢投诉增多或要做 SEO 域名时，可升级为：

| 升级项 | 做法 |
|--------|------|
| 下载加速 | **阿里云 OSS + CDN** 托管 Setup；官网按钮改 CDN URL；补 `upload-release-oss.ps1`（见原 M2.9 OSS 方案） |
| 更好被搜到 | 自有域名 + 百度/Google 站长；可选 ICP 备案 |
| 页面国内加速 | 域名备案后静态页迁国内 CDN，或保留 Vercel 仅作海外 |

预估 OSS 小流量仍约 **几十元/年**；与阶段 1 可无缝切换（Release 仍保留作备份）。

**M2 整体验收：** 新用户从**官网或安装包**完成安装，全程不碰 ZIP、不跑 PowerShell 解除锁定；老用户仍可用 ZIP。

**M2 人工验收清单（2026-06-11，用户确认通过）：**

验收包：`Friday-Setup-1.3.x`（含安装后 `--install-launch` 置顶 + `Friday.exe` + 内嵌 Unblock）

- [x] 干净目录安装（默认 `%LOCALAPPDATA%\Programs\Friday\`），安装结束勾选「启动星期五」→ 窗口自动置顶到前台
- [x] 双击 `Friday.exe` 无 SmartScreen「已阻止」类提示（Unblock 已内嵌）
- [x] 开始菜单 / 可选桌面快捷方式可启动
- [x] 卸载后程序目录消失，`%APPDATA%\Friday\` 用户数据仍在
- [x] 安装向导为简体中文（覆盖安装后生效）

**M2 里程碑关闭。** 下一主线：**M3.1 采购 IV 代码签名证书**（或先发 v1.3.2 含 SHA256/设置修复，签名待 M3.2）。

---

## M3 — 信任与安全（v1.3.x）

**用户可感知：** SmartScreen 不再显示「未知发布者」；更新包有校验。

**依赖：** M2.6（有正式安装包/Release 工件）；需采购代码签名证书（**个人 → IV，有公司 → OV**）

### M3.1 代码签名证书与密钥管理

- [ ] **工作量：** 1 天（+ 证书审批等待 3～7 工作日）  
- **内容：** 采购 **IV（Individual Validated）** Authenticode 证书（星期五维护者为个人，无需营业执照）；私钥须在 CA 提供的 **USB 硬件令牌**或云 HSM 上（行业强制，不接受纯文件型 .pfx）；CI/本机签名密钥存放约定（不进 git）  
- **推荐路径：** SSL.com IV Code Signing + USB 令牌（约 $100–200/年）；证书到手前 M1/M2 可照常无签名发版  
- **涉及文件：** `docs/SIGNING.md`（新建）；`.gitignore` 确认排除密钥  
- **验证：** 文档 + 本机 `signtool` 能对任意 exe 试签；右键属性 → 数字签名显示个人实名

### M3.2 签名 pipeline（exe + 安装包）

- [ ] **工作量：** 1～2 天  
- **内容：** 发布前对 `Friday.exe`、`FridayAgent.exe`、Setup 安装包签名  
- **涉及文件：** `scripts/sign-release.ps1`（新建）, `scripts/make-release.ps1`  
- **验证：** 右键 exe → 数字签名有效；SmartScreen 信誉随下载量积累（IV 非立刻零警告，属正常）

### M3.3 Release SHA256 清单

- [x] **工作量：** 0.5 天  
- **内容：** 每个 Release 附 `SHA256SUMS.txt` 或 Gitee Release 说明内嵌哈希  
- **涉及文件：** `scripts/make-release.ps1`, `scripts/publish_gitee_release.py`, `scripts/publish_github_release.py`, `friday/release_hashes.py`  
- **验证：** Release 页可核对 ZIP/Setup 哈希
- **2026-06-11：** `make-release.ps1` 生成 `release/SHA256SUMS.txt`；Gitee/GitHub 发布脚本上传该文件

### M3.4 更新下载校验

- [x] **工作量：** 1 天  
- **内容：** `update_installer.py` 下载后校验 SHA256，不匹配则拒绝安装  
- **涉及文件：** `friday/update_installer.py`, `friday/updates.py`, `tests/api/test_release_hashes.py`  
- **验证：** pytest + 故意篡改包应失败并提示
- **2026-06-11：** 检查更新返回 `download_sha256`；一键更新下载后校验；旧 Release 无清单时跳过校验（兼容）

### M3.5 崩溃/遥测 opt-in

- [ ] **工作量：** 1 天  
- **内容：** 设置页开关；默认关闭；文案说明收集范围  
- **涉及文件：** `web/settings.js`, `friday/server.py`, `friday/storage.py`  
- **验证：** 默认关闭；开启后才写入上报队列（可与 M4.1 衔接）

---

## M4 — 可靠性与可观测（v1.5.0）

**用户可感知：** 崩溃有记录；设置里可导出诊断包；更新能回滚（与 M2.8 闭环）。

**依赖：** M2.7/M2.8 备份回滚基础

### M4.1 崩溃捕获与本地落盘

- [x] **工作量：** 1～2 天  
- **内容：** 未处理异常 → `%APPDATA%/Friday/crashes/`；含时间、版本、堆栈  
- **涉及文件：** `friday/crash_handler.py`；`run.py` / `desktop.py` 最早注册  
- **验证：** 故意 `raise` 一次 → `crashes/` 下有新文件
- **2026-06-11：** 主线程 `sys.excepthook` + 后台 `threading.excepthook`；保留最近 30 份 `crash-*.log`

### M4.2 设置页「导出诊断包」

- [x] **工作量：** 1 天  
- **内容：** ZIP：版本、运行模式、日志尾部、系统信息、Gateway 状态（脱敏）  
- **涉及文件：** `friday/diagnostics_bundle.py`, `friday/server.py`, `web/settings.js`, `web/index.html`  
- **验证：** 点击导出 → 得到可打开的 zip；无 API Key 明文  
- **2026-06-11：** `POST /api/diagnostics/export`；设置页「导出诊断包」；`tests/api/test_diagnostics_bundle.py`

### M4.3 健康检查扩展

- [x] **工作量：** 0.5～1 天  
- **内容：** `/api/health` 增加 WebView、Gateway、Python env 子状态  
- **涉及文件：** `friday/health_check.py`, `friday/server.py`  
- **验证：**
  ```powershell
  curl http://127.0.0.1:PORT/api/health
  # JSON 含子服务 ok/degraded 字段
  ```
- **2026-06-11：** `services.webview|gateway|python_env`；顶层 `status` 仍为 `starting|ok`；`degraded` 标记可选子服务异常

### M4.4 日志轮转

- [x] **工作量：** 1 天  
- **内容：** `friday.log` 大小上限 + 保留 N 天；启动时清理过期  
- **涉及文件：** `friday/logging_config.py`  
- **验证：** 配置小阈值后跑一段时间 → 出现 `.log.1` 或归档删除  
- **2026-06-11：** `RotatingFileHandler`（默认 5MB / 14 份备份）；`purge_expired_logs()` 启动清理（默认 7 天）；`FRIDAY_LOG_MAX_BYTES` / `FRIDAY_LOG_RETAIN_DAYS` 可覆盖

### M4.5 启动崩溃触发回滚

- [x] **工作量：** 1 天  
- **内容：** 连续 3 次启动崩溃 → 自动从 `Friday.bak/` 恢复（衔接 M2.8）  
- **涉及文件：** `friday/update_rollback.py`, `friday/crash_handler.py`, `friday/desktop.py`, `run.py`  
- **验证：** 模拟坏包连续启动 → 自动回滚并提示  
- **2026-06-11：** `record_startup_crash()` 由崩溃钩子写入；`guard_startup_after_update()` 达 3 次后回滚；主窗口显示 `confirm_startup_success()` 清零

---

## M5 — 产品体验抛光（v1.6.0）

**用户可感知：** 设置更好找；空状态/加载/error 有温度；无障碍基线达标。

**依赖：** 无硬依赖；建议 M4 后再做大改 UI，减少返工

### M5.1 设置导航重组（7 组）

- [x] **工作量：** 2 天  
- **目标结构：**
  ```
  入门（API + 文件夹）
  连接（大模型 / 视觉 / 生图）
  自动化（定时 / 自启）
  扩展（插件 / 规则）
  微信
  数据（生成物 / 存储）
  关于（版本 / 诊断 / 更新）
  ```
- **涉及文件：** `web/index.html`, `web/settings.js`, `web/i18n.js`, `web/styles.css`  
- **验证：** 现有功能无丢失；E2E 或手工走一遍各面板  
- **2026-06-11：** 7 组侧栏；`panel-app` 拆为 `panel-data` + `panel-about`；自启迁入定时任务；`app`/`logs` 别名兼容

### M5.2 交互状态：对话列表 empty

- [x] **工作量：** 0.5 天  
- **涉及文件：** `web/sessions.js`, `web/styles.css`, `web/i18n.js`  
- **验证：** 无会话时显示引导文案 + 主操作（新建对话）  
- **2026-06-11：** `session-list-empty` 空状态 +「新对话」按钮

### M5.3 交互状态：Gateway / 微信 loading & error

- [x] **工作量：** 1 天  
- **涉及文件：** `web/weixin.js`, `web/statusbar.js`, `web/index.html`, `web/styles.css`, `web/i18n.js`, `friday/status_bar.py`  
- **验证：** 断网 / Gateway 未就绪时有明确状态，非空白或裸错误
- **2026-06-11：** 微信面板 loading/错误空状态 + Gateway 状态条；状态栏新增 Gateway 指示；`/api/status-bar` 返回 gateway_* 字段

### M5.4 交互状态：生成物 empty

- [x] **工作量：** 0.5 天  
- **涉及文件：** `web/index.html`, `web/settings.js`, `web/styles.css`, `web/i18n.js`  
- **验证：** 无生成物时显示说明与跳转设置
- **2026-06-11：** `artifactStorageEmpty` 空状态 + 跳转「文件夹」面板；加载/失败文案 i18n

### M5.5 DESIGN.md token 审计（一轮）

- [x] **工作量：** 1 天  
- **内容：** 对照 `DESIGN.md` 检查 `web/styles.css` 硬编码色/间距；修明显偏离  
- **验证：** 审计清单存档；无新增 AI slop 模式（紫渐变、三列图标卡片等）
- **2026-06-11：** `docs/design-token-audit.md`；补 token（`--text-secondary`、`--surface-2`、`--status-checking`、`--space-*`）；移除 indigo slop 与错误色 fallback

### M5.6 无障碍基线

- [x] **工作量：** 1～2 天  
- **内容：** 设置页键盘 Tab 顺序；对比度 ≥ 4.5:1；触屏目标 ≥ 44px；`prefers-reduced-motion`  
- **涉及文件：** `web/styles.css`, 各 panel HTML  
- **验证：** 键盘可完成保存设置；axe 或手工抽查 3 个主流程
- **2026-06-11：** `docs/a11y-baseline.md`；`--touch-target`、桌面 `focus-visible` 环；设置 tablist/焦点陷阱/方向键；侧栏对比度与 44px 触屏目标

---

## M6 — 架构与智能演进

**不阻塞 M3 签名。** M6.1 仅文档；**M6.2 为生产代码**，详细设计见 [`docs/context-session-plan.md`](docs/context-session-plan.md)。

**已拍板：** 实现路径 A（渐进增强）+ SELECTIVE EXPANSION；纳入 Goal、会话 fork、FTS、Dream；Max 采样 defer。

### M6.1 打包方案评估文档（v2.0，可选）

- [ ] **工作量：** 1～2 天  
- **内容：** PyInstaller onedir / onefile / Nuitka / Tauri 对比：体积、启动、构建、Agent Python 兼容性  
- **涉及文件：** 新建 `docs/architecture-v2-options.md`  
- **验证：** 文档含推荐结论与「v2.0 前不做什么」

---

## M6.2 — 上下文与会话智能（v1.4.0～v1.6.0）

**用户可感知：** 长聊不傻、跨天接得上、能搜历史对话、工作区规矩记得住、复杂任务少早停。

**参考：** [MiMo Code](https://github.com/XiaomiMiMo/MiMo-Code) 分层记忆 + checkpoint + rebuild。

**依赖：** 无硬依赖 M3；建议 M6.2.5 前合入微信桌面同步修复。

### 大计划 P0 — 可观测与压缩前移（v1.4.0）

- [x] **M6.2.1** 上下文 token API（0.5d）— `brain.py`, `status_bar.py`, `api/schemas.py`  
- [x] **M6.2.2** 状态栏上下文 UI（0.5d）— `statusbar.js`, `styles.css`, `i18n.js`  
- [x] **M6.2.3** 压缩双触发策略（1d）— `config.py`, `brain.py`, `agent.py`  
- [x] **M6.2.4** plan 块折叠优先级（0.5d）— `plan.py`, `agent.py`  
- [x] **M6.2.5** Phase 0 回归（0.5d）— `tests/weixin/`, `tests/agent/test_prefix_cache.py`  

### 大计划 P1 — Checkpoint Writer（v1.4.x）

- [x] **M6.2.6** writer 模块骨架（1d）— 新建 `checkpoint_writer.py`  
- [x] **M6.2.7** checkpoint.md 11 字段 schema（0.5d）  
- [x] **M6.2.8** 触发 20/45/70% 增量（1d）— `brain.py`, `agent.py`  
- [x] **M6.2.9** LLM 摘要 + deterministic fallback（0.5d）  
- [x] **M6.2.10** notes.md append 通道（0.5d）  
- [x] **M6.2.11** UI 工作记忆只读面板（1d）— `chat.js`, `server.py`  
- [x] **M6.2.12** writer 单元测试（1d）— `tests/brain/test_checkpoint_writer.py`  

### 大计划 P2 — Rebuild + Goal + Fork（v1.5.0）

- [x] **M6.2.13** context_assembler 分层预算（1.5d）— 新建 `context_assembler.py`  
- [x] **M6.2.14** rebuild 管线 85% 触发（1.5d）— `brain.py`, `agent.py`  
- [x] **M6.2.15** tool 结果 prune（1d）— `context.py`, `sessions.py`  
- [x] **M6.2.16** 微信统一 assembler（1d）— `weixin/bridge.py`  
- [x] **M6.2.17** Goal 完成校验（1.5d）— 新建 `goal_verifier.py`  
- [x] **M6.2.18** 会话 fork（1d）— `sessions.py`, `sessions.js`  
- [x] **M6.2.19** rebuild 提示 UI（0.5d）  
- [x] **M6.2.20** 长对话集成测试（1.5d）  

### 大计划 P3 — MEMORY + FTS + Dream（v1.5.x～v1.6.0）

- [x] **M6.2.21** 工作区 MEMORY.md + 晋升（1d）— `workspace_memory.py`  
- [x] **M6.2.22** MEMORY 设置页审阅/编辑（1.5d）— `settings.js`  
- [x] **M6.2.23** history.db + FTS5 schema（1d）— `history_index.py`  
- [x] **M6.2.24** 消息双写索引同步（1d）  
- [x] **M6.2.25** 历史搜索 API + UI（1.5d）  
- [x] **M6.2.26** Dream 定期蒸馏（1.5d，默认关）— `dream_task.py`  
- [x] **M6.2.27** ChatSession 扩展字段（0.5d）— `sessions.py`  
- [x] **M6.2.28** 全量回归矩阵（1d）  

**发版节奏：** v1.4.0（P0）→ v1.4.x（P1）→ v1.5.0（P2）→ v1.5.1～v1.6.0（P3）

---

# 附录

## A. 背景与痛点（简）

| 场景 | 任务管理器 | 根因 |
|------|------------|------|
| 开发 `pythonw run.py` | Python | 预期；关于页已提示 |
| 打包主进程 | 星期五 | M1 已修 |
| Agent 跑脚本 | FridayAgent | M1 已修 |
| ZIP 绿色包 | 手动解压 | M2 解决 |

成熟度自评：**5/10 → 目标 9/10**（进程/分发 3→9 靠 M1+M2+M3）

## B. 目标愿景（10/10）

1. 官网 **安装包** + 已签名（M2+M3）
2. 任务管理器 **星期五 / FridayAgent**（M1 ✅）
3. **卸载入口**（M2.5）
4. **诊断包** + 更新回滚（M4+M2.8）
5. UI **全状态有规格**（M5）
6. 长对话 **上下文智能**（M6.2）

## C. 明确不做

- 重写 Electron / Tauri（除非 M6 评估后 v2.0 决定）
- macOS / Linux 端口
- 云端账号 / 订阅计费
- 完全去掉 Python 运行时
- 全量多语言（保留中英骨架即可）
- Max 采样 / judge（M6.2 本期不做，见 TODOS）

## D. 应复用资产

| 资产 | 用途 |
|------|------|
| `DESIGN.md` + `web/styles.css` | M5 token 审计 |
| `scripts/version_info.py` | M1/M3 签名元数据 |
| `friday/update_installer.py` | M2.7/M2.8/M3.4/M4.5 |
| `friday/python_env.py` | M1.2 FridayAgent |
| `friday/brain.py` + `prefix_cache.py` | M6.2 压缩/rebuild |
| `friday/user_memory.py` + `plan.py` | M6.2 全局记忆与计划注入 |
| Playwright E2E | 每大任务结束回归 |

## E. 版本里程碑

| 版本 | 大任务 | 用户可感知 |
|------|--------|-----------|
| **1.3.0** | M1 + M2 | Friday.exe / Setup 安装包 / 更新回滚 |
| **1.3.2** | M3.3/4 + M4 + M5 | SHA256 校验、诊断包、设置重组、无障碍、测试版并行 |
| **1.3.x** | M3.1/2/5 | IV 签名、遥测 opt-in（待证书/产品决策） |
| **1.4.0** | M6.2 P0 | 上下文仪表、压缩前移 |
| **1.4.x** | M6.2 P1 | checkpoint 工作记忆 |
| **1.5.0** | M6.2 P2 | rebuild、Goal、会话 fork |
| **1.5.x～1.6.0** | M6.2 P3 | MEMORY、历史 FTS、Dream |
| **2.0** | M6.1 | 打包调研，视结论决定 |

## F. 设计评审记分卡

| 维度 | 基线 | 目标 | 对应子任务 |
|------|------|------|-----------|
| 信息架构 | 6/10 | 9/10 | M5.1 |
| 交互状态 | 5/10 | 9/10 | M5.2～M5.4 |
| 用户旅程 | 6/10 | 8/10 | M2 + M4.2 |
| 进程/分发 | 3/10 | 9/10 | M1 + M2 + M3 |
| a11y | 4/10 | 7/10 | M5.6 |
| 上下文智能 | 3/10 | 8/10 | M6.2 |

## G. 已拍板决策

| 决策 | 结论 |
|------|------|
| 主 exe | `Friday.exe` + 中文显示名 |
| Agent 子进程 | `FridayAgent.exe`（方案 A） |
| 安装器 | Inno Setup（M2） |
| 代码签名 | **IV 证书**（个人开发者，M3 前采购；有公司主体时改用 OV） |
| 官网 | **阶段 1：Vercel 页面 + Gitee Release 下载**（0 元 MVP）；**后续可升级** 阿里云 OSS/CDN 加速下载 + 自有域名/SEO |
| 架构迁移 | v2.0 再评估（M6.1） |
| 上下文/会话 | **A 渐进 + M6.2**（Goal/fork/FTS/Dream 纳入；Max defer） |

---

*计划结构：M1～M5 + M6.1 调研 + **M6.2 共 28 子任务**。详表见 `docs/context-session-plan.md`。*
