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

def test_get_due_items_returns_items_with_next_review_on_or_before_today(tmp_path):
    from datetime import date, timedelta
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)

    # 条目A：今天到期
    db.create_item("A", "contentA", today - timedelta(days=1), today)
    # 条目B：明天到期
    db.create_item("B", "contentB", today, today + timedelta(days=1))
    # 条目C：昨天到期（漏打卡）
    db.create_item("C", "contentC", today - timedelta(days=2), today - timedelta(days=1))

    due = db.get_due_items(today)
    titles = {item["title"] for item in due}
    assert titles == {"A", "C"}

def test_get_due_items_excludes_mastered(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    item_id = db.create_item("A", "contentA", today, today)
    db.conn.execute("UPDATE items SET status='mastered' WHERE id=?", (item_id,))
    db.conn.commit()

    due = db.get_due_items(today)
    assert len(due) == 0

def test_get_active_items_returns_learning_and_pending(tmp_path):
    from datetime import date, timedelta
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    id1 = db.create_item("A", "cA", today, today)
    id2 = db.create_item("B", "cB", today, today)
    db.conn.execute("UPDATE items SET status='mastered' WHERE id=?", (id2,))
    db.conn.commit()

    active = db.get_active_items()
    assert len(active) == 1
    assert active[0]["title"] == "A"

def test_get_mastered_items_returns_only_mastered(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    id1 = db.create_item("A", "cA", today, today)
    id2 = db.create_item("B", "cB", today, today)
    db.conn.execute("UPDATE items SET status='mastered' WHERE id=?", (id1,))
    db.conn.commit()

    mastered = db.get_mastered_items()
    assert len(mastered) == 1
    assert mastered[0]["title"] == "A"
