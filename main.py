# main.py
import os
import sys
from pathlib import Path
import customtkinter as ctk
from database import Database
from scheduler import Scheduler
from ui.main_window import MainWindow

APP_NAME = "一点不背"

def get_app_root() -> Path:
    """软件根目录：打包后为 exe 所在目录，开发模式为项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def get_db_path() -> str:
    """数据库路径：软件根目录下 data/ebbinghaus.db

    与 exe 同放在软件根目录下，便于统一备份和管理。
    重新打包/更新 exe 不会影响 data/ 文件夹里的数据。
    """
    data_dir = get_app_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "ebbinghaus.db")

def main():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    db = Database(get_db_path())
    db.init()
    scheduler = Scheduler()

    app = MainWindow(db, scheduler)
    app.protocol("WM_DELETE_WINDOW", lambda: (db.close(), app.destroy()))
    app.mainloop()

if __name__ == "__main__":
    main()
