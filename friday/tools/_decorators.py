"""工具装饰器 —— 零依赖模块，避免循环导入。

用法：
    from friday.tools._decorators import register_tool

    @register_tool(name="my_tool", description="...", parameters={...})
    def my_tool(arg: str) -> str:
        ...
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

# 保持插入顺序（Python 3.7+ dict 已有序，显式用 OrderedDict 更清晰）
_REGISTRY: OrderedDict[str, dict[str, Any]] = OrderedDict()


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable:
    """装饰器：注册一个工具函数，自动收集其定义。"""

    def decorator(func: Callable) -> Callable:
        _REGISTRY[name] = {
            "func": func,
            "definition": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
        }
        return func

    return decorator


def build_definitions() -> list[dict[str, Any]]:
    from friday.context import sort_tool_definitions

    items = [info["definition"] for info in _REGISTRY.values()]
    return sort_tool_definitions(items)


def build_tool_map() -> dict[str, Callable[..., str]]:
    return {name: info["func"] for name, info in _REGISTRY.items()}
