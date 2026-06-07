"""生图工具 —— generate_image。"""

from __future__ import annotations

from friday.image_gen import format_generate_result, generate_image, image_gen_ready
from friday.storage import load_settings
from friday.tools._decorators import register_tool


@register_tool(
    name="generate_image",
    description=(
        "根据文字描述生成图片并保存到默认操作文件夹下的「生成的图片」目录。"
        "用户要求画图、插画、壁纸、海报、头像、Logo 草图时使用。"
        "需先在设置中配置生图 API Key 与模型名称。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "画面描述（主体、场景、风格、构图等，中文或英文均可）",
            },
            "size": {
                "type": "string",
                "description": "可选。如 1024x1024、1280x720、768x1024",
            },
            "filename": {
                "type": "string",
                "description": "可选。保存文件名，如 wallpaper.png",
            },
            "style": {
                "type": "string",
                "description": "可选。风格补充，如「扁平插画」「写实摄影」",
            },
            "negative_prompt": {
                "type": "string",
                "description": "可选。希望避免出现的元素",
            },
        },
        "required": ["prompt"],
    },
)
def generate_image_tool(
    prompt: str,
    size: str = "",
    filename: str = "",
    style: str = "",
    negative_prompt: str = "",
) -> str:
    settings = load_settings()
    result = generate_image(
        settings,
        prompt,
        size=size,
        filename=filename,
        style=style,
        negative_prompt=negative_prompt,
    )
    return format_generate_result(result)


@register_tool(
    name="image_gen_status",
    description="检查生图 API 是否已在设置中配置就绪",
    parameters={"type": "object", "properties": {}},
)
def image_gen_status() -> str:
    settings = load_settings()
    if not settings.image_gen_enabled:
        return "生图未启用。请在 设置 → API 连接 → 生图 中开启并填写 Key 与模型。"
    if not image_gen_ready(settings):
        return "生图已启用但未就绪：请填写 API Key 与模型名称。"
    provider = settings.image_gen_provider or "openai_compat"
    provider_label = "火山方舟" if provider == "ark" else "OpenAI 兼容中转"
    model = settings.image_gen_model or "（未指定）"
    base = settings.image_gen_base_url.strip() or "（使用默认端点）"
    return f"生图已就绪\nProvider: {provider_label}\n模型: {model}\nBase URL: {base}"
