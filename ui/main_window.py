import customtkinter as ctk
from database import Database
from scheduler import Scheduler
from ui.review_panel import ReviewPanel
from ui.list_panels import AllItemsPanel, MasteredPanel
from ui.add_dialog import AddItemDialog
from ui.category_panel import CategoryPanel
from ui.stats_panel import StatsPanel
from ui.theme import title_font, heading_font, PRIMARY, PRIMARY_HOVER


class MainWindow(ctk.CTk):
    def __init__(self, db: Database, scheduler: Scheduler):
        super().__init__()
        self.db = db
        self.scheduler = scheduler

        self.title("一点不背")
        self.geometry("900x650")
        # 显式启用窗口缩放（允许拖动窗口边缘调整大小）
        self.resizable(True, True)
        self.minsize(700, 450)

        # 顶部栏
        top_bar = ctk.CTkFrame(self)
        top_bar.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(top_bar, text="📖 一点不背",
                     font=title_font()).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(top_bar, text="+ 新建背诵", width=120,
                      fg_color=PRIMARY, hover_color=PRIMARY_HOVER, font=heading_font(),
                      command=self._open_add_dialog).pack(side="right", padx=10, pady=10)

        # 标签页
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab_today = self.tabview.add("今日待背诵")
        self.tab_all = self.tabview.add("全部条目")
        self.tab_mastered = self.tabview.add("已掌握")
        self.tab_category = self.tabview.add("分类管理")
        self.tab_stats = self.tabview.add("统计")

        self.review_panel = ReviewPanel(self.tab_today, self.db, self.scheduler,
                                        on_data_changed=self._refresh_all)
        self.review_panel.pack(fill="both", expand=True)

        self.all_items_panel = AllItemsPanel(self.tab_all, self.db, self.scheduler)
        self.all_items_panel.pack(fill="both", expand=True)

        self.mastered_panel = MasteredPanel(self.tab_mastered, self.db)
        self.mastered_panel.pack(fill="both", expand=True)

        self.category_panel = CategoryPanel(self.tab_category, self.db,
                                            on_category_selected=self._on_category_selected)
        self.category_panel.pack(fill="both", expand=True)

        self.stats_panel = StatsPanel(self.tab_stats, self.db)
        self.stats_panel.pack(fill="both", expand=True)

    def _open_add_dialog(self):
        AddItemDialog(self, self.db, self._handle_add_item)

    def _handle_add_item(self, title: str, content: str, start_date, category_id):
        schedule = self.scheduler.schedule_new_item(start_date)
        self.db.create_item(
            title, content, start_date, schedule["next_review_date"],
            status=schedule["status"],
            round=schedule["round"],
            interval=schedule["interval"],
            consecutive_correct=schedule["consecutive_correct"],
            category_id=category_id
        )
        self._refresh_all()

    def _on_category_selected(self, cat_id):
        """分类面板选中分类时，同步过滤"全部条目"和"已掌握"面板。
        cat_id: None=全部，整数=指定分类（含子孙）
        在分类树里"全部条目"虚拟节点对应 None，不单独区分"未分类"（简化交互）。"""
        self.all_items_panel.set_category_filter(cat_id)
        self.mastered_panel.set_category_filter(cat_id)

    def _refresh_all(self):
        self.review_panel.refresh()
        self.all_items_panel.refresh()
        self.mastered_panel.refresh()
        self.category_panel.refresh()
        self.stats_panel.refresh()
