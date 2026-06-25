# main.py
import os
import sys
from pathlib import Path
import customtkinter as ctk
from database import Database
from scheduler import Scheduler
from ui.main_window import MainWindow

def get_db_path() -> str:
    """数据库路径：项目根目录下 data/ebbinghaus.db"""
    if getattr(sys, 'frozen', False):
        # 打包后的 exe 模式：放在 exe 同级目录
        base = Path(sys.executable).parent
    else:
        # 开发模式：项目根目录
        base = Path(__file__).parent
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
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
