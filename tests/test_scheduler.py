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
