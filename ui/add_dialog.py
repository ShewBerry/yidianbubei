import customtkinter as ctk
from tkinter import messagebox
from datetime import date, datetime


class AddItemDialog(ctk.CTkToplevel):
    def __init__(self, parent, db, on_save_callback):
        super().__init__(parent)
        self.title("新建背诵")
        self.geometry("450x560")
        self.db = db
        self.on_save_callback = on_save_callback

        # 标题
        ctk.CTkLabel(self, text="标题：").pack(pady=(15, 0), anchor="w", padx=20)
        self.title_entry = ctk.CTkEntry(self, width=410)
        self.title_entry.pack(padx=20, pady=(5, 8))

        # 开始背诵日期
        ctk.CTkLabel(self, text="开始背诵日期：").pack(anchor="w", padx=20)
        date_frame = ctk.CTkFrame(self, fg_color="transparent")
        date_frame.pack(fill="x", padx=20, pady=(2, 8))
        today_str = date.today().isoformat()
        self.date_entry = ctk.CTkEntry(date_frame, width=150, placeholder_text="YYYY-MM-DD")
        self.date_entry.insert(0, today_str)
        self.date_entry.pack(side="left")
        ctk.CTkLabel(date_frame, text="（可改为过去日期，软件会自动推算当前进度）",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=10)

        # 分类选择
        ctk.CTkLabel(self, text="分类：").pack(anchor="w", padx=20)
        cat_frame = ctk.CTkFrame(self, fg_color="transparent")
        cat_frame.pack(fill="x", padx=20, pady=(2, 8))
        self.category_var = ctk.StringVar(value="未分类")
        self.category_menu = ctk.CTkOptionMenu(cat_frame, variable=self.category_var, values=["未分类"])
        self.category_menu.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(cat_frame, text="刷新", width=60, command=self._refresh_categories).pack(side="left", padx=(5, 0))
        self._refresh_categories()

        # 正文
        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20)
        self.content_text = ctk.CTkTextbox(self, width=410, height=220)
        self.content_text.pack(padx=20, pady=(5, 8))

        # 按钮
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=100).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="保存", command=self._on_save, width=100).pack(side="left", padx=10)

        self.transient(parent)
        self.grab_set()

    def _refresh_categories(self):
        categories = self.db.get_categories()
        # 构建显示名（含路径），并保留 id 映射
        self._cat_options = {"未分类": None}
        display_values = ["未分类"]
        for cat in categories:
            path = self.db.get_category_path(cat["id"])
            display = " / ".join(c["name"] for c in path)
            self._cat_options[display] = cat["id"]
            display_values.append(display)
        self.category_menu.configure(values=display_values)
        self.category_var.set("未分类")

    def _on_save(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not title:
            messagebox.showwarning("提示", "请输入标题", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "请输入正文", parent=self)
            return

        # 解析开始日期
        date_str = self.date_entry.get().strip()
        try:
            start_date = date.fromisoformat(date_str)
        except ValueError:
            messagebox.showwarning("提示", "日期格式不正确，请用 YYYY-MM-DD 格式", parent=self)
            return

        # 解析分类
        selected = self.category_var.get()
        category_id = self._cat_options.get(selected)

        self.on_save_callback(title, content, start_date, category_id)
        self.destroy()
