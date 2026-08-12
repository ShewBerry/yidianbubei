import customtkinter as ctk
from database import Database
from scheduler import Scheduler
from ui.review_panel import ReviewPanel
from ui.list_panels import AllItemsPanel, MasteredPanel
from ui.trash_panel import TrashPanel
from ui.add_dialog import AddItemDialog
from ui.category_panel import CategoryPanel
from ui.stats_panel import StatsPanel
from ui.key_items_panel import KeyItemsPanel
from ui.errors import show_write_error
from ui.theme import (title_font, heading_font, PRIMARY, PRIMARY_HOVER)


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
        self.tabview = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab_today = self.tabview.add("今日待背诵")
        self.tab_all = self.tabview.add("全部条目")
        self.tab_mastered = self.tabview.add("已掌握")
        self.tab_key_items = self.tabview.add("重点条目")
        self.tab_category = self.tabview.add("分类管理")
        self.tab_stats = self.tabview.add("统计")
        self.tab_trash = self.tabview.add("回收站")

        # 懒构造：启动时只构造默认可见的 ReviewPanel，其余面板切换 tab 时才构造。
        # 这样避免启动时同步创建几百个 CTk widget 导致窗口长时间未响应。
        # _tab_panels: 标签页名 → 面板实例（None 表示尚未构造）
        self._tab_panels = {
            "今日待背诵": None,
            "全部条目": None,
            "已掌握": None,
            "重点条目": None,
            "分类管理": None,
            "统计": None,
            "回收站": None,
        }
        # _panel_factories: 标签名 → 构造函数（首次切换时调用）
        self._panel_factories = {
            "今日待背诵": lambda: self._create_review_panel(),
            "全部条目": lambda: self._create_all_items_panel(),
            "已掌握": lambda: self._create_mastered_panel(),
            "重点条目": lambda: self._create_key_items_panel(),
            "分类管理": lambda: self._create_category_panel(),
            "统计": lambda: self._create_stats_panel(),
            "回收站": lambda: self._create_trash_panel(),
        }
        # 脏标记：被标记的面板在切换到该标签时才刷新，避免每次数据变动都重建全部 6 个面板
        self._dirty_panels = set()
        # 待应用的分类过滤（在分类面板选中分类后，不立即构造"全部条目"/"已掌握"面板，
        # 而是保存过滤条件，等用户切到那些 tab 时才应用，避免切到分类管理就卡顿）
        self._pending_category_filter = None

        # 构造默认面板（ReviewPanel），但不立即 refresh——推迟到 mainloop 后，
        # 让窗口先显示出来，避免启动时长时间无响应
        self._ensure_panel("今日待背诵")
        # 首次 refresh 推迟到事件循环启动后，窗口已可见时再执行 DB 查询
        self.after(50, lambda: self._tab_panels["今日待背诵"].refresh())

    def _create_review_panel(self):
        panel = ReviewPanel(self.tab_today, self.db, self.scheduler,
                            on_data_changed=self._refresh_all)
        panel.pack(fill="both", expand=True)
        return panel

    def _create_all_items_panel(self):
        panel = AllItemsPanel(self.tab_all, self.db, self.scheduler,
                              on_data_changed=self._refresh_all)
        panel.pack(fill="both", expand=True)
        return panel

    def _create_mastered_panel(self):
        panel = MasteredPanel(self.tab_mastered, self.db,
                              on_data_changed=self._refresh_all)
        panel.pack(fill="both", expand=True)
        return panel

    def _create_key_items_panel(self):
        panel = KeyItemsPanel(self.tab_key_items, self.db, self.scheduler,
                              on_data_changed=self._refresh_all)
        panel.pack(fill="both", expand=True)
        return panel

    def _create_category_panel(self):
        panel = CategoryPanel(self.tab_category, self.db,
                              on_category_selected=self._on_category_selected)
        panel.pack(fill="both", expand=True)
        return panel

    def _create_stats_panel(self):
        panel = StatsPanel(self.tab_stats, self.db)
        panel.pack(fill="both", expand=True)
        return panel

    def _create_trash_panel(self):
        panel = TrashPanel(self.tab_trash, self.db, on_data_changed=self._refresh_all)
        panel.pack(fill="both", expand=True)
        return panel

    def _ensure_panel(self, tab_name: str):
        """确保指定标签页的面板已构造（懒加载）。返回面板实例或 None。"""
        if tab_name not in self._tab_panels:
            return None
        if self._tab_panels[tab_name] is None:
            self._tab_panels[tab_name] = self._panel_factories[tab_name]()
        return self._tab_panels[tab_name]

    def _open_add_dialog(self):
        AddItemDialog(self, self.db, self._handle_add_item)

    def _handle_add_item(self, title: str, content: str, start_date, category_id, notes: str = ""):
        schedule = self.scheduler.schedule_new_item(start_date)
        try:
            self.db.create_item(
                title, content, start_date, schedule["next_review_date"],
                status=schedule["status"],
                round=schedule["round"],
                interval=schedule["interval"],
                consecutive_correct=schedule["consecutive_correct"],
                category_id=category_id,
                notes=notes,
            )
        except Exception as e:
            show_write_error(self, e, "新建条目")
            return
        self._refresh_all()

    def _on_category_selected(self, cat_id):
        """分类面板选中分类时，记录待应用的过滤条件。
        不立即构造"全部条目"/"已掌握"面板——等用户切到那些 tab 时才应用，
        避免切到分类管理就触发联动构造导致卡顿。
        cat_id: None=全部，整数=指定分类（含子孙）"""
        self._pending_category_filter = cat_id
        # 若面板已构造，立即应用过滤；否则等切换到时再应用
        all_panel = self._tab_panels.get("全部条目")
        if all_panel is not None:
            all_panel.set_category_filter(cat_id)
            self._dirty_panels.discard("全部条目")
        mastered_panel = self._tab_panels.get("已掌握")
        if mastered_panel is not None:
            mastered_panel.set_category_filter(cat_id)
            self._dirty_panels.discard("已掌握")

    def _refresh_all(self):
        """数据变动后刷新面板：当前可见标签页立即刷新，其余标记为脏，切换时再刷新。
        这样在背诵标签页评分时，不必重建全部 6 个面板，显著降低卡顿。"""
        current = self.tabview.get()
        # 立即刷新当前可见面板（若已构造）
        if self._tab_panels.get(current) is not None:
            self._tab_panels[current].refresh()
            self._dirty_panels.discard(current)
        # 其余面板标记为脏，等切换到时再刷新
        for name in self._tab_panels:
            if name != current:
                self._dirty_panels.add(name)

    def _on_tab_changed(self):
        """切换标签页时：懒构造面板（若尚未构造），应用待定的分类过滤，再处理脏标记刷新"""
        current = self.tabview.get()
        # 懒构造：首次切换到该 tab 时才创建面板
        panel = self._ensure_panel(current)
        # 若有待应用的分类过滤，且当前切到的是"全部条目"或"已掌握"，立即应用
        if current in ("全部条目", "已掌握") and panel is not None and self._pending_category_filter is not None:
            panel.set_category_filter(self._pending_category_filter)
            self._dirty_panels.discard(current)
            return  # set_category_filter 已调 refresh，无需再刷新
        # 若面板被标记为脏则立即刷新
        if current in self._dirty_panels:
            self._dirty_panels.discard(current)
            if panel is not None:
                panel.refresh()
