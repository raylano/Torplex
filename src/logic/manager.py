import os
from pathlib import Path
from datetime import datetime
from src.config import config
from src.database import db
from src.clients.torbox import TorboxClient
from src.clients.tmdb import TMDBClient
from src.clients.plex import PlexClient
from src.clients.prowlarr import ProwlarrClient
from src.logic.quality import QualityManager

class Manager:
    def __init__(self):
        self.torbox = TorboxClient()
        self.tmdb = TMDBClient()
        self.plex = PlexClient()
        self.prowlarr = ProwlarrClient()
        self.quality = QualityManager()

    def sync_watchlist(self):
        """Checks Plex Watchlist and adds new items to DB."""
        token = config.get().plex_token
        if not token:
            print("No Plex Token set.")
            return

        watchlist = self.plex.get_watchlist(token)
        if not watchlist or 'MediaContainer' not in watchlist:
            return

        items = watchlist['MediaContainer'].get('Metadata', [])
        for item in items:
            guid = None
            for g in item.get('Guid', []):
                if 'tmdb://' in g['id']:
                    guid = g['id'].replace('tmdb://', '')
                    break

            if guid:
                title = item.get('title')
                year = item.get('year')
                m_type = 'movie' if item.get('type') == 'movie' else 'tv'

                if m_type == 'movie':
                    db.add_media_item(guid, title, 'movie', year)
                else:
                    # TV Show: Add to tracked series, then trigger scan
                    # Fetch details to get status
                    details = self.tmdb.get_tv_details(guid)
                    status = getattr(details, 'status', 'Returning Series') if details else 'Returning Series'
                    db.add_tracked_series(guid, title, status)

        # After syncing watchlist, verify we scan the series immediately if possible
        # but the scheduler will pick it up via sync_running_series

    def sync_running_series(self):
        """Scans tracked series for new episodes."""
        series_list = db.get_tracked_series()
        today = datetime.now().date()

        for series in series_list:
            # series: id, tmdb_id, title, status, last_scan
            s_tmdb_id = series['tmdb_id']
            s_title = series['title']

            # Fetch show details to get number of seasons
            details = self.tmdb.get_tv_details(s_tmdb_id)
            if not details: continue

            seasons = getattr(details, 'seasons', [])

            for season in seasons:
                s_num = season.get('season_number')
                if s_num is None: continue

                # Fetch Season Details (Episodes)
                s_details = self.tmdb.get_season_details(s_tmdb_id, s_num)
                if not s_details: continue

                episodes = getattr(s_details, 'episodes', [])
                for ep in episodes:
                    air_date_str = ep.get('air_date')
                    if not air_date_str: continue

                    try:
                        air_date = datetime.strptime(air_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        continue

                    # If aired or airing today
                    if air_date <= today:
                        e_num = ep.get('episode_number')
                        e_id = ep.get('id')
                        e_name = ep.get('name')

                        # Add to media_items
                        # Note: UNIQUE constraint prevents duplicates
                        db.add_media_item(
                            tmdb_id=e_id,
                            title=s_title, # Store Series Title for easier searching
                            media_type='episode',
                            year=None,
                            parent_tmdb_id=s_tmdb_id,
                            season=s_num,
                            episode=e_num,
                            air_date=air_date_str
                        )

    def _is_anime(self, tmdb_id, media_type):
        """Checks if the item is Anime based on TMDB metadata."""
        if media_type == 'movie':
            details = self.tmdb.get_movie_details(tmdb_id)
        else:
            # For episodes, we check the Parent Show
            # We assume tmdb_id passed here is the Parent ID if we call it correctly
            # Wait, in process_pending, for episodes, we have parent_tmdb_id
            pass
            return False # Logic moved to process_pending

        if not details: return False
        genres = [g['id'] for g in getattr(details, 'genres', [])]
        orig_lang = getattr(details, 'original_language', '')
        if 16 in genres and orig_lang == 'ja':
            return True
        return False

    def process_pending(self):
        """Searches for pending items."""
        items = db.get_pending_items()
        for item in items:
            # db row: id, tmdb_id, parent_tmdb_id, title, media_type, year, season, episode, air_date, status...
            row_id = item['id']
            title = item['title']
            media_type = item['media_type']
            year = item['year']
            season = item['season_number']
            episode = item['episode_number']
            parent_id = item['parent_tmdb_id']
            tmdb_id = item['tmdb_id']

            # Construct Query & Check Anime
            is_anime = False
            query = ""

            if media_type == 'movie':
                query = f"{title} {year}"
                is_anime = self._is_anime(tmdb_id, 'movie')
            else:
                # Episode
                # Format: Title S01E01
                query = f"{title} S{season:02d}E{episode:02d}"
                # Check if show is anime using parent_id
                details = self.tmdb.get_tv_details(parent_id)
                if details:
                    genres = [g['id'] for g in getattr(details, 'genres', [])]
                    orig_lang = getattr(details, 'original_language', '')
                    if 16 in genres and orig_lang == 'ja':
                        is_anime = True

            print(f"Searching for {query} (Anime={is_anime})...")
            db.update_status(row_id, "SEARCHING")

            search_results = self.prowlarr.search(query)

            if not search_results:
                print(f"No results for {query}")
                db.update_status(row_id, "NOT_FOUND") # Use NOT_FOUND for retry logic
                continue

            filtered = self.quality.filter_items(search_results, is_anime=is_anime)
            if not filtered:
                print(f"No suitable results for {query}")
                db.update_status(row_id, "NOT_FOUND")
                continue

            # Check cache logic (Same as before)
            top_candidates = filtered[:5]
            hashes = []
            magnet_map = {}

            for res in top_candidates:
                magnet = res.get('magnetUrl') or res.get('downloadUrl')
                if magnet and magnet.startswith('magnet:'):
                    h = self.quality.extract_hash(magnet)
                    if h:
                        hashes.append(h)
                        magnet_map[h] = magnet

            if not hashes:
                db.update_status(row_id, "NOT_FOUND")
                continue

            cache_result = self.torbox.check_cached(hashes)
            found_hash = None

            if isinstance(cache_result, dict) and 'data' in cache_result:
                 cache_list = cache_result['data']
            else:
                 cache_list = cache_result

            if isinstance(cache_list, list):
                for h in hashes:
                    if h in cache_list:
                        found_hash = h
                        break
            elif isinstance(cache_list, dict):
                 for h in hashes:
                    if h in cache_list and cache_list[h]:
                        found_hash = h
                        break

            if found_hash:
                print(f"Found cached: {query}")
                magnet = magnet_map[found_hash]
                resp = self.torbox.add_magnet(magnet)
                if resp and resp.get('success'):
                    db.update_status(row_id, "DOWNLOADING", magnet=magnet, hash=found_hash)
                else:
                    print("Failed to add magnet to Torbox")
                    db.update_status(row_id, "NOT_FOUND") # Fail safe
            else:
                print(f"Not cached: {query}")
                # Configurable: Add anyway or wait?
                db.update_status(row_id, "NOT_FOUND")

    def retry_failed_downloads(self):
        """Retries items that were NOT_FOUND > 12 hours ago."""
        count = db.retry_failed(hours=12)
        if count > 0:
            print(f"Reset {count} items to PENDING for retry.")

    def process_downloads(self):
        """Checks status of downloads and symlinks."""
        items = db.get_downloading_items()

        torbox_list_resp = self.torbox.get_torrents()
        if not torbox_list_resp or 'data' not in torbox_list_resp:
            return

        torbox_items = torbox_list_resp['data']
        torbox_map = { t['hash']: t for t in torbox_items }

        for item in items:
            # item is Row object
            row_id = item['id']
            title = item['title']
            media_type = item['media_type']
            year = item['year']
            season = item['season_number']
            item_hash = item['torbox_hash']

            if not item_hash: continue

            t_item = torbox_map.get(item_hash)
            if not t_item: continue

            if t_item['download_state'] == 'completed' or t_item['download_state'] == 'cached':
                self.create_symlink(row_id, title, year, media_type, season, item_hash, t_item)

    def create_symlink(self, row_id, title, year, media_type, season, item_hash, torbox_item):
        mount_path = Path(config.get().mount_path)
        symlink_base = Path(config.get().symlink_path)

        torrent_name = torbox_item['name']
        source_dir = mount_path / torrent_name

        # Robust find (as before)
        search_path = mount_path / torrent_name
        if not search_path.exists():
             return

        video_extensions = ['.mkv', '.mp4', '.avi']
        best_file = None
        max_size = 0

        if search_path.is_file():
             if search_path.suffix in video_extensions:
                best_file = search_path
        else:
            for root, dirs, files in os.walk(search_path):
                for f in files:
                    fp = Path(root) / f
                    if fp.suffix in video_extensions:
                        size = fp.stat().st_size
                        if size > max_size:
                            max_size = size
                            best_file = fp

        if best_file:
            clean_title = "".join([c for c in title if c.isalnum() or c in [' ', '-', '_']]).strip()

            if media_type == 'movie':
                year_str = f" ({year})" if year else ""
                dest_dir = symlink_base / "movies" / f"{clean_title}{year_str}"
                dest_file = dest_dir / f"{clean_title}.{best_file.suffix}"
            else:
                # TV Shows
                # Structure: /tv/Show Name/Season X/Show Name - SxxExx.mkv
                dest_dir = symlink_base / "tv" / f"{clean_title}" / f"Season {season}"
                dest_file = dest_dir / best_file.name # Keep original SxxExx filename

            dest_dir.mkdir(parents=True, exist_ok=True)

            if not dest_file.exists():
                try:
                    os.symlink(best_file, dest_file)
                    print(f"Linked: {dest_file} -> {best_file}")
                    db.update_status(row_id, "COMPLETED", symlink_path=str(dest_file))
                except Exception as e:
                    print(f"Symlink Error: {e}")
