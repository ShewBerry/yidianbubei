# 内容标记、条目笔记与字号缩放 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为「一点不背」增加正文章节标记（忘了/模糊）、条目级笔记、内容字号与框高缩放三项展示层辅助能力，不改动调度/评分/补签逻辑。

**Architecture:** 数据层新增 `item_marks` 表与 `settings` 表，items 表加 `notes` 字段；UI 层封装 `MarkableTextbox`（可标记+缩放）与 `NotesBox`（条目笔记）两个复用组件，接入今日背诵、全部条目展开、编辑对话框三处。

**Tech Stack:** Python 3.12 + CustomTkinter + SQLite + pytest

**Spec:** `docs/superpowers/specs/2026-06-26-content-marks-notes-zoom-design.md`

---

## 文件结构

**新建：**
- `ui/notes_box.py` — 条目级笔记组件（CTkFrame，失焦自动保存）
- `ui/markable_textbox.py` — 可标记+可缩放内容框组件（CTkFrame）

**修改：**
- `database.py` — 表迁移、notes 字段、item_marks CRUD、settings CRUD、_shift_marks
- `ui/review_panel.py` — 今日背诵展示内容时使用 MarkableTextbox + NotesBox
- `ui/list_panels.py` — 全部条目/已掌握展开时使用 MarkableTextbox + NotesBox
- `ui/edit_dialog.py` — 新增笔记编辑区
- `tests/test_database.py` — 新增数据层测试

**不改动：** `scheduler.py`、评分/补签/队列逻辑

---

## Task 1: 数据层迁移 — items.notes 字段 + item_marks/settings 表

**Files:**
- Modify: `database.py` 的 `init` 方法（L14-47）、`_row_to_item`（L111-116）、`update_item`（L164-176）
- Test: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 — 表结构与 notes 字段**

在 `tests/test_database.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_database.py::test_items_table_has_notes_field tests/test_database.py::test_item_marks_table_exists tests/test_database.py::test_settings_table_exists tests/test_database.py::test_create_item_default_notes_empty tests/test_database.py::test_update_item_notes -v`
Expected: 5 个测试 FAIL（notes 字段不存在 / item_marks 表不存在 / settings 表不存在）

- [ ] **Step 3: 修改 init 方法，加表与迁移**

将 `database.py` 的 `init` 方法（L14-47）替换为：

```python
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

            CREATE TABLE IF NOT EXISTS item_marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                start_pos INTEGER NOT NULL,
                end_pos INTEGER NOT NULL,
                mark_type TEXT NOT NULL,
                created_date TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_item_marks_item ON item_marks(item_id);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        # 迁移：为旧库的 items 表补 notes 字段（已存在则忽略）
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(items)")}
        if "notes" not in cols:
            self.conn.execute("ALTER TABLE items ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        self.conn.commit()
```

- [ ] **Step 4: 修改 _row_to_item，加 notes 字段**

将 `_row_to_item`（L111-116）替换为：

```python
    def _row_to_item(self, row) -> dict:
        return {
            "id": row[0], "title": row[1], "content": row[2], "created_date": row[3],
            "category_id": row[4], "status": row[5], "round": row[6], "interval": row[7],
            "consecutive_correct": row[8], "next_review_date": row[9],
            "notes": row[10] if len(row) > 10 else ""
        }
```

- [ ] **Step 5: 修改 update_item，allowed 集合加 notes**

将 `update_item` 的 allowed 行（L165-166）替换为：

```python
        allowed = {"title", "content", "status", "round", "interval",
                   "consecutive_correct", "next_review_date", "category_id", "notes"}
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `python -m pytest tests/test_database.py -v`
Expected: 全部 PASS（含 5 个新测试 + 原 17 个）

- [ ] **Step 7: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat: items 表新增 notes 字段，新建 item_marks/settings 表"
```

---

## Task 2: 标记 CRUD 方法 + settings 读写方法

**Files:**
- Modify: `database.py`（在 `get_category_progress` 后、`close` 前插入）
- Test: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 — 标记 CRUD 与 settings**

在 `tests/test_database.py` 末尾追加：

```python
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


def test_delete_item_cascades_marks(db):
    """删除条目时标记应级联删除"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "abcdefg", today, today)
    db.add_mark(item_id, 0, 2, "forgot")
    db.delete_item(item_id)
    marks = db.get_marks(item_id)
    assert len(marks) == 0


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
    # 默认值
    assert db.get_setting("content_font_size", "14") == "14"
    # 设置后读取
    db.set_setting("content_font_size", "18")
    assert db.get_setting("content_font_size", "14") == "18"
    # 覆盖
    db.set_setting("content_font_size", "20")
    assert db.get_setting("content_font_size", "14") == "20"


def test_setting_persists_across_connection(db, tmp_path):
    """settings 应跨连接持久化"""
    db_path = str(tmp_path / "test2.db")
    db.set_setting("content_box_height", "400")
    db.close()
    db2 = Database(db_path)
    db2.init()
    assert db2.get_setting("content_box_height", "200") == "400"
    db2.close()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_database.py::test_add_and_get_marks tests/test_database.py::test_get_marks_sorted_by_start tests/test_database.py::test_delete_mark tests/test_database.py::test_delete_item_cascades_marks tests/test_database.py::test_get_marks_filters_invalid tests/test_database.py::test_setting_get_and_set tests/test_database.py::test_setting_persists_across_connection -v`
Expected: 7 个 FAIL（方法不存在）

- [ ] **Step 3: 在 database.py 的 `get_category_progress` 方法后、`close` 前插入标记与设置方法**

```python
    # ===== 标记 CRUD =====
    def add_mark(self, item_id: int, start_pos: int, end_pos: int, mark_type: str) -> int:
        from datetime import date as _date
        today_str = _date.today().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO item_marks (item_id, start_pos, end_pos, mark_type, created_date)
               VALUES (?, ?, ?, ?, ?)""",
            (item_id, start_pos, end_pos, mark_type, today_str))
        self.conn.commit()
        return cursor.lastrowid

    def get_marks(self, item_id: int) -> list:
        """返回该条目的所有合法标记，按 start_pos 升序。
        过滤掉 start>=end 或超出当前 content 长度的非法标记（容错：编辑后位置漂移）。
        """
        item = self.get_item(item_id)
        content_len = len(item["content"]) if item else 0
        cursor = self.conn.execute(
            """SELECT id, item_id, start_pos, end_pos, mark_type, created_date
               FROM item_marks WHERE item_id=? ORDER BY start_pos ASC""", (item_id,))
        marks = []
        for r in cursor.fetchall():
            start, end = r[2], r[3]
            if start < end and end <= content_len:
                marks.append({"id": r[0], "item_id": r[1], "start_pos": start,
                              "end_pos": end, "mark_type": r[4], "created_date": r[5]})
        return marks

    def delete_mark(self, mark_id: int):
        self.conn.execute("DELETE FROM item_marks WHERE id=?", (mark_id,))
        self.conn.commit()

    # ===== 设置 CRUD =====
    def get_setting(self, key: str, default: str = "") -> str:
        cursor = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))
        self.conn.commit()
```

- [ ] **Step 4: 修改 delete_item，显式删除 item_marks**

将 `delete_item`（L159-162）替换为：

```python
    def delete_item(self, item_id: int):
        self.conn.execute("DELETE FROM review_logs WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM item_marks WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_database.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat: 标记 CRUD + settings 读写方法"
```

---

## Task 3: _shift_marks — 编辑正文后平移标记位置

**Files:**
- Modify: `database.py` 的 `update_item` 方法
- Test: `tests/test_database.py`

- [ ] **Step 1: 写失败测试 — 编辑正文后标记平移**

在 `tests/test_database.py` 末尾追加：

```python
def test_shift_marks_on_content_edit(db):
    """编辑正文（长度变化）后，已有标记应按比例平移"""
    today = date(2026, 6, 26)
    item_id = db.create_item("测试", "0123456789", today, today)  # 长度10
    db.add_mark(item_id, 2, 5, "forgot")   # 标记 "234"
    db.add_mark(item_id, 7, 9, "fuzzy")    # 标记 "78"
    # 把正文缩短为长度5：01234
    db.update_item(item_id, content="01234")
    marks = db.get_marks(item_id)
    # 旧 start=2 → round(2*5/10)=1；旧 start=7 → round(7*5/10)=4
    # 旧 end=5 → round(5*5/10)=3；旧 end=9 → round(9*5/10)=5
    assert len(marks) == 2
    assert marks[0]["start_pos"] == 1
    assert marks[0]["end_pos"] == 3
    assert marks[1]["start_pos"] == 4
    assert marks[1]["end_pos"] == 5


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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_database.py::test_shift_marks_on_content_edit tests/test_database.py::test_shift_marks_clears_when_content_empty tests/test_database.py::test_shift_marks_not_triggered_on_other_fields -v`
Expected: 3 个 FAIL（平移逻辑未实现）

- [ ] **Step 3: 实现 _shift_marks 并在 update_item 中调用**

在 `database.py` 的 `delete_mark` 方法后插入：

```python
    def _shift_marks(self, item_id: int, old_len: int, new_len: int):
        """编辑 content 后按比例平移已有标记位置。
        old_len=0 或 new_len=0 时清空该条目所有标记。
        """
        if old_len == 0 or new_len == 0:
            self.conn.execute("DELETE FROM item_marks WHERE item_id=?", (item_id,))
            self.conn.commit()
            return
        cursor = self.conn.execute(
            "SELECT id, start_pos, end_pos FROM item_marks WHERE item_id=?", (item_id,))
        rows = cursor.fetchall()
        for mark_id, start, end in rows:
            new_start = round(start * new_len / old_len)
            new_end = round(end * new_len / old_len)
            if new_start >= new_end:
                self.conn.execute("DELETE FROM item_marks WHERE id=?", (mark_id,))
            else:
                self.conn.execute(
                    "UPDATE item_marks SET start_pos=?, end_pos=? WHERE id=?",
                    (new_start, new_end, mark_id))
        self.conn.commit()
```

将 `update_item` 方法（L164-176）替换为：

```python
    def update_item(self, item_id: int, **fields):
        allowed = {"title", "content", "status", "round", "interval",
                   "consecutive_correct", "next_review_date", "category_id", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        # 编辑 content 时需平移已有标记
        if "content" in updates:
            old_item = self.get_item(item_id)
            old_len = len(old_item["content"]) if old_item else 0
            new_len = len(updates["content"])
        for date_field in ("next_review_date",):
            if date_field in updates and hasattr(updates[date_field], "isoformat"):
                updates[date_field] = updates[date_field].isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [item_id]
        self.conn.execute(f"UPDATE items SET {set_clause} WHERE id=?", values)
        self.conn.commit()
        if "content" in updates:
            self._shift_marks(item_id, old_len, new_len)
```

- [ ] **Step 4: 运行全部数据库测试，确认通过**

Run: `python -m pytest tests/test_database.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部测试，确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（含 scheduler 测试）

- [ ] **Step 6: 提交**

```bash
git add database.py tests/test_database.py
git commit -m "feat: 编辑正文后按比例平移标记位置"
```

---

## Task 4: ui/notes_box.py — 条目笔记组件

**Files:**
- Create: `ui/notes_box.py`

- [ ] **Step 1: 创建 ui/notes_box.py**

```python
# ui/notes_box.py
import customtkinter as ctk
from ui.theme import small_font, body_font, COLOR_TEXT_SECONDARY


class NotesBox(ctk.CTkFrame):
    """条目级笔记框：失焦时自动保存到数据库。
    在今日背诵展开内容和全部条目展开时复用。
    """
    def __init__(self, parent, db, item_id: int, current_notes: str = "",
                 height: int = 80):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.item_id = item_id
        self._initial_notes = current_notes or ""

        ctk.CTkLabel(self, text="📝 笔记", font=small_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=2, pady=(0, 2))

        self.textbox = ctk.CTkTextbox(self, height=height, font=body_font())
        self.textbox.pack(fill="x")
        if current_notes:
            self.textbox.insert("1.0", current_notes)
        # 失焦时自动保存
        self.textbox.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, event=None):
        new_notes = self.textbox.get("1.0", "end").rstrip("\n")
        if new_notes != self._initial_notes:
            self.db.update_item(self.item_id, notes=new_notes)
            self._initial_notes = new_notes

    def destroy(self):
        # 组件销毁前再保存一次，避免遗漏
        try:
            self._on_focus_out()
        except Exception:
            pass
        super().destroy()
```

- [ ] **Step 2: 冒烟验证（导入无报错）**

Run: `python -c "from ui.notes_box import NotesBox; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 3: 提交**

```bash
git add ui/notes_box.py
git commit -m "feat: 新建 NotesBox 条目笔记组件"
```

---

## Task 5: ui/markable_textbox.py — 可标记+可缩放内容框

**Files:**
- Create: `ui/markable_textbox.py`

- [ ] **Step 1: 创建 ui/markable_textbox.py**

```python
# ui/markable_textbox.py
import customtkinter as ctk
from ui.theme import body_font, small_font, COLOR_TEXT_SECONDARY, COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER


# 标记类型 → 高亮颜色配置
MARK_TAGS = {
    "forgot": {"bg": "#c1554b", "fg": "#ffffff"},   # 红
    "fuzzy":  {"bg": "#e09f3e", "fg": "#000000"},   # 橙
}

FONT_MIN, FONT_MAX = 10, 24
HEIGHT_OPTIONS = [200, 400, 600]


class MarkableTextbox(ctk.CTkFrame):
    """可标记+可缩放的内容展示框。
    - 选中文字 + 点「忘了/模糊」→ 存库并高亮
    - 选中已标记文字 + 点「取消标记」→ 删除覆盖的标记
    - A+/A- 调字号，⤢ 调框高，设置持久化到 settings 表
    """
    def __init__(self, parent, db, item: dict, read_only_marks: bool = False):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.item = item
        self.read_only_marks = read_only_marks  # 已掌握面板只读查看高亮

        # 从 settings 读取字号与框高
        self.font_size = int(db.get_setting("content_font_size", "14"))
        self.height_idx = 0
        saved_h = int(db.get_setting("content_box_height", "200"))
        for i, h in enumerate(HEIGHT_OPTIONS):
            if h >= saved_h:
                self.height_idx = i
                break

        # 工具栏
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 4))
        if not read_only_marks:
            ctk.CTkButton(toolbar, text="🔴 忘了", width=70, height=26,
                          fg_color="#c1554b", hover_color="#a04439",
                          font=small_font(),
                          command=lambda: self._add_mark("forgot")).pack(side="left", padx=2)
            ctk.CTkButton(toolbar, text="🟠 模糊", width=70, height=26,
                          fg_color="#e09f3e", hover_color="#c08a30",
                          font=small_font(),
                          command=lambda: self._add_mark("fuzzy")).pack(side="left", padx=2)
            ctk.CTkButton(toolbar, text="✕ 取消标记", width=80, height=26,
                          fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          font=small_font(),
                          command=self._remove_mark).pack(side="left", padx=2)
        # 字号与框高按钮放右侧
        ctk.CTkButton(toolbar, text="A-", width=32, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._decrease_font).pack(side="right", padx=2)
        ctk.CTkButton(toolbar, text="A+", width=32, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._increase_font).pack(side="right", padx=2)
        ctk.CTkButton(toolbar, text="⤢ 高度", width=60, height=26,
                      fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=small_font(), command=self._cycle_height).pack(side="right", padx=2)

        # 内容文本框
        self.textbox = ctk.CTkTextbox(self, height=HEIGHT_OPTIONS[self.height_idx],
                                       font=ctk.CTkFont(size=self.font_size))
        self.textbox.pack(fill="both", expand=True)
        self.textbox.insert("1.0", item["content"])
        self._apply_marks()
        # 已掌握只读模式下，文本框禁用编辑（但允许选择）
        if read_only_marks:
            self.textbox.configure(state="disabled")

    # ===== 位置转换 =====
    def _pos_to_tkindex(self, pos: int) -> str:
        """字符偏移 → tkinter Text index（'line.char'）"""
        return self.textbox.index(f"1.0 + {pos} chars")

    def _tkindex_to_pos(self, index: str) -> int:
        """tkinter Text index → 字符偏移"""
        # 用 compare 计算：从 1.0 到 index 的字符数
        # 通过 count_chars 方法
        start = self.textbox.index("1.0")
        # 临时启用以计算（只读模式下 disabled 无法 count）
        was_disabled = str(self.textbox.cget("state")) == "disabled"
        if was_disabled:
            self.textbox.configure(state="normal")
        count = self.textbox.count(start, index, "chars")
        if was_disabled:
            self.textbox.configure(state="disabled")
        return count[0] if count else 0

    # ===== 高亮应用 =====
    def _apply_marks(self):
        """根据数据库标记重新应用高亮 tag"""
        # 清除旧 tag
        for tag in MARK_TAGS:
            self.textbox.tag_remove(tag, "1.0", "end")
        # 配置 tag 样式
        for tag, cfg in MARK_TAGS.items():
            self.textbox.tag_config(tag, background=cfg["bg"], foreground=cfg["fg"])
        # 应用新标记
        marks = self.db.get_marks(self.item["id"])
        for m in marks:
            start_idx = self._pos_to_tkindex(m["start_pos"])
            end_idx = self._pos_to_tkindex(m["end_pos"])
            self.textbox.tag_add(m["mark_type"], start_idx, end_idx)

    # ===== 标记操作 =====
    def _get_selection_range(self):
        """返回 (start_pos, end_pos) 或 None（无选中）"""
        try:
            start_idx = self.textbox.index("sel.first")
            end_idx = self.textbox.index("sel.last")
        except Exception:
            return None
        if not start_idx or not end_idx:
            return None
        return self._tkindex_to_pos(start_idx), self._tkindex_to_pos(end_idx)

    def _add_mark(self, mark_type: str):
        if self.read_only_marks:
            return
        sel = self._get_selection_range()
        if not sel:
            return
        start_pos, end_pos = sel
        if start_pos >= end_pos:
            return
        # 先删除被选中范围覆盖的旧标记，再新增
        self._delete_overlapping_marks(start_pos, end_pos)
        self.db.add_mark(self.item["id"], start_pos, end_pos, mark_type)
        self._apply_marks()

    def _remove_mark(self):
        if self.read_only_marks:
            return
        sel = self._get_selection_range()
        if not sel:
            return
        start_pos, end_pos = sel
        self._delete_overlapping_marks(start_pos, end_pos)
        self._apply_marks()

    def _delete_overlapping_marks(self, start_pos: int, end_pos: int):
        """删除与 [start_pos, end_pos) 有重叠的所有标记"""
        marks = self.db.get_marks(self.item["id"])
        for m in marks:
            if m["start_pos"] < end_pos and m["end_pos"] > start_pos:
                self.db.delete_mark(m["id"])

    # ===== 字号与框高 =====
    def _increase_font(self):
        if self.font_size < FONT_MAX:
            self.font_size += 1
            self._apply_font_size()

    def _decrease_font(self):
        if self.font_size > FONT_MIN:
            self.font_size -= 1
            self._apply_font_size()

    def _apply_font_size(self):
        self.textbox.configure(font=ctk.CTkFont(size=self.font_size))
        self.db.set_setting("content_font_size", str(self.font_size))

    def _cycle_height(self):
        self.height_idx = (self.height_idx + 1) % len(HEIGHT_OPTIONS)
        self.textbox.configure(height=HEIGHT_OPTIONS[self.height_idx])
        self.db.set_setting("content_box_height", str(HEIGHT_OPTIONS[self.height_idx]))
```

- [ ] **Step 2: 冒烟验证（导入无报错）**

Run: `python -c "from ui.markable_textbox import MarkableTextbox; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 3: 提交**

```bash
git add ui/markable_textbox.py
git commit -m "feat: 新建 MarkableTextbox 可标记+可缩放内容框"
```

---

## Task 6: review_panel.py 接入 — 今日背诵

**Files:**
- Modify: `ui/review_panel.py` 的 `_render_current_card`（L110-165）和 `_render_complete_state` 不变

- [ ] **Step 1: 修改 review_panel.py，导入新组件**

将 `ui/review_panel.py` 顶部导入区（L1-12）替换为：

```python
# ui/review_panel.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler
from ui.theme import (
    title_font, heading_font, review_title_font, body_font, small_font, big_font,
    COLOR_PERFECT, COLOR_PERFECT_HOVER,
    COLOR_MOSTLY, COLOR_MOSTLY_HOVER,
    COLOR_PARTIAL, COLOR_PARTIAL_HOVER,
    COLOR_WRONG, COLOR_WRONG_HOVER,
    COLOR_TEXT_SECONDARY, PRIMARY,
)
from ui.markable_textbox import MarkableTextbox
from ui.notes_box import NotesBox
```

- [ ] **Step 2: 修改 _render_current_card 的 show_content 分支**

将 `_render_current_card`（L110-165）替换为：

```python
    def _render_current_card(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        if not self.queue:
            self._render_complete_state()
            return

        current = self.queue[0]
        item = current["item"]
        stage_desc = self.scheduler.stage_description(
            item["consecutive_correct"], item["round"])

        card = ctk.CTkFrame(self.card_frame, corner_radius=12)
        card.pack(fill="both", expand=True, pady=10)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text=item['title'],
                     font=review_title_font()).pack(side="left")
        ctk.CTkLabel(header, text=stage_desc, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")

        if current.get("show_content"):
            # 可标记+可缩放内容框
            self.markable_box = MarkableTextbox(card, self.db, item, read_only_marks=False)
            self.markable_box.pack(fill="both", expand=True, padx=20, pady=5)

            # 条目笔记
            self.notes_box = NotesBox(card, self.db, item["id"],
                                       current_notes=item.get("notes", ""), height=70)
            self.notes_box.pack(fill="x", padx=20, pady=(5, 5))

            # 评分按钮
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=(5, 15))

            ctk.CTkButton(btn_frame, text="✓ 完全正确", height=42,
                          fg_color=COLOR_PERFECT, hover_color=COLOR_PERFECT_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("perfect")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="👍 基本正确", height=42,
                          fg_color=COLOR_MOSTLY, hover_color=COLOR_MOSTLY_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("mostly_correct")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="🤔 部分正确", height=42,
                          fg_color=COLOR_PARTIAL, hover_color=COLOR_PARTIAL_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("partial")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="✗ 记错了", height=42,
                          fg_color=COLOR_WRONG, hover_color=COLOR_WRONG_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("wrong")).pack(side="left", padx=4, expand=True)
        else:
            ctk.CTkLabel(card, text="先回忆内容，再点下方按钮查看正文",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=40)
            ctk.CTkButton(card, text="📖 展示内容", width=160, height=38,
                          fg_color=PRIMARY, hover_color=COLOR_PERFECT_HOVER,
                          font=heading_font(),
                          command=self._show_content).pack(pady=10)
```

- [ ] **Step 3: 在 _handle_review 中保存笔记（评分前）**

在 `_handle_review` 方法（L190）开头插入笔记保存逻辑。将 `_handle_review` 开头部分（L190-196）替换为：

```python
    def _handle_review(self, result: str):
        if not self.queue:
            return
        current = self.queue[0]
        item = current["item"]
        today = date.today()

        # 评分前先保存笔记（NotesBox 失焦保存可能未触发）
        if hasattr(self, "notes_box"):
            try:
                self.notes_box._on_focus_out()
            except Exception:
                pass
```

- [ ] **Step 4: 冒烟验证（启动应用）**

Run: `python main.py`
Expected: 应用正常启动，今日待背诵展示内容后可见标记工具栏、字号按钮、笔记框

- [ ] **Step 5: 运行全部测试，确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add ui/review_panel.py
git commit -m "feat: 今日背诵接入 MarkableTextbox + NotesBox"
```

---

## Task 7: list_panels.py 接入 — 全部条目与已掌握

**Files:**
- Modify: `ui/list_panels.py` 的 `AllItemsPanel._render_card`（L75-124）和 `MasteredPanel._render_card`（L228-259）

- [ ] **Step 1: 修改 list_panels.py 导入**

将 `ui/list_panels.py` 导入区（L1-9）替换为：

```python
# ui/list_panels.py
import customtkinter as ctk
from datetime import date
from scheduler import Scheduler
from ui.theme import (
    title_font, heading_font, card_title_font, body_font, small_font,
    COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, COLOR_WARN, COLOR_WARN_HOVER,
    COLOR_TEXT_SECONDARY, PRIMARY, COLOR_PERFECT_HOVER,
)
from ui.markable_textbox import MarkableTextbox
from ui.notes_box import NotesBox
```

- [ ] **Step 2: 修改 AllItemsPanel._render_card，用 MarkableTextbox + NotesBox**

将 `AllItemsPanel._render_card`（L75-124）替换为：

```python
    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 3))
        ctk.CTkLabel(header, text=item['title'],
                     font=card_title_font()).pack(side="left")

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
        ctk.CTkLabel(header, text=status_text, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")

        if self.expanded_item_id == item["id"]:
            # 可标记+可缩放内容框
            self._current_markable = MarkableTextbox(card, self.db, item, read_only_marks=False)
            self._current_markable.pack(fill="x", padx=12, pady=5)

            # 条目笔记
            self._current_notes = NotesBox(card, self.db, item["id"],
                                            current_notes=item.get("notes", ""), height=70)
            self._current_notes.pack(fill="x", padx=12, pady=(0, 5))

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="补签", fg_color=COLOR_WARN, hover_color=COLOR_WARN_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._backfill_review(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=lambda: self._expand(item["id"])).pack(padx=12, pady=(0, 8), anchor="e")
```

- [ ] **Step 3: 修改 MasteredPanel._render_card，只读查看高亮 + 可编辑笔记**

将 `MasteredPanel._render_card`（L228-259）替换为：

```python
    def _render_card(self, item):
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 3))
        ctk.CTkLabel(header, text=item['title'],
                     font=card_title_font()).pack(side="left")
        status_text = "已掌握(一轮)" if item["status"] == "mastered" else "已归档(二轮)"
        ctk.CTkLabel(header, text=status_text, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")

        if self.expanded_item_id == item["id"]:
            # 只读查看高亮（已掌握面板不新增标记，但可见历史高亮）
            self._current_markable = MarkableTextbox(card, self.db, item, read_only_marks=True)
            self._current_markable.pack(fill="x", padx=12, pady=5)

            # 笔记仍可编辑
            self._current_notes = NotesBox(card, self.db, item["id"],
                                            current_notes=item.get("notes", ""), height=70)
            self._current_notes.pack(fill="x", padx=12, pady=(0, 5))

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkButton(btn_frame, text="收起", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=self._collapse).pack(side="right")
            ctk.CTkButton(btn_frame, text="历史", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._show_history(item)).pack(side="right", padx=(0, 5))
            ctk.CTkButton(btn_frame, text="编辑", fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                          width=70, font=body_font(),
                          command=lambda: self._edit_item(item)).pack(side="right", padx=(0, 5))
        else:
            ctk.CTkButton(card, text="展开", width=80, fg_color=COLOR_NEUTRAL,
                          hover_color=COLOR_NEUTRAL_HOVER, font=body_font(),
                          command=lambda: self._expand(item["id"])).pack(padx=12, pady=(0, 8), anchor="e")
```

- [ ] **Step 4: 冒烟验证**

Run: `python main.py`
Expected: 应用启动，全部条目展开后可见可标记内容框+笔记；已掌握展开后只读高亮+可编辑笔记

- [ ] **Step 5: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add ui/list_panels.py
git commit -m "feat: 全部条目/已掌握展开接入 MarkableTextbox + NotesBox"
```

---

## Task 8: edit_dialog.py 接入笔记编辑

**Files:**
- Modify: `ui/edit_dialog.py`（L29-37 正文区、L50-64 保存逻辑）

- [ ] **Step 1: 修改 edit_dialog.py，加笔记编辑区**

将 `ui/edit_dialog.py` 的正文区与提示部分（L29-37）替换为：

```python
        # 正文
        ctk.CTkLabel(self, text="正文：").pack(anchor="w", padx=20)
        self.content_text = ctk.CTkTextbox(self, width=410, height=240)
        self.content_text.pack(padx=20, pady=(5, 8))
        self.content_text.insert("1.0", item["content"])

        # 笔记
        ctk.CTkLabel(self, text="笔记（可选）：").pack(anchor="w", padx=20)
        self.notes_text = ctk.CTkTextbox(self, width=410, height=80)
        self.notes_text.pack(padx=20, pady=(5, 8))
        self.notes_text.insert("1.0", item.get("notes", "") or "")

        # 提示：修改正文不影响已排程的背诵进度
        ctk.CTkLabel(self, text="提示：修改标题/正文/分类不会影响当前背诵进度；修改正文会按比例平移已有标记",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(padx=20, pady=(0, 5))
```

- [ ] **Step 2: 修改 _on_save，保存 notes**

将 `_on_save` 方法（L50-64）替换为：

```python
    def _on_save(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not title:
            messagebox.showwarning("提示", "请输入标题", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "请输入正文", parent=self)
            return
        notes = self.notes_text.get("1.0", "end").rstrip("\n")
        selected = self.category_picker.get_category_id()
        category_id = selected
        self.db.update_item(self.item["id"], title=title, content=content,
                            category_id=category_id, notes=notes)
        if self.on_saved_callback:
            self.on_saved_callback(self.item["id"])
        self.destroy()
```

- [ ] **Step 3: 冒烟验证**

Run: `python main.py`
Expected: 编辑对话框中可见笔记编辑区，保存后笔记内容持久化

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add ui/edit_dialog.py
git commit -m "feat: 编辑对话框新增笔记编辑区"
```

---

## Task 9: 最终验证与打包

**Files:** 无代码改动

- [ ] **Step 1: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（48 个原有测试 + 新增的标记/设置/平移测试）

- [ ] **Step 2: 手动冒烟测试清单**

启动应用 `python main.py`，依次验证：
1. 新建条目 → 展开 → 选中一段文字 → 点「🔴 忘了」→ 文字变红底白字
2. 选中另一段 → 点「🟠 模糊」→ 文字变橙底黑字
3. 选中已标记文字 → 点「✕ 取消标记」→ 高亮消失
4. 点「A+」字号变大，「A-」字号变小，重启应用后字号保持
5. 点「⤢ 高度」框高在 200/400/600 间循环，重启后保持
6. 在笔记框输入文字 → 点别处（失焦）→ 重启应用笔记仍在
7. 今日待背诵展开内容 → 可见历史标记高亮、可新增/取消标记、可编辑笔记
8. 已掌握面板展开 → 可见历史高亮（只读）、笔记可编辑
9. 编辑条目改正文 → 原有标记按比例平移到新位置
10. 删除条目 → 该条目标记一并清除

- [ ] **Step 3: 运行 update.py 重新打包**

Run: `python update.py`
Expected: 测试通过 → 打包完成 → 安装到 `D:\桌面\艾宾浩斯小软件\一点不背.exe` → 快捷方式刷新

- [ ] **Step 4: 验证打包后的 exe 启动**

双击桌面「一点不背」快捷方式，确认应用正常启动且功能可用。

---

## 自审清单

**Spec 覆盖：**
- ✅ 片段标记（忘了/模糊）：Task 2（CRUD）+ Task 5（UI）+ Task 6/7（接入）
- ✅ 取消标记（选中后按按钮）：Task 5 `_remove_mark`
- ✅ 条目笔记：Task 1（notes 字段）+ Task 4（NotesBox）+ Task 6/7/8（接入）
- ✅ 字号缩放（A+/A-，10-24）：Task 5
- ✅ 框高缩放（200/400/600 循环）：Task 5
- ✅ 设置持久化：Task 2（settings CRUD）+ Task 5（读写）
- ✅ 今日背诵+全部条目可见/编辑：Task 6/7
- ✅ 编辑正文平移标记：Task 3
- ✅ 删除条目级联清除标记：Task 2
- ✅ 不改动调度/评分/补签：spec 第 5 节明确

**占位符扫描：** 无 TBD/TODO，所有步骤含完整代码。

**类型一致性：** `add_mark(item_id, start_pos, end_pos, mark_type)` / `get_marks(item_id)` / `delete_mark(mark_id)` / `get_setting(key, default)` / `set_setting(key, value)` / `_shift_marks(item_id, old_len, new_len)` 在所有任务中签名一致。`MarkableTextbox(db, item, read_only_marks)` 与 `NotesBox(db, item_id, current_notes, height)` 在所有接入点一致。
