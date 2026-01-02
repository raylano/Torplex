#!/usr/bin/env python3
"""
TorBox Usenet Automator V4 - Full Integration
- Scans TorBox history for COMPLETED items
- Creates symlinks in proper media folders
- Notifies Sonarr/Radarr when downloads complete
- Handles API Rate Limits intelligently
"""

import os
import sys
import time
import logging
import requests
import shutil
import json
import re
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
TORBOX_API_KEY = os.environ.get('TORBOX_API_KEY', '')
WATCH_FOLDER = Path(os.environ.get('NZB_WATCH_FOLDER', '/data/nzb_watch'))
MOUNT_FOLDER = Path(os.environ.get('MOUNT_FOLDER', '/mnt/torplex/torbox'))
MEDIA_MOVIES = Path(os.environ.get('MEDIA_MOVIES', '/data/media/movies'))
MEDIA_SHOWS = Path(os.environ.get('MEDIA_SHOWS', '/data/media/shows'))
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '60'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Sonarr/Radarr Configuration
SONARR_URL = os.environ.get('SONARR_URL', '')
SONARR_API_KEY = os.environ.get('SONARR_API_KEY', '')
RADARR_URL = os.environ.get('RADARR_URL', '')
RADARR_API_KEY = os.environ.get('RADARR_API_KEY', '')

# API Endpoints
TORBOX_API_BASE = "https://api.torbox.app/v1/api"
USENET_CREATE_URL = f"{TORBOX_API_BASE}/usenet/createusenetdownload"
USENET_LIST_URL = f"{TORBOX_API_BASE}/usenet/mylist"

# Folders
NZB_DIR = WATCH_FOLDER
COMPLETED_DIR = WATCH_FOLDER / "completed"
FAILED_DIR = WATCH_FOLDER / "failed"
HISTORY_FILE = WATCH_FOLDER / "history.json"

# Logging setup
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Track processed IDs
processed_ids = set()

# TV Show patterns
TV_PATTERNS = [
    r'[Ss]\d{1,2}[Ee]\d{1,2}',  # S01E01
    r'[Ss]eason[\s\.]?\d{1,2}',  # Season 1
    r'\d{1,2}x\d{2}',            # 1x01
]

def is_tv_show(name: str) -> bool:
    """Detect if content is a TV show based on name patterns."""
    for pattern in TV_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False

def extract_show_info(name: str) -> tuple:
    """Extract show name and season/episode info from filename."""
    # Try to extract show name (everything before S01E01 pattern)
    match = re.search(r'^(.+?)[.\s]([Ss]\d{1,2})', name)
    if match:
        show_name = match.group(1).replace('.', ' ').strip()
        return show_name, True
    return name, False

def extract_movie_info(name: str) -> str:
    """Extract movie name and year from filename."""
    # Try to extract movie name and year
    match = re.search(r'^(.+?)[.\s](\d{4})', name)
    if match:
        movie_name = match.group(1).replace('.', ' ').strip()
        year = match.group(2)
        return f"{movie_name} ({year})"
    return name.replace('.', ' ').strip()

def load_history():
    """Load processed IDs from JSON file to prevent amnesia."""
    global processed_ids
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                processed_ids = set(data.get('processed', []))
            logger.info(f"Loaded {len(processed_ids)} processed items from history.")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")

def save_history():
    """Save processed IDs to JSON file."""
    try:
        temp_file = HISTORY_FILE.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump({'processed': list(processed_ids)}, f)
        temp_file.replace(HISTORY_FILE)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

def setup_directories():
    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_MOVIES.mkdir(parents=True, exist_ok=True)
    MEDIA_SHOWS.mkdir(parents=True, exist_ok=True)
    load_history()

def move_to_failed(nzb_path: Path):
    try:
        dest = FAILED_DIR / nzb_path.name
        if dest.exists(): dest.unlink()
        shutil.move(str(nzb_path), str(dest))
        logger.info(f"Moved failed NZB to: {dest}")
    except Exception as e:
        logger.error(f"Could not move failed NZB: {e}")

def upload_nzb(nzb_path: Path):
    """Upload NZB to TorBox."""
    if not TORBOX_API_KEY: return False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            headers = {"Authorization": f"Bearer {TORBOX_API_KEY}"}
            with open(nzb_path, 'rb') as f:
                files = {'file': (nzb_path.name, f, 'application/x-nzb')}
                logger.info(f"Uploading: {nzb_path.name} (Attempt {attempt+1})")
                
                resp = requests.post(USENET_CREATE_URL, headers=headers, files=files, timeout=60)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('success'):
                        logger.info(f"Upload SUCCESS: {nzb_path.name}")
                        time.sleep(2)
                        return True
                    else:
                        detail = data.get('detail', '')
                        logger.error(f"API Error: {detail}")
                        if "limit" in detail.lower():
                             logger.warning("Rate limit hit. Sleeping 60s.")
                             time.sleep(60)
                        return False
                elif resp.status_code == 429:
                    logger.warning(f"RATE LIMIT (429). Pausing for 60 seconds...")
                    time.sleep(60)
                    continue 
                else:
                    logger.error(f"HTTP Error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
            
    move_to_failed(nzb_path)
    return False

def find_file_in_mount(filename_part: str) -> Path:
    """Recursively search for file in mount."""
    try:
        if not MOUNT_FOLDER.exists(): return None
        search_term = filename_part.lower()
        
        # Strategy 1: Glob match
        for f in MOUNT_FOLDER.rglob("*"):
             if f.is_file():
                 if search_term in f.name.lower():
                     if "sample" not in f.name.lower() and f.stat().st_size > 50 * 1024 * 1024:
                         return f
    except Exception: pass
    return None

def find_folder_in_mount(name: str) -> Path:
    """Find the folder containing the download in the mount."""
    try:
        if not MOUNT_FOLDER.exists(): return None
        search_term = name.lower()
        
        # Look for directory matching the name
        for d in MOUNT_FOLDER.iterdir():
            if d.is_dir() and search_term in d.name.lower():
                return d
                
        # Also check subdirectories
        for d in MOUNT_FOLDER.rglob("*"):
            if d.is_dir() and search_term in d.name.lower():
                return d
    except Exception:
        pass
    return None

def create_symlink(source: Path, dest: Path) -> bool:
    """Create a symlink, handling existing files."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        os.symlink(source, dest)
        return True
    except Exception as e:
        logger.error(f"Symlink creation failed: {e}")
        return False

def notify_sonarr(series_name: str):
    """Notify Sonarr to rescan for new content."""
    if not SONARR_URL or not SONARR_API_KEY:
        return
    try:
        # Trigger a rescan
        headers = {"X-Api-Key": SONARR_API_KEY, "Content-Type": "application/json"}
        resp = requests.post(
            f"{SONARR_URL}/api/v3/command",
            headers=headers,
            json={"name": "RescanSeries"},
            timeout=30
        )
        if resp.status_code == 201:
            logger.info(f"Sonarr notified to rescan")
        else:
            logger.warning(f"Sonarr notification failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to notify Sonarr: {e}")

def notify_radarr(movie_name: str):
    """Notify Radarr to rescan for new content."""
    if not RADARR_URL or not RADARR_API_KEY:
        return
    try:
        # Trigger a rescan
        headers = {"X-Api-Key": RADARR_API_KEY, "Content-Type": "application/json"}
        resp = requests.post(
            f"{RADARR_URL}/api/v3/command",
            headers=headers,
            json={"name": "RescanMovie"},
            timeout=30
        )
        if resp.status_code == 201:
            logger.info(f"Radarr notified to rescan")
        else:
            logger.warning(f"Radarr notification failed: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to notify Radarr: {e}")

def check_mount_health():
    """Debug function to check what the script actually sees."""
    try:
        contents = list(MOUNT_FOLDER.glob("*"))
        names = [p.name for p in contents]
        logger.info(f"Mount Check ({MOUNT_FOLDER}): {len(names)} items found.")
        if not names:
            logger.warning("MOUNT APPEARS EMPTY! Please check rclone service.")
    except Exception as e:
        logger.error(f"Mount check failed: {e}")

def process_history():
    """Scan TorBox history and process COMPLETED items."""
    try:
        headers = {"Authorization": f"Bearer {TORBOX_API_KEY}"}
        resp = requests.get(USENET_LIST_URL, headers=headers, params={'bypass_cache': 'true'}, timeout=30)
        
        if resp.status_code == 429:
            logger.warning("Rate limit during poll. Sleeping 60s.")
            time.sleep(60)
            return

        if resp.status_code != 200:
            logger.error(f"Failed to fetch list. HTTP {resp.status_code}")
            return

        items = resp.json().get('data', [])
        
        for item in items:
            tb_id = str(item.get('id'))
            name = item.get('name')
            state = item.get('download_state', '').lower()
            
            # If already processed, skip
            if tb_id in processed_ids: continue
            
            if state in ['completed', 'downloaded']:
                logger.info(f"Processing Completed Item: {name} (ID: {tb_id})")
                
                # Determine if TV or Movie
                is_show = is_tv_show(name)
                
                # Find folder/file in mount
                found_folder = find_folder_in_mount(name)
                found_path = find_file_in_mount(name) if not found_folder else None
                
                if found_folder or found_path:
                    source = found_folder or found_path.parent
                    
                    # Create symlink in appropriate media folder
                    if is_show:
                        show_name, _ = extract_show_info(name)
                        dest_folder = MEDIA_SHOWS / show_name
                        
                        # Symlink all files in the folder
                        if found_folder:
                            for f in found_folder.rglob("*"):
                                if f.is_file() and f.suffix.lower() in ['.mkv', '.mp4', '.avi']:
                                    dest_file = dest_folder / f.name
                                    if create_symlink(f, dest_file):
                                        logger.info(f"SHOW SYMLINK: {dest_file}")
                        else:
                            dest_file = dest_folder / found_path.name
                            if create_symlink(found_path, dest_file):
                                logger.info(f"SHOW SYMLINK: {dest_file}")
                        
                        notify_sonarr(show_name)
                    else:
                        movie_name = extract_movie_info(name)
                        dest_folder = MEDIA_MOVIES / movie_name
                        
                        # Symlink main file
                        if found_folder:
                            for f in found_folder.rglob("*"):
                                if f.is_file() and f.suffix.lower() in ['.mkv', '.mp4', '.avi']:
                                    if "sample" not in f.name.lower():
                                        dest_file = dest_folder / f.name
                                        if create_symlink(f, dest_file):
                                            logger.info(f"MOVIE SYMLINK: {dest_file}")
                                        break  # Only first main file
                        else:
                            dest_file = dest_folder / found_path.name
                            if create_symlink(found_path, dest_file):
                                logger.info(f"MOVIE SYMLINK: {dest_file}")
                        
                        notify_radarr(movie_name)
                    
                    processed_ids.add(tb_id)
                    save_history()
                else:
                    logger.debug(f"File not found in mount yet: {name}")

            elif state in ['error', 'failed']:
                if tb_id not in processed_ids:
                    logger.warning(f"Item failed in TorBox: {name}. Ignoring.")
                    processed_ids.add(tb_id)
                    save_history()

    except Exception as e:
        logger.error(f"Process Loop Error: {e}")

class NZBHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory: return
        path = Path(event.src_path)
        if path.suffix.lower() == '.nzb':
            time.sleep(2)
            if upload_nzb(path):
                try: path.unlink() 
                except: pass

def main():
    logger.info("Starting TorBox Usenet Automator V5 (Interleaved Processing)...")
    logger.info(f"Mount folder: {MOUNT_FOLDER}")
    logger.info(f"Media movies: {MEDIA_MOVIES}")
    logger.info(f"Media shows: {MEDIA_SHOWS}")
    logger.info(f"Sonarr URL: {SONARR_URL or 'Not configured'}")
    logger.info(f"Radarr URL: {RADARR_URL or 'Not configured'}")
    
    setup_directories()
    check_mount_health()

    # Start file watcher for new NZBs
    observer = Observer()
    observer.schedule(NZBHandler(), str(NZB_DIR), recursive=False)
    observer.start()
    
    try:
        while True:
            # Check for existing NZBs to upload
            nzbs = list(NZB_DIR.glob("*.nzb"))
            
            if nzbs:
                batch_size = 5
                batch_wait = 600  # 10 minutes between batches
                
                # Process up to batch_size NZBs
                uploaded_count = 0
                for nzb in nzbs[:batch_size]:
                    if upload_nzb(nzb):
                        try: nzb.unlink()
                        except: pass
                        uploaded_count += 1
                    time.sleep(10)  # Brief pause between uploads
                
                remaining = len(nzbs) - uploaded_count
                if remaining > 0:
                    logger.info(f"Uploaded {uploaded_count} NZBs. {remaining} remaining in queue.")
                else:
                    logger.info(f"Uploaded {uploaded_count} NZBs. Queue empty.")
                
                # Poll for completed downloads and create symlinks
                logger.info("Polling for completed downloads...")
                process_history()
                
                # Wait before next batch (only if more NZBs remaining)
                if remaining > 0:
                    logger.info(f"Waiting {batch_wait}s before next batch...")
                    # Split wait time to allow symlink polling in between
                    half_wait = batch_wait // 2
                    time.sleep(half_wait)
                    
                    # Poll again halfway through the wait
                    logger.info("Mid-wait poll for completed downloads...")
                    process_history()
                    
                    time.sleep(half_wait)
            else:
                # No NZBs to upload, just poll for completed downloads
                process_history()
                time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
