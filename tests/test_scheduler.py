from datetime import date, timedelta
from scheduler import Scheduler

def test_full_cycle_intervals():
    s = Scheduler()
    # 累计天数：录入当天(0) + 6次后续背诵(1,2,4,7,15,30)
    assert s.FULL_CYCLE == [0, 1, 2, 4, 7, 15, 30]

def test_short_cycle_intervals():
    s = Scheduler()
    # 短周期：录入当天(0) + 3次后续背诵(1,3,7)
    assert s.SHORT_CYCLE == [0, 1, 3, 7]

def test_schedule_new_item_first_review_today():
    s = Scheduler()
    today = date(2026, 6, 25)
    schedule = s.schedule_new_item(today)
    assert schedule["status"] == "learning"
    assert schedule["current_stage"] == 1
    assert schedule["cycle_type"] == "full"
    assert schedule["cycle_start_date"] == today
    # 录入当天即第1次背诵日
    assert schedule["next_review_date"] == today

def test_mark_reviewed_advances_stage_in_full_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    # 当前在阶段1，打卡后应进入阶段2
    # 阶段2背诵日 = cycle_start + 1 = today + 1
    item = {
        "status": "learning", "current_stage": 1, "cycle_type": "full",
        "cycle_start_date": today,
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 2
    assert result["cycle_type"] == "full"
    assert result["next_review_date"] == today + timedelta(days=1)

def test_mark_reviewed_last_stage_enters_pending_mastery():
    s = Scheduler()
    today = date(2026, 6, 25)
    # 完整周期共7次，第7次为最后阶段
    item = {
        "status": "learning", "current_stage": 7, "cycle_type": "full",
        "cycle_start_date": today - timedelta(days=30),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "pending_mastery"
    assert result["next_review_date"] == today  # 立即到期等待确认

def test_mark_reviewed_short_cycle_last_stage_enters_pending_mastery():
    s = Scheduler()
    today = date(2026, 6, 25)
    # 短周期共4次，第4次为最后阶段
    item = {
        "status": "learning", "current_stage": 4, "cycle_type": "short",
        "cycle_start_date": today - timedelta(days=7),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "pending_mastery"

def test_mark_reviewed_uses_short_cycle_intervals():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {
        "status": "learning", "current_stage": 1, "cycle_type": "short",
        "cycle_start_date": today,
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["current_stage"] == 2
    # 短周期阶段2 = cycle_start + 1
    assert result["next_review_date"] == today + timedelta(days=1)

def test_confirm_mastery_mastered():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 7, "cycle_type": "full",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "mastered")
    assert result["status"] == "mastered"

def test_confirm_mastery_fuzzy_enters_short_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 7, "cycle_type": "full",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "fuzzy")
    assert result["status"] == "learning"
    assert result["cycle_type"] == "short"
    assert result["current_stage"] == 1
    assert result["cycle_start_date"] == today
    # 短周期第1次背诵就在今天
    assert result["next_review_date"] == today

def test_confirm_mastery_forgotten_restarts_full_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 4, "cycle_type": "short",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "forgotten")
    assert result["status"] == "learning"
    assert result["cycle_type"] == "full"
    assert result["current_stage"] == 1
    assert result["cycle_start_date"] == today
    # 完整周期第1次背诵就在今天
    assert result["next_review_date"] == today

def test_is_due_today_true_when_next_review_equals_today():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today, "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_is_due_today_true_when_next_review_before_today():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today - timedelta(days=2), "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_is_due_today_false_when_future():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today + timedelta(days=1), "status": "learning"}
    assert s.is_due_today(item, today) is False

def test_is_due_today_false_when_mastered():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"next_review_date": today, "status": "mastered"}
    assert s.is_due_today(item, today) is False

def test_stage_description_full_cycle():
    s = Scheduler()
    assert s.stage_description(1, "full") == "第1次背诵"
    assert s.stage_description(7, "full") == "第7次背诵"

def test_stage_description_short_cycle():
    s = Scheduler()
    assert s.stage_description(1, "short") == "第1次背诵（短周期）"
    assert s.stage_description(4, "short") == "第4次背诵（短周期）"

def test_stage_description_pending_mastery():
    s = Scheduler()
    assert s.stage_description(7, "full") == "第7次背诵"

# ===== backfill_schedule 测试 =====
# FULL_CYCLE = [0, 1, 2, 4, 7, 15, 30]（累计天数，距开始日）
# 第N次背诵日 = start + FULL_CYCLE[N-1]
# stage1=start+0, stage2=start+1, stage3=start+2, stage4=start+4,
# stage5=start+7, stage6=start+15, stage7=start+30

def test_backfill_start_date_is_today_stage1_today():
    s = Scheduler()
    today = date(2026, 6, 25)
    result = s.backfill_schedule(today, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 1
    assert result["cycle_type"] == "full"
    assert result["cycle_start_date"] == today
    # 录入当天即第1次背诵日
    assert result["next_review_date"] == today

def test_backfill_two_days_ago_stage3():
    # 2天前开始：stage1=start(2天前), stage2=start+1(1天前), stage3=start+2(今天)
    # 今天正好是stage3的背诵日
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=2)
    result = s.backfill_schedule(start, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 3
    assert result["cycle_start_date"] == start
    # stage3背诵日 = start+2 = today
    assert result["next_review_date"] == today

def test_backfill_exactly_at_stage_boundary():
    # 3天前开始：stage3=start+2=昨天(已过), stage4=start+4=明天
    # 第一个 >= today 的是 stage4
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=3)
    result = s.backfill_schedule(start, today)
    assert result["current_stage"] == 4
    assert result["next_review_date"] == today + timedelta(days=1)

def test_backfill_10_days_ago_stage6():
    # 10天前开始：stage5=start+7=3天前(已过), stage6=start+15=5天后
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=10)
    result = s.backfill_schedule(start, today)
    assert result["current_stage"] == 6
    assert result["next_review_date"] == start + timedelta(days=15)

def test_backfill_60_days_ago_enters_pending_mastery():
    # 60天前开始：最后一个阶段(stage7)背诵日=start+30=30天前 < today
    # 所有阶段都过期，进入待确认掌握
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=60)
    result = s.backfill_schedule(start, today)
    assert result["status"] == "pending_mastery"
    assert result["current_stage"] == 7
    assert result["next_review_date"] == today

def test_schedule_new_item_with_explicit_start_date():
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=5)
    result = s.schedule_new_item(today, start_date=start)
    assert result["cycle_start_date"] == start
    # 累计0,1,2,4 → stage4=start+4=昨天(已过), stage5=start+7=2天后
    assert result["current_stage"] == 5
    assert result["next_review_date"] == start + timedelta(days=7)
