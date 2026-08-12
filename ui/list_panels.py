# ui/list_panels.py
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from datetime import date
from scheduler import Scheduler
from ui.card_list import VirtualCardList
from ui.theme import (
    title_font, heading_font, card_title_font, body_font, small_font,
    COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, COLOR_WARN, COLOR_WARN_HOVER,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, PRIMARY, COLOR_PERFECT_HOVER,
    COLOR_DANGER, COLOR_DANGER_HOVER,
)
from ui.markable_textbox import MarkableTextbox
from ui.notes_box import NotesBox
from ui.errors import show_write_error


def _card_colors():
    """获取当前主题下的卡片相关颜色。"""
    is_light = ctk.get_appearance_mode() == "Light"
    if is_light:
        return {"card_bg": "#dbdbdb", "text": "#212529"}
    else:
        return {"card_bg": "#2b2b2b", "text": "#dddddd"}


def _make_link_button(parent, text, command, bg, fg=COLOR_NEUTRAL, hover_fg=COLOR_NEUTRAL_HOVER):
    """用 tk.Label 模拟可点击的文字按钮（创建速度快，适合批量渲染卡片）。"""
    btn = tk.Label(parent, text=text, font=body_font(),
                   bg=bg, fg=fg, cursor="hand2", padx=8, pady=2)
    # 回调带默认 e=None：Tk 事件回调在个别情况下可能不带 event 调用，
    # 避免 missing 1 required positional argument 崩溃
    btn.bind("<ButtonRelease-1>", lambda e=None: command())
    btn.bind("<Enter>", lambda e=None: btn.configure(fg=hover_fg))
    btn.bind("<Leave>", lambda e=None: btn.configure(fg=fg))
    return btn


class _ItemListMixin:
    """AllItemsPanel / MasteredPanel 共用的卡片操作行为（删除/编辑/历史/重点/展开收起）。"""

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _expand_inplace(self, card, expand_container, item):
        """就地展开：只重建展开区，不触发整表 refresh"""
        for w in expand_container.winfo_children():
            w.destroy()
        self._fill_expand(expand_container, item)
        _make_link_button(
            expand_container, "收起 ▲",
            command=lambda: self._collapse_inplace(card, expand_container, item),
            bg=_card_colors()["card_bg"]).pack(side="right", pady=(5, 0))
        self.expanded_item_id = item["id"]

    def _collapse_inplace(self, card, expand_container, item):
        """就地收起：只重建展开区，不触发整表 refresh"""
        for w in expand_container.winfo_children():
            w.destroy()
        _make_link_button(
            expand_container, "展开 ▼",
            command=lambda: self._expand_inplace(card, expand_container, item),
            bg=_card_colors()["card_bg"]).pack(anchor="e")
        if self.expanded_item_id == item["id"]:
            self.expanded_item_id = None

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self._notify_data_changed(),
                       on_deleted_callback=lambda _id: self._notify_data_changed())

    def _delete_item(self, item):
        """软删除条目到回收站，可在 30 天内恢复"""
        if not messagebox.askyesno(
                "确认删除",
                f"确定删除条目“{item['title']}”吗？\n条目将移入回收站，30 天内可在回收站恢复。",
                parent=self):
            return
        try:
            self.db.delete_item(item["id"])
        except Exception as e:
            show_write_error(self, e, "删除条目")
            return
        self.expanded_item_id = None
        self._notify_data_changed()

    def _notify_data_changed(self):
        """通知 MainWindow 刷新所有面板（含自身）"""
        if self.on_data_changed:
            self.on_data_changed()
        else:
            self.refresh()

    def _show_history(self, item):
        from ui.history_dialog import ReviewHistoryDialog
        ReviewHistoryDialog(self, self.db, item)

    def _add_to_key_folder(self, item):
        from ui.key_folder_dialog import KeyFolderDialog
        KeyFolderDialog(self, self.db, item["id"],
                        on_confirm=lambda fid: self._after_key_add(fid, item))

    def _after_key_add(self, folder_id, item):
        try:
            self.db.add_item_to_key_folder(folder_id, item["id"])
        except Exception as e:
            show_write_error(self, e, "加入重点")
            return
        self._notify_data_changed()

    def _remove_from_key_folder(self, item):
        # getattr 兼容：MasteredPanel 无 key_folder_id 属性，但不会触发此操作
        if getattr(self, "key_folder_id", None) is None:
            return
        try:
            self.db.remove_item_from_key_folder(self.key_folder_id, item["id"])
        except Exception as e:
            show_write_error(self, e, "移出重点")
            return
        self._notify_data_changed()


class AllItemsPanel(_ItemListMixin, VirtualCardList):
    """全部条目面板：虚拟化卡片列表 + 搜索"""

    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None,
                 title: str = "全部条目"):
        super().__init__(parent, db)
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.filter_category_id = None
        self.key_folder_id = None
        self.empty_mode = False  # True 时强制显示空状态（如重点条目无任何文件夹）
        self._search_after_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text=title,
                     font=title_font()).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）",
                                          text_color=COLOR_TEXT_SECONDARY,
                                          font=body_font())
        self.filter_label.pack(side="left", padx=10)

        self.search_entry = ctk.CTkEntry(header_frame,
                                          placeholder_text="🔍 搜索标题或内容...",
                                          font=body_font())
        self.search_entry.pack(side="right", fill="x", expand=True, padx=(5, 0))
        self.search_entry.bind("<KeyRelease>", self._on_search_input)
        self.search_entry.bind(
            "<Return>",
            lambda e: (self._cancel_pending_search(), self._apply_search()))

        self.refresh()

    def _load_items(self):
        if self.empty_mode:
            return []
        if self.key_folder_id is not None:
            return self.db.get_key_folder_items(self.key_folder_id)
        if self.filter_category_id is None:
            # 全部条目：包含所有状态（学习中/已掌握/已归档），搜索不应被状态过滤排除
            return self.db.get_all_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_all_items() if i["category_id"] is None]
        return self.db.get_items_by_category(
            self.filter_category_id, include_descendants=True)

    def _on_search_input(self, event):
        """输入时防抖 150ms 触发搜索，避免每按一键就全量重建"""
        self._cancel_pending_search()
        self._search_after_id = self.after(150, self._apply_search)

    def _cancel_pending_search(self):
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None

    def _apply_search(self):
        self._search_after_id = None
        kw = self.search_entry.get().strip().lower()
        self.set_search_keyword(kw)

    def _render_card(self, item):
        colors = _card_colors()
        card_bg = colors["card_bg"]
        text_color = colors["text"]

        card = tk.Frame(self.scroll_frame, bg=card_bg, bd=0,
                        highlightthickness=1, highlightbackground=card_bg)
        card.pack(fill="x", pady=5, padx=5)

        header = tk.Frame(card, bg=card_bg)
        header.pack(fill="x", padx=12, pady=(8, 3))
        tk.Label(header, text=item["title"],
                 font=card_title_font(), bg=card_bg,
                 fg=text_color).pack(side="left")

        next_review = item["next_review_date"]
        # 档位进度：已通过 X/8 个档位（已掌握 = 全部档位通过）
        passed, total = self.scheduler.stage_progress(
            item.get("consecutive_correct", 0), item.get("round", 1))
        if item["status"] in ("mastered", "archived"):
            status_text = f"已掌握 {passed}/{total} ✓"
        elif next_review and next_review != "":
            if isinstance(next_review, str):
                try:
                    next_review = date.fromisoformat(next_review)
                except ValueError:
                    next_review = None
            today = date.today()
            if next_review and next_review <= today:
                status_text = f"已通过 {passed}/{total} · 今日待背诵"
            else:
                status_text = f"已通过 {passed}/{total} · 下次：{item['next_review_date']}"
        else:
            status_text = f"已通过 {passed}/{total}"
        tk.Label(header, text=status_text, fg=COLOR_TEXT_SECONDARY,
                 font=body_font(), bg=card_bg).pack(side="right")

        expand_container = tk.Frame(card, bg=card_bg)
        expand_container.pack(fill="x", padx=12, pady=(0, 8))

        if self.expanded_item_id == item["id"]:
            self._fill_expand(expand_container, item)
            _make_link_button(
                expand_container, "收起 ▲",
                command=lambda c=card, ec=expand_container, it=item:
                    self._collapse_inplace(c, ec, it),
                bg=card_bg).pack(side="right", pady=(5, 0))
        else:
            _make_link_button(
                expand_container, "展开 ▼",
                command=lambda c=card, ec=expand_container, it=item:
                    self._expand_inplace(c, ec, it),
                bg=card_bg).pack(anchor="e")
        return card

    def _fill_expand(self, container, item):
        """填充展开区内容：内容框 + 笔记 + 操作按钮行"""
        self._current_markable = MarkableTextbox(
            container, self.db, item, read_only_marks=False)
        self._current_markable.pack(fill="x", pady=5)

        self._current_notes = NotesBox(container, self.db, item["id"],
                                       current_notes=item.get("notes", ""), height=70)
        self._current_notes.pack(fill="x", pady=(0, 5))

        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="🗑 删除", width=80, fg_color=COLOR_DANGER,
                      hover_color=COLOR_DANGER_HOVER, font=body_font(),
                      command=lambda: self._delete_item(item)).pack(side="left")
        ctk.CTkButton(btn_frame, text="历史", fg_color=COLOR_NEUTRAL,
                      hover_color=COLOR_NEUTRAL_HOVER, width=70, font=body_font(),
                      command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="编辑", fg_color=COLOR_NEUTRAL,
                      hover_color=COLOR_NEUTRAL_HOVER, width=70, font=body_font(),
                      command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="补签", fg_color=COLOR_WARN,
                      hover_color=COLOR_WARN_HOVER, text_color=COLOR_TEXT_PRIMARY,
                      width=70, font=body_font(),
                      command=lambda: self._backfill_review(item)).pack(side="right", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="⭐ 加入重点", fg_color=COLOR_WARN,
                      hover_color=COLOR_WARN_HOVER, text_color=COLOR_TEXT_PRIMARY,
                      width=80, font=body_font(),
                      command=lambda: self._add_to_key_folder(item)).pack(side="right", padx=(0, 5))
        if self.key_folder_id is not None:
            ctk.CTkButton(btn_frame, text="移出", fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, width=60, font=body_font(),
                          command=lambda: self._remove_from_key_folder(item)).pack(side="right", padx=(0, 5))

    def _backfill_review(self, item):
        from ui.backfill_dialog import BackfillReviewDialog
        BackfillReviewDialog(self, item, self._handle_backfill)

    def _handle_backfill(self, item, review_date, result):
        """补签：用历史日期和评分结果重算状态，按补签日+间隔计算"""
        try:
            self.scheduler.apply(self.db, item, review_date, result, is_backfill=True)
        except Exception as e:
            show_write_error(self, e, "补签")
            return
        self._notify_data_changed()


class MasteredPanel(_ItemListMixin, VirtualCardList):
    """已掌握面板：虚拟化卡片列表"""

    def __init__(self, parent, db, on_data_changed=None):
        super().__init__(parent, db)
        self.on_data_changed = on_data_changed
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="已掌握",
                     font=title_font()).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）",
                                          text_color=COLOR_TEXT_SECONDARY,
                                          font=body_font())
        self.filter_label.pack(side="left", padx=10)

        self.refresh()

    def _load_items(self):
        if self.filter_category_id is None:
            return self.db.get_mastered_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_mastered_items() if i["category_id"] is None]
        items = self.db.get_items_by_category(
            self.filter_category_id, include_descendants=True)
        return [i for i in items if i["status"] in ("mastered", "archived")]

    def _render_card(self, item):
        colors = _card_colors()
        card_bg = colors["card_bg"]
        text_color = colors["text"]

        card = tk.Frame(self.scroll_frame, bg=card_bg, bd=0,
                        highlightthickness=1, highlightbackground=card_bg)
        card.pack(fill="x", pady=5, padx=5)

        header = tk.Frame(card, bg=card_bg)
        header.pack(fill="x", padx=12, pady=(8, 3))
        tk.Label(header, text=item["title"],
                 font=card_title_font(), bg=card_bg,
                 fg=text_color).pack(side="left")
        passed, total = Scheduler.stage_progress(
            item.get("consecutive_correct", 0), item.get("round", 1))
        if item["status"] == "mastered":
            status_text = f"已掌握 {passed}/{total} ✓（一轮）"
        else:
            status_text = f"已归档 {passed}/{total} ✓（二轮）"
        tk.Label(header, text=status_text, fg=COLOR_TEXT_SECONDARY,
                 font=body_font(), bg=card_bg).pack(side="right")

        expand_container = tk.Frame(card, bg=card_bg)
        expand_container.pack(fill="x", padx=12, pady=(0, 8))

        if self.expanded_item_id == item["id"]:
            self._fill_expand(expand_container, item)
            _make_link_button(
                expand_container, "收起 ▲",
                command=lambda c=card, ec=expand_container, it=item:
                    self._collapse_inplace(c, ec, it),
                bg=card_bg).pack(side="right", pady=(5, 0))
        else:
            _make_link_button(
                expand_container, "展开 ▼",
                command=lambda c=card, ec=expand_container, it=item:
                    self._expand_inplace(c, ec, it),
                bg=card_bg).pack(anchor="e")
        return card

    def _fill_expand(self, container, item):
        """填充展开区内容：只读内容框 + 笔记 + 操作按钮行"""
        self._current_markable = MarkableTextbox(
            container, self.db, item, read_only_marks=True)
        self._current_markable.pack(fill="x", pady=5)

        self._current_notes = NotesBox(container, self.db, item["id"],
                                       current_notes=item.get("notes", ""), height=70)
        self._current_notes.pack(fill="x", pady=(0, 5))

        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="🗑 删除", width=80, fg_color=COLOR_DANGER,
                      hover_color=COLOR_DANGER_HOVER, font=body_font(),
                      command=lambda: self._delete_item(item)).pack(side="left")
        ctk.CTkButton(btn_frame, text="历史", fg_color=COLOR_NEUTRAL,
                      hover_color=COLOR_NEUTRAL_HOVER, width=70, font=body_font(),
                      command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="编辑", fg_color=COLOR_NEUTRAL,
                      hover_color=COLOR_NEUTRAL_HOVER, width=70, font=body_font(),
                      command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="⭐ 加入重点", fg_color=COLOR_WARN,
                      hover_color=COLOR_WARN_HOVER, text_color=COLOR_TEXT_PRIMARY,
                      width=80, font=body_font(),
                      command=lambda: self._add_to_key_folder(item)).pack(side="right", padx=(0, 5))
