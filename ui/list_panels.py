# ui/list_panels.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler
from ui.theme import (
    title_font, heading_font, card_title_font, body_font, small_font,
    COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, COLOR_WARN, COLOR_WARN_HOVER,
    COLOR_TEXT_SECONDARY, PRIMARY, COLOR_PERFECT_HOVER,
)
from ui.markable_textbox import MarkableTextbox
from ui.notes_box import NotesBox


class AllItemsPanel(ctk.CTkFrame):
    """全部条目面板：展示所有学习中的条目"""
    def __init__(self, parent, db, scheduler: Scheduler):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.expanded_item_id = None
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="全部条目",
                     font=title_font()).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）",
                                          text_color=COLOR_TEXT_SECONDARY, font=body_font())
        self.filter_label.pack(side="left", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        self.expanded_item_id = None
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _get_items(self):
        if self.filter_category_id is None:
            return self.db.get_active_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_active_items() if i["category_id"] is None]
        else:
            items = self.db.get_items_by_category(self.filter_category_id, include_descendants=True)
            return [i for i in items if i["status"] == "learning"]

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self._get_items()
        if not items:
            self._render_empty_state("还没有条目", "点击右上角「+ 新建背诵」开始添加")
            return
        for item in items:
            self._render_card(item)

    def _render_empty_state(self, title, hint):
        """空状态美化"""
        frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        frame.pack(pady=60)
        ctk.CTkLabel(frame, text="📝", font=ctk.CTkFont(size=40)).pack(pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=heading_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack(pady=(0, 5))
        ctk.CTkLabel(frame, text=hint, font=small_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack()

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 3))
        ctk.CTkLabel(header, text=item['title'],
                     font=card_title_font()).pack(side="left")

        next_review = item["next_review_date"]
        if next_review and next_review != "":
            if isinstance(next_review, str):
                from datetime import date as date_cls
                try:
                    next_review = date_cls.fromisoformat(next_review)
                except ValueError:
                    next_review = None
            today = date.today()
            if next_review and next_review <= today:
                status_text = "今日待背诵"
            else:
                status_text = f"下次：{item['next_review_date']}"
        else:
            status_text = "—"
        ctk.CTkLabel(header, text=status_text, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")

        if self.expanded_item_id == item["id"]:
            # 可标记+可缩放内容框
            self._current_markable = MarkableTextbox(card, self.db, item, read_only_marks=False)
            self._current_markable.pack(fill="x", padx=12, pady=5)

            # 条目笔记
            self._current_notes = NotesBox(card, self.db, item["id"],
                                            current_notes=item.get("notes", ""), height=70)
            self._current_notes.pack(fill="x", padx=12, pady=(0, 5))

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="补签", fg_color=COLOR_WARN, hover_color=COLOR_WARN_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._backfill_review(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=lambda: self._expand(item["id"])).pack(padx=12, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.refresh(),
                       on_deleted_callback=lambda _id: self.refresh())

    def _show_history(self, item):
        from ui.history_dialog import ReviewHistoryDialog
        ReviewHistoryDialog(self, self.db, item)

    def _backfill_review(self, item):
        from ui.backfill_dialog import BackfillReviewDialog
        BackfillReviewDialog(self, item, self._handle_backfill)

    def _handle_backfill(self, item, review_date, result):
        """补签：用历史日期和评分结果重算状态，不重背，按补签日+间隔计算"""
        # 较多遗忘需查询补签当日已回退次数以应用上限（与今日背诵保持一致）
        today_forgotten_count = 0
        if result == "mostly_forgotten":
            today_forgotten_count = self.db.get_today_forgotten_count(item["id"], review_date)
        sched_result = self.scheduler.process_review(item, review_date, result,
                                                      is_retest=False, is_backfill=True,
                                                      today_forgotten_count=today_forgotten_count)
        update_fields = {
            "status": sched_result["status"],
            "round": sched_result["round"],
            "interval": sched_result["interval"],
            "consecutive_correct": sched_result["consecutive_correct"],
        }
        if sched_result["next_review_date"] is not None:
            update_fields["next_review_date"] = sched_result["next_review_date"]
        self.db.update_item(item["id"], **update_fields)
        self.db.log_review(item["id"], review_date, sched_result["round"], result,
                           sched_result["interval"])
        self.refresh()


class MasteredPanel(ctk.CTkFrame):
    """已掌握面板：展示已掌握和已归档条目"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="已掌握",
                     font=title_font()).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）",
                                          text_color=COLOR_TEXT_SECONDARY, font=body_font())
        self.filter_label.pack(side="left", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        self.expanded_item_id = None
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _get_items(self):
        if self.filter_category_id is None:
            return self.db.get_mastered_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_mastered_items() if i["category_id"] is None]
        else:
            items = self.db.get_items_by_category(self.filter_category_id, include_descendants=True)
            return [i for i in items if i["status"] in ("mastered", "archived")]

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self._get_items()
        if not items:
            self._render_empty_state("还没有已掌握的条目", "完成一轮背诵后会显示在这里")
            return
        for item in items:
            self._render_card(item)

    def _render_empty_state(self, title, hint):
        """空状态美化"""
        frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        frame.pack(pady=60)
        ctk.CTkLabel(frame, text="🎯", font=ctk.CTkFont(size=40)).pack(pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=heading_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack(pady=(0, 5))
        ctk.CTkLabel(frame, text=hint, font=small_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack()

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 3))
        ctk.CTkLabel(header, text=item['title'],
                     font=card_title_font()).pack(side="left")
        status_text = "已掌握(一轮)" if item["status"] == "mastered" else "已归档(二轮)"
        ctk.CTkLabel(header, text=status_text, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")

        if self.expanded_item_id == item["id"]:
            # 只读查看高亮（已掌握面板不新增标记，但可见历史高亮）
            self._current_markable = MarkableTextbox(card, self.db, item, read_only_marks=True)
            self._current_markable.pack(fill="x", padx=12, pady=5)

            # 笔记仍可编辑
            self._current_notes = NotesBox(card, self.db, item["id"],
                                            current_notes=item.get("notes", ""), height=70)
            self._current_notes.pack(fill="x", padx=12, pady=(0, 5))

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=lambda: self._expand(item["id"])).pack(padx=12, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.refresh(),
                       on_deleted_callback=lambda _id: self.refresh())

    def _show_history(self, item):
        from ui.history_dialog import ReviewHistoryDialog
        ReviewHistoryDialog(self, self.db, item)
