# 一点不背（yidianbubei）

一个基于艾宾浩斯遗忘曲线的本地离线背诵 / 记忆巩固桌面应用。纯单端应用，数据全部保存在本地 SQLite（`data/ebbinghaus.db`），**不依赖任何云端服务，无需联网**。

## ⬇️ 快速下载（免安装）

**Windows 用户直接下载 exe 双击即可使用，无需安装 Python：**

👉 [**点此下载 一点不背 v1.0.0**](https://github.com/ShewBerry/yidianbubei/releases/latest) （约 30MB，Windows 10/11）

- 下载 `yidianbubei.exe` 后双击运行
- 首次运行会在 exe 同级自动创建 `data/` 文件夹存放背诵数据
- 如需源码运行、二次开发或查看详细功能，继续阅读下文

## 功能特性

- **艾宾浩斯间隔复习**：按遗忘曲线自动安排每日待背诵条目，间隔档位逐级推进
  - 一轮：`1 / 2 / 3 / 5 / 8 / 13 / 21 / 34` 天（8 档）
  - 二轮：`3 / 7 / 14` 天
- **背诵循环状态机**：仅「完全正确」结束当前循环；「基本正确 / 部分正确 / 较多遗忘 / 记错了」会触发下一轮；间隔仅在循环结束时写入
- **富文本内容**：支持加粗 / 斜体 / 下划线，背诵时可对内容打标记、添加笔记
- **分类管理**：多级分类目录，支持移动、重命名
- **重点文件夹**：把重要条目单独归类，随时复习
- **搜索**：全条目实时搜索（标题 + 内容），覆盖学习中 / 已掌握 / 已归档所有状态
- **回收站**：删除的条目 30 天内可恢复
- **统计面板**：掌握进度、各状态数量等

## 项目下载与使用

### 1. 下载项目

方式一（命令行，推荐）：

```bash
git clone https://github.com/ShewBerry/yidianbubei.git
cd yidianbubei
```

方式二：打开 <https://github.com/ShewBerry/yidianbubei>，点击绿色 **Code → Download ZIP**，解压后进入该文件夹。

### 2. 安装 Python

需要 **Python 3.10 或更高版本**。可在 <https://www.python.org/downloads/> 下载安装。

> Windows 安装时请勾选 **“Add Python to PATH”**，否则命令行无法直接使用 `python` 命令。

安装完成后，在命令行验证：

```bash
python --version
```

### 3. 安装依赖

在项目文件夹内执行：

```bash
pip install -r requirements.txt
```

依赖列表：`customtkinter>=5.2.0`（界面库）、`pytest>=7.0.0`（仅测试用）。

> 若提示 `pip` 不可用或权限问题，可尝试 `python -m pip install -r requirements.txt`。

### 4. 启动应用

```bash
python main.py
```

看到「今日待背诵」主界面即启动成功。应用会在项目目录下自动创建 `data/ebbinghaus.db` 数据库。

### 5.（可选）打包为独立 exe

如需生成免安装的单文件 exe（Windows），使用 PyInstaller：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
  --add-data "<你的Python安装目录>\Lib\site-packages\customtkinter;customtkinter" \
  main.py
```

生成的 exe 位于 `dist/` 目录，可拷贝到任意位置运行（数据库仍保存在 exe 同级的 `data/` 目录）。

> **重要**：`--add-data` 必须包含 customtkinter 的 `assets` 资源目录，否则打包后窗口图标会因资源缺失而报错。

## 数据说明

- 所有数据（条目、背诵记录、笔记、设置）保存在本地 `data/ebbinghaus.db`
- 该目录**不会**被提交到代码仓库（见 `.gitignore`），备份或迁移时拷贝整个 `data/` 目录即可
- 删除的条目进入回收站，30 天后自动物理清理

## 项目结构

```
main.py             # 入口：外观设置、全局异常兜底、CTkButton 交互补丁
database.py         # SQLite 数据层（条目 / 分类 / 复习记录 / 设置）
scheduler.py        # 背诵调度模型（状态机 / 档位推进 / 效力计算）
ui/                 # customtkinter 界面组件
scripts/            # 运维脚本（历史数据修复、本地校准等）
tests/              # pytest 测试
```

## 测试

```bash
python -m pytest --ignore=_archive_20260801 --ignore=mobile_backup_20260801 --ignore=scripts --ignore=github_version
```

## License

MIT（未附带 LICENSE 文件，可自行添加）。
