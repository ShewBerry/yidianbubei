import customtkinter as ctk
from tkinter import messagebox


class AddItemDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("新建背诵")
        self.geometry("400x400")
        self.on_save_callback = on_save_callback

        ctk.CTkLabel(self, text="标题：").pack(pady=(15, 0), anchor="w", padx=20)
        self.title_entry = ctk.CTkEntry(self, width=360)
        self.title_entry.pack(padx=20, pady=(5, 10))

        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20)
        self.content_text = ctk.CTkTextbox(self, width=360, height=200)
        self.content_text.pack(padx=20, pady=(5, 10))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=100).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="保存", command=self._on_save, width=100).pack(side="left", padx=10)

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
        self.on_save_callback(title, content)
        self.destroy()
