# 星期五官网（M2.9）

阶段 1：**Vercel 托管静态页 + Gitee Release 直链下载**。零云存储成本；下载速度取决于 Gitee（常见约 0.5～2 分钟 / 64MB）。

**国内镜像**：`https://bxxxboo.gitee.io/friday`（Gitee Pages，无需 VPN）。部署脚本见下文。

## 目录

| 路径 | 说明 |
|------|------|
| `website/index.html` | 落地页 |
| `website/styles.css` | 样式（对齐 `DESIGN.md`） |
| `website/main.js` | 主题切换、读取 `download.json` / `changelog.json` |
| `website/download.json` | 当前版本与 Gitee 下载直链（发版后更新） |
| `website/changelog.json` | 从 `assets/changelog.json` 同步的副本 |
| `website/vercel.json` | Vercel 静态站配置 |
| `scripts/sync-website-download.ps1` | 从 `friday/version.py` 同步下载链接 |

## 本地预览

```powershell
cd E:\Friday\website
python -m http.server 8787
```

浏览器打开 http://127.0.0.1:8787/

## Vercel 部署（首次）

1. 登录 [Vercel](https://vercel.com)，Import 本仓库（GitHub 镜像 `Friday-WeChat-Windows-AI-Butler`）。
2. **Root Directory** 设为 `website`。
3. Framework Preset：**Other**（纯静态，无需 Build Command）。
4. Deploy。记下 Production URL，例如 `https://friday-xxx.vercel.app`。
5. （可选）在 `friday/version.py` 填写 `WEBSITE_HOME = "https://你的域名"`，应用设置页「更新源」会链到官网。

自定义域名：Vercel 项目 → Settings → Domains（备案域名可后续再接）。

## 发版后更新官网

**推荐**：用户明确说发版并给出版本号时，一条命令完成 bump + 双端 Release + 官网部署（见 `.cursor/rules/publish-release.mdc`）：

```powershell
scripts\publish-full-release.cmd -Version 1.3.2
```

手动分步（与 `publish-release` 同版本发 Gitee Release 后）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-website-download.ps1
git add website/download.json website/changelog.json
git commit -m "chore: sync website download links for vX.Y.Z"
git push origin main
git push gitee main
cd website
npx vercel deploy --prod --yes
```

仅推 Gitee、未跑 `publish-full-release` 时，Vercel 不会自动更新，须手动 `vercel deploy`。

## Gitee Pages 国内镜像

| 项 | 值 |
|----|-----|
| 访问地址 | `https://bxxxboo.gitee.io/friday` |
| 源码分支 | `pages`（仅含 `website/` 静态文件，由脚本推送） |
| 常量 | `friday/version.py` → `GITEE_PAGES_HOME` |

### 首次开通（一次性）

1. 完成 [Gitee 实名认证](https://gitee.com/profile/real_name)
2. 打开 `https://gitee.com/Bxxxboo/friday/pages`
3. 部署分支选 **`pages`**，目录留空（站点在分支根目录）
4. 点击 **启动** / **更新**

### 日常部署

发版脚本已包含 Gitee Pages（`publish-full-release.ps1` 在 Vercel 之后执行）。单独更新官网：

```powershell
$env:GITEE_TOKEN='令牌'
scripts\deploy-gitee-pages.cmd
```

步骤：将 `website/` 推送到 Gitee 的 `pages` 分支 → 调用 API 触发 Pages 构建。

Gitee 免费版 Pages **不会**在 push 后自动构建，须脚本触发或网页点「更新」。

## 下载 URL 约定

```
https://gitee.com/Bxxxboo/friday/releases/download/v{version}/Friday-Setup-{version}.exe
https://gitee.com/Bxxxboo/friday/releases/download/v{version}/Friday-Windows-{version}.zip
```

`sync-website-download.ps1` 按 `friday/version.py` 的 `__version__` 生成上述链接。

## 阶段 1 明确不做

- 阿里云 OSS / CDN 上传
- ICP 备案与自有域名（可后续升级）
- 应用内一键更新改 CDN（仍走 Gitee Releases API）

## 后续升级（非阻塞）

| 需求 | 做法 |
|------|------|
| 下载加速 | OSS + CDN；官网按钮改 CDN URL |
| SEO | 自有域名 + 站长工具 |
| 国内页面加速 | 备案后静态资源迁国内 CDN |
