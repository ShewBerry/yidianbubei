# ui/review_panel.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler
from ui.theme import (
    title_font, heading_font, review_title_font, body_font, small_font, big_font,
    COLOR_PERFECT, COLOR_PERFECT_HOVER,
    COLOR_MOSTLY, COLOR_MOSTLY_HOVER,
    COLOR_PARTIAL, COLOR_PARTIAL_HOVER,
    COLOR_WRONG, COLOR_WRONG_HOVER,
    COLOR_TEXT_SECONDARY, PRIMARY,
)


class ReviewPanel(ctk.CTkFrame):
    """今日待背诵面板：卡片式单张展示，4级评分交互"""
    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.queue = []  # 今日队列 [{item, is_retest}]
        self.completed_count = 0
        self.total_count = 0

        self.title_label = ctk.CTkLabel(self, text="今日待背诵", font=title_font())
        self.title_label.pack(pady=(15, 5))

        self.progress_label = ctk.CTkLabel(self, text="", text_color=COLOR_TEXT_SECONDARY,
                                           font=body_font())
        self.progress_label.pack(pady=(0, 5))

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(self, progress_color=PRIMARY, height=6)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=60, pady=(0, 10))

        self.card_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.card_frame.pack(fill="both", expand=True, padx=30, pady=(0, 15))

        self.refresh()

    def refresh(self):
        """刷新今日队列。

        - 队列非空时（背诵进行中）：只追加新出现的 due 条目到末尾，不重建队列，
          避免重背条目丢失或当前背诵条目跳变。
        - 队列为空时：从数据库完整重建队列。
        """
        today = date.today()
        self.db.bring_overdue_to_today(today)
        due_items = self.db.get_due_items(today)
        reviewed_ids = self.db.get_today_reviewed_item_ids(today)

        if self.queue:
            # 背诵进行中：只追加新条目，不重建队列
            existing_ids = {q["item"]["id"] for q in self.queue}
            for item in due_items:
                if item["id"] not in existing_ids:
                    is_retest = item["id"] in reviewed_ids
                    self.queue.append({"item": item, "is_retest": is_retest})
            self.total_count = len(self.queue) + self.completed_count
            self._update_progress()
            self._render_current_card()
        else:
            # 队列为空：完整重建
            # 循环型队列：未评分条目优先，已评分的重背条目排后。
            # 这样关闭软件重开后，会从第一个未处理的条目开始，而不是从已评过分的重背条目重新开始。
            for widget in self.card_frame.winfo_children():
                widget.destroy()
            unscheduled = []
            rescheduled = []
            for item in due_items:
                if item["id"] in reviewed_ids:
                    rescheduled.append({"item": item, "is_retest": True})
                else:
                    unscheduled.append({"item": item, "is_retest": False})
            self.queue = unscheduled + rescheduled
            # 从数据库恢复今日已完成数（perfect 评分且不再 due 的条目）
            # = 今日 perfect 评分总数 - 仍在 due 中的 perfect（重背后又 perfect 的情况极少，忽略）
            today_perfect = self.db.get_perfect_count_in_range(today, today)
            # 今日 due 中的 perfect 次数（重背后又 perfect 的条目，这些已在队列中）
            due_perfect_in_logs = 0
            if due_items:
                due_ids = [i["id"] for i in due_items]
                due_perfect_in_logs = self._count_perfect_in_logs(today, due_ids)
            self.completed_count = today_perfect - due_perfect_in_logs
            self.total_count = self.completed_count + len(self.queue)
            self._update_progress()
            self._render_current_card()

    def _count_perfect_in_logs(self, today, item_ids):
        """统计今日这些条目的 perfect 评分次数（用于避免重复计数）"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        placeholders = ",".join("?" * len(item_ids))
        cursor = self.db.conn.execute(
            f"SELECT COUNT(*) FROM review_logs WHERE review_date=? AND result='perfect' AND item_id IN ({placeholders})",
            [today_str] + item_ids)
        return cursor.fetchone()[0]

    def _update_progress(self):
        if self.total_count == 0:
            self.progress_label.configure(text="")
            self.progress_bar.set(0)
        else:
            self.progress_label.configure(
                text=f"{self.completed_count} / {self.total_count} 已完成")
            self.progress_bar.set(self.completed_count / self.total_count)

    def _render_current_card(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        if not self.queue:
            self._render_complete_state()
            return

        current = self.queue[0]
        item = current["item"]
        stage_desc = self.scheduler.stage_description(
            item["consecutive_correct"], item["round"])

        card = ctk.CTkFrame(self.card_frame, corner_radius=12)
        card.pack(fill="both", expand=True, pady=10)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text=item['title'],
                     font=review_title_font()).pack(side="left")
        ctk.CTkLabel(header, text=stage_desc, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")

        if current.get("show_content"):
            content_box = ctk.CTkTextbox(card, height=200, font=body_font())
            content_box.pack(fill="x", padx=20, pady=10)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")

            # 评分按钮：加大高度、加emoji图标、加描述文案
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(5, 15))

            ctk.CTkButton(btn_frame, text="✓ 完全正确", height=42,
                          fg_color=COLOR_PERFECT, hover_color=COLOR_PERFECT_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("perfect")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="👍 基本正确", height=42,
                          fg_color=COLOR_MOSTLY, hover_color=COLOR_MOSTLY_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("mostly_correct")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="🤔 部分正确", height=42,
                          fg_color=COLOR_PARTIAL, hover_color=COLOR_PARTIAL_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("partial")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="✗ 记错了", height=42,
                          fg_color=COLOR_WRONG, hover_color=COLOR_WRONG_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("wrong")).pack(side="left", padx=4, expand=True)
        else:
            ctk.CTkLabel(card, text="先回忆内容，再点下方按钮查看正文",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=40)
            ctk.CTkButton(card, text="📖 展示内容", width=160, height=38,
                          fg_color=PRIMARY, hover_color=COLOR_PERFECT_HOVER,
                          font=heading_font(),
                          command=self._show_content).pack(pady=10)

    def _render_complete_state(self):
        """今日背诵完成的庆祝态"""
        card = ctk.CTkFrame(self.card_frame, corner_radius=12)
        card.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(card, text="🎉", font=ctk.CTkFont(size=48)).pack(pady=(50, 10))
        ctk.CTkLabel(card, text="今日背诵完成", font=ctk.CTkFont(family="微软雅黑", size=22, weight="bold")).pack(pady=5)

        # 显示今日统计
        today = date.today()
        completed = self.db.get_perfect_count_in_range(today, today)
        if completed > 0:
            ctk.CTkLabel(card, text=f"今天完成了 {completed} 条背诵",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=(5, 30))
        else:
            ctk.CTkLabel(card, text="休息一下，明天继续加油",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=(5, 30))

    def _show_content(self):
        if self.queue:
            self.queue[0]["show_content"] = True
            self._render_current_card()

    def _handle_review(self, result: str):
        if not self.queue:
            return
        current = self.queue[0]
        item = current["item"]
        today = date.today()

        # partial 需查询今日已回退次数以应用上限
        today_partial_count = 0
        if result == "partial":
            today_partial_count = self.db.get_today_partial_count(item["id"], today)

        sched_result = self.scheduler.process_review(
            item, today, result,
            is_retest=current["is_retest"],
            today_partial_count=today_partial_count)

        # 更新数据库
        update_fields = {
            "status": sched_result["status"],
            "round": sched_result["round"],
            "interval": sched_result["interval"],
            "consecutive_correct": sched_result["consecutive_correct"],
        }
        if sched_result["next_review_date"] is not None:
            update_fields["next_review_date"] = sched_result["next_review_date"]
        self.db.update_item(item["id"], **update_fields)

        # 记录日志
        self.db.log_review(item["id"], today, sched_result["round"], result,
                           sched_result["interval"])

        if sched_result["requeue_today"]:
            # 移到队列末尾，标记为重背
            current["is_retest"] = True
            current["show_content"] = False
            # 更新item字典以反映新状态（update_fields 已含非None的next_review_date）
            item.update(update_fields)
            self.queue.pop(0)
            self.queue.append(current)
        else:
            # 完成或移出队列
            self.queue.pop(0)
            self.completed_count += 1

        self._update_progress()
        self._render_current_card()

        if self.on_data_changed and not sched_result["requeue_today"]:
            self.on_data_changed()
