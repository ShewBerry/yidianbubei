# tests/test_richtext_editor_ui.py
"""离线验证 RichTextEditor 工具栏按钮是否齐全、能否正常序列化/反序列化。
不弹窗，只检查组件结构。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk
from customtkinter import CTkButton
from ui.richtext_editor import RichTextEditor


def _walk_buttons(widget, found):
    """递归遍历所有 CTkButton（适配分组 frame 嵌套）。"""
    for child in widget.winfo_children():
        if isinstance(child, CTkButton):
            found.append(child.cget("text"))
        _walk_buttons(child, found)


@pytest.fixture(scope="module")
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


def _make_editor(root):
    editor = RichTextEditor(root, height=240)
    editor.pack(fill="both", expand=True)
    root.update_idletasks()
    return editor


def test_toolbar_buttons_complete(root):
    """工具栏应包含 B/I/U/颜色，且图片/表格按钮已移除"""
    editor = _make_editor(root)
    try:
        button_texts = []
        _walk_buttons(editor, button_texts)
        for text in ["B", "I", "U", "🎨 颜色"]:
            assert text in button_texts, f"缺少工具栏按钮: {text}"
        for text in ["🖼 图片", "📊 表格"]:
            assert text not in button_texts, f"应移除的按钮仍存在: {text}"
    finally:
        editor.destroy()


def test_html_roundtrip(root):
    """HTML 序列化应往返一致"""
    editor = _make_editor(root)
    try:
        test_html = '<b>加粗</b>普通<i>斜体</i><u>下划</u>'
        editor.set_html(test_html)
        assert editor.get_html() == test_html
    finally:
        editor.destroy()


def test_plain_text_backward_compatible(root):
    """纯文本加载（向后兼容）"""
    editor = _make_editor(root)
    try:
        editor.set_html("纯文本内容")
        assert editor.get_html() == "纯文本内容"
        assert editor.get_plain_text() == "纯文本内容"
    finally:
        editor.destroy()
