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


def make_item(iid, title, content, category_id=None):
    return {"id": iid, "title": title, "content": content,
            "category_id": category_id, "notes": "", "status": "learning",
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


def test_search_title(panel_factory):
    items = [
        make_item(1, "唐诗春晓", "春眠不觉晓"),
        make_item(2, "宋词", "大江东去"),
    ]
    panel = panel_factory(items)
    panel.set_search_keyword("唐诗")
    assert [i["id"] for i in panel._filtered] == [1]


def test_search_content_html(panel_factory):
    items = [
        make_item(1, "题目", "普通文本"),
        make_item(2, "宋词", "大江东去 <b>千古</b>风流人物"),
    ]
    panel = panel_factory(items)
    panel.set_search_keyword("千古")
    assert [i["id"] for i in panel._filtered] == [2]


def test_search_case_insensitive(panel_factory):
    items = [
        make_item(1, "英语单词", "abandon 放弃"),
        make_item(2, "Abandon 复习", "再次复习 abandon"),
        make_item(3, "历史笔记", "唐朝建立"),
    ]
    panel = panel_factory(items)
    panel.set_search_keyword("abandon")
    assert sorted(i["id"] for i in panel._filtered) == [1, 2]


def test_search_no_match(panel_factory):
    items = [make_item(1, "唐诗", "内容")]
    panel = panel_factory(items)
    panel.set_search_keyword("不存在的关键词xyz")
    assert panel._filtered == []


def test_search_html_tag_not_matched(panel_factory):
    items = [make_item(1, "宋词", "大江东去 <b>千古</b>风流人物")]
    panel = panel_factory(items)
    panel.set_search_keyword("<b>")
    assert panel._filtered == []


def test_search_combined_with_category_filter(panel_factory):
    items = [make_item(1, "唐诗春晓", "春眠不觉晓", category_id=1),
             make_item(2, "宋词", "大江东去", category_id=None)]
    panel = panel_factory(items)
    panel.filter_category_id = "uncategorized"
    panel.refresh()
    panel.set_search_keyword("宋词")
    assert [i["id"] for i in panel._filtered] == [2]
