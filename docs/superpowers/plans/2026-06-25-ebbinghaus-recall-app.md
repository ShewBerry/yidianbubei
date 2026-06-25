# 艾宾浩斯背诵小软件 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 Windows 桌面背诵辅助软件，按艾宾浩斯遗忘曲线自动排程复习，支持漏打卡持续提醒和掌握程度确认。

**Architecture:** 三层架构：`database.py`（SQLite 数据层）→ `scheduler.py`（纯逻辑调度引擎，可独立测试）→ `ui/`（CustomTkinter 界面）。调度引擎与 UI 解耦，核心逻辑通过单元测试验证。

**Tech Stack:** Python 3.8+、CustomTkinter、SQLite（内置 `sqlite3`）、`datetime`、`pytest`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `database.py` | SQLite 建表、连接管理、items/review_logs 的增删改查 |
| `scheduler.py` | 艾宾浩斯调度引擎：间隔表、阶段推进、状态流转、到期判断 |
| `ui/main_window.py` | 主窗口，三标签页 + 顶部"新建背诵"按钮 |
| `ui/review_panel.py` | 复习交互面板：展开正文、打卡、掌握确认弹窗 |
| `ui/add_dialog.py` | 新建背诵对话框 |
| `main.py` | 程序入口，初始化数据库并启动 GUI |
| `tests/test_scheduler.py` | 调度引擎单元测试 |
| `tests/test_database.py` | 数据层单元测试 |
| `data/ebbinghaus.db` | 运行时自动创建的数据库文件 |

---

## Task 1: 项目骨架与依赖

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: 创建 `requirements.txt`**

```
customtkinter>=5.2.0
pytest>=7.0.0
```

- [ ] **Step 2: 创建 `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
data/*.db
.venv/
venv/
```

- [ ] **Step 3: 创建空文件 `tests/__init__.py`**

- [ ] **Step 4: 安装依赖**

Run: `pip install -r requirements.txt`
Expected: 成功安装 customtkinter 和 pytest

- [ ] **Step 5: 提交**

```bash
git add requirements.txt .gitignore tests/__init__.py
git commit -m "chore: 项目骨架与依赖"
```

---

## Task 2: 数据层 - 建表与连接

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 - 建表与初始化**

```python
# tests/test_database.py
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_database.py::test_init_creates_tables -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'database'"

- [ ] **Step 3: 实现 Database 类**

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
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'learning',
                current_stage INTEGER NOT NULL DEFAULT 1,
                next_review_date TEXT NOT NULL,
                cycle_start_date TEXT NOT NULL,
                cycle_type TEXT NOT NULL DEFAULT 'full'
            );

            CREATE TABLE IF NOT EXISTS review_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                review_date TEXT NOT NULL,
                stage_completed INTEGER NOT NULL,
                result TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id)
            );
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_database.py::test_init_creates_tables -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat(database): 建表与连接管理"
```

---

## Task 3: 数据层 - 新建条目

**Files:**
- Modify: `database.py`
- Modify: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 - 新建条目**

```python
# tests/test_database.py 追加
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_database.py::test_create_item_returns_id_and_persists -v`
Expected: FAIL with "AttributeError: 'Database' object has no attribute 'create_item'"

- [ ] **Step 3: 实现 create_item 方法**

```python
# database.py 在 Database 类中追加方法
    def create_item(self, title: str, content: str, created_date, next_review_date) -> int:
        cursor = self.conn.execute(
            """INSERT INTO items (title, content, created_date, status, current_stage,
                                   next_review_date, cycle_start_date, cycle_type)
               VALUES (?, ?, ?, 'learning', 1, ?, ?, 'full')""",
            (title, content, created_date.isoformat(), next_review_date.isoformat(), created_date.isoformat())
        )
        self.conn.commit()
        return cursor.lastrowid
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_database.py::test_create_item_returns_id_and_persists -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat(database): 新建背诵条目"
```

---

## Task 4: 数据层 - 查询今日待复习与全部条目

**Files:**
- Modify: `database.py`
- Modify: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 - 查询今日待复习**

```python
# tests/test_database.py 追加
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_database.py -v -k "due or active or mastered"`
Expected: FAIL with "AttributeError: 'Database' object has no attribute 'get_due_items'"

- [ ] **Step 3: 实现查询方法**

```python
# database.py 在 Database 类中追加方法
    def _row_to_item(self, row) -> dict:
        return {
            "id": row[0], "title": row[1], "content": row[2],
            "created_date": row[3], "status": row[4], "current_stage": row[5],
            "next_review_date": row[6], "cycle_start_date": row[7], "cycle_type": row[8]
        }

    def get_due_items(self, today) -> list:
        cursor = self.conn.execute(
            """SELECT * FROM items
               WHERE status IN ('learning', 'pending_mastery')
                 AND next_review_date <= ?
               ORDER BY next_review_date ASC""",
            (today.isoformat(),)
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_active_items(self) -> list:
        cursor = self.conn.execute(
            """SELECT * FROM items
               WHERE status IN ('learning', 'pending_mastery')
               ORDER BY next_review_date ASC"""
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_mastered_items(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM items WHERE status='mastered' ORDER BY created_date DESC"
        )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_item(self, item_id: int) -> dict:
        cursor = self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,))
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_database.py -v -k "due or active or mastered"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat(database): 查询今日待复习/全部/已掌握条目"
```

---

## Task 5: 数据层 - 更新条目与记录复习日志

**Files:**
- Modify: `database.py`
- Modify: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 - 更新条目与记录日志**

```python
# tests/test_database.py 追加
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_database.py::test_update_item_status_and_stage -v`
Expected: FAIL with "AttributeError: 'Database' object has no attribute 'update_item'"

- [ ] **Step 3: 实现更新与日志方法**

```python
# database.py 在 Database 类中追加方法
    def update_item(self, item_id: int, **fields):
        allowed = {"status", "current_stage", "next_review_date",
                   "cycle_start_date", "cycle_type"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [item_id]
        self.conn.execute(f"UPDATE items SET {set_clause} WHERE id=?", values)
        self.conn.commit()

    def log_review(self, item_id: int, review_date, stage_completed: int, result: str):
        self.conn.execute(
            """INSERT INTO review_logs (item_id, review_date, stage_completed, result)
               VALUES (?, ?, ?, ?)""",
            (item_id, review_date.isoformat(), stage_completed, result)
        )
        self.conn.commit()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_database.py -v -k "update_item or log_review"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat(database): 更新条目状态与记录复习日志"
```

---

## Task 6: 调度引擎 - 间隔表与新建条目排程

**Files:**
- Create: `scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: 写失败测试 - 间隔表与新建排程**

```python
# tests/test_scheduler.py
from datetime import date, timedelta
from scheduler import Scheduler

def test_full_cycle_intervals():
    s = Scheduler()
    assert s.FULL_CYCLE == [1, 2, 4, 7, 15, 30]

def test_short_cycle_intervals():
    s = Scheduler()
    assert s.SHORT_CYCLE == [1, 3, 7]

def test_schedule_new_item_first_review_tomorrow():
    s = Scheduler()
    today = date(2026, 6, 25)
    schedule = s.schedule_new_item(today)
    assert schedule["status"] == "learning"
    assert schedule["current_stage"] == 1
    assert schedule["cycle_type"] == "full"
    assert schedule["cycle_start_date"] == today
    assert schedule["next_review_date"] == today + timedelta(days=1)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scheduler'"

- [ ] **Step 3: 实现 Scheduler 基础**

```python
# scheduler.py
from datetime import date, timedelta

class Scheduler:
    FULL_CYCLE = [1, 2, 4, 7, 15, 30]
    SHORT_CYCLE = [1, 3, 7]

    def schedule_new_item(self, today: date) -> dict:
        return {
            "status": "learning",
            "current_stage": 1,
            "cycle_type": "full",
            "cycle_start_date": today,
            "next_review_date": today + timedelta(days=1)
        }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(scheduler): 间隔表与新建条目排程"
```

---

## Task 7: 调度引擎 - 打卡推进阶段

**Files:**
- Modify: `scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 写失败测试 - 打卡推进**

```python
# tests/test_scheduler.py 追加
def test_mark_reviewed_advances_stage_in_full_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    # 当前在阶段1，打卡后应进入阶段2，下次复习=今天+2天
    item = {
        "status": "learning", "current_stage": 1, "cycle_type": "full",
        "cycle_start_date": today - timedelta(days=1),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 2
    assert result["cycle_type"] == "full"
    assert result["next_review_date"] == today + timedelta(days=2)

def test_mark_reviewed_last_stage_enters_pending_mastery():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {
        "status": "learning", "current_stage": 6, "cycle_type": "full",
        "cycle_start_date": today - timedelta(days=30),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "pending_mastery"
    assert result["next_review_date"] == today  # 立即到期等待确认

def test_mark_reviewed_short_cycle_last_stage_enters_pending_mastery():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {
        "status": "learning", "current_stage": 3, "cycle_type": "short",
        "cycle_start_date": today - timedelta(days=7),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "pending_mastery"

def test_mark_reviewed_uses_short_cycle_intervals():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {
        "status": "learning", "current_stage": 1, "cycle_type": "short",
        "cycle_start_date": today - timedelta(days=1),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["current_stage"] == 2
    assert result["next_review_date"] == today + timedelta(days=3)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_scheduler.py -v -k mark_reviewed`
Expected: FAIL with "AttributeError: 'Scheduler' object has no attribute 'mark_reviewed'"

- [ ] **Step 3: 实现 mark_reviewed**

```python
# scheduler.py 在 Scheduler 类中追加方法
    def mark_reviewed(self, item: dict, review_date: date) -> dict:
        cycle = self.SHORT_CYCLE if item["cycle_type"] == "short" else self.FULL_CYCLE
        current_stage = item["current_stage"]

        if current_stage >= len(cycle):
            # 已是最后阶段，进入待确认掌握
            return {
                "status": "pending_mastery",
                "current_stage": current_stage,
                "cycle_type": item["cycle_type"],
                "cycle_start_date": item["cycle_start_date"],
                "next_review_date": review_date
            }

        next_stage = current_stage + 1
        next_interval = cycle[next_stage - 1]  # 阶段序号1-based，列表0-based
        return {
            "status": "learning",
            "current_stage": next_stage,
            "cycle_type": item["cycle_type"],
            "cycle_start_date": item["cycle_start_date"],
            "next_review_date": review_date + timedelta(days=next_interval)
        }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_scheduler.py -v -k mark_reviewed`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(scheduler): 打卡推进阶段"
```

---

## Task 8: 调度引擎 - 掌握确认分流

**Files:**
- Modify: `scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 写失败测试 - 掌握确认分流**

```python
# tests/test_scheduler.py 追加
def test_confirm_mastery_mastered():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 6, "cycle_type": "full",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "mastered")
    assert result["status"] == "mastered"

def test_confirm_mastery_fuzzy_enters_short_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 6, "cycle_type": "full",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "fuzzy")
    assert result["status"] == "learning"
    assert result["cycle_type"] == "short"
    assert result["current_stage"] == 1
    assert result["cycle_start_date"] == today
    assert result["next_review_date"] == today + timedelta(days=1)

def test_confirm_mastery_forgotten_restarts_full_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 3, "cycle_type": "short",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "forgotten")
    assert result["status"] == "learning"
    assert result["cycle_type"] == "full"
    assert result["current_stage"] == 1
    assert result["cycle_start_date"] == today
    assert result["next_review_date"] == today + timedelta(days=1)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_scheduler.py -v -k confirm_mastery`
Expected: FAIL with "AttributeError: 'Scheduler' object has no attribute 'confirm_mastery'"

- [ ] **Step 3: 实现 confirm_mastery**

```python
# scheduler.py 在 Scheduler 类中追加方法
    def confirm_mastery(self, item: dict, today: date, result: str) -> dict:
        if result == "mastered":
            return {
                "status": "mastered",
                "current_stage": item["current_stage"],
                "cycle_type": item["cycle_type"],
                "cycle_start_date": item["cycle_start_date"],
                "next_review_date": item["next_review_date"]
            }
        if result == "fuzzy":
            return {
                "status": "learning",
                "current_stage": 1,
                "cycle_type": "short",
                "cycle_start_date": today,
                "next_review_date": today + timedelta(days=1)
            }
        if result == "forgotten":
            return {
                "status": "learning",
                "current_stage": 1,
                "cycle_type": "full",
                "cycle_start_date": today,
                "next_review_date": today + timedelta(days=1)
            }
        raise ValueError(f"未知的掌握确认结果: {result}")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_scheduler.py -v -k confirm_mastery`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(scheduler): 掌握确认分流"
```

---

## Task 9: 调度引擎 - 漏打卡持续到期判断

**Files:**
- Modify: `scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 写失败测试 - 到期判断**

```python
# tests/test_scheduler.py 追加
def test_is_due_today_true_when_next_review_equals_today():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today, "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_is_due_today_true_when_next_review_before_today():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today - timedelta(days=2), "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_is_due_today_false_when_future():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today + timedelta(days=1), "status": "learning"}
    assert s.is_due_today(item, today) is False

def test_is_due_today_false_when_mastered():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today, "status": "mastered"}
    assert s.is_due_today(item, today) is False
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_scheduler.py -v -k is_due_today`
Expected: FAIL with "AttributeError: 'Scheduler' object has no attribute 'is_due_today'"

- [ ] **Step 3: 实现 is_due_today**

```python
# scheduler.py 在 Scheduler 类中追加方法
    def is_due_today(self, item: dict, today: date) -> bool:
        if item["status"] == "mastered":
            return False
        next_review = item["next_review_date"]
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        return next_review <= today
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_scheduler.py -v -k is_due_today`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(scheduler): 漏打卡持续到期判断"
```

---

## Task 10: 调度引擎 - 阶段描述辅助方法

**Files:**
- Modify: `scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: 写失败测试 - 阶段描述**

```python
# tests/test_scheduler.py 追加
def test_stage_description_full_cycle():
    s = Scheduler()
    assert s.stage_description(1, "full") == "第1次复习（1天后）"
    assert s.stage_description(6, "full") == "第6次复习（30天后）"

def test_stage_description_short_cycle():
    s = Scheduler()
    assert s.stage_description(1, "short") == "第1次复习（1天后）"
    assert s.stage_description(3, "short") == "第3次复习（7天后）"

def test_stage_description_pending_mastery():
    s = Scheduler()
    assert s.stage_description(6, "full") == "第6次复习（30天后）"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_scheduler.py -v -k stage_description`
Expected: FAIL with "AttributeError: 'Scheduler' object has no attribute 'stage_description'"

- [ ] **Step 3: 实现 stage_description**

```python
# scheduler.py 在 Scheduler 类中追加方法
    def stage_description(self, stage: int, cycle_type: str) -> str:
        cycle = self.SHORT_CYCLE if cycle_type == "short" else self.FULL_CYCLE
        if stage < 1 or stage > len(cycle):
            return f"第{stage}次复习"
        return f"第{stage}次复习（{cycle[stage - 1]}天后）"
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_scheduler.py -v -k stage_description`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(scheduler): 阶段描述辅助方法"
```

---

## Task 11: 新建背诵对话框

**Files:**
- Create: `ui/__init__.py`
- Create: `ui/add_dialog.py`

- [ ] **Step 1: 创建 `ui/__init__.py` 空文件**

- [ ] **Step 2: 实现 AddItemDialog**

```python
# ui/add_dialog.py
import customtkinter as ctk
from tkinter import messagebox

class AddItemDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("新建背诵")
        self.geometry("400x400")
        self.on_save_callback = on_save_callback

        ctk.CTkLabel(self, text="标题：").pack(pady=(15, 0), anchor="w", padx=20)
        self.title_entry = ctk.CTkEntry(self, width=360)
        self.title_entry.pack(padx=20, pady=(5, 10))

        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20)
        self.content_text = ctk.CTkTextbox(self, width=360, height=200)
        self.content_text.pack(padx=20, pady=(5, 10))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=100).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="保存", command=self._on_save, width=100).pack(side="left", padx=10)

        self.transient(parent)
        self.grab_set()

    def _on_save(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not title:
            messagebox.showwarning("提示", "请输入标题", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "请输入正文", parent=self)
            return
        self.on_save_callback(title, content)
        self.destroy()
```

- [ ] **Step 3: 手动验证（创建临时测试脚本）**

```python
# 临时验证脚本，验证后删除
import customtkinter as ctk
from ui.add_dialog import AddItemDialog

root = ctk.CTk()
root.withdraw()
AddItemDialog(root, lambda t, c: print(f"保存: {t}, {c}"))
root.mainloop()
```

Run: `python -c "import customtkinter as ctk; from ui.add_dialog import AddItemDialog; root=ctk.CTk(); root.withdraw(); AddItemDialog(root, lambda t,c: print(f'保存:{t},{c}')); root.mainloop()"`
Expected: 弹出对话框，输入标题和正文后点保存，控制台打印内容

- [ ] **Step 4: 提交**

```bash
git add ui/__init__.py ui/add_dialog.py
git commit -m "feat(ui): 新建背诵对话框"
```

---

## Task 12: 掌握确认弹窗

**Files:**
- Create: `ui/mastery_dialog.py`

- [ ] **Step 1: 实现 MasteryConfirmDialog**

```python
# ui/mastery_dialog.py
import customtkinter as ctk

class MasteryConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, item, on_result_callback):
        super().__init__(parent)
        self.title("掌握确认")
        self.geometry("500x450")
        self.item = item
        self.on_result_callback = on_result_callback

        ctk.CTkLabel(self, text=f"《{item['title']}》", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text="你已经完成了完整复习周期，请确认掌握情况：").pack(pady=(0, 10))

        content_box = ctk.CTkTextbox(self, width=460, height=220)
        content_box.pack(padx=20, pady=5)
        content_box.insert("1.0", item["content"])
        content_box.configure(state="disabled")

        ctk.CTkLabel(self, text="你掌握了吗？").pack(pady=(10, 5))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="已掌握", fg_color="#2ecc71", width=120,
                      command=lambda: self._on_result("mastered")).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="有点模糊", fg_color="#f39c12", width=120,
                      command=lambda: self._on_result("fuzzy")).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="完全没记住", fg_color="#e74c3c", width=120,
                      command=lambda: self._on_result("forgotten")).pack(side="left", padx=10)

        self.transient(parent)
        self.grab_set()

    def _on_result(self, result: str):
        self.on_result_callback(self.item, result)
        self.destroy()
```

- [ ] **Step 2: 手动验证**

Run: `python -c "import customtkinter as ctk; from ui.mastery_dialog import MasteryConfirmDialog; root=ctk.CTk(); root.withdraw(); item={'title':'测试','content':'内容...'}; MasteryConfirmDialog(root, item, lambda i,r: print(f'结果:{r}')); root.mainloop()"`
Expected: 弹出确认窗口，显示标题和正文，三个按钮可点击

- [ ] **Step 3: 提交**

```bash
git add ui/mastery_dialog.py
git commit -m "feat(ui): 掌握确认弹窗"
```

---

## Task 13: 复习交互面板

**Files:**
- Create: `ui/review_panel.py`

- [ ] **Step 1: 实现 ReviewPanel**

```python
# ui/review_panel.py
import customtkinter as ctk
from datetime import date, datetime
from scheduler import Scheduler

class ReviewPanel(ctk.CTkFrame):
    """今日待复习面板：展示到期条目，支持打卡和掌握确认"""
    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.expanded_item_id = None

        self.title_label = ctk.CTkLabel(self, text="今日待复习", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(15, 10))

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.refresh()

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        today = date.today()
        due_items = self.db.get_due_items(today)

        if not due_items:
            ctk.CTkLabel(self.scroll_frame, text="今天没有需要复习的内容 🎉",
                         font=ctk.CTkFont(size=14)).pack(pady=50)
            return

        for item in due_items:
            self._render_item_card(item, today)

    def _render_item_card(self, item, today):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(8, 3))

        stage_desc = self.scheduler.stage_description(item["current_stage"], item["cycle_type"])
        if item["cycle_type"] == "short":
            stage_desc += "（短周期再确认）"
        if item["status"] == "pending_mastery":
            stage_desc = "✅ 完成复习周期，请确认掌握"

        ctk.CTkLabel(header_frame, text=f"《{item['title']}》",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(header_frame, text=stage_desc,
                     text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=150)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(0, 8))

            if item["status"] == "pending_mastery":
                ctk.CTkButton(btn_frame, text="确认掌握", fg_color="#2ecc71",
                              command=lambda: self._confirm_mastery(item)).pack(side="right", padx=(5, 0))
            else:
                ctk.CTkButton(btn_frame, text="打卡复习", fg_color="#3498db",
                              command=lambda: self._mark_reviewed(item, today)).pack(side="right", padx=(5, 0))

            ctk.CTkButton(btn_frame, text="收起", fg_color="gray",
                          width=80, command=self._collapse).pack(side="right")
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()

    def _mark_reviewed(self, item, today):
        result = self.scheduler.mark_reviewed(item, today)
        self.db.update_item(
            item["id"],
            status=result["status"],
            current_stage=result["current_stage"],
            cycle_type=result["cycle_type"],
            cycle_start_date=result["cycle_start_date"],
            next_review_date=result["next_review_date"]
        )
        self.db.log_review(item["id"], today, item["current_stage"], "done")
        if self.on_data_changed:
            self.on_data_changed()

    def _confirm_mastery(self, item):
        from ui.mastery_dialog import MasteryConfirmDialog
        MasteryConfirmDialog(self, item, self._handle_mastery_result)

    def _handle_mastery_result(self, item, result):
        today = date.today()
        sched_result = self.scheduler.confirm_mastery(item, today, result)
        self.db.update_item(
            item["id"],
            status=sched_result["status"],
            current_stage=sched_result["current_stage"],
            cycle_type=sched_result["cycle_type"],
            cycle_start_date=sched_result["cycle_start_date"],
            next_review_date=sched_result["next_review_date"]
        )
        self.db.log_review(item["id"], today, item["current_stage"], result)
        if self.on_data_changed:
            self.on_data_changed()
```

- [ ] **Step 2: 提交**

```bash
git add ui/review_panel.py
git commit -m "feat(ui): 复习交互面板"
```

---

## Task 14: 全部条目面板与已掌握面板

**Files:**
- Create: `ui/list_panels.py`

- [ ] **Step 1: 实现 AllItemsPanel 和 MasteredPanel**

```python
# ui/list_panels.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler

class AllItemsPanel(ctk.CTkFrame):
    """全部条目面板：展示所有学习中/待确认的条目"""
    def __init__(self, parent, db, scheduler: Scheduler):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.expanded_item_id = None

        ctk.CTkLabel(self, text="全部条目", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(15, 10))
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self.db.get_active_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="还没有背诵条目，点击右上角"新建背诵"开始吧").pack(pady=50)
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
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        today = date.today()
        if item["status"] == "pending_mastery":
            status_text = "待确认掌握"
        elif next_review <= today:
            status_text = "今日待复习"
        else:
            status_text = f"下次复习：{next_review.isoformat()}"
        ctk.CTkLabel(header, text=status_text, text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            ctk.CTkButton(card, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(padx=10, pady=(0, 8), anchor="e")
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()


class MasteredPanel(ctk.CTkFrame):
    """已掌握面板：展示归档条目"""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None

        ctk.CTkLabel(self, text="已掌握", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(15, 10))
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.refresh()

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        items = self.db.get_mastered_items()
        if not items:
            ctk.CTkLabel(self.scroll_frame, text="还没有已掌握的条目").pack(pady=50)
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
        ctk.CTkLabel(header, text=f"创建于 {item['created_date']}", text_color="gray").pack(side="right")

        if self.expanded_item_id == item["id"]:
            content_box = ctk.CTkTextbox(card, height=120)
            content_box.pack(fill="x", padx=10, pady=5)
            content_box.insert("1.0", item["content"])
            content_box.configure(state="disabled")
            ctk.CTkButton(card, text="收起", width=80, fg_color="gray",
                          command=self._collapse).pack(padx=10, pady=(0, 8), anchor="e")
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color="gray",
                          command=lambda: self._expand(item["id"])).pack(padx=10, pady=(0, 8), anchor="e")

    def _expand(self, item_id):
        self.expanded_item_id = item_id
        self.refresh()

    def _collapse(self):
        self.expanded_item_id = None
        self.refresh()
```

- [ ] **Step 2: 提交**

```bash
git add ui/list_panels.py
git commit -m "feat(ui): 全部条目面板与已掌握面板"
```

---

## Task 15: 主窗口

**Files:**
- Create: `ui/main_window.py`

- [ ] **Step 1: 实现 MainWindow**

```python
# ui/main_window.py
import customtkinter as ctk
from datetime import date
from database import Database
from scheduler import Scheduler
from ui.review_panel import ReviewPanel
from ui.list_panels import AllItemsPanel, MasteredPanel
from ui.add_dialog import AddItemDialog

class MainWindow(ctk.CTk):
    def __init__(self, db: Database, scheduler: Scheduler):
        super().__init__()
        self.db = db
        self.scheduler = scheduler

        self.title("艾宾浩斯背诵助手")
        self.geometry("800x600")

        # 顶部栏
        top_bar = ctk.CTkFrame(self)
        top_bar.pack(fill="x", padx=15, pady=(15, 0))
        ctk.CTkLabel(top_bar, text="📖 艾宾浩斯背诵助手",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(top_bar, text="+ 新建背诵", width=120,
                      command=self._open_add_dialog).pack(side="right", padx=10, pady=10)

        # 标签页
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab_today = self.tabview.add("今日待复习")
        self.tab_all = self.tabview.add("全部条目")
        self.tab_mastered = self.tabview.add("已掌握")

        self.review_panel = ReviewPanel(self.tab_today, self.db, self.scheduler,
                                        on_data_changed=self._refresh_all)
        self.review_panel.pack(fill="both", expand=True)

        self.all_items_panel = AllItemsPanel(self.tab_all, self.db, self.scheduler)
        self.all_items_panel.pack(fill="both", expand=True)

        self.mastered_panel = MasteredPanel(self.tab_mastered, self.db)
        self.mastered_panel.pack(fill="both", expand=True)

    def _open_add_dialog(self):
        AddItemDialog(self, self._handle_add_item)

    def _handle_add_item(self, title: str, content: str):
        today = date.today()
        schedule = self.scheduler.schedule_new_item(today)
        self.db.create_item(title, content, today, schedule["next_review_date"])
        self._refresh_all()

    def _refresh_all(self):
        self.review_panel.refresh()
        self.all_items_panel.refresh()
        self.mastered_panel.refresh()
```

- [ ] **Step 2: 提交**

```bash
git add ui/main_window.py
git commit -m "feat(ui): 主窗口"
```

---

## Task 16: 程序入口

**Files:**
- Create: `main.py`

- [ ] **Step 1: 实现 main.py**

```python
# main.py
import os
import sys
from pathlib import Path
import customtkinter as ctk
from database import Database
from scheduler import Scheduler
from ui.main_window import MainWindow

def get_db_path() -> str:
    """数据库路径：项目根目录下 data/ebbinghaus.db"""
    if getattr(sys, 'frozen', False):
        # 打包后的 exe 模式：放在 exe 同级目录
        base = Path(sys.executable).parent
    else:
        # 开发模式：项目根目录
        base = Path(__file__).parent
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "ebbinghaus.db")

def main():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    db = Database(get_db_path())
    db.init()
    scheduler = Scheduler()

    app = MainWindow(db, scheduler)
    app.protocol("WM_DELETE_WINDOW", lambda: (db.close(), app.destroy()))
    app.mainloop()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行完整测试套件**

Run: `pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 手动启动应用验证**

Run: `python main.py`
Expected: 窗口打开，三个标签页正常显示，"今日待复习"显示空状态提示

- [ ] **Step 4: 提交**

```bash
git add main.py
git commit -m "feat: 程序入口"
```

---

## Task 17: 端到端手动验证清单

**Files:** 无（仅手动操作）

- [ ] **Step 1: 启动应用**

Run: `python main.py`
Expected: 窗口正常打开

- [ ] **Step 2: 新建条目**

点击"新建背诵"，输入标题"测试古诗"和正文"床前明月光，疑是地上霜。"，保存。
Expected: 对话框关闭，"全部条目"标签页出现该条目，状态显示"下次复习：明天日期"

- [ ] **Step 3: 验证今日待复习为空**

切换到"今日待复习"标签页
Expected: 显示"今天没有需要复习的内容 🎉"

- [ ] **Step 4: 模拟到期（修改数据库）**

用 sqlite3 命令行或 DB 工具，将该条目的 next_review_date 改为今天：
```sql
UPDATE items SET next_review_date = date('now') WHERE title = '测试古诗';
```
切换回"今日待复习"并重启应用
Expected: 该条目出现在今日待复习列表

- [ ] **Step 5: 打卡复习**

展开条目，点击"打卡复习"
Expected: 条目从今日待复习消失，"全部条目"中下次复习日期变为后天（+2天）

- [ ] **Step 6: 验证漏打卡持续提醒**

修改 next_review_date 为昨天，重启应用
Expected: 条目仍出现在今日待复习（漏打卡持续提醒）

- [ ] **Step 7: 验证完整周期完成**

将 current_stage 改为 6，next_review_date 改为今天，重启应用
Expected: 条目出现，展开后按钮变为"确认掌握"

- [ ] **Step 8: 验证掌握确认 - 模糊**

点击"确认掌握"，选择"有点模糊"
Expected: 条目 cycle_type 变为 short，current_stage=1，下次复习为明天

- [ ] **Step 9: 验证掌握确认 - 已掌握**

重复 Step 7，选择"已掌握"
Expected: 条目从"今日待复习"和"全部条目"消失，出现在"已掌握"标签页

- [ ] **Step 10: 验证掌握确认 - 完全没记住**

重复 Step 7，选择"完全没记住"
Expected: 条目 cycle_type 变为 full，current_stage=1，重走完整周期

- [ ] **Step 11: 提交验证记录**

```bash
git commit --allow-empty -m "test: 端到端手动验证通过"
```
