"""一次性校准脚本（本地单端应用，无云端）。

用法：
    python scripts/calibrate.py local   # 校准本地 items 状态与应背日（先备份）
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
    """按新调度语义（有限状态机）重放日志：返回 (state, expected_nrd)。

    终止类「完全正确」结束本轮循环，最终效力按本轮历史最低档（排除基本正确）计算；
    延续类仅进入下一轮，调度状态不变。expected_nrd 在循环结束时更新。"""
    logs = conn.execute(
        "SELECT id, review_date, result FROM review_logs "
        "WHERE item_id=? ORDER BY id", (item_id,)).fetchall()
    scheduler = Scheduler()
    state = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    expected_nrd = None
    session_results = []
    for log in logs:
        log_date = date.fromisoformat(log["review_date"])
        result = log["result"]
        session_results.append(result)
        if result == "perfect":
            # 本轮循环结束：按历史最低档最终化
            res = scheduler.compute_finalize(state, log_date, session_results)
            state = {"round": res["round"], "interval": res["interval"],
                     "consecutive_correct": res["consecutive_correct"],
                     "status": res["status"]}
            if res["next_review_date"] is not None:
                expected_nrd = res["next_review_date"]
            session_results = []  # 开始新的循环
        # else: 延续类仅推进轮次，状态不变
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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "local":
        return calibrate_local()
    print(f"未知子命令: {cmd}（仅支持 local）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
