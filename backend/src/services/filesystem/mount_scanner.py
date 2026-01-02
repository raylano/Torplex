"""
Mount Scanner Service
Scans the rclone mount for existing media files and matches them to episodes.
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
import re
from loguru import logger

from src.config import settings


class MountScanner:
    """
    Scans mount for existing files BEFORE any scraping.
    Handles season packs, batch releases, and individual episodes.
    """
    
    def __init__(self):
        self.mount_path = Path(settings.mount_path)
        self.video_extensions = {'.mkv', '.mp4', '.avi', '.m4v', '.mov'}
    
    def find_matching_folders(self, show_title: str) -> List[Path]:
        """
        Find all folders that match a show title using PTN (Parse Torrent Name).
        This mimics 'Riven-style' matching by extracting the clean title from the folder first.
        """
        from difflib import SequenceMatcher
        import PTN
        
        folders = []
        # Normalize the requested show title (e.g. "Dan Da Dan" -> "dandadan")
        target_clean = self._normalize_title(show_title)
        
        # Ignored trash words
        ignore_words = {"sample", "extras", "featurettes"}
        
        for subdir in ["__all__", "anime", "shows"]:
            search_path = self.mount_path / subdir
            if not search_path.exists():
                continue
            
            try:
                for item in search_path.iterdir():
                    if not item.is_dir():
                        continue
                    
                    if item.name.lower() in ignore_words:
                        continue
                        
                    # 1. Parse the folder name to get the "release title"
                    # e.g. "Araiguma.Calcal-dan.S01E21..." -> title="Araiguma Calcal-dan"
                    parsed = PTN.parse(item.name)
                    folder_title_raw = parsed.get("title")
                    
                    if not folder_title_raw:
                        # Fallback if PTN fails: use the folder name excluding dots
                        folder_title_raw = item.name.replace(".", " ")
                    
                    # 2. Normalize the parsed title (e.g. "Araiguma Calcal-dan" -> "araigumacalcaldan")
                    folder_clean = self._normalize_title(folder_title_raw)
                    
                    # 3. Compare the CLEAN titles
                    # Now we compare "dandadan" vs "araigumacalcaldan" -> clearly NO match
                    if not folder_clean or not target_clean:
                        continue
                        
                    # Calculate similarity ratio
                    ratio = SequenceMatcher(None, target_clean, folder_clean).ratio()
                    
                    # Strict threshold (0.9) because we are comparing "clean vs clean" title
                    # Also allow startswith for "The Office" matching "The Office US" situations
                    if ratio > 0.85 or (len(target_clean) > 4 and folder_clean.startswith(target_clean)):
                        folders.append(item)
                        logger.debug(f"Matched folder: {item.name} | Parsed: '{folder_title_raw}' | Ratio: {ratio:.2f}")
                        
            except Exception as e:
                logger.error(f"Error scanning {search_path}: {e}")
        
        return folders
    
    def scan_folder_for_episodes(self, folder: Path) -> Dict[Tuple[int, int], Path]:
        """
        Scan a folder and extract episode mappings.
        Returns: {(season, episode): file_path}
        """
        episodes = {}
        
        try:
            for file in folder.rglob("*"):
                if not file.is_file():
                    continue
                if file.suffix.lower() not in self.video_extensions:
                    continue
                
                # Try to extract season/episode from filename
                se = self._extract_season_episode(file.name)
                if se:
                    season, episode = se
                    # Store mapping, prefer larger files (better quality)
                    key = (season, episode)
                    if key not in episodes or file.stat().st_size > episodes[key].stat().st_size:
                        episodes[key] = file
        except Exception as e:
            logger.error(f"Error scanning folder {folder}: {e}")
        
        return episodes
    
    def _extract_season_episode(self, filename: str) -> Optional[Tuple[int, int]]:
        """Extract S01E01 or absolute episode number from filename"""
        filename_lower = filename.lower()
        
        # Pattern 1: S01E001 or S1E1
        match = re.search(r's(\d{1,2})e(\d{1,4})', filename_lower)
        if match:
            return int(match.group(1)), int(match.group(2))
        
        # Pattern 2: 1x01
        match = re.search(r'(\d{1,2})x(\d{1,4})', filename_lower)
        if match:
            return int(match.group(1)), int(match.group(2))
        
        # Pattern 3: Season X ... Episode Y
        match = re.search(r'season\s*(\d+).*?episode\s*(\d+)', filename_lower)
        if match:
            return int(match.group(1)), int(match.group(2))
        
        # Pattern 4: Absolute numbering - " - 0001" or "[0001]" or ".0001."
        # Common in anime: "One Piece - 0837.mkv"
        match = re.search(r'(?:^|[\[\s\-\.])(\d{2,4})(?:[\]\s\.\-]|\.mkv|\.mp4|$)', filename_lower)
        if match:
            episode_num = int(match.group(1))
            # Sanity check: absolute numbers are usually > 0 and reasonable
            if 1 <= episode_num <= 9999:
                # For absolute numbering, we'll return season 1 and the absolute number
                # The caller can convert to proper season/episode if needed
                return 1, episode_num
        
        return None
    
    def find_all_episodes_for_show(self, show_title: str) -> Dict[Tuple[int, int], Path]:
        """
        Main entry point: Find ALL available episodes for a show.
        Searches all matching folders and aggregates results.
        """
        all_episodes = {}
        
        try:
            folders = self.find_matching_folders(show_title)
            
            if folders:
                logger.info(f"Found {len(folders)} potential folders for '{show_title}'")
            
            for folder in folders:
                folder_episodes = self.scan_folder_for_episodes(folder)
                
                if folder_episodes:
                    logger.info(f"  📁 {folder.name}: {len(folder_episodes)} episodes")
                
                # Merge results, preferring larger files
                for key, path in folder_episodes.items():
                    if key not in all_episodes:
                        all_episodes[key] = path
                    elif path.stat().st_size > all_episodes[key].stat().st_size:
                        all_episodes[key] = path
            
            if all_episodes:
                logger.success(f"Total: Found {len(all_episodes)} existing episodes for '{show_title}'")
                
        except Exception as e:
            logger.error(f"Error scanning mount for {show_title}: {e}")
        
        return all_episodes
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison"""
        # Remove special characters, convert to lowercase
        return re.sub(r'[^a-z0-9\s]', '', title.lower()).strip()
    
    def check_mount_available(self) -> bool:
        """Check if the mount is accessible"""
        try:
            all_folder = self.mount_path / "__all__"
            if all_folder.exists():
                # Try to list at least one item
                next(all_folder.iterdir(), None)
                return True
        except OSError as e:
            if e.errno == 107:  # Transport endpoint not connected
                logger.warning("Mount not available: Transport endpoint not connected")
            else:
                logger.error(f"Mount check failed: {e}")
        return False


# Singleton instance
mount_scanner = MountScanner()
