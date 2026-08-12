# tests/test_rebuild_dates.py
"""历史数据修复脚本（rebuild_dates）集成测试。"""
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler import Scheduler
from scripts.rebuild_dates import rebuild_item


def make_db(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE review_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            review_date TEXT NOT NULL,
            round INTEGER NOT NULL,
            result TEXT NOT NULL,
            interval_after INTEGER
        );
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            round INTEGER NOT NULL DEFAULT 1,
            interval INTEGER NOT NULL DEFAULT 0,
            consecutive_correct INTEGER NOT NULL DEFAULT 0,
            next_review_date TEXT NOT NULL
        );
    """)
    return conn


def test_rebuild_fixes_wrong_dates(tmp_path):
    """实际日期乱序时，按状态机重算为理论日期并更新下次背诵日期"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, next_review_date) VALUES (1, 'learning', '2099-01-01')")
    # 理论：第一次 06-26，第二次 = 06-26 + 1（perfect 间隔1），最终间隔 2
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-26', 1, 'perfect')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-07-10', 1, 'perfect')")  # 实际乱，应为 06-27
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "ok"
    assert len(date_changes) == 1  # 只有第二条被改
    assert date_changes[0][1] == "2026-07-10"  # 原日期
    assert date_changes[0][2] == "2026-06-27"  # 理论日期
    row = conn.execute("SELECT next_review_date FROM items WHERE id=1").fetchone()
    assert row[0] == "2026-06-29"  # 最后理论日期(06-27) + 最终间隔(2)


def test_rebuild_keeps_unmodified_when_already_correct(tmp_path):
    """日期已符合理论时不做修改"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, next_review_date) VALUES (1, 'learning', '2099-01-01')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-26', 1, 'perfect')")
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "ok"
    assert date_changes == []


def test_rebuild_skips_missing_first_date(tmp_path):
    """首次背诵日期缺失：跳过并标记人工介入"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, next_review_date) VALUES (1, 'learning', '2099-01-01')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '', 1, 'perfect')")
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "skipped_incomplete"
    assert skipped is True


def test_rebuild_unmasters_incomplete_mastered(tmp_path):
    """未完成全部档位的已掌握条目 → 撤销为学习中，保留正确档位并更新下次背诵日期"""
    conn = make_db(tmp_path / "t.db")
    # 旧逻辑误判：只有 1 条记录却标记 mastered
    conn.execute("INSERT INTO items (id, status, round, interval, consecutive_correct, "
                 "next_review_date) VALUES (1, 'mastered', 1, 34, 8, '')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-26', 1, 'perfect')")
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "ok"
    # 撤销已掌握 → 学习中，correct 重放为 1、间隔 1
    row = conn.execute("SELECT status, round, interval, consecutive_correct, next_review_date "
                       "FROM items WHERE id=1").fetchone()
    assert row[0] == "learning"
    assert row[3] == 1
    assert row[2] == 1
    assert row[4] == "2026-06-27"  # 06-26 + 1
    # item_changes 含 status 撤销记录
    status_change = [c for c in item_changes if c[0] == "status"]
    assert status_change and status_change[0][1] == "mastered" and status_change[0][2] == "learning"


def test_rebuild_keeps_completed_mastered(tmp_path):
    """完成全部 8 个档位的条目保持已掌握（不撤销），next_review_date 为空"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, round, interval, consecutive_correct, "
                 "next_review_date) VALUES (1, 'mastered', 1, 34, 8, '')")
    # 8 个背诵日全部完全正确 → correct 1..8
    day = date(2026, 6, 26)
    for i in range(8):
        conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                     "VALUES (1, ?, 1, 'perfect')", (day.isoformat(),))
        day = day + timedelta(days=[1, 2, 3, 5, 8, 13, 21][min(i, 6)])
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "ok"
    row = conn.execute("SELECT status, interval, consecutive_correct, next_review_date "
                       "FROM items WHERE id=1").fetchone()
    assert row[0] == "mastered"   # 达标不撤销
    assert row[1] == 34
    assert row[2] == 8
    assert row[3] == ""


def test_rebuild_groups_same_day_and_keeps_results(tmp_path):
    """按背诵日分组重算日期；选项内容（result）原样保留，不改动"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, next_review_date) VALUES (1, 'learning', '2099-01-01')")
    # 06-25 只有基本正确；06-26 有[基本正确, 完全正确]；07-10 完全正确（实际乱）
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-25', 1, 'mostly_correct')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-26', 1, 'mostly_correct')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-26', 1, 'perfect')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-07-10', 1, 'perfect')")
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "ok"
    assert not skipped
    # 背诵日：06-25(仅基本正确→完全正确) → 06-26(+1) → 06-28(+2)
    assert len(date_changes) == 1
    assert date_changes[0][1] == "2026-07-10"  # 原日期
    assert date_changes[0][2] == "2026-06-28"  # 理论日期
    # 选项内容原样保留（含基本正确）
    rows = conn.execute("SELECT result FROM review_logs ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["mostly_correct", "mostly_correct", "perfect", "perfect"]
    # 同一天的多条记录日期相同（06-26 两条都是 06-26）
    dates = conn.execute("SELECT review_date FROM review_logs ORDER BY id").fetchall()
    assert [d[0] for d in dates] == ["2026-06-25", "2026-06-26", "2026-06-26", "2026-06-28"]
    # interval_after：决定档位的记录=当日实际间隔；同日基本正确置空（不占档位）
    intervals = conn.execute("SELECT interval_after FROM review_logs ORDER BY id").fetchall()
    assert [i[0] for i in intervals] == [1, None, 2, 3]
    # 下次背诵日期：最后理论日期(06-28) + 最终间隔(3) = 07-01
    row = conn.execute("SELECT next_review_date FROM items WHERE id=1").fetchone()
    assert row[0] == "2026-07-01"


def test_rebuild_incomplete_loop_last_day_basic(tmp_path):
    """回归：最后一个背诵日未选完全正确 → 循环未结束，间隔置空、correct 不推进、下次=该日继续"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, round, interval, consecutive_correct, "
                 "next_review_date) VALUES (1, 'learning', 1, 34, 8, '')")
    # 三次完全正确 → correct 3（间隔 3）
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result, interval_after) "
                 "VALUES (1, '2026-06-28', 1, 'perfect', 1)")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result, interval_after) "
                 "VALUES (1, '2026-06-29', 1, 'perfect', 2)")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result, interval_after) "
                 "VALUES (1, '2026-07-04', 1, 'perfect', 3)")
    # 8-08 运行日：第1轮选基本正确，循环未结束，但旧逻辑错误写入了间隔 3
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result, interval_after) "
                 "VALUES (1, '2026-08-08', 1, 'mostly_correct', 3)")
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(
        conn, Scheduler(), 1, today=date(2026, 8, 8))
    assert status == "ok"
    # 8-08 记录的间隔被清空（待定），运行日日期保留
    row = conn.execute("SELECT interval_after, review_date FROM review_logs "
                       "WHERE review_date='2026-08-08'").fetchone()
    assert row[0] is None       # 间隔 → 待定
    assert row[1] == "2026-08-08"  # 日期保留（运行日）
    # items：correct/interval 保持进入循环前（3/3，不推进），下次背诵 = 8-08（今天继续）
    row = conn.execute("SELECT status, round, interval, consecutive_correct, next_review_date "
                       "FROM items WHERE id=1").fetchone()
    assert row[0] == "learning"
    assert row[2] == 3
    assert row[3] == 3
    assert row[4] == "2026-08-08"
    # interval_changes 记录了 3 → None
    assert any(c[1] == 3 and c[2] is None for c in interval_changes)


def test_rebuild_keeps_low_efficacy_results(tmp_path):
    """低效档位（部分正确/较多遗忘/记错了）保持原样，只改日期"""
    conn = make_db(tmp_path / "t.db")
    conn.execute("INSERT INTO items (id, status, next_review_date) VALUES (1, 'learning', '2099-01-01')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-06-25', 1, 'partial')")
    conn.execute("INSERT INTO review_logs (item_id, review_date, round, result) "
                 "VALUES (1, '2026-07-10', 1, 'perfect')")
    conn.commit()

    status, date_changes, interval_changes, item_changes, skipped = rebuild_item(conn, Scheduler(), 1)
    assert status == "ok"
    assert not skipped
    rows = conn.execute("SELECT result FROM review_logs ORDER BY id").fetchall()
    assert rows[0][0] == "partial"  # 原样保留
