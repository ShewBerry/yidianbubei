# ui/richtext_editor.py
"""富文本编辑器：支持 B/I/U、字号、颜色。

存储格式：HTML 子集（见 ui/html_utils.py），向后兼容纯文本。
内部使用 tkinter Text 原生 tag 系统实现样式，保存时序列化为 HTML。
"""
import tkinter as tk
from tkinter import colorchooser

import customtkinter as ctk

from ui.theme import (
    small_font, FONT_FAMILY,
    COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER,
    COLOR_TEXT_SECONDARY,
)
from ui.html_utils import (
    html_to_segments, text_widget_to_html,
)


# 候选字号
FONT_SIZES = [12, 14, 16, 18, 20, 24]


class RichTextEditor(ctk.CTkFrame):
    """富文本编辑器组件（可嵌入对话框）。

    公开方法：
    - get_html(): 返回当前内容的 HTML 字符串（保存时调用）
    - set_html(html): 加载 HTML 到编辑器
    - get_plain_text(): 返回可见纯文本（无 HTML 标签）
    """

    def __init__(self, parent, height: int = 240, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        # ===== 工具栏：两组语义分组 + 竖线分隔 =====
        # 组1 文字样式 (B/I/U) | 组2 字体属性 (颜色/字号)
        # 设固定 height=34 防止 CTkFrame 默认 200px 高度把工具栏撑大
        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=34)
        toolbar.pack(fill="x", pady=(0, 6))
        toolbar.pack_propagate(False)  # 禁止子组件撑大工具栏

        # --- 组1：文字样式 ---
        g1 = ctk.CTkFrame(toolbar, fg_color="transparent")
        g1.pack(side="left", padx=(0, 6))
        ctk.CTkButton(g1, text="B", width=34, height=28,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      command=lambda: self._toggle_tag("b")).pack(side="left", padx=2)
        ctk.CTkButton(g1, text="I", width=34, height=28,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=14, slant="italic"),
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      command=lambda: self._toggle_tag("i")).pack(side="left", padx=2)
        ctk.CTkButton(g1, text="U", width=34, height=28,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=14, underline=True),
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      command=lambda: self._toggle_tag("u")).pack(side="left", padx=2)

        self._add_separator(toolbar)

        # --- 组2：字体属性（颜色 + 字号）---
        g2 = ctk.CTkFrame(toolbar, fg_color="transparent")
        g2.pack(side="left", padx=(6, 6))
        ctk.CTkButton(g2, text="🎨 颜色", width=72, height=28,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(),
                      command=self._apply_color).pack(side="left", padx=2)
        ctk.CTkLabel(g2, text="字号", font=small_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack(side="left", padx=(4, 2))
        self.size_menu = ctk.CTkOptionMenu(
            g2, width=68, height=28,
            values=[str(s) for s in FONT_SIZES],
            command=self._apply_font_size,
            font=small_font())
        self.size_menu.set("14")
        self.size_menu.pack(side="left", padx=2)

        # ===== 文本编辑区（用原生 tk.Text 获得完整 tag 支持）=====
        # 用原生 tk.Frame + grid 权重分配，确保 text 区填满剩余空间
        text_frame = tk.Frame(self)
        text_frame.pack(fill="both", expand=True)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        is_light = ctk.get_appearance_mode() == "Light"
        bg = "#ffffff" if is_light else "#2b2b2b"
        fg = "#212529" if is_light else "#dddddd"

        self.text = tk.Text(text_frame, height=12, wrap="word", borderwidth=0,
                            padx=8, pady=6,
                            font=(FONT_FAMILY, 14),
                            background=bg, foreground=fg,
                            insertbackground=fg,
                            highlightthickness=0)
        scrollbar = ctk.CTkScrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        # grid 布局：text 占 (0,0) 并 sticky 四方向填充，scrollbar 占 (0,1)
        self.text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # 预配置基础 tag 样式
        self._configure_base_tags()
        # 绑定快捷键
        self.text.bind("<Control-b>", lambda e: (self._toggle_tag("b"), "break")[1])
        self.text.bind("<Control-i>", lambda e: (self._toggle_tag("i"), "break")[1])
        self.text.bind("<Control-u>", lambda e: (self._toggle_tag("u"), "break")[1])

        # 限制高度
        self.configure(height=height)

    def _add_separator(self, parent):
        """工具栏分组竖线：1px 宽，填充高度，弱化视觉权重。"""
        sep = ctk.CTkFrame(parent, width=1, fg_color=COLOR_NEUTRAL_HOVER)
        sep.pack(side="left", fill="y", padx=2, pady=4)

    def _configure_base_tags(self):
        """预配置常用 tag 样式（动态 tag 在使用时再 config）"""
        self.text.tag_config("b", font=(FONT_FAMILY, 14, "bold"))
        self.text.tag_config("i", font=(FONT_FAMILY, 14, "italic"))
        self.text.tag_config("u", underline=True)

    # ============ Tag 操作 ============
    def _toggle_tag(self, tag_name: str):
        """在当前选区上切换指定 tag。无选区时不操作。"""
        try:
            if self.text.tag_ranges("sel"):
                start, end = "sel.first", "sel.last"
                first_idx = self.text.index("sel.first")
                existing = self.text.tag_names(first_idx)
                if tag_name in existing:
                    self.text.tag_remove(tag_name, start, end)
                else:
                    self.text.tag_add(tag_name, start, end)
        except tk.TclError:
            pass

    def _apply_font_size(self, size_str: str):
        """对选区应用字号"""
        try:
            size = int(size_str)
        except ValueError:
            return
        tag_name = f"size_{size}"
        self.text.tag_config(tag_name, font=(FONT_FAMILY, size))
        try:
            if self.text.tag_ranges("sel"):
                # 先移除其他 size_ tag
                for s in FONT_SIZES:
                    self.text.tag_remove(f"size_{s}", "sel.first", "sel.last")
                self.text.tag_add(tag_name, "sel.first", "sel.last")
        except tk.TclError:
            pass

    def _apply_color(self):
        """对选区应用文字颜色"""
        try:
            (_rgb, hex_color) = colorchooser.askcolor(title="选择文字颜色")
        except Exception:
            return
        if not hex_color:
            return
        hex_color = hex_color.lower()
        tag_name = f"color_{hex_color}"
        self.text.tag_config(tag_name, foreground=hex_color)
        try:
            if self.text.tag_ranges("sel"):
                self.text.tag_add(tag_name, "sel.first", "sel.last")
        except tk.TclError:
            pass

    # ============ 公开 API ============
    def get_html(self) -> str:
        """返回当前内容的 HTML 字符串。若无富文本样式，返回纯文本。"""
        html = text_widget_to_html(self.text)
        html = html.rstrip("\n")
        return html

    def set_html(self, html_str: str):
        """加载 HTML 到编辑器。纯文本直接插入。"""
        self.text.delete("1.0", "end")
        if not html_str:
            return
        segments = html_to_segments(html_str)
        for text, tags in segments:
            if not text:
                continue
            # 普通文本段：插入并应用 tags
            start_index = self.text.index("insert")
            self.text.insert("insert", text)
            end_index = self.text.index("insert")
            for t in tags:
                tk_tag = self._segment_tag_to_tk_tag(t)
                if tk_tag:
                    # 动态配置颜色/字号 tag
                    if tk_tag.startswith("color_"):
                        self.text.tag_config(tk_tag, foreground=tk_tag[6:])
                    elif tk_tag.startswith("size_"):
                        try:
                            sz = int(tk_tag[5:])
                            self.text.tag_config(tk_tag, font=(FONT_FAMILY, sz))
                        except ValueError:
                            pass
                    self.text.tag_add(tk_tag, start_index, end_index)

    def get_plain_text(self) -> str:
        """返回可见纯文本（无 HTML 标签）"""
        return self.text.get("1.0", "end-1c")

    def _segment_tag_to_tk_tag(self, seg_tag: str) -> str:
        """段列表中的 tag → tkinter Text tag 名"""
        if seg_tag in ("b", "i", "u"):
            return seg_tag
        if seg_tag.startswith("color:"):
            return f"color_{seg_tag[6:].lower()}"
        if seg_tag.startswith("size:"):
            return f"size_{seg_tag[5:]}"
        return ""

    # ============ 兼容方法（与 CTkTextbox 接口对齐）============
    def get(self, start, end=None):
        """兼容 CTkTextbox.get()：返回纯文本。"""
        if end is None:
            return self.text.get(start, "end-1c")
        return self.text.get(start, end)

    def insert(self, index, content):
        """兼容 CTkTextbox.insert()：插入纯文本。"""
        self.text.insert(index, content)

    def focus_set(self):
        self.text.focus_set()
