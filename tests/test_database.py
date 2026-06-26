# tests/test_database.py
import pytest
from datetime import date, timedelta
from database import Database


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    yield db
    db.close()


def test_init_creates_tables(db):
    cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "categories" in tables
    assert "items" in tables
    assert "review_logs" in tables


def test_items_table_has_new_fields(db):
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(items)")}
    assert "status" in cols
    assert "round" in cols
    assert "interval" in cols
    assert "consecutive_correct" in cols
    assert "next_review_date" in cols
    assert "category_id" in cols
    # 旧字段不应存在
    assert "current_stage" not in cols
    assert "cycle_type" not in cols
    assert "cycle_start_date" not in cols
    assert "memory_strength" not in cols


def test_create_item(db):
    today = date(2026, 6, 26)
    item_id = db.create_item(
        title="测试", content="内容", created_date=today,
        next_review_date=today, status="learning",
        round=1, interval=0, consecutive_correct=0
    )
    assert item_id > 0
    item = db.get_item(item_id)
    assert item["title"] == "测试"
    assert item["round"] == 1
    assert item["interval"] == 0
    assert item["consecutive_correct"] == 0
    assert item["status"] == "learning"


def test_get_due_items(db):
    today = date(2026, 6, 26)
    db.create_item("到期", "内容", today, today, status="learning",
                   round=1, interval=0, consecutive_correct=0)
    db.create_item("未到期", "内容", today, today + __import__("datetime").timedelta(days=5),
                   status="learning", round=1, interval=5, consecutive_correct=4)
    db.create_item("已完成", "内容", today, "", status="mastered",
                   round=1, interval=34, consecutive_correct=8)
    due = db.get_due_items(today)
    assert len(due) == 1
    assert due[0]["title"] == "到期"


def test_get_mastered_items(db):
    today = date(2026, 6, 26)
    db.create_item("已掌握", "内容", today, "", status="mastered",
                   round=1, interval=34, consecutive_correct=8)
    db.create_item("学习中", "内容", today, today, status="learning",
                   round=1, interval=0, consecutive_correct=0)
    mastered = db.get_mastered_items()
    assert len(mastered) == 1
    assert mastered[0]["title"] == "已掌握"


def test_bring_overdue_to_today(db):
    today = date(2026, 6, 26)
    yesterday = today - timedelta(days=1)
    db.create_item("过期", "内容", yesterday, yesterday, status="learning",
                   round=1, interval=1, consecutive_correct=1)
    db.bring_overdue_to_today(today)
    due = db.get_due_items(today)
    assert len(due) == 1
    assert due[0]["title"] == "过期"


def test_log_and_get_review_logs(db):
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "内容", today, today, status="learning",
                             round=1, interval=0, consecutive_correct=0)
    db.log_review(item_id, today, 1, "perfect", 1)
    logs = db.get_review_logs(item_id)
    assert len(logs) == 1
    assert logs[0]["result"] == "perfect"
    assert logs[0]["round"] == 1
    assert logs[0]["interval_after"] == 1


def test_batch_update_for_round2(db):
    today = date(2026, 6, 26)
    id1 = db.create_item("条目1", "内容", today, "", status="mastered",
                         round=1, interval=34, consecutive_correct=8)
    id2 = db.create_item("条目2", "内容", today, "", status="mastered",
                         round=1, interval=34, consecutive_correct=8)
    db.batch_update_round2([id1, id2], today)
    item1 = db.get_item(id1)
    assert item1["round"] == 2
    assert item1["status"] == "learning"
    assert item1["consecutive_correct"] == 0
    assert item1["next_review_date"] == today.isoformat()


def test_category_crud_unchanged(db):
    cat_id = db.create_category("英语", None)
    sub_id = db.create_category("单词", cat_id)
    children = db.get_category_children(cat_id)
    assert len(children) == 1
    assert children[0]["name"] == "单词"


def test_update_item_allowed_fields(db):
    """update_item 应更新白名单内字段"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "内容", today, today, status="learning",
                             round=1, interval=0, consecutive_correct=0)
    db.update_item(item_id, status="mastered", round=2, interval=14,
                   consecutive_correct=3, next_review_date="")
    item = db.get_item(item_id)
    assert item["status"] == "mastered"
    assert item["round"] == 2
    assert item["interval"] == 14
    assert item["consecutive_correct"] == 3
    assert item["next_review_date"] == ""


def test_update_item_ignores_non_allowed_fields(db):
    """update_item 应忽略白名单外的字段（如 id），不污染主键"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "内容", today, today, status="learning",
                             round=1, interval=0, consecutive_correct=0)
    # 传入 id 和不存在的字段，都应被忽略
    db.update_item(item_id, id=999, foo="bar", title="新标题")
    item = db.get_item(item_id)
    assert item["id"] == item_id  # 主键未被篡改
    assert item["title"] == "新标题"  # 白名单内字段已更新


def test_update_item_converts_date_object_to_iso(db):
    """update_item 接收 date 对象时应转为 isoformat 字符串存储"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "内容", today, today, status="learning",
                             round=1, interval=0, consecutive_correct=0)
    future = today + timedelta(days=5)
    db.update_item(item_id, next_review_date=future)
    item = db.get_item(item_id)
    assert item["next_review_date"] == future.isoformat()


def test_get_mastered_items_includes_archived(db):
    """get_mastered_items 应同时返回 mastered 和 archived 状态"""
    today = date(2026, 6, 26)
    db.create_item("已掌握", "内容", today, "", status="mastered",
                   round=1, interval=34, consecutive_correct=8)
    db.create_item("已归档", "内容", today, "", status="archived",
                   round=2, interval=14, consecutive_correct=3)
    db.create_item("学习中", "内容", today, today, status="learning",
                   round=1, interval=0, consecutive_correct=0)
    mastered = db.get_mastered_items()
    titles = {m["title"] for m in mastered}
    assert "已掌握" in titles
    assert "已归档" in titles
    assert "学习中" not in titles
    assert len(mastered) == 2


def test_get_today_reviewed_item_ids(db):
    """get_today_reviewed_item_ids 返回今日有 review_logs 的 item_id 集合"""
    today = date(2026, 6, 26)
    yesterday = today - timedelta(days=1)
    id1 = db.create_item("条目1", "内容", today, today, status="learning",
                         round=1, interval=0, consecutive_correct=0)
    id2 = db.create_item("条目2", "内容", today, today, status="learning",
                         round=1, interval=0, consecutive_correct=0)
    # id1 今日有日志，id2 昨日有日志
    db.log_review(id1, today, 1, "perfect", 1)
    db.log_review(id2, yesterday, 1, "perfect", 1)
    reviewed_today = db.get_today_reviewed_item_ids(today)
    assert reviewed_today == {id1}
    # 昨日的查询应返回 id2
    reviewed_yesterday = db.get_today_reviewed_item_ids(yesterday)
    assert reviewed_yesterday == {id2}
