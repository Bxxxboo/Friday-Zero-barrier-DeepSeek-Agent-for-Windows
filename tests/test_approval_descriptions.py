from friday.approval_descriptions import (
    _extract_quoted_paths,
    describe_approval_detail,
    describe_approval_plain,
)
from friday.weixin.approval import format_approval_prompt_weixin


def test_extract_quoted_paths_ignores_powershell_format_strings():
    cmd = (
        '$desktop = "C:\\Users\\me\\Desktop"\n'
        'Get-ChildItem $classDir | ForEach-Object { '
        '"{0:N1} KB | 修改时间: $($_.LastWriteTime)" -f ($_.Length/1KB) }'
    )
    paths = _extract_quoted_paths(cmd)
    assert paths == ["C:\\Users\\me\\Desktop"]


def test_describe_powershell_desktop_listing_no_template_garbage():
    cmd = (
        '$desktop = "C:\\Users\\me\\Desktop"\n'
        '$classDir = Get-ChildItem $desktop -Directory | Where-Object { $_.Name -match "上课" }\n'
        'Get-ChildItem $classDir.FullName -Directory'
    )
    plain = describe_approval_plain("run_powershell", {"command": cmd})
    assert "桌面" in plain
    assert "$(" not in plain
    assert "LastWriteTime" not in plain
    assert "KB" not in plain
    assert plain.count("「") <= 2


def test_describe_powershell_detail_skips_bogus_target_locations():
    cmd = (
        '$desktop = "C:\\Users\\me\\Desktop"\n'
        'Get-ChildItem $desktop | ForEach-Object { '
        '"$($_.Length/1KB)" }'
    )
    detail = describe_approval_detail("run_powershell", {"command": cmd})
    assert "目标位置" not in detail
    assert "LastWriteTime" not in detail


def test_format_approval_prompt_weixin_omits_command_summary():
    plain = "查看你电脑「桌面」上有哪些文件"
    preview = "目标位置：桌面\n命令摘要：Get-ChildItem $desktop -Directory"
    text = format_approval_prompt_weixin(plain, preview=preview)
    assert "命令摘要" not in text
    assert "Get-ChildItem" not in text
    assert "目标位置" in text or "桌面" in text


def test_format_approval_prompt_weixin_truncates_on_word_boundary():
    plain = "查看你电脑「桌面」上有哪些文件"
    preview = "目标位置：" + "桌面、" * 40
    text = format_approval_prompt_weixin(plain, preview=preview)
    assert "Directo" not in text
    assert text.endswith("）\n回复「同意」执行，「拒绝」取消（5 分钟内有效）") or "…" in text


def test_describe_python_detail_ignores_fstring_size_fragments():
    code = (
        'import shutil, os\n'
        'src = r"C:\\Users\\me\\Desktop\\lesson.docx"\n'
        'dst = r"C:\\work\\.friday\\delivered\\lesson.docx"\n'
        'shutil.copy2(src, dst)\n'
        'print(f"Copied {os.path.getsize(dst)/1024**2:.2f} MB")\n'
    )
    detail = describe_approval_detail("run_python", {"code": code})
    assert "1024" not in detail
    assert ".2f" not in detail
    text = format_approval_prompt_weixin(
        describe_approval_plain("run_python", {"code": code}),
        preview=detail,
    )
    assert "1024" not in text
    assert ".2f" not in text
