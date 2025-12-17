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

    def _check_anime_status(self, tmdb_id, media_type):
        """
        Helper to check if an item is Anime.
        Returns 1 (True) or 0 (False).
        """
        if media_type == 'movie':
            details = self.tmdb.get_movie_details(tmdb_id)
        else:
            # For TV, we check the show details.
            # If passed tmdb_id is episode ID, this won't work directly, need Show ID.
            # Usually called with Show ID for TV.
            details = self.tmdb.get_tv_details(tmdb_id)

        if not details: return 0

        genres = [g['id'] for g in getattr(details, 'genres', [])]
        orig_lang = getattr(details, 'original_language', '')

        # 16 = Animation.
        # Language = ja (Japanese) or zh (Chinese/Donghua)
        if 16 in genres and orig_lang in ['ja', 'zh']:
            print(f"Detected as anime/donghua: lang={orig_lang}, genres={genres}")
            return 1
        return 0

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

                # Check Anime Status early
                is_anime = self._check_anime_status(guid, m_type)

                if m_type == 'movie':
                    db.add_media_item(guid, title, 'movie', year, is_anime=is_anime)
                else:
                    details = self.tmdb.get_tv_details(guid)
                    status = getattr(details, 'status', 'Returning Series') if details else 'Returning Series'
                    db.add_tracked_series(guid, title, status)

    def sync_running_series(self):
        """Scans tracked series for new episodes."""
        series_list = db.get_tracked_series()
        today = datetime.now().date()

        for series in series_list:
            s_tmdb_id = series['tmdb_id']
            s_title = series['title']

            # Check Anime Status for the series
            is_anime = self._check_anime_status(s_tmdb_id, 'tv')

            details = self.tmdb.get_tv_details(s_tmdb_id)
            if not details: continue

            seasons = getattr(details, 'seasons', [])

            for season in seasons:
                s_num = season.get('season_number')
                if s_num is None: continue

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

                    if air_date <= today:
                        e_num = ep.get('episode_number')
                        e_id = ep.get('id')

                        db.add_media_item(
                            tmdb_id=e_id,
                            title=s_title,
                            media_type='episode',
                            year=None,
                            parent_tmdb_id=s_tmdb_id,
                            season=s_num,
                            episode=e_num,
                            air_date=air_date_str,
                            is_anime=is_anime
                        )

    def process_pending(self):
        """Searches for pending items."""
        items = db.get_pending_items()
        for item in items:
            row_id = item['id']
            title = item['title']
            media_type = item['media_type']
            year = item['year']
            season = item['season_number']
            episode = item['episode_number']
            parent_id = item['parent_tmdb_id']
            tmdb_id = item['tmdb_id']
            is_anime_db = item['is_anime']

            query = ""
            is_anime = bool(is_anime_db)

            if media_type == 'movie':
                query = f"{title} {year}"
                # Re-check if not set?
                if not is_anime_db:
                    check = self._check_anime_status(tmdb_id, 'movie')
                    if check:
                        is_anime = True
                        db.update_status(row_id, "PENDING", is_anime=1) # Update DB
            else:
                query = f"{title} S{season:02d}E{episode:02d}"
                if not is_anime_db and parent_id:
                     check = self._check_anime_status(parent_id, 'tv')
                     if check:
                        is_anime = True
                        db.update_status(row_id, "PENDING", is_anime=1)

            print(f"Searching for {query} (Anime={is_anime})...")
            db.update_status(row_id, "SEARCHING")

            search_results = self.prowlarr.search(query)

            if not search_results:
                print(f"No results for {query}")
                db.update_status(row_id, "NOT_FOUND")
                continue

            filtered = self.quality.filter_items(search_results, is_anime=is_anime)
            if not filtered:
                print(f"No suitable results for {query}")
                db.update_status(row_id, "NOT_FOUND")
                continue

            top_candidates = filtered[:5]  # Check up to 5 for cache
            hashes = []
            magnet_map = {}
            
            print(f"Processing {len(top_candidates)} candidates for {query}...")

            # Extract magnets for multiple candidates (so we can check cache)
            for i, res in enumerate(top_candidates):
                print(f"  Candidate {i+1}: {res.get('title', 'Unknown')[:60]}...")
                magnet, info_hash = self.prowlarr.get_magnet_from_result(res)
                if magnet and info_hash:
                    hashes.append(info_hash)
                    magnet_map[info_hash] = magnet
                    # Don't break - collect multiple for cache check

            if not hashes:
                print(f"No magnet links could be extracted for {query}")
                db.update_status(row_id, "NOT_FOUND")
                continue

            # Check cache for ALL collected hashes
            print(f"Checking cache for {len(hashes)} hashes...")
            cache_result = self.torbox.check_cached(hashes)
            cached_hashes = []

            if isinstance(cache_result, dict) and 'data' in cache_result:
                cache_list = cache_result['data']
            else:
                cache_list = cache_result

            if isinstance(cache_list, list):
                cached_hashes = [h for h in hashes if h in cache_list]
            elif isinstance(cache_list, dict):
                cached_hashes = [h for h in hashes if h in cache_list and cache_list[h]]

            # PRIORITY: Use cached hash if available, otherwise first (highest seeded)
            if cached_hashes:
                use_hash = cached_hashes[0]  # First cached
                print(f"✓ Found {len(cached_hashes)} cached! Using: {use_hash[:16]}...")
            else:
                use_hash = hashes[0]  # First non-cached (highest seeded)
                print(f"✗ No cached torrents, using highest seeded: {use_hash[:16]}...")
            
            magnet = magnet_map[use_hash]
            resp = self.torbox.add_magnet(magnet)
            if resp and resp.get('success'):
                db.update_status(row_id, "DOWNLOADING", magnet=magnet, hash=use_hash)
                print(f"Successfully added to Torbox: {query}")
            else:
                db.update_status(row_id, "NOT_FOUND", error="Failed to add to Torbox")

    def retry_failed_downloads(self):
        count = db.retry_failed(hours=12)
        if count > 0:
            print(f"Reset {count} items to PENDING for retry.")

    def process_downloads(self):
        items = db.get_downloading_items()
        print(f"Process downloads: {len(items)} items with DOWNLOADING status")

        torbox_list_resp = self.torbox.get_torrents()
        if not torbox_list_resp or 'data' not in torbox_list_resp:
            print("No torrents in Torbox list")
            return

        torbox_items = torbox_list_resp['data']
        print(f"Torbox has {len(torbox_items)} torrents")
        torbox_map = { t['hash']: t for t in torbox_items }

        for item in items:
            row_id = item['id']
            title = item['title']
            media_type = item['media_type']
            year = item['year']
            season = item['season_number']
            item_hash = item['torbox_hash']
            is_anime = bool(item['is_anime']) # Retrieve from DB

            if not item_hash: continue

            t_item = torbox_map.get(item_hash)
            if not t_item: continue

            if t_item['download_state'] == 'completed' or t_item['download_state'] == 'cached':
                self.create_symlink(row_id, title, year, media_type, season, item_hash, t_item, is_anime)

    def create_symlink(self, row_id, title, year, media_type, season, item_hash, torbox_item, is_anime):
        mount_path = Path(config.get().mount_path)
        symlink_base = Path(config.get().symlink_path)

        torrent_name = torbox_item['name']
        source_dir = mount_path / torrent_name

        search_path = mount_path / torrent_name
        print(f"Looking for files in: {search_path}")
        if not search_path.exists():
            print(f"Path does not exist: {search_path}")
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

            # Determine Target Directory based on media_type and is_anime
            if media_type == 'movie':
                if is_anime:
                    # Anime Movies -> /mnt/media/animemovies
                    base_folder = symlink_base / "animemovies"
                else:
                    # Movies -> /mnt/media/movies
                    base_folder = symlink_base / "movies"

                year_str = f" ({year})" if year else ""
                dest_dir = base_folder / f"{clean_title}{year_str}"
                dest_file = dest_dir / f"{clean_title}.{best_file.suffix}"
            else:
                # TV
                if is_anime:
                    # Anime Series -> /mnt/media/animeshows
                    base_folder = symlink_base / "animeshows"
                else:
                    # TV Series -> /mnt/media/tvshows
                    base_folder = symlink_base / "tvshows"

                dest_dir = base_folder / f"{clean_title}" / f"Season {season}"
                dest_file = dest_dir / best_file.name

            dest_dir.mkdir(parents=True, exist_ok=True)

            if not dest_file.exists():
                try:
                    os.symlink(best_file, dest_file)
                    print(f"Linked: {dest_file} -> {best_file}")
                    db.update_status(row_id, "COMPLETED", symlink_path=str(dest_file))
                except Exception as e:
                    print(f"Symlink Error: {e}")
