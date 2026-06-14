"""应用版本号 —— 与 PyInstaller version_info 保持一致。"""

__version__ = "1.4.1"
__dev_version__ = "1.4.1-dev"
__version_tuple__ = (1, 4, 1, 0)


def release_zip_name(version: str | None = None) -> str:
    """官网/手动下载 ZIP（内含 Setup 安装程序），与 scripts/make-release.ps1 一致。"""
    v = (version or __version__).strip()
    return f"Friday-Windows-{v}.zip"


def release_update_zip_name(version: str | None = None) -> str:
    """应用内一键更新 ZIP（便携 Friday 目录），与 scripts/make-release.ps1 一致。"""
    v = (version or __version__).strip()
    return f"Friday-Update-{v}.zip"


def release_setup_name(version: str | None = None) -> str:
    """Windows Inno Setup 安装包文件名，与 installer/friday.iss 一致。"""
    v = (version or __version__).strip()
    return f"Friday-Setup-{v}.exe"

# GitHub Releases（备用，国内常需 VPN）
GITHUB_REPO = "Bxxxboo/Friday-WeChat-Windows-AI-Butler"
GITHUB_HOME = f"https://github.com/{GITHUB_REPO}"

# Gitee Releases（默认更新源，国内可直连）。环境变量 FRIDAY_GITEE_REPO 可覆盖。
GITEE_REPO = "Bxxxboo/friday"
GITEE_HOME = f"https://gitee.com/{GITEE_REPO}"

# 官网（Vercel，海外）。部署后填 production URL；空则应用内仍链 Gitee Releases。
WEBSITE_HOME = "https://fridayaiagent.vercel.app"

# Gitee Pages（国内镜像，无需 VPN）。scripts/deploy-gitee-pages.ps1 部署。
GITEE_PAGES_HOME = "https://bxxxboo.gitee.io/friday"
