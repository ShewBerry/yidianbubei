from datetime import date, timedelta

class Scheduler:
    FULL_CYCLE = [1, 2, 4, 7, 15, 30]
    SHORT_CYCLE = [1, 3, 7]

    def schedule_new_item(self, today: date, start_date: date = None) -> dict:
        """新建条目的初始排程。导入当天即第1次复习日。
        - start_date 为 None 或等于 today：第1次复习就在今天（current_stage=1）
        - start_date 早于 today：按艾宾浩斯曲线反推当前应处于的阶段和下次复习日期
        """
        if start_date is None:
            start_date = today
        return self.backfill_schedule(start_date, today)

    def backfill_schedule(self, start_date: date, today: date) -> dict:
        """根据开始日期和今天日期，推算当前应处的阶段和下次复习日期。

        规则（导入当天即第1次复习）：
        - 阶段N的"应复习日" = start_date + 前N-1个间隔之和（阶段1=导入当天，累计0天）
        - 找到第一个"应复习日" >= today 的阶段，这就是当前待复习的阶段
        - 该阶段的 next_review_date = 该阶段应复习日
        - 若所有阶段应复习日都 < today，说明已完成完整周期，进入待确认掌握
        """
        cumulative = 0  # 阶段1的累计天数为0（导入当天）
        for stage, interval in enumerate(self.FULL_CYCLE, start=1):
            stage_due_date = start_date + timedelta(days=cumulative)
            if stage_due_date >= today:
                return {
                    "status": "learning",
                    "current_stage": stage,
                    "cycle_type": "full",
                    "cycle_start_date": start_date,
                    "next_review_date": stage_due_date
                }
            cumulative += interval  # 进入下一阶段前累加当前阶段的间隔
        # 所有阶段都已到期，进入待确认掌握
        return {
            "status": "pending_mastery",
            "current_stage": len(self.FULL_CYCLE),
            "cycle_type": "full",
            "cycle_start_date": start_date,
            "next_review_date": today
        }

    def mark_reviewed(self, item: dict, review_date: date) -> dict:
        """打卡复习后推进阶段。current_stage 是刚完成的复习序号。
        下一次复习的间隔 = 当前阶段的间隔（cycle[current_stage-1]）。
        例如完成阶段1（间隔1天）后，下次复习在 review_date+1天。"""
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
        next_interval = cycle[current_stage - 1]  # 刚完成阶段的间隔，即到下一次复习的天数
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
                "next_review_date": today  # 短周期第1次复习就在今天
            }
        if result == "forgotten":
            return {
                "status": "learning",
                "current_stage": 1,
                "cycle_type": "full",
                "cycle_start_date": today,
                "next_review_date": today  # 完整周期第1次复习就在今天
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
        天数信息可在复习历史记录中查看。"""
        if cycle_type == "short":
            return f"第{stage}次复习（短周期）"
        return f"第{stage}次复习"
