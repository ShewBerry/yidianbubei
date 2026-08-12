import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk

from scheduler import Scheduler
from ui.list_panels import AllItemsPanel


class FakeDB:
    def __init__(self, items):
        self._items = items

    def get_active_items(self):
        return self._items

    def get_all_items(self):
        return self._items

    def get_items_by_category(self, cid, include_descendants=False):
        return self._items

    def get_category_path(self, cid):
        return []

    def get_setting(self, k, d=""):
        return d

    def set_setting(self, k, v):
        pass

    def get_marks(self, iid):
        return []

    def add_mark(self, *a, **kw):
        pass

    def delete_mark(self, *a, **kw):
        pass


def make_item(iid, title, content):
    return {"id": iid, "title": title, "content": content,
            "category_id": None, "notes": "", "status": "learning",
            "next_review_date": "", "round": 1, "interval": 1,
            "consecutive_correct": 0}


@pytest.fixture(scope="module")
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def panel_factory(root):
    panels = []

    def _make(items):
        p = AllItemsPanel(root, FakeDB(items), Scheduler())
        panels.append(p)
        return p

    yield _make
    for p in panels:
        try:
            p.destroy()
        except Exception:
            pass


def test_refresh_renders_only_first_batch(panel_factory):
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = panel_factory(items)
    panel.refresh()
    assert len(panel._card_cache) <= panel.RENDER_BATCH
    assert len(panel._filtered) == 120


def test_render_batch_grows_progressively(panel_factory):
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = panel_factory(items)
    panel.refresh()
    first = len(panel._card_cache)
    panel._render_batch()
    assert len(panel._card_cache) == first + panel.RENDER_BATCH


def test_search_filters_and_renders_only_match(panel_factory):
    items = [make_item(i, f"title-{i}", f"content-{i}") for i in range(120)]
    items.append(make_item(999, "special", "unique-needle-xyz"))
    panel = panel_factory(items)
    panel.set_search_keyword("unique-needle-xyz")
    assert len(panel._filtered) == 1
    panel._render_batch()
    assert len(panel._card_cache) == 1


def test_plain_text_computed_lazily_only_for_search(panel_factory):
    items = [make_item(i, f"title-{i}", f"<b>keyword-{i}</b>") for i in range(120)]
    panel = panel_factory(items)
    panel.refresh()
    assert panel._plain_cache == {}  # 无关键词时不解析纯文本
    panel.set_search_keyword("keyword-7")
    assert panel._plain_cache  # 搜索时才解析
    assert panel._filtered and panel._filtered[0]["id"] == 7


def test_search_resets_scroll_to_top(panel_factory, monkeypatch):
    """回归：搜索/清空搜索后调用 yview_moveto(0) 重置滚动位置到顶部"""
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = panel_factory(items)
    calls = []
    canvas = panel.scroll_frame._parent_canvas
    monkeypatch.setattr(canvas, "yview_moveto", lambda pos: calls.append(pos))

    # 搜索 → 立即滚动到顶部 + 渲染完成后停在顶部
    panel.set_search_keyword("title-1")
    assert 0.0 in calls
    assert panel._pending_scroll == 0.0  # 分批发渲染完成后也 moveto(0)
    assert panel._filtered

    # 清空搜索（重置关键词）→ 同样回到顶部
    calls.clear()
    panel.set_search_keyword("")
    assert 0.0 in calls
    assert panel._pending_scroll == 0.0
    assert len(panel._filtered) == 120


def test_search_no_result_stays_at_top(panel_factory, monkeypatch):
    """回归：搜索无结果时滚动到顶部并显示空状态"""
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = panel_factory(items)
    calls = []
    canvas = panel.scroll_frame._parent_canvas
    monkeypatch.setattr(canvas, "yview_moveto", lambda pos: calls.append(pos))
    panel.set_search_keyword("不存在的关键词xyz")
    assert 0.0 in calls
    assert panel._filtered == []
