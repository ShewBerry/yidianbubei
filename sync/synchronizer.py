# sync/synchronizer.py
"""核心同步逻辑。

设计原则：
- 桌面端 SQLite 是主存储，云端是镜像
- 阶段2：只做"桌面 → 云端"上传（全量 + 增量）
- 阶段4：增加"云端 → 桌面"拉取
- 同步失败不影响本地任何操作
- 不修改 database.py，通过 db.conn 直接读

同步状态 watermark 存在 SQLite settings 表：
- sync_last_upload_at：上次成功上传的时间戳
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable

from sync import client
from sync.auth import get_user_id
from sync.config import is_sync_enabled, load_config
from sync.client import SyncError, AuthExpiredError


# 表名映射：本地表 → 云端表
# 云端表多了 user_id 字段，需要在上传时注入
TABLES = ["categories", "items", "review_logs", "item_marks"]

# 每张表的字段映射：本地列名 → 云端列名
# 大部分一致，只是云端把 id 改成 local_id，把 item_id 改成 item_local_id
# 注意：interval 是 Postgres 保留字，云端统一用 interval_days
FIELD_MAP = {
    "categories": {"id": "local_id"},
    "items": {"id": "local_id", "interval": "interval_days"},
    "review_logs": {"id": "local_id", "item_id": "item_local_id"},
    "item_marks": {"id": "local_id", "item_id": "item_local_id"},
    "settings": {},
}

class Synchronizer:
    """同步器：负责本地 SQLite ↔ Supabase 的数据同步

    重要：同步在后台线程执行，SQLite 连接不能跨线程使用，
    所以这里用独立的只读连接读取本地数据，不影响主线程的 db.conn。
    写入本地（如更新 watermark）也用这个独立连接，避免污染主线程。
    """

    def __init__(self, db):
        self.db = db
        self._db_path = db.db_path  # 用于在子线程打开独立连接
        self._local_conn = None  # 子线程独立连接（懒创建）

    def _get_local_conn(self) -> sqlite3.Connection:
        """获取当前线程的独立 SQLite 连接（只读模式）。
        SQLite 连接不能跨线程，每个子线程需自己创建。
        """
        if self._local_conn is None:
            # 用 check_same_thread=True（默认）但因为是当前线程创建的所以可用
            # uri=True + mode=ro 以只读方式打开，避免与主线程写冲突
            self._local_conn = sqlite3.connect(
                f"file:{self._db_path}?mode=ro", uri=True,
                check_same_thread=False,  # 安全：只读连接可被任意线程使用
            )
            self._local_conn.row_factory = sqlite3.Row
        return self._local_conn

    def _get_setting(self, key: str, default: str = "") -> str:
        cursor = self._get_local_conn().execute(
            "SELECT value FROM settings WHERE key=?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def _set_setting(self, key: str, value: str):
        """写设置：用独立可写连接（只读连接不能写）。
        单条写入，每次新建连接避免线程问题。"""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            conn.commit()
        finally:
            conn.close()

    def full_upload(self, on_progress: Callable[[str, int, int], None] = None) -> dict:
        """全量上传所有表到云端。

        on_progress(table_name, current, total) 进度回调。
        返回 {table: uploaded_count}。
        失败抛 SyncError。
        """
        if not is_sync_enabled():
            raise SyncError("同步未启用")

        user_id = get_user_id()
        if not user_id:
            raise AuthExpiredError("未登录，请先登录")

        stats = {}
        total_tables = len(TABLES)

        for idx, table in enumerate(TABLES):
            if on_progress:
                on_progress(table, idx, total_tables)

            # 读取本地全量数据（用子线程独立连接，避免跨线程问题）
            cursor = self._get_local_conn().execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()

            if not rows:
                stats[table] = 0
                continue

            # 转为云端格式
            cloud_rows = []
            field_map = FIELD_MAP.get(table, {})
            for row in rows:
                record = {}
                for key in row.keys():
                    cloud_key = field_map.get(key, key)
                    record[cloud_key] = row[key]
                record["user_id"] = user_id
                cloud_rows.append(record)

            # 分批 upsert（每批 500 条，避免请求体过大）
            BATCH_SIZE = 500
            uploaded = 0
            for i in range(0, len(cloud_rows), BATCH_SIZE):
                batch = cloud_rows[i:i + BATCH_SIZE]
                client.upsert(table, batch)
                uploaded += len(batch)

            stats[table] = uploaded

        # 记录本次上传时间
        now_iso = datetime.now(timezone.utc).isoformat()
        self._set_setting("sync_last_upload_at", now_iso)

        # 全量上传后，记录 review_logs 的 max id，供增量上传用
        cursor = self._get_local_conn().execute("SELECT MAX(id) FROM review_logs")
        max_log_id = cursor.fetchone()[0]
        if max_log_id:
            self._set_setting("sync_last_uploaded_log_id", str(max_log_id))

        return stats

    def upload_record(self, table: str, local_id: int) -> bool:
        """单条记录增量上传（实时同步用）。

        table: 表名（categories/items/review_logs/item_marks）
        local_id: 本地 id
        返回 True 表示成功，False 表示记录不存在或失败。
        异常会抛出 SyncError。
        """
        if table not in FIELD_MAP or table == "settings":
            return False  # settings 表用全量同步，不支持单条

        user_id = get_user_id()
        if not user_id:
            raise AuthExpiredError("未登录")

        cursor = self._get_local_conn().execute(
            f"SELECT * FROM {table} WHERE id=?", (local_id,))
        row = cursor.fetchone()
        if not row:
            return False

        field_map = FIELD_MAP[table]
        record = {}
        for key in row.keys():
            cloud_key = field_map.get(key, key)
            record[cloud_key] = row[key]
        record["user_id"] = user_id

        client.upsert(table, [record])

        # review_logs 单条上传后更新 max id，保持与增量上传逻辑一致
        if table == "review_logs":
            last_uploaded_id = int(self._get_setting("sync_last_uploaded_log_id", "0"))
            if local_id > last_uploaded_id:
                self._set_setting("sync_last_uploaded_log_id", str(local_id))
        return True

    def upload_table_incremental(self, table: str, since_iso: str = None) -> int:
        """增量上传某张表。

        - review_logs 是追加表（只创建不修改）：只上传 id > last_uploaded_log_id 的新日志，
          避免全量 upsert 刷新所有日志的 updated_at，否则会淹没手机端的增量日志。
        - 其他表（items/categories 等）：本地无 updated_at，简化为全表 upsert。
          数据量小（约 200 条 items），全量 upsert 性能可接受。

        返回上传条数。
        """
        if table not in FIELD_MAP:
            return 0

        user_id = get_user_id()
        if not user_id:
            raise AuthExpiredError("未登录")

        # review_logs 特殊处理：只上传新日志
        if table == "review_logs":
            return self._upload_new_review_logs(user_id)

        cursor = self._get_local_conn().execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        if not rows:
            return 0

        field_map = FIELD_MAP[table]
        cloud_rows = []
        for row in rows:
            record = {}
            for key in row.keys():
                cloud_key = field_map.get(key, key)
                record[cloud_key] = row[key]
            record["user_id"] = user_id
            cloud_rows.append(record)

        BATCH_SIZE = 500
        uploaded = 0
        for i in range(0, len(cloud_rows), BATCH_SIZE):
            batch = cloud_rows[i:i + BATCH_SIZE]
            client.upsert(table, batch)
            uploaded += len(batch)
        return uploaded

    def _upload_new_review_logs(self, user_id: str) -> int:
        """只上传本地新增的 review_logs（id > last_uploaded_log_id）。

        review_logs 是追加表（只创建不修改），无需全量 upsert。
        全量 upsert 会刷新所有日志的 updated_at，导致手机端增量日志被
        大量同 updated_at 的桌面日志淹没（超过 1000 条限制后被截断）。
        """
        last_uploaded_id = int(self._get_setting("sync_last_uploaded_log_id", "0"))

        # 查询本地 id > last_uploaded_id 的新日志
        cursor = self._get_local_conn().execute(
            "SELECT * FROM review_logs WHERE id > ? ORDER BY id ASC",
            (last_uploaded_id,))
        rows = cursor.fetchall()
        if not rows:
            return 0

        field_map = FIELD_MAP["review_logs"]
        cloud_rows = []
        max_id = last_uploaded_id
        for row in rows:
            record = {}
            for key in row.keys():
                cloud_key = field_map.get(key, key)
                record[cloud_key] = row[key]
            record["user_id"] = user_id
            cloud_rows.append(record)
            if row["id"] > max_id:
                max_id = row["id"]

        # 分批 upsert
        BATCH_SIZE = 500
        uploaded = 0
        for i in range(0, len(cloud_rows), BATCH_SIZE):
            batch = cloud_rows[i:i + BATCH_SIZE]
            client.upsert("review_logs", batch)
            uploaded += len(batch)

        # 记录已上传到的最大 id，下次只传更新的
        self._set_setting("sync_last_uploaded_log_id", str(max_id))
        return uploaded

    def incremental_upload_all(self, on_progress: Callable[[str, int, int], None] = None) -> dict:
        """增量上传所有表（实际是全表 upsert，云端按主键 merge）。

        比 full_upload 轻量：不重置 watermark，只确保云端与本地一致。
        适用于实时同步触发。
        """
        if not is_sync_enabled():
            raise SyncError("同步未启用")

        stats = {}
        total = len(TABLES)
        for idx, table in enumerate(TABLES):
            if on_progress:
                on_progress(table, idx, total)
            try:
                count = self.upload_table_incremental(table)
                stats[table] = count
            except SyncError as e:
                stats[table] = f"error: {e}"
                # 继续下一张表，不要因为一张表失败就全停

        now_iso = datetime.now(timezone.utc).isoformat()
        self._set_setting("sync_last_upload_at", now_iso)
        return stats

    def get_last_sync_time(self) -> str | None:
        """获取上次同步时间（ISO 格式），未同步返回 None"""
        ts = self._get_setting("sync_last_upload_at", "")
        return ts if ts else None

