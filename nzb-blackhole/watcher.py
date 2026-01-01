#!/usr/bin/env python3
"""
TorBox NZB Blackhole Watcher & Symlinker
1. Watches /data/nzb_watch for .nzb files
2. Uploads them to TorBox API
3. Polls TorBox for download completion
4. Locates the file in /mnt/torplex
5. Creates a symlink in /data/nzb_watch/completed/<Name> pointing to the mounted file
6. This allows Sonarr/Radarr to "Import" the file (as a symlink) automatically
"""

import os
import sys
import time
import logging
import requests
import shutil
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
TORBOX_API_KEY = os.environ.get('TORBOX_API_KEY', '')
WATCH_FOLDER = Path(os.environ.get('NZB_WATCH_FOLDER', '/data/nzb_watch'))
MOUNT_FOLDER = Path(os.environ.get('MOUNT_FOLDER', '/mnt/torplex'))
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '10'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

TORBOX_API_BASE = "https://api.torbox.app/v1/api"
USENET_CREATE_URL = f"{TORBOX_API_BASE}/usenet/createusenetdownload"
USENET_LIST_URL = f"{TORBOX_API_BASE}/usenet/mylist"

# Folders for blackhole workflow
NZB_DIR = WATCH_FOLDER
COMPLETED_DIR = WATCH_FOLDER / "completed"

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Track active downloads: { torbox_id: { 'name': str, 'attempts': int } }
active_downloads = {}

def setup_directories():
    """Ensure completed directory exists."""
    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)

def upload_nzb(nzb_path: Path):
    """Upload NZB to TorBox and track it. Handles rate limiting."""
    if not TORBOX_API_KEY:
        return False
    
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            headers = {"Authorization": f"Bearer {TORBOX_API_KEY}"}
            with open(nzb_path, 'rb') as f:
                files = {'file': (nzb_path.name, f, 'application/x-nzb')}
                logger.info(f"Uploading NZB: {nzb_path.name} (Attempt {attempt+1})")
                resp = requests.post(USENET_CREATE_URL, headers=headers, files=files, timeout=60)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('success'):
                        tb_id = data.get('data', {}).get('usenetdownload_id')
                        name = data.get('data', {}).get('name', nzb_path.stem)
                        logger.info(f"Uploaded {nzb_path.name} -> ID: {tb_id}")
                        
                        # Add to active tracking
                        if tb_id:
                            active_downloads[str(tb_id)] = {'name': name, 'original_stem': nzb_path.stem, 'attempts': 0}
                        
                        # Sleep a bit to be nice to API
                        time.sleep(2)
                        return True
                    else:
                        logger.error(f"TorBox API Error: {data.get('detail')}")
                        return False
                
                elif resp.status_code == 429:
                    logger.warning(f"Rate limited (429). Sleeping for {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff
                    continue
                else:
                    logger.error(f"HTTP Error {resp.status_code}: {resp.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
            
    return False

def find_file_in_mount(filename_part: str) -> Path:
    """Recursively search for a file in the mount."""
    logger.debug(f"Searching for '{filename_part}' in {MOUNT_FOLDER}...")
    
    # Try exact match first in root
    try:
        if not MOUNT_FOLDER.exists():
            return None
            
        for f in MOUNT_FOLDER.glob("*"):
            if filename_part.lower() in f.name.lower():
                if f.is_file(): return f
                # If directory, look inside
                if f.is_dir():
                    for sub in f.rglob("*"):
                         if sub.is_file() and filename_part.lower() in sub.name.lower(): # Basic matching
                             # Avoid samples
                             if "sample" in sub.name.lower(): continue
                             # Prefer large video files
                             if sub.stat().st_size > 50 * 1024 * 1024: # > 50MB
                                 return sub
    except Exception as e:
        logger.error(f"Quick search error: {e}")
    
    # Deep search if not found quickly
    try:
        extensions = ['*.mkv', '*.mp4', '*.avi']
        for ext in extensions:
             for f in MOUNT_FOLDER.rglob(ext):
                 if filename_part.lower() in str(f).lower():
                     return f
    except Exception as e:
        logger.error(f"Deep search error: {e}")
        
    return None

def check_downloads():
    """Poll TorBox status and process completed downloads."""
    if not active_downloads:
        return

    try:
        headers = {"Authorization": f"Bearer {TORBOX_API_KEY}"}
        resp = requests.get(USENET_LIST_URL, headers=headers, params={'bypass_cache': 'true'}, timeout=30)
        
        if resp.status_code == 429:
            logger.warning("Rate limited on status check. Skipping this poll.")
            return

        if resp.status_code != 200:
            logger.error(f"Failed to list downloads: {resp.status_code}")
            return
            
        data = resp.json()
        if not data.get('success'): return
        
        downloads_list = data.get('data', [])
        # Map by ID
        current_status = {str(d['id']): d for d in downloads_list}
        
        completed_ids = []
        
        for tb_id, info in active_downloads.items():
            remote = current_status.get(tb_id)
            if not remote:
                # Disappeared?
                info['attempts'] += 1
                if info['attempts'] > 10:
                    logger.warning(f"Download ID {tb_id} disappeared from TorBox list. Removing.")
                    completed_ids.append(tb_id)
                continue
            
            state = remote.get('download_state', '').lower()
            if state == 'completed' or state == 'downloaded': 
                # Download finished!
                logger.info(f"Download {info['name']} finished! Searching file...")
                
                search_name = info['name']
                found_path = find_file_in_mount(search_name)
                
                if not found_path:
                    found_path = find_file_in_mount(info['original_stem'])

                if found_path:
                    logger.info(f"Found file at: {found_path}")
                    
                    # Create Folder in Completed
                    # Use original stem to match what Sonarr expects? 
                    # Generally Sonarr matches folder name.
                    dest_folder = COMPLETED_DIR / info['original_stem']
                    dest_folder.mkdir(parents=True, exist_ok=True)
                    
                    # Symlink
                    dest_file = dest_folder / found_path.name
                    if dest_file.exists(): dest_file.unlink()
                    
                    try:
                        os.symlink(found_path, dest_file)
                        logger.info(f"Created symlink: {dest_file} -> {found_path}")
                        completed_ids.append(tb_id)
                    except Exception as e:
                        logger.error(f"Failed to symlink: {e}")
                else:
                    # Increment wait count? No, just wait indefinitely or until timeout
                    pass
            
            elif state == 'error' or state == 'failed':
                logger.error(f"Download {info['name']} failed on TorBox.")
                completed_ids.append(tb_id)
                
        # Cleanup completed
        for cid in completed_ids:
            active_downloads.pop(cid, None)
            
    except Exception as e:
        logger.error(f"Check loop error: {e}")

class NZBHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory: return
        path = Path(event.src_path)
        if path.suffix.lower() == '.nzb':
            time.sleep(1)
            # Try to upload
            if upload_nzb(path):
                try: path.unlink() 
                except: pass

def main():
    logger.info("Starting TorBox Usenet Automator (Rate-Limit Friendly)...")
    setup_directories()
    
    # Startup process existing
    for nzb in NZB_DIR.glob("*.nzb"):
        if upload_nzb(nzb):
            try: nzb.unlink()
            except: pass
        # Pause slightly between existing files to avoid burst rate limits
        time.sleep(2)
            
    # Watcher
    observer = Observer()
    observer.schedule(NZBHandler(), str(NZB_DIR), recursive=False)
    observer.start()
    
    try:
        while True:
            check_downloads()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
