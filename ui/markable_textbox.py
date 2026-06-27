# ui/markable_textbox.py
import customtkinter as ctk
from ui.theme import body_font, small_font, COLOR_TEXT_SECONDARY, COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER


# 标记类型 → 高亮颜色配置
MARK_TAGS = {
    "forgot": {"bg": "#c1554b", "fg": "#ffffff"},   # 红
    "fuzzy":  {"bg": "#e09f3e", "fg": "#000000"},   # 橙
}

FONT_MIN, FONT_MAX = 10, 24
HEIGHT_OPTIONS = [200, 400, 600]


class MarkableTextbox(ctk.CTkFrame):
    """可标记+可缩放的内容展示框。
    - 选中文字 + 点「忘了/模糊」→ 存库并高亮
    - 选中已标记文字 + 点「取消标记」→ 删除覆盖的标记
    - A+/A- 调字号，⤢ 调框高，设置持久化到 settings 表
    """
    def __init__(self, parent, db, item: dict, read_only_marks: bool = False):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.item = item
        self.read_only_marks = read_only_marks  # 已掌握面板只读查看高亮

        # 从 settings 读取字号与框高
        self.font_size = int(db.get_setting("content_font_size", "14"))
        self.height_idx = 0
        saved_h = int(db.get_setting("content_box_height", "200"))
        for i, h in enumerate(HEIGHT_OPTIONS):
            if h >= saved_h:
                self.height_idx = i
                break

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
        # 字号与框高按钮放右侧
        ctk.CTkButton(toolbar, text="A-", width=32, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._decrease_font).pack(side="right", padx=2)
        ctk.CTkButton(toolbar, text="A+", width=32, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._increase_font).pack(side="right", padx=2)
        ctk.CTkButton(toolbar, text="⤢ 高度", width=60, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._cycle_height).pack(side="right", padx=2)

        # 内容文本框
        self.textbox = ctk.CTkTextbox(self, height=HEIGHT_OPTIONS[self.height_idx],
                                       font=ctk.CTkFont(size=self.font_size))
        self.textbox.pack(fill="both", expand=True)
        self.textbox.insert("1.0", item["content"])
        self._apply_marks()
        # 已掌握只读模式下，文本框禁用编辑（但允许选择）
        if read_only_marks:
            self.textbox.configure(state="disabled")

    # ===== 位置转换 =====
    def _pos_to_tkindex(self, pos: int) -> str:
        """字符偏移 → tkinter Text index（'line.char'）"""
        return self.textbox.index(f"1.0 + {pos} chars")

    def _tkindex_to_pos(self, index: str) -> int:
        """tkinter Text index ('line.char') → 全局字符偏移。
        不依赖 Text.count（CTkTextbox 未代理该方法），改为逐行累加长度。
        """
        line_str, char_str = index.split(".")
        line_num = int(line_str)
        char_num = int(char_str)
        if line_num == 1:
            return char_num
        pos = 0
        for l in range(1, line_num):
            end_idx = self.textbox.index(f"{l}.end")
            line_len = int(end_idx.split(".")[1])
            pos += line_len + 1  # +1 为换行符
        return pos + char_num

    # ===== 高亮应用 =====
    def _apply_marks(self):
        """根据数据库标记重新应用高亮 tag"""
        # 清除旧 tag
        for tag in MARK_TAGS:
            self.textbox.tag_remove(tag, "1.0", "end")
        # 配置 tag 样式
        for tag, cfg in MARK_TAGS.items():
            self.textbox.tag_config(tag, background=cfg["bg"], foreground=cfg["fg"])
        # 应用新标记
        marks = self.db.get_marks(self.item["id"])
        for m in marks:
            start_idx = self._pos_to_tkindex(m["start_pos"])
            end_idx = self._pos_to_tkindex(m["end_pos"])
            self.textbox.tag_add(m["mark_type"], start_idx, end_idx)

    # ===== 标记操作 =====
    def _get_selection_range(self):
        """返回 (start_pos, end_pos) 或 None（无选中）。
        sel.first/sel.last 在无选中时抛 TclError，仅捕获该异常。
        """
        try:
            start_idx = self.textbox.index("sel.first")
            end_idx = self.textbox.index("sel.last")
        except Exception as e:
            # 无选中时 tkinter 抛 _tkinter.TclError；其他异常不应被吞掉
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
        # 先删除被选中范围覆盖的旧标记，再新增
        self._delete_overlapping_marks(start_pos, end_pos)
        self.db.add_mark(self.item["id"], start_pos, end_pos, mark_type)
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
        """删除与 [start_pos, end_pos) 有重叠的所有标记"""
        marks = self.db.get_marks(self.item["id"])
        for m in marks:
            if m["start_pos"] < end_pos and m["end_pos"] > start_pos:
                self.db.delete_mark(m["id"])

    # ===== 字号与框高 =====
    def _increase_font(self):
        if self.font_size < FONT_MAX:
            self.font_size += 1
            self._apply_font_size()

    def _decrease_font(self):
        if self.font_size > FONT_MIN:
            self.font_size -= 1
            self._apply_font_size()

    def _apply_font_size(self):
        self.textbox.configure(font=ctk.CTkFont(size=self.font_size))
        self.db.set_setting("content_font_size", str(self.font_size))

    def _cycle_height(self):
        self.height_idx = (self.height_idx + 1) % len(HEIGHT_OPTIONS)
        self.textbox.configure(height=HEIGHT_OPTIONS[self.height_idx])
        self.db.set_setting("content_box_height", str(HEIGHT_OPTIONS[self.height_idx]))
