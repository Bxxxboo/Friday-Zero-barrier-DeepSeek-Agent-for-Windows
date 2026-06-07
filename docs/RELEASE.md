# 发布流程（Gitee + GitHub）

当前版本见 `friday/version.py`（须与 `scripts/version_info.py` 一致）。

## 一键发布（推荐）

需 [Git](https://git-scm.com/)、Gitee 私人令牌；GitHub 可选（`gh` 或 `GITHUB_TOKEN`）。

```powershell
$env:GITEE_TOKEN = '你的Gitee令牌'
# 可选：$env:GITHUB_TOKEN = 'ghp_...'
powershell -ExecutionPolicy Bypass -File scripts/publish-release.ps1 `
  -GitHubRepoName Friday-Zero-barrier-DeepSeek-Agent-for-Windows
```

步骤：

1. 提交并 push **GitHub（origin）** 与 **Gitee（gitee）**
2. 打包 `release/Friday-Windows.zip`
3. 创建/更新 **Gitee Release**（国内默认更新源）
4. 创建/更新 **GitHub Release**（备用）

## 仅同步代码（不发安装包）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-remotes.ps1 `
  -CommitMessage "chore: release v1.1.0" `
  -GitHubRepoName Friday-Zero-barrier-DeepSeek-Agent-for-Windows
```

## 更新公告

每次发版在 **`assets/changelog.json`** 的 `entries` **最前面**增加新版本条目（与 `CHANGELOG.md` 保持一致）。用户升级后会在应用内看到未读公告。

生成 Release 说明文本：

```powershell
powershell -File scripts/release-notes.ps1          # 当前版本
powershell -File scripts/release-notes.ps1 -All     # 完整日志
```

## 远端地址

| 远端 | 仓库 |
|------|------|
| `origin` | https://github.com/Bxxxboo/Friday-Zero-barrier-DeepSeek-Agent-for-Windows |
| `gitee` | https://gitee.com/Bxxxboo/friday |

## 打 tag（可选）

Release 脚本按 `v{version}` 创建 Release；若需显式 tag：

```powershell
git tag v1.1.0
git push origin v1.1.0
git push gitee v1.1.0
```
