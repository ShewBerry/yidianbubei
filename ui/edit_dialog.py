import customtkinter as ctk
from tkinter import messagebox, simpledialog
from datetime import date


class EditItemDialog(ctk.CTkToplevel):
    """编辑已有背诵条目：标题、正文、分类可改；删除按钮在此对话框内"""
    def __init__(self, parent, db, item, on_saved_callback=None, on_deleted_callback=None):
        super().__init__(parent)
        self.title("编辑条目")
        self.geometry("450x600")
        self.db = db
        self.item = item
        self.on_saved_callback = on_saved_callback
        self.on_deleted_callback = on_deleted_callback

        # 标题
        ctk.CTkLabel(self, text="标题：").pack(pady=(15, 0), anchor="w", padx=20)
        self.title_entry = ctk.CTkEntry(self, width=410)
        self.title_entry.pack(padx=20, pady=(5, 8))
        self.title_entry.insert(0, item["title"])

        # 分类选择
        ctk.CTkLabel(self, text="分类：").pack(anchor="w", padx=20)
        cat_frame = ctk.CTkFrame(self, fg_color="transparent")
        cat_frame.pack(fill="x", padx=20, pady=(2, 8))
        self.category_var = ctk.StringVar(value="未分类")
        self.category_menu = ctk.CTkOptionMenu(cat_frame, variable=self.category_var, values=["未分类"])
        self.category_menu.pack(side="left", fill="x", expand=True)
        self._refresh_categories()
        # 回显当前分类
        if item["category_id"]:
            path = db.get_category_path(item["category_id"])
            if path:
                display = " / ".join(c["name"] for c in path)
                self.category_var.set(display)

        # 正文
        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20)
        self.content_text = ctk.CTkTextbox(self, width=410, height=240)
        self.content_text.pack(padx=20, pady=(5, 8))
        self.content_text.insert("1.0", item["content"])

        # 提示：修改正文不影响已排程的复习进度
        ctk.CTkLabel(self, text="提示：修改标题/正文/分类不会影响当前复习进度",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(padx=20, pady=(0, 5))

        # 按钮
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=90).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="保存修改", command=self._on_save, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="删除条目", fg_color="#e74c3c", hover_color="#c0392b",
                      width=100, command=self._on_delete).pack(side="left", padx=5)

        self.transient(parent)
        self.grab_set()

    def _refresh_categories(self):
        categories = self.db.get_categories()
        self._cat_options = {"未分类": None}
        display_values = ["未分类"]
        for cat in categories:
            path = self.db.get_category_path(cat["id"])
            display = " / ".join(c["name"] for c in path)
            self._cat_options[display] = cat["id"]
            display_values.append(display)
        self.category_menu.configure(values=display_values)

    def _on_save(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not title:
            messagebox.showwarning("提示", "请输入标题", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "请输入正文", parent=self)
            return
        selected = self.category_var.get()
        category_id = self._cat_options.get(selected)
        self.db.update_item(self.item["id"], title=title, content=content, category_id=category_id)
        if self.on_saved_callback:
            self.on_saved_callback(self.item["id"])
        self.destroy()

    def _on_delete(self):
        if not messagebox.askyesno("确认删除",
                                    f"确定删除条目“{self.item['title']}”吗？\n该条目的所有复习记录也会一起删除，此操作不可撤销。",
                                    parent=self):
            return
        self.db.delete_item(self.item["id"])
        if self.on_deleted_callback:
            self.on_deleted_callback(self.item["id"])
        self.destroy()
