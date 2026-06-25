from datetime import date, timedelta
from scheduler import Scheduler

def test_full_cycle_intervals():
    s = Scheduler()
    assert s.FULL_CYCLE == [1, 2, 4, 7, 15, 30]

def test_short_cycle_intervals():
    s = Scheduler()
    assert s.SHORT_CYCLE == [1, 3, 7]

def test_schedule_new_item_first_review_tomorrow():
    s = Scheduler()
    today = date(2026, 6, 25)
    schedule = s.schedule_new_item(today)
    assert schedule["status"] == "learning"
    assert schedule["current_stage"] == 1
    assert schedule["cycle_type"] == "full"
    assert schedule["cycle_start_date"] == today
    assert schedule["next_review_date"] == today + timedelta(days=1)

def test_mark_reviewed_advances_stage_in_full_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    # 当前在阶段1，打卡后应进入阶段2，下次复习=今天+2天
    item = {
        "status": "learning", "current_stage": 1, "cycle_type": "full",
        "cycle_start_date": today - timedelta(days=1),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 2
    assert result["cycle_type"] == "full"
    assert result["next_review_date"] == today + timedelta(days=2)

def test_mark_reviewed_last_stage_enters_pending_mastery():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {
        "status": "learning", "current_stage": 6, "cycle_type": "full",
        "cycle_start_date": today - timedelta(days=30),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["status"] == "pending_mastery"
    assert result["next_review_date"] == today  # 立即到期等待确认

def test_mark_reviewed_short_cycle_last_stage_enters_pending_mastery():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {
        "status": "learning", "current_stage": 3, "cycle_type": "short",
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
        "cycle_start_date": today - timedelta(days=1),
        "next_review_date": today
    }
    result = s.mark_reviewed(item, today)
    assert result["current_stage"] == 2
    assert result["next_review_date"] == today + timedelta(days=3)

def test_confirm_mastery_mastered():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 6, "cycle_type": "full",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "mastered")
    assert result["status"] == "mastered"

def test_confirm_mastery_fuzzy_enters_short_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 6, "cycle_type": "full",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "fuzzy")
    assert result["status"] == "learning"
    assert result["cycle_type"] == "short"
    assert result["current_stage"] == 1
    assert result["cycle_start_date"] == today
    assert result["next_review_date"] == today + timedelta(days=1)

def test_confirm_mastery_forgotten_restarts_full_cycle():
    s = Scheduler()
    today = date(2026, 6, 25)
    item = {"status": "pending_mastery", "current_stage": 3, "cycle_type": "short",
            "cycle_start_date": today, "next_review_date": today}
    result = s.confirm_mastery(item, today, "forgotten")
    assert result["status"] == "learning"
    assert result["cycle_type"] == "full"
    assert result["current_stage"] == 1
    assert result["cycle_start_date"] == today
    assert result["next_review_date"] == today + timedelta(days=1)

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
    assert s.stage_description(1, "full") == "第1次复习（1天后）"
    assert s.stage_description(6, "full") == "第6次复习（30天后）"

def test_stage_description_short_cycle():
    s = Scheduler()
    assert s.stage_description(1, "short") == "第1次复习（1天后）"
    assert s.stage_description(3, "short") == "第3次复习（7天后）"

def test_stage_description_pending_mastery():
    s = Scheduler()
    assert s.stage_description(6, "full") == "第6次复习（30天后）"

# ===== backfill_schedule 测试 =====
# FULL_CYCLE = [1, 2, 4, 7, 15, 30]，累计天数：1, 3, 7, 14, 29, 59

def test_backfill_start_date_is_today_stage1_tomorrow():
    s = Scheduler()
    today = date(2026, 6, 25)
    result = s.backfill_schedule(today, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 1
    assert result["cycle_type"] == "full"
    assert result["cycle_start_date"] == today
    # 阶段1累计1天，应复习日 = today+1
    assert result["next_review_date"] == today + timedelta(days=1)

def test_backfill_two_days_ago_stage2():
    # 2天前开始：阶段1累计1天(昨天到期)，阶段2累计3天(明天到期)
    # 今天是第2天，阶段1已过期，下一个>=today的是阶段2(today+1)
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=2)
    result = s.backfill_schedule(start, today)
    assert result["status"] == "learning"
    assert result["current_stage"] == 2
    assert result["cycle_start_date"] == start
    # 阶段2累计3天，应复习日 = start+3 = today+1
    assert result["next_review_date"] == today + timedelta(days=1)

def test_backfill_exactly_at_stage_boundary():
    # 3天前开始：阶段1累计1天(2天前到期)，阶段2累计3天(今天到期)
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=3)
    result = s.backfill_schedule(start, today)
    assert result["current_stage"] == 2
    # 阶段2应复习日 = start+3 = today
    assert result["next_review_date"] == today

def test_backfill_10_days_ago_stage4():
    # 10天前开始：累计天数 1,3,7,14 → 阶段4应复习日=start+14=today+4
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=10)
    result = s.backfill_schedule(start, today)
    assert result["current_stage"] == 4
    assert result["next_review_date"] == start + timedelta(days=14)

def test_backfill_60_days_ago_enters_pending_mastery():
    # 60天前开始：最后一个阶段累计59天，应复习日=start+59=today-1 < today
    # 所有阶段都过期，进入待确认掌握
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=60)
    result = s.backfill_schedule(start, today)
    assert result["status"] == "pending_mastery"
    assert result["current_stage"] == 6
    assert result["next_review_date"] == today

def test_schedule_new_item_with_explicit_start_date():
    s = Scheduler()
    today = date(2026, 6, 25)
    start = today - timedelta(days=5)
    result = s.schedule_new_item(today, start_date=start)
    assert result["cycle_start_date"] == start
    assert result["current_stage"] == 3  # 累计7天，start+7=today+2
