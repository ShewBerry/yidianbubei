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
                status TEXT NOT NULL DEFAULT 'learning',
                current_stage INTEGER NOT NULL DEFAULT 1,
                next_review_date TEXT NOT NULL,
                cycle_start_date TEXT NOT NULL,
                cycle_type TEXT NOT NULL DEFAULT 'full',
                category_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
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
        # 兼容旧库：若 items 表缺少 category_id 列则补上
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(items)")}
        if "category_id" not in cols:
            self.conn.execute("ALTER TABLE items ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
        self.conn.commit()

    # ===== 分类 CRUD =====
    def create_category(self, name: str, parent_id: int = None) -> int:
        cursor = self.conn.execute(
            "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
            (name, parent_id)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_categories(self) -> list:
        """返回所有分类，每项含 id/name/parent_id"""
        cursor = self.conn.execute("SELECT id, name, parent_id FROM categories ORDER BY name")
        return [{"id": row[0], "name": row[1], "parent_id": row[2]} for row in cursor.fetchall()]

    def get_category_children(self, parent_id: int = None) -> list:
        """返回指定父分类下的直接子分类；parent_id=None 返回顶层分类"""
        cursor = self.conn.execute(
            "SELECT id, name, parent_id FROM categories WHERE parent_id IS ? ORDER BY name",
            (parent_id,)
        )
        return [{"id": row[0], "name": row[1], "parent_id": row[2]} for row in cursor.fetchall()]

    def rename_category(self, category_id: int, new_name: str):
        self.conn.execute("UPDATE categories SET name=? WHERE id=?", (new_name, category_id))
        self.conn.commit()

    def delete_category(self, category_id: int):
        """删除分类。子分类因 ON DELETE CASCADE 自动删除；条目的 category_id 因 ON DELETE SET NULL 自动置空"""
        self.conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
        self.conn.commit()

    def get_category_path(self, category_id: int) -> list:
        """返回从根到该分类的路径列表，如 [{id:1,name:'英语'}, {id:2,name:'单词'}]"""
        path = []
        current_id = category_id
        while current_id is not None:
            cursor = self.conn.execute("SELECT id, name, parent_id FROM categories WHERE id=?", (current_id,))
            row = cursor.fetchone()
            if row is None:
                break
            path.insert(0, {"id": row[0], "name": row[1], "parent_id": row[2]})
            current_id = row[2]
        return path

    def create_item(self, title: str, content: str, created_date, next_review_date,
                    current_stage: int = 1, cycle_type: str = "full",
                    cycle_start_date=None, status: str = "learning",
                    category_id: int = None) -> int:
        cursor = self.conn.execute(
            """INSERT INTO items (title, content, created_date, status, current_stage,
                                   next_review_date, cycle_start_date, cycle_type, category_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, content, created_date.isoformat(), status, current_stage,
             next_review_date.isoformat(),
             (cycle_start_date if cycle_start_date else created_date).isoformat(),
             cycle_type, category_id)
        )
        self.conn.commit()
        return cursor.lastrowid

    def _row_to_item(self, row) -> dict:
        return {
            "id": row[0], "title": row[1], "content": row[2],
            "created_date": row[3], "status": row[4], "current_stage": row[5],
            "next_review_date": row[6], "cycle_start_date": row[7], "cycle_type": row[8],
            "category_id": row[9] if len(row) > 9 else None
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

    def get_category_descendant_ids(self, category_id: int) -> list:
        """返回该分类及其所有子孙分类的 id 列表（含自身）"""
        cursor = self.conn.execute(
            """WITH RECURSIVE descendants(id) AS (
                   SELECT id FROM categories WHERE id = ?
                   UNION ALL
                   SELECT c.id FROM categories c
                   JOIN descendants d ON c.parent_id = d.id
               )
               SELECT id FROM descendants""",
            (category_id,)
        )
        return [row[0] for row in cursor.fetchall()]

    def get_items_by_category(self, category_id: int = None, include_descendants: bool = True) -> list:
        """返回指定分类（默认含子孙分类）下的所有条目。
        category_id=None 返回未分类的条目。
        若要查全部条目，用 get_active_items / get_mastered_items。
        """
        if category_id is None:
            cursor = self.conn.execute(
                "SELECT * FROM items WHERE category_id IS NULL ORDER BY created_date DESC"
            )
            return [self._row_to_item(row) for row in cursor.fetchall()]

        if include_descendants:
            ids = self.get_category_descendant_ids(category_id)
            placeholders = ",".join("?" * len(ids))
            cursor = self.conn.execute(
                f"SELECT * FROM items WHERE category_id IN ({placeholders}) ORDER BY created_date DESC",
                ids
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM items WHERE category_id=? ORDER BY created_date DESC",
                (category_id,)
            )
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def update_item(self, item_id: int, **fields):
        allowed = {"status", "current_stage", "next_review_date",
                   "cycle_start_date", "cycle_type", "category_id"}
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
