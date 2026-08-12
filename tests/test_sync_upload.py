import pytest
from datetime import date
from database import Database
from sync.synchronizer import Synchronizer, TABLES


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    yield db
    db.close()


@pytest.fixture
def sync(db, monkeypatch):
    monkeypatch.setattr("sync.synchronizer.is_sync_enabled", lambda: True)
    monkeypatch.setattr("sync.synchronizer.get_user_id", lambda: "user-uuid-123")
    return Synchronizer(db)


def test_tables_do_not_include_settings():
    """settings 不再参与同步，避免 watermark 互相覆盖"""
    assert "settings" not in TABLES


def test_tables_include_key_folders_and_key_items():
    """重点条目两张表应加入同步备份"""
    assert "key_folders" in TABLES
    assert "key_items" in TABLES


def test_incremental_upload_all_uploads_items_but_not_settings(sync, db, monkeypatch):
    db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    uploaded = []

    def fake_upsert(table, rows):
        uploaded.append(table)

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting",
        lambda self, k, v: None)
    sync.incremental_upload_all()
    assert "items" in uploaded
    assert "settings" not in uploaded


def test_incremental_upload_all_keeps_timestamp_on_partial_error(sync, db, monkeypatch):
    """回归：某张表上传失败时不得更新 sync_last_upload_at（防止"假成功"）"""
    from sync.client import SyncError
    db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    written = []

    def fake_upsert(table, rows):
        if table == "items":
            raise SyncError("boom")
        written.append(table)

    def fake_set_setting(self, k, v):
        written.append((k, v))

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting", fake_set_setting)
    stats = sync.incremental_upload_all()
    assert stats["items"].startswith("error:")
    assert all(k != "sync_last_upload_at" for k, _ in written)


def test_incremental_upload_all_updates_timestamp_on_full_success(sync, db, monkeypatch):
    """全部表成功后应更新 sync_last_upload_at"""
    written = []

    def fake_upsert(table, rows):
        pass

    def fake_set_setting(self, k, v):
        written.append((k, v))

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting", fake_set_setting)
    sync.incremental_upload_all()
    assert any(k == "sync_last_upload_at" for k, _ in written)


def test_parallel_incremental_uploads_are_serialized(sync, db, monkeypatch):
    """回归：并发批量上传必须串行执行（防止 watermark 回退/重复上传）"""
    import threading
    import time
    db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_upsert(table, rows):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting",
        lambda self, k, v: None)

    results = []

    def run():
        results.append(sync.incremental_upload_all())

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 3
    assert max_active == 1, f"并发上传未串行化，最大并发深度 {max_active}"


def test_upload_new_review_logs_only_since_watermark(sync, db, monkeypatch):
    db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    db.set_setting("sync_last_uploaded_log_id", "0")
    db.log_review(1, date(2026, 7, 26), 1, "perfect", 1)
    seen = {}

    def fake_upsert(table, rows):
        seen["rows"] = rows

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting",
        lambda self, k, v: None)
    sync.upload_table_incremental("review_logs")
    assert seen.get("rows"), "应有新日志被上传"
    assert all(r["local_id"] > 0 for r in seen["rows"])


def test_key_items_upload_maps_local_ids(sync, db, monkeypatch):
    """回归：key_items 上传必须把 folder_id/item_id 映射为 folder_local_id/item_local_id。
    若映射失效，云端表结构不匹配时 SyncError 会被静默吞掉、备份失效。"""
    folder_id = db.create_key_folder("易混点")
    item_id = db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    db.add_item_to_key_folder(folder_id, item_id)
    seen = {}

    def fake_upsert(table, rows):
        seen["rows"] = rows

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting",
        lambda self, k, v: None)
    sync.upload_table_incremental("key_items")
    assert seen.get("rows"), "应有 key_items 行被上传"
    row = seen["rows"][0]
    assert row["folder_local_id"] == folder_id
    assert row["item_local_id"] == item_id
    assert row["user_id"] == "user-uuid-123"
    # 不应残留未映射的本地列名
    assert "folder_id" not in row
    assert "item_id" not in row
