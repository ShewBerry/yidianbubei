from datetime import date, timedelta

class Scheduler:
    FULL_CYCLE = [1, 2, 4, 7, 15, 30]
    SHORT_CYCLE = [1, 3, 7]

    def schedule_new_item(self, today: date) -> dict:
        return {
            "status": "learning",
            "current_stage": 1,
            "cycle_type": "full",
            "cycle_start_date": today,
            "next_review_date": today + timedelta(days=1)
        }

    def mark_reviewed(self, item: dict, review_date: date) -> dict:
        cycle = self.SHORT_CYCLE if item["cycle_type"] == "short" else self.FULL_CYCLE
        current_stage = item["current_stage"]

        if current_stage >= len(cycle):
            # 已是最后阶段，进入待确认掌握
            return {
                "status": "pending_mastery",
                "current_stage": current_stage,
                "cycle_type": item["cycle_type"],
                "cycle_start_date": item["cycle_start_date"],
                "next_review_date": review_date
            }

        next_stage = current_stage + 1
        next_interval = cycle[next_stage - 1]  # 阶段序号1-based，列表0-based
        return {
            "status": "learning",
            "current_stage": next_stage,
            "cycle_type": item["cycle_type"],
            "cycle_start_date": item["cycle_start_date"],
            "next_review_date": review_date + timedelta(days=next_interval)
        }

    def confirm_mastery(self, item: dict, today: date, result: str) -> dict:
        if result == "mastered":
            return {
                "status": "mastered",
                "current_stage": item["current_stage"],
                "cycle_type": item["cycle_type"],
                "cycle_start_date": item["cycle_start_date"],
                "next_review_date": item["next_review_date"]
            }
        if result == "fuzzy":
            return {
                "status": "learning",
                "current_stage": 1,
                "cycle_type": "short",
                "cycle_start_date": today,
                "next_review_date": today + timedelta(days=1)
            }
        if result == "forgotten":
            return {
                "status": "learning",
                "current_stage": 1,
                "cycle_type": "full",
                "cycle_start_date": today,
                "next_review_date": today + timedelta(days=1)
            }
        raise ValueError(f"未知的掌握确认结果: {result}")

    def is_due_today(self, item: dict, today: date) -> bool:
        if item["status"] == "mastered":
            return False
        next_review = item["next_review_date"]
        if isinstance(next_review, str):
            next_review = date.fromisoformat(next_review)
        return next_review <= today
