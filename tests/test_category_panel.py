import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk

from ui.category_panel import CategoryPanel


class FakeDB:
    def __init__(self, cats):
        self._cats = [dict(c) for c in cats]

    def get_categories(self):
        return [dict(c) for c in self._cats]

    def create_category(self, name, parent_id=None):
        new_id = max((c["id"] for c in self._cats), default=0) + 1
        self._cats.append({"id": new_id, "name": name,
                           "parent_id": parent_id, "sort_order": len(self._cats)})
        return new_id

    def rename_category(self, cat_id, new_name):
        for c in self._cats:
            if c["id"] == cat_id:
                c["name"] = new_name

    def delete_category(self, cat_id):
        self._cats = [c for c in self._cats if c["id"] != cat_id]

    def move_category(self, cat_id, direction):
        pass

    def get_items_by_category(self, cat_id, include_descendants=True):
        return []

    def batch_update_round2(self, item_ids, today):
        pass


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

    def _make(cats):
        p = CategoryPanel(root, FakeDB(cats))
        panels.append(p)
        return p

    yield _make
    for p in panels:
        try:
            p.destroy()
        except Exception:
            pass


def make_cats():
    return [
        {"id": 1, "name": "刑法", "parent_id": None, "sort_order": 0},
        {"id": 2, "name": "总则", "parent_id": 1, "sort_order": 0},
    ]


def find_node(tree, node, cat_id):
    values = tree.item(node, "values")
    if values and values[0] not in (None, "None", ""):
        try:
            if int(values[0]) == cat_id:
                return node
        except (ValueError, TypeError):
            pass
    for child in tree.get_children(node):
        found = find_node(tree, child, cat_id)
        if found:
            return found
    return None


def is_open(tree, node):
    return bool(tree.item(node, "open"))


def test_categories_collapsed_by_default(panel_factory):
    panel = panel_factory(make_cats())
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    assert cat1 is not None
    assert is_open(panel.tree, cat1) is False  # 默认折叠


def test_manual_expand_preserved_after_refresh(panel_factory):
    panel = panel_factory(make_cats())
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    panel.tree.item(cat1, open=True)  # 手动展开
    panel.refresh()
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    assert is_open(panel.tree, cat1) is True  # 刷新后保持展开


def test_manual_collapse_preserved_after_refresh(panel_factory):
    panel = panel_factory(make_cats())
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    panel.tree.item(cat1, open=True)
    panel.tree.item(cat1, open=False)  # 手动折叠
    panel.refresh()
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    assert is_open(panel.tree, cat1) is False  # 刷新后保持折叠


def test_add_category_keeps_existing_state(panel_factory):
    panel = panel_factory(make_cats())
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    panel.tree.item(cat1, open=True)
    panel.db.create_category("新分类", parent_id=None)  # 模拟新增文件夹
    panel.refresh()
    root_node = panel.tree.get_children("")[0]
    cat1 = find_node(panel.tree, root_node, 1)
    new_node = find_node(panel.tree, root_node, 3)
    assert is_open(panel.tree, cat1) is True  # 原文件夹保持展开
    assert new_node is not None
    assert is_open(panel.tree, new_node) is False  # 新文件夹默认折叠
