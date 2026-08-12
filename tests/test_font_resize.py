# tests/test_font_resize.py
"""验证 MarkableTextbox 的 A+/A- 字号缩放是否生效。
重点：点 A+ 后 textbox 的默认 font 字号要随之变化（之前 bug 就是没变）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk
from ui.markable_textbox import MarkableTextbox


class FakeDB:
    """最小化的 db 替身，供 MarkableTextbox 用"""
    def __init__(self):
        self.settings = {}
    def get_setting(self, key, default=""):
        return self.settings.get(key, default)
    def set_setting(self, key, value):
        self.settings[key] = value
    def get_marks(self, item_id, content_len=None):
        return []
    def add_mark(self, *a, **kw):
        pass
    def delete_mark(self, *a, **kw):
        pass


def get_textbox_font_size(textbox):
    """读取 tk.Text 当前 font 配置的字号"""
    font_obj = textbox.cget("font")
    # font 可能是 tuple / list / 字符串
    if isinstance(font_obj, (tuple, list)):
        return font_obj[1]
    if isinstance(font_obj, str):
        return int(font_obj.split()[-1])
    return font_obj.cget("size")


@pytest.fixture(scope="module")
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


def test_font_increase_decrease_persists(root):
    """A+ 三次、A- 两次：字号应实时变化并持久化到 settings"""
    db = FakeDB()
    item = {"id": 1, "content": "这是一段纯文本内容，用于测试字号缩放"}
    box = MarkableTextbox(root, db, item, read_only_marks=False)
    box.pack(fill="both", expand=True)
    root.update_idletasks()

    initial_size = get_textbox_font_size(box.textbox)
    box._increase_font()
    box._increase_font()
    box._increase_font()
    assert get_textbox_font_size(box.textbox) == initial_size + 3

    box._decrease_font()
    box._decrease_font()
    assert get_textbox_font_size(box.textbox) == initial_size + 1

    # 持久化到 db
    assert db.settings.get("content_font_size") == str(initial_size + 1)
    box.destroy()


def test_html_content_font_scales(root):
    """HTML 内容（无 tag 的普通文字段）同样能缩放字号"""
    db = FakeDB()
    item = {"id": 2, "content": "普通<b>加粗</b>普通"}
    box = MarkableTextbox(root, db, item, read_only_marks=False)
    box.pack(fill="both", expand=True)
    root.update_idletasks()

    initial_size = get_textbox_font_size(box.textbox)
    box._increase_font()
    assert get_textbox_font_size(box.textbox) == initial_size + 1
    box.destroy()
