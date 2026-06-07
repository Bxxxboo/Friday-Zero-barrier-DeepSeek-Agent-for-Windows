# 微信 ↔ 星期五桥接

将 OpenClaw 微信渠道的**文字消息**转发到本地「星期五」执行，结果通过微信文字回复；需要审批的操作会在微信里询问「同意 / 拒绝」。

## 前提

1. 已安装并登录 OpenClaw 微信插件（`openclaw-weixin`）
2. **星期五桌面版正在运行**（会写入 `%APPDATA%/Friday/weixin-bridge.json`）
3. 星期五设置里已配置 DeepSeek API Key

## 安装桥接插件

在项目根目录执行：

```powershell
openclaw plugins install "e:\cursor\workspace\星期五\extensions\friday-weixin-bridge"
openclaw config set plugins.entries.friday-weixin-bridge.enabled true
openclaw gateway restart
```

或使用脚本：

```powershell
.\scripts\install-friday-weixin-bridge.ps1
```

## 使用

1. 启动星期五：`.\.venv\Scripts\python run.py`
2. 用手机给已绑定的微信 Bot 发文字，例如：「列出桌面文件」
3. 若涉及写入/执行类操作，星期五会在微信发审批消息，回复 **同意** 或 **拒绝** 即可

## 故障排查

- 回复「星期五未运行…」→ 先打开桌面版星期五
- 回复「微信通道未登录」→ `openclaw channels login --channel openclaw-weixin`
- 检查桥接状态：星期五运行中访问 `GET /api/weixin/status`（需 API Token）
