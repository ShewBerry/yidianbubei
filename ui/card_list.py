# ui/card_list.py
"""虚拟化卡片列表基类：分批发渲染 + 滚动加载 + 搜索过滤。

解决“全部条目/已掌握”面板在条目多时一次性渲染全部卡片导致的卡顿：
- refresh(): 重置视图，分批发渲染（每批 RENDER_BATCH 张，用 after 分片）
- 内容未填满视口时自动继续渲染；滚动接近底部时按需渲染下一批
- 搜索: 在完整内存列表上过滤（标题 + 内容纯文本懒计算），只渲染匹配项
"""
import customtkinter as ctk

from ui.html_utils import html_to_plain_text
from ui.theme import COLOR_TEXT_SECONDARY, heading_font, small_font


class VirtualCardList(ctk.CTkFrame):
    RENDER_BATCH = 40

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None
        self.search_keyword = ""
        self._items = []          # 分类过滤后的完整条目列表
        self._filtered = []       # 再应用搜索后的有序列表
        self._visible_end = 0     # 已渲染的卡片数
        self._card_cache = {}     # item_id -> card widget
        self._plain_cache = {}    # item_id -> 纯文本（仅搜索时计算）
        self._pending_render = None
        self._pending_scroll = None

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        canvas = self.scroll_frame._parent_canvas
        canvas.bind("<MouseWheel>", self._on_scroll, add="+")
        canvas.bind("<Button-4>", self._on_scroll, add="+")
        canvas.bind("<Button-5>", self._on_scroll, add="+")
        self.scroll_frame.bind_all("<MouseWheel>", self._on_scroll_all, add="+")
        self.bind("<Configure>", lambda e: self.after_idle(self._maybe_render_more))

    # ============ 数据与过滤 ============

    def _load_items(self):
        """子类实现：返回当前分类过滤下的完整条目列表"""
        raise NotImplementedError

    def refresh(self):
        self._pending_scroll = self.scroll_frame._parent_canvas.yview()[0]
        self._items = self._load_items()
        self._rebuild_filtered()
        self._reset_view()

    def _rebuild_filtered(self):
        kw = self.search_keyword
        if not kw:
            self._filtered = list(self._items)
            return
        result = []
        for item in self._items:
            if kw in item["title"].lower():
                result.append(item)
                continue
            plain = self._plain_cache.get(item["id"])
            if plain is None:
                plain = html_to_plain_text(
                    item.get("content", "")).replace("\xa0", " ").lower()
                self._plain_cache[item["id"]] = plain
            if kw in plain:
                result.append(item)
        self._filtered = result

    def set_search_keyword(self, keyword: str):
        self.search_keyword = keyword if keyword else ""
        self.expanded_item_id = None
        self._pending_scroll = None
        self._rebuild_filtered()
        self._reset_view()

    # ============ 渲染 ============

    def _reset_view(self):
        if self._pending_render is not None:
            try:
                self.after_cancel(self._pending_render)
            except Exception:
                pass
            self._pending_render = None
        for widget in self._card_cache.values():
            try:
                widget.destroy()
            except Exception:
                pass
        self._card_cache = {}
        self._visible_end = 0
        self._toggle_empty_state(len(self._filtered) == 0)
        if self._filtered:
            self._pending_render = self.after(0, self._render_batch)

    def _render_batch(self):
        self._pending_render = None
        end = min(self._visible_end + self.RENDER_BATCH, len(self._filtered))
        for item in self._filtered[self._visible_end:end]:
            self._card_cache[item["id"]] = self._render_card(item)
        self._visible_end = end
        if self._visible_end >= len(self._filtered) and self._pending_scroll is not None:
            try:
                self.scroll_frame._parent_canvas.yview_moveto(self._pending_scroll)
            except Exception:
                pass
            self._pending_scroll = None
        if self._visible_end < len(self._filtered):
            self.after_idle(self._maybe_render_more)

    def _maybe_render_more(self):
        if self._pending_render is not None:
            return
        if self._visible_end >= len(self._filtered):
            return
        try:
            _top, bottom = self.scroll_frame._parent_canvas.yview()
        except Exception:
            return
        if bottom >= 0.95:
            self._pending_render = self.after(0, self._render_batch)

    def _on_scroll(self, _event):
        self.after_idle(self._maybe_render_more)

    def _on_scroll_all(self, event):
        """bind_all 兜底：滚轮事件落在卡片子控件上时也能触发按需加载"""
        try:
            w = event.widget
            while w is not None:
                if w is self.scroll_frame or w is self.scroll_frame._parent_canvas:
                    self.after_idle(self._maybe_render_more)
                    return
                w = getattr(w, "master", None)
        except Exception:
            pass

    def _render_card(self, item):
        """子类实现：创建并 pack 一张卡片，返回 widget"""
        raise NotImplementedError

    # ============ 空状态 ============

    def _toggle_empty_state(self, show: bool):
        if show:
            if not hasattr(self, "_empty_frame") or not self._empty_frame.winfo_exists():
                self._empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
                ctk.CTkLabel(self._empty_frame, text="📭",
                             font=ctk.CTkFont(size=40)).pack(pady=(0, 10))
                self._empty_title = ctk.CTkLabel(
                    self._empty_frame, font=heading_font(),
                    text_color=COLOR_TEXT_SECONDARY)
                self._empty_title.pack(pady=(0, 5))
                self._empty_hint = ctk.CTkLabel(
                    self._empty_frame, font=small_font(),
                    text_color=COLOR_TEXT_SECONDARY)
                self._empty_hint.pack()
            if self.search_keyword:
                self._empty_title.configure(text="没有匹配的条目")
                self._empty_hint.configure(
                    text=f"没有标题或内容包含“{self.search_keyword}”的条目")
            else:
                self._empty_title.configure(text="还没有条目")
                self._empty_hint.configure(text="点击右上角“+ 新建背诵”开始添加")
            self._empty_frame.pack(pady=60)
        else:
            if hasattr(self, "_empty_frame") and self._empty_frame.winfo_exists():
                self._empty_frame.pack_forget()
