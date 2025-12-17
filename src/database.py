import sqlite3
from pathlib import Path
import os
from datetime import datetime

class Database:
    def __init__(self):
        self.db_path = Path(os.getenv("DATA_PATH", "./data")) / "app.db"
        self.init_db()

    def get_connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()

        # Media Items table
        # Status: PENDING, SEARCHING, DOWNLOADING, COMPLETED, FAILED
        c.execute('''
            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id TEXT,
                title TEXT,
                media_type TEXT, -- 'movie' or 'tv'
                year INTEGER,
                status TEXT DEFAULT 'PENDING',
                magnet_link TEXT,
                torbox_hash TEXT,
                symlink_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                UNIQUE(tmdb_id, media_type)
            )
        ''')

        conn.commit()
        conn.close()

    def add_item(self, tmdb_id, title, media_type, year):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR IGNORE INTO media_items (tmdb_id, title, media_type, year, status)
                VALUES (?, ?, ?, ?, 'PENDING')
            ''', (str(tmdb_id), title, media_type, year))
            conn.commit()
            return c.lastrowid
        except Exception as e:
            print(f"Error adding item: {e}")
            return None
        finally:
            conn.close()

    def get_pending_items(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM media_items WHERE status = 'PENDING'")
        items = c.fetchall()
        conn.close()
        return items

    def get_downloading_items(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM media_items WHERE status IN ('DOWNLOADING', 'SEARCHING')")
        items = c.fetchall()
        conn.close()
        return items

    def get_all_items(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM media_items ORDER BY created_at DESC")
        items = c.fetchall()
        conn.close()
        return items

    def update_status(self, db_id, status, magnet=None, hash=None, error=None):
        conn = self.get_connection()
        c = conn.cursor()
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status]

        if magnet:
            updates.append("magnet_link = ?")
            params.append(magnet)
        if hash:
            updates.append("torbox_hash = ?")
            params.append(hash)
        if error:
            updates.append("error_message = ?")
            params.append(error)

        params.append(db_id)

        sql = f"UPDATE media_items SET {', '.join(updates)} WHERE id = ?"
        c.execute(sql, params)
        conn.commit()
        conn.close()

db = Database()
