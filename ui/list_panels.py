import customtkinter as ctk
from datetime import date
from scheduler import Scheduler

class AllItemsPanel(ctk.CTkFrame):
    """全部条目面板：展示所有学习中/待确认的条目"""
    def __init__(self, parent, db, scheduler: Scheduler):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.expanded_item_id = None

        ctk.CTkLabel(self, text="全部条目", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(15, 10))
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self.db.get_active_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="还没有背诵条目，点击右上角“新建背诵”开始吧").pack(pady=50)
            return
        for item in items:
            self._render_card(item)

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 3))

        ctk.CTkLabel(header, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        next_review = item["next_review_date"]
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        today = date.today()
        if item["status"] == "pending_mastery":
            status_text = "待确认掌握"
        elif next_review <= today:
            status_text = "今日待复习"
        else:
            status_text = f"下次复习：{next_review.isoformat()}"
        ctk.CTkLabel(header, text=status_text, text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            ctk.CTkButton(card, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(padx=10, pady=(0, 8), anchor="e")
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()


class MasteredPanel(ctk.CTkFrame):
    """已掌握面板：展示归档条目"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None

        ctk.CTkLabel(self, text="已掌握", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(15, 10))
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self.db.get_mastered_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="还没有已掌握的条目").pack(pady=50)
            return
        for item in items:
            self._render_card(item)

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 3))
        ctk.CTkLabel(header, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text=f"创建于 {item['created_date']}", text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            ctk.CTkButton(card, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(padx=10, pady=(0, 8), anchor="e")
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()
