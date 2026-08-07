# database.py
import sqlite3
import os
from datetime import date
from ui.html_utils import html_to_plain_text


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

            CREATE TABLE IF NOT EXISTS key_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS key_items (
                folder_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                created_date TEXT NOT NULL,
                PRIMARY KEY (folder_id, item_id),
                FOREIGN KEY (folder_id) REFERENCES key_folders(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
        """)
        # 迁移：为旧库的 items 表补 notes 字段（已存在则忽略）
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(items)")}
        if "notes" not in cols:
            self.conn.execute("ALTER TABLE items ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        # 迁移：为旧库的 items 表补 deleted_at 字段（软删除，回收站用）
        if "deleted_at" not in cols:
            self.conn.execute("ALTER TABLE items ADD COLUMN deleted_at TEXT")
        # 迁移：为旧库的 categories 表补 sort_order 字段（已存在则忽略）
        cat_cols = {row[1] for row in self.conn.execute("PRAGMA table_info(categories)")}
        if "sort_order" not in cat_cols:
            self.conn.execute("ALTER TABLE categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()

    # ===== 分类 CRUD =====
    def create_category(self, name: str, parent_id: int = None) -> int:
        # 新分类的 sort_order 取同级最大值 +1，保证新分类排在末尾
        cursor = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM categories WHERE parent_id IS ?",
            (parent_id,))
        max_order = cursor.fetchone()[0]
        new_order = max_order + 1
        cursor = self.conn.execute(
            "INSERT INTO categories (name, parent_id, sort_order) VALUES (?, ?, ?)",
            (name, parent_id, new_order))
        self.conn.commit()
        return cursor.lastrowid

    def get_categories(self) -> list:
        cursor = self.conn.execute(
            "SELECT id, name, parent_id, sort_order FROM categories ORDER BY sort_order")
        return [{"id": r[0], "name": r[1], "parent_id": r[2], "sort_order": r[3]}
                for r in cursor.fetchall()]

    def get_category_children(self, parent_id: int = None) -> list:
        cursor = self.conn.execute(
            "SELECT id, name, parent_id, sort_order FROM categories WHERE parent_id IS ? ORDER BY sort_order",
            (parent_id,))
        return [{"id": r[0], "name": r[1], "parent_id": r[2], "sort_order": r[3]}
                for r in cursor.fetchall()]

    def get_category_siblings(self, category_id: int) -> list:
        """返回同父分类下的所有兄弟分类（含自身），按 sort_order 排序"""
        cursor = self.conn.execute(
            "SELECT parent_id FROM categories WHERE id=?", (category_id,))
        row = cursor.fetchone()
        if row is None:
            return []
        parent_id = row[0]
        cursor = self.conn.execute(
            "SELECT id, name, parent_id, sort_order FROM categories WHERE parent_id IS ? ORDER BY sort_order",
            (parent_id,))
        return [{"id": r[0], "name": r[1], "parent_id": r[2], "sort_order": r[3]}
                for r in cursor.fetchall()]

    def move_category(self, category_id: int, direction: str):
        """上移/下移分类：与相邻兄弟交换 sort_order。
        direction: 'up' 或 'down'"""
        siblings = self.get_category_siblings(category_id)
        if len(siblings) < 2:
            return
        # 找当前分类在兄弟列表中的位置
        idx = next((i for i, c in enumerate(siblings) if c["id"] == category_id), -1)
        if idx == -1:
            return
        if direction == "up" and idx > 0:
            swap_idx = idx - 1
        elif direction == "down" and idx < len(siblings) - 1:
            swap_idx = idx + 1
        else:
            return  # 已在边界，无法移动
        cur = siblings[idx]
        target = siblings[swap_idx]
        # 交换两者的 sort_order
        self.conn.execute(
            "UPDATE categories SET sort_order=? WHERE id=?",
            (target["sort_order"], cur["id"]))
        self.conn.execute(
            "UPDATE categories SET sort_order=? WHERE id=?",
            (cur["sort_order"], target["id"]))
        self.conn.commit()

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
                    consecutive_correct: int = 0, category_id: int = None,
                    notes: str = "") -> int:
        nrd = next_review_date.isoformat() if hasattr(next_review_date, "isoformat") else next_review_date
        cd = created_date.isoformat() if hasattr(created_date, "isoformat") else created_date
        cursor = self.conn.execute(
            """INSERT INTO items (title, content, created_date, category_id, status,
                                   round, interval, consecutive_correct, next_review_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, content, cd, category_id, status, round, interval,
             consecutive_correct, nrd, notes))
        self.conn.commit()
        return cursor.lastrowid

    def _row_to_item(self, row) -> dict:
        return {
            "id": row[0], "title": row[1], "content": row[2], "created_date": row[3],
            "category_id": row[4], "status": row[5], "round": row[6], "interval": row[7],
            "consecutive_correct": row[8], "next_review_date": row[9],
            "notes": row[10] if len(row) > 10 else "",
            "deleted_at": row[11] if len(row) > 11 else None
        }

    def get_due_items(self, today) -> list:
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        cursor = self.conn.execute(
            """SELECT * FROM items
               WHERE deleted_at IS NULL AND status='learning'
                 AND next_review_date != '' AND next_review_date <= ?
               ORDER BY next_review_date ASC""", (today_str,))
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def get_active_items(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM items WHERE deleted_at IS NULL AND status='learning' ORDER BY next_review_date ASC")
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def get_mastered_items(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM items WHERE deleted_at IS NULL AND status IN ('mastered','archived') ORDER BY created_date DESC")
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def get_item(self, item_id: int) -> dict:
        """按 id 获取单个条目。注意：不过滤 deleted_at，回收站 UI 等场景需要读取已删除条目。
        调用方需自行判断 deleted_at 是否为 None。"""
        cursor = self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,))
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None

    def get_items_by_category(self, category_id: int = None, include_descendants: bool = True) -> list:
        if category_id is None:
            cursor = self.conn.execute(
                "SELECT * FROM items WHERE deleted_at IS NULL AND category_id IS NULL ORDER BY created_date DESC")
            return [self._row_to_item(r) for r in cursor.fetchall()]
        if include_descendants:
            ids = self.get_category_descendant_ids(category_id)
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            cursor = self.conn.execute(
                f"SELECT * FROM items WHERE deleted_at IS NULL AND category_id IN ({placeholders}) ORDER BY created_date DESC",
                ids)
        else:
            cursor = self.conn.execute(
                "SELECT * FROM items WHERE deleted_at IS NULL AND category_id=? ORDER BY created_date DESC", (category_id,))
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def delete_item(self, item_id: int):
        """软删除：标记 deleted_at，不真正删除数据。
        回收站保留 30 天，过期后由 purge_expired_deleted 自动清理。"""
        from datetime import datetime
        now = datetime.now().isoformat()
        self.conn.execute("UPDATE items SET deleted_at=? WHERE id=?", (now, item_id))
        self.conn.commit()

    def get_deleted_items(self) -> list:
        """获取回收站中的条目（已软删除），按删除时间倒序。"""
        cursor = self.conn.execute(
            "SELECT * FROM items WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def restore_item(self, item_id: int):
        """从回收站恢复条目（清除 deleted_at 标记）"""
        self.conn.execute("UPDATE items SET deleted_at=NULL WHERE id=?", (item_id,))
        self.conn.commit()

    def purge_item(self, item_id: int):
        """彻底删除条目（物理删除，不可恢复）。
        用于回收站的"彻底删除"操作，或删除已软删除的条目。"""
        self.conn.execute("DELETE FROM review_logs WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM item_marks WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()

    def purge_expired_deleted(self, days: int = 30):
        """清理回收站中超过指定天数的条目（物理删除）。
        默认保留 30 天。"""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "SELECT id FROM items WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))
        expired_ids = [row[0] for row in cursor.fetchall()]
        for item_id in expired_ids:
            self.purge_item(item_id)
        return len(expired_ids)

    def update_item(self, item_id: int, **fields):
        allowed = {"title", "content", "status", "round", "interval",
                   "consecutive_correct", "next_review_date", "category_id", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        # 编辑 content 时需平移已有标记（按纯文本，HTML 标签不计入）
        if "content" in updates:
            old_item = self.get_item(item_id)
            old_plain = html_to_plain_text(old_item["content"]) if old_item else ""
            new_plain = html_to_plain_text(updates["content"])
        for date_field in ("next_review_date",):
            if date_field in updates and hasattr(updates[date_field], "isoformat"):
                updates[date_field] = updates[date_field].isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [item_id]
        self.conn.execute(f"UPDATE items SET {set_clause} WHERE id=?", values)
        self.conn.commit()
        if "content" in updates:
            self._shift_marks(item_id, old_plain, new_plain)

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

    def get_today_forgotten_count(self, item_id: int, today) -> int:
        """返回今日某条目已评分 mostly_forgotten 的次数（用于回退上限）"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE review_date=? AND item_id=? AND result='mostly_forgotten'",
            (today_str, item_id))
        return cursor.fetchone()[0]

    def get_status_counts(self) -> dict:
        """返回各状态的条目数（不含已软删除）"""
        cursor = self.conn.execute(
            "SELECT status, COUNT(*) FROM items WHERE deleted_at IS NULL GROUP BY status")
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
        """返回每个顶层分类（含子孙）的进度统计。
        用单条递归 CTE 一次查出，避免 N+1 查询。"""
        cursor = self.conn.execute("""
            WITH RECURSIVE cat_tree(root_id, id) AS (
                SELECT id, id FROM categories WHERE parent_id IS NULL
                UNION ALL
                SELECT ct.root_id, c.id FROM categories c
                JOIN cat_tree ct ON c.parent_id = ct.id
            )
            SELECT t.id, t.name,
                   COUNT(i.id) AS total,
                   COALESCE(SUM(CASE WHEN i.status='learning' THEN 1 ELSE 0 END), 0) AS learning,
                   COALESCE(SUM(CASE WHEN i.status='mastered' THEN 1 ELSE 0 END), 0) AS mastered,
                   COALESCE(SUM(CASE WHEN i.status='archived' THEN 1 ELSE 0 END), 0) AS archived
            FROM categories t
            LEFT JOIN cat_tree ct ON ct.root_id = t.id
            LEFT JOIN items i ON i.category_id = ct.id AND i.deleted_at IS NULL
            WHERE t.parent_id IS NULL
            GROUP BY t.id, t.name, t.sort_order
            ORDER BY t.sort_order
        """)
        return [{"id": r[0], "name": r[1], "total": r[2],
                 "learning": r[3], "mastered": r[4], "archived": r[5]}
                for r in cursor.fetchall()]

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

    def get_marks(self, item_id: int, content_len: int = None) -> list:
        """返回该条目的所有合法标记，按 start_pos 升序。
        过滤掉 start>=end 或超出当前 content 长度的非法标记（容错：编辑后位置漂移）。
        content_len: 调用方已知纯文本长度时可传入，避免内部重复 get_item + html_to_plain_text。
        """
        if content_len is None:
            item = self.get_item(item_id)
            content_len = len(html_to_plain_text(item["content"])) if item else 0
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

    def _shift_marks(self, item_id: int, old_text: str, new_text: str):
        """编辑 content 后平移已有标记位置（基于纯文本，HTML 标签不计入）。

        用公共前缀+后缀定位编辑区段，只平移编辑点之后的标记：
        - 标记完全在编辑区段之前：位置不变
        - 标记完全在编辑区段之后：位置整体增量平移 delta = new_len - old_len
        - 标记跨越或在编辑区段内：删除（无法精确恢复）

        这样局部编辑（如在开头插入1字）只影响后续标记的位置，
        不会按比例错误缩放所有标记。
        """
        old_len = len(old_text)
        new_len = len(new_text)
        if old_len == 0 or new_len == 0:
            # 旧或新为空：无法定位编辑点，清空所有标记
            self.conn.execute("DELETE FROM item_marks WHERE item_id=?", (item_id,))
            self.conn.commit()
            return
        # 找最长公共前缀
        prefix_len = 0
        max_prefix = min(old_len, new_len)
        while prefix_len < max_prefix and old_text[prefix_len] == new_text[prefix_len]:
            prefix_len += 1
        # 找最长公共后缀（不能与前缀重叠）
        suffix_len = 0
        max_suffix = min(old_len - prefix_len, new_len - prefix_len)
        while (suffix_len < max_suffix
               and old_text[old_len - 1 - suffix_len] == new_text[new_len - 1 - suffix_len]):
            suffix_len += 1
        # 编辑区段在 old 中：[prefix_len, old_edit_end)
        old_edit_end = old_len - suffix_len
        # 编辑区段在 new 中：[prefix_len, new_edit_end)
        new_edit_end = new_len - suffix_len
        delta = new_edit_end - old_edit_end  # 编辑点之后的平移量

        cursor = self.conn.execute(
            "SELECT id, start_pos, end_pos FROM item_marks WHERE item_id=?", (item_id,))
        rows = cursor.fetchall()
        for mark_id, start, end in rows:
            if end <= prefix_len:
                # 标记完全在编辑区段之前：位置不变
                continue
            if start >= old_edit_end:
                # 标记完全在编辑区段之后：整体增量平移
                new_start = start + delta
                new_end = end + delta
                # 边界容错（不应超出新长度）
                if new_start >= new_end or new_start >= new_len:
                    self.conn.execute("DELETE FROM item_marks WHERE id=?", (mark_id,))
                else:
                    new_end = min(new_end, new_len)
                    if new_start >= new_end:
                        self.conn.execute("DELETE FROM item_marks WHERE id=?", (mark_id,))
                    else:
                        self.conn.execute(
                            "UPDATE item_marks SET start_pos=?, end_pos=? WHERE id=?",
                            (new_start, new_end, mark_id))
            else:
                # 标记跨越或在编辑区段内：删除（无法精确恢复）
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

    # ===== 重点条目 CRUD =====
    def create_key_folder(self, name: str) -> int:
        from datetime import date as _date
        cursor = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM key_folders")
        new_order = cursor.fetchone()[0] + 1
        cursor = self.conn.execute(
            "INSERT INTO key_folders (name, sort_order, created_date) VALUES (?, ?, ?)",
            (name, new_order, _date.today().isoformat()))
        self.conn.commit()
        return cursor.lastrowid

    def rename_key_folder(self, folder_id: int, new_name: str):
        self.conn.execute(
            "UPDATE key_folders SET name=? WHERE id=?", (new_name, folder_id))
        self.conn.commit()

    def delete_key_folder(self, folder_id: int):
        self.conn.execute("DELETE FROM key_folders WHERE id=?", (folder_id,))
        self.conn.commit()

    def get_key_folders(self) -> list:
        cursor = self.conn.execute(
            "SELECT id, name, sort_order, created_date FROM key_folders "
            "ORDER BY sort_order, id")
        return [{"id": r[0], "name": r[1], "sort_order": r[2], "created_date": r[3]}
                for r in cursor.fetchall()]

    def add_item_to_key_folder(self, folder_id: int, item_id: int):
        from datetime import date as _date
        self.conn.execute(
            "INSERT OR IGNORE INTO key_items (folder_id, item_id, created_date) "
            "VALUES (?, ?, ?)",
            (folder_id, item_id, _date.today().isoformat()))
        self.conn.commit()

    def remove_item_from_key_folder(self, folder_id: int, item_id: int):
        self.conn.execute(
            "DELETE FROM key_items WHERE folder_id=? AND item_id=?",
            (folder_id, item_id))
        self.conn.commit()

    def get_key_folder_items(self, folder_id: int) -> list:
        cursor = self.conn.execute(
            """SELECT i.* FROM items i
               JOIN key_items ki ON ki.item_id = i.id
               WHERE ki.folder_id=? AND i.deleted_at IS NULL
               ORDER BY ki.created_date DESC, i.id DESC""", (folder_id,))
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def is_item_in_key_folder(self, folder_id: int, item_id: int) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM key_items WHERE folder_id=? AND item_id=?",
            (folder_id, item_id))
        return cursor.fetchone() is not None

    def get_item_key_folder_ids(self, item_id: int) -> list:
        cursor = self.conn.execute(
            "SELECT folder_id FROM key_items WHERE item_id=? ORDER BY created_date",
            (item_id,))
        return [r[0] for r in cursor.fetchall()]

    def close(self):
        self.conn.close()
