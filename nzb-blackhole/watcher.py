#!/usr/bin/env python3
"""
TorBox NZB Blackhole Watcher
Watches a folder for NZB files and uploads them to TorBox for usenet download.
"""

import os
import sys
import time
import logging
import requests
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration from environment
TORBOX_API_KEY = os.environ.get('TORBOX_API_KEY', '')
WATCH_FOLDER = os.environ.get('NZB_WATCH_FOLDER', '/data/nzb_watch')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '10'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# TorBox API endpoints
TORBOX_API_BASE = "https://api.torbox.app/v1/api"
TORBOX_USENET_UPLOAD = f"{TORBOX_API_BASE}/usenet/createusenetdownload"

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def upload_nzb_to_torbox(nzb_path: Path) -> bool:
    """Upload an NZB file to TorBox for usenet download."""
    if not TORBOX_API_KEY:
        logger.error("TORBOX_API_KEY not configured!")
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {TORBOX_API_KEY}"
        }
        
        with open(nzb_path, 'rb') as f:
            files = {
                'file': (nzb_path.name, f, 'application/x-nzb')
            }
            
            logger.info(f"Uploading NZB to TorBox: {nzb_path.name}")
            
            response = requests.post(
                TORBOX_USENET_UPLOAD,
                headers=headers,
                files=files,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    logger.info(f"Successfully uploaded: {nzb_path.name} -> TorBox ID: {data.get('data', {}).get('usenetdownload_id', 'unknown')}")
                    return True
                else:
                    logger.error(f"TorBox API error: {data.get('detail', 'Unknown error')}")
                    return False
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return False
                
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error uploading {nzb_path.name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error uploading {nzb_path.name}: {e}")
        return False


def process_existing_nzbs():
    """Process any NZB files that already exist in the watch folder."""
    watch_path = Path(WATCH_FOLDER)
    if not watch_path.exists():
        logger.warning(f"Watch folder does not exist: {WATCH_FOLDER}")
        return
    
    nzb_files = list(watch_path.glob('*.nzb'))
    if nzb_files:
        logger.info(f"Found {len(nzb_files)} existing NZB files to process")
        for nzb_path in nzb_files:
            if upload_nzb_to_torbox(nzb_path):
                # Move to processed folder or delete
                try:
                    nzb_path.unlink()
                    logger.info(f"Deleted processed NZB: {nzb_path.name}")
                except Exception as e:
                    logger.warning(f"Could not delete {nzb_path.name}: {e}")


class NZBHandler(FileSystemEventHandler):
    """Handle new NZB files dropped in watch folder."""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if file_path.suffix.lower() == '.nzb':
            # Wait a moment for file to be fully written
            time.sleep(1)
            
            if upload_nzb_to_torbox(file_path):
                try:
                    file_path.unlink()
                    logger.info(f"Deleted processed NZB: {file_path.name}")
                except Exception as e:
                    logger.warning(f"Could not delete {file_path.name}: {e}")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("TorBox NZB Blackhole Watcher")
    logger.info("=" * 60)
    logger.info(f"Watch folder: {WATCH_FOLDER}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"TorBox API: {'Configured' if TORBOX_API_KEY else 'NOT CONFIGURED!'}")
    logger.info("=" * 60)
    
    if not TORBOX_API_KEY:
        logger.error("TORBOX_API_KEY environment variable is required!")
        sys.exit(1)
    
    # Create watch folder if it doesn't exist
    watch_path = Path(WATCH_FOLDER)
    watch_path.mkdir(parents=True, exist_ok=True)
    
    # Process any existing NZB files
    process_existing_nzbs()
    
    # Setup file watcher
    event_handler = NZBHandler()
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=False)
    observer.start()
    
    logger.info("Watching for NZB files... Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(POLL_INTERVAL)
            # Periodic check for any missed files
            process_existing_nzbs()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        observer.stop()
    
    observer.join()
    logger.info("Goodbye!")


if __name__ == "__main__":
    main()
