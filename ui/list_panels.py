import customtkinter as ctk
from datetime import date
from scheduler import Scheduler


class AllItemsPanel(ctk.CTkFrame):
    """全部条目面板：展示所有学习中/待确认的条目，支持按分类过滤"""
    def __init__(self, parent, db, scheduler: Scheduler):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.expanded_item_id = None
        self.filter_category_id = None  # None 表示全部

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="全部条目", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")

        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）", text_color="gray")
        self.filter_label.pack(side="left", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def set_category_filter(self, category_id):
        """设置分类过滤；None=全部，'uncategorized'=未分类，整数=指定分类（含子孙）"""
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
        """根据过滤条件获取条目列表"""
        if self.filter_category_id is None:
            return self.db.get_active_items()
        elif self.filter_category_id == "uncategorized":
            all_active = self.db.get_active_items()
            return [i for i in all_active if i["category_id"] is None]
        else:
            items = self.db.get_items_by_category(self.filter_category_id, include_descendants=True)
            return [i for i in items if i["status"] in ("learning", "pending_mastery")]

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self._get_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="没有符合条件的条目").pack(pady=50)
            return
        for item in items:
            self._render_card(item)

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 3))

        title_text = f"《{item['title']}》"
        if item["category_id"]:
            path = self.db.get_category_path(item["category_id"])
            cat_name = " / ".join(c["name"] for c in path) if path else ""
            title_text += f"  [📁{cat_name}]"
        ctk.CTkLabel(header, text=title_text,
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
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(side="right")
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

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.refresh(),
                       on_deleted_callback=lambda _id: self.refresh())


class MasteredPanel(ctk.CTkFrame):
    """已掌握面板：展示归档条目，支持按分类过滤"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="已掌握", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）", text_color="gray")
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
            return [i for i in items if i["status"] == "mastered"]

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self._get_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="没有符合条件的条目").pack(pady=50)
            return
        for item in items:
            self._render_card(item)

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 3))
        title_text = f"《{item['title']}》"
        if item["category_id"]:
            path = self.db.get_category_path(item["category_id"])
            cat_name = " / ".join(c["name"] for c in path) if path else ""
            title_text += f"  [📁{cat_name}]"
        ctk.CTkLabel(header, text=title_text,
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text=f"创建于 {item['created_date']}", text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(side="right")
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

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.refresh(),
                       on_deleted_callback=lambda _id: self.refresh())
