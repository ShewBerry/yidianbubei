# tests/test_scheduler.py
from datetime import date, timedelta
from scheduler import Scheduler

def test_round1_intervals():
    s = Scheduler()
    assert s.ROUND1_INTERVALS == [1, 2, 3, 5, 8, 13, 21, 34]

def test_round2_intervals():
    s = Scheduler()
    assert s.ROUND2_INTERVALS == [3, 7, 14]

def test_schedule_new_item_initial_state():
    s = Scheduler()
    today = date(2026, 6, 26)
    result = s.schedule_new_item(today)
    assert result["status"] == "learning"
    assert result["round"] == 1
    assert result["interval"] == 0
    assert result["consecutive_correct"] == 0
    assert result["next_review_date"] == today

def test_process_review_perfect_first_time():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1  # ROUND1_INTERVALS[0]
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is False
    assert result["status"] == "learning"

def test_process_review_perfect_completes_round1():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 8
    assert result["status"] == "mastered"
    assert result["next_review_date"] == ""
    assert result["requeue_today"] is False

def test_process_review_perfect_completes_round2():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 2, "interval": 7, "consecutive_correct": 2, "status": "learning"}
    result = s.process_review(item, today, "perfect", is_retest=False)
    assert result["consecutive_correct"] == 3
    assert result["status"] == "archived"
    assert result["next_review_date"] == ""

def test_process_review_mostly_correct_first_time():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "mostly_correct", is_retest=False)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is True

def test_process_review_mostly_correct_retest():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 5, "consecutive_correct": 4, "status": "learning"}
    result = s.process_review(item, today, "mostly_correct", is_retest=True)
    assert result["consecutive_correct"] == 4  # 不变
    assert result["interval"] == 5  # 不变
    assert result["next_review_date"] is None  # 不更新数据库
    assert result["requeue_today"] is True

def test_process_review_partial_normal():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 13, "consecutive_correct": 6, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 4  # 6-2
    assert result["interval"] == 5  # ROUND1_INTERVALS[3]
    assert result["next_review_date"] == today + timedelta(days=5)
    assert result["requeue_today"] is True

def test_process_review_partial_at_zero():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 1, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is True

def test_process_review_wrong():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, today, "wrong", is_retest=False)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today + timedelta(days=1)
    assert result["requeue_today"] is True

def test_start_round2():
    s = Scheduler()
    today = date(2026, 6, 26)
    items = [
        {"id": 1, "round": 1, "interval": 34, "consecutive_correct": 8, "status": "mastered"},
        {"id": 2, "round": 1, "interval": 34, "consecutive_correct": 8, "status": "mastered"},
    ]
    results = s.start_round2(items, today)
    for r in results:
        assert r["round"] == 2
        assert r["status"] == "learning"
        assert r["interval"] == 0
        assert r["consecutive_correct"] == 0
        assert r["next_review_date"] == today
