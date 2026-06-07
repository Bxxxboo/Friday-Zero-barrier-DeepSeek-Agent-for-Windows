# 生图功能说明

星期五内置 AI 生图能力，通过 OpenAI 兼容接口调用第三方中转（如 zhima.world）或火山方舟（Ark）。生图结果保存到工作区，并在聊天中展示缩略图预览。

## 功能概览

| 能力 | 说明 |
|------|------|
| 工具名 | `generate_image` |
| 审批 | 每次生图均需用户确认（不受「本对话同意一次」影响） |
| 保存位置 | `{工作区}/生成的图片/`（可在设置中自定义目录） |
| 会话持久化 | 生图路径写入服务端 `display_messages`，切换/重开会话后仍可预览 |
| 预览 | 聊天内加载压缩缩略图；点击可在浏览器中查看原图 |

## 设置页配置

路径：**设置 → 生图**

| 字段 | 说明 |
|------|------|
| 启用生图 | 总开关 |
| 提供商 | `openai_compat`（OpenAI 兼容）或 `ark` |
| API Key | 加密保存在 `%APPDATA%/Friday/settings.json` |
| Base URL | 默认 `https://next.zhima.world` |
| 备用 URL | 逗号分隔，主端点失败时依次尝试 |
| 模型 | 如 `image2`（以服务商文档为准） |
| 默认尺寸 | 如 `1024x1024` |
| 保存目录 | 留空则使用工作区下 `生成的图片/` |

保存后可用 **测试连接** 验证 Key、模型与端点是否可用（会发起一次轻量请求）。

## 使用方式

1. 在设置中启用并配置生图 API。
2. 在对话中说「帮我画一张…」或使用内置技能 **生成图片**。
3. 弹出审批卡片，确认后开始生图（通常 40～60 秒）。
4. 完成后助手回复下方出现缩略图；点击可查看大图。

## 会话与持久化

- 后端在 `save_agent_state` 时从 agent 历史中解析 `generate_image` 工具结果。
- 展示消息格式（`display_messages`）示例：

```json
{
  "role": "assistant",
  "content": "图片已生成。",
  "generated_images": [{ "path": "D:/工作区/生成的图片/grassland.png" }]
}
```

- 前端通过 `GET /api/sessions/{id}` 加载历史时读取 `generated_images`，渲染为聊天缩略图。
- 旧会话无需迁移：读取详情时会从 `agent_messages` 自动重建带生图路径的展示消息。

## API 参考

### 测试生图配置

`POST /api/settings/test-image-gen`

请求体与设置保存相同（含 `image_gen_*` 字段）。

### 获取生成的图片

`GET /api/chat/generated-image?path={绝对路径}&token={API_TOKEN}&preview=1`

- `preview=1`：返回 JPEG 缩略图（宽 ≤720px），避免 WebView 卡死。
- 省略 `preview` 或 `preview=0`：返回原图。
- 路径必须位于当前工作区内。

### 状态栏

`GET /api/status` 返回 `image_gen_enabled`、`image_gen_online`（启用且配置完整）。

## 安全与限制

- 生图属于 **WRITE** 操作，每次调用需审批。
- 图片路径校验：仅允许工作区内的 `.png/.jpg/.jpeg/.webp/.gif`。
- API Key 与识图 Key 分开存储、分开配置。
- 生图 HTTP 超时默认 180 秒（见 `friday/config.py`）。

## 故障排查

| 现象 | 建议 |
|------|------|
| 状态栏生图离线 | 检查启用开关、API Key、模型名是否填写 |
| 测试连接失败 | 核对 Base URL、模型名；查看 `%APPDATA%/Friday/friday.log` |
| 聊天有文字无缩略图 | 确认文件仍在保存路径；切换会话再回来（应已持久化） |
| 预览失败但文件存在 | 路径含特殊字符或文件过大时，可点击「查看大图」链接 |
| 返回空白/米色图 | 多为上游模型或 prompt 问题，尝试改写描述或更换模型 |

## 相关代码

| 模块 | 路径 |
|------|------|
| 生图核心 | `friday/image_gen.py` |
| 工具入口 | `friday/tools/image_gen.py` |
| 会话持久化 | `friday/sessions.py` → `build_display_messages` |
| 前端预览 | `web/utils.js` → `appendGeneratedImages` |
| 设置 UI | `web/settings.js` |
