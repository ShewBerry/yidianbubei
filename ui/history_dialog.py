import customtkinter as ctk


class ReviewHistoryDialog(ctk.CTkToplevel):
    """背诵历史记录对话框：展示某条目所有背诵打卡记录"""
    def __init__(self, parent, db, item):
        super().__init__(parent)
        self.title("背诵记录")
        self.geometry("500x520")
        self.db = db
        self.item = item

        ctk.CTkLabel(self, text="背诵记录", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=f"《{item['title']}》", text_color="gray").pack(pady=(0, 10))

        # 创建日期
        created = item["created_date"]
        ctk.CTkLabel(self, text=f"开始背诵日期：{created}").pack(anchor="w", padx=30, pady=(0, 8))

        # 背诵记录列表
        logs = db.get_review_logs(item["id"])
        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        if not logs:
            ctk.CTkLabel(scroll, text="暂无背诵记录", text_color="gray").pack(pady=30)
        else:
            # 表头
            header = ctk.CTkFrame(scroll, fg_color="transparent")
            header.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(header, text="日期", width=110, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="背诵次序", width=90, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="类型", width=120, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")

            for log in logs:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=log["review_date"], width=110, anchor="w").pack(side="left")
                stage_text = f"第{log['stage_completed']}次" if log["stage_completed"] else "—"
                ctk.CTkLabel(row, text=stage_text, width=90, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=self._result_text(log["result"]), width=120, anchor="w").pack(side="left")

        ctk.CTkButton(self, text="关闭", width=100, fg_color="gray", command=self.destroy).pack(pady=(0, 15))

        self.transient(parent)
        self.grab_set()

    def _result_text(self, result: str) -> str:
        return {
            "done": "正常打卡",
            "backfilled": "补签",
            "mastered": "确认掌握",
            "fuzzy": "模糊→短周期",
            "forgotten": "忘了→重背",
        }.get(result, result)
