import os
import tempfile
from database import Database

def test_init_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.init()

    # 验证 items 表存在且有正确字段
    cursor = db.conn.execute("PRAGMA table_info(items)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {
        "id", "title", "content", "created_date",
        "status", "current_stage", "next_review_date",
        "cycle_start_date", "cycle_type"
    }

    # 验证 review_logs 表存在且有正确字段
    cursor = db.conn.execute("PRAGMA table_info(review_logs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {"id", "item_id", "review_date", "stage_completed", "result"}

def test_create_item_returns_id_and_persists(tmp_path):
    from datetime import date, timedelta
    db = Database(str(tmp_path / "test.db"))
    db.init()

    today = date(2026, 6, 25)
    next_review = today + timedelta(days=1)
    item_id = db.create_item("静夜思", "床前明月光...", today, next_review)

    assert item_id > 0
    cursor = db.conn.execute("SELECT title, content, status, current_stage, cycle_type FROM items WHERE id=?", (item_id,))
    row = cursor.fetchone()
    assert row == ("静夜思", "床前明月光...", "learning", 1, "full")
