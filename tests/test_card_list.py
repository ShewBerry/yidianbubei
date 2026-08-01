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


@pytest.fixture
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


def test_refresh_renders_only_first_batch(root):
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.refresh()
    assert len(panel._card_cache) <= panel.RENDER_BATCH
    assert len(panel._filtered) == 120


def test_render_batch_grows_progressively(root):
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.refresh()
    first = len(panel._card_cache)
    panel._render_batch()
    assert len(panel._card_cache) == first + panel.RENDER_BATCH


def test_search_filters_and_renders_only_match(root):
    items = [make_item(i, f"title-{i}", f"content-{i}") for i in range(120)]
    items.append(make_item(999, "special", "unique-needle-xyz"))
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("unique-needle-xyz")
    assert len(panel._filtered) == 1
    panel._render_batch()
    assert len(panel._card_cache) == 1


def test_plain_text_computed_lazily_only_for_search(root):
    items = [make_item(i, f"title-{i}", f"<b>keyword-{i}</b>") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.refresh()
    assert panel._plain_cache == {}  # 无关键词时不解析纯文本
    panel.set_search_keyword("keyword-7")
    assert panel._plain_cache  # 搜索时才解析
    assert panel._filtered and panel._filtered[0]["id"] == 7
