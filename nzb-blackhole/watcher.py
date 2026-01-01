#!/usr/bin/env python3
"""
TorBox NZB Blackhole Watcher & Symlinker
Handles rate limiting aggressively and isolates failed files.
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
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '15')) # Increased default poll
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

TORBOX_API_BASE = "https://api.torbox.app/v1/api"
USENET_CREATE_URL = f"{TORBOX_API_BASE}/usenet/createusenetdownload"
USENET_LIST_URL = f"{TORBOX_API_BASE}/usenet/mylist"

# Folders
NZB_DIR = WATCH_FOLDER
COMPLETED_DIR = WATCH_FOLDER / "completed"
FAILED_DIR = WATCH_FOLDER / "failed"

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

active_downloads = {}

def setup_directories():
    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

def move_to_failed(nzb_path: Path):
    try:
        dest = FAILED_DIR / nzb_path.name
        shutil.move(str(nzb_path), str(dest))
        logger.info(f"Moved failed NZB to: {dest}")
    except Exception as e:
        logger.error(f"Could not move failed NZB: {e}")

def upload_nzb(nzb_path: Path):
    """Upload NZB to TorBox with aggressive rate limit handling."""
    if not TORBOX_API_KEY: return False
    
    max_retries = 3
    # If we hit rate limit, we pause GLOBALLY
    
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
                        tb_id = data.get('data', {}).get('usenetdownload_id')
                        name = data.get('data', {}).get('name', nzb_path.stem)
                        logger.info(f"SUCCESS: {nzb_path.name} -> ID: {tb_id}")
                        
                        if tb_id:
                            active_downloads[str(tb_id)] = {'name': name, 'original_stem': nzb_path.stem, 'attempts': 0}
                        
                        time.sleep(5) # Always wait 5s after success
                        return True
                    else:
                        detail = data.get('detail', '')
                        logger.error(f"API Error: {detail}")
                        if "limit" in detail.lower():
                             logger.warning("Soft rate limit in response. Sleeping 60s.")
                             time.sleep(60)
                             return False # Don't retry immediately, let main loop handle next time? 
                                          # Actually better to retry after sleep logic below
                        return False
                
                elif resp.status_code == 429:
                    logger.warning(f"RATE LIMIT (429). Pausing for 60 seconds...")
                    time.sleep(60)
                    continue # Retry current file
                else:
                    logger.error(f"HTTP Error {resp.status_code}: {resp.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
    
    # If we get here, all retries failed
    logger.error(f"Giving up on {nzb_path.name} after {max_retries} attempts.")
    move_to_failed(nzb_path)
    return False

def find_file_in_mount(filename_part: str) -> Path:
    # ... existing find logic ...
    # Simplified for brevity in tool call, copying logic is fine
    try:
        if not MOUNT_FOLDER.exists(): return None
        # Quick check
        for f in MOUNT_FOLDER.glob("*"):
            if filename_part.lower() in f.name.lower():
                if f.is_file(): return f
                if f.is_dir():
                    for sub in f.rglob("*"):
                         if sub.is_file() and filename_part.lower() in sub.name.lower(): 
                             if "sample" in sub.name.lower(): continue
                             if sub.stat().st_size > 50 * 1024 * 1024: return sub
    except Exception: pass
    
    # Deep search
    try:
        for ext in ['*.mkv', '*.mp4', '*.avi']:
             for f in MOUNT_FOLDER.rglob(ext):
                 if filename_part.lower() in str(f).lower(): return f
    except Exception: pass
    return None

def check_downloads():
    if not active_downloads: return

    try:
        headers = {"Authorization": f"Bearer {TORBOX_API_KEY}"}
        resp = requests.get(USENET_LIST_URL, headers=headers, params={'bypass_cache': 'true'}, timeout=30)
        
        if resp.status_code == 429:
            logger.warning("Rate limit checking status. Sleeping 60s.")
            time.sleep(60)
            return

        if resp.status_code != 200 or not resp.json().get('success'): return
        
        current_status = {str(d['id']): d for d in resp.json().get('data', [])}
        completed_ids = []
        
        for tb_id, info in active_downloads.items():
            remote = current_status.get(tb_id)
            if not remote:
                info['attempts'] += 1
                if info['attempts'] > 50: # Wait longer before giving up
                    completed_ids.append(tb_id)
                continue
            
            state = remote.get('download_state', '').lower()
            if state in ['completed', 'downloaded']: 
                logger.info(f"Download finished: {info['name']}")
                
                path = find_file_in_mount(info['name'])
                if not path: path = find_file_in_mount(info['original_stem'])

                if path:
                    dest_folder = COMPLETED_DIR / info['original_stem']
                    dest_folder.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_folder / path.name
                    if dest_file.exists(): dest_file.unlink()
                    try:
                        os.symlink(path, dest_file)
                        logger.info(f"Symlinked: {dest_file}")
                        completed_ids.append(tb_id)
                    except Exception as e: logger.error(f"Symlink failed: {e}")
            
            elif state in ['error', 'failed']:
                logger.error(f"Download failed: {info['name']}")
                completed_ids.append(tb_id)
                
        for cid in completed_ids:
            active_downloads.pop(cid, None)
            
    except Exception as e:
        logger.error(f"Check error: {e}")

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
    logger.info("Starting TorBox Usenet Automator (Aggressive Rate Handling)...")
    setup_directories()
    
    # Process existing sequentially with pauses
    nzbs = list(NZB_DIR.glob("*.nzb"))
    logger.info(f"Found {len(nzbs)} existing NZBs.")
    
    for nzb in nzbs:
        if upload_nzb(nzb):
            try: nzb.unlink()
            except: pass
        else:
            # If failed/rate limited, upload_nzb already handles retries/moves
            pass
        time.sleep(5) # Pause between files
            
    observer = Observer()
    observer.schedule(NZBHandler(), str(NZB_DIR), recursive=False)
    observer.start()
    
    try:
        while True:
            # Poll for new files (fallback for watchdog)
            for nzb in NZB_DIR.glob("*.nzb"):
                if upload_nzb(nzb):
                    try: nzb.unlink()
                    except: pass
                # Small pause to process
                time.sleep(2)

            check_downloads()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
