# `scripts/` 维护脚本

开发/构建用，**不**打入用户 exe。`.cmd` 多为对同名 `.ps1` 的薄包装，便于双击或文档引用。

## 分类

### 开发与诊断

| 脚本 | 用途 |
|------|------|
| `run-dev.cmd` / `run-dev.vbs` | 无黑框启动 `run.py` |
| `diagnose_api.py` | API 连通性诊断 |
| `configure-mimo.py` | Mimo 模型配置辅助 |
| `link-cursor-dev.ps1` | `.cursor` → `.friday` 联接 |

### 构建

| 脚本 | 用途 |
|------|------|
| `build.ps1` | PyInstaller 一键打包 |
| `pack-windows.ps1` / `pack-windows.cmd` | **本地一键**：编译 + 打 `release/Friday-Windows-{版本}.zip`（换机试用） |
| `friday-dist.ps1` | 分发目录整理 |
| `create_icon.py` | 生成应用图标 |
| `clean.ps1` | 清理 build/dist/__pycache__ |
| `pyi_rth_*.py` | PyInstaller runtime hooks |
| `make-release.ps1` | 组装 `release/Friday-Windows-{版本}.zip` |

### 版本与发布

| 脚本 | 用途 |
|------|------|
| `bump-version.ps1` | 递增 `friday/version.py`（`__version__` + `__dev_version__`）+ `version_info.py` |
| `sync-remotes.ps1` | push GitHub + Gitee |
| `publish-release.ps1` | bump + 双端 push + 双端 Release |
| `publish-*-release.ps1` / `publish_*_release.py` | 单平台 Release |
| `release-notes.ps1` / `render_release_notes.py` | 从 changelog 生成说明 |
| `update-repo-profile.ps1` / `update_repo_profile.py` | 更新 GitHub/Gitee 仓库简介与主页 |
| `version_info.py` | PyInstaller 版本元数据 |

### 安装与自启

| 脚本 | 用途 |
|------|------|
| `setup-python-env.ps1` | 工作区 Agent Python 环境 |
| `install-friday-autostart.ps1` | 星期五登录自启 |
| `install-openclaw-autostart.ps1` | Gateway 自启 |
| `install-friday-weixin-bridge.ps1` | 微信桥插件安装 |

### 微信 / OpenClaw

| 脚本 | 用途 |
|------|------|
| `start-openclaw-gateway-silent.py` | 静默启动 Gateway |
| `openclaw-gateway-hidden.vbs` | 隐藏窗口启动 |
| `send-weixin-file.py` | 发送文件到微信（调试） |

### Git 源站（可选）

`setup-source-git.ps1`, `push-gitee-source.ps1`, `serve-source-repo.ps1`

## 常用命令

```powershell
# 开发
scripts\run-dev.cmd

# 打包
powershell -File scripts\build.ps1

# 发布（需 GITEE_TOKEN）
powershell -File scripts\publish-release.ps1 -GitHubRepoName Friday-WeChat-Windows-AI-Butler
```

用户侧快捷方式脚本在 `release/`，不在此目录。
