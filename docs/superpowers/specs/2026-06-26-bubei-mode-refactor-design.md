# 不背单词模式重构设计

**日期**: 2026-06-26
**状态**: 已确认
**背景**: 用户要求将固定艾宾浩斯曲线改为「不背单词」式动态间隔算法，并新增二轮巩固功能

## 1. 目标

- 抛弃固定艾宾浩斯曲线（累计天数锚定录入日）
- 采用动态间隔算法：根据4级评分实时调整下次背诵日期
- 卡片式交互：只显示标题，用户先回忆再展示内容，最后4级自评
- 今日队列：非「完全正确」的条目移到队列末尾需再背，直到「完全正确」
- 当日未处理的条目自动顺延到下一天（类似不背单词）
- 二轮巩固：某文件夹全部掌握后，手动触发二轮（间隔更长、次数更少）
- 统计面板：今日背诵量、本周完成量、各文件夹进度
- 半年内记住大量内容：间隔序列适当压缩

## 2. 算法设计

### 2.1 核心数据字段（每条目）

| 字段 | 类型 | 说明 |
|------|------|------|
| `interval` | INTEGER | 当前间隔天数（下次背诵距今天的天数） |
| `consecutive_correct` | INTEGER | 当前轮次内连续「完全正确」次数 |
| `round` | INTEGER | 轮次：1=一轮，2=二轮巩固 |
| `status` | TEXT | learning / mastered / archived |

**已删除字段**：`memory_strength`（原设计未实际参与间隔计算，4级评分已足够动态）

### 2.2 间隔序列（斐波那契式）

**一轮**（`round=1`）：
```
ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
```
- 第1次背诵（录入当天）：`interval=0`（今天就要背），`consecutive_correct=0`
- 第1次点「完全正确」后：`consecutive_correct=1`，`interval=ROUND1_INTERVALS[0]=1`
- 第N次点「完全正确」后：`consecutive_correct=N`，`interval=ROUND1_INTERVALS[N-1]`
- 第8次点「完全正确」：`consecutive_correct=8` → 一轮完成，`status=mastered`

一轮总时长约 1+2+3+5+8+13+21+34 = 87天 ≈ 3个月

**二轮**（`round=2`，手动触发）：
```
ROUND2_INTERVALS = [3, 7, 14]
```
- 触发时：`round=2`, `interval=0`, `consecutive_correct=0`, `status=learning`
- 第3次点「完全正确」：`consecutive_correct=3` → 二轮完成，`status=archived`

二轮总时长约 3+7+14 = 24天 ≈ 3周

### 2.3 反馈处理规则（4级评分系统）

用户看到标题后回忆，点击「展示内容」查看正文，对照后进行4级自评。

**核心原则**：只有 `requeue_today=False` 时才更新数据库的 `next_review_date`；`requeue_today=True` 时仅在内存队列追加，数据库的 `next_review_date` 保持不变（仍为 today，确保明天若未完成还在队列）。

**完全正确 (perfect)**：
```
consecutive_correct += 1
if consecutive_correct >= len(当前轮次序列):
    # 本轮完成，不再调度
    status = mastered (一轮) 或 archived (二轮)
    interval = 序列最后一项（仅作记录）
    next_review_date = ""  # 空字符串表示不再调度
else:
    interval = 序列[consecutive_correct - 1]
    next_review_date = today + interval
requeue_today = False  # 移出今日队列
```

**基本正确 (mostly_correct)**：
```
# 间隔按完全正确逻辑递增，但需当日重背
if 首次评分 (今日首次出现):
    consecutive_correct += 1
    if consecutive_correct >= len(当前轮次序列):
        # 本轮完成（同完全正确），不再重背
        status = mastered 或 archived
        next_review_date = ""
        requeue_today = False
    else:
        interval = 序列[consecutive_correct - 1]
        # 数据库 next_review_date 更新为 today + interval
        next_review_date = today + interval
        requeue_today = True  # 但当日仍需重背
else (重背评分):
    # 不再递增 consecutive_correct，保持当前状态
    # next_review_date 已在首次评分时设置，不重复更新
    requeue_today = True
```

**部分正确 (partial)**：
```
# 间隔回退2步，consecutive_correct 也减2
new_correct = max(0, consecutive_correct - 2)
consecutive_correct = new_correct
if new_correct > 0:
    interval = 序列[new_correct - 1]
    next_review_date = today + interval
else:
    interval = 1
    next_review_date = today + 1
requeue_today = True  # 当日重背
```

**记错了 (wrong)**：
```
interval = 1
consecutive_correct = 0
next_review_date = today + 1
requeue_today = True  # 当日重背
```

### 2.4 今日队列逻辑

- 每日初始队列 = `next_review_date <= today AND next_review_date != '' AND status='learning'` 的条目
- 按到期日期升序排列
- 展示时**只显示标题**，用户点击「展示内容」后看正文
- 看完后进行4级自评：
  - **完全正确**：更新数据库 `next_review_date`，移出今日队列
  - **基本正确**（首次）：更新数据库 `next_review_date`，移到队列末尾重背
  - **基本正确**（重背）：不更新数据库，移到队列末尾再重背
  - **部分正确**：更新数据库 `next_review_date`，移到队列末尾重背
  - **记错了**：更新数据库 `next_review_date`，移到队列末尾重背
- 队列空了 → 今日背诵完成

**首次/重背判断**：UI 层维护一个 `reviewed_today_ids` 集合，记录今日已评过分的 item_id。若 item_id 在集合中则为重背。

### 2.5 当日未处理条目自动顺延

类似不背单词的逻辑：

- 每日首次打开应用时，检查是否有 `next_review_date < today` 的条目（即昨日或更早到期但未处理的）
- 这些条目的 `next_review_date` 自动更新为 `today`，加入今日队列
- 新到期的条目（`next_review_date == today`）也正常加入
- **不累积延迟**：只顺延到今天，不会把昨天的待背推到明天

**实现**：在 `get_due_items` 查询前，先执行批量更新：
```sql
UPDATE items SET next_review_date = ?
WHERE next_review_date < ? AND next_review_date != '' AND status = 'learning'
```

这样所有过期未背的条目都会汇入今日队列，用户统一处理。

### 2.6 二轮巩固触发

**触发条件**：
- 用户在「分类管理」面板选中某文件夹
- 点击「二轮巩固」按钮
- 系统检查：该文件夹（含子孙）下所有条目 `status='mastered'`（即一轮全部完成）

**触发动作**：
- 该文件夹下所有 `status='mastered'` 的条目：
  - `round = 2`
  - `status = 'learning'`
  - `interval = 0`
  - `consecutive_correct = 0`
  - `next_review_date = today`（立即加入今日队列）

**部分完成时的处理**：
- 若文件夹下仍有 `status='learning'` 的条目，提示用户「还有N条目未完成一轮，无法开始二轮」
- 不允许部分触发

## 3. 数据库设计

### 3.1 表结构（清空重建）

```sql
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_date TEXT NOT NULL,
    category_id INTEGER,

    -- 调度字段
    status TEXT NOT NULL DEFAULT 'learning',  -- learning / mastered / archived
    round INTEGER NOT NULL DEFAULT 1,          -- 1=一轮, 2=二轮
    interval INTEGER NOT NULL DEFAULT 0,       -- 当前间隔天数
    consecutive_correct INTEGER NOT NULL DEFAULT 0,  -- 连续完全正确次数
    next_review_date TEXT NOT NULL,            -- 下次背诵日期，空字符串表示不再调度

    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

CREATE TABLE review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    review_date TEXT NOT NULL,
    round INTEGER NOT NULL,                    -- 属于哪轮
    result TEXT NOT NULL,                      -- perfect / mostly_correct / partial / wrong
    interval_after INTEGER,                    -- 本次打卡后的新间隔
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

### 3.2 删除的字段（相比旧版）

- `current_stage` → 由 `consecutive_correct` 替代
- `cycle_type` → 由 `round` 替代
- `cycle_start_date` → 不再需要，间隔动态计算
- `stage_completed` (review_logs) → 由 `interval_after` 替代
- `memory_strength` → 删除（未实际参与计算）

### 3.3 兼容性

用户已确认「清空重建」，旧数据不保留。`database.py` 的 `init()` 方法直接创建新表结构。

## 4. UI 设计

### 4.1 今日待背诵面板（重构）

**卡片式布局**（借鉴不背单词）：

**阶段一：只显示标题**
```
┌─────────────────────────────────┐
│  《静夜思》          第3次背诵   │  ← 只显示标题+次数
│                                  │
│         [展示内容]               │  ← 回忆后点击查看正文
└─────────────────────────────────┘
```

**阶段二：展示内容 + 4级自评**
```
┌─────────────────────────────────┐
│  《静夜思》          第3次背诵   │
│ ┌─────────────────────────────┐ │
│ │ 床前明月光，疑是地上霜。     │ │  ← 正文展示
│ │ 举头望明月，低头思故乡。     │ │
│ └─────────────────────────────┘ │
│ [完全正确][基本正确][部分正确][记错了] │  ← 4级自评
└─────────────────────────────────┘
```

- 一次只显示一张卡片（队列首位）
- 队列进度显示：「3/12 已完成」
- 队列空了 → 显示「🎉 今日背诵完成」

**详细交互**：
1. 进入面板：显示队列第1张卡片（只标题）+「展示内容」按钮
2. 用户心里回忆
3. 点击「展示内容」→ 卡片展开显示正文 + 4级自评按钮
4. 用户对照后点击4级之一：
   - **完全正确**：1.5秒后自动切到下一张，或用户点「下一张」
   - **基本正确/部分正确/记错了**：用户看完内容后点「继续背诵」，该卡片移到队列末尾
5. 循环直到队列空

### 4.2 全部条目面板（适配新字段）

- 状态显示改为：`第N次背诵` 或 `已掌握(一轮)` 或 `已归档(二轮)`
- 下次背诵日期显示
- 保留：展开看内容、编辑、删除、历史、补签按钮
- 补签逻辑调整：补签时记录当时的 result，重算 interval

### 4.3 已掌握面板

- 显示 `status='mastered'` 的条目（一轮完成）
- 已归档（二轮完成）的单独标记或归到此处
- 保留编辑/历史按钮

### 4.4 分类管理面板（新增二轮巩固按钮）

- 选中某文件夹后，底部新增「二轮巩固」按钮
- 点击后：
  1. 检查该文件夹（含子孙）下所有条目是否都 `status='mastered'`
  2. 若有未完成 → 提示「还有N条目未完成一轮」
  3. 若全部完成 → 弹确认框「确认对该文件夹下N条目启动二轮巩固？」
  4. 确认后批量重置为二轮状态

### 4.5 历史记录对话框（适配新字段）

- 列：日期 / 轮次 / 结果 / 打卡后间隔
- 结果映射：
  - `perfect` → 完全正确
  - `mostly_correct` → 基本正确
  - `partial` → 部分正确
  - `wrong` → 记错了

### 4.6 统计面板（新增）

在主界面底部状态栏或单独标签页展示：
- **今日进度**：已完成 X / 共 Y 条
- **本周完成**：N 条完全正确
- **各文件夹进度**：每文件夹的一轮完成率、二轮完成率
- **总览**：学习中 N 条、已掌握 N 条、已归档 N 条

## 5. 模块改动清单

### 5.1 重写

- `scheduler.py`：完全重写，4级评分算法
- `database.py`：表结构重写，新增 round/interval 等字段，删除旧阶段字段
- `ui/review_panel.py`：改为卡片式单张展示，4级评分交互

### 5.2 适配修改

- `ui/list_panels.py`：状态文案、补签逻辑适配新字段
- `ui/history_dialog.py`：列名和结果映射适配4级评分
- `ui/main_window.py`：标签页文案微调，新增统计面板
- `ui/backfill_dialog.py`：补签时需选择 result（4级评分之一）

### 5.3 新增

- `ui/round2_dialog.py`：二轮巩固确认对话框（或集成到 category_panel）
- `ui/stats_panel.py`：统计面板

### 5.4 删除

- `ui/mastery_dialog.py`：不再需要单独的掌握确认对话框，一轮8次「完全正确」自动完成

### 5.5 测试

- `tests/test_scheduler.py`：完全重写，覆盖新算法
- `tests/test_database.py`：适配新表结构

## 6. 调度算法伪代码

```python
class Scheduler:
    ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
    ROUND2_INTERVALS = [3, 7, 14]

    def schedule_new_item(self, today):
        """新建条目初始状态：今天就要背第1次"""
        return {
            "status": "learning",
            "round": 1,
            "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        }

    def process_review(self, item, today, result, is_retest=False):
        """处理用户的4级评分反馈，返回新的调度状态。

        is_retest: True 表示该条目今日非首次出现（重背评分）。
                   重背时 mostly_correct 不再 +1，仅追加到队列末尾。
        返回值含 requeue_today 字段：True 表示需追加到今日队列末尾。
        只有 requeue_today=False 时才将 next_review_date 写入数据库。
        """
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS
        current_correct = item["consecutive_correct"]

        if result == "perfect":
            new_correct = current_correct + 1
            return self._build_result(item, round_intervals, new_correct, today)

        elif result == "mostly_correct":
            if is_retest:
                # 重背时不再递增，保持当前状态，仅追加到末尾
                # 不更新数据库 next_review_date（保持首次评分时的值）
                return {
                    "status": item["status"], "round": item["round"],
                    "interval": item["interval"],
                    "consecutive_correct": current_correct,
                    "next_review_date": None,  # None 表示不更新数据库
                    "requeue_today": True
                }
            else:
                new_correct = current_correct + 1
                return self._build_result(item, round_intervals, new_correct, today,
                                          requeue_today=True)

        elif result == "partial":
            new_correct = max(0, current_correct - 2)
            return self._build_result(item, round_intervals, new_correct, today,
                                      requeue_today=True)

        elif result == "wrong":
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "next_review_date": today + timedelta(days=1),
                "requeue_today": True
            }

    def _build_result(self, item, round_intervals, new_correct, today, requeue_today=False):
        """根据新的 consecutive_correct 构建结果。"""
        if new_correct >= len(round_intervals):
            # 本轮完成，不再调度
            if item["round"] == 1:
                new_status = "mastered"
            else:
                new_status = "archived"
            new_interval = round_intervals[-1]
            next_date = ""  # 空字符串表示不再调度
            requeue_today = False  # 完成后不重背
        else:
            new_status = "learning"
            new_interval = round_intervals[new_correct - 1] if new_correct > 0 else 1
            next_date = today + timedelta(days=new_interval)

        return {
            "status": new_status, "round": item["round"],
            "interval": new_interval, "consecutive_correct": new_correct,
            "next_review_date": next_date,
            "requeue_today": requeue_today
        }

    def start_round2(self, items, today):
        """二轮巩固：批量重置条目为二轮状态"""
        return [{
            "status": "learning", "round": 2, "interval": 0,
            "consecutive_correct": 0,
            "next_review_date": today
        } for item in items]

    def bring_overdue_to_today(self, today):
        """将过期未处理的条目顺延到今天。在 get_due_items 前调用。"""
        # 返回 SQL: UPDATE items SET next_review_date = today
        #          WHERE next_review_date < today AND next_review_date != '' AND status = 'learning'
```

## 7. 边界情况处理

1. **新建条目当天**：`interval=0`, `next_review_date=today`，立即进入今日队列
2. **延迟打卡**：过期条目自动顺延到今天（见2.5节），按今天处理
3. **二轮触发时队列中已有条目**：二轮只影响 `mastered` 状态的条目，`learning` 的不动
4. **「基本正确」重背状态丢失**：若用户关闭面板重开，`reviewed_today_ids` 集合重置。此时重背的条目会被当作首次评分。为避免此问题，`reviewed_today_ids` 在面板刷新时从数据库查询今日已有 review_logs 的 item_id 重建。
5. **补签历史日期**：以补签日为 today 计算 interval，`next_review_date = 补签日 + interval`（可能早于今天，则会被 bring_overdue_to_today 顺延）
6. **删除分类**：`ON DELETE SET NULL`，条目变未分类，不影响调度
7. **next_review_date 为空字符串**：`get_due_items` 查询条件 `WHERE next_review_date != '' AND next_review_date <= today` 自动排除已完成条目

## 8. 测试策略

### 8.1 scheduler 测试

- `schedule_new_item`：初始状态正确
- `process_review` 各分支：
  - perfect 未达上限：interval/consecutive_correct 正确递增，requeue_today=False
  - perfect 达到一轮上限：status=mastered, next_review_date=""
  - perfect 达到二轮上限：status=archived
  - mostly_correct 首次：consecutive_correct +1, requeue_today=True, next_review_date 已更新
  - mostly_correct 重背(is_retest=True)：consecutive_correct 不变, next_review_date=None(不更新), requeue_today=True
  - partial：consecutive_correct 减2（最低0），interval 回退2步，requeue_today=True
  - partial 当 consecutive_correct=0：new_correct=0, interval=1
  - wrong：interval=1、consecutive_correct=0、requeue_today=True
- `start_round2`：批量重置正确
- `bring_overdue_to_today`：过期条目顺延到今天

### 8.2 database 测试

- 新表结构创建（无 memory_strength 字段）
- CRUD 适配新字段
- `get_due_items`：正确返回 `next_review_date <= today AND next_review_date != '' AND status='learning'`
- `get_mastered_items`：返回 `status='mastered'`
- 批量更新（用于二轮触发和顺延）

### 8.3 UI 测试（手动）

- 今日队列卡片流转：完全正确→下一张，基本正确/部分正确/记错了→末尾重背
- 队列空了提示
- 二轮巩固触发：全完成可触发，部分完成提示
- 历史记录新列展示
- 统计面板数据正确
- 过期条目自动顺延
