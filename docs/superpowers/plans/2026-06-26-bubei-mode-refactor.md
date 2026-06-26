# 不背单词模式重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将固定艾宾浩斯曲线重构为「不背单词」式4级评分动态间隔算法，含二轮巩固和统计面板

**Architecture:** 三层架构：database.py（SQLite持久化）→ scheduler.py（4级评分调度算法）→ ui/（卡片式交互）。清空重建数据库，旧数据不保留。

**Tech Stack:** Python, CustomTkinter, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-06-26-bubei-mode-refactor-design.md`

---

## 文件结构

**重写：**
- `scheduler.py` — 4级评分算法，斐波那契间隔序列
- `database.py` — 新表结构（items含round/interval/consecutive_correct，删除旧字段）
- `ui/review_panel.py` — 卡片式单张展示，4级评分交互

**适配修改：**
- `ui/list_panels.py` — 状态文案、补签逻辑适配新字段
- `ui/history_dialog.py` — 列名和结果映射适配4级评分
- `ui/main_window.py` — 标签页文案，新增统计面板
- `ui/backfill_dialog.py` — 补签时选择result（4级评分之一）
- `ui/category_panel.py` — 新增二轮巩固按钮
- `ui/add_dialog.py` — 适配新字段（无需cycle_type等）

**新增：**
- `ui/stats_panel.py` — 统计面板

**删除：**
- `ui/mastery_dialog.py` — 不再需要掌握确认对话框

**测试：**
- `tests/test_scheduler.py` — 完全重写
- `tests/test_database.py` — 适配新表结构

---

## Task 1: 重写 scheduler.py 核心4级评分算法

**Files:**
- Rewrite: `scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: 写测试文件（覆盖所有算法分支）**

```python
# tests/test_scheduler.py
from datetime import date, timedelta
from scheduler import Scheduler

def test_round1_intervals():
    s = Scheduler()
    assert s.ROUND1_INTERVALS == [1, 2, 3, 5, 8, 13, 21, 34]

def test_round2_intervals():
    s = Scheduler()
    assert s.ROUND2_INTERVALS == [3, 7, 14]

def test_schedule_new_item_initial_state():
    s = Scheduler()
    today = date(2026, 6, 26)
    result = s.schedule_new_item(today)
    assert result["status"] == "learning"
    assert result["round"] == 1
    assert result["interval"] == 0
    assert result["consecutive_correct"] == 0
    assert result["next_review_date"] == today

def test_process_review_perfect_first_time():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1  # ROUND1_INTERVALS[0]
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is False
    assert result["status"] == "learning"

def test_process_review_perfect_completes_round1():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 8
    assert result["status"] == "mastered"
    assert result["next_review_date"] == ""
    assert result["requeue_today"] is False

def test_process_review_perfect_completes_round2():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 2, "interval": 7, "consecutive_correct": 2, "status": "learning"}
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 3
    assert result["status"] == "archived"
    assert result["next_review_date"] == ""

def test_process_review_mostly_correct_first_time():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "mostly_correct", is_retest=False)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is True

def test_process_review_mostly_correct_retest():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 5, "consecutive_correct": 4, "status": "learning"}
    result = s.process_review(item, today, "mostly_correct", is_retest=True)
    assert result["consecutive_correct"] == 4  # 不变
    assert result["interval"] == 5  # 不变
    assert result["next_review_date"] is None  # 不更新数据库
    assert result["requeue_today"] is True

def test_process_review_partial_normal():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 13, "consecutive_correct": 6, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 4  # 6-2
    assert result["interval"] == 5  # ROUND1_INTERVALS[3]
    assert result["next_review_date"] == today + timedelta(days=5)
    assert result["requeue_today"] is True

def test_process_review_partial_at_zero():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 1, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is True

def test_process_review_wrong():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, today, "wrong", is_retest=False)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is True

def test_start_round2():
    s = Scheduler()
    today = date(2026, 6, 26)
    items = [
        {"id": 1, "round": 1, "interval": 34, "consecutive_correct": 8, "status": "mastered"},
        {"id": 2, "round": 1, "interval": 34, "consecutive_correct": 8, "status": "mastered"},
    ]
    results = s.start_round2(items, today)
    for r in results:
        assert r["round"] == 2
        assert r["status"] == "learning"
        assert r["interval"] == 0
        assert r["consecutive_correct"] == 0
        assert r["next_review_date"] == today
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL（模块不存在或类不匹配）

- [ ] **Step 3: 实现 scheduler.py**

```python
# scheduler.py
from datetime import date, timedelta


class Scheduler:
    ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
    ROUND2_INTERVALS = [3, 7, 14]

    def schedule_new_item(self, today: date) -> dict:
        """新建条目初始状态：今天就要背第1次"""
        return {
            "status": "learning",
            "round": 1,
            "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        }

    def process_review(self, item: dict, today: date, result: str,
                       is_retest: bool = False) -> dict:
        """处理用户的4级评分反馈，返回新的调度状态。

        is_retest: True 表示该条目今日非首次出现（重背评分）。
        返回值含 requeue_today 字段：True 表示需追加到今日队列末尾。
        next_review_date 为 None 表示不更新数据库。
        """
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        current_correct = item["consecutive_correct"]

        if result == "perfect":
            new_correct = current_correct + 1
            return self._build_result(item["round"], round_intervals, new_correct, today)

        elif result == "mostly_correct":
            if is_retest:
                return {
                    "status": item["status"], "round": item["round"],
                    "interval": item["interval"],
                    "consecutive_correct": current_correct,
                    "next_review_date": None,
                    "requeue_today": True
                }
            else:
                new_correct = current_correct + 1
                return self._build_result(item["round"], round_intervals, new_correct, today,
                                          requeue_today=True)

        elif result == "partial":
            new_correct = max(0, current_correct - 2)
            return self._build_result(item["round"], round_intervals, new_correct, today,
                                      requeue_today=True)

        elif result == "wrong":
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "next_review_date": today + timedelta(days=1),
                "requeue_today": True
            }

        raise ValueError(f"未知的评分结果: {result}")

    def _build_result(self, round_num: int, round_intervals: list, new_correct: int,
                      today: date, requeue_today: bool = False) -> dict:
        """根据新的 consecutive_correct 构建结果。"""
        if new_correct >= len(round_intervals):
            new_status = "mastered" if round_num == 1 else "archived"
            new_interval = round_intervals[-1]
            next_date = ""
            requeue_today = False
        else:
            new_status = "learning"
            new_interval = round_intervals[new_correct - 1] if new_correct > 0 else 1
            next_date = today + timedelta(days=new_interval)

        return {
            "status": new_status, "round": round_num,
            "interval": new_interval, "consecutive_correct": new_correct,
            "next_review_date": next_date,
            "requeue_today": requeue_today
        }

    def start_round2(self, items: list, today: date) -> list:
        """二轮巩固：批量重置条目为二轮状态"""
        return [{
            "status": "learning", "round": 2, "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        } for item in items]

    def is_due_today(self, item: dict, today: date) -> bool:
        if item["status"] not in ("learning",):
            return False
        next_review = item["next_review_date"]
        if not next_review or next_review == "":
            return False
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        return next_review <= today

    def stage_description(self, consecutive_correct: int, round_num: int) -> str:
        """返回简洁的阶段描述。"""
        if round_num == 2:
            return f"第{consecutive_correct + 1}次背诵（二轮）"
        return f"第{consecutive_correct + 1}次背诵"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_scheduler.py -v`
Expected: 11 passed

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "refactor: 重写scheduler为4级评分动态间隔算法"
```

---

## Task 2: 重写 database.py 新表结构

**Files:**
- Rewrite: `database.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: 写测试文件**

```python
# tests/test_database.py
import pytest
from datetime import date
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
    yesterday = today - __import__("datetime").timedelta(days=1)
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_database.py -v`
Expected: FAIL（表结构不匹配）

- [ ] **Step 3: 实现 database.py**

```python
# database.py
import sqlite3
import os
from datetime import date


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_date TEXT NOT NULL,
                category_id INTEGER,
                status TEXT NOT NULL DEFAULT 'learning',
                round INTEGER NOT NULL DEFAULT 1,
                interval INTEGER NOT NULL DEFAULT 0,
                consecutive_correct INTEGER NOT NULL DEFAULT 0,
                next_review_date TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS review_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                review_date TEXT NOT NULL,
                round INTEGER NOT NULL,
                result TEXT NOT NULL,
                interval_after INTEGER,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
        """)
        self.conn.commit()

    # ===== 分类 CRUD（不变）=====
    def create_category(self, name: str, parent_id: int = None) -> int:
        cursor = self.conn.execute(
            "INSERT INTO categories (name, parent_id) VALUES (?, ?)", (name, parent_id))
        self.conn.commit()
        return cursor.lastrowid

    def get_categories(self) -> list:
        cursor = self.conn.execute("SELECT id, name, parent_id FROM categories ORDER BY name")
        return [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in cursor.fetchall()]

    def get_category_children(self, parent_id: int = None) -> list:
        cursor = self.conn.execute(
            "SELECT id, name, parent_id FROM categories WHERE parent_id IS ? ORDER BY name",
            (parent_id,))
        return [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in cursor.fetchall()]

    def rename_category(self, category_id: int, new_name: str):
        self.conn.execute("UPDATE categories SET name=? WHERE id=?", (new_name, category_id))
        self.conn.commit()

    def delete_category(self, category_id: int):
        self.conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
        self.conn.commit()

    def get_category_path(self, category_id: int) -> list:
        path = []
        current_id = category_id
        while current_id is not None:
            cursor = self.conn.execute("SELECT id, name, parent_id FROM categories WHERE id=?",
                                       (current_id,))
            row = cursor.fetchone()
            if row is None:
                break
            path.insert(0, {"id": row[0], "name": row[1], "parent_id": row[2]})
            current_id = row[2]
        return path

    def get_category_descendant_ids(self, category_id: int) -> list:
        cursor = self.conn.execute(
            """WITH RECURSIVE descendants(id) AS (
                   SELECT id FROM categories WHERE id = ?
                   UNION ALL
                   SELECT c.id FROM categories c JOIN descendants d ON c.parent_id = d.id
               ) SELECT id FROM descendants""", (category_id,))
        return [row[0] for row in cursor.fetchall()]

    # ===== 条目 CRUD =====
    def create_item(self, title: str, content: str, created_date, next_review_date,
                    status: str = "learning", round: int = 1, interval: int = 0,
                    consecutive_correct: int = 0, category_id: int = None) -> int:
        nrd = next_review_date.isoformat() if hasattr(next_review_date, "isoformat") else next_review_date
        cd = created_date.isoformat() if hasattr(created_date, "isoformat") else created_date
        cursor = self.conn.execute(
            """INSERT INTO items (title, content, created_date, category_id, status,
                                   round, interval, consecutive_correct, next_review_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, content, cd, category_id, status, round, interval,
             consecutive_correct, nrd))
        self.conn.commit()
        return cursor.lastrowid

    def _row_to_item(self, row) -> dict:
        return {
            "id": row[0], "title": row[1], "content": row[2], "created_date": row[3],
            "category_id": row[4], "status": row[5], "round": row[6], "interval": row[7],
            "consecutive_correct": row[8], "next_review_date": row[9]
        }

    def get_due_items(self, today) -> list:
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        cursor = self.conn.execute(
            """SELECT * FROM items
               WHERE status='learning' AND next_review_date != '' AND next_review_date <= ?
               ORDER BY next_review_date ASC""", (today_str,))
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def get_active_items(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM items WHERE status='learning' ORDER BY next_review_date ASC")
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def get_mastered_items(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM items WHERE status IN ('mastered','archived') ORDER BY created_date DESC")
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def get_item(self, item_id: int) -> dict:
        cursor = self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,))
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None

    def get_items_by_category(self, category_id: int = None, include_descendants: bool = True) -> list:
        if category_id is None:
            cursor = self.conn.execute(
                "SELECT * FROM items WHERE category_id IS NULL ORDER BY created_date DESC")
            return [self._row_to_item(r) for r in cursor.fetchall()]
        if include_descendants:
            ids = self.get_category_descendant_ids(category_id)
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            cursor = self.conn.execute(
                f"SELECT * FROM items WHERE category_id IN ({placeholders}) ORDER BY created_date DESC",
                ids)
        else:
            cursor = self.conn.execute(
                "SELECT * FROM items WHERE category_id=? ORDER BY created_date DESC", (category_id,))
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def delete_item(self, item_id: int):
        self.conn.execute("DELETE FROM review_logs WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()

    def update_item(self, item_id: int, **fields):
        allowed = {"title", "content", "status", "round", "interval",
                   "consecutive_correct", "next_review_date", "category_id"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        for date_field in ("next_review_date",):
            if date_field in updates and hasattr(updates[date_field], "isoformat"):
                updates[date_field] = updates[date_field].isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [item_id]
        self.conn.execute(f"UPDATE items SET {set_clause} WHERE id=?", values)
        self.conn.commit()

    def bring_overdue_to_today(self, today):
        """将过期未处理的条目顺延到今天"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        self.conn.execute(
            """UPDATE items SET next_review_date = ?
               WHERE next_review_date < ? AND next_review_date != '' AND status = 'learning'""",
            (today_str, today_str))
        self.conn.commit()

    def batch_update_round2(self, item_ids: list, today):
        """批量将条目重置为二轮状态"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        for item_id in item_ids:
            self.conn.execute(
                """UPDATE items SET round=2, status='learning', interval=0,
                   consecutive_correct=0, next_review_date=? WHERE id=?""",
                (today_str, item_id))
        self.conn.commit()

    def log_review(self, item_id: int, review_date, round_num: int, result: str,
                   interval_after: int):
        rd = review_date.isoformat() if hasattr(review_date, "isoformat") else review_date
        self.conn.execute(
            """INSERT INTO review_logs (item_id, review_date, round, result, interval_after)
               VALUES (?, ?, ?, ?, ?)""",
            (item_id, rd, round_num, result, interval_after))
        self.conn.commit()

    def get_review_logs(self, item_id: int) -> list:
        cursor = self.conn.execute(
            """SELECT id, review_date, round, result, interval_after
               FROM review_logs WHERE item_id=? ORDER BY review_date ASC, id ASC""",
            (item_id,))
        return [{"id": r[0], "review_date": r[1], "round": r[2],
                 "result": r[3], "interval_after": r[4]} for r in cursor.fetchall()]

    def get_today_reviewed_item_ids(self, today) -> set:
        """返回今日已评过分的 item_id 集合"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        cursor = self.conn.execute(
            "SELECT DISTINCT item_id FROM review_logs WHERE review_date=?", (today_str,))
        return {row[0] for row in cursor.fetchall()}

    def close(self):
        self.conn.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_database.py -v`
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "refactor: 重写database为新表结构，删除旧艾宾浩斯字段"
```

---

## Task 3: 删除旧数据文件，重置数据库

**Files:**
- Delete: `data/ebbinghaus.db`（若存在）

- [ ] **Step 1: 删除旧数据库文件**

```bash
python -c "import os; os.remove('data/ebbinghaus.db') if os.path.exists('data/ebbinghaus.db') else print('无旧数据库')"
```

- [ ] **Step 2: 验证新数据库能正常初始化**

```bash
python -c "from database import Database; db = Database('data/ebbinghaus.db'); db.init(); print('数据库初始化成功'); db.close()"
```

Expected: 输出「数据库初始化成功」

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "chore: 删除旧数据库，使用新表结构"
```

---

## Task 4: 重写 ui/review_panel.py 卡片式4级评分交互

**Files:**
- Rewrite: `ui/review_panel.py`

- [ ] **Step 1: 实现 review_panel.py**

```python
# ui/review_panel.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler


class ReviewPanel(ctk.CTkFrame):
    """今日待背诵面板：卡片式单张展示，4级评分交互"""
    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.queue = []  # 今日队列 [{item, is_retest}]
        self.completed_count = 0
        self.total_count = 0

        self.title_label = ctk.CTkLabel(self, text="今日待背诵",
                                        font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(15, 5))

        self.progress_label = ctk.CTkLabel(self, text="", text_color="gray")
        self.progress_label.pack(pady=(0, 10))

        self.card_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.card_frame.pack(fill="both", expand=True, padx=30, pady=(0, 15))

        self.refresh()

    def refresh(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        today = date.today()
        self.db.bring_overdue_to_today(today)
        due_items = self.db.get_due_items(today)
        reviewed_ids = self.db.get_today_reviewed_item_ids(today)

        self.queue = []
        for item in due_items:
            is_retest = item["id"] in reviewed_ids
            self.queue.append({"item": item, "is_retest": is_retest})
        self.completed_count = 0
        self.total_count = len(self.queue)

        self._update_progress()
        self._render_current_card()

    def _update_progress(self):
        if self.total_count == 0:
            self.progress_label.configure(text="")
        else:
            self.progress_label.configure(
                text=f"{self.completed_count} / {self.total_count} 已完成")

    def _render_current_card(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        if not self.queue:
            ctk.CTkLabel(self.card_frame, text="🎉 今日背诵完成",
                         font=ctk.CTkFont(size=18)).pack(expand=True)
            return

        current = self.queue[0]
        item = current["item"]
        stage_desc = self.scheduler.stage_description(
            item["consecutive_correct"], item["round"])

        card = ctk.CTkFrame(self.card_frame, corner_radius=10)
        card.pack(fill="both", expand=True, pady=10)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text=stage_desc, text_color="gray").pack(side="right")

        if current.get("show_content"):
            content_box = ctk.CTkTextbox(card, height=200)
            content_box.pack(fill="x", padx=20, pady=10)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(0, 15))
            ctk.CTkButton(btn_frame, text="完全正确", fg_color="#2ecc71",
                          command=lambda: self._handle_review("perfect")).pack(side="left", padx=5, expand=True)
            ctk.CTkButton(btn_frame, text="基本正确", fg_color="#3498db",
                          command=lambda: self._handle_review("mostly_correct")).pack(side="left", padx=5, expand=True)
            ctk.CTkButton(btn_frame, text="部分正确", fg_color="#f39c12",
                          command=lambda: self._handle_review("partial")).pack(side="left", padx=5, expand=True)
            ctk.CTkButton(btn_frame, text="记错了", fg_color="#e74c3c",
                          command=lambda: self._handle_review("wrong")).pack(side="left", padx=5, expand=True)
        else:
            ctk.CTkLabel(card, text="回忆后点击下方按钮查看正文",
                         text_color="gray").pack(pady=40)
            ctk.CTkButton(card, text="展示内容", width=150, fg_color="#3498db",
                          command=self._show_content).pack(pady=10)

    def _show_content(self):
        if self.queue:
            self.queue[0]["show_content"] = True
            self._render_current_card()

    def _handle_review(self, result: str):
        if not self.queue:
            return
        current = self.queue[0]
        item = current["item"]
        today = date.today()

        sched_result = self.scheduler.process_review(
            item, today, result, is_retest=current["is_retest"])

        # 更新数据库
        update_fields = {
            "status": sched_result["status"],
            "round": sched_result["round"],
            "interval": sched_result["interval"],
            "consecutive_correct": sched_result["consecutive_correct"],
        }
        if sched_result["next_review_date"] is not None:
            update_fields["next_review_date"] = sched_result["next_review_date"]
        self.db.update_item(item["id"], **update_fields)

        # 记录日志
        self.db.log_review(item["id"], today, sched_result["round"], result,
                           sched_result["interval"])

        if sched_result["requeue_today"]:
            # 移到队列末尾，标记为重背
            current["is_retest"] = True
            current["show_content"] = False
            # 更新item字典以反映新状态
            item.update(update_fields)
            if sched_result["next_review_date"] is not None:
                item["next_review_date"] = sched_result["next_review_date"]
            self.queue.append(current)
            self.queue.pop(0)
        else:
            # 完成或移出队列
            self.queue.pop(0)
            self.completed_count += 1

        self._update_progress()
        self._render_current_card()

        if self.on_data_changed and not sched_result["requeue_today"]:
            self.on_data_changed()
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from ui.review_panel import ReviewPanel; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 3: 提交**

```bash
git add ui/review_panel.py
git commit -m "feat: 重写review_panel为卡片式4级评分交互"
```

---

## Task 5: 适配 ui/list_panels.py 新字段

**Files:**
- Modify: `ui/list_panels.py`

- [ ] **Step 1: 重写 list_panels.py**

```python
# ui/list_panels.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler


class AllItemsPanel(ctk.CTkFrame):
    """全部条目面板：展示所有学习中的条目"""
    def __init__(self, parent, db, scheduler: Scheduler):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.expanded_item_id = None
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="全部条目",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）", text_color="gray")
        self.filter_label.pack(side="left", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        self.expanded_item_id = None
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _get_items(self):
        if self.filter_category_id is None:
            return self.db.get_active_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_active_items() if i["category_id"] is None]
        else:
            items = self.db.get_items_by_category(self.filter_category_id, include_descendants=True)
            return [i for i in items if i["status"] == "learning"]

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self._get_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="没有符合条件的条目").pack(pady=50)
            return
        for item in items:
            self._render_card(item)

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 3))
        ctk.CTkLabel(header, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        next_review = item["next_review_date"]
        if next_review and next_review != "":
            if isinstance(next_review, str):
                from datetime import date as date_cls
                try:
                    next_review = date_cls.fromisoformat(next_review)
                except ValueError:
                    next_review = None
            today = date.today()
            if next_review and next_review <= today:
                status_text = "今日待背诵"
            else:
                status_text = f"下次：{item['next_review_date']}"
        else:
            status_text = "—"
        ctk.CTkLabel(header, text=status_text, text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color="#7f8c8d", hover_color="#95a5a6",
                          width=70, command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color="#7f8c8d", hover_color="#95a5a6",
                          width=70, command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="补签", fg_color="#f39c12", hover_color="#d68910",
                          width=70, command=lambda: self._backfill_review(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.refresh(),
                       on_deleted_callback=lambda _id: self.refresh())

    def _show_history(self, item):
        from ui.history_dialog import ReviewHistoryDialog
        ReviewHistoryDialog(self, self.db, item)

    def _backfill_review(self, item):
        from ui.backfill_dialog import BackfillReviewDialog
        BackfillReviewDialog(self, item, self._handle_backfill)

    def _handle_backfill(self, item, review_date, result):
        """补签：用历史日期和评分结果重算状态"""
        sched_result = self.scheduler.process_review(item, review_date, result, is_retest=False)
        update_fields = {
            "status": sched_result["status"],
            "round": sched_result["round"],
            "interval": sched_result["interval"],
            "consecutive_correct": sched_result["consecutive_correct"],
        }
        if sched_result["next_review_date"] is not None:
            update_fields["next_review_date"] = sched_result["next_review_date"]
        self.db.update_item(item["id"], **update_fields)
        self.db.log_review(item["id"], review_date, sched_result["round"], result,
                           sched_result["interval"])
        self.refresh()


class MasteredPanel(ctk.CTkFrame):
    """已掌握面板：展示已掌握和已归档条目"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="已掌握",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）", text_color="gray")
        self.filter_label.pack(side="left", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        self.expanded_item_id = None
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _get_items(self):
        if self.filter_category_id is None:
            return self.db.get_mastered_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_mastered_items() if i["category_id"] is None]
        else:
            items = self.db.get_items_by_category(self.filter_category_id, include_descendants=True)
            return [i for i in items if i["status"] in ("mastered", "archived")]

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self._get_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="没有符合条件的条目").pack(pady=50)
            return
        for item in items:
            self._render_card(item)

    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 3))
        ctk.CTkLabel(header, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        status_text = "已掌握(一轮)" if item["status"] == "mastered" else "已归档(二轮)"
        ctk.CTkLabel(header, text=status_text, text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color="#7f8c8d", hover_color="#95a5a6",
                          width=70, command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color="#7f8c8d", hover_color="#95a5a6",
                          width=70, command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()

    def _edit_item(self, item):
        from ui.edit_dialog import EditItemDialog
        EditItemDialog(self, self.db, item,
                       on_saved_callback=lambda _id: self.refresh(),
                       on_deleted_callback=lambda _id: self.refresh())

    def _show_history(self, item):
        from ui.history_dialog import ReviewHistoryDialog
        ReviewHistoryDialog(self, self.db, item)
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from ui.list_panels import AllItemsPanel, MasteredPanel; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 3: 提交**

```bash
git add ui/list_panels.py
git commit -m "refactor: 适配list_panels新字段和4级评分补签"
```

---

## Task 6: 适配 ui/history_dialog.py 和 ui/backfill_dialog.py

**Files:**
- Modify: `ui/history_dialog.py`
- Modify: `ui/backfill_dialog.py`

- [ ] **Step 1: 重写 history_dialog.py**

```python
# ui/history_dialog.py
import customtkinter as ctk


class ReviewHistoryDialog(ctk.CTkToplevel):
    """背诵历史记录对话框"""
    def __init__(self, parent, db, item):
        super().__init__(parent)
        self.title("背诵记录")
        self.geometry("520x520")
        self.db = db
        self.item = item

        ctk.CTkLabel(self, text="背诵记录", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=f"《{item['title']}》", text_color="gray").pack(pady=(0, 10))
        ctk.CTkLabel(self, text=f"开始日期：{item['created_date']}").pack(anchor="w", padx=30, pady=(0, 8))

        logs = db.get_review_logs(item["id"])
        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        if not logs:
            ctk.CTkLabel(scroll, text="暂无背诵记录", text_color="gray").pack(pady=30)
        else:
            header = ctk.CTkFrame(scroll, fg_color="transparent")
            header.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(header, text="日期", width=110, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="轮次", width=60, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="结果", width=100, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(header, text="间隔", width=60, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")

            for log in logs:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=log["review_date"], width=110, anchor="w").pack(side="left")
                round_text = f"第{log['round']}轮"
                ctk.CTkLabel(row, text=round_text, width=60, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=self._result_text(log["result"]), width=100, anchor="w").pack(side="left")
                interval_text = f"{log['interval_after']}天" if log["interval_after"] is not None else "—"
                ctk.CTkLabel(row, text=interval_text, width=60, anchor="w").pack(side="left")

        ctk.CTkButton(self, text="关闭", width=100, fg_color="gray", command=self.destroy).pack(pady=(0, 15))
        self.transient(parent)
        self.grab_set()

    def _result_text(self, result: str) -> str:
        return {
            "perfect": "完全正确",
            "mostly_correct": "基本正确",
            "partial": "部分正确",
            "wrong": "记错了",
        }.get(result, result)
```

- [ ] **Step 2: 重写 backfill_dialog.py（新增result选择）**

```python
# ui/backfill_dialog.py
import customtkinter as ctk
from tkinter import messagebox
from datetime import date, timedelta


class BackfillReviewDialog(ctk.CTkToplevel):
    """补签对话框：选择历史日期和评分结果"""
    def __init__(self, parent, item, on_confirm_callback):
        super().__init__(parent)
        self.title("补签背诵")
        self.geometry("420x450")
        self.item = item
        self.on_confirm_callback = on_confirm_callback
        self.selected_result = None

        ctk.CTkLabel(self, text="补签背诵", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=f"条目：《{item['title']}》").pack(pady=(0, 15))

        ctk.CTkLabel(self, text="补签日期：").pack(anchor="w", padx=30)
        date_frame = ctk.CTkFrame(self, fg_color="transparent")
        date_frame.pack(fill="x", padx=30, pady=(2, 15))
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.date_entry = ctk.CTkEntry(date_frame, width=150, placeholder_text="YYYY-MM-DD")
        self.date_entry.insert(0, yesterday.isoformat())
        self.date_entry.pack(side="left")
        ctk.CTkButton(date_frame, text="昨天", width=60,
                      command=lambda: self.date_entry.delete(0, "end") or self.date_entry.insert(0, yesterday.isoformat())).pack(side="left", padx=5)
        ctk.CTkButton(date_frame, text="前天", width=60,
                      command=lambda: self.date_entry.delete(0, "end") or self.date_entry.insert(0, (today - timedelta(days=2)).isoformat())).pack(side="left")

        ctk.CTkLabel(self, text="评分结果：").pack(anchor="w", padx=30)
        result_frame = ctk.CTkFrame(self, fg_color="transparent")
        result_frame.pack(fill="x", padx=30, pady=(2, 15))
        self.result_var = ctk.StringVar(value="perfect")
        for text, value, color in [("完全正确", "perfect", "#2ecc71"),
                                     ("基本正确", "mostly_correct", "#3498db"),
                                     ("部分正确", "partial", "#f39c12"),
                                     ("记错了", "wrong", "#e74c3c")]:
            ctk.CTkRadioButton(result_frame, text=text, variable=self.result_var,
                               value=value, fg_color=color).pack(anchor="w", pady=2)

        ctk.CTkLabel(self, text="补签后将从该日期按评分重算间隔",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(pady=(0, 15))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=90, fg_color="gray").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="确认补签", width=100,
                      command=self._on_confirm).pack(side="left", padx=5)

        self.transient(parent)
        self.grab_set()

    def _on_confirm(self):
        date_str = self.date_entry.get().strip()
        try:
            review_date = date.fromisoformat(date_str)
        except ValueError:
            messagebox.showwarning("提示", "日期格式不正确，请用 YYYY-MM-DD 格式", parent=self)
            return
        today = date.today()
        if review_date > today:
            messagebox.showwarning("提示", "补签日期不能晚于今天", parent=self)
            return
        start_date = self.item.get("created_date")
        if start_date:
            if isinstance(start_date, str):
                start_date = date.fromisoformat(start_date)
            if review_date < start_date:
                messagebox.showwarning("提示", "补签日期不能早于条目创建日期", parent=self)
                return
        self.on_confirm_callback(self.item, review_date, self.result_var.get())
        self.destroy()
```

- [ ] **Step 3: 验证导入**

Run: `python -c "from ui.history_dialog import ReviewHistoryDialog; from ui.backfill_dialog import BackfillReviewDialog; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 4: 提交**

```bash
git add ui/history_dialog.py ui/backfill_dialog.py
git commit -m "refactor: 适配history和backfill对话框为4级评分"
```

---

## Task 7: 适配 ui/add_dialog.py 和 ui/edit_dialog.py

**Files:**
- Modify: `ui/add_dialog.py`
- Modify: `ui/edit_dialog.py`

- [ ] **Step 1: 读取现有 add_dialog.py**

Run: Read `ui/add_dialog.py`

- [ ] **Step 2: 修改 add_dialog.py 的回调签名**

在 `AddItemDialog` 中，`_on_confirm` 调用 `on_confirm_callback(title, content, start_date, category_id)`。这部分逻辑不变，因为 `main_window._handle_add_item` 会调用 `scheduler.schedule_new_item` 生成新字段。

检查 `add_dialog.py` 是否引用了旧字段（cycle_type 等），若有则删除。

- [ ] **Step 3: 修改 edit_dialog.py 的提示文案**

将 `ui/edit_dialog.py` 中：
```python
ctk.CTkLabel(self, text="提示：修改标题/正文/分类不会影响当前背诵进度", ...)
```
保持不变（文案仍准确）。

删除提示文案中的「复习」字样（如有）。

- [ ] **Step 4: 验证导入**

Run: `python -c "from ui.add_dialog import AddItemDialog; from ui.edit_dialog import EditItemDialog; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 5: 提交**

```bash
git add ui/add_dialog.py ui/edit_dialog.py
git commit -m "refactor: 适配add和edit对话框新字段"
```

---

## Task 8: 新增 ui/category_panel.py 二轮巩固按钮

**Files:**
- Modify: `ui/category_panel.py`

- [ ] **Step 1: 读取现有 category_panel.py**

Run: Read `ui/category_panel.py`

- [ ] **Step 2: 在 CategoryPanel 中添加二轮巩固按钮和处理逻辑**

在按钮区域新增「二轮巩固」按钮，点击后：
1. 获取当前选中分类的所有子孙分类id
2. 查询这些分类下所有条目
3. 检查是否全部 `status='mastered'`
4. 若有未完成，提示「还有N条目未完成一轮」
5. 若全部完成，弹确认框，确认后调用 `db.batch_update_round2`

- [ ] **Step 3: 验证导入**

Run: `python -c "from ui.category_panel import CategoryPanel; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 4: 提交**

```bash
git add ui/category_panel.py
git commit -m "feat: 分类面板新增二轮巩固按钮"
```

---

## Task 9: 新增 ui/stats_panel.py 统计面板

**Files:**
- Create: `ui/stats_panel.py`

- [ ] **Step 1: 实现 stats_panel.py**

```python
# ui/stats_panel.py
import customtkinter as ctk
from datetime import date, timedelta


class StatsPanel(ctk.CTkFrame):
    """统计面板：展示今日进度、本周完成、各状态数量"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db

        ctk.CTkLabel(self, text="统计", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(15, 10))

        self.scroll = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def refresh(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()

        today = date.today()
        week_ago = today - timedelta(days=7)

        # 今日进度
        self.db.bring_overdue_to_today(today)
        due = self.db.get_due_items(today)
        reviewed_ids = self.db.get_today_reviewed_item_ids(today)
        ctk.CTkLabel(self.scroll, text=f"今日待背诵：{len(due)} 条",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(self.scroll, text=f"今日已背诵：{len(reviewed_ids)} 条",
                     text_color="gray").pack(anchor="w", pady=(0, 10))

        # 总览
        active = self.db.get_active_items()
        mastered = self.db.get_mastered_items()
        mastered_count = len([m for m in mastered if m["status"] == "mastered"])
        archived_count = len([m for m in mastered if m["status"] == "archived"])
        ctk.CTkLabel(self.scroll, text="总览",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(self.scroll, text=f"学习中：{len(active)} 条").pack(anchor="w")
        ctk.CTkLabel(self.scroll, text=f"已掌握（一轮）：{mastered_count} 条").pack(anchor="w")
        ctk.CTkLabel(self.scroll, text=f"已归档（二轮）：{archived_count} 条").pack(anchor="w", pady=(0, 10))

        # 各文件夹进度
        ctk.CTkLabel(self.scroll, text="文件夹进度",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 2))
        categories = self.db.get_categories()
        top_cats = [c for c in categories if c["parent_id"] is None]
        if not top_cats:
            ctk.CTkLabel(self.scroll, text="暂无分类", text_color="gray").pack(anchor="w")
        else:
            for cat in top_cats:
                items = self.db.get_items_by_category(cat["id"], include_descendants=True)
                total = len(items)
                if total == 0:
                    continue
                mastered_in_cat = len([i for i in items if i["status"] == "mastered"])
                archived_in_cat = len([i for i in items if i["status"] == "archived"])
                learning_in_cat = len([i for i in items if i["status"] == "learning"])
                pct = int((mastered_in_cat + archived_in_cat) / total * 100) if total > 0 else 0
                ctk.CTkLabel(
                    self.scroll,
                    text=f"{cat['name']}：{learning_in_cat}学习 / {mastered_in_cat}掌握 / {archived_in_cat}归档（{pct}%完成）"
                ).pack(anchor="w", pady=2)
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from ui.stats_panel import StatsPanel; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 3: 提交**

```bash
git add ui/stats_panel.py
git commit -m "feat: 新增统计面板"
```

---

## Task 10: 适配 ui/main_window.py 并删除 mastery_dialog

**Files:**
- Modify: `ui/main_window.py`
- Delete: `ui/mastery_dialog.py`

- [ ] **Step 1: 修改 main_window.py**

- 将 `_handle_add_item` 改为使用新 scheduler 字段
- 新增「统计」标签页
- 删除 mastery_dialog 的引用

- [ ] **Step 2: 删除 mastery_dialog.py**

```bash
git rm ui/mastery_dialog.py
```

- [ ] **Step 3: 验证导入**

Run: `python -c "from ui.main_window import MainWindow; print('导入成功')"`
Expected: 导入成功

- [ ] **Step 4: 提交**

```bash
git add ui/main_window.py
git commit -m "refactor: 适配main_window新字段，新增统计标签页，删除mastery_dialog"
```

---

## Task 11: 运行全部测试并最终验证

**Files:**
- Test: all

- [ ] **Step 1: 运行全部测试**

Run: `pytest tests/ -v`
Expected: All passed

- [ ] **Step 2: 验证应用启动**

Run: `python -c "from database import Database; from scheduler import Scheduler; from ui.main_window import MainWindow; db = Database('data/ebbinghaus.db'); db.init(); print('应用初始化成功'); db.close()"`
Expected: 应用初始化成功

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "test: 全部测试通过，应用可正常启动"
```

---

## 自审清单

**Spec 覆盖检查：**
- [x] 4级评分算法 → Task 1
- [x] 新表结构 → Task 2
- [x] 清空重建数据库 → Task 3
- [x] 卡片式交互 → Task 4
- [x] 全部条目/已掌握面板适配 → Task 5
- [x] 历史/补签对话框适配 → Task 6
- [x] 添加/编辑对话框适配 → Task 7
- [x] 二轮巩固按钮 → Task 8
- [x] 统计面板 → Task 9
- [x] 主窗口适配、删除mastery → Task 10
- [x] 过期顺延 → Task 2 (bring_overdue_to_today) + Task 4 (refresh时调用)

**Placeholder 检查：** 无 TBD/TODO，所有步骤含完整代码

**类型一致性：** `process_review` 返回值在所有Task中一致含 `requeue_today`/`next_review_date`（None表示不更新）
