# ui/key_folder_dialog.py
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import review_title_font, body_font, small_font, COLOR_TEXT_SECONDARY
from ui.errors import show_write_error


class KeyFolderDialog(ctk.CTkToplevel):
    """选择或新建重点文件夹，确认后回调 on_confirm(folder_id)"""

    def __init__(self, parent, db, item_id, on_confirm):
        super().__init__(parent)
        self.db = db
        self.item_id = item_id
        self.on_confirm = on_confirm
        self.title("加入重点条目")
        self.geometry("420x320")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="加入重点条目",
                     font=review_title_font()).pack(pady=(15, 10))

        folders = db.get_key_folders()
        self.folder_map = {f["name"]: f["id"] for f in folders}
        names = list(self.folder_map.keys())

        ctk.CTkLabel(self, text="选择已有文件夹：",
                     font=body_font()).pack(anchor="w", padx=30)
        if names:
            self.menu_var = ctk.StringVar(value=names[0])
            ctk.CTkOptionMenu(self, values=names, variable=self.menu_var,
                              width=340).pack(padx=30, pady=(2, 12), fill="x")
        else:
            self.menu_var = None
            ctk.CTkLabel(self, text="（还没有文件夹，请在下方新建）",
                         text_color=COLOR_TEXT_SECONDARY,
                         font=small_font()).pack(pady=(2, 12))

        ctk.CTkLabel(self, text="或新建文件夹：",
                     font=body_font()).pack(anchor="w", padx=30)
        self.new_entry = ctk.CTkEntry(self, placeholder_text="新文件夹名称", width=340)
        self.new_entry.pack(padx=30, pady=(2, 15), fill="x")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 15))
        ctk.CTkButton(btn_frame, text="取消", width=110, fg_color="gray",
                      command=self.destroy).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="加入", width=110,
                      command=self._confirm).pack(side="left", padx=5)

        self.transient(parent)
        self.grab_set()

    def _confirm(self):
        new_name = self.new_entry.get().strip()
        folder_id = None
        if new_name:
            try:
                folder_id = self.db.create_key_folder(new_name)
            except Exception as e:
                show_write_error(self, e, "新建文件夹")
                return
        elif self.menu_var is not None:
            folder_id = self.folder_map.get(self.menu_var.get())
        if folder_id is None:
            messagebox.showwarning("提示", "请选择或新建一个文件夹", parent=self)
            return
        if self.db.is_item_in_key_folder(folder_id, self.item_id):
            messagebox.showinfo("提示", "该条目已在选中的重点文件夹中", parent=self)
            self.destroy()
            return
        self.on_confirm(folder_id)
        self.destroy()
