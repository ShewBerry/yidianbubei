import sqlite3
import os
from datetime import date

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'learning',
                current_stage INTEGER NOT NULL DEFAULT 1,
                next_review_date TEXT NOT NULL,
                cycle_start_date TEXT NOT NULL,
                cycle_type TEXT NOT NULL DEFAULT 'full'
            );

            CREATE TABLE IF NOT EXISTS review_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                review_date TEXT NOT NULL,
                stage_completed INTEGER NOT NULL,
                result TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id)
            );
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()
