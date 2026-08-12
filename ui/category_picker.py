import customtkinter as ctk

from ui.theme import COLOR_TEXT_SECONDARY, COLOR_PERFECT, COLOR_PERFECT_HOVER


class CategoryPickerButton(ctk.CTkFrame):
    """层级式分类选择按钮：显示当前选中分类路径，点击弹出逐级浏览窗口。
    像Windows文件夹一样，一层一层进入子文件夹来定位。"""

    def __init__(self, parent, db, initial_category_id=None, on_change=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.db = db
        self.on_change = on_change
        self.selected_category_id = initial_category_id  # None = 未分类

        self.path_label = ctk.CTkButton(self, text="未分类", anchor="w",
                                        command=self._open_browser, height=32)
        self.path_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(self, text="清除", width=60, command=self._clear,
                      fg_color="gray").pack(side="left", padx=(5, 0))

        self._update_display()

    def _update_display(self):
        if self.selected_category_id is None:
            self.path_label.configure(text="未分类")
        else:
            path = self.db.get_category_path(self.selected_category_id)
            if path:
                self.path_label.configure(text=" / ".join(c["name"] for c in path))
            else:
                self.selected_category_id = None
                self.path_label.configure(text="未分类")

    def _clear(self):
        self.selected_category_id = None
        self._update_display()
        if self.on_change:
            self.on_change(None)

    def get_category_id(self):
        return self.selected_category_id

    def _open_browser(self):
        CategoryBrowserDialog(self, self.db, self.selected_category_id, self._on_selected)

    def _on_selected(self, category_id):
        self.selected_category_id = category_id
        self._update_display()
        if self.on_change:
            self.on_change(category_id)


class CategoryBrowserDialog(ctk.CTkToplevel):
    """层级式分类浏览对话框：逐级进入子文件夹，选定后返回 id"""

    def __init__(self, parent, db, current_id, on_selected):
        super().__init__(parent)
        self.title("选择分类")
        self.geometry("380x420")
        self.db = db
        self.on_selected = on_selected
        self.current_id = current_id  # 当前浏览到的层级（None=顶层）

        # 顶部：当前路径 + 上级按钮
        self.top_bar = ctk.CTkFrame(self)
        self.top_bar.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkButton(self.top_bar, text="⬆ 上级", width=80, command=self._go_up).pack(side="left", padx=(0, 5))
        self.path_label = ctk.CTkLabel(self.top_bar, text="📁 全部分类", anchor="w",
                                       text_color=COLOR_TEXT_SECONDARY)
        self.path_label.pack(side="left", fill="x", expand=True)

        # 列表区域
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 底部：选定此分类 / 取消
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(btn_frame, text="选定此文件夹", command=self._select_current,
                      fg_color=COLOR_PERFECT).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="选定“未分类”", fg_color="gray",
                      command=self._select_uncategorized).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="取消", fg_color="gray", width=70,
                      command=self.destroy).pack(side="right")

        self.transient(parent)
        self.grab_set()
        self._render()

    def _current_path_text(self):
        if self.current_id is None:
            return "📁 全部分类"
        path = self.db.get_category_path(self.current_id)
        return " / ".join("📁 " + c["name"] for c in path) if path else "📁 全部分类"

    def _render(self):
        self.path_label.configure(text=self._current_path_text())
        for w in self.list_frame.winfo_children():
            w.destroy()
        children = self.db.get_category_children(self.current_id)
        if not children:
            ctk.CTkLabel(self.list_frame, text="（此文件夹下没有子文件夹）",
                         text_color=COLOR_TEXT_SECONDARY).pack(pady=30)
            return
        for cat in children:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkButton(row, text=f"📁 {cat['name']}", anchor="w",
                          command=lambda cid=cat["id"]: self._enter(cid)).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="选定", width=60, fg_color=COLOR_PERFECT,
                          hover_color=COLOR_PERFECT_HOVER,
                          command=lambda cid=cat["id"]: self._pick(cid)).pack(side="left", padx=(5, 0))

    def _enter(self, category_id):
        self.current_id = category_id
        self._render()

    def _go_up(self):
        if self.current_id is None:
            return
        path = self.db.get_category_path(self.current_id)
        if len(path) <= 1:
            self.current_id = None
        else:
            self.current_id = path[-2]["id"]
        self._render()

    def _select_current(self):
        """选定当前正在浏览的文件夹层级"""
        self._pick(self.current_id)

    def _select_uncategorized(self):
        self._pick(None)

    def _pick(self, category_id):
        self.on_selected(category_id)
        self.destroy()
