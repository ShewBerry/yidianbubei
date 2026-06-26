# 内容标记、条目笔记与字号缩放 设计

> 日期：2026-06-26
> 状态：待评审
> 关联：在「一点不背」4级评分背诵系统基础上，增加背诵过程中的薄弱点标记、条目级笔记、内容字号/框高缩放三项辅助能力。

## 1. 背景与目标

当前背诵界面仅以只读文本框展示条目正文，用户在背诵时发现某段内容"忘了"或"模糊"，无法记录下来供下次回顾；且正文字号固定，内容多时阅读吃力。

本设计目标：
1. **片段标记**：背诵时可选中正文的一段文字，标记为"忘了"(红)或"模糊"(橙)，下次该条目出现时自动高亮薄弱处；掌握后可取消标记。
2. **条目笔记**：每个条目有一个独立的笔记区，在今日背诵展开内容和全部条目展开时均可见可编辑，用于记录背诵心得、易混点等。
3. **字号/框高缩放**：可手动放大正文字号和展示框高度，设置持久化，全局生效。

调度算法、评分逻辑、补签、队列管理**均不受影响**——标记/笔记/缩放是纯展示层辅助，不改变 consecutive_correct、interval 或 next_review_date。

## 2. 数据层改动

### 2.1 items 表新增 notes 字段

```sql
ALTER TABLE items ADD COLUMN notes TEXT NOT NULL DEFAULT '';
```

条目级笔记，空字符串表示无笔记。`update_item` 的允许字段列表增加 `notes`。

### 2.2 新增 item_marks 表

```sql
CREATE TABLE IF NOT EXISTS item_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    start_pos INTEGER NOT NULL,   -- 正文中的起始字符偏移（含换行，基于 content 文本）
    end_pos INTEGER NOT NULL,     -- 结束字符偏移（不含）
    mark_type TEXT NOT NULL,      -- 'forgot'(忘了) / 'fuzzy'(模糊)
    created_date TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_item_marks_item ON item_marks(item_id);
```

位置语义：以 `item["content"]` 字符串的字符偏移为准（Python `content[start:end]` 即为被标记文本）。换行符计入偏移。这样与 tkinter Text 的 index 转换简单且稳定。

### 2.3 新增 settings 表

```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

存储键值：
- `content_font_size`：正文字号，整数，默认 14
- `content_box_height`：展示框高度，整数，默认 200

### 2.4 database.py 新增方法

- `add_mark(item_id, start_pos, end_pos, mark_type) -> int`：新增标记，返回 id
- `get_marks(item_id) -> list[dict]`：返回该条目所有标记，按 start_pos 排序
- `delete_mark(mark_id)`：删除指定标记
- `get_setting(key, default)` / `set_setting(key, value)`：读写设置
- `update_item` 允许字段增加 `notes`；编辑 content 时调用 `_shift_marks(item_id, old_len, new_len)` 按比例平移已有标记位置（容错：若新长度为0则清空该条目标记）

## 3. UI 组件设计

### 3.1 新建 ui/markable_textbox.py

封装 `MarkableTextbox(ctk.CTkFrame)`，内部包含一个 `CTkTextbox` + 工具栏，复用于今日背诵和全部条目展开。

**职责**：
- 加载时插入 content，按 item_marks 应用高亮 tag
- 提供"标记选中为忘了/模糊"与"取消标记"操作
- 字号 A+/A- 与框高调整按钮
- 字号/框高变更即写入 settings，全局生效

**高亮 tag 配置**：
- `forgot`：`background=#c1554b`(红)，`foreground=#ffffff`(白字)
- `fuzzy`：`background=#e09f3e`(橙)，`foreground=#000000`(黑字)

**位置转换**：tkinter Text 用 `"line.char"` index。提供 `_pos_to_index(pos)`：用 `text.index(f"1.0 + {pos} chars")` 把字符偏移转成 Text index。新增标记时用 `text.index("sel.first")` / `text.index("sel.last")` 反向计算字符偏移（遍历行累加）。

**交互**：
- 用户在文本框选中一段文字 → 点工具栏「🔴 忘了」/「🟠 模糊」→ 调 `db.add_mark` → 应用高亮
- 选中已标记文字（或部分覆盖）→ 点「取消标记」→ 删除被选中范围覆盖的所有标记 → 重绘高亮
- 工具栏右上角：`A-` / `A+` 调字号（范围 10–24，步长1），`⤢ 高度` 按钮在 200/400/600 间循环

### 3.2 新建 ui/notes_box.py

`NotesBox(ctk.CTkFrame)`：一个带标签的可编辑文本框。
- 加载时显示 `item["notes"]`
- 失焦（`<FocusOut>`）时若内容变化则 `db.update_item(item_id, notes=...)`
- 顶部小标签"📝 笔记"

## 4. 各界面接入

### 4.1 今日背诵（ui/review_panel.py）

`_render_current_card` 中 `show_content=True` 分支改为：

```
┌─────────────────────────────────────┐
│ [标题]              [A- A+ ⤢高度]   │
│ [MarkableTextbox 内容框（可标记）]   │
│ [🔴 忘了] [🟠 模糊] [✕ 取消标记]     │  ← 标记工具栏
│ [📝 笔记]                           │
│ [NotesBox 笔记框]                   │
│ [✓完全正确] [👍基本正确] [🤔部分正确] [✗记错了] │
└─────────────────────────────────────┘
```

不选文字直接评分 = 原流程不变。`show_content=False`（先回忆）阶段保持原样，只有展示内容后才出现标记/笔记/字号工具。

### 4.2 全部条目展开（ui/list_panels.py）

`AllItemsPanel._render_card` 展开分支：用 `MarkableTextbox` 替换原只读 `CTkTextbox`，下方加 `NotesBox`。标记和笔记均可查看/编辑。"已掌握"面板同理，但标记工具栏可隐藏（只读查看高亮），笔记仍可编辑。

### 4.3 编辑对话框（ui/edit_dialog.py）

新增"笔记"编辑区（`CTkTextbox`），保存时一并写入 `notes` 字段。修改正文时由 database 层 `_shift_marks` 自动平移标记位置。

## 5. 不改动部分

- scheduler.py：完全不变
- 评分、补签、队列重建、completed_count 恢复逻辑：不变
- 标记/笔记不参与 is_due_today、不写入 review_logs

## 6. 边界与容错

- 编辑正文导致 content 长度变化：按 `new_pos = round(old_pos * new_len / old_len)` 平移所有标记；若 `new_len == 0` 则清空该条目标记
- 标记范围越界（start≥end 或 超出 content 长度）：`get_marks` 返回时过滤掉非法标记
- 同一段文字重复标记：后标记覆盖前者（先删除被范围覆盖的旧标记再新增）
- 字号范围限制 10–24，超出不再增减
- 删除条目时 item_marks 通过外键 CASCADE 自动清理

## 7. 测试要点

- database：add/get/delete mark、settings 读写、notes 字段、_shift_marks 平移与清空
- MarkableTextbox：选中→标记→高亮、取消标记、字号/框高持久化（需在集成测试或手动验证）
- 编辑正文后标记位置平移正确
- 现有 48 个测试保持通过（无回归）

## 8. 实现顺序建议

1. 数据层：表结构迁移 + database.py 方法 + _shift_marks
2. ui/notes_box.py
3. ui/markable_textbox.py
4. review_panel.py 接入
5. list_panels.py 接入
6. edit_dialog.py 接入笔记
7. 测试与打包
