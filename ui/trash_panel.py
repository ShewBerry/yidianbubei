# ui/trash_panel.py
"""回收站面板：展示已软删除的条目，支持恢复和彻底删除。
条目保留 30 天，过期后由 Database.purge_expired_deleted 自动清理。"""
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import (
    title_font, heading_font, card_title_font, body_font, small_font,
    COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER,
    COLOR_TEXT_SECONDARY,
    COLOR_DANGER, COLOR_DANGER_HOVER,
)
from ui.list_panels import _card_colors
from ui.errors import show_write_error


class TrashPanel(ctk.CTkFrame):
    """回收站面板"""
    RETENTION_DAYS = 30

    def __init__(self, parent, db, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.on_data_changed = on_data_changed  # 恢复/彻底删除后通知 MainWindow 刷新其他面板

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="回收站",
                     font=title_font()).pack(side="left")
        ctk.CTkLabel(header_frame,
                     text=f"条目保留 {self.RETENTION_DAYS} 天，过期自动清理",
                     text_color=COLOR_TEXT_SECONDARY, font=small_font()).pack(side="left", padx=10)
        # 右侧"清空回收站"按钮
        ctk.CTkButton(header_frame, text="清空回收站", width=100,
                      fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                      font=body_font(),
                      command=self._purge_all).pack(side="right")

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def refresh(self):
        # 保存滚动位置，重建后恢复
        scroll_y = self.scroll_frame._parent_canvas.yview()[0]
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self.db.get_deleted_items()
        if not items:
            self._render_empty_state()
            return
        for item in items:
            self._render_card(item)
        # 恢复滚动位置
        self.scroll_frame._parent_canvas.update_idletasks()
        self.scroll_frame._parent_canvas.yview_moveto(scroll_y)

    def _render_empty_state(self):
        frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        frame.pack(pady=60)
        ctk.CTkLabel(frame, text="🗑", font=ctk.CTkFont(size=40)).pack(pady=(0, 10))
        ctk.CTkLabel(frame, text="回收站为空",
                     font=heading_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack(pady=(0, 5))
        ctk.CTkLabel(frame, text="删除的条目会暂存在这里，30 天内可恢复",
                     font=small_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack()

    def _format_deleted_info(self, item) -> str:
        """格式化删除时间+剩余天数提示"""
        from datetime import datetime
        deleted_at = item.get("deleted_at")
        if not deleted_at:
            return "已删除"
        try:
            dt = datetime.fromisoformat(deleted_at)
        except (ValueError, TypeError):
            return "已删除"
        # 截断到分钟显示
        deleted_str = dt.strftime("%Y-%m-%d %H:%M")
        days_passed = (datetime.now() - dt).days
        days_left = max(0, self.RETENTION_DAYS - days_passed)
        return f"删除于 {deleted_str} · {days_left} 天后清理"

    def _render_card(self, item):
        # 用 tk 原生 widget 渲染卡片（与 AllItemsPanel/MasteredPanel 保持一致，创建速度快）
        colors = _card_colors()
        card_bg = colors["card_bg"]
        text_color = colors["text"]

        card = tk.Frame(self.scroll_frame, bg=card_bg, bd=0,
                        highlightthickness=1, highlightbackground=card_bg)
        card.pack(fill="x", pady=5, padx=5)

        header = tk.Frame(card, bg=card_bg)
        header.pack(fill="x", padx=12, pady=(8, 3))
        tk.Label(header, text=item['title'],
                 font=card_title_font(), bg=card_bg, fg=text_color).pack(side="left")
        tk.Label(header, text=self._format_deleted_info(item),
                 fg=COLOR_TEXT_SECONDARY, font=body_font(),
                 bg=card_bg).pack(side="right")

        # 操作按钮行
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(btn_frame, text="↩ 恢复", width=80,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=body_font(),
                      command=lambda: self._restore_item(item)).pack(side="left")
        ctk.CTkButton(btn_frame, text="彻底删除", width=80,
                      fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                      font=body_font(),
                      command=lambda: self._purge_item(item)).pack(side="left", padx=5)

    def _restore_item(self, item):
        if not messagebox.askyesno("确认恢复",
                                    f"恢复条目“{item['title']}”吗？\n恢复后将回到对应的列表中。",
                                    parent=self):
            return
        try:
            self.db.restore_item(item["id"])
        except Exception as e:
            show_write_error(self, e, "恢复条目")
            return
        self._notify_data_changed()

    def _purge_item(self, item):
        if not messagebox.askyesno("彻底删除",
                                    f"彻底删除条目“{item['title']}”吗？\n此操作不可撤销，条目及其背诵记录将被永久删除。",
                                    parent=self):
            return
        try:
            self.db.purge_item(item["id"])
        except Exception as e:
            show_write_error(self, e, "彻底删除")
            return
        self._notify_data_changed()

    def _purge_all(self):
        items = self.db.get_deleted_items()
        if not items:
            messagebox.showinfo("回收站", "回收站已经是空的", parent=self)
            return
        if not messagebox.askyesno("清空回收站",
                                    f"确定清空回收站吗？共 {len(items)} 条条目将被永久删除，此操作不可撤销。",
                                    parent=self):
            return
        for item in items:
            try:
                self.db.purge_item(item["id"])
            except Exception as e:
                show_write_error(self, e, "清空回收站")
                return
        self._notify_data_changed()

    def _notify_data_changed(self):
        """通知 MainWindow 刷新所有面板（含自身）。
        若未设置 callback（独立使用），则只刷新自身。"""
        if self.on_data_changed:
            self.on_data_changed()
        else:
            self.refresh()
