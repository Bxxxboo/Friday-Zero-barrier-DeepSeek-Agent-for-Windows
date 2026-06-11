# 星期五 (Friday) 商业级成熟化 — 长期计划

> 版本基准：v1.3.0（M1+M2 已发版）；M2.9 官网代码已就绪，待 Vercel 部署  
> 更新日期：2026-06-11  
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
| **M2** 分发与安装 | v1.3.0 | ✅ 9/9 | 部署 Vercel（见 `docs/WEBSITE.md`） |
| M3 信任与安全 | v1.4.x | 未开始 | 依赖 M2；**个人开发者采购 IV 证书**（见 M3.1） |
| M4 可靠性与可观测 | v1.5.0 | 未开始 | 依赖 M2 备份/回滚基础 |
| M5 产品体验抛光 | v1.6.0 | 未开始 | 可与 M4 后期并行 |
| M6 架构调研 | v2.0 | 未开始 | 不阻塞 M1～M5 |

---

## 路线图总览

| 大任务 | 版本 | 主题 | 子任务数 | 周期（估） |
|--------|------|------|----------|-----------|
| **M1** | v1.3.0 | 桌面进程身份 | 5 | ✅ 基本完成 |
| **M2** | v1.3.0 | 分发与安装体验 | 9 | ✅ 已发（含 Setup） |
| **M3** | v1.3.x | 信任与安全（签名） | 5 | 4～6 周 |
| **M4** | v1.5.0 | 可靠性与可观测 | 5 | 3～4 周 |
| **M5** | v1.6.0 | 产品体验抛光 | 6 | 4～6 周 |
| **M6** | v2.0 | 架构演进（调研） | 1 | 按需 |

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

**M2 人工验收清单（2026-06-11，安装包已就绪）：**

产物：`release/Friday-Setup-1.2.5.exe`（含安装后 `--install-launch` 置顶修复 + `Friday.exe`）

```powershell
# 重新打包含最新 dist（已执行过一次，需要时再跑）
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
powershell -ExecutionPolicy Bypass -File scripts/build-installer.ps1
```

- [ ] 干净目录安装（默认 `%LOCALAPPDATA%\Programs\Friday\`），安装结束勾选「启动星期五」→ 窗口自动置顶到前台
- [ ] 双击 `Friday.exe` 无 SmartScreen「已阻止」类提示（Unblock 已内嵌）
- [ ] 开始菜单 / 可选桌面快捷方式可启动
- [ ] 卸载后程序目录消失，`%APPDATA%\Friday\` 用户数据仍在
- [ ] 安装向导为简体中文（覆盖安装后生效）

v1.3.0 Release 已含 ZIP + Setup；人工验收项可继续补测。

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

- [ ] **工作量：** 0.5 天  
- **内容：** 每个 Release 附 `SHA256SUMS.txt` 或 Gitee Release 说明内嵌哈希  
- **涉及文件：** `scripts/make-release.ps1`, `scripts/publish_gitee_release.py`  
- **验证：** Release 页可核对 ZIP/Setup 哈希

### M3.4 更新下载校验

- [ ] **工作量：** 1 天  
- **内容：** `update_installer.py` 下载后校验 SHA256，不匹配则拒绝安装  
- **涉及文件：** `friday/update_installer.py`, `tests/api/test_update_installer.py`  
- **验证：** pytest + 故意篡改包应失败并提示

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

- [ ] **工作量：** 1～2 天  
- **内容：** 未处理异常 → `%APPDATA%/Friday/crashes/`；含时间、版本、堆栈  
- **涉及文件：** 新建 `friday/crash_handler.py`；`run.py` / `desktop.py` 最早注册  
- **验证：** 故意 `raise` 一次 → `crashes/` 下有新文件

### M4.2 设置页「导出诊断包」

- [ ] **工作量：** 1 天  
- **内容：** ZIP：版本、运行模式、日志尾部、系统信息、Gateway 状态（脱敏）  
- **涉及文件：** `friday/server.py`, `web/settings.js`, `web/index.html`  
- **验证：** 点击导出 → 得到可打开的 zip；无 API Key 明文

### M4.3 健康检查扩展

- [ ] **工作量：** 0.5～1 天  
- **内容：** `/api/health` 增加 WebView、Gateway、Python env 子状态  
- **涉及文件：** `friday/server.py`；相关 status 模块  
- **验证：**
  ```powershell
  curl http://127.0.0.1:PORT/api/health
  # JSON 含子服务 ok/degraded 字段
  ```

### M4.4 日志轮转

- [ ] **工作量：** 1 天  
- **内容：** `friday.log` 大小上限 + 保留 N 天；启动时清理过期  
- **涉及文件：** `friday/logging_config.py`  
- **验证：** 配置小阈值后跑一段时间 → 出现 `.log.1` 或归档删除

### M4.5 启动崩溃触发回滚

- [ ] **工作量：** 1 天  
- **内容：** 连续 3 次启动崩溃 → 自动从 `Friday.bak/` 恢复（衔接 M2.8）  
- **涉及文件：** `friday/update_installer.py`, 启动入口  
- **验证：** 模拟坏包连续启动 → 自动回滚并提示

---

## M5 — 产品体验抛光（v1.6.0）

**用户可感知：** 设置更好找；空状态/加载/error 有温度；无障碍基线达标。

**依赖：** 无硬依赖；建议 M4 后再做大改 UI，减少返工

### M5.1 设置导航重组（7 组）

- [ ] **工作量：** 2 天  
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

### M5.2 交互状态：对话列表 empty

- [ ] **工作量：** 0.5 天  
- **涉及文件：** `web/chat.js`, `web/styles.css`  
- **验证：** 无会话时显示引导文案 + 主操作（新建对话）

### M5.3 交互状态：Gateway / 微信 loading & error

- [ ] **工作量：** 1 天  
- **涉及文件：** `web/weixin.js`, `web/statusbar.js`  
- **验证：** 断网 / Gateway 未就绪时有明确状态，非空白或裸错误

### M5.4 交互状态：生成物 empty

- [ ] **工作量：** 0.5 天  
- **涉及文件：** 生成物相关 `web/*.js`  
- **验证：** 无生成物时显示说明与跳转设置

### M5.5 DESIGN.md token 审计（一轮）

- [ ] **工作量：** 1 天  
- **内容：** 对照 `DESIGN.md` 检查 `web/styles.css` 硬编码色/间距；修明显偏离  
- **验证：** 审计清单存档；无新增 AI slop 模式（紫渐变、三列图标卡片等）

### M5.6 无障碍基线

- [ ] **工作量：** 1～2 天  
- **内容：** 设置页键盘 Tab 顺序；对比度 ≥ 4.5:1；触屏目标 ≥ 44px；`prefers-reduced-motion`  
- **涉及文件：** `web/styles.css`, 各 panel HTML  
- **验证：** 键盘可完成保存设置；axe 或手工抽查 3 个主流程

---

## M6 — 架构演进调研（v2.0，可选）

**不阻塞 M1～M5。** 产出文档即可，不写生产代码。

### M6.1 打包方案评估文档

- [ ] **工作量：** 1～2 天  
- **内容：** PyInstaller onedir / onefile / Nuitka / Tauri 对比：体积、启动、构建、Agent Python 兼容性  
- **涉及文件：** 新建 `docs/architecture-v2-options.md`  
- **验证：** 文档含推荐结论与「v2.0 前不做什么」

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

## C. 明确不做

- 重写 Electron / Tauri（除非 M6 评估后 v2.0 决定）
- macOS / Linux 端口
- 云端账号 / 订阅计费
- 完全去掉 Python 运行时
- 全量多语言（保留中英骨架即可）

## D. 应复用资产

| 资产 | 用途 |
|------|------|
| `DESIGN.md` + `web/styles.css` | M5 token 审计 |
| `scripts/version_info.py` | M1/M3 签名元数据 |
| `friday/update_installer.py` | M2.7/M2.8/M3.4/M4.5 |
| `friday/python_env.py` | M1.2 FridayAgent |
| Playwright E2E | 每大任务结束回归 |

## E. 版本里程碑

| 版本 | 大任务 | 用户可感知 |
|------|--------|-----------|
| **1.3.0** | M1 + M2 | Friday.exe / Setup 安装包 / 更新回滚 |
| **1.3.x** | M3 | IV 签名、SmartScreen 友好 |
| **1.5.0** | M4 | 崩溃可查、诊断包、回滚 |
| **1.6.0** | M5 | 设置清晰、空状态温暖 |
| **2.0** | M6 | 视调研决定 |

## F. 设计评审记分卡

| 维度 | 基线 | 目标 | 对应子任务 |
|------|------|------|-----------|
| 信息架构 | 6/10 | 9/10 | M5.1 |
| 交互状态 | 5/10 | 9/10 | M5.2～M5.4 |
| 用户旅程 | 6/10 | 8/10 | M2 + M4.2 |
| 进程/分发 | 3/10 | 9/10 | M1 + M2 + M3 |
| a11y | 4/10 | 7/10 | M5.6 |

## G. 已拍板决策

| 决策 | 结论 |
|------|------|
| 主 exe | `Friday.exe` + 中文显示名 |
| Agent 子进程 | `FridayAgent.exe`（方案 A） |
| 安装器 | Inno Setup（M2） |
| 代码签名 | **IV 证书**（个人开发者，M3 前采购；有公司主体时改用 OV） |
| 官网 | **阶段 1：Vercel 页面 + Gitee Release 下载**（0 元 MVP）；**后续可升级** 阿里云 OSS/CDN 加速下载 + 自有域名/SEO |
| 架构迁移 | v2.0 再评估（M6） |

---

*计划结构：6 个大任务（M1～M6），共 31 个子任务。随实现进度更新勾选与「当前进度」表。*
