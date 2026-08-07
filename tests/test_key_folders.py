import pytest
from datetime import date

from database import Database


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    yield db
    db.close()


def test_key_folder_crud(db):
    fid = db.create_key_folder("易混点")
    folders = db.get_key_folders()
    assert len(folders) == 1
    assert folders[0]["name"] == "易混点"

    db.rename_key_folder(fid, "考前冲刺")
    assert db.get_key_folders()[0]["name"] == "考前冲刺"

    db.delete_key_folder(fid)
    assert db.get_key_folders() == []


def test_add_remove_and_multi_folder(db):
    fid1 = db.create_key_folder("A")
    fid2 = db.create_key_folder("B")
    iid = db.create_item("t", "c", date(2026, 8, 7), date(2026, 8, 7))
    db.add_item_to_key_folder(fid1, iid)
    db.add_item_to_key_folder(fid2, iid)
    assert len(db.get_key_folder_items(fid1)) == 1
    assert db.is_item_in_key_folder(fid1, iid) is True

    db.remove_item_from_key_folder(fid1, iid)
    assert db.get_key_folder_items(fid1) == []
    assert len(db.get_key_folder_items(fid2)) == 1


def test_delete_folder_clears_links_keeps_item(db):
    fid = db.create_key_folder("A")
    iid = db.create_item("t", "c", date(2026, 8, 7), date(2026, 8, 7))
    db.add_item_to_key_folder(fid, iid)
    db.delete_key_folder(fid)
    assert db.get_key_folders() == []
    assert db.get_item(iid) is not None  # 条目本身不受影响


def test_soft_deleted_items_excluded_from_folder(db):
    fid = db.create_key_folder("A")
    iid = db.create_item("t", "c", date(2026, 8, 7), date(2026, 8, 7))
    db.add_item_to_key_folder(fid, iid)
    db.delete_item(iid)  # 软删除
    assert db.get_key_folder_items(fid) == []


def test_folder_sort_order_follows_creation(db):
    f1 = db.create_key_folder("第一")
    f2 = db.create_key_folder("第二")
    assert [f["id"] for f in db.get_key_folders()] == [f1, f2]
