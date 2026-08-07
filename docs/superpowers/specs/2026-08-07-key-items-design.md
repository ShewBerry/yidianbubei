# 重点条目（多文件夹标记）功能设计

日期：2026-08-07
状态：已获用户确认的设计稿

## 1. 背景与目标

用户需要一个“标记条目”的功能，类似不背单词的生词本，但采用**多个自建文件夹**的形式，
功能命名为**重点条目**。被标记的条目只是被“收藏”，**不改变原有的背诵计划**
（状态、应背日、间隔均不受影响）。

## 2. 数据模型

新增两张表：

```sql
CREATE TABLE IF NOT EXISTS key_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_items (
    folder_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    created_date TEXT NOT NULL,
    PRIMARY KEY (folder_id, item_id),
    FOREIGN KEY (folder_id) REFERENCES key_folders(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

要点：

- 一个条目可以同时属于多个重点文件夹（联合主键）。
- 删除重点文件夹时，该文件夹下的关联记录级联删除；条目本身不受影响。
- 条目的软删除（`deleted_at`）不影响关联记录，但重点条目列表查询会过滤已删除条目。

## 3. 数据库接口（Database 类新增方法）

- `create_key_folder(name) -> int`
- `rename_key_folder(folder_id, new_name)`
- `delete_key_folder(folder_id)`（级联清理关联）
- `get_key_folders() -> list`（按 sort_order 排序）
- `add_item_to_key_folder(folder_id, item_id)`
- `remove_item_from_key_folder(folder_id, item_id)`
- `get_key_folder_items(folder_id) -> list`（返回条目 dict，过滤 `deleted_at IS NOT NULL`）
- `is_item_in_key_folder(folder_id, item_id) -> bool`（用于“已加入”判断，避免重复插入）
- `get_item_key_folder_ids(item_id) -> list`（可选，用于显示条目已在哪些文件夹）

排序规则：新文件夹的 `sort_order` 取当前最大值 + 1，与现有分类一致。

## 4. 云端单向备份

- `key_folders`、`key_items` 两张表加入同步：
  - `sync/synchronizer.py` 的 `TABLES`、`FIELD_MAP`、`LOCAL_COLS`；
  - `sync/schema.sql` 补建云端表结构；
  - `scripts/calibrate.py` 的云端校准循环表名单。
- 仍为“电脑端 → 云端”单向上传，不拉取。

## 5. 界面

### 5.1 新增“重点条目”页签

- 主窗口新增页签“重点条目”，懒加载（沿用现有 `_tab_panels` / `_panel_factories` 机制）。
- 左侧：重点文件夹列表（“新建”“重命名”“删除”按钮）。
- 右侧：选中文件夹中的条目列表，复用虚拟化卡片（`VirtualCardList`）：
  - 卡片可展开查看内容/笔记、编辑、删除；
  - 增加“移出该文件夹”操作；
  - 空文件夹显示空状态提示。

### 5.2 “加入重点”入口

- “全部条目 / 已掌握”卡片操作行新增“⭐ 加入重点”按钮：
  - 点击弹出文件夹选择对话框（列出所有重点文件夹 + “新建文件夹”输入框）；
  - 选择后调用 `add_item_to_key_folder`。
- “今日待背诵”评分卡片标题旁新增小的“⭐ 加入重点”按钮，交互同上。
- 已在该文件夹中的条目再次选择时提示“已加入”，不重复插入。

### 5.3 交互约定

- 加入/移出重点**不修改**条目的 `status / round / interval / consecutive_correct / next_review_date`。
- 重点条目列表与普通列表一样采用虚拟化分批渲染，避免卡顿。

## 6. 测试

### 6.1 数据库层（tests/test_database.py 或新文件）

- 创建/重命名/删除重点文件夹；
- 文件夹排序按创建顺序；
- 加入/移出条目；一个条目加入多个文件夹；
- 删除文件夹后关联记录被清理（条目仍在）；
- 软删除的条目不出现在重点列表。

### 6.2 界面层（新增 tests/test_key_items_panel.py）

- 重点条目页签渲染文件夹列表；
- 选中文件夹后渲染条目（虚拟化，仅渲染首批）；
- 空文件夹显示空状态。

## 7. 实施范围

| 文件 | 改动 |
| --- | --- |
| `database.py` | 新增两张表 + 上述方法 |
| `ui/key_items_panel.py` | 新增重点条目页签面板 |
| `ui/main_window.py` | 注册“重点条目”页签 |
| `ui/list_panels.py` | 卡片加“加入重点”按钮 |
| `ui/review_panel.py` | 评分卡加“加入重点”按钮 |
| `ui/key_folder_dialog.py` | 文件夹选择/新建对话框 |
| `sync/synchronizer.py` | 新表加入备份 |
| `sync/schema.sql` | 云端建表 |
| `scripts/calibrate.py` | 云端校准表名单 |
| 测试文件 | 数据库 + 界面测试 |

## 8. 非目标

- 不改变背诵计划与调度逻辑。
- 不做重点条目的专属复习流程（当前按普通列表查看即可）。
- 不恢复手机端。
