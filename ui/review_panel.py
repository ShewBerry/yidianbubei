# ui/review_panel.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler


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

        self.title_label = ctk.CTkLabel(self, text="今日待背诵",
                                        font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(15, 5))

        self.progress_label = ctk.CTkLabel(self, text="", text_color="gray")
        self.progress_label.pack(pady=(0, 10))

        self.card_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.card_frame.pack(fill="both", expand=True, padx=30, pady=(0, 15))

        self.refresh()

    def refresh(self):
        # 若队列中仍有条目（背诵进行中），仅重新渲染当前卡片，
        # 不从数据库重建队列——避免 on_data_changed 回调导致重背条目丢失
        # （重背条目的 next_review_date 已更新为未来日期，不在 get_due_items 中）
        if self.queue:
            self._render_current_card()
            return

        for widget in self.card_frame.winfo_children():
            widget.destroy()

        today = date.today()
        self.db.bring_overdue_to_today(today)
        due_items = self.db.get_due_items(today)
        reviewed_ids = self.db.get_today_reviewed_item_ids(today)

        self.queue = []
        for item in due_items:
            is_retest = item["id"] in reviewed_ids
            self.queue.append({"item": item, "is_retest": is_retest})
        self.completed_count = 0
        self.total_count = len(self.queue)

        self._update_progress()
        self._render_current_card()

    def _update_progress(self):
        if self.total_count == 0:
            self.progress_label.configure(text="")
        else:
            self.progress_label.configure(
                text=f"{self.completed_count} / {self.total_count} 已完成")

    def _render_current_card(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        if not self.queue:
            ctk.CTkLabel(self.card_frame, text="🎉 今日背诵完成",
                         font=ctk.CTkFont(size=18)).pack(expand=True)
            return

        current = self.queue[0]
        item = current["item"]
        stage_desc = self.scheduler.stage_description(
            item["consecutive_correct"], item["round"])

        card = ctk.CTkFrame(self.card_frame, corner_radius=10)
        card.pack(fill="both", expand=True, pady=10)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text=stage_desc, text_color="gray").pack(side="right")

        if current.get("show_content"):
            content_box = ctk.CTkTextbox(card, height=200)
            content_box.pack(fill="x", padx=20, pady=10)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(0, 15))
            ctk.CTkButton(btn_frame, text="完全正确", fg_color="#2ecc71",
                          command=lambda: self._handle_review("perfect")).pack(side="left", padx=5, expand=True)
            ctk.CTkButton(btn_frame, text="基本正确", fg_color="#3498db",
                          command=lambda: self._handle_review("mostly_correct")).pack(side="left", padx=5, expand=True)
            ctk.CTkButton(btn_frame, text="部分正确", fg_color="#f39c12",
                          command=lambda: self._handle_review("partial")).pack(side="left", padx=5, expand=True)
            ctk.CTkButton(btn_frame, text="记错了", fg_color="#e74c3c",
                          command=lambda: self._handle_review("wrong")).pack(side="left", padx=5, expand=True)
        else:
            ctk.CTkLabel(card, text="回忆后点击下方按钮查看正文",
                         text_color="gray").pack(pady=40)
            ctk.CTkButton(card, text="展示内容", width=150, fg_color="#3498db",
                          command=self._show_content).pack(pady=10)

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

        sched_result = self.scheduler.process_review(
            item, today, result, is_retest=current["is_retest"])

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
