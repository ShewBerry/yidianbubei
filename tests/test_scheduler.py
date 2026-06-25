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
