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
            "consecutive_correct": row[8], "next_review_date": row[9],
            "notes": row[10] if len(row) > 10 else ""
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
        self.conn.execute("DELETE FROM item_marks WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()

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

    def get_today_partial_count(self, item_id: int, today) -> int:
        """返回今日某条目已评分 partial 的次数"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE review_date=? AND item_id=? AND result='partial'",
            (today_str, item_id))
        return cursor.fetchone()[0]

    def get_status_counts(self) -> dict:
        """返回各状态的条目数"""
        cursor = self.conn.execute(
            "SELECT status, COUNT(*) FROM items GROUP BY status")
        counts = {"learning": 0, "mastered": 0, "archived": 0}
        for row in cursor.fetchall():
            counts[row[0]] = row[1]
        return counts

    def get_perfect_count_in_range(self, start_date, end_date) -> int:
        """返回日期范围内 perfect 评分的数量"""
        sd = start_date.isoformat() if hasattr(start_date, "isoformat") else start_date
        ed = end_date.isoformat() if hasattr(end_date, "isoformat") else end_date
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE result='perfect' AND review_date >= ? AND review_date <= ?",
            (sd, ed))
        return cursor.fetchone()[0]

    def get_category_progress(self) -> list:
        """返回每个顶层分类（含子孙）的进度统计"""
        top_cats = self.conn.execute(
            "SELECT id, name FROM categories WHERE parent_id IS NULL ORDER BY name").fetchall()
        result = []
        for cat_id, cat_name in top_cats:
            descendant_ids = self.get_category_descendant_ids(cat_id)
            if not descendant_ids:
                result.append({"id": cat_id, "name": cat_name, "total": 0,
                               "learning": 0, "mastered": 0, "archived": 0})
                continue
            placeholders = ",".join("?" * len(descendant_ids))
            cursor = self.conn.execute(
                f"""SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status='learning' THEN 1 ELSE 0 END) as learning,
                    SUM(CASE WHEN status='mastered' THEN 1 ELSE 0 END) as mastered,
                    SUM(CASE WHEN status='archived' THEN 1 ELSE 0 END) as archived
                    FROM items WHERE category_id IN ({placeholders})""", descendant_ids)
            row = cursor.fetchone()
            result.append({"id": cat_id, "name": cat_name, "total": row[0],
                           "learning": row[1] or 0, "mastered": row[2] or 0, "archived": row[3] or 0})
        return result

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

    def _shift_marks(self, item_id: int, old_len: int, new_len: int):
        """编辑 content 后按比例平移已有标记位置。
        old_len=0 或 new_len=0 时清空该条目所有标记。
        start 向下取整、end 向上取整，避免标记范围被意外压缩消失。
        """
        import math
        if old_len == 0 or new_len == 0:
            self.conn.execute("DELETE FROM item_marks WHERE item_id=?", (item_id,))
            self.conn.commit()
            return
        cursor = self.conn.execute(
            "SELECT id, start_pos, end_pos FROM item_marks WHERE item_id=?", (item_id,))
        rows = cursor.fetchall()
        for mark_id, start, end in rows:
            new_start = math.floor(start * new_len / old_len)
            new_end = math.ceil(end * new_len / old_len)
            if new_start >= new_end or new_start >= new_len:
                self.conn.execute("DELETE FROM item_marks WHERE id=?", (mark_id,))
            else:
                # end 不超过新长度
                new_end = min(new_end, new_len)
                if new_start >= new_end:
                    self.conn.execute("DELETE FROM item_marks WHERE id=?", (mark_id,))
                else:
                    self.conn.execute(
                        "UPDATE item_marks SET start_pos=?, end_pos=? WHERE id=?",
                        (new_start, new_end, mark_id))
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

    def close(self):
        self.conn.close()
