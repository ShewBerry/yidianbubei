"""一次性校准脚本（电脑端数据为唯一权威）。

用法：
    python scripts/calibrate.py local   # 校准本地 items 状态与应背日（先备份）
    python scripts/calibrate.py cloud   # 校准云端为本地镜像（全量上传 + 删除多余）
"""
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import Scheduler

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ebbinghaus.db"


def backup_db() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"ebbinghaus_backup_{ts}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"已备份数据库到: {backup}")
    return backup


def replay_item_state(conn, item_id):
    """按新调度语义重放日志：返回 (state, expected_nrd)。
    重背结果不更新日期，因此 expected_nrd 保持上一次的有效值。"""
    logs = conn.execute(
        "SELECT id, review_date, result FROM review_logs "
        "WHERE item_id=? ORDER BY id", (item_id,)).fetchall()
    scheduler = Scheduler()
    state = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    expected_nrd = None
    for log in logs:
        log_date = date.fromisoformat(log["review_date"])
        prior_today = conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE item_id=? AND review_date=? AND id < ?",
            (item_id, log["review_date"], log["id"])).fetchone()[0]
        forgotten_count = conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE item_id=? AND review_date=? "
            "AND result='mostly_forgotten' AND id < ?",
            (item_id, log["review_date"], log["id"])).fetchone()[0]
        res = scheduler.process_review(
            state, log_date, log["result"],
            is_retest=prior_today > 0,
            today_forgotten_count=forgotten_count)
        state = {"round": res["round"], "interval": res["interval"],
                 "consecutive_correct": res["consecutive_correct"],
                 "status": res["status"]}
        if res["next_review_date"] is not None:
            expected_nrd = res["next_review_date"]
    return state, expected_nrd


def calibrate_local():
    if not DB_PATH.exists():
        print(f"未找到数据库: {DB_PATH}")
        return 1
    backup_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, status, round, interval, consecutive_correct, "
        "next_review_date FROM items WHERE deleted_at IS NULL").fetchall()
    changed = []
    for row in rows:
        has_logs = conn.execute(
            "SELECT 1 FROM review_logs WHERE item_id=? LIMIT 1",
            (row["id"],)).fetchone()
        if not has_logs:
            continue
        state, expected_nrd = replay_item_state(conn, row["id"])
        nrd_str = (expected_nrd.isoformat()
                   if hasattr(expected_nrd, "isoformat")
                   else expected_nrd)
        diffs = []
        for field, value in (
                ("consecutive_correct", state["consecutive_correct"]),
                ("interval", state["interval"]),
                ("round", state["round"]),
                ("status", state["status"]),
                ("next_review_date", nrd_str)):
            if value != row[field]:
                diffs.append((field, value))
        if diffs:
            changed.append((row["id"], row["title"], diffs))
            for field, value in diffs:
                conn.execute(
                    f"UPDATE items SET {field}=? WHERE id=?", (value, row["id"]))
    conn.commit()
    print(f"共检查 {len(rows)} 条（有日志），校准 {len(changed)} 条:")
    for iid, title, diffs in changed[:30]:
        detail = ", ".join(f"{f}={v}" for f, v in diffs)
        print(f"  item {iid} [{title[:25]}] -> {detail}")
    if len(changed) > 30:
        print(f"  ... 还有 {len(changed) - 30} 条")
    conn.close()
    print("本地校准完成。")
    return 0


def calibrate_cloud():
    if not DB_PATH.exists():
        print(f"未找到数据库: {DB_PATH}")
        return 1
    from database import Database
    from sync.client import _do_request, delete_by_local_ids, fetch_all
    from sync.synchronizer import Synchronizer

    db = Database(str(DB_PATH))
    db.init()  # 确保本地已建 key_folders / key_items 等新表
    sync = Synchronizer(db)
    print("步骤1: 全量上传本地数据到云端 ...")
    stats = sync.full_upload()
    for table, count in stats.items():
        print(f"  {table}: 上传 {count} 条")

    conn = sqlite3.connect(str(DB_PATH))
    for table in ("categories", "items", "review_logs", "item_marks",
                  "key_folders", "key_items"):
        try:
            cloud_rows = fetch_all(
                table, order="folder_local_id.asc" if table == "key_items" else "local_id.asc")
        except Exception as e:
            print(f"  {table}: 云端读取失败（请先执行 sync/schema.sql 建表）: {e}")
            continue
        if table == "key_items":
            local_pairs = {(r[0], r[1]) for r in conn.execute(
                "SELECT folder_id, item_id FROM key_items")}
            cloud_pairs = {(r["folder_local_id"], r["item_local_id"]) for r in cloud_rows}
            extra = sorted(cloud_pairs - local_pairs)
            for fid, iid in extra:
                _do_request("DELETE", "key_items", query={
                    "folder_local_id": f"eq.{fid}",
                    "item_local_id": f"eq.{iid}"})
            print(f"  key_items: 云端 {len(cloud_pairs)} 条，删除多余 {len(extra)} 条")
            continue
        local_ids = {r[0] for r in conn.execute(f"SELECT id FROM {table}")}
        cloud_ids = {r["local_id"] for r in cloud_rows}
        extra = sorted(cloud_ids - local_ids)
        if extra:
            print(f"  删除云端 {table} 多余 {len(extra)} 条: {extra[:20]}")
            delete_by_local_ids(table, extra)
        else:
            print(f"  {table}: 云端与本地一致（{len(cloud_ids)} 条）")
    try:
        cloud_settings = fetch_all("settings", order="key.asc")
        keys = [r["key"] for r in cloud_settings]
        if keys:
            _do_request("DELETE", "settings",
                        query={"key": f"in.({','.join(keys)})"})
            print(f"  已清理云端 settings {len(keys)} 条（不再参与同步）")
    except Exception as e:
        print(f"  settings 清理跳过: {e}")
    conn.close()
    db.close()
    print("云端校准完成。")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "local":
        return calibrate_local()
    if cmd == "cloud":
        return calibrate_cloud()
    print(f"未知子命令: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
