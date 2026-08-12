"""全量校验并修复背诵历史日期（按有限状态机逐次累加重算）。

用法：
    python scripts/rebuild_dates.py            # 执行修复（自动备份 + 生成《修改影响报告》）
    python scripts/rebuild_dates.py --dry-run  # 只校验并生成报告，不修改数据库

修正原则（以背诵次数为基准重算）：
- 取该条目首次背诵日期作为起始锚点；
- 按时间顺序遍历每次背诵记录，根据当次选项（完全正确/基本正确/部分正确/
  较多遗忘/记错了）算出对应理论间隔天数；
- 从首次日期起逐次累加间隔天数，推算出每次背诵应有的理论日期；
- 将数据库中实际记录的背诵日期替换为推算出的理论日期。

下次背诵日期修正：以最后一次背诵的理论日期为基准，结合该次选项对应的间隔
天数，重新计算并更新 items.next_review_date（已掌握/已归档条目保持空，不再调度）。

安全约束（强制执行）：
- 仅修改日期字段（review_logs.review_date、items.next_review_date），
  严禁删除或修改任何选项内容；
- 修改前自动备份原始数据库；
- 首次背诵日期缺失的条目跳过，并在报告中标记"数据不完整，需人工介入"。
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import Scheduler

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ebbinghaus.db"


def backup_db(db_path: Path = DB_PATH) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.parent / f"{db_path.stem}_backup_{ts}.db"
    shutil.copy2(db_path, backup)
    print(f"已备份数据库到: {backup}")
    return backup


def collect_item_ids(conn) -> list:
    """所有有背诵历史（review_logs）的条目 id"""
    rows = conn.execute("SELECT DISTINCT item_id FROM review_logs ORDER BY item_id").fetchall()
    return [r[0] for r in rows]


def fetch_logs(conn, item_id: int) -> list:
    rows = conn.execute(
        "SELECT id, review_date, result, round FROM review_logs "
        "WHERE item_id=? ORDER BY id", (item_id,)).fetchall()
    return [dict(r) for r in rows]


def rebuild_item(conn, scheduler, item_id: int, today=None):
    """重算单个条目的理论日期、间隔档位并同步 items 状态。

    安全约束：只修改 review_logs.review_date / interval_after 与
    items 的调度字段（status/round/interval/consecutive_correct/next_review_date），
    选项内容（result）原样保留。

    运行日（today）的记录保留实际背诵日期（用户当天真实背诵不穿越），
    但其 interval_after 与 items 状态仍按重放修正。

    返回 (status, date_changes, interval_changes, item_changes, skipped)。
    status: "ok" / "skipped_incomplete"
    date_changes: [(log_id, 原日期, 新日期), ...]
    interval_changes: [(log_id, 原间隔, 新间隔), ...]
    item_changes: [(字段名, 原值, 新值), ...]（items 表调度字段变更）
    """
    today = today or date.today()
    today_iso = today.isoformat()
    logs = fetch_logs(conn, item_id)
    if not logs:
        return "ok", [], [], [], False
    corrected, intervals, final = scheduler.compute_historical_dates(logs)
    if corrected is None:
        return "skipped_incomplete", [], [], [], True

    date_changes = []
    for log_id, new_date in corrected:
        old = conn.execute("SELECT review_date FROM review_logs WHERE id=?",
                           (log_id,)).fetchone()[0]
        new_iso = new_date.isoformat()
        # 运行日的记录保留实际日期（不穿越到理论过去日期）
        if old != new_iso and old != today_iso:
            date_changes.append((log_id, old, new_iso))

    # interval_after：决定档位的记录=当日实际间隔；同日其他记录=None（不再占档位）
    interval_changes = []
    for log_id, new_interval in intervals:
        old = conn.execute("SELECT interval_after FROM review_logs WHERE id=?",
                           (log_id,)).fetchone()[0]
        if old != new_interval:
            interval_changes.append((log_id, old, new_interval))

    # items 表同步：目标状态 = 完成全部档位才 mastered/archived，否则学习
    intervals_table = (scheduler.ROUND2_INTERVALS if final["round"] == 2
                       else scheduler.ROUND1_INTERVALS)
    if final.get("incomplete_loop"):
        # 最后一个背诵日未选「完全正确」→ 循环未结束：
        # correct/interval 保持进入循环前（compute 已不推进），下次背诵 = 该日继续
        target_status = "learning"
        last_log_date = logs[-1]["review_date"]
        if last_log_date == today_iso:
            base_date = today
        else:
            base_date = corrected[-1][1]
        target_next = base_date.isoformat()
    elif final["consecutive_correct"] >= len(intervals_table):
        target_status = "archived" if final["round"] == 2 else "mastered"
        target_next = ""
    else:
        target_status = "learning"
        # 下次背诵基准日：最后一条记录若保留实际日期（运行日）用实际日期，否则用理论日期
        last_log_date = logs[-1]["review_date"]
        if last_log_date == today_iso:
            base_date = today
        else:
            base_date = corrected[-1][1]
        target_next = (base_date + timedelta(days=final["interval"])).isoformat()

    item_changes = []
    row = conn.execute("SELECT status, round, interval, consecutive_correct, "
                       "next_review_date FROM items WHERE id=?", (item_id,)).fetchone()
    if row is None:
        return "ok", date_changes, interval_changes, item_changes, False
    fields = {
        "status": target_status,
        "round": final["round"],
        "interval": final["interval"],
        "consecutive_correct": final["consecutive_correct"],
        "next_review_date": target_next,
    }
    for field, new_value in fields.items():
        old_value = row[["status", "round", "interval", "consecutive_correct",
                         "next_review_date"].index(field)]
        if old_value != new_value:
            item_changes.append((field, old_value, new_value))

    # 仅当有差异才写库
    for log_id, old, new_iso in date_changes:
        conn.execute("UPDATE review_logs SET review_date=? WHERE id=?",
                     (new_iso, log_id))
    for log_id, old_i, new_i in interval_changes:
        conn.execute("UPDATE review_logs SET interval_after=? WHERE id=?",
                     (new_i, log_id))
    if item_changes:
        sets = ", ".join(f"{f}=?" for f, _, _ in item_changes)
        values = [v for _, _, v in item_changes]
        conn.execute(f"UPDATE items SET {sets} WHERE id=?", (*values, item_id))

    return "ok", date_changes, interval_changes, item_changes, False


def main():
    parser = argparse.ArgumentParser(description="全量校验并修复背诵历史日期")
    parser.add_argument("--dry-run", action="store_true",
                        help="只校验并生成报告，不修改数据库")
    parser.add_argument("--db", default=None,
                        help="数据库路径（默认 data/ebbinghaus.db）")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    report_path = db_path.parent / "修改影响报告.md"

    if not db_path.exists():
        print(f"未找到数据库: {db_path}")
        return 1

    backup = None
    if not args.dry_run:
        backup = backup_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    scheduler = Scheduler()

    total_items = 0
    total_date_changes = 0
    total_interval_changes = 0
    total_item_changes = 0
    unmastered = []  # 被撤销已掌握/已归档的条目
    modified_items = set()
    skipped = []
    report_lines = []
    report_lines.append("# 修改影响报告")
    report_lines.append("")
    report_lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"- 备份文件：{backup.name if backup else '（dry-run 未备份）'}")
    report_lines.append(f"- 模式：{'执行修复' if not args.dry_run else '校验（dry-run，未修改）'}")
    report_lines.append("")

    for item_id in collect_item_ids(conn):
        total_items += 1
        status, date_changes, interval_changes, item_changes, is_skipped = \
            rebuild_item(conn, scheduler, item_id, today=date.today())
        if is_skipped:
            skipped.append(item_id)
            continue
        if not date_changes and not interval_changes and not item_changes:
            continue  # 无差异，无需报告
        total_date_changes += len(date_changes)
        total_interval_changes += len(interval_changes)
        total_item_changes += len(item_changes)
        modified_items.add(item_id)
        # 撤销已掌握/已归档记录
        for field, old_v, new_v in item_changes:
            if field == "status" and old_v in ("mastered", "archived") and new_v == "learning":
                unmastered.append(item_id)
        if date_changes:
            report_lines.append(f"## 条目 ID {item_id}（修改 {len(date_changes)} 条记录日期）")
            report_lines.append("")
            report_lines.append("| 记录ID | 原日期 | 新日期 |")
            report_lines.append("|---|---|---|")
            for log_id, old, new in date_changes:
                report_lines.append(f"| {log_id} | {old} | {new} |")
            report_lines.append("")
        if interval_changes:
            report_lines.append(f"## 条目 ID {item_id}（修正 {len(interval_changes)} 条间隔档位）")
            report_lines.append("")
            report_lines.append("| 记录ID | 原间隔(天) | 新间隔(天) |")
            report_lines.append("|---|---|---|")
            for log_id, old_i, new_i in interval_changes:
                report_lines.append(f"| {log_id} | {old_i} | {new_i} |")
            report_lines.append("")
        if item_changes:
            report_lines.append(f"## 条目 ID {item_id}（同步 {len(item_changes)} 项调度状态）")
            report_lines.append("")
            report_lines.append("| 字段 | 原值 | 新值 |")
            report_lines.append("|---|---|---|")
            for field, old_v, new_v in item_changes:
                report_lines.append(f"| {field} | {old_v} | {new_v} |")
            report_lines.append("")

    if skipped:
        report_lines.append("## 数据不完整（需人工介入）")
        report_lines.append("")
        report_lines.append("以下条目首次背诵日期缺失，已跳过，请人工核对：")
        report_lines.append("")
        report_lines.append(", ".join(str(i) for i in skipped))
        report_lines.append("")

    report_lines.append(f"## 汇总")
    report_lines.append("")
    report_lines.append(f"- 有历史记录的条目数：{total_items}")
    report_lines.append(f"- 被修改的条目数：{len(modified_items)}")
    report_lines.append(f"- 被修改的记录数（日期）：{total_date_changes}")
    report_lines.append(f"- 被修改的记录数（间隔档位）：{total_interval_changes}")
    report_lines.append(f"- 被同步的调度状态项数：{total_item_changes}")
    report_lines.append(f"- 被撤销「已掌握/已归档」的条目数：{len(unmastered)}")
    if unmastered:
        report_lines.append(f"  （条目 ID：{', '.join(map(str, unmastered))}）")
    report_lines.append(f"- 跳过（数据不完整）条目数：{len(skipped)}")
    report_lines.append("")
    report_lines.append("> 说明：按背诵日（review_date 分组）推算，同一天多条记录合并为当日循环；")
    report_lines.append("> 当日档位取排除「基本正确」后的最低档，仅含基本正确的日按「完全正确」计算；")
    report_lines.append("> 只修改日期/间隔档位/调度状态字段，选项内容（result）原样保留；")
    report_lines.append("> 「已掌握/已归档」要求连续正确遍历完全部间隔档位（correct ≥ 档位数），")
    report_lines.append("> 未达标的已掌握条目自动撤销为学习中并保留当前档位。")

    if not args.dry_run:
        conn.commit()
    conn.close()

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"报告已生成: {report_path}")
    print(f"共 {total_items} 个条目有历史记录，修改 {total_date_changes} 条记录日期、"
          f"{total_interval_changes} 条间隔档位、{total_item_changes} 项调度状态，"
          f"撤销 {len(unmastered)} 个误判的已掌握条目，跳过 {len(skipped)} 条不完整数据。")
    if skipped:
        print(f"需人工介入的条目 ID：{', '.join(str(i) for i in skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
