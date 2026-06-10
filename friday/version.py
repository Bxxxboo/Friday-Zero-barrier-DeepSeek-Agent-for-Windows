"""应用版本号 —— 与 PyInstaller version_info 保持一致。"""

__version__ = "1.2.5"
__version_tuple__ = (1, 2, 5, 0)


def release_zip_name(version: str | None = None) -> str:
    """Windows 安装包文件名，与 scripts/make-release.ps1 一致。"""
    v = (version or __version__).strip()
    return f"Friday-Windows-{v}.zip"

# GitHub Releases（备用，国内常需 VPN）
GITHUB_REPO = "Bxxxboo/Friday-WeChat-Windows-AI-Butler"
GITHUB_HOME = f"https://github.com/{GITHUB_REPO}"

# Gitee Releases（默认更新源，国内可直连）。环境变量 FRIDAY_GITEE_REPO 可覆盖。
GITEE_REPO = "Bxxxboo/friday"
GITEE_HOME = f"https://gitee.com/{GITEE_REPO}"
