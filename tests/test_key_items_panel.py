import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk

from scheduler import Scheduler
from ui.key_items_panel import KeyItemsPanel


class FakeDB:
    def __init__(self, folders, items):
        self._folders = folders
        self._items = items

    def get_key_folders(self):
        return [dict(f) for f in self._folders]

    def get_key_folder_items(self, folder_id):
        return [dict(i) for i in self._items if i["folder_id"] == folder_id]

    def create_key_folder(self, name):
        new_id = max((f["id"] for f in self._folders), default=0) + 1
        self._folders.append({"id": new_id, "name": name})
        return new_id

    def rename_key_folder(self, folder_id, new_name):
        for f in self._folders:
            if f["id"] == folder_id:
                f["name"] = new_name

    def delete_key_folder(self, folder_id):
        self._folders = [f for f in self._folders if f["id"] != folder_id]

    def get_active_items(self):
        return [dict(i) for i in self._items]

    def get_items_by_category(self, cid, include_descendants=False):
        return [dict(i) for i in self._items]

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

    def _make(folders, items):
        p = KeyItemsPanel(root, FakeDB(folders, items), Scheduler())
        panels.append(p)
        return p

    yield _make
    for p in panels:
        try:
            p.destroy()
        except Exception:
            pass


def make_folder(fid, name):
    return {"id": fid, "name": name, "sort_order": 0, "created_date": "2026-08-07"}


def make_item(iid, folder_id, title):
    return {"id": iid, "folder_id": folder_id, "title": title, "content": "c",
            "category_id": None, "notes": "", "status": "learning",
            "next_review_date": "", "round": 1, "interval": 1,
            "consecutive_correct": 0}


def test_no_folders_shows_empty_state(panel_factory):
    panel = panel_factory([], [])
    assert panel.current_folder_id is None
    assert panel.item_list._filtered == []


def test_select_folder_filters_items(panel_factory):
    folders = [make_folder(1, "易混点"), make_folder(2, "考前")]
    items = [make_item(11, 1, "刑法题"), make_item(12, 2, "民法题")]
    panel = panel_factory(folders, items)
    panel.refresh()
    panel._select_folder(1)
    assert panel.current_folder_id == 1
    assert [i["id"] for i in panel.item_list._filtered] == [11]


def test_add_folder_appears_and_selects(panel_factory):
    panel = panel_factory([], [])
    fid = panel.db.create_key_folder("新文件夹")
    panel.refresh()
    panel._select_folder(fid)
    assert panel.current_folder_id == fid
    assert fid in panel._folder_buttons
