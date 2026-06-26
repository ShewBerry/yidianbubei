import customtkinter as ctk
from tkinter import messagebox
from datetime import date, timedelta


class BackfillReviewDialog(ctk.CTkToplevel):
    """补签对话框：为指定条目补打过去某天的背诵打卡。
    补签后从补签日期重算下次背诵日期。"""
    def __init__(self, parent, item, on_confirm_callback):
        super().__init__(parent)
        self.title("补签背诵")
        self.geometry("420x320")
        self.item = item
        self.on_confirm_callback = on_confirm_callback

        ctk.CTkLabel(self, text="补签背诵", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=f"条目：《{item['title']}》").pack(pady=(0, 5))

        # 当前状态提示
        next_review = item["next_review_date"]
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        info = f"当前阶段：第{item['current_stage']}次背诵  |  下次背诵：{next_review.isoformat()}"
        ctk.CTkLabel(self, text=info, text_color="gray").pack(pady=(0, 15))

        # 日期输入
        ctk.CTkLabel(self, text="补签的背诵日期：").pack(anchor="w", padx=30)
        date_frame = ctk.CTkFrame(self, fg_color="transparent")
        date_frame.pack(fill="x", padx=30, pady=(2, 5))
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.date_entry = ctk.CTkEntry(date_frame, width=150, placeholder_text="YYYY-MM-DD")
        self.date_entry.insert(0, yesterday.isoformat())
        self.date_entry.pack(side="left")
        ctk.CTkButton(date_frame, text="昨天", width=60,
                      command=lambda: self.date_entry.delete(0, "end") or self.date_entry.insert(0, yesterday.isoformat())).pack(side="left", padx=5)
        ctk.CTkButton(date_frame, text="前天", width=60,
                      command=lambda: self.date_entry.delete(0, "end") or self.date_entry.insert(0, (today - timedelta(days=2)).isoformat())).pack(side="left")

        ctk.CTkLabel(self, text="补签后，下次背诵日期将从该日期起重新计算。",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(pady=(5, 15))

        # 按钮
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
        if review_date < date.fromisoformat(self.item["cycle_start_date"] if isinstance(self.item["cycle_start_date"], str) else self.item["cycle_start_date"].isoformat()):
            messagebox.showwarning("提示", "补签日期不能早于该条目的开始日期", parent=self)
            return
        self.on_confirm_callback(self.item, review_date)
        self.destroy()
