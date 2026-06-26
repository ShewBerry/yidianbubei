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
