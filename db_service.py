# db_service.py

import sqlite3
import os

DATABASE_PATH = 'users.db'


class DatabaseService:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self._ensure_database()

    def _ensure_database(self):
        if not os.path.exists(self.db_path):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    user_name TEXT,
                    folder TEXT
                )
            ''')
            conn.commit()
            conn.close()

    def add_user_to_db(self, user_id, user_name, folder):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, user_name, folder)
            VALUES (?, ?, ?)
        ''', (user_id, user_name, folder))
        conn.commit()
        conn.close()

    def get_last_folder(self, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT folder FROM users WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
