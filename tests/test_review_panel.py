# tests/test_review_panel.py
"""ReviewPanel._handle_review 评分闭环测试：队列出队/重背/计数/写库通知。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date

import pytest
import customtkinter as ctk

from scheduler import Scheduler
from ui.review_panel import ReviewPanel


def make_item(iid=1):
    return {
        "id": iid, "title": "测试条目", "content": "<p>内容</p>",
        "category_id": None, "notes": "", "status": "learning",
        "round": 1, "interval": 0, "consecutive_correct": 0,
        "next_review_date": date.today().isoformat(), "created_date": "2026-08-07",
    }


class FakeDB:
    """记录 update_item/log_review 调用，并让条目状态按真实语义更新。"""

    def __init__(self):
        self.calls = []
        self._items = {}

    def get_due_items(self, today):
        return [dict(v) for v in self._items.values()]

    def get_today_reviewed_item_ids(self, today):
        return set()

    def get_today_forgotten_count(self, item_id, today):
        return 0

    def get_perfect_count_in_range(self, start, end):
        return 0

    def update_item(self, item_id, **fields):
        self.calls.append(("update_item", item_id, dict(fields)))
        if item_id in self._items:
            self._items[item_id].update(fields)

    def log_review(self, item_id, review_date, round_num, result, interval_after):
        self.calls.append(("log_review", item_id, review_date, round_num,
                           result, interval_after))

    def get_setting(self, k, d=""):
        return d


@pytest.fixture(scope="module")
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def panel_factory(root, monkeypatch):
    panels = []

    def _make():
        panel = ReviewPanel(root, FakeDB(), Scheduler())
        panels.append(panel)
        # 渲染路径依赖真实 widget 布局，本测试聚焦调度/队列逻辑，屏蔽渲染
        monkeypatch.setattr(panel, "_update_progress", lambda: None)
        monkeypatch.setattr(panel, "_render_current_card", lambda: None)
        return panel

    yield _make
    for p in panels:
        try:
            p.destroy()
        except Exception:
            pass


def test_review_perfect_completes_and_notifies(panel_factory):
    panel = panel_factory()
    item = make_item()
    panel.db._items[item["id"]] = item
    panel.queue = [{"item": item, "is_retest": False}]
    changed = []
    panel.on_data_changed = lambda: changed.append(True)

    panel._handle_review("perfect")

    assert panel.queue == []
    assert panel.completed_count == 1
    assert changed == [True]
    kinds = [c[0] for c in panel.db.calls]
    assert kinds == ["update_item", "log_review"]
    log = panel.db.calls[1]
    assert log[4] == "perfect"
    assert item["consecutive_correct"] == 1


def test_review_mostly_forgotten_requeues(panel_factory):
    panel = panel_factory()
    item = make_item()
    panel.db._items[item["id"]] = item
    panel.queue = [{"item": item, "is_retest": False}]
    changed = []
    panel.on_data_changed = lambda: changed.append(True)

    panel._handle_review("mostly_forgotten")

    # 重背：条目移到队尾，不计数、不触发数据变更通知；调度状态保持不变
    assert len(panel.queue) == 1
    assert panel.queue[0]["item"]["id"] == item["id"]
    assert panel.queue[0]["is_retest"] is True
    assert panel.completed_count == 0
    assert changed == []
    assert item["consecutive_correct"] == 0  # 效力在结束时才确定
    # 延续类：只记评分日志，不更新条目状态
    kinds = [c[0] for c in panel.db.calls]
    assert kinds == ["log_review"]
    assert panel.db.calls[0][4] == "mostly_forgotten"


def test_review_partial_requeues_without_progress(panel_factory):
    panel = panel_factory()
    item = make_item()
    panel.db._items[item["id"]] = item
    panel.queue = [{"item": item, "is_retest": False}]

    panel._handle_review("partial")

    assert len(panel.queue) == 1
    assert panel.queue[0]["is_retest"] is True
    assert panel.completed_count == 0
    # 部分正确：consecutive_correct 不变
    assert item["consecutive_correct"] == 0


def test_review_empty_queue_noop(panel_factory):
    panel = panel_factory()
    panel.queue = []
    panel._handle_review("perfect")  # 不应抛异常、不应写库
    assert panel.db.calls == []
    assert panel.completed_count == 0


def test_review_wrong_then_perfect_finalizes_lowest(panel_factory):
    """多轮循环：记错了 → 完全正确，最终时间效力按历史最低档（记错了）"""
    panel = panel_factory()
    item = make_item()
    item["consecutive_correct"] = 6
    item["interval"] = 13
    panel.db._items[item["id"]] = item
    panel.queue = [{"item": item, "is_retest": False}]
    changed = []
    panel.on_data_changed = lambda: changed.append(True)

    # 第一轮：记错了 → 重背，调度状态不变
    panel._handle_review("wrong")
    assert len(panel.queue) == 1
    assert panel.queue[0]["is_retest"] is True
    assert item["consecutive_correct"] == 6  # 状态不变
    assert changed == []

    # 第二轮：完全正确 → 结束循环，最终效力按最低档（记错了 → 重新计算）
    panel._handle_review("perfect")
    assert panel.queue == []
    assert panel.completed_count == 1
    assert item["consecutive_correct"] == 0
    assert item["interval"] == 1
    assert changed == [True]
    # 延续类只记日志；结束时 update_item + log_review(perfect)
    kinds = [c[0] for c in panel.db.calls]
    assert kinds == ["log_review", "update_item", "log_review"]
    assert panel.db.calls[-1][4] == "perfect"


def test_review_mostly_correct_then_perfect_uses_perfect(panel_factory):
    """只选过基本正确与完全正确：最终按完全正确计算（基本正确不参与效力）"""
    panel = panel_factory()
    item = make_item()
    item["consecutive_correct"] = 2
    item["interval"] = 3
    panel.db._items[item["id"]] = item
    panel.queue = [{"item": item, "is_retest": False}]

    panel._handle_review("mostly_correct")  # 重背
    panel._handle_review("perfect")         # 结束
    assert panel.queue == []
    assert item["consecutive_correct"] == 3  # +1
    assert item["interval"] == 3  # ROUND1_INTERVALS[2]
