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
        # Added is_anime column
        c.execute('''
            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id TEXT,
                parent_tmdb_id TEXT,
                title TEXT,
                media_type TEXT, -- 'movie' or 'episode'
                year INTEGER,
                season_number INTEGER,
                episode_number INTEGER,
                air_date TEXT,
                status TEXT DEFAULT 'PENDING',
                magnet_link TEXT,
                torbox_hash TEXT,
                symlink_path TEXT,
                is_anime INTEGER DEFAULT 0, -- 0 = False, 1 = True
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
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

    def add_media_item(self, tmdb_id, title, media_type, year=None, parent_tmdb_id=None, season=None, episode=None, air_date=None, is_anime=0):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            if media_type == 'movie':
                c.execute('''
                    INSERT OR IGNORE INTO media_items (tmdb_id, title, media_type, year, status, is_anime)
                    VALUES (?, ?, ?, ?, 'PENDING', ?)
                ''', (str(tmdb_id), title, media_type, year, is_anime))
            else:
                c.execute('''
                    INSERT OR IGNORE INTO media_items (
                        tmdb_id, parent_tmdb_id, title, media_type, year,
                        season_number, episode_number, air_date, status, is_anime
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                ''', (str(tmdb_id), str(parent_tmdb_id), title, media_type, year, season, episode, air_date, is_anime))

            conn.commit()
            return c.lastrowid
        except Exception as e:
            # print(f"Error adding item: {e}")
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

    def get_stats(self):
        """Get summary statistics for dashboard."""
        conn = self.get_connection()
        c = conn.cursor()
        
        stats = {}
        
        # Count by status
        c.execute("""
            SELECT status, COUNT(*) as count 
            FROM media_items 
            GROUP BY status
        """)
        status_counts = {row['status']: row['count'] for row in c.fetchall()}
        stats['pending'] = status_counts.get('PENDING', 0)
        stats['downloading'] = status_counts.get('DOWNLOADING', 0)
        stats['completed'] = status_counts.get('COMPLETED', 0)
        stats['failed'] = status_counts.get('NOT_FOUND', 0)
        stats['total'] = sum(status_counts.values())
        
        # Count by media type
        c.execute("""
            SELECT media_type, COUNT(*) as count 
            FROM media_items 
            GROUP BY media_type
        """)
        type_counts = {row['media_type']: row['count'] for row in c.fetchall()}
        stats['movies'] = type_counts.get('movie', 0)
        stats['episodes'] = type_counts.get('episode', 0)
        
        # Count tracked series
        c.execute("SELECT COUNT(*) as count FROM tracked_series")
        stats['series'] = c.fetchone()['count']
        
        # Recent items (last 10)
        c.execute("""
            SELECT * FROM media_items 
            ORDER BY updated_at DESC 
            LIMIT 10
        """)
        stats['recent'] = c.fetchall()
        
        # Failed items
        c.execute("""
            SELECT * FROM media_items 
            WHERE status = 'NOT_FOUND'
            ORDER BY updated_at DESC
            LIMIT 5
        """)
        stats['failed_items'] = c.fetchall()
        
        conn.close()
        return stats

    def update_status(self, db_id, status, magnet=None, hash=None, error=None, symlink_path=None, is_anime=None):
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
        if is_anime is not None:
            updates.append("is_anime = ?")
            params.append(is_anime)

        params.append(db_id)

        sql = f"UPDATE media_items SET {', '.join(updates)} WHERE id = ?"
        c.execute(sql, params)
        conn.commit()
        conn.close()

    def retry_failed(self, hours=12):
        """Resets items from NOT_FOUND to PENDING if older than X hours."""
        conn = self.get_connection()
        c = conn.cursor()
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

    def get_library_items(self, filter_type):
        """Get items filtered by type (movies, series, completed, pending)."""
        conn = self.get_connection()
        c = conn.cursor()
        
        if filter_type == 'movies':
            c.execute("SELECT * FROM media_items WHERE media_type = 'movie' ORDER BY created_at DESC")
            items = c.fetchall()
        elif filter_type == 'series':
            # Get unique series with calculated status (only COMPLETED if ALL episodes done)
            c.execute("""
                SELECT parent_tmdb_id as tmdb_id, 
                       MIN(title) as title, 
                       'series' as media_type, 
                       MIN(year) as year,
                       NULL as season_number, 
                       NULL as episode_number,
                       MAX(id) as id,
                       CASE 
                           WHEN COUNT(*) = SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) THEN 'COMPLETED'
                           WHEN SUM(CASE WHEN status = 'NOT_FOUND' THEN 1 ELSE 0 END) > 0 THEN 'NOT_FOUND'
                           WHEN SUM(CASE WHEN status = 'DOWNLOADING' THEN 1 ELSE 0 END) > 0 THEN 'DOWNLOADING'
                           ELSE 'PENDING'
                       END as status,
                       MAX(created_at) as created_at,
                       COUNT(*) as total_episodes,
                       SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_episodes
                FROM media_items 
                WHERE media_type = 'episode' 
                GROUP BY parent_tmdb_id
                ORDER BY created_at DESC
            """)
            items = c.fetchall()
        elif filter_type == 'completed':
            # Get completed movies and fully completed series separately
            # Movies
            c.execute("SELECT * FROM media_items WHERE media_type = 'movie' AND status = 'COMPLETED' ORDER BY updated_at DESC")
            movies = c.fetchall()
            
            # Series where ALL episodes are completed
            c.execute("""
                SELECT parent_tmdb_id as tmdb_id, 
                       MIN(title) as title, 
                       'series' as media_type, 
                       MIN(year) as year,
                       NULL as season_number, 
                       NULL as episode_number,
                       MAX(id) as id,
                       'COMPLETED' as status,
                       MAX(created_at) as created_at,
                       NULL as updated_at,
                       NULL as magnet_link,
                       NULL as torbox_hash,
                       NULL as symlink_path,
                       0 as is_anime,
                       NULL as error_message
                FROM media_items 
                WHERE media_type = 'episode' 
                GROUP BY parent_tmdb_id
                HAVING COUNT(*) = SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END)
                ORDER BY created_at DESC
            """)
            series = c.fetchall()
            
            # Combine and sort
            items = list(movies) + list(series)
        elif filter_type == 'pending':
            c.execute("SELECT * FROM media_items WHERE status IN ('PENDING', 'DOWNLOADING') ORDER BY created_at DESC")
            items = c.fetchall()
        elif filter_type == 'failed':
            c.execute("SELECT * FROM media_items WHERE status = 'NOT_FOUND' ORDER BY updated_at DESC")
            items = c.fetchall()
        else:
            c.execute("SELECT * FROM media_items ORDER BY created_at DESC")
            items = c.fetchall()
        
        conn.close()
        return items

    def get_item_by_id(self, item_id):
        """Get a single item by ID."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM media_items WHERE id = ?", (item_id,))
        item = c.fetchone()
        conn.close()
        return item

    def get_series_episodes(self, parent_tmdb_id):
        """Get all episodes for a series, grouped by season."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT * FROM media_items 
            WHERE parent_tmdb_id = ? AND media_type = 'episode'
            ORDER BY season_number, episode_number
        """, (str(parent_tmdb_id),))
        episodes = c.fetchall()
        conn.close()
        
        # Group by season
        grouped = {}
        for ep in episodes:
            season = ep['season_number'] or 1
            if season not in grouped:
                grouped[season] = []
            grouped[season].append(dict(ep))
        
        return grouped

db = Database()

