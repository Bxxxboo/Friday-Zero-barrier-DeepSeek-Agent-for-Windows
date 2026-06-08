from __future__ import annotations

from friday.tools.registry import TOOL_DEFINITIONS, _IMPORTED, ensure_all_tools, get_tool_definitions


def test_lazy_modules_not_loaded_at_import():
    """documents/media 仍按需加载；与 eager 模块是否已被其他测试 import 无关。"""
    from friday.tools import registry as reg

    assert "documents" in reg._LAZY_MODULES
    assert "media" in reg._LAZY_MODULES
    assert "plan_tools" in reg._EAGER_MODULES


def test_eager_tools_loaded_without_lazy_modules():
    assert "list_directory" in {d["function"]["name"] for d in TOOL_DEFINITIONS}
    assert "update_session_plan" in {d["function"]["name"] for d in TOOL_DEFINITIONS}


def test_lazy_modules_load_on_demand():
    ensure_all_tools()
    names = {d["function"]["name"] for d in get_tool_definitions()}
    assert "create_docx" in names
    assert "read_pdf" in names
    assert "documents" in _IMPORTED
    assert "media" in _IMPORTED
