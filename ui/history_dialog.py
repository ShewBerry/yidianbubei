# ui/history_dialog.py
import customtkinter as ctk

from ui.theme import review_title_font, heading_font, COLOR_TEXT_SECONDARY

# 效力档位（决定当日背诵间隔档位的选项）：记错了 < 较多遗忘 < 部分正确 < 完全正确；
# 基本正确不参与档位计算，仅作轮次推进器
_RESULT_RANK = {
    "wrong": 0,
    "mostly_forgotten": 1,
    "partial": 2,
    "perfect": 3,
}


class ReviewHistoryDialog(ctk.CTkToplevel):
    """背诵历史记录对话框"""
    def __init__(self, parent, db, item):
        super().__init__(parent)
        self.title("背诵记录")
        self.geometry("520x520")
        self.db = db
        self.item = item

        ctk.CTkLabel(self, text="背诵记录", font=review_title_font()).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=item['title'], text_color=COLOR_TEXT_SECONDARY).pack(pady=(0, 10))
        ctk.CTkLabel(self, text=f"开始日期：{item['created_date']}").pack(anchor="w", padx=30, pady=(0, 8))

        logs = db.get_review_logs(item["id"])
        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        if not logs:
            ctk.CTkLabel(scroll, text="暂无背诵记录", text_color=COLOR_TEXT_SECONDARY).pack(pady=30)
        else:
            # 按背诵日分组：同一天的多条记录（当日循环内多轮）只显示
            # 「决定当日档位」的那一条，避免基本正确等占用间隔档位
            shown = self._group_by_day(logs)
            header = ctk.CTkFrame(scroll, fg_color="transparent")
            header.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(header, text="日期", width=110, anchor="w",
                         font=heading_font()).pack(side="left")
            ctk.CTkLabel(header, text="轮次", width=60, anchor="w",
                         font=heading_font()).pack(side="left")
            ctk.CTkLabel(header, text="结果", width=100, anchor="w",
                         font=heading_font()).pack(side="left")
            ctk.CTkLabel(header, text="间隔", width=60, anchor="w",
                         font=heading_font()).pack(side="left")

            for log in shown:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=log["review_date"], width=110, anchor="w").pack(side="left")
                round_text = f"第{log['round']}轮"
                ctk.CTkLabel(row, text=round_text, width=60, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=self._result_text(log["result"]), width=100, anchor="w").pack(side="left")
                # 循环未结束（未选完全正确）时 interval_after 为 None，显示「待定」
                interval_text = f"{log['interval_after']}天" if log["interval_after"] is not None else "待定"
                ctk.CTkLabel(row, text=interval_text, width=60, anchor="w").pack(side="left")

        ctk.CTkButton(self, text="关闭", width=100, fg_color="gray", command=self.destroy).pack(pady=(0, 15))
        self.transient(parent)
        self.grab_set()

    @staticmethod
    def _group_by_day(logs: list) -> list:
        """按背诵日分组，每天只保留决定当日档位的记录。

        决定档位的记录 = 排除「基本正确」后效力最低的那条；
        当日只有基本正确时取最后一条（当日循环以完全正确收尾，按完全正确计算）。
        """
        days = {}
        for log in logs:
            days.setdefault(log["review_date"], []).append(log)
        shown = []
        for day_logs in days.values():
            relevant = [l for l in day_logs if l["result"] != "mostly_correct"]
            if relevant:
                deciding = min(relevant, key=lambda l: _RESULT_RANK.get(l["result"], 99))
            else:
                deciding = day_logs[-1]
            shown.append(deciding)
        return shown

    def _result_text(self, result: str) -> str:
        return {
            "perfect": "完全正确",
            "mostly_correct": "基本正确",
            "partial": "部分正确",
            "mostly_forgotten": "较多遗忘",
            "wrong": "记错了",
        }.get(result, result)
