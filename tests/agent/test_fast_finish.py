from __future__ import annotations

from friday.fast_finish import looks_like_multi_step_task, try_fast_finish_reply


def test_fast_finish_write_text_file():
    reply = try_fast_finish_reply([
        ("write_text_file", {"path": "a.py"}, "已写入: D:\\work\\a.py"),
    ])
    assert reply is not None
    assert "D:\\work\\a.py" in reply


def test_fast_finish_skips_multi_step_goal():
    reply = try_fast_finish_reply(
        [("write_text_file", {}, "已写入: x.py")],
        user_goal="请重构整个项目的所有文件",
    )
    assert reply is None


def test_fast_finish_skips_many_pending_todos():
    reply = try_fast_finish_reply(
        [("write_text_file", {}, "已写入: x.py")],
        pending_todos=5,
    )
    assert reply is None


def test_fast_finish_generate_image():
    reply = try_fast_finish_reply([
        (
            "generate_image",
            {},
            "已生成图片并保存：D:\\img\\a.png\n实际尺寸：1024x1024，模型：ep-1。",
        ),
    ])
    assert reply is not None
    assert "a.png" in reply


def test_fast_finish_requires_single_tool():
    assert try_fast_finish_reply([
        ("read_text_file", {}, "ok"),
        ("write_text_file", {}, "已写入: x.py"),
    ]) is None


def test_fast_finish_plugin_list_pair():
    reply = try_fast_finish_reply(
        [
            ("list_friday_plugins", {}, "尚未安装任何插件。"),
            ("list_plugin_catalog", {}, "推荐插件：\n- demo"),
        ],
        user_goal="GitHub 上有什么 rules 适合星期五",
    )
    assert reply is not None
    assert "已安装" in reply
    assert "推荐" in reply


def test_fast_finish_plugin_catalog_single():
    reply = try_fast_finish_reply(
        [("list_plugin_catalog", {}, "推荐插件列表")],
        user_goal="有哪些扩展插件",
    )
    assert reply is not None
    assert "推荐插件列表" in reply


def test_multi_step_hint():
    assert looks_like_multi_step_task("批量修改多个文件")
    assert not looks_like_multi_step_task("把 utils.js 里的 showThinking 改个名")
