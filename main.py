# main.py
import os
import sys
from pathlib import Path
import customtkinter as ctk
from database import Database
from scheduler import Scheduler
from ui.main_window import MainWindow

APP_NAME = "艾宾浩斯背诵"

def get_db_path() -> str:
    """数据库路径：%APPDATA%/艾宾浩斯背诵/ebbinghaus.db

    与 exe 分离：无论 exe 放在哪里、重新打包多少次，数据库始终在此固定位置，
    用户数据永不丢失。这也是 Windows 软件的标准做法（Chrome/VSCode/微信等同理）。
    """
    app_data = os.environ.get('APPDATA') or str(Path.home() / "AppData" / "Roaming")
    data_dir = Path(app_data) / APP_NAME
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
