from datetime import date, timedelta

class Scheduler:
    # 艾宾浩斯遗忘曲线：录入当天为第0天（第1次背诵）
    # 各次背诵日为距录入天的累计天数：0, 1, 2, 4, 7, 15, 30 天
    # 共7次背诵，第7次完成后进入待确认掌握
    FULL_CYCLE = [0, 1, 2, 4, 7, 15, 30]  # 各次背诵的累计天数（距开始日）
    SHORT_CYCLE = [0, 1, 3, 7]  # 短周期：共4次背诵

    def schedule_new_item(self, today: date, start_date: date = None) -> dict:
        """新建条目的初始排程。录入当天即第1次背诵日。
        - start_date 为 None 或等于 today：第1次背诵就在今天（current_stage=1）
        - start_date 早于 today：按艾宾浩斯曲线反推当前应处的阶段和下次背诵日期
        """
        if start_date is None:
            start_date = today
        return self.backfill_schedule(start_date, today)

    def backfill_schedule(self, start_date: date, today: date) -> dict:
        """根据开始日期和今天日期，推算当前应处的阶段和下次背诵日期。

        规则（艾宾浩斯遗忘曲线，累计天数）：
        - 第N次背诵日 = start_date + FULL_CYCLE[N-1] 天（第1次=录入当天，累计0天）
        - 找到第一个"背诵日" >= today 的阶段，即为当前待背诵阶段
        - 该阶段的 next_review_date = 该阶段背诵日
        - 若所有背诵日都 < today，进入待确认掌握
        """
        for stage, days in enumerate(self.FULL_CYCLE, start=1):
            stage_due_date = start_date + timedelta(days=days)
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
        """打卡背诵后推进阶段。背诵日期固定为距 cycle_start_date 的累计天数。
        - 若按时打卡，下次背诵日为下一阶段的累计日期
        - 若延迟打卡（已超过后续阶段日期），跳到第一个未过期的阶段
        - 若所有后续阶段都已过期，进入待确认掌握"""
        cycle = self.SHORT_CYCLE if item["cycle_type"] == "short" else self.FULL_CYCLE
        current_stage = item["current_stage"]
        cycle_start = item["cycle_start_date"]
        if isinstance(cycle_start, str):
            cycle_start = date.fromisoformat(cycle_start)

        # 从下一阶段开始，找第一个背诵日 >= review_date 的阶段
        for stage in range(current_stage + 1, len(cycle) + 1):
            stage_date = cycle_start + timedelta(days=cycle[stage - 1])
            if stage_date >= review_date:
                return {
                    "status": "learning",
                    "current_stage": stage,
                    "cycle_type": item["cycle_type"],
                    "cycle_start_date": cycle_start,
                    "next_review_date": stage_date
                }

        # 所有后续阶段都已过期，进入待确认掌握
        return {
            "status": "pending_mastery",
            "current_stage": len(cycle),
            "cycle_type": item["cycle_type"],
            "cycle_start_date": cycle_start,
            "next_review_date": review_date
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
                "next_review_date": today  # 短周期第1次背诵就在今天
            }
        if result == "forgotten":
            return {
                "status": "learning",
                "current_stage": 1,
                "cycle_type": "full",
                "cycle_start_date": today,
                "next_review_date": today  # 完整周期第1次背诵就在今天
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
        """返回简洁的阶段描述，不显示天数（避免语义歧义）。
        天数信息可在背诵历史记录中查看。"""
        if cycle_type == "short":
            return f"第{stage}次背诵（短周期）"
        return f"第{stage}次背诵"
