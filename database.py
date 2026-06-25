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

    def create_item(self, title: str, content: str, created_date, next_review_date) -> int:
        cursor = self.conn.execute(
            """INSERT INTO items (title, content, created_date, status, current_stage,
                                   next_review_date, cycle_start_date, cycle_type)
               VALUES (?, ?, ?, 'learning', 1, ?, ?, 'full')""",
            (title, content, created_date.isoformat(), next_review_date.isoformat(), created_date.isoformat())
        )
        self.conn.commit()
        return cursor.lastrowid

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

    def update_item(self, item_id: int, **fields):
        allowed = {"status", "current_stage", "next_review_date",
                   "cycle_start_date", "cycle_type"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        # 日期字段转 isoformat 字符串
        for date_field in ("next_review_date", "cycle_start_date"):
            if date_field in updates and hasattr(updates[date_field], "isoformat"):
                updates[date_field] = updates[date_field].isoformat()
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

    def close(self):
        self.conn.close()
