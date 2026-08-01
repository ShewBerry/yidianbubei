# 电脑端权威重构与性能优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除手机端、修复背诵时间逻辑（应背日不被改写、过期顺延、延迟从实际背诵日重算）、校准本地与云端数据、云端改为单向备份，并优化列表渲染性能、清理无用代码。

**Architecture:** 调度器把重背结果改为“不更新下次背诵日期”（`None`），数据库不再被 `bring_overdue_to_today` 改写；同步收敛为“电脑端 → 云端”单向上传（不再拉取、不再上传 settings）；“全部条目/已掌握”面板改为分批渲染 + 滚动加载的虚拟化列表；新增一次性校准脚本修复历史数据。

**Tech Stack:** Python 3.12、tkinter/customtkinter、SQLite、Supabase REST API、pytest。

**设计文档:** `docs/superpowers/specs/2026-08-01-desktop-authoritative-rebuild-design.md`

---

## Task 1: 调度器——重背结果不再更新下次背诵日期

**Files:**
- Modify: `scheduler.py`
- Test: `tests/test_scheduler.py`

背景：重背（部分正确 / 较多遗忘 / 记错了 / 基本正确的重背）当前把 `next_review_date` 写成“今天”，污染原始应背日。改为返回 `None`，由调用方保持原应背日。

- [ ] **Step 1: 更新测试（先让旧实现失败）**

修改 `tests/test_scheduler.py` 中以下断言的 `next_review_date` 从 `today` 改为 `None`：

- `test_process_review_mostly_correct_first_time`
- `test_process_review_partial_normal`
- `test_process_review_partial_at_zero`
- `test_process_review_wrong`
- `test_process_review_forgotten_cap_first`
- `test_process_review_forgotten_cap_second`
- `test_process_review_forgotten_cap_reached`
- `test_process_review_forgotten_cap_beyond`
- `test_process_review_forgotten_cap_at_zero`

例如：

```python
def test_process_review_partial_normal():
    """部分正确：进度不变，但需重背；不更新 next_review_date"""
    s = Scheduler()
    today = date(2026, 6, 26)
    item = {"round": 1, "interval": 13, "consecutive_correct": 6, "status": "learning"}
    result = s.process_review(item, today, "partial", is_retest=False)
    assert result["consecutive_correct"] == 6
    assert result["interval"] == 13
    assert result["next_review_date"] is None  # 重背不更新日期
    assert result["requeue_today"] is True
```

新增测试（追加到 `tests/test_scheduler.py` 末尾）：

```python
def test_requeue_results_never_set_next_review_date():
    """重背类结果（partial/mostly_forgotten/wrong/首次 mostly_correct）都不应更新日期"""
    s = Scheduler()
    today = date(2026, 6, 26)
    base = {"round": 1, "interval": 5, "consecutive_correct": 4, "status": "learning"}
    for result in ("partial", "mostly_forgotten", "wrong"):
        r = s.process_review(dict(base), today, result, is_retest=False)
        assert r["next_review_date"] is None, f"{result} 不应更新日期"
        assert r["requeue_today"] is True
    r = s.process_review(dict(base), today, "mostly_correct", is_retest=False)
    assert r["next_review_date"] is None
    assert r["requeue_today"] is True


def test_backfill_still_sets_date_from_review_date():
    """补签仍按补签日 + 间隔计算日期，不回归"""
    s = Scheduler()
    review_date = date(2026, 6, 20)
    item = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    r = s.process_review(item, review_date, "mostly_correct", is_retest=False, is_backfill=True)
    assert r["next_review_date"] == review_date + timedelta(days=1)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_scheduler.py -q`
Expected: 失败，因为 `next_review_date` 仍是 `today` 而非 `None`。

- [ ] **Step 3: 修改 `scheduler.py`**

在 `_build_result` 中把重背分支的日期从 `today` 改为 `None`：

```python
        else:
            new_status = "learning"
            new_interval = round_intervals[new_correct - 1] if new_correct > 0 else 1
            if is_backfill:
                next_date = today + timedelta(days=new_interval)
                requeue_today = False
            elif requeue_today:
                next_date = None  # 重背不更新数据库日期，保持原应背日
            else:
                next_date = today + timedelta(days=new_interval)
```

把 `wrong` 分支的非补签返回从 `next_review_date: today` 改为 `next_review_date: None`：

```python
        elif result == "wrong":
            if is_backfill:
                return {
                    "status": "learning", "round": item["round"],
                    "interval": 1, "consecutive_correct": 0,
                    "next_review_date": today + timedelta(days=1),
                    "requeue_today": False
                }
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "next_review_date": None,  # 重背不更新日期
                "requeue_today": True
            }
```

同步更新 `process_review` 的 docstring：把“next_review_date 为 today 表示当日需重背”改为“重背结果 next_review_date 为 None，表示不更新数据库中的应背日；条目由队列机制保持今日重背，未完成则次日继续顺延出现”。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_scheduler.py -q`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "fix: 重背结果不再改写 next_review_date，保留原始应背日"
```

---

## Task 2: 移除 bring_overdue_to_today（应背日永不被改写）

**Files:**
- Modify: `database.py`（删除方法）、`ui/review_panel.py`（删除调用）
- Test: `tests/test_database.py`

- [ ] **Step 1: 先更新测试**

删除 `tests/test_database.py` 中的 `test_bring_overdue_to_today`，替换为：

```python
def test_get_due_items_includes_overdue_without_mutation(db):
    """过期条目应出现在待背列表，但 next_review_date 不被改写"""
    today = date(2026, 6, 26)
    past = today - timedelta(days=3)
    item_id = db.create_item("过期条目", "内容", today, past)
    due = db.get_due_items(today)
    assert any(i["id"] == item_id for i in due)
    row = db.conn.execute(
        "SELECT next_review_date FROM items WHERE id=?", (item_id,)).fetchone()
    assert row[0] == past.isoformat()  # 原始应背日保持不变
    assert not hasattr(db, "bring_overdue_to_today")  # 方法已删除
```

确保文件顶部有 `from datetime import date, timedelta`（若 `timedelta` 未导入则补上）。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_database.py -q`
Expected: 失败（旧测试引用已删除的方法或断言过期条目 nrd 被改写）。

- [ ] **Step 3: 删除方法并移除调用**

在 `database.py` 中删除整个 `bring_overdue_to_today` 方法（方法体从 `def bring_overdue_to_today(self, today):` 到下一个 `def` 之前）。

在 `ui/review_panel.py` 的 `refresh()` 中删除这一行：

```python
        self.db.bring_overdue_to_today(today)
```

`refresh()` 开头应变为：

```python
    def refresh(self):
        """刷新今日队列。"""
        today = date.today()
        due_items = self.db.get_due_items(today)
        reviewed_ids = self.db.get_today_reviewed_item_ids(today)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_database.py tests/test_scheduler.py -q`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add database.py ui/review_panel.py tests/test_database.py
git commit -m "fix: 删除 bring_overdue_to_today，过期条目顺延出现且保留原始应背日"
```

---

## Task 3: 同步单向化——去掉拉取与 settings 上传

**Files:**
- Modify: `sync/synchronizer.py`、`ui/main_window.py`、`ui/sync_dialog.py`
- Delete: `tests/test_sync_pull.py`
- Create: `tests/test_sync_upload.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_sync_upload.py`：

```python
import pytest
from datetime import date
from database import Database
from sync.synchronizer import Synchronizer, TABLES


@pytest.fixture
def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.init()
    yield db
    db.close()


@pytest.fixture
def sync(db, monkeypatch):
    monkeypatch.setattr("sync.synchronizer.is_sync_enabled", lambda: True)
    monkeypatch.setattr("sync.synchronizer.get_user_id", lambda: "user-uuid-123")
    return Synchronizer(db)


def test_tables_do_not_include_settings():
    """settings 不再参与同步，避免 watermark 互相覆盖"""
    assert "settings" not in TABLES


def test_incremental_upload_all_uploads_items_but_not_settings(sync, db, monkeypatch):
    db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    uploaded = []

    def fake_upsert(table, rows):
        uploaded.append(table)

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting",
        lambda self, k, v: None)
    sync.incremental_upload_all()
    assert "items" in uploaded
    assert "settings" not in uploaded


def test_upload_new_review_logs_only_since_watermark(sync, db, monkeypatch):
    db.create_item("t", "c", date(2026, 7, 26), date(2026, 7, 26))
    db.set_setting("sync_last_uploaded_log_id", "0")
    db.log_review(1, date(2026, 7, 26), 1, "perfect", 1)
    seen = {}

    def fake_upsert(table, rows):
        seen["rows"] = rows

    monkeypatch.setattr("sync.synchronizer.client.upsert", fake_upsert)
    monkeypatch.setattr(
        "sync.synchronizer.Synchronizer._set_setting",
        lambda self, k, v: None)
    sync.upload_table_incremental("review_logs")
    assert seen.get("rows"), "应有新日志被上传"
    assert all(r["local_id"] > 0 for r in seen["rows"])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_sync_upload.py -q`
Expected: `test_tables_do_not_include_settings` 失败（`settings` 仍在 TABLES 中）。

- [ ] **Step 3: 修改 `sync/synchronizer.py`**

把 TABLES 常量改为：

```python
# 表名映射：本地表 → 云端表
# 注意：settings 不参与同步（watermark 只存本地，避免互相覆盖）
TABLES = ["categories", "items", "review_logs", "item_marks"]
```

删除拉取相关方法 `pull_changes`、`_upsert_local`、`get_last_pull_time`。

把文件顶部导入 `from datetime import datetime, timezone, date` 改为 `from datetime import datetime, timezone`。

同时删除 `pull_changes` 中用于“修正 nrd”的整段逻辑（随方法一起删除），并删除 docstring 中关于双向同步的描述，改为“电脑端 → 云端单向备份；云端数据不覆盖本地”。

- [ ] **Step 4: 修改 `ui/main_window.py`**

把 `_auto_pull_on_startup` 重命名为 `_auto_upload_on_startup`，内容改为只上传：

```python
    def _auto_upload_on_startup(self):
        """启动后自动上传一次本地数据到云端（单向备份，不再拉取）。
        手机端已移除，云端仅作为备份；云端数据任何情况下不覆盖本地。"""
        from sync.config import is_sync_enabled
        from sync.auth import get_user_id
        if not is_sync_enabled() or not get_user_id():
            return

        import threading
        from sync.synchronizer import Synchronizer
        from sync.client import SyncError, AuthExpiredError

        def worker():
            try:
                Synchronizer(self.db).incremental_upload_all()
            except (SyncError, AuthExpiredError):
                pass
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()
```

把 `__init__` 末尾的调用改名为：

```python
        self.after(2000, self._auto_upload_on_startup)
```

- [ ] **Step 5: 修改 `ui/sync_dialog.py`**

删除“从云端下载”按钮：

```python
        ctk.CTkButton(btn_frame, text="⬇ 从云端下载", width=180, height=34,
                      fg_color="transparent", border_width=1,
                      command=self._do_pull).pack(fill="x", pady=(0, 5))
```

删除 `_do_pull` 方法。

状态区只显示“上次上传”，删除 `get_last_pull_time` 相关代码：

```python
            sync = Synchronizer(self.db)
            last_upload = sync.get_last_sync_time()
            if last_upload:
                self.last_sync_label.configure(
                    text=f"上次上传：{last_upload[:19].replace('T', ' ')}")
            else:
                self.last_sync_label.configure(text="尚未同步")
```

把操作区说明文字改为：

```python
        ctk.CTkLabel(frame,
                     text="云端作为电脑端的备份：点“立即全量上传”把本地数据传到云端。\n"
                          "启用“实时同步”会在每次数据变动后自动上传。\n"
                          "云端数据不会覆盖电脑端。",
                     text_color="gray", font=ctk.CTkFont(size=11),
                     justify="left").pack(pady=(15, 0), anchor="w")
```

同步删除对话框顶部“登录后可在手机端访问今日待背诵条目并评分”的说明文字。

- [ ] **Step 6: 删除旧测试、运行测试**

删除 `tests/test_sync_pull.py`，然后运行：

Run: `python -m pytest tests/ -q`
Expected: 全部通过（旧的 pull 测试已删除，新测试通过）。

- [ ] **Step 7: 提交**

```bash
git add sync/synchronizer.py ui/main_window.py ui/sync_dialog.py
git add tests/test_sync_upload.py
git rm tests/test_sync_pull.py
git commit -m "feat: 同步改为电脑端单向备份，移除拉取与 settings 上传"
```

---

## Task 4: 虚拟化卡片列表（性能优化）

**Files:**
- Create: `ui/card_list.py`
- Modify: `ui/list_panels.py`
- Create: `tests/test_card_list.py`
- Rewrite: `tests/test_search.py`

背景：目前“全部条目 / 已掌握”面板每次刷新同步创建全部卡片（约 300 张），搜索时全部 pack_forget/pack，导致 UI 卡顿、未响应。

### Task 4.1: 创建虚拟化基类

- [ ] **Step 1: 创建 `ui/card_list.py`**

```python
# ui/card_list.py
"""虚拟化卡片列表基类：分批发渲染 + 滚动加载 + 搜索过滤。

解决“全部条目/已掌握”面板在条目多时一次性渲染全部卡片导致的卡顿：
- refresh(): 重置视图，分批发渲染（每批 RENDER_BATCH 张，用 after 分片）
- 内容未填满视口时自动继续渲染；滚动接近底部时按需渲染下一批
- 搜索: 在完整内存列表上过滤（标题 + 内容纯文本懒计算），只渲染匹配项
"""
import customtkinter as ctk

from ui.html_utils import html_to_plain_text
from ui.theme import COLOR_TEXT_SECONDARY, heading_font, small_font


class VirtualCardList(ctk.CTkFrame):
    RENDER_BATCH = 40

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.expanded_item_id = None
        self.search_keyword = ""
        self._items = []          # 分类过滤后的完整条目列表
        self._filtered = []       # 再应用搜索后的有序列表
        self._visible_end = 0     # 已渲染的卡片数
        self._card_cache = {}     # item_id -> card widget
        self._plain_cache = {}    # item_id -> 纯文本（仅搜索时计算）
        self._pending_render = None
        self._pending_scroll = None

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        canvas = self.scroll_frame._parent_canvas
        canvas.bind("<MouseWheel>", self._on_scroll, add="+")
        canvas.bind("<Button-4>", self._on_scroll, add="+")
        canvas.bind("<Button-5>", self._on_scroll, add="+")
        self.scroll_frame.bind_all("<MouseWheel>", self._on_scroll_all, add="+")
        self.bind("<Configure>", lambda e: self.after_idle(self._maybe_render_more))

    # ============ 数据与过滤 ============

    def _load_items(self):
        """子类实现：返回当前分类过滤下的完整条目列表"""
        raise NotImplementedError

    def refresh(self):
        self._pending_scroll = self.scroll_frame._parent_canvas.yview()[0]
        self._items = self._load_items()
        self._rebuild_filtered()
        self._reset_view()

    def _rebuild_filtered(self):
        kw = self.search_keyword
        if not kw:
            self._filtered = list(self._items)
            return
        result = []
        for item in self._items:
            if kw in item["title"].lower():
                result.append(item)
                continue
            plain = self._plain_cache.get(item["id"])
            if plain is None:
                plain = html_to_plain_text(
                    item.get("content", "")).replace("\xa0", " ").lower()
                self._plain_cache[item["id"]] = plain
            if kw in plain:
                result.append(item)
        self._filtered = result

    def set_search_keyword(self, keyword: str):
        self.search_keyword = keyword if keyword else ""
        self.expanded_item_id = None
        self._pending_scroll = None
        self._rebuild_filtered()
        self._reset_view()

    # ============ 渲染 ============

    def _reset_view(self):
        if self._pending_render is not None:
            try:
                self.after_cancel(self._pending_render)
            except Exception:
                pass
            self._pending_render = None
        for widget in self._card_cache.values():
            try:
                widget.destroy()
            except Exception:
                pass
        self._card_cache = {}
        self._visible_end = 0
        self._toggle_empty_state(len(self._filtered) == 0)
        if self._filtered:
            self._pending_render = self.after(0, self._render_batch)

    def _render_batch(self):
        self._pending_render = None
        end = min(self._visible_end + self.RENDER_BATCH, len(self._filtered))
        for item in self._filtered[self._visible_end:end]:
            self._card_cache[item["id"]] = self._render_card(item)
        self._visible_end = end
        if self._visible_end >= len(self._filtered) and self._pending_scroll is not None:
            try:
                self.scroll_frame._parent_canvas.yview_moveto(self._pending_scroll)
            except Exception:
                pass
            self._pending_scroll = None
        if self._visible_end < len(self._filtered):
            self.after_idle(self._maybe_render_more)

    def _maybe_render_more(self):
        if self._pending_render is not None:
            return
        if self._visible_end >= len(self._filtered):
            return
        try:
            _top, bottom = self.scroll_frame._parent_canvas.yview()
        except Exception:
            return
        if bottom >= 0.95:
            self._pending_render = self.after(0, self._render_batch)

    def _on_scroll(self, _event):
        self.after_idle(self._maybe_render_more)

    def _on_scroll_all(self, event):
        """bind_all 兜底：滚轮事件落在卡片子控件上时也能触发按需加载"""
        try:
            w = event.widget
            while w is not None:
                if w is self.scroll_frame or w is self.scroll_frame._parent_canvas:
                    self.after_idle(self._maybe_render_more)
                    return
                w = getattr(w, "master", None)
        except Exception:
            pass

    def _render_card(self, item):
        """子类实现：创建并 pack 一张卡片，返回 widget"""
        raise NotImplementedError

    # ============ 空状态 ============

    def _toggle_empty_state(self, show: bool):
        if show:
            if not hasattr(self, "_empty_frame") or not self._empty_frame.winfo_exists():
                self._empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
                ctk.CTkLabel(self._empty_frame, text="📭",
                             font=ctk.CTkFont(size=40)).pack(pady=(0, 10))
                self._empty_title = ctk.CTkLabel(
                    self._empty_frame, font=heading_font(),
                    text_color=COLOR_TEXT_SECONDARY)
                self._empty_title.pack(pady=(0, 5))
                self._empty_hint = ctk.CTkLabel(
                    self._empty_frame, font=small_font(),
                    text_color=COLOR_TEXT_SECONDARY)
                self._empty_hint.pack()
            if self.search_keyword:
                self._empty_title.configure(text="没有匹配的条目")
                self._empty_hint.configure(
                    text=f"没有标题或内容包含“{self.search_keyword}”的条目")
            else:
                self._empty_title.configure(text="还没有条目")
                self._empty_hint.configure(text="点击右上角“+ 新建背诵”开始添加")
            self._empty_frame.pack(pady=60)
        else:
            if hasattr(self, "_empty_frame") and self._empty_frame.winfo_exists():
                self._empty_frame.pack_forget()
```

- [ ] **Step 2: 运行静态检查（编译）**

Run: `python -m py_compile ui/card_list.py`
Expected: 无输出，退出码 0。

- [ ] **Step 3: 提交**

```bash
git add ui/card_list.py
git commit -m "feat: 新增虚拟化卡片列表基类"
```

### Task 4.2: 重构 AllItemsPanel / MasteredPanel

- [ ] **Step 1: 改写 `ui/list_panels.py` 的两个面板类**

把 `AllItemsPanel(ctk.CTkFrame)` 改为 `AllItemsPanel(VirtualCardList)`，`MasteredPanel` 同理。删除旧的 `refresh()`、`_apply_search_filter()`、`_get_items()`（改名为 `_load_items()`）、`_toggle_empty_state()`、`_render_empty_state()` 等由基类提供的方法；保留卡片渲染、展开/收起、编辑/删除/补签/历史等逻辑。

`AllItemsPanel` 的完整新实现：

```python
class AllItemsPanel(VirtualCardList):
    """全部条目面板：虚拟化卡片列表 + 搜索"""

    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent, db)
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.filter_category_id = None
        self._search_after_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="全部条目",
                     font=title_font()).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）",
                                          text_color=COLOR_TEXT_SECONDARY,
                                          font=body_font())
        self.filter_label.pack(side="left", padx=10)

        self.search_entry = ctk.CTkEntry(header_frame, width=220,
                                          placeholder_text="🔍 搜索标题或内容...",
                                          font=body_font())
        self.search_entry.pack(side="right", padx=(5, 0))
        self.search_entry.bind("<KeyRelease>", self._on_search_input)
        self.search_entry.bind(
            "<Return>",
            lambda e: (self._cancel_pending_search(), self._apply_search()))

        self.refresh()

    def _load_items(self):
        if self.filter_category_id is None:
            return self.db.get_active_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_active_items() if i["category_id"] is None]
        items = self.db.get_items_by_category(
            self.filter_category_id, include_descendants=True)
        return [i for i in items if i["status"] == "learning"]

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _on_search_input(self, event):
        self._cancel_pending_search()
        self._search_after_id = self.after(150, self._apply_search)

    def _cancel_pending_search(self):
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None

    def _apply_search(self):
        self._search_after_id = None
        kw = self.search_entry.get().strip().lower()
        self.set_search_keyword(kw)

    def _render_card(self, item):
        colors = _card_colors()
        card_bg = colors["card_bg"]
        text_color = colors["text"]

        card = tk.Frame(self.scroll_frame, bg=card_bg, bd=0,
                        highlightthickness=1, highlightbackground=card_bg)
        card.pack(fill="x", pady=5, padx=5)

        header = tk.Frame(card, bg=card_bg)
        header.pack(fill="x", padx=12, pady=(8, 3))
        tk.Label(header, text=item["title"],
                 font=card_title_font(), bg=card_bg,
                 fg=text_color).pack(side="left")

        next_review = item["next_review_date"]
        if next_review and next_review != "":
            if isinstance(next_review, str):
                from datetime import date as date_cls
                try:
                    next_review = date_cls.fromisoformat(next_review)
                except ValueError:
                    next_review = None
            today = date.today()
            if next_review and next_review <= today:
                status_text = "今日待背诵"
            else:
                status_text = f"下次：{item['next_review_date']}"
        else:
            status_text = "—"
        tk.Label(header, text=status_text, fg=COLOR_TEXT_SECONDARY,
                 font=body_font(), bg=card_bg).pack(side="right")

        expand_container = tk.Frame(card, bg=card_bg)
        expand_container.pack(fill="x", padx=12, pady=(0, 8))

        if self.expanded_item_id == item["id"]:
            self._fill_expand(expand_container, item)
            _make_link_button(
                expand_container, "收起 ▲",
                command=lambda c=card, ec=expand_container, it=item:
                    self._collapse_inplace(c, ec, it),
                bg=card_bg).pack(side="right", pady=(5, 0))
        else:
            _make_link_button(
                expand_container, "展开 ▼",
                command=lambda c=card, ec=expand_container, it=item:
                    self._expand_inplace(c, ec, it),
                bg=card_bg).pack(anchor="e")
        return card
```

`MasteredPanel` 的完整新实现：

```python
class MasteredPanel(VirtualCardList):
    """已掌握面板：虚拟化卡片列表"""

    def __init__(self, parent, db, on_data_changed=None):
        super().__init__(parent, db)
        self.on_data_changed = on_data_changed
        self.filter_category_id = None

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header_frame, text="已掌握",
                     font=title_font()).pack(side="left")
        self.filter_label = ctk.CTkLabel(header_frame, text="（全部）",
                                          text_color=COLOR_TEXT_SECONDARY,
                                          font=body_font())
        self.filter_label.pack(side="left", padx=10)

        self.refresh()

    def _load_items(self):
        if self.filter_category_id is None:
            return self.db.get_mastered_items()
        elif self.filter_category_id == "uncategorized":
            return [i for i in self.db.get_mastered_items() if i["category_id"] is None]
        items = self.db.get_items_by_category(
            self.filter_category_id, include_descendants=True)
        return [i for i in items if i["status"] in ("mastered", "archived")]

    def set_category_filter(self, category_id):
        self.filter_category_id = category_id
        if category_id is None:
            self.filter_label.configure(text="（全部）")
        elif category_id == "uncategorized":
            self.filter_label.configure(text="（未分类）")
        else:
            path = self.db.get_category_path(category_id)
            name = " / ".join(c["name"] for c in path) if path else "?"
            self.filter_label.configure(text=f"（{name}）")
        self.refresh()

    def _render_card(self, item):
        colors = _card_colors()
        card_bg = colors["card_bg"]
        text_color = colors["text"]

        card = tk.Frame(self.scroll_frame, bg=card_bg, bd=0,
                        highlightthickness=1, highlightbackground=card_bg)
        card.pack(fill="x", pady=5, padx=5)

        header = tk.Frame(card, bg=card_bg)
        header.pack(fill="x", padx=12, pady=(8, 3))
        tk.Label(header, text=item["title"],
                 font=card_title_font(), bg=card_bg,
                 fg=text_color).pack(side="left")
        status_text = "已掌握（一轮）" if item["status"] == "mastered" else "已归档（二轮）"
        tk.Label(header, text=status_text, fg=COLOR_TEXT_SECONDARY,
                 font=body_font(), bg=card_bg).pack(side="right")

        expand_container = tk.Frame(card, bg=card_bg)
        expand_container.pack(fill="x", padx=12, pady=(0, 8))

        if self.expanded_item_id == item["id"]:
            self._fill_expand(expand_container, item)
            _make_link_button(
                expand_container, "收起 ▲",
                command=lambda c=card, ec=expand_container, it=item:
                    self._collapse_inplace(c, ec, it),
                bg=card_bg).pack(side="right", pady=(5, 0))
        else:
            _make_link_button(
                expand_container, "展开 ▼",
                command=lambda c=card, ec=expand_container, it=item:
                    self._expand_inplace(c, ec, it),
                bg=card_bg).pack(anchor="e")
        return card
```

保留 `_fill_expand`、`_expand_inplace`、`_collapse_inplace`、`_edit_item`、`_delete_item`、`_notify_data_changed`、`_show_history`、`_backfill_review`、`_handle_backfill` 及模块级函数 `_make_link_button`、`_card_colors`，从当前文件原样保留。

模块顶部导入改为：

```python
from ui.card_list import VirtualCardList
```

（其余导入保持不变。）

- [ ] **Step 2: 编译检查**

Run: `python -m py_compile ui/list_panels.py ui/card_list.py`
Expected: 无输出，退出码 0。

- [ ] **Step 3: 创建 `tests/test_card_list.py`**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk

from scheduler import Scheduler
from ui.list_panels import AllItemsPanel


class FakeDB:
    def __init__(self, items):
        self._items = items

    def get_active_items(self):
        return self._items

    def get_items_by_category(self, cid, include_descendants=False):
        return self._items

    def get_category_path(self, cid):
        return []

    def get_setting(self, k, d=""):
        return d

    def set_setting(self, k, v):
        pass

    def get_marks(self, iid):
        return []

    def add_mark(self, *a, **kw):
        pass

    def delete_mark(self, *a, **kw):
        pass


def make_item(iid, title, content):
    return {"id": iid, "title": title, "content": content,
            "category_id": None, "notes": "", "status": "learning",
            "next_review_date": "", "round": 1, "interval": 1,
            "consecutive_correct": 0}


@pytest.fixture
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


def test_refresh_renders_only_first_batch(root):
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.refresh()
    assert len(panel._card_cache) <= panel.RENDER_BATCH
    assert len(panel._filtered) == 120


def test_render_batch_grows_progressively(root):
    items = [make_item(i, f"title-{i}", "content") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.refresh()
    first = len(panel._card_cache)
    panel._render_batch()
    assert len(panel._card_cache) == first + panel.RENDER_BATCH


def test_search_filters_and_renders_only_match(root):
    items = [make_item(i, f"title-{i}", f"content-{i}") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("title-5")
    assert len(panel._filtered) == 1
    panel._render_batch()
    assert len(panel._card_cache) == 1


def test_plain_text_computed_lazily_only_for_search(root):
    items = [make_item(i, f"title-{i}", f"<b>keyword-{i}</b>") for i in range(120)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.refresh()
    assert panel._plain_cache == {}  # 无关键词时不解析纯文本
    panel.set_search_keyword("keyword-7")
    assert panel._plain_cache  # 搜索时才解析
    assert panel._filtered and panel._filtered[0]["id"] == 7
```

- [ ] **Step 4: 运行新测试**

Run: `python -m pytest tests/test_card_list.py -q`
Expected: 全部通过。

- [ ] **Step 5: 重写 `tests/test_search.py` 为 pytest 函数**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import customtkinter as ctk

from scheduler import Scheduler
from ui.list_panels import AllItemsPanel


class FakeDB:
    def __init__(self, items):
        self._items = items

    def get_active_items(self):
        return self._items

    def get_items_by_category(self, cid, include_descendants=False):
        return self._items

    def get_category_path(self, cid):
        return []

    def get_setting(self, k, d=""):
        return d

    def set_setting(self, k, v):
        pass

    def get_marks(self, iid):
        return []

    def add_mark(self, *a, **kw):
        pass

    def delete_mark(self, *a, **kw):
        pass


def make_item(iid, title, content, category_id=None):
    return {"id": iid, "title": title, "content": content,
            "category_id": category_id, "notes": "", "status": "learning",
            "next_review_date": "", "round": 1, "interval": 1,
            "consecutive_correct": 0}


@pytest.fixture
def root():
    ctk.set_appearance_mode("System")
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()


def test_search_title(root):
    items = [
        make_item(1, "唐诗春晓", "春眠不觉晓"),
        make_item(2, "宋词", "大江东去"),
    ]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("唐诗")
    assert [i["id"] for i in panel._filtered] == [1]


def test_search_content_html(root):
    items = [
        make_item(1, "题目", "普通文本"),
        make_item(2, "宋词", "大江东去 <b>千古</b>风流人物"),
    ]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("千古")
    assert [i["id"] for i in panel._filtered] == [2]


def test_search_case_insensitive(root):
    items = [
        make_item(1, "英语单词", "abandon 放弃"),
        make_item(2, "Abandon 复习", "再次复习 abandon"),
        make_item(3, "历史笔记", "唐朝建立"),
    ]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("abandon")
    assert sorted(i["id"] for i in panel._filtered) == [1, 2]


def test_search_no_match(root):
    items = [make_item(1, "唐诗", "内容")]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("不存在的关键词xyz")
    assert panel._filtered == []


def test_search_html_tag_not_matched(root):
    items = [make_item(1, "宋词", "大江东去 <b>千古</b>风流人物")]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.set_search_keyword("<b>")
    assert panel._filtered == []


def test_search_combined_with_category_filter(root):
    items = [make_item(1, "唐诗春晓", "春眠不觉晓", category_id=1),
             make_item(2, "宋词", "大江东去", category_id=None)]
    panel = AllItemsPanel(root, FakeDB(items), Scheduler())
    panel.filter_category_id = "uncategorized"
    panel.refresh()
    panel.set_search_keyword("宋词")
    assert [i["id"] for i in panel._filtered] == [2]
```

- [ ] **Step 6: 运行全部相关测试**

Run: `python -m pytest tests/test_search.py tests/test_card_list.py -q`
Expected: 全部通过。

- [ ] **Step 7: 提交**

```bash
git add ui/list_panels.py tests/test_card_list.py tests/test_search.py
git commit -m "perf: 全部条目/已掌握面板改为虚拟化分批渲染与懒加载搜索"
```

---

## Task 5: 本地数据校准脚本

**Files:**
- Create: `scripts/calibrate.py`

注意：该任务会修改真实数据库，脚本第一步先备份。

- [ ] **Step 1: 创建 `scripts/calibrate.py`**

```python
"""一次性校准脚本（电脑端数据为唯一权威）。

用法：
    python scripts/calibrate.py local   # 校准本地 items 状态与应背日（先备份）
    python scripts/calibrate.py cloud   # 校准云端为本地镜像（全量上传 + 删除多余）
"""
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import Scheduler

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ebbinghaus.db"


def backup_db() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"ebbinghaus_backup_{ts}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"已备份数据库到: {backup}")
    return backup


def replay_item_state(conn, item_id):
    """按新调度语义重放日志：返回 (state, expected_nrd)。
    重背结果不更新日期，因此 expected_nrd 保持上一次的有效值。"""
    logs = conn.execute(
        "SELECT id, review_date, result FROM review_logs "
        "WHERE item_id=? ORDER BY id", (item_id,)).fetchall()
    scheduler = Scheduler()
    state = {"round": 1, "interval": 0, "consecutive_correct": 0, "status": "learning"}
    expected_nrd = None
    for log in logs:
        log_date = date.fromisoformat(log["review_date"])
        prior_today = conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE item_id=? AND review_date=? AND id < ?",
            (item_id, log["review_date"], log["id"])).fetchone()[0]
        forgotten_count = conn.execute(
            "SELECT COUNT(*) FROM review_logs WHERE item_id=? AND review_date=? "
            "AND result='mostly_forgotten' AND id < ?",
            (item_id, log["review_date"], log["id"])).fetchone()[0]
        res = scheduler.process_review(
            state, log_date, log["result"],
            is_retest=prior_today > 0,
            today_forgotten_count=forgotten_count)
        state = {"round": res["round"], "interval": res["interval"],
                 "consecutive_correct": res["consecutive_correct"],
                 "status": res["status"]}
        if res["next_review_date"] is not None:
            expected_nrd = res["next_review_date"]
    return state, expected_nrd


def calibrate_local():
    if not DB_PATH.exists():
        print(f"未找到数据库: {DB_PATH}")
        return 1
    backup_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, status, round, interval, consecutive_correct, "
        "next_review_date FROM items WHERE deleted_at IS NULL").fetchall()
    changed = []
    for row in rows:
        has_logs = conn.execute(
            "SELECT 1 FROM review_logs WHERE item_id=? LIMIT 1",
            (row["id"],)).fetchone()
        if not has_logs:
            continue
        state, expected_nrd = replay_item_state(conn, row["id"])
        nrd_str = (expected_nrd.isoformat()
                   if hasattr(expected_nrd, "isoformat")
                   else expected_nrd)
        diffs = []
        for field, value in (
                ("consecutive_correct", state["consecutive_correct"]),
                ("interval", state["interval"]),
                ("round", state["round"]),
                ("status", state["status"]),
                ("next_review_date", nrd_str)):
            if value != row[field]:
                diffs.append((field, value))
        if diffs:
            changed.append((row["id"], row["title"], diffs))
            for field, value in diffs:
                conn.execute(
                    f"UPDATE items SET {field}=? WHERE id=?", (value, row["id"]))
    conn.commit()
    print(f"共检查 {len(rows)} 条（有日志），校准 {len(changed)} 条:")
    for iid, title, diffs in changed[:30]:
        detail = ", ".join(f"{f}={v}" for f, v in diffs)
        print(f"  item {iid} [{title[:25]}] -> {detail}")
    if len(changed) > 30:
        print(f"  ... 还有 {len(changed) - 30} 条")
    conn.close()
    print("本地校准完成。")
    return 0


def calibrate_cloud():
    if not DB_PATH.exists():
        print(f"未找到数据库: {DB_PATH}")
        return 1
    from database import Database
    from sync.client import _do_request, delete_by_local_ids, fetch_all
    from sync.synchronizer import Synchronizer

    db = Database(str(DB_PATH))
    sync = Synchronizer(db)
    print("步骤1: 全量上传本地数据到云端 ...")
    stats = sync.full_upload()
    for table, count in stats.items():
        print(f"  {table}: 上传 {count} 条")

    conn = sqlite3.connect(str(DB_PATH))
    for table in ("categories", "items", "review_logs", "item_marks"):
        cloud_rows = fetch_all(table, order="local_id.asc")
        local_ids = {r[0] for r in conn.execute(f"SELECT id FROM {table}")}
        cloud_ids = {r["local_id"] for r in cloud_rows}
        extra = sorted(cloud_ids - local_ids)
        if extra:
            print(f"  删除云端 {table} 多余 {len(extra)} 条: {extra[:20]}")
            delete_by_local_ids(table, extra)
        else:
            print(f"  {table}: 云端与本地一致（{len(cloud_ids)} 条）")
    try:
        cloud_settings = fetch_all("settings", order="key.asc")
        keys = [r["key"] for r in cloud_settings]
        if keys:
            _do_request("DELETE", "settings",
                        query={"key": f"in.({','.join(keys)})"})
            print(f"  已清理云端 settings {len(keys)} 条（不再参与同步）")
    except Exception as e:
        print(f"  settings 清理跳过: {e}")
    conn.close()
    db.close()
    print("云端校准完成。")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "local":
        return calibrate_local()
    if cmd == "cloud":
        return calibrate_cloud()
    print(f"未知子命令: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 在真实数据库上执行本地校准**

Run: `python scripts/calibrate.py local`
Expected: 先输出备份路径，再输出“共检查 N 条，校准 M 条”及差异明细；退出码 0。

- [ ] **Step 3: 提交**

```bash
git add scripts/calibrate.py
git commit -m "feat: 新增本地/云端一次性校准脚本"
```

---

## Task 6: 云端校准（单向备份镜像）

**Files:**
- Modify: 无（复用 `scripts/calibrate.py`）

前置条件：Task 3 已完成（TABLES 不含 settings），Task 5 已完成（本地已校准）。

- [ ] **Step 1: 执行云端校准**

Run: `python scripts/calibrate.py cloud`
Expected: 全量上传后输出各表“云端与本地一致”或删除多余记录，并清理云端 settings；退出码 0。

- [ ] **Step 2: 验证云端一致性**

Run:
```bash
python -c "from sync.client import fetch_all; \
print('items', len(fetch_all('items'))); \
print('logs', len(fetch_all('review_logs')))"
```
Expected: items 数 = 本地 `SELECT COUNT(*) FROM items` 的结果；review_logs 数 = 本地同表行数。

- [ ] **Step 3: 提交（如有脚本改动）**

```bash
git add scripts/calibrate.py
git commit -m "chore: 云端校准后记录"
```

---

## Task 7: 清理无用代码与文件

**Files:**
- Move: 根目录一次性调试脚本 → `_archive_20260801/`
- Move: `mobile/` → `mobile_backup_20260801/`
- Delete: `__pycache__/`、`.pytest_cache/` 等缓存目录

- [ ] **Step 1: 归档一次性调试脚本**

Run:
```powershell
New-Item -ItemType Directory -Force -Path "_archive_20260801" | Out-Null
$scripts = @("check_conflict.py","check_items.py","check_watermark.py",
             "compare_due.py","find_diff.py","diag_progress.py","full_audit.py",
             "test_fetch.py","test_query.py","test_rpc.py")
foreach ($s in $scripts) {
  if (Test-Path $s) { Move-Item -LiteralPath $s -Destination "_archive_20260801/" }
}
```

Expected: 根目录不再有这些脚本。

- [ ] **Step 2: 归档手机端**

Run:
```powershell
if (Test-Path "mobile") { Move-Item -LiteralPath "mobile" -Destination "mobile_backup_20260801" }
```

Expected: `mobile/` 消失，`mobile_backup_20260801/` 存在。

- [ ] **Step 3: 删除缓存目录**

Run:
```powershell
Get-ChildItem -Recurse -Force -Directory -Filter "__pycache__" |
  Where-Object { $_.FullName -notmatch "\\mobile_backup_20260801\\" } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
if (Test-Path ".pytest_cache") { Remove-Item -LiteralPath ".pytest_cache" -Recurse -Force }
```

Expected: 无 `__pycache__` 残留（除归档目录内），`.pytest_cache` 被删除。

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest tests/ -q`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "chore: 清理一次性调试脚本、缓存目录，归档手机端"
```

---

## Task 8: 全量回归与冒烟检查

**Files:** 无新增

- [ ] **Step 1: 全量测试**

Run: `python -m pytest tests/ -q`
Expected: 全部通过，无网络请求（根目录 test_*.py 调试脚本已移走）。

- [ ] **Step 2: 导入冒烟检查**

Run:
```bash
python -c "import main, ui.list_panels, ui.review_panel, sync.synchronizer; print('imports ok')"
```
Expected: 输出 `imports ok`。

- [ ] **Step 3: 数据一致性复核**

Run:
```bash
python scripts/calibrate.py local
```
Expected: 输出“校准 0 条”（二次运行应无差异，证明数据已一致）。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "chore: 全量回归通过"
```

---

## Self-Review 记录

- **Spec 覆盖检查**
  - 3.1 移除手机端 → Task 7
  - 3.2 时间逻辑重设计（重背不更新日期）→ Task 1、2
  - 3.3 数据校准 → Task 5
  - 3.4 云端单向备份 → Task 3、6
  - 7 性能优化（虚拟化、懒加载、滚动渲染）→ Task 4
  - 8 代码/文件清理 → Task 7
  - 5 测试 → 各任务内 TDD 步骤 + Task 8
  - 无遗漏项。
- **占位符扫描**：无 TBD/TODO；每个代码步骤都含完整代码。
- **类型一致性**：基类方法名 `_load_items`、`_render_card`、`set_search_keyword`、`_rebuild_filtered`、`_reset_view`、`_render_batch`、`_maybe_render_more` 在各任务中一致；`Scheduler.process_review` 返回的 `next_review_date` 在重背时为 `None` 的语义在 Task 1、2、5 一致。
