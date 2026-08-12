# ui/stats_panel.py
import customtkinter as ctk
from datetime import date, timedelta
from ui.theme import (title_font, heading_font, body_font, small_font,
                      COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, COLOR_TEXT_SECONDARY,
                      COLOR_WRONG, COLOR_PERFECT)


class StatsPanel(ctk.CTkFrame):
    """统计面板：今日进度、本周完成、总览、各分类进度"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db

        ctk.CTkLabel(self, text="背诵统计",
                     font=title_font()).pack(anchor="w", padx=15, pady=(15, 10))

        self.scroll = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        ctk.CTkButton(self, text="⟲ 刷新", width=80, fg_color=COLOR_NEUTRAL,
                      hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                      command=self.refresh).pack(pady=(0, 10))

        self.refresh()

    def refresh(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()

        today = date.today()

        self._render_today_progress(today)
        self._render_weekly_stats(today)
        self._render_overview()
        self._render_category_progress()

    def _render_today_progress(self, today):
        """今日进度：已完成 X / 共 Y 条"""
        frame = ctk.CTkFrame(self.scroll, corner_radius=10)
        frame.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(frame, text="今日进度",
                     font=heading_font()).pack(anchor="w", padx=10, pady=(8, 3))

        # 已完成 = 今日 perfect 评分的条目数（perfect 不重背，每条目当日最多1次）
        completed = self.db.get_perfect_count_in_range(today, today)
        # 总数 = 已完成 + 当前待背诵数
        due_items = self.db.get_due_items(today)
        total = completed + len(due_items)

        ctk.CTkLabel(frame, text=f"已完成 {completed} / 共 {total} 条",
                     font=body_font()).pack(anchor="w", padx=10, pady=(0, 8))

    def _render_weekly_stats(self, today):
        """本周完成：N 条完全正确"""
        frame = ctk.CTkFrame(self.scroll, corner_radius=10)
        frame.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(frame, text="本周完成",
                     font=heading_font()).pack(anchor="w", padx=10, pady=(8, 3))

        # 本周 = 从周一开始
        weekday = today.weekday()  # 0=周一
        week_start = today - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)

        count = self.db.get_perfect_count_in_range(week_start, week_end)
        ctk.CTkLabel(frame, text=f"{count} 条完全正确（{week_start.isoformat()} ~ {week_end.isoformat()}）",
                     font=body_font()).pack(anchor="w", padx=10, pady=(0, 8))

    def _render_overview(self):
        """总览：学习中/已掌握/已归档"""
        frame = ctk.CTkFrame(self.scroll, corner_radius=10)
        frame.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(frame, text="总览",
                     font=heading_font()).pack(anchor="w", padx=10, pady=(8, 3))

        counts = self.db.get_status_counts()
        ctk.CTkLabel(frame, text=f"学习中：{counts['learning']} 条",
                     font=body_font(), text_color=COLOR_WRONG).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(frame, text=f"已掌握（一轮）：{counts['mastered']} 条",
                     font=body_font(), text_color=COLOR_PERFECT).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(frame, text=f"已归档（二轮）：{counts['archived']} 条",
                     font=body_font(), text_color=COLOR_NEUTRAL).pack(anchor="w", padx=10, pady=(2, 8))

    def _render_category_progress(self):
        """各分类进度"""
        frame = ctk.CTkFrame(self.scroll, corner_radius=10)
        frame.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(frame, text="各分类进度",
                     font=heading_font()).pack(anchor="w", padx=10, pady=(8, 3))

        progress = self.db.get_category_progress()
        if not progress:
            ctk.CTkLabel(frame, text="暂无分类", text_color=COLOR_TEXT_SECONDARY,
                         font=small_font()).pack(anchor="w", padx=10, pady=(0, 8))
            return

        for cat in progress:
            cat_frame = ctk.CTkFrame(frame, fg_color="transparent")
            cat_frame.pack(fill="x", padx=10, pady=3)

            total = cat["total"]
            mastered = cat["mastered"]
            archived = cat["archived"]

            if total == 0:
                rate_text = "无条目"
            else:
                round1_rate = mastered * 100 // total
                round2_rate = archived * 100 // total
                rate_text = f"一轮 {round1_rate}% / 二轮 {round2_rate}%"

            ctk.CTkLabel(cat_frame, text=f"📁 {cat['name']}",
                         font=body_font()).pack(side="left")
            ctk.CTkLabel(cat_frame, text=f"{total} 条 · {rate_text}",
                         font=small_font(), text_color=COLOR_TEXT_SECONDARY).pack(side="right")

        ctk.CTkLabel(frame, text="").pack(pady=(0, 8))
