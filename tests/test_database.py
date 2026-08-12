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


def test_init_creates_performance_indexes(db):
    """热查询索引必须在 init 时创建，防止性能退化回归"""
    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}
    expected = {
        "idx_review_logs_item",
        "idx_review_logs_date",
        "idx_review_logs_date_result",
        "idx_items_status_due",
        "idx_items_category",
        "idx_items_deleted",
        "idx_categories_parent",
    }
    assert expected <= indexes


def test_init_enables_wal(db):
    """WAL 模式应持久化在库文件中（降低并发写锁竞争）"""
    row = db.conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


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


def test_count_items_due_on(db):
    """明日待背诵计数：只统计指定日期到期的 learning 条目，排除已删除/已掌握"""
    today = date(2026, 6, 26)
    tomorrow = today + timedelta(days=1)
    db.create_item("明天到期", "内容", today, tomorrow, status="learning",
                   round=1, interval=0, consecutive_correct=0)
    db.create_item("今天到期", "内容", today, today, status="learning",
                   round=1, interval=0, consecutive_correct=0)
    db.create_item("明天已掌握", "内容", today, tomorrow, status="mastered",
                   round=1, interval=34, consecutive_correct=8)
    # 软删除的明日条目不计入
    deleted = db.create_item("明天已删", "内容", today, tomorrow, status="learning",
                             round=1, interval=0, consecutive_correct=0)
    db.delete_item(deleted)
    assert db.count_items_due_on(today) == 1
    assert db.count_items_due_on(tomorrow) == 1
    assert db.count_items_due_on(today + timedelta(days=2)) == 0


def test_get_mastered_items(db):
    today = date(2026, 6, 26)
    db.create_item("已掌握", "内容", today, "", status="mastered",
                   round=1, interval=34, consecutive_correct=8)
    db.create_item("学习中", "内容", today, today, status="learning",
                   round=1, interval=0, consecutive_correct=0)
    mastered = db.get_mastered_items()
    assert len(mastered) == 1
    assert mastered[0]["title"] == "已掌握"


def test_get_due_items_includes_overdue_without_mutation(db):
    """过期条目应出现在待背列表，但 next_review_date 不被改写"""
    today = date(2026, 6, 26)
    past = today - timedelta(days=3)
    item_id = db.create_item("过期条目", "内容", today, past)
    due = db.get_due_items(today)
    assert any(i["id"] == item_id for i in due)
    row = db.conn.execute(
        "SELECT next_review_date FROM items WHERE id=?", (item_id,)).fetchone()
    assert row[0] == past.isoformat()  # 原始应背日保持不变
    assert not hasattr(db, "bring_overdue_to_today")  # 方法已删除


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


def test_get_status_counts(db):
    """测试状态计数"""
    today = date(2026, 6, 26)
    db.create_item("学习1", "内容", today, today, status="learning")
    db.create_item("学习2", "内容", today, today, status="learning")
    db.create_item("掌握1", "内容", today, today, status="mastered")
    db.create_item("归档1", "内容", today, today, status="archived")
    counts = db.get_status_counts()
    assert counts["learning"] == 2
    assert counts["mastered"] == 1
    assert counts["archived"] == 1


def test_get_perfect_count_in_range(db):
    """测试日期范围内的 perfect 计数"""
    today = date(2026, 6, 26)
    yesterday = today - timedelta(days=1)
    item_id = db.create_item("条目1", "内容", today, today)
    db.log_review(item_id, today, 1, "perfect", 1)
    db.log_review(item_id, yesterday, 1, "mostly_correct", 0)
    # 今日 perfect 数
    assert db.get_perfect_count_in_range(today, today) == 1
    # 昨日 perfect 数
    assert db.get_perfect_count_in_range(yesterday, yesterday) == 0
    # 两天合计 perfect 数
    assert db.get_perfect_count_in_range(yesterday, today) == 1


def test_get_category_progress(db):
    """测试分类进度统计（含子孙分类）"""
    today = date(2026, 6, 26)
    # 顶层分类：语文
    cat_id = db.create_category("语文", parent_id=None)
    sub_id = db.create_category("唐诗", parent_id=cat_id)
    # 语文分类下：1个learning, 1个mastered
    db.create_item("静夜思", "内容", today, today, status="learning", category_id=cat_id)
    db.create_item("春晓", "内容", today, today, status="mastered", category_id=sub_id)
    # 未分类条目不计入任何分类进度
    db.create_item("无分类", "内容", today, today, status="learning")

    progress = db.get_category_progress()
    assert len(progress) == 1
    assert progress[0]["name"] == "语文"
    assert progress[0]["total"] == 2  # 含子分类的条目
    assert progress[0]["learning"] == 1
    assert progress[0]["mastered"] == 1
    assert progress[0]["archived"] == 0


def test_items_table_has_notes_field(db):
    """items 表应包含 notes 字段"""
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(items)")}
    assert "notes" in cols


def test_item_marks_table_exists(db):
    """item_marks 表应存在"""
    cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "item_marks" in tables


def test_settings_table_exists(db):
    """settings 表应存在"""
    cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "settings" in tables


def test_create_item_default_notes_empty(db):
    """新建条目 notes 默认为空字符串"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "内容", today, today)
    item = db.get_item(item_id)
    assert item["notes"] == ""


def test_update_item_notes(db):
    """update_item 应能更新 notes 字段"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "内容", today, today)
    db.update_item(item_id, notes="这是笔记")
    item = db.get_item(item_id)
    assert item["notes"] == "这是笔记"


def test_add_and_get_marks(db):
    """新增标记并查询"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    mark_id = db.add_mark(item_id, 2, 5, "forgot")
    assert mark_id > 0
    marks = db.get_marks(item_id)
    assert len(marks) == 1
    assert marks[0]["start_pos"] == 2
    assert marks[0]["end_pos"] == 5
    assert marks[0]["mark_type"] == "forgot"
    assert marks[0]["id"] == mark_id


def test_get_marks_sorted_by_start(db):
    """get_marks 应按 start_pos 升序返回"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    db.add_mark(item_id, 5, 7, "fuzzy")
    db.add_mark(item_id, 0, 2, "forgot")
    marks = db.get_marks(item_id)
    assert marks[0]["start_pos"] == 0
    assert marks[1]["start_pos"] == 5


def test_delete_mark(db):
    """删除标记"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    mark_id = db.add_mark(item_id, 0, 2, "forgot")
    db.delete_mark(mark_id)
    marks = db.get_marks(item_id)
    assert len(marks) == 0


def test_delete_item_soft_delete_and_restore(db):
    """删除条目应软删除（保留数据和标记），可恢复；彻底删除才级联清理标记"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    db.add_mark(item_id, 0, 2, "forgot")

    # 软删除：标记 deleted_at，但数据与标记保留（便于恢复）
    db.delete_item(item_id)
    deleted_items = db.get_deleted_items()
    assert any(i["id"] == item_id for i in deleted_items)
    # 标记仍保留（恢复后可继续使用）
    assert len(db.get_marks(item_id)) == 1
    # 软删除后不在常规查询中
    assert all(i["id"] != item_id for i in db.get_active_items())

    # 恢复：清除 deleted_at，条目回到常规查询
    db.restore_item(item_id)
    assert all(i["id"] != item_id for i in db.get_deleted_items())
    assert any(i["id"] == item_id for i in db.get_active_items())

    # 彻底删除：级联清理标记
    db.delete_item(item_id)  # 先软删除
    db.purge_item(item_id)
    assert len(db.get_marks(item_id)) == 0
    assert db.get_item(item_id) is None


def test_get_marks_filters_invalid(db):
    """get_marks 应过滤掉 start>=end 或超出 content 长度的非法标记"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abc", today, today)
    db.add_mark(item_id, 0, 3, "forgot")    # 合法
    db.add_mark(item_id, 2, 2, "fuzzy")     # 非法：start==end
    db.add_mark(item_id, 0, 10, "fuzzy")    # 非法：end 超出 content 长度
    marks = db.get_marks(item_id)
    assert len(marks) == 1
    assert marks[0]["start_pos"] == 0


def test_setting_get_and_set(db):
    """settings 读写"""
    assert db.get_setting("content_font_size", "14") == "14"
    db.set_setting("content_font_size", "18")
    assert db.get_setting("content_font_size", "14") == "18"
    db.set_setting("content_font_size", "20")
    assert db.get_setting("content_font_size", "14") == "20"


def test_setting_persists_across_connection(db):
    """settings 应跨连接持久化"""
    db.set_setting("content_box_height", "400")
    db_path = db.db_path
    db.close()
    db2 = Database(db_path)
    db2.init()
    assert db2.get_setting("content_box_height", "200") == "400"
    db2.close()


def test_shift_marks_on_content_edit(db):
    """编辑正文（末尾删除）后：编辑点之前的标记不变，被删内容覆盖的标记删除"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "0123456789", today, today)  # 长度10
    db.add_mark(item_id, 2, 5, "forgot")   # 标记 "234"，在编辑点之前
    db.add_mark(item_id, 7, 9, "fuzzy")    # 标记 "78"，在被删除的区段内
    # 把正文缩短为长度5：01234（删掉末尾5个字）
    db.update_item(item_id, content="01234")
    marks = db.get_marks(item_id)
    # 标记1 [2,5] 在前缀"01234"内 → 位置不变
    # 标记2 [7,9] 在被删区段内 → 删除
    assert len(marks) == 1
    assert marks[0]["start_pos"] == 2
    assert marks[0]["end_pos"] == 5


def test_shift_marks_insert_at_start(db):
    """在开头插入字符：之后的标记应整体增量平移，不按比例缩放"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "0123456789", today, today)  # 长度10
    db.add_mark(item_id, 2, 5, "forgot")   # 标记 "234"
    db.add_mark(item_id, 7, 9, "fuzzy")    # 标记 "78"
    # 在开头插入 "X"，新内容 "X0123456789"（长度11）
    db.update_item(item_id, content="X0123456789")
    marks = db.get_marks(item_id)
    # 公共前缀=0，公共后缀=10（"0123456789"），编辑区段在 old=[0,0)，在 new=[0,1)
    # delta = 1 - 0 = 1
    # 标记1 [2,5]：start(2)>=old_edit_end(0) → 平移 → [3,6]
    # 标记2 [7,9]：start(7)>=old_edit_end(0) → 平移 → [8,10]
    assert len(marks) == 2
    m1 = next(m for m in marks if m["mark_type"] == "forgot")
    m2 = next(m for m in marks if m["mark_type"] == "fuzzy")
    assert (m1["start_pos"], m1["end_pos"]) == (3, 6)
    assert (m2["start_pos"], m2["end_pos"]) == (8, 10)


def test_shift_marks_delete_in_middle(db):
    """在中间删除字符：删除点之前的标记不变，之后的标记按 delta 平移"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "0123456789", today, today)  # 长度10
    db.add_mark(item_id, 1, 3, "forgot")   # 标记 "12"，在删除点之前
    db.add_mark(item_id, 7, 9, "fuzzy")    # 标记 "78"，在删除点之后
    # 删除 "345"（位置3-6），新内容 "0126789"（长度7）
    db.update_item(item_id, content="0126789")
    marks = db.get_marks(item_id)
    # 公共前缀=3（"012"），公共后缀=3（"789"）
    # 编辑区段在 old=[3,7)，在 new=[3,4)
    # delta = 4 - 7 = -3
    # 标记1 [1,3]：end(3)<=prefix_len(3) → 不变 → [1,3]
    # 标记2 [7,9]：start(7)>=old_edit_end(7) → 平移 -3 → [4,6]
    assert len(marks) == 2
    m1 = next(m for m in marks if m["mark_type"] == "forgot")
    m2 = next(m for m in marks if m["mark_type"] == "fuzzy")
    assert (m1["start_pos"], m1["end_pos"]) == (1, 3)
    assert (m2["start_pos"], m2["end_pos"]) == (4, 6)


def test_shift_marks_no_change(db):
    """正文未变化（或只改了 HTML 标签）：所有标记位置不变"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    db.add_mark(item_id, 1, 4, "forgot")
    db.update_item(item_id, content="abcdefg")  # 相同纯文本
    marks = db.get_marks(item_id)
    assert len(marks) == 1
    assert (marks[0]["start_pos"], marks[0]["end_pos"]) == (1, 4)


def test_shift_marks_clears_when_content_empty(db):
    """正文清空后，标记应全部删除"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    db.add_mark(item_id, 0, 3, "forgot")
    db.update_item(item_id, content="")
    marks = db.get_marks(item_id)
    assert len(marks) == 0


def test_shift_marks_not_triggered_on_other_fields(db):
    """只更新非 content 字段时，不应触发平移"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    db.add_mark(item_id, 0, 3, "forgot")
    db.update_item(item_id, status="mastered")
    marks = db.get_marks(item_id)
    assert len(marks) == 1
    assert marks[0]["start_pos"] == 0
    assert marks[0]["end_pos"] == 3
