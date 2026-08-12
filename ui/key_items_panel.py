# ui/key_items_panel.py
import customtkinter as ctk
from tkinter import messagebox, simpledialog

from scheduler import Scheduler
from ui.list_panels import AllItemsPanel
from ui.theme import (title_font, body_font, small_font,
                      COLOR_DANGER, COLOR_DANGER_HOVER,
                      COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER,
                      COLOR_TEXT_SECONDARY, PRIMARY, PRIMARY_HOVER)
from ui.errors import show_write_error


class KeyItemsPanel(ctk.CTkFrame):
    """重点条目页签：左侧重点文件夹管理，右侧文件夹内条目列表"""

    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.current_folder_id = None
        self._folder_buttons = {}

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(toolbar, text="重点条目",
                     font=title_font()).pack(side="left")
        ctk.CTkButton(toolbar, text="🗑 删除", width=80, fg_color=COLOR_DANGER,
                      hover_color=COLOR_DANGER_HOVER, font=body_font(),
                      command=self._delete_folder).pack(side="right", padx=(5, 0))
        ctk.CTkButton(toolbar, text="✎ 重命名", width=90, fg_color=COLOR_NEUTRAL,
                      hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                      command=self._rename_folder).pack(side="right", padx=5)
        ctk.CTkButton(toolbar, text="＋ 新建文件夹", width=120, fg_color=PRIMARY,
                      hover_color=PRIMARY_HOVER, font=body_font(),
                      command=self._add_folder).pack(side="right", padx=5)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.folder_list = ctk.CTkScrollableFrame(body, width=180, label_text="")
        self.folder_list.pack(side="left", fill="y", padx=(0, 10))

        self.item_list = AllItemsPanel(body, db, scheduler,
                                       on_data_changed=on_data_changed,
                                       title="重点条目")
        self.item_list.pack(side="left", fill="both", expand=True)

        self.refresh()

    def refresh(self):
        self._refresh_folders()
        if not self._folder_buttons:
            # 没有任何重点文件夹：显式进入空模式，避免 key_folder_id=None
            # 时 AllItemsPanel 回退显示全部条目（错误上下文）。
            self.current_folder_id = None
            self.item_list.empty_mode = True
            self.item_list.empty_title = "还没有重点文件夹"
            self.item_list.empty_hint = "点击右上角“＋ 新建文件夹”创建第一个文件夹"
            self.item_list.refresh()
            return
        self.item_list.empty_mode = False
        if self.current_folder_id is None:
            self._select_folder(next(iter(self._folder_buttons)))
        else:
            self.item_list.key_folder_id = self.current_folder_id
            self.item_list.refresh()

    def _refresh_folders(self):
        for w in self.folder_list.winfo_children():
            w.destroy()
        self._folder_buttons = {}
        folders = self.db.get_key_folders()
        for folder in folders:
            btn = ctk.CTkButton(
                self.folder_list, text=folder["name"], anchor="w",
                fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                font=body_font(),
                command=lambda fid=folder["id"]: self._select_folder(fid))
            btn.pack(fill="x", pady=3)
            self._folder_buttons[folder["id"]] = btn
        if not folders:
            ctk.CTkLabel(self.folder_list, text="还没有重点文件夹",
                         text_color=COLOR_TEXT_SECONDARY,
                         font=small_font()).pack(pady=10)

    def _select_folder(self, folder_id):
        self.current_folder_id = folder_id
        for fid, btn in self._folder_buttons.items():
            btn.configure(fg_color=PRIMARY if fid == folder_id else COLOR_NEUTRAL,
                          hover_color=PRIMARY_HOVER if fid == folder_id else COLOR_NEUTRAL_HOVER)
        self.item_list.key_folder_id = folder_id
        self.item_list.refresh()

    def _add_folder(self):
        name = simpledialog.askstring("新建重点文件夹", "请输入文件夹名称：", parent=self)
        if not name or not name.strip():
            return
        try:
            fid = self.db.create_key_folder(name.strip())
        except Exception as e:
            show_write_error(self, e, "新建文件夹")
            return
        self.refresh()
        self._select_folder(fid)
        if self.on_data_changed:
            self.on_data_changed()

    def _rename_folder(self):
        if self.current_folder_id is None:
            messagebox.showwarning("提示", "请先选择一个重点文件夹", parent=self)
            return
        old = self.db.get_key_folders()
        old_name = next((f["name"] for f in old if f["id"] == self.current_folder_id), "")
        new_name = simpledialog.askstring("重命名重点文件夹", "请输入新名称：",
                                          initialvalue=old_name, parent=self)
        if not new_name or not new_name.strip():
            return
        try:
            self.db.rename_key_folder(self.current_folder_id, new_name.strip())
        except Exception as e:
            show_write_error(self, e, "重命名文件夹")
            return
        self.refresh()
        self._select_folder(self.current_folder_id)
        if self.on_data_changed:
            self.on_data_changed()

    def _delete_folder(self):
        if self.current_folder_id is None:
            messagebox.showwarning("提示", "请先选择一个重点文件夹", parent=self)
            return
        if not messagebox.askyesno(
                "确认删除",
                "确定删除该重点文件夹吗？\n文件夹内的条目不会被删除，只会取消收藏。",
                parent=self):
            return
        try:
            self.db.delete_key_folder(self.current_folder_id)
        except Exception as e:
            show_write_error(self, e, "删除文件夹")
            return
        self.current_folder_id = None
        self.refresh()
        if self.on_data_changed:
            self.on_data_changed()
