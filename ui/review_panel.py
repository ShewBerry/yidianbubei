import customtkinter as ctk
from datetime import date, datetime
from scheduler import Scheduler

class ReviewPanel(ctk.CTkFrame):
    """今日待复习面板：展示到期条目，支持打卡和掌握确认"""
    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.expanded_item_id = None

        self.title_label = ctk.CTkLabel(self, text="今日待复习", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(15, 10))

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.refresh()

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        today = date.today()
        due_items = self.db.get_due_items(today)

        if not due_items:
            ctk.CTkLabel(self.scroll_frame, text="今天没有需要复习的内容 🎉",
                         font=ctk.CTkFont(size=14)).pack(pady=50)
            return

        for item in due_items:
            self._render_item_card(item, today)

    def _render_item_card(self, item, today):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(8, 3))

        stage_desc = self.scheduler.stage_description(item["current_stage"], item["cycle_type"])
        if item["status"] == "pending_mastery":
            stage_desc = "✅ 完成复习周期，请确认掌握"

        ctk.CTkLabel(header_frame, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(header_frame, text=stage_desc,
                     text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=150)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))

            if item["status"] == "pending_mastery":
                ctk.CTkButton(btn_frame, text="确认掌握", fg_color="#2ecc71",
                              command=lambda: self._confirm_mastery(item)).pack(side="right", padx=(5, 0))
            else:
                ctk.CTkButton(btn_frame, text="打卡复习", fg_color="#3498db",
                              command=lambda: self._mark_reviewed(item, today)).pack(side="right", padx=(5, 0))
                ctk.CTkButton(btn_frame, text="补签", fg_color="#f39c12", hover_color="#d68910",
                              width=70, command=lambda: self._backfill_review(item)).pack(side="right", padx=(0, 5))

            ctk.CTkButton(btn_frame, text="收起", fg_color="gray",
                          width=80, command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color="#7f8c8d", hover_color="#95a5a6",
                          width=70, command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color="#7f8c8d", hover_color="#95a5a6",
                          width=70, command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()

    def _mark_reviewed(self, item, today):
        result = self.scheduler.mark_reviewed(item, today)
        self.db.update_item(
            item["id"],
            status=result["status"],
            current_stage=result["current_stage"],
            cycle_type=result["cycle_type"],
            cycle_start_date=result["cycle_start_date"],
            next_review_date=result["next_review_date"]
        )
        self.db.log_review(item["id"], today, item["current_stage"], "done")
        if self.on_data_changed:
            self.on_data_changed()

    def _confirm_mastery(self, item):
        from ui.mastery_dialog import MasteryConfirmDialog
        MasteryConfirmDialog(self, item, self._handle_mastery_result)

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.on_data_changed() if self.on_data_changed else self.refresh(),
                       on_deleted_callback=lambda _id: self.on_data_changed() if self.on_data_changed else self.refresh())

    def _show_history(self, item):
        from ui.history_dialog import ReviewHistoryDialog
        ReviewHistoryDialog(self, self.db, item)

    def _backfill_review(self, item):
        from ui.backfill_dialog import BackfillReviewDialog
        BackfillReviewDialog(self, item, self._handle_backfill)

    def _handle_backfill(self, item, review_date):
        """补签：用历史日期作为复习日，推进阶段并从该日期重算下次复习。"""
        result = self.scheduler.mark_reviewed(item, review_date)
        self.db.update_item(
            item["id"],
            status=result["status"],
            current_stage=result["current_stage"],
            cycle_type=result["cycle_type"],
            cycle_start_date=result["cycle_start_date"],
            next_review_date=result["next_review_date"]
        )
        self.db.log_review(item["id"], review_date, item["current_stage"], "backfilled")
        if self.on_data_changed:
            self.on_data_changed()

    def _handle_mastery_result(self, item, result):
        today = date.today()
        sched_result = self.scheduler.confirm_mastery(item, today, result)
        self.db.update_item(
            item["id"],
            status=sched_result["status"],
            current_stage=sched_result["current_stage"],
            cycle_type=sched_result["cycle_type"],
            cycle_start_date=sched_result["cycle_start_date"],
            next_review_date=sched_result["next_review_date"]
        )
        self.db.log_review(item["id"], today, item["current_stage"], result)
        if self.on_data_changed:
            self.on_data_changed()
