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
                       is_retest: bool = False) -> dict:
        """处理用户的4级评分反馈，返回新的调度状态。

        is_retest: True 表示该条目今日非首次出现（重背评分）。
        返回值含 requeue_today 字段：True 表示需追加到今日队列末尾。
        next_review_date 为 None 表示不更新数据库。
        """
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        current_correct = item["consecutive_correct"]

        if result == "perfect":
            new_correct = current_correct + 1
            return self._build_result(item["round"], round_intervals, new_correct, today)

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
                                          requeue_today=True)

        elif result == "partial":
            new_correct = max(0, current_correct - 2)
            return self._build_result(item["round"], round_intervals, new_correct, today,
                                      requeue_today=True)

        elif result == "wrong":
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "next_review_date": today + timedelta(days=1),
                "requeue_today": True
            }

        raise ValueError(f"未知的评分结果: {result}")

    def _build_result(self, round_num: int, round_intervals: list, new_correct: int,
                      today: date, requeue_today: bool = False) -> dict:
        """根据新的 consecutive_correct 构建结果。"""
        if new_correct >= len(round_intervals):
            new_status = "mastered" if round_num == 1 else "archived"
            new_interval = round_intervals[-1]
            next_date = ""
            requeue_today = False
        else:
            new_status = "learning"
            new_interval = round_intervals[new_correct - 1] if new_correct > 0 else 1
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
