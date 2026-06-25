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
        "cycle_start_date", "cycle_type", "category_id"
    }

    # 验证 review_logs 表存在且有正确字段
    cursor = db.conn.execute("PRAGMA table_info(review_logs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {"id", "item_id", "review_date", "stage_completed", "result"}

    # 验证 categories 表存在且有正确字段
    cursor = db.conn.execute("PRAGMA table_info(categories)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {"id", "name", "parent_id"}

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

def test_update_item_status_and_stage(tmp_path):
    from datetime import date, timedelta
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    item_id = db.create_item("A", "cA", today, today)

    db.update_item(item_id, status="pending_mastery", current_stage=6,
                   next_review_date=today, cycle_start_date=today, cycle_type="full")
    item = db.get_item(item_id)
    assert item["status"] == "pending_mastery"
    assert item["current_stage"] == 6

def test_log_review_records_entry(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    item_id = db.create_item("A", "cA", today, today)

    db.log_review(item_id, today, stage_completed=1, result="done")
    cursor = db.conn.execute("SELECT item_id, review_date, stage_completed, result FROM review_logs")
    row = cursor.fetchone()
    assert row == (item_id, today.isoformat(), 1, "done")

# ===== 分类 CRUD 测试 =====

def test_create_category_top_level(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    cat_id = db.create_category("英语")
    assert cat_id > 0
    cats = db.get_categories()
    assert len(cats) == 1
    assert cats[0] == {"id": cat_id, "name": "英语", "parent_id": None}

def test_create_category_nested(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    parent_id = db.create_category("英语")
    child_id = db.create_category("单词", parent_id=parent_id)
    children = db.get_category_children(parent_id)
    assert len(children) == 1
    assert children[0]["name"] == "单词"
    assert children[0]["parent_id"] == parent_id

def test_get_category_children_top_level(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    db.create_category("英语")
    db.create_category("语文")
    top = db.get_category_children(None)
    names = {c["name"] for c in top}
    assert names == {"英语", "语文"}

def test_rename_category(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    cat_id = db.create_category("英语")
    db.rename_category(cat_id, "English")
    cats = db.get_categories()
    assert cats[0]["name"] == "English"

def test_delete_category_cascade_children(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    parent_id = db.create_category("英语")
    db.create_category("单词", parent_id=parent_id)
    db.delete_category(parent_id)
    cats = db.get_categories()
    assert len(cats) == 0  # 子分类被级联删除

def test_delete_category_sets_items_category_null(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    cat_id = db.create_category("英语")
    item_id = db.create_item("A", "cA", today, today, category_id=cat_id)
    db.delete_category(cat_id)
    item = db.get_item(item_id)
    assert item["category_id"] is None

def test_get_category_path(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    id1 = db.create_category("英语")
    id2 = db.create_category("单词", parent_id=id1)
    id3 = db.create_category("高频词", parent_id=id2)
    path = db.get_category_path(id3)
    assert [c["name"] for c in path] == ["英语", "单词", "高频词"]

def test_create_item_with_category(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    cat_id = db.create_category("英语")
    item_id = db.create_item("A", "cA", today, today, category_id=cat_id)
    item = db.get_item(item_id)
    assert item["category_id"] == cat_id

def test_create_item_with_backfill_fields(tmp_path):
    """验证 create_item 支持指定 current_stage/cycle_type/cycle_start_date/status"""
    from datetime import date, timedelta
    db = Database(str(tmp_path / "test.db"))
    db.init()
    start = date(2026, 6, 20)
    today = date(2026, 6, 25)
    item_id = db.create_item(
        "A", "cA", start, today,
        current_stage=3, cycle_type="full",
        cycle_start_date=start, status="learning"
    )
    item = db.get_item(item_id)
    assert item["current_stage"] == 3
    assert item["cycle_start_date"] == start.isoformat()
    assert item["status"] == "learning"

def test_get_category_descendant_ids(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    id1 = db.create_category("英语")
    id2 = db.create_category("单词", parent_id=id1)
    id3 = db.create_category("高频词", parent_id=id2)
    id4 = db.create_category("低频词", parent_id=id2)
    ids = db.get_category_descendant_ids(id2)
    assert set(ids) == {id2, id3, id4}

def test_get_items_by_category_includes_descendants(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    id1 = db.create_category("英语")
    id2 = db.create_category("单词", parent_id=id1)
    db.create_item("A", "cA", today, today, category_id=id1)
    db.create_item("B", "cB", today, today, category_id=id2)
    db.create_item("C", "cC", today, today, category_id=None)
    # 查 id1（含子孙）应返回 A 和 B
    items = db.get_items_by_category(id1)
    titles = {i["title"] for i in items}
    assert titles == {"A", "B"}
    # 查未分类应返回 C
    items = db.get_items_by_category(None)
    titles = {i["title"] for i in items}
    assert titles == {"C"}

def test_update_item_category(tmp_path):
    from datetime import date
    db = Database(str(tmp_path / "test.db"))
    db.init()
    today = date(2026, 6, 25)
    cat_id = db.create_category("英语")
    item_id = db.create_item("A", "cA", today, today)
    db.update_item(item_id, category_id=cat_id)
    item = db.get_item(item_id)
    assert item["category_id"] == cat_id

def test_init_adds_category_id_to_legacy_db(tmp_path):
    """验证旧库（无 category_id 列）init 后自动补列"""
    from datetime import date
    db_path = tmp_path / "legacy.db"
    # 模拟旧库结构
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT,
        created_date TEXT, status TEXT, current_stage INTEGER,
        next_review_date TEXT, cycle_start_date TEXT, cycle_type TEXT
    )""")
    conn.execute("INSERT INTO items (title, content, created_date, status, current_stage, next_review_date, cycle_start_date, cycle_type) VALUES ('A','c','2026-06-25','learning',1,'2026-06-26','2026-06-25','full')")
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    db.init()  # 应自动补 category_id 列
    item = db.get_item(1)
    assert item["category_id"] is None
    assert item["title"] == "A"
