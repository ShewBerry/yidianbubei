# tests/test_scheduler.py
from datetime import date, timedelta
from scheduler import Scheduler


class FakeDB:
    """finalize_session 写库用：记录 update_item/log_review 调用并更新 item"""

    def __init__(self, item):
        self.item = item
        self.updates = []
        self.logs = []

    def update_item(self, item_id, **fields):
        self.updates.append(dict(fields))
        self.item.update(fields)

    def log_review(self, *args):
        self.logs.append(args)


def base_item(correct=0, interval=0, round_num=1, status="learning"):
    return {"id": 1, "round": round_num, "interval": interval,
            "consecutive_correct": correct, "status": status}


def test_round1_intervals():
    s = Scheduler()
    assert s.ROUND1_INTERVALS == [1, 2, 3, 5, 8, 13, 21, 34]


def test_round2_intervals():
    s = Scheduler()
    assert s.ROUND2_INTERVALS == [3, 7, 14]


def test_effcacy_rank_order():
    """效力排序（低→高）：记错了 < 较多遗忘 < 部分正确 < 完全正确；基本正确不参与"""
    s = Scheduler()
    assert s.EFFICACY_RANK["wrong"] < s.EFFICACY_RANK["mostly_forgotten"] < \
        s.EFFICACY_RANK["partial"] < s.EFFICACY_RANK["perfect"]
    assert "mostly_correct" not in s.EFFICACY_RANK


def test_schedule_new_item_initial_state():
    s = Scheduler()
    today = date(2026, 6, 26)
    result = s.schedule_new_item(today)
    assert result["status"] == "learning"
    assert result["round"] == 1
    assert result["interval"] == 0
    assert result["consecutive_correct"] == 0
    assert result["next_review_date"] == today


# ===== 轮次规则：延续类只推进轮次，状态不变 =====

def test_process_review_mostly_correct_does_not_change_state():
    """基本正确：仅推进轮次，不参与效力计算，调度状态不变"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=4, interval=5)
    result = s.process_review(item, today, "mostly_correct", is_retest=False)
    assert result["consecutive_correct"] == 4  # 不推进
    assert result["interval"] == 5  # 不变
    assert result["next_review_date"] is None  # 不更新日期
    assert result["requeue_today"] is True


def test_process_review_partial_does_not_change_state():
    """部分正确：仅推进轮次，调度状态不变"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 6
    assert result["interval"] == 13
    assert result["next_review_date"] is None
    assert result["requeue_today"] is True


def test_process_review_forgotten_does_not_change_state():
    """较多遗忘：仅推进轮次（无同日回退上限，效力在结束时统一按最低档算）"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=4, interval=5)
    result = s.process_review(item, today, "mostly_forgotten", is_retest=False)
    assert result["consecutive_correct"] == 4  # 状态不变
    assert result["interval"] == 5
    assert result["next_review_date"] is None
    assert result["requeue_today"] is True


def test_process_review_wrong_does_not_change_state():
    """记错了：仅推进轮次，调度状态不变（重新计算在结束时按最低档生效）"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=7, interval=21)
    result = s.process_review(item, today, "wrong", is_retest=False)
    assert result["consecutive_correct"] == 7
    assert result["interval"] == 21
    assert result["next_review_date"] is None
    assert result["requeue_today"] is True


def test_requeue_results_never_set_next_review_date():
    """延续类结果都不应更新应背日期"""
    s = Scheduler()
    today = date(2026, 6, 26)
    for result in ("mostly_correct", "partial", "mostly_forgotten", "wrong"):
        r = s.process_review(base_item(correct=4, interval=5), today, result, is_retest=False)
        assert r["next_review_date"] is None, f"{result} 不应更新日期"
        assert r["requeue_today"] is True


def test_process_review_perfect_default():
    """完全正确（单次即结束）：间隔推进一档"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=0, interval=0)
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1  # ROUND1_INTERVALS[0]
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is False


def test_process_review_perfect_completes_round1():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=7, interval=21)
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 8
    assert result["status"] == "mastered"
    assert result["next_review_date"] == ""
    assert result["requeue_today"] is False


def test_process_review_perfect_completes_round2():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=2, interval=7, round_num=2)
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 3
    assert result["status"] == "archived"
    assert result["next_review_date"] == ""


# ===== 效力计算：最终时间效力 = 历史轮次中排除基本正确后的最低档 =====

def test_finalize_perfect_only():
    """只选过完全正确：按完全正确计算（连续正确 +1）"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=0, interval=0)
    sched = s.finalize_session(FakeDB(item), item, today, ["perfect"])
    assert sched["consecutive_correct"] == 1
    assert sched["interval"] == 1
    assert sched["next_review_date"] == today + timedelta(days=1)


def test_finalize_mostly_correct_then_perfect():
    """只出现过基本正确与完全正确：按完全正确计算"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=2, interval=3)
    sched = s.finalize_session(FakeDB(item), item, today, ["mostly_correct", "perfect"])
    assert sched["consecutive_correct"] == 3  # 基本正确不参与
    assert sched["interval"] == 3  # ROUND1_INTERVALS[2]


def test_finalize_partial_then_perfect():
    """历史最低档为部分正确：间隔不推进"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today, ["partial", "perfect"])
    assert sched["consecutive_correct"] == 6  # 不变
    assert sched["interval"] == 13


def test_finalize_forgotten_then_perfect():
    """历史最低档为较多遗忘：间隔回退一档"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today, ["mostly_forgotten", "perfect"])
    assert sched["consecutive_correct"] == 5  # 6-1
    assert sched["interval"] == 8  # ROUND1_INTERVALS[4]


def test_finalize_wrong_then_perfect():
    """历史最低档为记错了：重新计算间隔"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today, ["wrong", "perfect"])
    assert sched["consecutive_correct"] == 0  # 重置
    assert sched["interval"] == 1


def test_finalize_lowest_wins_over_multiple_rounds():
    """多次轮次取最低档：wrong 覆盖 partial"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today,
                               ["partial", "wrong", "perfect"])
    assert sched["consecutive_correct"] == 0  # wrong 最低


def test_finalize_forgotten_overrides_partial():
    """用户示例：循环中出现较多遗忘 + 部分正确 → 最终按较多遗忘（-1）"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today,
                               ["mostly_forgotten", "partial", "perfect"])
    assert sched["consecutive_correct"] == 5  # 6 - 1
    assert sched["interval"] == 8  # ROUND1_INTERVALS[4]


def test_finalize_partial_alone_is_neutral():
    """只出现部分正确（+基本正确）→ 最终按部分正确（0，不推进）"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today,
                               ["mostly_correct", "partial", "perfect"])
    assert sched["consecutive_correct"] == 6  # 不变
    assert sched["interval"] == 13


def test_finalize_mostly_correct_only_is_neutral():
    """基本正确作为再来一轮的中性操作：不干扰任何间隔计算"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today,
                               ["mostly_correct", "mostly_correct", "perfect"])
    assert sched["consecutive_correct"] == 7  # 只有 perfect 参与 → +1
    assert sched["interval"] == 21  # ROUND1_INTERVALS[6]


def test_finalize_forgotten_twice_rolls_back_once():
    """多次较多遗忘也只回退一档（无同日累计上限，效力取档位）"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=6, interval=13)
    sched = s.finalize_session(FakeDB(item), item, today,
                               ["mostly_forgotten", "mostly_forgotten", "perfect"])
    assert sched["consecutive_correct"] == 5  # 只回退一档


def test_finalize_wrong_at_zero_stays_zero():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=0, interval=1)
    sched = s.finalize_session(FakeDB(item), item, today, ["wrong", "perfect"])
    assert sched["consecutive_correct"] == 0


def test_finalize_completes_round():
    """结束轮次时最低档为完全正确：连续正确达到上限 → mastered"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=7, interval=21)
    sched = s.finalize_session(FakeDB(item), item, today, ["perfect"])
    assert sched["consecutive_correct"] == 8
    assert sched["status"] == "mastered"
    assert sched["next_review_date"] == ""


def test_finalize_persists_to_db():
    """最终化应写库：update_item + log_review(perfect)"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = base_item(correct=0, interval=0)
    db = FakeDB(item)
    s.finalize_session(db, item, today, ["wrong", "perfect"])
    assert db.updates and db.updates[-1]["consecutive_correct"] == 0
    assert db.updates[-1]["interval"] == 1
    assert db.logs and db.logs[-1][3] == "perfect"


# ===== 补签：单次评分直接决定最终状态（保持既有语义） =====

def test_backfill_mostly_correct_advances():
    """补签基本正确：保持旧语义 +1，不重背，next_review_date = 补签日 + interval"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = base_item(correct=0, interval=0)
    result = s.process_review(item, review_date, "mostly_correct",
                              is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1
    assert result["next_review_date"] == review_date + timedelta(days=1)
    assert result["requeue_today"] is False


def test_backfill_partial():
    """补签部分正确：进度不变，不重背"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = base_item(correct=6, interval=13)
    result = s.process_review(item, review_date, "partial",
                              is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 6
    assert result["interval"] == 13
    assert result["next_review_date"] == review_date + timedelta(days=13)
    assert result["requeue_today"] is False


def test_backfill_forgotten_rolls_back_one():
    """补签较多遗忘：回退一档（补签无循环，直接按该档位计算）"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = base_item(correct=4, interval=5)
    result = s.process_review(item, review_date, "mostly_forgotten",
                              is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 3
    assert result["interval"] == 3  # ROUND1_INTERVALS[2]
    assert result["next_review_date"] == review_date + timedelta(days=3)
    assert result["requeue_today"] is False


def test_backfill_wrong():
    """补签记错了：重置 0，间隔 1 天，不重背"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = base_item(correct=7, interval=21)
    result = s.process_review(item, review_date, "wrong",
                              is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == review_date + timedelta(days=1)
    assert result["requeue_today"] is False


# ===== 其余 =====

def test_start_round2():
    s = Scheduler()
    today = date(2026, 6, 26)
    items = [{"id": 1, "round": 1, "interval": 34, "consecutive_correct": 8, "status": "mastered"},
             {"id": 2, "round": 1, "interval": 34, "consecutive_correct": 8, "status": "mastered"}]
    results = s.start_round2(items, today)
    for r in results:
        assert r["round"] == 2
        assert r["status"] == "learning"
        assert r["interval"] == 0
        assert r["consecutive_correct"] == 0
        assert r["next_review_date"] == today


def test_is_due_today_true_when_next_review_equals_today():
    s = Scheduler()
    today = date(2026, 6, 26)
    assert s.is_due_today({"next_review_date": today, "status": "learning"}, today) is True


def test_is_due_today_true_when_next_review_before_today():
    s = Scheduler()
    today = date(2026, 6, 26)
    assert s.is_due_today({"next_review_date": today - timedelta(days=2), "status": "learning"}, today) is True


def test_is_due_today_false_when_future():
    s = Scheduler()
    today = date(2026, 6, 26)
    assert s.is_due_today({"next_review_date": today + timedelta(days=1), "status": "learning"}, today) is False


def test_is_due_today_false_when_mastered():
    s = Scheduler()
    today = date(2026, 6, 26)
    assert s.is_due_today({"next_review_date": today, "status": "mastered"}, today) is False


def test_is_due_today_false_when_empty_string():
    s = Scheduler()
    today = date(2026, 6, 26)
    assert s.is_due_today({"next_review_date": "", "status": "learning"}, today) is False


def test_is_due_today_handles_iso_string():
    s = Scheduler()
    today = date(2026, 6, 26)
    assert s.is_due_today({"next_review_date": "2026-06-26", "status": "learning"}, today) is True


def test_stage_description_round1():
    s = Scheduler()
    assert s.stage_description(0, 1) == "第1次背诵"
    assert s.stage_description(7, 1) == "第8次背诵"


def test_stage_description_round2():
    s = Scheduler()
    assert s.stage_description(0, 2) == "第1次背诵（二轮）"
    assert s.stage_description(2, 2) == "第3次背诵（二轮）"


# ===== 历史数据重算：按状态机逐次累加理论日期 =====

def mklog(lid, review_date, result, round_num=1):
    if isinstance(review_date, str):
        review_date_str = review_date
    else:
        review_date_str = review_date.isoformat()
    return {"id": lid, "review_date": review_date_str,
            "result": result, "round": round_num}


def test_compute_historical_dates_single_perfect():
    """单次完全正确：理论日期=锚点，最终间隔推进一档"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    corrected, intervals, final = s.compute_historical_dates(
        [mklog(1, anchor, "perfect")])
    assert corrected == [(1, anchor)]
    assert final["consecutive_correct"] == 1
    assert final["interval"] == 1


def test_compute_historical_dates_two_perfect():
    """两次完全正确：第二次 = 锚点 + 1 天，间隔推进到 2 天"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    corrected, intervals, final = s.compute_historical_dates(
        [mklog(1, anchor, "perfect"), mklog(2, anchor + timedelta(days=1), "perfect")])
    assert corrected == [(1, anchor), (2, anchor + timedelta(days=1))]
    assert final["consecutive_correct"] == 2
    assert final["interval"] == 2


def test_compute_historical_dates_wrong_then_perfect():
    """记错了（间隔重置1）→ 完全正确：第二次 = 锚点 + 1 天"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    corrected, intervals, final = s.compute_historical_dates(
        [mklog(1, anchor, "wrong"), mklog(2, anchor + timedelta(days=1), "perfect")])
    assert corrected == [(1, anchor), (2, anchor + timedelta(days=1))]
    assert final["consecutive_correct"] == 1
    assert final["interval"] == 1


def test_compute_historical_dates_forgotten_rolls_back():
    """中间日「较多遗忘」回退一档；最后一天完全正确结束循环"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "perfect"),
            mklog(2, anchor + timedelta(days=1), "perfect"),
            mklog(3, anchor + timedelta(days=3), "mostly_forgotten"),
            mklog(4, anchor + timedelta(days=4), "perfect")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    # day1 perfect c1 i1；day2(锚+1) perfect c2 i2；day3(锚+3) forgotten c1 i1；
    # day4(锚+4) perfect c2 i2 → final c2 i2
    assert corrected == [(1, anchor),
                         (2, anchor + timedelta(days=1)),
                         (3, anchor + timedelta(days=3)),
                         (4, anchor + timedelta(days=4))]
    assert final["consecutive_correct"] == 2
    assert final["interval"] == 2
    assert final["incomplete_loop"] is False


def test_compute_historical_dates_basic_only_days_count_as_perfect():
    """中间日只有基本正确按完全正确推进；最后一个背诵日未选完全正确 → 循环未结束不推进"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    # 三个不同背诵日，都是只有基本正确
    logs = [mklog(1, anchor, "mostly_correct"),
            mklog(2, anchor + timedelta(days=1), "mostly_correct"),
            mklog(3, anchor + timedelta(days=3), "mostly_correct")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    # 前两日按完全正确：correct 1 → 2，间隔 1 → 2
    # 最后一日循环未结束：correct 保持 2、间隔保持 2、该日间隔待定
    assert corrected == [(1, anchor),
                         (2, anchor + timedelta(days=1)),
                         (3, anchor + timedelta(days=3))]
    assert final["consecutive_correct"] == 2
    assert final["interval"] == 2
    assert final["incomplete_loop"] is True
    interval_by_id = dict(intervals)
    assert interval_by_id[1] == 1
    assert interval_by_id[2] == 2
    assert interval_by_id[3] is None  # 最后一天循环未结束 → 间隔待定


def test_compute_historical_dates_last_day_perfect_completes():
    """最后一个背诵日选完全正确 → 循环结束，间隔确定，incomplete_loop=False"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "mostly_correct"),
            mklog(2, anchor + timedelta(days=1), "mostly_correct"),
            mklog(3, anchor + timedelta(days=3), "perfect")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    assert final["consecutive_correct"] == 3
    assert final["interval"] == 3
    assert final["incomplete_loop"] is False
    interval_by_id = dict(intervals)
    assert interval_by_id[3] == 3  # 最后一天完全正确 → 间隔确定


def test_compute_historical_dates_last_day_partial_incomplete():
    """最后一个背诵日选了部分正确（延续类）未选完全正确 → 循环未结束，间隔待定"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "perfect"),
            mklog(2, anchor + timedelta(days=1), "partial")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    assert final["consecutive_correct"] == 1  # 部分正确不推进（保持 day1 后）
    assert final["incomplete_loop"] is True
    interval_by_id = dict(intervals)
    assert interval_by_id[1] == 1
    assert interval_by_id[2] is None  # 循环未结束 → 间隔待定


def test_compute_historical_dates_groups_same_day():
    """同一天多条记录合并为当日循环：取排除基本正确后的最低档，日期相同"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "mostly_correct"),
            mklog(2, anchor, "perfect"),
            mklog(3, anchor + timedelta(days=1), "perfect")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    # 日1(锚): [基本正确, 完全正确] → 最低有效=完全正确 → c1 → 间隔1
    # 日2 = 锚+1: 完全正确 → c2 → 间隔2
    assert corrected == [(1, anchor), (2, anchor), (3, anchor + timedelta(days=1))]
    # 间隔档位只挂在决定档位的记录上；基本正确不占档位
    interval_by_id = dict(intervals)
    assert interval_by_id[1] is None   # 基本正确 → 不占间隔档位
    assert interval_by_id[2] == 1      # 完全正确 → 当日间隔 1
    assert interval_by_id[3] == 2
    assert final["consecutive_correct"] == 2
    assert final["interval"] == 2


def test_compute_historical_dates_lowest_wins_in_day():
    """当日多条记录取最低档：部分正确 + 完全正确 → 当日按部分正确（不推进）"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "partial"),
            mklog(2, anchor, "perfect"),
            mklog(3, anchor + timedelta(days=1), "perfect")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    # 日1: [部分正确, 完全正确] → 最低=部分正确 → c 不变(0) → 间隔1
    # 日2 = 锚+1: 完全正确 → c1 → 间隔1
    assert corrected == [(1, anchor), (2, anchor), (3, anchor + timedelta(days=1))]
    assert final["consecutive_correct"] == 1
    assert final["interval"] == 1


def test_compute_historical_dates_item14_example():
    """用户示例「简述处断的一罪」：按背诵日分组重算，6.26 后间隔两天 → 第三次 6.28"""
    s = Scheduler()
    logs = [
        mklog(21, date(2026, 6, 25), "mostly_correct"),
        mklog(26, date(2026, 6, 26), "mostly_correct"),
        mklog(32, date(2026, 6, 26), "perfect"),
        mklog(77, date(2026, 6, 29), "mostly_correct"),
        mklog(85, date(2026, 6, 29), "mostly_correct"),
        mklog(89, date(2026, 6, 29), "perfect"),
        mklog(251, date(2026, 7, 7), "perfect"),
        mklog(830, date(2026, 7, 20), "perfect"),
    ]
    corrected, intervals, final = s.compute_historical_dates(logs)
    by_id = dict(corrected)
    # 背诵日：6.25(仅基本正确→完全正确) → 6.26(+1) → 6.28(+2) → 7.01(+3) → 7.06(+5)
    assert by_id[21] == date(2026, 6, 25)   # 锚点
    assert by_id[26] == date(2026, 6, 26)   # 同天两条同日期
    assert by_id[32] == date(2026, 6, 26)
    assert by_id[77] == date(2026, 6, 28)   # 6.26 后间隔两天
    assert by_id[85] == date(2026, 6, 28)
    assert by_id[89] == date(2026, 6, 28)
    assert by_id[251] == date(2026, 7, 1)
    assert by_id[830] == date(2026, 7, 6)
    # 间隔档位：只有决定当日档位的记录持有；基本正确置 None
    interval_by_id = dict(intervals)
    assert interval_by_id[21] == 1   # 6.25 只有基本正确 → 决定档位（按完全正确）
    assert interval_by_id[26] is None
    assert interval_by_id[32] == 2   # 6.26 完全正确 → 2 天
    assert interval_by_id[77] is None
    assert interval_by_id[85] is None
    assert interval_by_id[89] == 3   # 6.29 完全正确 → 3 天
    assert interval_by_id[251] == 5
    assert interval_by_id[830] == 8
    assert final["consecutive_correct"] == 5
    assert final["interval"] == 8


def test_compute_historical_dates_mixed_results():
    """混合选项：完全正确推进、记错了归零、较多遗忘回退（归一化只影响基本正确）"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "perfect"),
            mklog(2, anchor + timedelta(days=1), "wrong"),
            mklog(3, anchor + timedelta(days=2), "mostly_forgotten"),
            mklog(4, anchor + timedelta(days=3), "perfect")]
    corrected, intervals, final = s.compute_historical_dates(logs)
    # log2 = 锚+1（perfect 后间隔1）；log3 = 锚+2（wrong 归零后间隔1）
    # log4 = 锚+3（forgotten 后 c=0 间隔1）；final: perfect → c=1 间隔1
    assert corrected[-1] == (4, anchor + timedelta(days=3))
    assert final["consecutive_correct"] == 1
    assert final["interval"] == 1


def test_compute_historical_dates_round2_intervals():
    """二轮条目用 ROUND2_INTERVALS（3,7,14）"""
    s = Scheduler()
    anchor = date(2026, 6, 26)
    logs = [mklog(1, anchor, "perfect", round_num=2),
            mklog(2, anchor + timedelta(days=3), "perfect", round_num=2)]
    corrected, intervals, final = s.compute_historical_dates(logs)
    assert corrected == [(1, anchor), (2, anchor + timedelta(days=3))]
    assert final["interval"] == 7


def test_stage_progress():
    """档位进度：(已通过, 总档位)。一轮 8 档、二轮 3 档；correct 超上限按满档"""
    assert Scheduler.stage_progress(0, 1) == (0, 8)
    assert Scheduler.stage_progress(3, 1) == (3, 8)
    assert Scheduler.stage_progress(8, 1) == (8, 8)   # 达标已掌握
    assert Scheduler.stage_progress(10, 1) == (8, 8)  # 超上限按满档
    assert Scheduler.stage_progress(2, 2) == (2, 3)
    assert Scheduler.stage_progress(3, 2) == (3, 3)   # 二轮达标


def test_compute_historical_dates_missing_first_date():
    """首次背诵日期缺失：返回 (None, None) 供人工介入标记"""
    s = Scheduler()
    logs = [mklog(1, "", "perfect"), mklog(2, date(2026, 6, 27), "perfect")]
    assert s.compute_historical_dates(logs) == (None, None, None)


def test_compute_historical_dates_empty():
    s = Scheduler()
    corrected, intervals, final = s.compute_historical_dates([])
    assert corrected == []
    assert intervals == []
    assert final["consecutive_correct"] == 0
    assert final["interval"] == 0
