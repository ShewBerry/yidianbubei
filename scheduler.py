# scheduler.py
from datetime import date, timedelta


class Scheduler:
    ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
    ROUND2_INTERVALS = [3, 7, 14]

    def schedule_new_item(self, today: date) -> dict:
        """新建条目初始状态：今天就要背第1次"""
        return {
            "status": "learning",
            "round": 1,
            "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        }

    def process_review(self, item: dict, today: date, result: str,
                       is_retest: bool = False, is_backfill: bool = False,
                       today_forgotten_count: int = 0) -> dict:
        """处理用户的5级评分反馈，返回新的调度状态。

        评分等级（从好到差）：
          perfect        完全正确  +1
          mostly_correct 基本正确  +1（重背时不递增，仅重背）
          partial        部分正确   0（进度不变，但仍需重背）
          mostly_forgotten 较多遗忘 -1（带回退上限，同日最多累计 -2）
          wrong          记错了    重置为0

        is_retest: True 表示该条目今日非首次出现（重背评分）。
        is_backfill: True 表示补签历史日期。补签时不重背，next_review_date 按补签日+间隔计算。
        today_forgotten_count: 今日该条目已评分 mostly_forgotten 的次数（不含本次）。
            同一日内较多遗忘累计回退上限为 -2，达到上限后不再回退，避免无限重背。
        返回值含 requeue_today 字段：True 表示需追加到今日队列末尾。
        next_review_date 为 None 表示不更新数据库（用于基本正确重背）。
        next_review_date 为空字符串 "" 表示已完成轮次、不再调度。
        next_review_date 为 None 表示重背：不更新数据库中的应背日（保持原应背日），
        条目由调用方排回今日队列重背；未完成则次日继续顺延出现。
        """
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        current_correct = item["consecutive_correct"]

        if result == "perfect":
            new_correct = current_correct + 1
            return self._build_result(item["round"], round_intervals, new_correct, today,
                                      is_backfill=is_backfill)

        elif result == "mostly_correct":
            if is_retest:
                return {
                    "status": item["status"], "round": item["round"],
                    "interval": item["interval"],
                    "consecutive_correct": current_correct,
                    "next_review_date": None,
                    "requeue_today": True
                }
            else:
                new_correct = current_correct + 1
                return self._build_result(item["round"], round_intervals, new_correct, today,
                                          requeue_today=True, is_backfill=is_backfill)

        elif result == "partial":
            # 部分正确：进度不变（0），当日仍需重背
            new_correct = current_correct
            return self._build_result(item["round"], round_intervals, new_correct, today,
                                      requeue_today=True, is_backfill=is_backfill)

        elif result == "mostly_forgotten":
            # 较多遗忘：-1，同日内累计回退上限为 -2（最多执行两次 -1）
            # 达到上限后保持当前进度不再回退，但当日仍需重背
            if today_forgotten_count >= 2:
                new_correct = current_correct  # 不再回退
            else:
                new_correct = max(0, current_correct - 1)
            return self._build_result(item["round"], round_intervals, new_correct, today,
                                      requeue_today=True, is_backfill=is_backfill)

        elif result == "wrong":
            if is_backfill:
                return {
                    "status": "learning", "round": item["round"],
                    "interval": 1, "consecutive_correct": 0,
                    "next_review_date": today + timedelta(days=1),
                    "requeue_today": False
                }
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "next_review_date": None,
                "requeue_today": True
            }

        raise ValueError(f"未知的评分结果: {result}")

    def _build_result(self, round_num: int, round_intervals: list, new_correct: int,
                      today: date, requeue_today: bool = False,
                      is_backfill: bool = False) -> dict:
        """根据新的 consecutive_correct 构建结果。

        补签(is_backfill=True)时：requeue_today 强制为 False，next_review_date = today + interval。
        非补签且 requeue_today=True 时：next_review_date = today（保持今天，关闭应用后不丢失重背条目）。
        非补签且 requeue_today=False 时（完全正确或完成轮次）：next_review_date = today + interval。
        """
        if new_correct >= len(round_intervals):
            new_status = "mastered" if round_num == 1 else "archived"
            new_interval = round_intervals[-1]
            next_date = ""
            requeue_today = False
        else:
            new_status = "learning"
            new_interval = round_intervals[new_correct - 1] if new_correct > 0 else 1
            if is_backfill:
                next_date = today + timedelta(days=new_interval)
                requeue_today = False
            elif requeue_today:
                next_date = None
            else:
                next_date = today + timedelta(days=new_interval)

        return {
            "status": new_status, "round": round_num,
            "interval": new_interval, "consecutive_correct": new_correct,
            "next_review_date": next_date,
            "requeue_today": requeue_today
        }

    def start_round2(self, items: list, today: date) -> list:
        """二轮巩固：批量重置条目为二轮状态"""
        return [{
            "status": "learning", "round": 2, "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        } for item in items]

    def is_due_today(self, item: dict, today: date) -> bool:
        if item["status"] not in ("learning",):
            return False
        next_review = item["next_review_date"]
        if not next_review or next_review == "":
            return False
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        return next_review <= today

    def stage_description(self, consecutive_correct: int, round_num: int) -> str:
        """返回简洁的阶段描述。"""
        if round_num == 2:
            return f"第{consecutive_correct + 1}次背诵（二轮）"
        return f"第{consecutive_correct + 1}次背诵"
