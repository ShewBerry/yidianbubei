import customtkinter as ctk
from tkinter import messagebox, simpledialog
from datetime import date
from ui.richtext_editor import RichTextEditor
from ui.errors import show_write_error
from ui.theme import small_font, COLOR_TEXT_SECONDARY, COLOR_DANGER, COLOR_DANGER_HOVER


class EditItemDialog(ctk.CTkToplevel):
    """编辑已有背诵条目：标题、正文、分类可改；删除按钮在此对话框内"""
    def __init__(self, parent, db, item, on_saved_callback=None, on_deleted_callback=None):
        super().__init__(parent)
        self.title("编辑条目")
        self.geometry("640x700")
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

        # 按钮：先 pack，固定底部，确保不被正文挤掉
        # 左侧删除条目（红色醒目），右侧保存/取消
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", pady=8, padx=20)
        ctk.CTkButton(btn_frame, text="🗑 删除条目", fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                      width=120, height=34, command=self._on_delete).pack(side="left")
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy,
                      width=80, height=34).pack(side="right", padx=(5, 0))
        ctk.CTkButton(btn_frame, text="保存修改", command=self._on_save,
                      width=100, height=34).pack(side="right", padx=(0, 5))

        # 提示：修改正文不影响已排程的背诵进度（紧贴按钮上方）
        ctk.CTkLabel(self, text="提示：修改标题/正文/分类不会影响当前背诵进度；修改正文时，编辑点之前的标记不变，之后的标记会随编辑量平移，被改动覆盖的标记将删除",
                     text_color=COLOR_TEXT_SECONDARY, font=small_font()).pack(side="bottom", padx=20, pady=(0, 5))

        # 笔记（紧贴提示上方）
        ctk.CTkLabel(self, text="笔记（可选）：").pack(side="bottom", anchor="w", padx=20)
        self.notes_text = ctk.CTkTextbox(self, width=410, height=80)
        self.notes_text.pack(side="bottom", fill="x", padx=20, pady=(5, 8))
        self.notes_text.insert("1.0", item.get("notes", "") or "")

        # 正文（富文本编辑器：支持 B/I/U/字号/颜色）
        # 标签紧贴编辑器、间距收紧；给足固定高度，内部 text 区才能显示多行
        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20, pady=(8, 0))
        self.content_text = RichTextEditor(self, height=320)
        self.content_text.pack(fill="x", padx=20, pady=(2, 8))
        self.content_text.set_html(item["content"])

        self.transient(parent)
        self.grab_set()

    def _on_save(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get_html().strip()
        if not title:
            messagebox.showwarning("提示", "请输入标题", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "请输入正文", parent=self)
            return
        notes = self.notes_text.get("1.0", "end").rstrip("\n")
        selected = self.category_picker.get_category_id()
        category_id = selected
        try:
            self.db.update_item(self.item["id"], title=title, content=content,
                                category_id=category_id, notes=notes)
        except Exception as e:
            show_write_error(self, e, "保存修改")
            return
        if self.on_saved_callback:
            self.on_saved_callback(self.item["id"])
        self.destroy()

    def _on_delete(self):
        if not messagebox.askyesno("确认删除",
                                    f"确定删除条目“{self.item['title']}”吗？\n条目将移入回收站，30 天内可在回收站恢复。",
                                    parent=self):
            return
        try:
            self.db.delete_item(self.item["id"])
        except Exception as e:
            show_write_error(self, e, "删除条目")
            return
        if self.on_deleted_callback:
            self.on_deleted_callback(self.item["id"])
        self.destroy()
