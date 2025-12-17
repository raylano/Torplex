import os
from pathlib import Path
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
        # Parse Plex XML/JSON response
        # Assuming JSON for now, need to verify structure or use library
        # If raw JSON:
        if not watchlist or 'MediaContainer' not in watchlist:
            return

        items = watchlist['MediaContainer'].get('Metadata', [])
        for item in items:
            # Plex ID vs TMDB ID matching
            # Plex usually provides GUIDs like tmdb://12345
            guid = None
            for g in item.get('Guid', []):
                if 'tmdb://' in g['id']:
                    guid = g['id'].replace('tmdb://', '')
                    break

            if guid:
                title = item.get('title')
                year = item.get('year')
                m_type = 'movie' if item.get('type') == 'movie' else 'tv'
                db.add_item(guid, title, m_type, year)

    def process_pending(self):
        """Searches for pending items."""
        items = db.get_pending_items()
        for item in items:
            # db row: id, tmdb_id, title, media_type, year, status...
            row_id, tmdb_id, title, media_type, year, _, _, _, _, _, _, _ = item

            print(f"Searching for {title} ({year})...")

            db.update_status(row_id, "SEARCHING")

            query = f"{title} {year}"
            search_results = self.prowlarr.search(query)

            if not search_results:
                print(f"No results for {title}")
                # Retry later or mark failed? Keep pending for retry?
                # For now revert to pending to retry later
                db.update_status(row_id, "PENDING")
                continue

            filtered = self.quality.filter_items(search_results)
            if not filtered:
                print(f"No suitable results for {title}")
                db.update_status(row_id, "PENDING")
                continue

            # Check cache for top X results
            top_candidates = filtered[:5]
            hashes = []
            magnet_map = {}

            for res in top_candidates:
                magnet = res.get('magnetUrl') or res.get('downloadUrl') # Some might be torrent file links
                if magnet and magnet.startswith('magnet:'):
                    h = self.quality.extract_hash(magnet)
                    if h:
                        hashes.append(h)
                        magnet_map[h] = magnet

            if not hashes:
                continue

            # Check cache
            # Note: Torbox check_cached takes comma separated string
            cache_result = self.torbox.check_cached(hashes)

            # Find first cached
            found_hash = None

            # Torbox returns: { "hash1": { "name": "...", "size": ... }, "hash2": ... } or List
            # If using format=list (as implemented in client currently returns raw response)
            # The client implementation actually returns the JSON response.
            # If format=object was default in doc but I used list in client param?
            # Re-reading client: params={"format": "list"}.
            # If format=list, response is likely [ "hash1", "hash2" ] (only the ones available).
            # Wait, docs say "List is the most performant option".
            # Let's assume it returns a list of cached hashes strings.

            if isinstance(cache_result, dict) and 'data' in cache_result:
                 # Torbox wrapper often wraps in 'data'
                 cache_list = cache_result['data']
            else:
                 cache_list = cache_result

            # If it's a list
            if isinstance(cache_list, list):
                for h in hashes:
                    if h in cache_list: # If hash is in the cached list
                        found_hash = h
                        break
            # If it's a dict (format=object)
            elif isinstance(cache_list, dict):
                 for h in hashes:
                    if h in cache_list and cache_list[h]: # Assuming bool or object
                        found_hash = h
                        break

            if found_hash:
                print(f"Found cached: {title}")
                magnet = magnet_map[found_hash]
                resp = self.torbox.add_magnet(magnet)
                if resp and resp.get('success'):
                    db.update_status(row_id, "DOWNLOADING", magnet=magnet, hash=found_hash)
                else:
                    print("Failed to add magnet to Torbox")
            else:
                print(f"Not cached: {title}")
                # Configurable: Add anyway or wait?
                # For now, wait.
                db.update_status(row_id, "PENDING")

    def process_downloads(self):
        """Checks status of downloads and symlinks."""
        items = db.get_downloading_items()

        # Get current torbox list to save API calls
        torbox_list_resp = self.torbox.get_torrents()
        if not torbox_list_resp or 'data' not in torbox_list_resp:
            return

        torbox_items = torbox_list_resp['data']
        # Map hash to item
        torbox_map = { t['hash']: t for t in torbox_items }

        for item in items:
            row_id, _, title, media_type, year, status, _, item_hash, _, _, _, _ = item

            if not item_hash:
                continue

            t_item = torbox_map.get(item_hash)
            if not t_item:
                # Torrent might have been deleted or not added yet?
                continue

            # Check status
            # Torbox statuses: "completed", "cached", "downloading", ...
            # "completed" means downloaded to Torbox.
            if t_item['download_state'] == 'completed' or t_item['download_state'] == 'cached':
                # Ready to symlink
                self.create_symlink(row_id, title, year, media_type, item_hash, t_item)

    def create_symlink(self, row_id, title, year, media_type, item_hash, torbox_item):
        mount_path = Path(config.get().mount_path)
        symlink_base = Path(config.get().symlink_path)

        # Determine source file in mount
        # Torbox mount structure: /mnt/torbox/torrents/{name}/... or just /mnt/torbox/{name}
        # usually it preserves the folder structure of the torrent.
        # We need to find the main video file.

        # rclone mount name usually matches torrent name.
        torrent_name = torbox_item['name']
        source_dir = mount_path / torrent_name

        if not source_dir.exists():
            # Maybe it's not in a folder?
            source_dir = mount_path
            # Check if file exists directly?
            # Safe bet: Recursive search for largest video file in mount/torrent_name
            # But wait, if it's not a folder?
            # Let's assume searching under mount_path for now if we can identify it.
            pass

        # Strategy: Search recursively for the largest file in the torrent's folder
        # We need to know where the torrent is in the mount.
        # Assuming Rclone mounts the root of Torbox.
        # Torbox folder structure:
        # It seems Torbox puts downloads in the root or a 'downloads' folder?
        # Let's assume root for now.

        # Robust find:
        search_path = mount_path / torrent_name
        if not search_path.exists():
             # Try matching by hash if possible? No.
             # Maybe the name is different.
             print(f"Source path not found: {search_path}")
             return

        # Find largest MKV/MP4
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
            # Create Symlink
            # dest: /mnt/media/movies/Title (Year)/Title.mkv
            clean_title = "".join([c for c in title if c.isalnum() or c in [' ', '-', '_']]).strip()

            year_str = f" ({year})" if year else ""

            if media_type == 'movie':
                dest_dir = symlink_base / "movies" / f"{clean_title}{year_str}"
                dest_file = dest_dir / f"{clean_title}.{best_file.suffix}" # Sonarr style renaming
            else:
                # TV Shows logic is complex (seasons/episodes).
                # For MVP, let's dump in a folder.
                # Ideal: Detect SxxExx from filename.
                dest_dir = symlink_base / "tv" / f"{clean_title}"
                dest_file = dest_dir / best_file.name # Keep original name for episodes to preserve SxxExx

            dest_dir.mkdir(parents=True, exist_ok=True)

            if not dest_file.exists():
                try:
                    os.symlink(best_file, dest_file)
                    print(f"Linked: {dest_file} -> {best_file}")
                    db.update_status(row_id, "COMPLETED", symlink_path=str(dest_file))
                except Exception as e:
                    print(f"Symlink Error: {e}")
