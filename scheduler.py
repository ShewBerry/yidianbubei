from datetime import date, timedelta

class Scheduler:
    FULL_CYCLE = [1, 2, 4, 7, 15, 30]
    SHORT_CYCLE = [1, 3, 7]

    def schedule_new_item(self, today: date, start_date: date = None) -> dict:
        """新建条目的初始排程。
        - start_date 为 None 或等于 today：首次复习在明天（阶段1）
        - start_date 早于 today：按艾宾浩斯曲线反推当前应处于的阶段和下次复习日期
        """
        if start_date is None:
            start_date = today
        return self.backfill_schedule(start_date, today)

    def backfill_schedule(self, start_date: date, today: date) -> dict:
        """根据开始日期和今天日期，推算当前应处的阶段和下次复习日期。

        规则（按完整周期 FULL_CYCLE 的累计天数）：
        - 阶段N的"应复习日" = start_date + 累计天数（阶段1..N的间隔之和）
        - 找到第一个"应复习日" >= today 的阶段，这就是当前待复习的阶段
        - 该阶段的 next_review_date = max(该阶段应复习日, today)（不早于今天）
        - 若所有阶段应复习日都 < today，说明已完成完整周期，进入待确认掌握
        """
        cumulative = 0
        for stage, interval in enumerate(self.FULL_CYCLE, start=1):
            cumulative += interval
            stage_due_date = start_date + timedelta(days=cumulative)
            if stage_due_date >= today:
                return {
                    "status": "learning",
                    "current_stage": stage,
                    "cycle_type": "full",
                    "cycle_start_date": start_date,
                    "next_review_date": stage_due_date
                }
        # 所有阶段都已到期，进入待确认掌握
        return {
            "status": "pending_mastery",
            "current_stage": len(self.FULL_CYCLE),
            "cycle_type": "full",
            "cycle_start_date": start_date,
            "next_review_date": today
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

    def stage_description(self, stage: int, cycle_type: str) -> str:
        cycle = self.SHORT_CYCLE if cycle_type == "short" else self.FULL_CYCLE
        if stage < 1 or stage > len(cycle):
            return f"第{stage}次复习"
        return f"第{stage}次复习（{cycle[stage - 1]}天后）"
