# 电脑端权威重构：移除手机端、修复时间逻辑、校准数据、云端单向备份

日期：2026-08-01
状态：已获用户确认的设计稿

## 1. 背景与问题

当前应用同时存在电脑端（Tkinter/customtkinter + SQLite）与手机端（PWA，直连 Supabase）。
两端的背诵数据通过 Supabase 双向同步，但存在以下问题：

- 电脑端每次同步把本地 items **整表 upsert** 到云端，没有“哪边更新”的判断；手机端刚评完分、
  把下次背诵日期推到未来的条目，会被电脑端较旧的本地状态覆盖回旧值，导致“背完又出现”。
- 拉取（pull）时用 `INSERT OR REPLACE` 整行覆盖本地；拉取瞬间刚评分的条目会被云端旧状态覆盖。
- 电脑端每次打开“今日待背诵”以及每次同步拉取后，都会调用 `bring_overdue_to_today()`，
  把过期待背条目的 `next_review_date` 永久改写成今天，原始应背日丢失，历史无法追溯。
- 重背机制（部分正确 / 较多遗忘 / 记错了 / 基本正确的重背）每次点击都把 `next_review_date`
  改写成当天，导致同一条目多天重复出现、历史日志膨胀、日期“被污染”。
- 同步上传把 settings 表（含各类 watermark）也带上云端，watermark 互相覆盖，
  加上云端 review_logs 的 `updated_at` 被整表上传刷新，增量同步断点失效。

用户决定：手机端暂不做了；电脑端必须绝对顺畅、正确；云端仅作为电脑端的备份，
以电脑端数据为唯一权威基准。

## 2. 目标

1. 移除手机端（代码归档保留，暂不物理删除）。
2. 重设计时间逻辑：应背日真实存库、过期顺延、延迟背诵从实际背诵日重算。
3. 对现有数据做一次校准（先备份），修复被污染的状态与日期。
4. 云端收敛为“电脑端 → 云端”单向备份，任何情况下云端数据不再覆盖电脑端。

## 3. 决策与设计

### 3.1 移除手机端

- `mobile/` 目录整体移动到 `mobile_backup_20260801/`（保留一份，确认电脑端稳定后再删除）。
- 同步设置对话框删除手机端相关说明文字与“从云端下载”按钮。
- 电脑端启动时不再自动拉取云端数据。
- 手机端相关对外文案（如 Vercel 地址）一并移除。

### 3.2 时间逻辑重设计

核心原则：**`next_review_date` 是真实的“应背日”，任何日常流程都不得改写它，除非一次评分完成。**

#### 3.2.1 今日待背诵判定

- 不再调用 `bring_overdue_to_today()`。
- “今日待背诵” = `status='learning'` 且 `next_review_date != ''` 且 `next_review_date <= 今天`。
- 过期未背的条目自动顺延出现在待背列表，直到被背完。

#### 3.2.2 评分后的日期计算

- 结束本轮（`perfect`）：连续正确 +1，`next_review_date = 评分当天 + 对应间隔`；
  达到轮次上限则 `mastered`/`archived`，`next_review_date = ''`。
- 延迟背诵：按“实际评分当天 + 间隔”重算（与现状一致，保持）。
- 重背（`partial` / `mostly_forgotten` / `wrong`，以及 `mostly_correct` 的首次与重背）：
  条目排回今天队列末尾继续重背，日志照常记录，进度照常影响
  （部分正确 0、较多遗忘 −1 且当日最多累计 −2、记错了清零、基本正确首次 +1），
  **但 `next_review_date` 不更新**（保持原应背日，避免污染）。
- 只有 `perfect` 会结束重背循环；“基本正确”按现状不会结束循环。
- 若当天始终未点出 `perfect`，条目第二天继续顺延出现，直到背出 `perfect`。

#### 3.2.3 对调度器接口的改动

- `scheduler.process_review` 对重背类结果返回 `next_review_date = None`（表示“不更新日期”），
  而不是返回“今天”。
- `_build_result` 中 `requeue_today=True` 时不再把日期设为今天。
- `wrong` 的重背分支同样返回 `None` 日期，`requeue_today=True`。
- 补签（backfill）逻辑保持不变：`next_review_date = 补签日 + 间隔`。
- 所有日志仍按原逻辑写入 `review_logs`，不做去重。

### 3.3 数据校准（一次性）

- 校准前复制 `data/ebbinghaus.db` 为带时间戳的备份文件。
- 对每条未删除条目，用其 `review_logs` 按新语义逐条重放调度器，
  将 `status / round / interval / consecutive_correct / next_review_date` 校准为日志应产生的值。
- 无日志的条目不动（新建当天即到期，逻辑正确）。
- 校准脚本只写被校准后有差异的字段，并输出差异报告。
- 校准结果应使“本地状态 ↔ 日志重放”完全一致。

### 3.4 云端单向备份

- 同步只保留“电脑端 → 云端”上传：
  - `items`、`categories`、`item_marks`：全量 upsert 兜底；
  - `review_logs`：按 `sync_last_uploaded_log_id` 增量上传新日志。
- 上传内容**不再包含 `settings` 表**，消除 watermark 互相覆盖。
- 移除所有云端 → 本地拉取路径：
  - `main_window._auto_pull_on_startup` 只上传不再拉取；
  - 同步对话框删除“从云端下载”按钮及其调用；
  - 删除 `synchronizer` 中的拉取相关实现（`pull_changes`、`_upsert_local` 等），
    相关测试同步删除或改写。
- 校准完成后执行一次全量上传，使云端与电脑端一致；
  随后以本地 `local_id` 集合为准，删除云端多余的行（每张表分别校准），保证两边一致。
- 云端出任何问题都不影响电脑端运行（上传失败静默，沿用现有 try/except）。

## 4. 测试

- 更新 `tests/test_scheduler.py`：重背结果不再更新 `next_review_date`；延迟背诵从实际评分日重算。
- 更新/改写 `tests/test_sync_pull.py`：同步不再包含拉取；上传不再包含 settings。
- 更新 `tests/test_database.py`：如有 `bring_overdue_to_today` 相关用例则调整。
- 运行全部测试，确认无回归。
- 对校准逻辑单独验证：构造已知日志序列，重放后与预期状态一致。

## 5. 实施范围

| 文件 | 改动 |
| --- | --- |
| `scheduler.py` | 重背结果返回 `next_review_date=None` |
| `database.py` | 移除 `bring_overdue_to_today` 的调用方依赖（方法可保留或删除） |
| `ui/review_panel.py` | `refresh()` 不再调用 `bring_overdue_to_today` |
| `ui/main_window.py` | 启动自动拉取改为只上传 |
| `ui/sync_dialog.py` | 删除下载按钮、手机端文案 |
| `sync/synchronizer.py` | TABLES 去掉 settings；拉取路径移除 |
| `sync/config.py` / 其他同步文件 | 按需清理 |
| `mobile/` | 移动到 `mobile_backup_20260801/` |
| 根目录校准脚本 | 一次性数据校准 + 云端校准 |

## 6. 非目标

- 不重新做手机端。
- 不改变五档评分的语义（perfect / mostly_correct / partial / mostly_forgotten / wrong）。
- 不删除历史日志；重背过程日志照记。
- 不实现系统级推送/通知（维持“打开软件查看今日待背诵”的设计）。

## 7. 性能优化

用户反馈：软件经常未响应，搜索等功能慢、卡顿。

已定位的主要瓶颈：

- “全部条目 / 已掌握”面板在每次 `refresh()` 时同步销毁并重建全部卡片
  （约 300 张卡片 × 每张 6+ 个 widget），并逐条调用 `html_to_plain_text()` 解析 HTML，
  全部发生在 UI 线程上。
- 搜索时 `_apply_search_filter()` 对全部卡片执行 `pack_forget()` + `pack()`，
  并强制 `update_idletasks()` 触发整表布局重算。
- 搜索用到的纯文本（plain_text）在每次刷新时无差别预计算，即使没有关键词。

优化方案：

1. **列表虚拟化渲染**：全部条目 / 已掌握面板只渲染可视窗口内的卡片
   （首屏约 30~40 张），滚动接近底部时按需追加渲染；不再一次创建全部卡片。
2. **搜索改为内存过滤 + 虚拟化渲染**：搜索在完整内存列表上过滤
   （标题 + 内容纯文本），只渲染匹配且位于可视窗口内的卡片；
   内容纯文本改为**按需懒计算**（仅在有关键词时解析），避免每次刷新全量解析。
3. **刷新时复用卡片**：数据变动刷新时尽量复用已渲染卡片、只更新有变化的条目，
   避免全量 destroy/recreate。
4. 移除搜索布局强制刷新中的 `update_idletasks()` 全表重算路径。
5. 移除每次刷新都会执行的 `bring_overdue_to_today()` 数据库写入（见 3.2）。

## 8. 代码与文件清理

1. 根目录一次性调试脚本归档到 `_archive_20260801/`：
   `check_conflict.py`、`check_items.py`、`check_watermark.py`、
   `compare_due.py`、`find_diff.py`、`diag_progress.py`、`full_audit.py`、
   `test_fetch.py`、`test_query.py`、`test_rpc.py`。
   其中 `test_fetch.py` / `test_query.py` / `test_rpc.py` 会在模块导入时发网络请求，
   会被 pytest 收集执行，导致测试套件变慢或失败，必须移出测试目录。
2. 删除 `__pycache__/`、`.pytest_cache/` 等构建缓存目录。
3. `mobile/` 按 3.1 归档到 `mobile_backup_20260801/`。
4. 未使用的 Python 代码（如仅被测试引用的调度器方法）视情况移除，并同步更新测试。
5. `dist/`、`*.exe`、数据库备份文件等大文件不删除，只做说明；
   是否删除由用户决定。
