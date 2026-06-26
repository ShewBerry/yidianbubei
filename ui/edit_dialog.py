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
        from ui.category_picker import CategoryPickerButton
        self.category_picker = CategoryPickerButton(self, db, initial_category_id=item["category_id"])
        self.category_picker.pack(fill="x", padx=20, pady=(2, 8))

        # 正文
        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20)
        self.content_text = ctk.CTkTextbox(self, width=410, height=240)
        self.content_text.pack(padx=20, pady=(5, 8))
        self.content_text.insert("1.0", item["content"])

        # 笔记
        ctk.CTkLabel(self, text="笔记（可选）：").pack(anchor="w", padx=20)
        self.notes_text = ctk.CTkTextbox(self, width=410, height=80)
        self.notes_text.pack(padx=20, pady=(5, 8))
        self.notes_text.insert("1.0", item.get("notes", "") or "")

        # 提示：修改正文不影响已排程的背诵进度
        ctk.CTkLabel(self, text="提示：修改标题/正文/分类不会影响当前背诵进度；修改正文会按比例平移已有标记",
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

    def _on_save(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not title:
            messagebox.showwarning("提示", "请输入标题", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "请输入正文", parent=self)
            return
        notes = self.notes_text.get("1.0", "end").rstrip("\n")
        selected = self.category_picker.get_category_id()
        category_id = selected
        self.db.update_item(self.item["id"], title=title, content=content,
                            category_id=category_id, notes=notes)
        if self.on_saved_callback:
            self.on_saved_callback(self.item["id"])
        self.destroy()

    def _on_delete(self):
        if not messagebox.askyesno("确认删除",
                                    f"确定删除条目“{self.item['title']}”吗？\n该条目的所有背诵记录也会一起删除，此操作不可撤销。",
                                    parent=self):
            return
        self.db.delete_item(self.item["id"])
        if self.on_deleted_callback:
            self.on_deleted_callback(self.item["id"])
        self.destroy()
