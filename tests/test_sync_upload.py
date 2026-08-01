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
