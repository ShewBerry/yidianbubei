import customtkinter as ctk


class MasteryConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, item, on_result_callback):
        super().__init__(parent)
        self.title("掌握确认")
        self.geometry("500x450")
        self.item = item
        self.on_result_callback = on_result_callback

        ctk.CTkLabel(self, text=f"《{item['title']}》", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text="你已经完成了完整背诵周期，请确认掌握情况：").pack(pady=(0, 10))

        content_box = ctk.CTkTextbox(self, width=460, height=220)
        content_box.pack(padx=20, pady=5)
        content_box.insert("1.0", item["content"])
        content_box.configure(state="disabled")

        ctk.CTkLabel(self, text="你掌握了吗？").pack(pady=(10, 5))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="已掌握", fg_color="#2ecc71", width=120,
                      command=lambda: self._on_result("mastered")).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="有点模糊", fg_color="#f39c12", width=120,
                      command=lambda: self._on_result("fuzzy")).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="完全没记住", fg_color="#e74c3c", width=120,
                      command=lambda: self._on_result("forgotten")).pack(side="left", padx=10)

        self.transient(parent)
        self.grab_set()

    def _on_result(self, result: str):
        self.on_result_callback(self.item, result)
        self.destroy()
