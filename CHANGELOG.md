# 更新日志

版本说明与 `assets/changelog.json` 同步；应用内「更新公告」亦读取该文件。

## 1.3.3（2026-06-11）

**安全加固与设置修复**

### 安全

- **一键更新**：仅允许从 Gitee/GitHub/官网等信任域名下载；解压时校验路径，防止 Zip Slip
- **打开文件夹**：`/api/open-path` 白名单（工作区、`%AppData%\\Friday` 等），禁止任意路径
- **Token 暴露收缩**：首页不再内联 Token；桌面 WebView 启动 URL 去掉 `?token=`；WebSocket 首包鉴权
- **生图预览**：改用带鉴权的 blob URL，避免 Token 出现在地址栏
- **微信桥接**：扩展配置不再持久化明文 API Token
- **Agent 执行安全**：新增 `docs/AGENT-SAFETY.md`（Yolo 解锁、黑名单范围与已知限制）；PowerShell/Python 危险命令拦截与 bypass 回归测试

### 修复

- **视觉/生图设置**：切换服务商后新 Key 不再被凭据库中的旧值覆盖
- **设置测试与保存**：与 `load_settings` / `merge` 运行路径一致，避免「测试通过但重启丢失」
- **测试隔离**：`test_artifacts` 等用例默认使用临时 AppData，避免在侧边栏出现 pytest 残留的「画图」会话

### 改进

- 设置页 **一键更新** 进度条、轮询超时与错误文案
- 应用内更新 **SHA256** 校验与安装失败回滚链路加固

### 测试

- 新增/扩充：zip_safety、open_path_security、ws_auth、shell bypass、safety、category_profiles、credentials_store 等

---

## 1.3.2（2026-06-11）

**可靠性、设置体验与无障碍；测试版可与正式版并行**

### 新功能

- **崩溃本地记录**：未处理异常写入 `%APPDATA%/Friday/crashes/`，保留最近 30 份
- **导出诊断包**：设置 → 版本与诊断 → 一键 ZIP（版本、运行模式、日志尾部、系统信息、Gateway 状态，已脱敏）
- **健康检查扩展**：`/api/health` 含 WebView、Gateway、Python 环境子状态
- **日志轮转**：`friday.log` 默认 5MB × 14 份备份，启动清理超期日志
- **连续启动崩溃回滚**：更新后 3 次启动崩溃自动从 `Friday.bak/` 恢复
- **Release SHA256 清单**：发布附 `SHA256SUMS.txt`；应用内一键更新下载后校验哈希
- **设置导航 7 组**：入门 / 连接 / 自动化 / 扩展 / 微信 / 数据 / 关于
- **测试版（--dev）**：与正式版可同时运行（独立端口与窗口标题「星期五（测试版）」）

### 改进

- 对话列表、微信桥接、生成物存储等 **空状态 / 加载 / 错误** 文案与重试
- 状态栏与微信面板 **Gateway 连接状态**
- **DESIGN.md token 审计**一轮：补 `--touch-target`、`--text-secondary` 等，去除 indigo slop
- **无障碍基线**：设置页键盘 Tab/方向键、焦点环、44px 触屏目标、`prefers-reduced-motion`
- Gitee/GitHub Release 发布脚本与配额清理优化

### 测试

- 新增/扩充：crash_handler、diagnostics_bundle、health、release_hashes、update_rollback、status_bar、edition、instance_lock 等（505+ 用例）

---

## 1.3.1（2026-06-11）

**修复发布包与一键更新**

### 修复

- `Friday-Windows.zip` 同时含 **Setup 安装程序** 与 **Friday 程序目录**，兼容 1.2.x 应用内一键更新
- Gitee/GitHub Release 附带 `Friday-Update.zip`，1.3+ 应用内更新优先拉取更新包

### 改进

- 安装教程与官网下载说明：解压后运行 `Friday-Setup` 安装程序

---

## 1.3.0（2026-06-11）

**桌面进程身份、Windows 安装包与更新回滚**

### 新功能

- **主程序品牌化**：打包后主进程为 `Friday.exe`，任务管理器显示「星期五 - AI 电脑管家」
- **Agent 子进程**：`FridayAgent.exe` 运行脚本，减少裸 `python.exe` 暴露
- **Inno Setup 安装包**：`Friday-Setup-{version}.exe`，内置 Unblock、开始菜单/桌面快捷方式、简体中文向导；安装完成可选启动并自动置顶
- **更新前备份与失败回滚**：覆盖安装前备份 `Friday.bak`，启动自检失败可恢复上一版
- 设置页 **关于 → 运行模式**（开发/打包、主进程路径、任务管理器提示）

### 改进

- 自启、一键更新重启、安装后启动等路径统一指向 `Friday.exe`
- 生图设置页测试超时延长至 120 秒，慢速中转探测失败后可继续完整生图测试
- 微信扫码：备用浏览器链接改为手动打开，避免自动弹窗干扰

### 分发

- Release 同时附 **ZIP（绿色版）** 与 **Setup（推荐新用户）**
- 文档：`docs/INSTALL-LAYOUT.md` 说明安装目录与用户数据分离

### 测试

- 扩充 autostart、update_installer、update_rollback、runtime_info、python_env、image_gen 等回归

---

## 1.2.5（2026-06-10）

**生成物存储管理、微信扫码体验、E2E 与插件生态**

### 新功能

- **工作区生成物管理**（`artifacts`）：登记 scratch/session/delivered 生命周期、软删除 trash、TTL 自动回收；设置页可查看占用并手动 GC
- **单工具快路径**（`fast_finish`）：列出插件/规则等只读查询成功后直接返回，跳过大模型总结轮
- **Playwright E2E** 冒烟（5 用例）与 `scripts/qa_deep_smoke.py` 深度验收脚本
- 内置 **SciPilot 科研配图** 插件推荐与本地 skill 包；恢复 Karpathy 编码准则 catalog 项
- 前端启动时轮询 `/health` 直至 `status === "ok"`，避免后端未就绪误报

### 改进

- **微信扫码登录**：优先扫描终端二维码；检测到链接仅缓存备用 URL，不再自动弹出浏览器（需时在设置页点「浏览器打开扫码页」）
- 规则/插件系统增强：GitHub skill 安装格式说明、扩展 catalog 与 `list_plugin_catalog` 工具
- Windows 安装包统一命名为 `Friday-Windows-{version}.zip`；发布/打包脚本与 release notes 流程对齐

### 修复

- `POST /api/sessions/{id}/activate` 返回类型错误导致 500
- 插件 catalog 推荐列表为空时的回归

### 测试

- 新增/扩充：artifacts、fast_finish、E2E、plugin catalog、sessions activate、微信 login_runner 等

---

## 1.2.4（2026-06-10）

**一键更新、报错提示优化、微信审批与界面焕新**

### 新功能

- **Windows 打包版一键更新**：设置页「一键更新并重启」— 自动下载 Release、解压覆盖安装目录并重启（无需手动解压 zip）
- 更新失败展示**具体原因与修复建议**（网络/zip 损坏/权限/磁盘等）
- **审批说明 LLM 化**（`approval_narration`）：先弹模板文案，后台用大模型生成更自然的操作说明并刷新桌面/微信
- 前端加载 `errorHints.js`，设置页 API 测试统一展示 `message + hint`
- 界面动效（GSAP `motion.js`）：启动/退出、窗口最大化过渡
- 新应用图标（奶油色 squircle + 金色「五」），启动页与主界面 mark 一致
- Windows 11 风格**圆角窗口**与 DWM 边框色同步（`win32_chrome`）

### 改进

- **报错分类全面优化**：生图/视觉/大模型 401 不再误报「本地认证已过期」；按服务给出正确 Key 指引
- 设置页测试接口（LLM/视觉/生图）返回结构化 `hint`；后端 `build_test_response` 统一格式化
- 微信 Gateway：`hooks.timeoutMs` 上限对齐 OpenClaw（600000），修复一键配置启动超时
- 微信审批：600s 内重复「同意」去重；误触时轻量提示而非重复完整回复
- 微信 setup/bridge 审批文案走统一 facade；聊天支持 `approval_summary_update` 事件刷新
- Python 虚拟环境面板：修复 `refreshPythonEnvStatus` 未绑定导致一直「加载中」
- Python 环境状态查询不再触发 winget/下载，响应更快
- 快捷方式脚本：生成新图标并复制到 `%APPDATA%\\Friday\\friday.ico`，避免 Windows 图标缓存指向旧路径
- 项目更名为 **Friday-WeChat-Windows-AI-Butler**，双端 README/更新源说明同步

### 修复

- 生图测试误显示「本地认证已过期」（实为 API Key 问题）
- 设置 → Agent → Python 环境永久「加载中…」
- 微信桥接 Gateway 启动超时（其他设备一键配置失败）
- 用户回复「同意」后重复发送「当前没有待审批的操作」
- 审批弹窗说明过于笼统，无法看出具体要执行什么

### 测试

- 新增/扩充：`error_hints`、`update_installer`、微信 bridge/setup  inbound、审批 narration 等测试

---

## 1.2.3（2026-06-10）

**微信桥接加固、文件安全、状态栏检测与 API 稳定性**

### 新功能

- 内置「文件删改安全」准则（skill + 规则 + 插件）：删/改/移须专用工具并审批，禁止 Python/PowerShell 绕过
- `run_python` 静态安全分析（`python_code_safety`）：拦截改 AppData/星期五配置；删除/覆盖每次审批，工作区新建同轮确认一次
- API 凭据独立存储（`credentials_store`），与 settings 分离，换机/更新更稳
- 开机 API 检测与设置页「测试连接」统一逻辑（`startup-tests` + `test_*_service`）
- 状态栏三项（API / 视觉 / 生图）独立并行检测，谁先完成谁先更新
- 微信登录运行器（`login_runner`）与资料同步（`profile`），Gateway 插件单 hook 去重
- 审批说明文案外置（`approval_descriptions`），工具审批弹窗更清晰
- `server` 拆出 `status_bar`、`weixin_routes`；设置页拆 weixin / python_env 面板脚本
- 打包脚本 `pack-windows.cmd` / `pack-windows.ps1`

### 改进

- 微信桥接：去掉 `inbound_claim` 双转发；`forwardToFridayOnce` 去重；`before_dispatch` 620s 超时防慢回复
- 微信问候快路径（你好等）在 API 就绪时直接回复，减少空等
- 状态栏开机默认「检测中」黄点，不再先显示关/离线；检测完成前轮询不覆盖结果
- 测试连接成功不再清空其他服务状态缓存，避免生图测完后视觉/API 被重复检测
- API 瞬态超时/限流不误标永久离线；`brain` 对瞬态失败自动重试
- 生图状态栏：有成功缓存时跳过重复 live probe；快速探测不覆盖成功缓存
- 交互规则：允许正常闲聊，不必强行拉回电脑管理话题
- Python Agent 环境：修复误绑开发目录 venv、跨机重建与设置页后台安装进度
- 可移植性/配置包：credentials 合并、插件 manifest 与内置 file-safety 一并迁移
- Yolo 模式下 `run_python` / PowerShell 仍须每次审批
- 扩展管理 UI 与 onboarding 流程优化

### 修复

- 用着用着误报「无法连接 API」、设置里测试却正常（响应超时与缓存污染）
- 状态栏 API/视觉/生图与设置页测试结果不一致
- `run_python` 未审批即可删改 `operations.json` 等应用数据
- 微信英文错答、重复回复、审批/通道与 Gateway 插件 inflight 问题
- 生图离线误报、设置测试通过但底部仍显示离线
- `category_profiles` / `llm_profiles` 切换生图与 API 快照恢复
- registry 工具导入与若干微信/setup 边界用例

### 测试

- 新增/扩充：`api_connect`、`status_bar`、`startup_tests`、`python_code_safety`、`credentials_store`、weixin bridge/login/profile/node_runtime 等测试

---

## 1.2.2（2026-06-09）

**微信桥接、设置持久化与生图测试修复**

### 改进

- 状态栏常驻显示缓存命中百分比
- 微信「我的微信」会话启动预建与 WebSocket 实时刷新侧边栏
- 设置页 Python 环境 / 生图测试改为后台执行，不再卡死整个后端

### 修复

- 更新后 API Key 丢失：自动迁移 Friday-Test 与 `.fernet_key` 配对
- 生图设置测试超时无反馈、中转站探测过久
- Agent Python 环境误绑开发目录 venv 导致更新后需重装

---

## 1.2.1（2026-06-09）

**Plan/Todo 完整版与 API 连接修复**

### 改进

- Plan / 待办面板恢复 1.2.1 完整 UI：拖拽排序、待办队列、从计划生成、进度徽章
- 长任务待办自动勾选、计划 Markdown 同步、对话中实时刷新面板
- 设置页空 base_url 自动回退 DeepSeek 默认地址，修复 API 测试 Connection error

### 修复

- 源码回退后待办面板与版本号与安装包不一致的问题

---

## 1.2.0（2026-06-08）

**缓存优化、变更审查、Plan/MCP 与自启完善**

### 新功能

- DeepSeek 前缀缓存：冻结 system/tools、append-only 上下文折叠、状态栏 cache 命中率
- Agent 写文件后在聊天区展示 diff 摘要，支持在资源管理器中打开
- 会话 Plan / Todo 面板与 `update_session_plan` / `update_session_todos` 工具
- MCP stdio 客户端：设置 → 扩展 → MCP，配置随配置包 portable 迁移
- OpenClaw Gateway 开机自启开关（设置 → 微信端 AI）
- 星期五本体开机自启（设置 → 启动）

### 改进

- 工具输出智能压缩、重复工具循环检测、前缀漂移日志
- 配置包导出/导入包含 `mcp_servers.json`
- 内置技能「制定计划」

## 1.1.3（2026-06-08）

**可移植性迁移、对话体验与 UI 抛光**

### 新功能

- 设置 → 日志：配置包导出/导入（zip），换机迁移设置、技能、规则、插件与加密密钥
- 可移植性自检：工作区、API Key 加密、插件 manifest、Agent Python 环境
- 助手回复支持一键复制与引用到输入框
- workspace 支持 `~/`、`%VAR%`、`auto`；settings 自动 schema 迁移
- 安全设置新增「只读访问桌面/文档/下载等用户文件夹」

### 改进

- 插件 manifest 磁盘保留 `{plugin_dir}`，运行时替换；启动一次性迁移旧绝对路径
- 会话生图路径相对化，整夹迁移后历史图片仍可显示
- PowerShell / Python 子进程 UTF-8 输出链路补全
- 无效 workspace、生图目录、加密密钥未配对时启动自愈并提示
- UI 抛光：历史抽屉避让标题栏、Composer 停止/发送并排、复制/引用置于回复末尾
- 启动加速：路径/插件 manifest 迁移完成后跳过重复全量扫描

### 修复

- 修复配置包导入缺少 python-multipart 导致后端无法启动、应用打不开
- 修复 workspace 指向其他用户或无效盘符时无法使用
- Agent Python 虚拟环境跨机拷贝后失效检测与重建引导

---

## 1.1.2（2026-06-07）

**Win10 零门槛安装：运行组件自动补齐**

### 新功能

- 首次启动自动检测并安装 WebView2、VC++ 运行库（Win10 白屏/缺 DLL 常见修复）
- 新增「首次安装.ps1」：一键解除锁定、创建快捷方式并启动
- Agent Python 环境支持自动 winget / 便携 Python 下载，无需手动装 Python
- 微信端 AI 一条龙：自动安装 Node/OpenClaw、扫码登录、长超时与桥接修复

### 改进

- 安装包打包阶段自动 Unblock，减少 Zone.Identifier 导致的 pythonnet 错误
- 安装教程更新为零门槛 3 步流程

---

## 1.1.1（2026-06-07）

**打包修复：跨机运行与 API 测试**

### 修复

- 修复其他电脑运行 exe 时 pythonnet / Python.Runtime 初始化失败
- 安装包目录改为英文 `Friday`，避免中文路径导致 DLL 加载失败
- 修复首次向导测试 API 时误报「网络错误」
- 打包版补充 HTTPS 证书链，修复 DeepSeek API 测试连接失败
- 修复 Gitee Release 名称中文乱码

### 改进

- 安装教程补充 .NET / WebView2 / API 测试排错说明

---

## 1.1.0（2026-06-07）

**生图持久化、桌面体验与更新公告**

### 新功能

- 生图结果写入会话历史，重新打开对话仍可查看已生成图片
- 内置更新公告：启动时展示未读版本说明，设置页可查看完整更新历史
- 微信端 AI 桥接向导（OpenClaw 一键配置）

### 改进

- 桌面窗口启动流程优化，减少黑屏闪烁
- Win11 风格无边框标题栏，去除最小化按钮周围黑色焦点框
- 生图 API 支持 OpenAI 兼容中转与火山方舟，可配置备用端点

### 修复

- 修复会话刷新后生图附件丢失的问题
- 修复微信 Bot User-Agent 版本号未随应用更新同步的问题

---

## 1.0.4（2026-05-01）

**稳定版维护**

### 改进

- 更新检查优先使用 Gitee Releases（国内免 VPN）
- 设置页安全策略与定时任务体验优化
