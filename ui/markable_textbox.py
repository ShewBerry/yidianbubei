# ui/markable_textbox.py
import tkinter as tk
import customtkinter as ctk

from ui.theme import (small_font, COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, FONT_FAMILY)
from ui.html_utils import html_to_segments, is_html_content, html_to_plain_text
from ui.errors import show_write_error


# 标记类型 → 高亮颜色配置
MARK_TAGS = {
    "forgot": {"bg": "#c1554b", "fg": "#ffffff"},   # 红
    "fuzzy":  {"bg": "#e09f3e", "fg": "#000000"},   # 橙
}

FONT_MIN, FONT_MAX = 10, 24
DEFAULT_FONT_SIZE = 14


class MarkableTextbox(ctk.CTkFrame):
    """可标记+可缩放的内容展示框（支持富文本 HTML 渲染）。
    - 选中文字 + 点「忘了/模糊」→ 存库并高亮（覆盖在富文本样式之上）
    - 选中已标记文字 + 点「取消标记」→ 删除覆盖的标记
    - A+/A- 调字号（持久化），内容框高度跟随窗口大小自由伸缩
    - 内容若是 HTML，解析为 B/I/U/颜色/字号等样式渲染

    标记偏移基于"渲染后纯文本"，与编辑器保持一致。
    """
    def __init__(self, parent, db, item: dict, read_only_marks: bool = False):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.item = item
        self.read_only_marks = read_only_marks
        # 缓存纯文本长度，避免 get_marks 内部重复解析 HTML
        self._content_len = len(html_to_plain_text(item.get("content", "")))

        # 从 settings 读取字号
        self.font_size = int(db.get_setting("content_font_size", str(DEFAULT_FONT_SIZE)))

        # 工具栏
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 4))
        if not read_only_marks:
            ctk.CTkButton(toolbar, text="🔴 忘了", width=70, height=26,
                          fg_color="#c1554b", hover_color="#a04439",
                          font=small_font(),
                          command=lambda: self._add_mark("forgot")).pack(side="left", padx=2)
            ctk.CTkButton(toolbar, text="🟠 模糊", width=70, height=26,
                          fg_color="#e09f3e", hover_color="#c08a30",
                          font=small_font(),
                          command=lambda: self._add_mark("fuzzy")).pack(side="left", padx=2)
            ctk.CTkButton(toolbar, text="✕ 取消标记", width=80, height=26,
                          fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          font=small_font(),
                          command=self._remove_mark).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="A-", width=32, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._decrease_font).pack(side="right", padx=2)
        ctk.CTkButton(toolbar, text="A+", width=32, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._increase_font).pack(side="right", padx=2)

        # 内容文本框：用原生 tk.Text 获得完整 tag 支持
        text_frame = ctk.CTkFrame(self)
        text_frame.pack(fill="both", expand=True)

        is_light = ctk.get_appearance_mode() == "Light"
        bg = "#ffffff" if is_light else "#2b2b2b"
        fg = "#212529" if is_light else "#dddddd"

        self.textbox = tk.Text(text_frame, height=15, wrap="word",
                               font=(FONT_FAMILY, self.font_size),
                               background=bg, foreground=fg,
                               insertbackground=fg,
                               padx=8, pady=6,
                               borderwidth=0, highlightthickness=0)
        scrollbar = ctk.CTkScrollbar(text_frame, command=self.textbox.yview)
        self.textbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.textbox.pack(side="left", fill="both", expand=True)

        # 渲染内容
        self._render_content()
        # 应用标记
        self._apply_marks()
        # 已掌握只读模式下，文本框禁用编辑（但允许选择）
        if read_only_marks:
            self.textbox.configure(state="disabled")

    # ===== 内容渲染 =====
    def _render_content(self):
        """根据 content 是否为 HTML 选择渲染方式"""
        content = self.item["content"]
        self.textbox.delete("1.0", "end")

        if not is_html_content(content):
            self.textbox.insert("1.0", content)
            return

        segments = html_to_segments(content)
        for text, tags in segments:
            if not text:
                continue
            start_index = self.textbox.index("insert")
            self.textbox.insert("insert", text)
            end_index = self.textbox.index("insert")
            for t in tags:
                tk_tag = self._segment_tag_to_tk_tag(t)
                if tk_tag:
                    self._ensure_tag_config(tk_tag)
                    self.textbox.tag_add(tk_tag, start_index, end_index)

    def _segment_tag_to_tk_tag(self, seg_tag: str) -> str:
        if seg_tag in ("b", "i", "u"):
            return seg_tag
        if seg_tag.startswith("color:"):
            return f"color_{seg_tag[6:].lower()}"
        if seg_tag.startswith("size:"):
            return f"size_{seg_tag[5:]}"
        return ""

    def _ensure_tag_config(self, tk_tag: str):
        """首次遇到某 tag 时配置其样式"""
        if tk_tag == "b":
            self.textbox.tag_config("b", font=(FONT_FAMILY, self.font_size, "bold"))
        elif tk_tag == "i":
            self.textbox.tag_config("i", font=(FONT_FAMILY, self.font_size, "italic"))
        elif tk_tag == "u":
            self.textbox.tag_config("u", underline=True)
        elif tk_tag.startswith("color_"):
            color = tk_tag[6:]
            self.textbox.tag_config(tk_tag, foreground=color)
        elif tk_tag.startswith("size_"):
            try:
                sz = int(tk_tag[5:])
                self.textbox.tag_config(tk_tag, font=(FONT_FAMILY, sz))
            except ValueError:
                pass

    # ===== 位置转换 =====
    def _pos_to_tkindex(self, pos: int) -> str:
        return self.textbox.index(f"1.0 + {pos} chars")

    def _tkindex_to_pos(self, index: str) -> int:
        """tkinter Text index → 全局字符偏移。"""
        line_str, char_str = index.split(".")
        line_num = int(line_str)
        char_num = int(char_str)
        if line_num == 1:
            return char_num
        pos = 0
        for l in range(1, line_num):
            end_idx = self.textbox.index(f"{l}.end")
            line_len = int(end_idx.split(".")[1])
            pos += line_len + 1
        return pos + char_num

    # ===== 高亮应用 =====
    def _apply_marks(self):
        """根据数据库标记重新应用高亮 tag。
        forgot/fuzzy 高亮覆盖在富文本样式之上（最后应用+raise 优先级最高）。
        """
        for tag in MARK_TAGS:
            self.textbox.tag_remove(tag, "1.0", "end")
        for tag, cfg in MARK_TAGS.items():
            self.textbox.tag_config(tag, background=cfg["bg"], foreground=cfg["fg"])
        for tag in MARK_TAGS:
            self.textbox.tag_raise(tag)
        marks = self.db.get_marks(self.item["id"], content_len=self._content_len)
        for m in marks:
            try:
                start_idx = self._pos_to_tkindex(m["start_pos"])
                end_idx = self._pos_to_tkindex(m["end_pos"])
                self.textbox.tag_add(m["mark_type"], start_idx, end_idx)
            except tk.TclError:
                pass

    # ===== 标记操作 =====
    def _get_selection_range(self):
        try:
            start_idx = self.textbox.index("sel.first")
            end_idx = self.textbox.index("sel.last")
        except Exception as e:
            if "TclError" in type(e).__name__:
                return None
            raise
        return self._tkindex_to_pos(start_idx), self._tkindex_to_pos(end_idx)

    def _add_mark(self, mark_type: str):
        if self.read_only_marks:
            return
        sel = self._get_selection_range()
        if not sel:
            return
        start_pos, end_pos = sel
        if start_pos >= end_pos:
            return
        self._delete_overlapping_marks(start_pos, end_pos)
        try:
            self.db.add_mark(self.item["id"], start_pos, end_pos, mark_type)
        except Exception as e:
            show_write_error(self, e, "添加标记")
            return
        self._apply_marks()

    def _remove_mark(self):
        if self.read_only_marks:
            return
        sel = self._get_selection_range()
        if not sel:
            return
        start_pos, end_pos = sel
        self._delete_overlapping_marks(start_pos, end_pos)
        self._apply_marks()

    def _delete_overlapping_marks(self, start_pos: int, end_pos: int):
        marks = self.db.get_marks(self.item["id"], content_len=self._content_len)
        for m in marks:
            if m["start_pos"] < end_pos and m["end_pos"] > start_pos:
                try:
                    self.db.delete_mark(m["id"])
                except Exception as e:
                    show_write_error(self, e, "删除标记")

    # ===== 字号缩放 =====
    def _increase_font(self):
        if self.font_size < FONT_MAX:
            self.font_size += 1
            self._apply_font_size()

    def _decrease_font(self):
        if self.font_size > FONT_MIN:
            self.font_size -= 1
            self._apply_font_size()

    def _apply_font_size(self):
        self.db.set_setting("content_font_size", str(self.font_size))
        # 同步更新 textbox 默认 font，否则重新渲染后纯文本段字号仍是旧值
        self.textbox.configure(font=(FONT_FAMILY, self.font_size))
        was_disabled = self.textbox.cget("state") == "disabled"
        if was_disabled:
            self.textbox.configure(state="normal")
        self._render_content()
        self._apply_marks()
        if was_disabled:
            self.textbox.configure(state="disabled")
