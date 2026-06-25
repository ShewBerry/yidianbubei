import customtkinter as ctk
from datetime import date
from database import Database
from scheduler import Scheduler
from ui.review_panel import ReviewPanel
from ui.list_panels import AllItemsPanel, MasteredPanel
from ui.add_dialog import AddItemDialog


class MainWindow(ctk.CTk):
    def __init__(self, db: Database, scheduler: Scheduler):
        super().__init__()
        self.db = db
        self.scheduler = scheduler

        self.title("艾宾浩斯背诵助手")
        self.geometry("800x600")

        # 顶部栏
        top_bar = ctk.CTkFrame(self)
        top_bar.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(top_bar, text="📖 艾宾浩斯背诵助手",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(top_bar, text="+ 新建背诵", width=120,
                      command=self._open_add_dialog).pack(side="right", padx=10, pady=10)

        # 标签页
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab_today = self.tabview.add("今日待复习")
        self.tab_all = self.tabview.add("全部条目")
        self.tab_mastered = self.tabview.add("已掌握")

        self.review_panel = ReviewPanel(self.tab_today, self.db, self.scheduler,
                                        on_data_changed=self._refresh_all)
        self.review_panel.pack(fill="both", expand=True)

        self.all_items_panel = AllItemsPanel(self.tab_all, self.db, self.scheduler)
        self.all_items_panel.pack(fill="both", expand=True)

        self.mastered_panel = MasteredPanel(self.tab_mastered, self.db)
        self.mastered_panel.pack(fill="both", expand=True)

    def _open_add_dialog(self):
        AddItemDialog(self, self._handle_add_item)

    def _handle_add_item(self, title: str, content: str):
        today = date.today()
        schedule = self.scheduler.schedule_new_item(today)
        self.db.create_item(title, content, today, schedule["next_review_date"])
        self._refresh_all()

    def _refresh_all(self):
        self.review_panel.refresh()
        self.all_items_panel.refresh()
        self.mastered_panel.refresh()
