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
