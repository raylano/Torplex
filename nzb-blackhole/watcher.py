#!/usr/bin/env python3
"""
TorBox Usenet Automator (V3 - State Reconstruction)
- Scans TorBox history for COMPLETED items.
- Checks if they match files in the mount.
- Symlinks them.
- Remembers processed IDs to avoid looping.
- Handles API Rate Limits intelligently.
"""

import os
import sys
import time
import logging
import requests
import shutil
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
TORBOX_API_KEY = os.environ.get('TORBOX_API_KEY', '')
WATCH_FOLDER = Path(os.environ.get('NZB_WATCH_FOLDER', '/data/nzb_watch'))
MOUNT_FOLDER = Path(os.environ.get('MOUNT_FOLDER', '/mnt/torplex'))
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '60'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

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
                             # Retry logic matches outer loop
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

def check_mount_health():
    """Debug function to check what the script actually sees."""
    try:
        contents = list(MOUNT_FOLDER.glob("*"))
        names = [p.name for p in contents]
        logger.info(f"Mount Check ({MOUNT_FOLDER}): {len(names)} items found. Contents: {names}")
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
        # Iterate REVERSE to process oldest first (if needed), or standard
        
        for item in items:
            tb_id = str(item.get('id'))
            name = item.get('name')
            state = item.get('download_state', '').lower()
            
            # If already processed, skip
            if tb_id in processed_ids: continue
            
            if state in ['completed', 'downloaded']:
                logger.info(f"Processing Completed Item: {name} (ID: {tb_id})")
                
                # Try to find file
                found_path = find_file_in_mount(name)
                
                if found_path:
                    # Symlink
                    try:
                        dest_folder = COMPLETED_DIR / name
                        dest_folder.mkdir(parents=True, exist_ok=True)
                        dest_file = dest_folder / found_path.name
                        
                        if dest_file.exists(): dest_file.unlink()
                        os.symlink(found_path, dest_file)
                        
                        logger.info(f"SYMLINK CREATED: {dest_file}")
                        processed_ids.add(tb_id)
                        save_history()
                        
                    except Exception as e:
                        logger.error(f"Symlink failed for {name}: {e}")
                else:
                    # Only log warning occasionally / debug
                    # logger.debug(f"File not found in mount yet: {name}")
                    pass

            elif state in ['error', 'failed']:
                # Mark as processed so we don't keep checking
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
    logger.info("Starting TorBox Usenet Automator V3 (State Reconstruction)...")
    setup_directories()
    
    # Check mount visibility on startup
    check_mount_health()

    # Process existing NZBs
    nzbs = list(NZB_DIR.glob("*.nzb"))
    if nzbs:
        logger.info(f"Found {len(nzbs)} existing NZBs to upload.")
        for nzb in nzbs:
            if upload_nzb(nzb):
                try: nzb.unlink()
                except: pass
            time.sleep(5) 
            
    observer = Observer()
    observer.schedule(NZBHandler(), str(NZB_DIR), recursive=False)
    observer.start()
    
    try:
        while True:
            # Periodic Mount Check (Debug)
            # check_mount_health() 
            
            process_history()
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
