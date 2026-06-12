from __future__ import annotations

from friday.python_code_safety import analyze_python_code


def test_blocks_friday_appdata_delete():
    code = """
import os
config_dir = r"C:/Users/me/AppData/Roaming/Friday"
os.remove(os.path.join(config_dir, "operations.json.tmp"))
"""
    safety = analyze_python_code(code)
    assert safety.blocked is True
    assert "星期五" in safety.block_reason


def test_blocks_friday_appdata_json_rewrite():
    code = """
import json
path = r"E:\\Friday-workspace\\..\\AppData\\Roaming\\Friday\\operations.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump([], f)
"""
    safety = analyze_python_code(code)
    assert safety.blocked is True


def test_destructive_workspace_code_requires_approval():
    code = "import os\nos.remove('old.txt')"
    safety = analyze_python_code(code)
    assert safety.blocked is False
    assert safety.always_require_approval is True


def test_read_only_code_is_neutral():
    code = "import requests\nprint(requests.get('https://example.com').status_code)"
    safety = analyze_python_code(code)
    assert safety.blocked is False
    assert safety.always_require_approval is False


def test_workspace_create_write_is_neutral():
    code = """
with open("report.md", "w", encoding="utf-8") as f:
    f.write("# Hello")
"""
    safety = analyze_python_code(code)
    assert safety.blocked is False
    assert safety.always_require_approval is False


def test_json_dump_new_file_is_neutral():
    code = """
import json
with open("data/out.json", "w", encoding="utf-8") as f:
    json.dump({"ok": True}, f)
"""
    safety = analyze_python_code(code)
    assert safety.blocked is False
    assert safety.always_require_approval is False


def test_move_existing_file_requires_approval():
    code = "import shutil\nshutil.move('a.txt', 'b.txt')"
    safety = analyze_python_code(code)
    assert safety.blocked is False
    assert safety.always_require_approval is True


def test_blocks_windows_c_os_delete_in_python():
    code = r"""
import os
os.remove(r"C:\Windows\Temp\friday_test.txt")
"""
    safety = analyze_python_code(code)
    assert safety.blocked is True
    assert "绝对禁止" in safety.block_reason
