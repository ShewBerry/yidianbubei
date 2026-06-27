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
    assert result["next_review_date"] == today  # 重背时保持今天，关闭应用后不丢失
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
    """部分正确：进度不变（0），但仍需重背"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 13, "consecutive_correct": 6, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 6  # 不变
    assert result["interval"] == 13  # ROUND1_INTERVALS[5]，保持不变
    assert result["next_review_date"] == today  # 重背时保持今天，关闭应用后不丢失
    assert result["requeue_today"] is True

def test_process_review_partial_at_zero():
    """部分正确且已在0：进度不变，仍为0"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 1, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today  # 重背时保持今天，关闭应用后不丢失
    assert result["requeue_today"] is True

def test_process_review_wrong():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, today, "wrong", is_retest=False)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today  # 重背时保持今天，关闭应用后不丢失
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

def test_is_due_today_true_when_next_review_equals_today():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"next_review_date": today, "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_is_due_today_true_when_next_review_before_today():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"next_review_date": today - timedelta(days=2), "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_is_due_today_false_when_future():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"next_review_date": today + timedelta(days=1), "status": "learning"}
    assert s.is_due_today(item, today) is False

def test_is_due_today_false_when_mastered():
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"next_review_date": today, "status": "mastered"}
    assert s.is_due_today(item, today) is False

def test_is_due_today_false_when_empty_string():
    """已完成轮次的条目 next_review_date 为空字符串，不应到期"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"next_review_date": "", "status": "learning"}
    assert s.is_due_today(item, today) is False

def test_is_due_today_handles_iso_string():
    """数据库存储为 TEXT，is_due_today 应能解析 ISO 字符串"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"next_review_date": "2026-06-26", "status": "learning"}
    assert s.is_due_today(item, today) is True

def test_stage_description_round1():
    s = Scheduler()
    assert s.stage_description(0, 1) == "第1次背诵"
    assert s.stage_description(7, 1) == "第8次背诵"

def test_stage_description_round2():
    s = Scheduler()
    assert s.stage_description(0, 2) == "第1次背诵（二轮）"
    assert s.stage_description(2, 2) == "第3次背诵（二轮）"

def test_process_review_mostly_correct_completes_round1():
    """基本正确首次评分达到一轮上限应进入 mastered，且不重背"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, today, "mostly_correct", is_retest=False)
    assert result["consecutive_correct"] == 8
    assert result["status"] == "mastered"
    assert result["next_review_date"] == ""
    assert result["requeue_today"] is False  # 完成后强制不重背

def test_process_review_partial_round2():
    """二轮的部分正确：进度不变，仍需重背"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 2, "interval": 7, "consecutive_correct": 2, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 2  # 不变
    assert result["interval"] == 7  # ROUND2_INTERVALS[1]，保持不变
    assert result["next_review_date"] == today  # 重背时保持今天，关闭应用后不丢失
    assert result["requeue_today"] is True


def test_process_review_backfill_mostly_correct():
    """补签基本正确：不重背，next_review_date = 补签日 + interval"""
    s = Scheduler()
    review_date = date(2026, 6, 20)  # 历史日期
    item = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, review_date, "mostly_correct", is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 1
    assert result["interval"] == 1
    assert result["next_review_date"] == review_date + timedelta(days=1)
    assert result["requeue_today"] is False


def test_process_review_backfill_partial():
    """补签部分正确：进度不变，不重背，next_review_date = 补签日 + interval"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = {"round": 1, "interval": 13, "consecutive_correct": 6, "status": "learning"}
    result = s.process_review(item, review_date, "partial", is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 6  # 不变
    assert result["interval"] == 13  # ROUND1_INTERVALS[5]，保持不变
    assert result["next_review_date"] == review_date + timedelta(days=13)
    assert result["requeue_today"] is False


def test_process_review_backfill_wrong():
    """补签记错了：不重背，next_review_date = 补签日 + 1"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = {"round": 1, "interval": 21, "consecutive_correct": 7, "status": "learning"}
    result = s.process_review(item, review_date, "wrong", is_retest=False, is_backfill=True)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == review_date + timedelta(days=1)
    assert result["requeue_today"] is False


def test_process_review_forgotten_cap_first():
    """同日第1次较多遗忘（today_forgotten_count=0）：正常回退 -1"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 13, "consecutive_correct": 6, "status": "learning"}
    result = s.process_review(item, today, "mostly_forgotten", is_retest=False, today_forgotten_count=0)
    assert result["consecutive_correct"] == 5  # 6-1
    assert result["interval"] == 8
    assert result["next_review_date"] == today
    assert result["requeue_today"] is True


def test_process_review_forgotten_cap_second():
    """同日第2次较多遗忘（today_forgotten_count=1）：仍回退 -1，累计 -2"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 8, "consecutive_correct": 5, "status": "learning"}
    result = s.process_review(item, today, "mostly_forgotten", is_retest=False, today_forgotten_count=1)
    assert result["consecutive_correct"] == 4  # 5-1
    assert result["interval"] == 5  # ROUND1_INTERVALS[3]
    assert result["next_review_date"] == today
    assert result["requeue_today"] is True


def test_process_review_forgotten_cap_reached():
    """同日第3次较多遗忘（today_forgotten_count=2）：达到上限，不再回退，但当日仍需重背"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 5, "consecutive_correct": 4, "status": "learning"}
    result = s.process_review(item, today, "mostly_forgotten", is_retest=False, today_forgotten_count=2)
    assert result["consecutive_correct"] == 4  # 保持不变，不再回退
    assert result["interval"] == 5  # 保持不变
    assert result["next_review_date"] == today  # 仍需重背
    assert result["requeue_today"] is True


def test_process_review_forgotten_cap_beyond():
    """同日第4次较多遗忘（today_forgotten_count=3）：超过上限，依然不回退"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 5, "consecutive_correct": 4, "status": "learning"}
    result = s.process_review(item, today, "mostly_forgotten", is_retest=False, today_forgotten_count=3)
    assert result["consecutive_correct"] == 4
    assert result["interval"] == 5
    assert result["next_review_date"] == today
    assert result["requeue_today"] is True


def test_process_review_forgotten_cap_at_zero():
    """同日多次较多遗忘且 consecutive_correct 已为 0：不会变为负数"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 1, "consecutive_correct": 0, "status": "learning"}
    result = s.process_review(item, today, "mostly_forgotten", is_retest=False, today_forgotten_count=1)
    assert result["consecutive_correct"] == 0
    assert result["interval"] == 1
    assert result["next_review_date"] == today
    assert result["requeue_today"] is True


def test_process_review_forgotten_cap_backfill():
    """补签较多遗忘也应遵循上限：达到上限后不回退，但按补签日+interval 计算"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = {"round": 1, "interval": 5, "consecutive_correct": 4, "status": "learning"}
    result = s.process_review(item, review_date, "mostly_forgotten",
                              is_retest=False, is_backfill=True, today_forgotten_count=2)
    assert result["consecutive_correct"] == 4  # 上限，不回退
    assert result["interval"] == 5
    assert result["next_review_date"] == review_date + timedelta(days=5)
    assert result["requeue_today"] is False
