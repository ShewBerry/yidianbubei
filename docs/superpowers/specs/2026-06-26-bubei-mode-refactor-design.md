# 不背单词模式重构设计

**日期**: 2026-06-26
**状态**: 已确认
**背景**: 用户要求将固定艾宾浩斯曲线改为「不背单词」式动态间隔算法，并新增二轮巩固功能

## 1. 目标

- 抛弃固定艾宾浩斯曲线（累计天数锚定录入日）
- 采用动态间隔算法：根据「记得/模糊/忘记」实时调整下次背诵日期
- 卡片式交互：只显示标题，用户先回忆再点击三选项之一，之后才展示内容
- 今日队列：点「模糊/忘记」的条目移到队列末尾需再背，直到点「记得」
- 二轮巩固：某文件夹全部掌握后，手动触发二轮（间隔更长、次数更少、着重模糊）
- 半年内记住大量内容：间隔序列适当压缩

## 2. 算法设计

### 2.1 核心数据字段（每条目）

| 字段 | 类型 | 说明 |
|------|------|------|
| `interval` | INTEGER | 当前间隔天数（下次背诵距今天的天数） |
| `memory_strength` | REAL | 记忆强度 0.0-1.0，影响间隔计算 |
| `consecutive_correct` | INTEGER | 当前轮次内连续「记得」次数 |
| `round` | INTEGER | 轮次：1=一轮，2=二轮巩固 |
| `status` | TEXT | learning / mastered / archived |

### 2.2 间隔序列（斐波那契式）

**一轮**（`round=1`）：
```
ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
```
- 第1次背诵（录入当天）：`interval=0`（今天就要背），`consecutive_correct=0`
- 第1次点「记得」后：`consecutive_correct=1`，`interval=ROUND1_INTERVALS[0]=1`
- 第N次点「记得」后：`consecutive_correct=N`，`interval=ROUND1_INTERVALS[N-1]`
- 第8次点「记得」：`consecutive_correct=8` → 一轮完成，`status=mastered`

一轮总时长约 1+2+3+5+8+13+21+34 = 87天 ≈ 3个月

**二轮**（`round=2`，手动触发）：
```
ROUND2_INTERVALS = [3, 7, 14, 30]
```
- 触发时：`round=2`, `interval=0`, `consecutive_correct=0`, `status=learning`
- 第4次点「记得」：`consecutive_correct=4` → 二轮完成，`status=archived`

二轮总时长约 3+7+14+30 = 54天 ≈ 2个月

### 2.3 反馈处理规则

用户点击三选项之一后：

**记得 (remember)**：
```
consecutive_correct += 1
if consecutive_correct >= len(当前轮次序列):
    # 本轮完成，不再调度
    status = mastered (一轮) 或 archived (二轮)
    interval = 序列最后一项（仅作记录，不再用于调度）
    next_review_date = null（标记为不再调度）
else:
    interval = 序列[consecutive_correct - 1]
    next_review_date = today + interval
memory_strength = min(1.0, memory_strength + 0.05)
```

**注**：`next_review_date` 为 null 时，`get_due_items` 查询自动排除。数据库字段保持 NOT NULL，用空字符串 '' 表示 null，查询时 `WHERE next_review_date != '' AND next_review_date <= today`。

**模糊 (fuzzy)**：
```
interval = max(1, interval // 2)  # 当前间隔减半，至少1天
consecutive_correct 不变（不递增也不重置）
memory_strength = max(0.1, memory_strength * 0.9)
next_review_date = today + interval
# 条目加入今日队列末尾，需再背
```

**忘记 (forget)**：
```
interval = 1
consecutive_correct = 0  # 重置
memory_strength = max(0.1, memory_strength * 0.5)
next_review_date = today + 1
# 条目加入今日队列末尾，需再背
```

### 2.4 今日队列逻辑

- 每日初始队列 = `next_review_date <= today AND next_review_date != '' AND status='learning'` 的条目
- 按到期日期升序排列
- 展示时**只显示标题**，用户回忆后点三选项之一
- 点「记得」：移出今日队列，安排下次日期
- 点「模糊/忘记」：移到今日队列**末尾**，当日需再背一次
- 队列空了 → 今日背诵完成

**防无限循环**：同一条目在今日队列中可出现多次（每次模糊/忘记都追加一份到末尾），但这是预期行为——用户需确实记住才能完成。若用户中途关闭面板，下次打开时队列重新从数据库查询生成，已「记得」的不会重复出现，未完成的会重新进入队列。

### 2.5 二轮巩固触发

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
  - `memory_strength` 保留原值（不重置，因为二轮是基于一轮的记忆）
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
    consecutive_correct INTEGER NOT NULL DEFAULT 0,  -- 连续记得次数
    memory_strength REAL NOT NULL DEFAULT 1.0,        -- 记忆强度
    next_review_date TEXT NOT NULL,            -- 下次背诵日期

    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

CREATE TABLE review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    review_date TEXT NOT NULL,
    round INTEGER NOT NULL,                    -- 属于哪轮
    result TEXT NOT NULL,                      -- remember / fuzzy / forget
    interval_after INTEGER,                    -- 本次打卡后的新间隔
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

### 3.2 删除的字段（相比旧版）

- `current_stage` → 由 `consecutive_correct` 替代
- `cycle_type` → 由 `round` 替代
- `cycle_start_date` → 不再需要，间隔动态计算
- `stage_completed` (review_logs) → 由 `interval_after` 替代

### 3.3 兼容性

用户已确认「清空重建」，旧数据不保留。`database.py` 的 `init()` 方法直接创建新表结构。

## 4. UI 设计

### 4.1 今日待背诵面板（重构）

**卡片式布局**（借鉴不背单词）：

```
┌─────────────────────────────────┐
│  《静夜思》          第3次背诵   │  ← 只显示标题+次数
│                                  │
│        [记得]  [模糊]  [忘记]    │  ← 三选项按钮
└─────────────────────────────────┘
```

- 一次只显示一张卡片（队列首位）
- 用户点击选项后：
  - 若点「记得」→ 展示内容几秒确认，然后切换到下一张
  - 若点「模糊/忘记」→ 展示内容供重背，然后该卡片移到队列末尾
- 队列进度显示：「3/12 已完成」
- 队列空了 → 显示「🎉 今日背诵完成」

**详细交互**：
1. 进入面板：显示队列第1张卡片（只标题）
2. 用户心里回忆
3. 点击三选项之一
4. 卡片展开显示内容（让用户对照）
5. 若「记得」：1.5秒后自动切到下一张，或用户点「下一张」
6. 若「模糊/忘记」：用户看完内容后点「继续背诵」，该卡片移到队列末尾
7. 循环直到队列空

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
  - `remember` → 记得
  - `fuzzy` → 模糊
  - `forget` → 忘记

## 5. 模块改动清单

### 5.1 重写

- `scheduler.py`：完全重写，新算法
- `database.py`：表结构重写，新增 round/interval 等字段，删除旧阶段字段
- `ui/review_panel.py`：改为卡片式单张展示，三选项交互

### 5.2 适配修改

- `ui/list_panels.py`：状态文案、补签逻辑适配新字段
- `ui/history_dialog.py`：列名和结果映射适配
- `ui/main_window.py`：标签页文案微调
- `ui/backfill_dialog.py`：补签时需选择 result（记得/模糊/忘记）

### 5.3 新增

- `ui/round2_dialog.py`：二轮巩固确认对话框（或集成到 category_panel）

### 5.4 删除

- `ui/mastery_dialog.py`：不再需要单独的掌握确认对话框，一轮8次「记得」自动完成

### 5.5 测试

- `tests/test_scheduler.py`：完全重写，覆盖新算法
- `tests/test_database.py`：适配新表结构

## 6. 调度算法伪代码

```python
class Scheduler:
    ROUND1_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]
    ROUND2_INTERVALS = [3, 7, 14, 30]

    def schedule_new_item(self, today):
        """新建条目初始状态：今天就要背第1次"""
        return {
            "status": "learning",
            "round": 1,
            "interval": 0,
            "consecutive_correct": 0,
            "memory_strength": 1.0,
            "next_review_date": today
        }

    def process_review(self, item, today, result):
        """处理用户的三选项反馈，返回新的调度状态"""
        round_intervals = self.ROUND2_INTERVALS if item["round"] == 2 else self.ROUND1_INTERVALS

        if result == "remember":
            new_correct = item["consecutive_correct"] + 1
            new_strength = min(1.0, item["memory_strength"] + 0.05)

            if new_correct >= len(round_intervals):
                # 本轮完成，不再调度
                if item["round"] == 1:
                    new_status = "mastered"
                else:
                    new_status = "archived"
                new_interval = round_intervals[-1]
                next_date = ""  # 空字符串表示不再调度
            else:
                new_status = "learning"
                new_interval = round_intervals[new_correct - 1]
                next_date = today + timedelta(days=new_interval)

            return {
                "status": new_status, "round": item["round"],
                "interval": new_interval, "consecutive_correct": new_correct,
                "memory_strength": new_strength, "next_review_date": next_date
            }

        elif result == "fuzzy":
            new_interval = max(1, item["interval"] // 2)
            new_strength = max(0.1, item["memory_strength"] * 0.9)
            return {
                "status": "learning", "round": item["round"],
                "interval": new_interval, "consecutive_correct": item["consecutive_correct"],
                "memory_strength": new_strength, "next_review_date": today + timedelta(days=new_interval)
            }

        elif result == "forget":
            new_strength = max(0.1, item["memory_strength"] * 0.5)
            return {
                "status": "learning", "round": item["round"],
                "interval": 1, "consecutive_correct": 0,
                "memory_strength": new_strength, "next_review_date": today + timedelta(days=1)
            }

    def start_round2(self, items, today):
        """二轮巩固：批量重置条目为二轮状态"""
        return [{
            "status": "learning", "round": 2, "interval": 0,
            "consecutive_correct": 0,
            "memory_strength": item["memory_strength"],  # 保留记忆强度
            "next_review_date": today
        } for item in items]
```

## 7. 边界情况处理

1. **新建条目当天**：`interval=0`, `next_review_date=today`，立即进入今日队列
2. **延迟打卡**：若 `next_review_date < today`，仍按今天处理，`next_review_date = today + interval`
3. **二轮触发时队列中已有条目**：二轮只影响 `mastered` 状态的条目，`learning` 的不动
4. **记忆强度极低**：`memory_strength` 下限 0.1，不会归零
5. **补签历史日期**：以补签日为 today 计算 interval，`next_review_date = 补签日 + interval`（可能早于今天，则下次进队列时再算）
6. **删除分类**：`ON DELETE SET NULL`，条目变未分类，不影响调度

## 8. 测试策略

### 8.1 scheduler 测试

- `schedule_new_item`：初始状态正确
- `process_review` 各分支：
  - remember 未达上限：interval/consecutive_correct 正确递增
  - remember 达到一轮上限：status=mastered
  - remember 达到二轮上限：status=archived
  - fuzzy：interval 减半、consecutive_correct 不变、memory_strength 衰减
  - forget：interval=1、consecutive_correct=0、memory_strength 大幅衰减
  - memory_strength 上下限（0.1 / 1.0）
- `start_round2`：批量重置正确，memory_strength 保留

### 8.2 database 测试

- 新表结构创建
- CRUD 适配新字段
- `get_due_items`：正确返回 `next_review_date <= today AND status='learning'`
- `get_mastered_items`：返回 `status='mastered'`
- 批量更新（用于二轮触发）

### 8.3 UI 测试（手动）

- 今日队列卡片流转：记得→下一张，模糊/忘记→末尾重背
- 队列空了提示
- 二轮巩固触发：全完成可触发，部分完成提示
- 历史记录新列展示
