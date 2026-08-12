# scheduler.py
"""背诵调度逻辑：有限状态机模型。

选项分类（两种角色）：
- 终止类：仅「完全正确」(perfect)。选择即结束当前条目的背诵循环。
- 延续类：「基本正确」「部分正确」「较多遗忘」「记错了」。选择任意一项均触发下一轮。

轮次规则：背诵轮次持续循环，直至当前轮选择「完全正确」才停止。
首次背诵选延续类 → 第二次背诵；此后每次未选「完全正确」→ 继续下一轮。

效力计算（核心）：
- 「基本正确」仅作为轮次推进器，不参与最终时间效力的计算。
- 最终时间效力 = 所有历史轮次中，排除「基本正确」后剩余选项里效力最低的那一个。
- 效力排序（低→高）：记错了 < 较多遗忘 < 部分正确 < 完全正确。
- 效力作用于「进入本轮循环前的连续正确数」：
    完全正确   → 连续正确 +1（间隔按艾宾浩斯表推进一档）
    部分正确   → 连续正确不变（间隔不推进）
    较多遗忘   → 连续正确 -1（间隔回退一档，最低 0）
    记错了     → 连续正确重置 0（间隔重新计算 = 1 天）
- 若历史轮次只出现过「基本正确」与「完全正确」，则按「完全正确」计算。
"""
from collections import OrderedDict
from datetime import date, timedelta


class Scheduler:
    ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
    ROUND2_INTERVALS = [3, 7, 14]

    # 效力档位（低→高）；「基本正确」不参与效力计算
    EFFICACY_RANK = {"wrong": 1, "mostly_forgotten": 2, "partial": 3, "perfect": 4}
    TERMINAL_RESULT = "perfect"
    CONTINUE_RESULTS = ("mostly_correct", "partial", "mostly_forgotten", "wrong")

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
                       is_retest: bool = False, is_backfill: bool = False) -> dict:
        """单次评分 → 调度结果（纯计算，不写库）。

        - 补签(is_backfill=True)：无循环，单次评分直接决定最终状态（保持既有语义）。
        - 非补签：「完全正确」结束循环（最终效力由 finalize_session 按本轮历史最低档
          覆盖计算）；其余选项仅推进轮次（requeue_today=True），调度状态保持不变。

        返回值含 requeue_today 字段：True 表示需追加到今日队列末尾重背。
        next_review_date 为 None 表示不更新应背日（延续类轮次）；
        为空字符串 "" 表示已完成轮次、不再调度。
        """
        if is_backfill:
            return self._backfill_result(item, today, result)
        if result == self.TERMINAL_RESULT:
            # 默认按「完全正确」效力（连续正确 +1）；finalize_session 会按历史最低档覆盖
            return self._perfect_result(item, today)
        # 延续类：仅推进轮次，调度状态保持不变
        return {
            "status": item["status"], "round": item["round"],
            "interval": item["interval"],
            "consecutive_correct": item["consecutive_correct"],
            "next_review_date": None,  # 不更新应背日，排回今日队列末尾重背
            "requeue_today": True,
        }

    def apply(self, db, item: dict, today: date, result: str,
              is_retest: bool = False, is_backfill: bool = False,
              session_results: list = None) -> dict:
        """评分 → 调度 + 写库（今日背诵与补签共用入口）。

        今日背诵（非补签）：
        - 完全正确：结束循环，按本轮历史最低档（session_results）最终化并写库；
        - 延续类：仅记录评分日志（log_review），不改变调度状态，排回今日队列。
        补签：单次评分直接最终化并写库。
        """
        if is_backfill:
            sched = self._backfill_result(item, today, result)
            self._persist(db, item, today, sched, result)
            return sched
        if result == self.TERMINAL_RESULT:
            return self.finalize_session(db, item, today,
                                         session_results if session_results else [result])
        # 延续类：只记日志，调度状态不变（效力在结束时才确定）。
        # interval_after 传 None：循环未结束，间隔为「待定」，不写确定数值
        db.log_review(item["id"], today, item["round"], result, None)
        return {
            "status": item["status"], "round": item["round"],
            "interval": item["interval"],
            "consecutive_correct": item["consecutive_correct"],
            "next_review_date": None,
            "requeue_today": True,
        }

    def finalize_session(self, db, item: dict, today: date, results: list) -> dict:
        """本轮背诵循环结束（当前轮选「完全正确」）：按历史最低档计算最终效力并写库。"""
        sched = self.compute_finalize(item, today, results)
        self._persist(db, item, today, sched, "perfect")
        return sched

    def compute_finalize(self, item: dict, today: date, results: list) -> dict:
        """纯计算（不写库）：按历史最低档计算本轮最终状态。

        最终时间效力 = 历史轮次中排除「基本正确」后的最低档：
        记错了 < 较多遗忘 < 部分正确 < 完全正确。
        仅出现过「基本正确/完全正确」时按「完全正确」计算。
        """
        relevant = [r for r in results if r != "mostly_correct"]
        lowest = min(relevant, key=lambda r: self.EFFICACY_RANK[r]) if relevant else "perfect"

        base = item["consecutive_correct"]  # 进入本轮循环前的连续正确数
        if lowest == "wrong":
            new_correct = 0
        elif lowest == "mostly_forgotten":
            new_correct = max(0, base - 1)
        elif lowest == "partial":
            new_correct = base
        else:  # perfect
            new_correct = base + 1

        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        return self._build_result(item["round"], round_intervals, new_correct, today,
                                  is_backfill=False)

    # ===== 内部工具 =====

    def _persist(self, db, item, today, sched, result):
        """按调度结果写库（update_item + log_review）。"""
        update_fields = {
            "status": sched["status"],
            "round": sched["round"],
            "interval": sched["interval"],
            "consecutive_correct": sched["consecutive_correct"],
        }
        if sched["next_review_date"] is not None:
            update_fields["next_review_date"] = sched["next_review_date"]
        db.update_item(item["id"], **update_fields)
        db.log_review(item["id"], today, sched["round"], result, sched["interval"])

    def _perfect_result(self, item: dict, today: date) -> dict:
        """完全正确档：间隔推进一档（艾宾浩斯表）。"""
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        new_correct = item["consecutive_correct"] + 1
        return self._build_result(item["round"], round_intervals, new_correct, today,
                                  is_backfill=False)

    def _backfill_result(self, item: dict, today: date, result: str) -> dict:
        """补签（无循环）：单次评分直接决定最终状态，保持既有语义。

        - 完全正确/基本正确：连续正确 +1
        - 部分正确：连续正确不变
        - 较多遗忘：连续正确 -1（最低 0）
        - 记错了：重置 0，间隔 1 天
        """
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        current = item["consecutive_correct"]
        if result == "perfect":
            return self._build_result(item["round"], round_intervals, current + 1, today,
                                      is_backfill=True)
        if result == "mostly_correct":
            return self._build_result(item["round"], round_intervals, current + 1, today,
                                      is_backfill=True)
        if result == "partial":
            return self._build_result(item["round"], round_intervals, current, today,
                                      is_backfill=True)
        if result == "mostly_forgotten":
            return self._build_result(item["round"], round_intervals, max(0, current - 1), today,
                                      is_backfill=True)
        if result == "wrong":
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "next_review_date": today + timedelta(days=1),
                "requeue_today": False,
            }
        raise ValueError(f"未知的评分结果: {result}")

    def _build_result(self, round_num: int, round_intervals: list, new_correct: int,
                      today: date, requeue_today: bool = False,
                      is_backfill: bool = False) -> dict:
        """根据新的 consecutive_correct 构建结果。

        补签(is_backfill=True)时：requeue_today 强制为 False，next_review_date = today + interval。
        非补签且 requeue_today=True 时：next_review_date = None（不更新应背日，排回今日队列重背）。
        非补签且 requeue_today=False 时（完全正确/最终化）：next_review_date = today + interval。
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

    def _interval_after_result(self, correct: int, result: str, round_num: int) -> tuple:
        """按选项更新连续正确数并返回对应间隔天数。

        完全正确 +1 / 部分正确不变 / 较多遗忘 -1 / 记错了重置 0 / 基本正确不变（仅推进轮次）。
        间隔按艾宾浩斯表取档；连续正确达到上限后取最后一档。
        """
        intervals = self.ROUND2_INTERVALS if round_num == 2 else self.ROUND1_INTERVALS
        if result == "perfect":
            c = correct + 1
        elif result in ("mostly_correct", "partial"):
            c = correct  # 基本正确仅推进轮次，不参与效力；部分正确不推进
        elif result == "mostly_forgotten":
            c = max(0, correct - 1)
        elif result == "wrong":
            c = 0
        else:
            raise ValueError(f"未知的评分结果: {result}")
        if c <= 0:
            interval = 1
        elif c >= len(intervals):
            interval = intervals[-1]
        else:
            interval = intervals[c - 1]
        return c, interval

    def compute_historical_dates(self, logs: list) -> tuple:
        """按背诵日（review_date 分组）推算理论日期与间隔档位（历史数据修复用）。

        logs: 按时间顺序（id 升序）的 [{id, review_date, result, round}]。
        规则（用户确认）：
        - 同一天的多条记录 = 当日背诵循环内的多轮，合并为一次有效背诵；
        - 当日档位 = 排除「基本正确」后的最低档；当日只有「基本正确」时按
          「完全正确」计算（仅计算层，不改动 result 字段）；
        - 基本正确不参与档位计算；
        - 每个背诵日之后按该日档位更新连续正确数，间隔按艾宾浩斯表取档；
        - 日期：锚点 = 首次背诵日，其后每个背诵日 = 前一背诵日 + 前一日的间隔；
        - interval_after：只有「决定当日档位的记录」持有该日实际间隔，
          同日其他记录（如基本正确）为 None，避免占用间隔档位。

        返回 (corrected: [(log_id, 理论日期)],
              intervals: [(log_id, interval_after 或 None)],
              final: {consecutive_correct, interval, round})；
        若首条 review_date 缺失/非法，返回 (None, None, None) 由调用方标记人工介入。
        """
        if not logs:
            return [], [], {"consecutive_correct": 0, "interval": 0, "round": 1}
        first = logs[0]
        try:
            anchor = date.fromisoformat(first["review_date"])
        except (ValueError, TypeError):
            return None, None, None

        # 按 review_date 分组（保持出现顺序）
        days = OrderedDict()
        for log in logs:
            days.setdefault(log["review_date"], []).append(log)
        last_day_key = list(days.keys())[-1]

        correct = 0
        prev_round = first.get("round", 1)
        interval = 0
        corrected = []
        interval_map = {}
        prev_date = None
        incomplete_loop = False  # 最后一个背诵日未选「完全正确」→ 循环未结束
        for day_str, day_logs in days.items():
            if prev_date is None:
                day_date = anchor
            else:
                day_date = prev_date + timedelta(days=interval)
            for log in day_logs:
                corrected.append((log["id"], day_date))

            is_last_day = (day_str == last_day_key)
            relevant = [l for l in day_logs if l["result"] != "mostly_correct"]
            has_perfect = any(l["result"] == "perfect" for l in day_logs)

            if not relevant:
                if is_last_day:
                    # 最后一天只有基本正确且循环未结束：间隔待定，correct 不推进
                    for log in day_logs:
                        interval_map[log["id"]] = None
                    incomplete_loop = True
                    prev_date = day_date
                    continue
                # 中间日只有基本正确 → 当日循环实际已结束，按完全正确计算
                deciding = day_logs[-1]
                lowest = "perfect"
            else:
                if is_last_day and not has_perfect:
                    # 最后一天选过延续类（部分正确/较多遗忘/记错了/基本正确）但未选完全正确
                    # → 循环未结束：间隔待定，correct 不推进
                    for log in day_logs:
                        interval_map[log["id"]] = None
                    incomplete_loop = True
                    prev_date = day_date
                    continue
                deciding = min(relevant, key=lambda l: self.EFFICACY_RANK[l["result"]])
                lowest = deciding["result"]

            correct = self._efficacy_delta(lowest, correct)
            day_round = day_logs[-1].get("round", prev_round)
            interval = self._interval_for_correct(correct, day_round)
            prev_round = day_round
            prev_date = day_date

            # 只有决定档位的记录持有当日间隔，其他记录（基本正确等）为 None
            for log in day_logs:
                interval_map[log["id"]] = interval if log["id"] == deciding["id"] else None

        intervals = [(log_id, interval_map[log_id]) for log_id, _ in corrected]
        return corrected, intervals, {"consecutive_correct": correct,
                                      "interval": interval, "round": prev_round,
                                      "incomplete_loop": incomplete_loop}

    @staticmethod
    def _efficacy_delta(lowest: str, base_correct: int) -> int:
        """按当日决定档位应用连续正确数变化。

        完全正确 +1 / 部分正确 不变 / 较多遗忘 -1（最低0）/ 记错了 归零。
        （当日只有基本正确时 lowest 已被归一化为 perfect）
        """
        if lowest == "wrong":
            return 0
        if lowest == "mostly_forgotten":
            return max(0, base_correct - 1)
        if lowest == "partial":
            return base_correct
        return base_correct + 1  # perfect

    @classmethod
    def _interval_for_correct(cls, correct: int, round_num: int) -> int:
        """按连续正确数查艾宾浩斯档位表得间隔天数。"""
        intervals = cls.ROUND2_INTERVALS if round_num == 2 else cls.ROUND1_INTERVALS
        if correct <= 0:
            return 1
        if correct >= len(intervals):
            return intervals[-1]
        return intervals[correct - 1]

    def start_round2(self, items: list, today: date) -> list:
        """二轮巩固：批量重置条目为二轮状态"""
        return [{
            "status": "learning", "round": 2, "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        } for item in items]

    def is_due_today(self, item: dict, today: date) -> bool:
        if item["status"] != "learning":
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

    @classmethod
    def stage_progress(cls, consecutive_correct: int, round_num: int) -> tuple:
        """返回 (已通过档位数, 总档位数)。已掌握需遍历完全部档位（correct == 档位数）。"""
        intervals = cls.ROUND2_INTERVALS if round_num == 2 else cls.ROUND1_INTERVALS
        passed = min(consecutive_correct, len(intervals))
        return passed, len(intervals)
