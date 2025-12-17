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

        # Tracked Series (The Shows themselves)
        c.execute('''
            CREATE TABLE IF NOT EXISTS tracked_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id TEXT UNIQUE,
                title TEXT,
                status TEXT, -- 'Returning Series', 'Ended', etc.
                last_scan TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Media Items (Movies OR Episodes)
        # parent_tmdb_id is populated for Episodes (pointing to the Show)
        # season_number/episode_number populated for Episodes
        c.execute('''
            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id TEXT, -- For movies, it's the movie ID. For episodes, it's the Episode ID (if avail) or null
                parent_tmdb_id TEXT, -- For episodes, the Show ID
                title TEXT,
                media_type TEXT, -- 'movie' or 'episode'
                year INTEGER,
                season_number INTEGER,
                episode_number INTEGER,
                air_date TEXT,
                status TEXT DEFAULT 'PENDING', -- PENDING, SEARCHING, DOWNLOADING, COMPLETED, NOT_FOUND
                magnet_link TEXT,
                torbox_hash TEXT,
                symlink_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                -- Unique constraint to prevent duplicate downloads
                -- For Movie: parent_tmdb_id is NULL, so uniqueness is on tmdb_id + media_type
                -- For Episode: Uniqueness on parent_tmdb_id + season + episode
                UNIQUE(parent_tmdb_id, season_number, episode_number),
                UNIQUE(tmdb_id, media_type)
            )
        ''')

        conn.commit()
        conn.close()

    def add_tracked_series(self, tmdb_id, title, status):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR IGNORE INTO tracked_series (tmdb_id, title, status, last_scan)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (str(tmdb_id), title, status))
            conn.commit()
        finally:
            conn.close()

    def add_media_item(self, tmdb_id, title, media_type, year=None, parent_tmdb_id=None, season=None, episode=None, air_date=None):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            if media_type == 'movie':
                c.execute('''
                    INSERT OR IGNORE INTO media_items (tmdb_id, title, media_type, year, status)
                    VALUES (?, ?, ?, ?, 'PENDING')
                ''', (str(tmdb_id), title, media_type, year))
            else:
                c.execute('''
                    INSERT OR IGNORE INTO media_items (
                        tmdb_id, parent_tmdb_id, title, media_type, year,
                        season_number, episode_number, air_date, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                ''', (str(tmdb_id), str(parent_tmdb_id), title, media_type, year, season, episode, air_date))

            conn.commit()
            return c.lastrowid
        except Exception as e:
            # print(f"Error adding item: {e}")
            # Ignore unique constraint errors usually
            pass
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

    def get_tracked_series(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM tracked_series")
        items = c.fetchall()
        conn.close()
        return items

    def update_status(self, db_id, status, magnet=None, hash=None, error=None, symlink_path=None):
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
        if symlink_path:
            updates.append("symlink_path = ?")
            params.append(symlink_path)

        params.append(db_id)

        sql = f"UPDATE media_items SET {', '.join(updates)} WHERE id = ?"
        c.execute(sql, params)
        conn.commit()
        conn.close()

    def retry_failed(self, hours=12):
        """Resets items from NOT_FOUND to PENDING if older than X hours."""
        conn = self.get_connection()
        c = conn.cursor()
        # SQLite doesn't have interval math like PG, use python or modifiers
        c.execute(f'''
            UPDATE media_items
            SET status = 'PENDING', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'NOT_FOUND'
            AND updated_at < datetime('now', '-{hours} hours')
        ''')
        count = c.rowcount
        conn.commit()
        conn.close()
        return count

db = Database()
