# 一点不背（yidianbubei）

一个基于艾宾浩斯遗忘曲线的本地离线背诵 / 记忆巩固桌面应用。用 `customtkinter` 构建，数据全部保存在本地 SQLite（`data/ebbinghaus.db`），无需联网即可使用。

## 功能特性

- **艾宾浩斯间隔复习**：按遗忘曲线自动安排每日待背诵条目，间隔档位逐级推进
  - 一轮：`1 / 2 / 3 / 5 / 8 / 13 / 21 / 34` 天（8 档）
  - 二轮：`3 / 7 / 14` 天
- **背诵循环状态机**：仅「完全正确」结束当前循环；「基本正确 / 部分正确 / 较多遗忘 / 记错了」会触发下一轮
- **富文本内容**：支持加粗 / 斜体 / 下划线，背诵时可对内容打标记、添加笔记
- **分类管理**：多级分类目录，支持移动、重命名
- **重点文件夹**：把重要条目单独归类，随时复习
- **搜索**：全条目实时搜索（标题 + 内容），覆盖学习中 / 已掌握 / 已归档所有状态
- **回收站**：删除的条目 30 天内可恢复
- **统计面板**：掌握进度、各状态数量等
- **云端同步（可选）**：基于 Supabase 的增量同步，默认关闭，需自行配置

## 安装运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py
```

依赖：`customtkinter>=5.2.0`、`pytest>=7.0.0`（仅测试用）。Python 3.10+。

## 打包为 exe

本项目使用 PyInstaller 打包。示例命令：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
  --add-data "<你的Python目录>\Lib\site-packages\customtkinter;customtkinter" \
  main.py
```

> 注意：`--add-data` 必须带上 customtkinter 的 `assets` 资源目录，否则打包后窗口图标会因资源缺失而报错。

## 数据说明

- 数据库与用户数据保存在 `data/` 目录，**不会**提交到代码仓库（见 `.gitignore`）
- 云端同步的登录凭证（access token）只保存在本地 `data/sync_auth.json`，同样不入库
- `sync/config.py` 中的 Supabase 地址与 anon key 为**空模板**，需要同步功能的使用者请在“设置 → 云端同步”中填入自己的 Supabase 项目信息（anon key 为 publishable 公开性质）

## 项目结构

```
main.py             # 入口：外观设置、全局异常兜底、CTkButton 交互补丁
database.py         # SQLite 数据层（条目 / 分类 / 复习记录 / 设置）
scheduler.py        # 背诵调度模型（状态机 / 档位推进 / 效力计算）
sync/               # 可选云端同步（Supabase）
ui/                 # customtkinter 界面组件
scripts/            # 运维脚本（历史数据修复等）
tests/              # pytest 测试
```

## 测试

```bash
python -m pytest --ignore=_archive_20260801 --ignore=mobile_backup_20260801 --ignore=scripts
```

## License

[MIT](LICENSE)（未附带 LICENSE 文件，可自行添加）。
