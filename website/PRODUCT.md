# 星期五 — 官网文案事实表

Agent 写 `index.html` 时只陈述本文档与 changelog 已确认的内容。

## 产品定位

- 名称：**星期五**（Friday）
- 类型：Windows 桌面 AI 助手 / 电脑管家
- 平台：Windows 10 / 11，64 位；界面基于 WebView2
- 分发：Gitee Release 安装包 ZIP（内含 Setup）；官网 https://fridayaiagent.vercel.app

## 核心能力

- **自然语言任务**：用户描述目标，Agent 规划步骤并执行
- **本机执行**：文件整理、目录操作、系统状态检查、文档生成（Word/PPT 等）、截图识图、从官网下载软件等；工具集 28+（以代码库 agent tools 为准）
- **运行模式**：Ask（只读）、Agent（需确认后改文件）、Yolo 等；危险操作需用户确认
- **数据位置**：设置与会话保存在 `%APPDATA%\Friday\`，不依赖云账号绑定

## 微信集成

- 手机微信可向家中 Windows 下发任务
- 执行在本机完成；进度与结果回到微信
- 删改类操作需在聊天中审批

## 可配置扩展

- 多服务商 API：对话、推理、视觉、生图（DeepSeek、火山方舟、小米 MiMo 等）
- 技能：`/` 选择技能包；`Ctrl+V` 粘贴截图问视觉模型
- 生图 API、GitHub 技能/规则扩展（设置 → 扩展）

## 系统要求

- Windows 10 / 11（64 位）
- Microsoft WebView2 运行时
- 联网 + 至少一个对话 API Key
- Agent Python 脚本：本机 Python 3.11+（可选）

## 下载说明

- 官网提供**安装包 ZIP**，解压后运行 `Friday-Setup-{版本}.exe` 安装
- 应用内更新使用 `Friday-Update-{版本}.zip`（便携目录）
