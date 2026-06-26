# ui/backfill_dialog.py
import customtkinter as ctk
from tkinter import messagebox
from datetime import date, timedelta


class BackfillReviewDialog(ctk.CTkToplevel):
    """补签对话框：选择历史日期和评分结果"""
    def __init__(self, parent, item, on_confirm_callback):
        super().__init__(parent)
        self.title("补签背诵")
        self.geometry("420x450")
        self.item = item
        self.on_confirm_callback = on_confirm_callback

        ctk.CTkLabel(self, text="补签背诵", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=f"条目：《{item['title']}》").pack(pady=(0, 15))

        ctk.CTkLabel(self, text="补签日期：").pack(anchor="w", padx=30)
        date_frame = ctk.CTkFrame(self, fg_color="transparent")
        date_frame.pack(fill="x", padx=30, pady=(2, 15))
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.date_entry = ctk.CTkEntry(date_frame, width=150, placeholder_text="YYYY-MM-DD")
        self.date_entry.insert(0, yesterday.isoformat())
        self.date_entry.pack(side="left")
        ctk.CTkButton(date_frame, text="昨天", width=60,
                      command=lambda: self.date_entry.delete(0, "end") or self.date_entry.insert(0, yesterday.isoformat())).pack(side="left", padx=5)
        ctk.CTkButton(date_frame, text="前天", width=60,
                      command=lambda: self.date_entry.delete(0, "end") or self.date_entry.insert(0, (today - timedelta(days=2)).isoformat())).pack(side="left")

        ctk.CTkLabel(self, text="评分结果：").pack(anchor="w", padx=30)
        result_frame = ctk.CTkFrame(self, fg_color="transparent")
        result_frame.pack(fill="x", padx=30, pady=(2, 15))
        self.result_var = ctk.StringVar(value="perfect")
        for text, value, color in [("完全正确", "perfect", "#2ecc71"),
                                     ("基本正确", "mostly_correct", "#3498db"),
                                     ("部分正确", "partial", "#f39c12"),
                                     ("记错了", "wrong", "#e74c3c")]:
            ctk.CTkRadioButton(result_frame, text=text, variable=self.result_var,
                               value=value, fg_color=color).pack(anchor="w", pady=2)

        ctk.CTkLabel(self, text="补签后将从该日期按评分重算间隔",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(pady=(0, 15))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=90, fg_color="gray").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="确认补签", width=100,
                      command=self._on_confirm).pack(side="left", padx=5)

        self.transient(parent)
        self.grab_set()

    def _on_confirm(self):
        date_str = self.date_entry.get().strip()
        try:
            review_date = date.fromisoformat(date_str)
        except ValueError:
            messagebox.showwarning("提示", "日期格式不正确，请用 YYYY-MM-DD 格式", parent=self)
            return
        today = date.today()
        if review_date > today:
            messagebox.showwarning("提示", "补签日期不能晚于今天", parent=self)
            return
        start_date = self.item.get("created_date")
        if start_date:
            if isinstance(start_date, str):
                start_date = date.fromisoformat(start_date)
            if review_date < start_date:
                messagebox.showwarning("提示", "补签日期不能早于条目创建日期", parent=self)
                return
        self.on_confirm_callback(self.item, review_date, self.result_var.get())
        self.destroy()