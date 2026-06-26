# ui/history_dialog.py
import customtkinter as ctk


class ReviewHistoryDialog(ctk.CTkToplevel):
    """背诵历史记录对话框"""
    def __init__(self, parent, db, item):
        super().__init__(parent)
        self.title("背诵记录")
        self.geometry("520x520")
        self.db = db
        self.item = item

        ctk.CTkLabel(self, text="背诵记录", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=f"《{item['title']}》", text_color="gray").pack(pady=(0, 10))
        ctk.CTkLabel(self, text=f"开始日期：{item['created_date']}").pack(anchor="w", padx=30, pady=(0, 8))

        logs = db.get_review_logs(item["id"])
        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        if not logs:
            ctk.CTkLabel(scroll, text="暂无背诵记录", text_color="gray").pack(pady=30)
        else:
            header = ctk.CTkFrame(scroll, fg_color="transparent")
            header.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(header, text="日期", width=110, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="轮次", width=60, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="结果", width=100, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="间隔", width=60, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")

            for log in logs:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=log["review_date"], width=110, anchor="w").pack(side="left")
                round_text = f"第{log['round']}轮"
                ctk.CTkLabel(row, text=round_text, width=60, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=self._result_text(log["result"]), width=100, anchor="w").pack(side="left")
                interval_text = f"{log['interval_after']}天" if log["interval_after"] is not None else "—"
                ctk.CTkLabel(row, text=interval_text, width=60, anchor="w").pack(side="left")

        ctk.CTkButton(self, text="关闭", width=100, fg_color="gray", command=self.destroy).pack(pady=(0, 15))
        self.transient(parent)
        self.grab_set()

    def _result_text(self, result: str) -> str:
        return {
            "perfect": "完全正确",
            "mostly_correct": "基本正确",
            "partial": "部分正确",
            "wrong": "记错了",
        }.get(result, result)
