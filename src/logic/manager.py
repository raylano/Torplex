import os
from pathlib import Path
from datetime import datetime
from src.config import config
from src.database import db
from src.clients.debrid import get_client as get_debrid_client
from src.clients.tmdb import TMDBClient
from src.clients.plex import PlexClient
from src.clients.prowlarr import ProwlarrClient
from src.logic.quality import QualityManager
from src.logic.scraper import get_scraper, MultiScraper

class Manager:
    def __init__(self):
        self.debrid = get_debrid_client()
        self.tmdb = TMDBClient()
        self.plex = PlexClient()
        self.prowlarr = ProwlarrClient()
        self.quality = QualityManager()
        self.scraper = get_scraper()

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
        """Checks Plex Watchlist and adds new items to DB using plexapi."""
        token = config.get().plex_token
        if not token:
            print("[Watchlist] No Plex Token set.")
            return

        # Get watchlist using new plexapi-based client
        items = self.plex.get_watchlist(token)
        
        if not items:
            print("[Watchlist] No items found or error fetching watchlist")
            return
        
        print(f"[Watchlist] Processing {len(items)} items from Plex")
        added_count = 0
        
        for item in items:
            try:
                title = item.get('title')
                year = item.get('year')
                media_type = item.get('type')  # 'movie' or 'show'
                tmdb_id = item.get('tmdb_id')
                imdb_id = item.get('imdb_id')
                tvdb_id = item.get('tvdb_id')
                
                if media_type == 'movie':
                    if not tmdb_id:
                        print(f"  [!] {title}: No TMDB ID, skipping")
                        continue
                    
                    # Check if already exists
                    existing = db.get_media_item(tmdb_id, 'movie')
                    if existing:
                        continue
                    
                    # Check anime status
                    is_anime = self._check_anime_status(tmdb_id, 'movie')
                    
                    db.add_media_item(tmdb_id, title, 'movie', year, is_anime=is_anime)
                    print(f"  [+] Added movie: {title} ({year})")
                    added_count += 1
                    
                else:  # show/series
                    # For shows, we need TMDB ID - try to convert from TVDB if needed
                    if not tmdb_id and tvdb_id:
                        # Try to find TMDB ID from TVDB
                        search_results = self.tmdb.search_tv(title)
                        if search_results:
                            for result in search_results:
                                if hasattr(result, 'id'):
                                    tmdb_id = str(result.id)
                                    break
                    
                    if not tmdb_id:
                        print(f"  [!] {title}: No TMDB ID, skipping")
                        continue
                    
                    # Check if series already tracked
                    existing = db.get_tracked_series_by_id(tmdb_id)
                    if existing:
                        continue
                    
                    # Get show details and add
                    details = self.tmdb.get_tv_details(tmdb_id)
                    status = getattr(details, 'status', 'Returning Series') if details else 'Returning Series'
                    
                    db.add_tracked_series(tmdb_id, title, status)
                    print(f"  [+] Added series: {title}")
                    added_count += 1
                    
            except Exception as e:
                print(f"  [!] Error processing {item.get('title', 'unknown')}: {e}")
        
        print(f"[Watchlist] Added {added_count} new items")

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

    def _get_imdb_id(self, tmdb_id: str, media_type: str) -> str:
        """Get IMDB ID from TMDB ID."""
        try:
            if media_type == 'movie':
                details = self.tmdb.get_movie_details(tmdb_id)
            else:
                details = self.tmdb.get_tv_details(tmdb_id)
            
            if details:
                return getattr(details, 'imdb_id', None) or getattr(details, 'external_ids', {}).get('imdb_id')
        except:
            pass
        return None

    def process_pending(self):
        """Searches for pending items using multi-scraper (Torrentio -> Prowlarr)."""
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
            
            # Get or lookup IMDB ID for better scraping
            # sqlite3.Row doesn't have .get(), use try/except
            try:
                imdb_id = item['imdb_id'] or item['parent_imdb_id']
            except (KeyError, IndexError):
                imdb_id = None
            
            is_anime = bool(is_anime_db)

            if media_type == 'movie':
                # Re-check anime status
                if not is_anime_db:
                    check = self._check_anime_status(tmdb_id, 'movie')
                    if check:
                        is_anime = True
                        db.update_status(row_id, "PENDING", is_anime=1)
                
                # Lookup IMDB ID if not present
                if not imdb_id:
                    imdb_id = self._get_imdb_id(tmdb_id, 'movie')
                    print(f"  IMDB lookup: {tmdb_id} -> {imdb_id}")
                
                print(f"\n[Scrape] {title} ({year}) - IMDB: {imdb_id or 'N/A'}")
                db.update_status(row_id, "SEARCHING")
                
                # Use multi-scraper
                scraped = self.scraper.scrape_movie(title, year, imdb_id)
            else:
                # Episode
                if not is_anime_db and parent_id:
                    check = self._check_anime_status(parent_id, 'tv')
                    if check:
                        is_anime = True
                        db.update_status(row_id, "PENDING", is_anime=1)
                
                # Lookup IMDB ID for parent series
                if not imdb_id and parent_id:
                    imdb_id = self._get_imdb_id(parent_id, 'tv')
                    print(f"  IMDB lookup: {parent_id} -> {imdb_id}")
                
                print(f"\n[Scrape] {title} S{season:02d}E{episode:02d} - IMDB: {imdb_id or 'N/A'}")
                db.update_status(row_id, "SEARCHING")
                
                # Use multi-scraper
                scraped = self.scraper.scrape_episode(title, season, episode, year, imdb_id, is_anime)
            
            if not scraped:
                # Build from hash
                magnet = f"magnet:?xt=urn:btih:{selected.info_hash}"
            
            # Add to debrid
            resp = self.debrid.add_magnet(magnet)
            if resp and resp.get('success'):
                db.update_status(
                    row_id, 
                    "DOWNLOADING", 
                    magnet=magnet, 
                    hash=selected.info_hash
                )
                print(f"  ✓ Added to {self.debrid.name}")
            else:
                db.update_status(row_id, "NOT_FOUND", error=f"Failed to add to {self.debrid.name}")

    def retry_failed_downloads(self):
        count = db.retry_failed(hours=12)
        if count > 0:
            print(f"Reset {count} items to PENDING for retry.")

    def process_downloads(self):
        items = db.get_downloading_items()
        print(f"Process downloads: {len(items)} items with DOWNLOADING status")

        debrid_torrents = self.debrid.get_torrents()
        if not debrid_torrents:
            print(f"No torrents in {self.debrid.name} list")
            return

        print(f"{self.debrid.name} has {len(debrid_torrents)} torrents")
        debrid_map = { t['hash'].lower(): t for t in debrid_torrents }

        recovery_failures = 0

        for item in items:
            row_id = item['id']
            title = item['title']
            media_type = item['media_type']
            year = item['year']
            season = item['season_number']
            item_hash = item['torbox_hash']
            is_anime = bool(item['is_anime']) # Retrieve from DB

            if not item_hash: 
                print(f"  Skipping {title}: no hash in DB")
                continue

            # Normalize hash to lowercase for comparison
            item_hash_lower = item_hash.lower()
            t_item = debrid_map.get(item_hash_lower)
            
            if not t_item:
                print(f"  {title}: hash {item_hash_lower[:16]}... not found in {self.debrid.name}")
                
                # Anti-spam / rate limit protection
                if recovery_failures >= 3:
                    print("  [!] Too many recovery failures. Skipping remaining recoveries to avoid rate limits.")
                    continue

                # Try to recover by re-adding if not in list but marked as downloading
                try:
                    magnet = item['magnet_link']
                    if magnet:
                        print(f"  Attempting to re-add missing download to {self.debrid.name}...")
                        res = self.debrid.add_magnet(magnet)
                        if not res:
                            recovery_failures += 1
                except Exception as e:
                    print(f"  Recovery failed: {e}")
                    recovery_failures += 1
                continue

            print(f"  {title}: state={t_item['download_state']}")
            if t_item['download_state'] == 'completed' or t_item['download_state'] == 'cached':
                # Pass extra info if available
                try:
                    debrid_file_id = item['debrid_file_id']
                except (KeyError, IndexError):
                    debrid_file_id = None
                
                self.create_symlink(row_id, title, year, media_type, season, item_hash_lower, t_item, is_anime, debrid_file_id)

    def create_symlink(self, row_id, title, year, media_type, season, item_hash, debrid_item, is_anime, debrid_file_id=None):
        mount_path = Path(config.get().mount_path)
        symlink_base = Path(config.get().symlink_path)

        debrid_name = debrid_item.get('name', '')
        
        # Smart file finder - handles name mismatches between debrid API and actual files
        best_file = self._find_video_file(mount_path, debrid_name, title, year)
        
        if not best_file:
            print(f"  Could not find video file for: {title}")
            return

        print(f"  Found video: {best_file}")
        
        clean_title = "".join([c for c in title if c.isalnum() or c in [' ', '-', '_']]).strip()

        # Determine Target Directory based on media_type and is_anime
        if media_type == 'movie':
            if is_anime:
                base_folder = symlink_base / "animemovies"
            else:
                base_folder = symlink_base / "movies"

            year_str = f" ({year})" if year else ""
            dest_dir = base_folder / f"{clean_title}{year_str}"
            dest_file = dest_dir / f"{clean_title}{best_file.suffix}"
        else:
            # TV
            if is_anime:
                base_folder = symlink_base / "animeshows"
            else:
                base_folder = symlink_base / "tvshows"

            dest_dir = base_folder / f"{clean_title}" / f"Season {season}"
            dest_file = dest_dir / best_file.name

        dest_dir.mkdir(parents=True, exist_ok=True)

        if not dest_file.exists():
            try:
                os.symlink(best_file, dest_file)
                print(f"  ✓ Linked: {dest_file.name} -> {best_file}")
                db.update_status(row_id, "COMPLETED", symlink_path=str(dest_file))
            except Exception as e:
                print(f"  ✗ Symlink Error: {e}")
        else:
            print(f"  Symlink already exists: {dest_file}")
            db.update_status(row_id, "COMPLETED", symlink_path=str(dest_file))

    def _find_video_file(self, mount_path: Path, debrid_name: str, title: str, year: int) -> Path:
        """
        Smart file finder that handles name mismatches between debrid API and actual files.
        
        Strategy:
        1. Try exact debrid name match
        2. Try fuzzy title match on folders
        3. Scan all recent folders if nothing found
        """
        video_extensions = ['.mkv', '.mp4', '.avi', '.m4v', '.webm']
        
        def find_best_video(search_path: Path) -> Path:
            """Find largest video file in a path."""
            if not search_path.exists():
                return None
            
            if search_path.is_file():
                if search_path.suffix.lower() in video_extensions:
                    return search_path
                return None
            
            best_file = None
            max_size = 0
            
            try:
                for root, dirs, files in os.walk(search_path):
                    for f in files:
                        fp = Path(root) / f
                        if fp.suffix.lower() in video_extensions:
                            try:
                                size = fp.stat().st_size
                                if size > max_size:
                                    max_size = size
                                    best_file = fp
                            except:
                                pass
                return best_file
            except Exception as e:
                print(f"  Error scanning {search_path}: {e}")
                return None
            
        # Strategy 1: Try exact debrid name match
        result = None
        if debrid_name:
            result = find_best_video(mount_path / debrid_name)

        if result:
            return result

        # Strategy 2: Fuzzy match on title
        normalized_title = normalize_name(title)
        print(f"  Exact path failed. Fuzzy matching for: {title}")
        
        try:
            for folder in mount_path.iterdir():
                if folder.is_dir():
                    normalized_folder = normalize_name(folder.name)
                    # Check if title is contained in folder name
                    if normalized_title in normalized_folder or normalized_folder in normalized_title:
                        print(f"  Fuzzy match found: {folder.name}")
                        result = find_best_video(folder)
                        if result:
                            return result
        except Exception as e:
            print(f"  Error listing mount: {e}")

        # Strategy 3: If year provided, try to match year in folder name
        if year:
            print(f"  Trying year-based match for {year}")
            try:
                for folder in mount_path.iterdir():
                    if folder.is_dir() and str(year) in folder.name:
                        normalized_folder = normalize_name(folder.name)
                        # Looser match - just check first few chars
                        if normalized_title[:5] in normalized_folder:
                            print(f"  Year+prefix match: {folder.name}")
                            result = find_best_video(folder)
                            if result:
                                return result
            except:
                pass

        print(f"  No match found for: {title}")
        return None

