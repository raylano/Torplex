"""
Filesystem Service
Handles symlink creation and media organization
"""
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

try:
    import PTN
except ImportError:
    PTN = None
    logger.warning("PTN not installed, falling back to regex matching")

from src.config import settings
from src.models import MediaItem, MediaType


class SymlinkService:
    """Service for creating and managing symlinks to mounted media"""
    
    def __init__(self):
        self.mount_path = Path(settings.mount_path)
        self.symlink_path = Path(settings.symlink_path)
        
        # Subfolders for different media types
        self.paths = {
            MediaType.MOVIE: self.symlink_path / "movies",
            MediaType.SHOW: self.symlink_path / "tvshows",
            MediaType.ANIME_MOVIE: self.symlink_path / "anime_movies",
            MediaType.ANIME_SHOW: self.symlink_path / "anime_shows",
        }
    
    def ensure_directories(self):
        """Create all required directories"""
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory: {path}")
    
    def find_file_in_mount(self, filename_pattern: str) -> Optional[Path]:
        """
        Search for a file in the mount path.
        Uses glob pattern matching.
        """
        if not self.mount_path.exists():
            logger.warning(f"Mount path does not exist: {self.mount_path}")
            return None
        
        # Search recursively
        matches = list(self.mount_path.rglob(f"*{filename_pattern}*"))
        
        if not matches:
            return None
        
        # Return largest file if multiple matches
        if len(matches) > 1:
            matches.sort(key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=True)
        
        return matches[0]
    
    def find_by_infohash(self, info_hash: str, title: str = None, year: int = None) -> Optional[Path]:
        """
        Find file by searching in mount.
        First tries to match by info hash, then falls back to title search.
        """
        # First try by hash (rarely works with Zurg)
        for subdir in ["movies", "shows", "anime", "__all__"]:
            search_path = self.mount_path / subdir
            if not search_path.exists():
                continue
            
            for item in search_path.iterdir():
                if info_hash.lower() in item.name.lower():
                    if item.is_file():
                        return item
                    elif item.is_dir():
                        video_files = self._find_video_files(item)
                        if video_files:
                            return video_files[0]
        
        # If title provided, search by title (with year for better matching)
        if title:
            return self.find_by_title(title, year)
        
        return None
    
    def find_by_title(self, title: str, year: Optional[int] = None) -> Optional[Path]:
        """
        Find file by searching for title in mount.
        Uses better matching - includes year and more keywords.
        """
        if not title:
            return None
        
        import re
        
        # Clean title - remove special chars and make lowercase
        clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower())
        words = clean_title.split()
        
        # Skip common words
        skip_words = {'the', 'a', 'an', 'and', 'of', 'in', 'on', 'at', 'to', 'for', 'is', 'it'}
        keywords = [w for w in words if w not in skip_words and len(w) > 2]
        
        if not keywords:
            keywords = words[:1] if words else []
        
        if not keywords:
            return None
        
        year_str = str(year) if year else None
        logger.info(f"Searching mount for: {keywords} (year: {year_str})")
        
        # Collect all matches with scores
        matches = []
        
        # Search all subdirs
        for subdir in ["movies", "shows", "anime", "__all__"]:
            search_path = self.mount_path / subdir
            if not search_path.exists():
                continue
            
            for item in search_path.iterdir():
                # Clean item name same way
                item_name_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', item.name.lower())
                
                # Check if at least first 2 important keywords are present
                min_keywords = keywords[:2] if len(keywords) > 1 else keywords
                if not all(kw in item_name_clean for kw in min_keywords):
                    continue
                
                # Calculate match score
                score = 0
                
                # +10 for each keyword match
                for kw in keywords:
                    if kw in item_name_clean:
                        score += 10
                
                # +50 for year match (critical for series like Harry Potter)
                if year_str and year_str in item.name:
                    score += 50
                
                # -20 penalty if year is wrong
                elif year:
                    year_match = re.search(r'(19|20)\d{2}', item.name)
                    if year_match and year_match.group() != year_str:
                        score -= 20
                
                if item.is_file():
                    matches.append((score, item, None))
                elif item.is_dir():
                    video_files = self._find_video_files(item)
                    if video_files:
                        matches.append((score, item, video_files[0]))
        
        if not matches:
            logger.warning(f"No match found for: {title} ({year})")
            return None
        
        # Sort by score (highest first) and return best match
        matches.sort(key=lambda x: x[0], reverse=True)
        best_score, best_folder, best_file = matches[0]
        
        logger.info(f"Found match: {best_folder.name} (score: {best_score})")
        return best_file if best_file else best_folder
    
    async def find_episode_in_torrent(self, torrent_name: str, season: int, episode: int, 
                              absolute_episode_number: Optional[int] = None) -> Optional[Path]:
        """
        Find specific episode file within a known torrent folder.
        Uses the stored torrent_name for direct path construction.
        Supports absolute episode numbering for Anime.
        """
        import re
        
        if not torrent_name:
            return None
        
        # Patterns to match episode numbers
        # IMPORTANT: Prevent matching S03E01E02 as S03E02 using negative lookbehind
        patterns = [
            rf'(?<![eE]\d)(?<![eE]\d\d)s0*{season}e0*{episode}(?![\d])',  # S1E1, S01E01, but NOT S03E01E02
            rf'(?<![xX]\d)(?<![xX]\d\d){season}x0*{episode}(?![\d])',      # 1x01
            rf's0*{season}\s*-\s*0*{episode}(?![\d])',  # S3 - 04 format (common in anime releases)
            # Anime specific patterns (when we are inside the torrent, we can be looser)
            rf'(?:e|ep|episode)\.?\s*0*{episode}\b', # Episode 001
            rf'(?:^|[\s\-\.\[\(])0*{episode}(?:[\s\-\.\]\)]|$)', # Standalone number: " 001 ", " 01 "
        ]
        
        # Add absolute numbering patterns if available
        if absolute_episode_number:
            logger.info(f"Using absolute episode number {absolute_episode_number} for matching")
            patterns.extend([
                rf'(?:e|ep|episode)\.?\s*0*{absolute_episode_number}\b',     # Episode 328
                rf'(?:^|[\s\-\.\[\(])0*{absolute_episode_number}(?:[\s\-\.\]\)]|$)', # " - 328 ", "[328]"
                rf'^{absolute_episode_number}\b', # Starts with 328 (e.g. "328 - Title.mkv")
            ])
        
        logger.info(f"Searching for S{season:02d}E{episode:02d} (Abs: {absolute_episode_number}) in torrent: {torrent_name}")
        
        video_exts = {'.mkv', '.mp4', '.avi', '.mov', '.m4v'}
        found_files = []
        
        # Search in standard mount locations
        search_locations = ["__all__", "shows", "anime"]
        
        # Normalize torrent name for fuzzy matching
        def normalize(name: str) -> str:
            """Normalize name for matching - lowercase, remove special chars"""
            import unicodedata
            # Normalize unicode characters
            normalized = unicodedata.normalize('NFKD', name.lower())
            # Keep only alphanumeric and spaces
            return re.sub(r'[^a-z0-9\s]', '', normalized)
        
        torrent_norm = normalize(torrent_name)
        torrent_words = set(torrent_norm.split())
        
        for subdir in search_locations:
            subdir_path = self.mount_path / subdir
            if not subdir_path.exists():
                continue
            
            # First try: exact match
            path = subdir_path / torrent_name
            
            # FORCE REFRESH: Zurg/Rclone sometimes returns cached empty listings.
            # Explicitly listing the parent directory forces a kernel/fuse refresh.
            try:
                # This listing creates fs noise but ensures the mount is fresh
                import asyncio
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: list(os.scandir(str(subdir_path))))
                
                if path.exists():
                     await loop.run_in_executor(None, lambda: list(os.scandir(str(path))))
            except Exception:
                pass

            # Second try: exact match without file extension (common case: torrent_name has .mkv but folder doesn't)
            if not path.exists():
                # Strip extension and try again
                torrent_base = torrent_name.rsplit('.', 1)[0] if '.' in torrent_name else torrent_name
                path_no_ext = subdir_path / torrent_base
                if path_no_ext.exists():
                    logger.debug(f"Found folder without extension: {path_no_ext.name}")
                    path = path_no_ext
            
            # Third try: fuzzy match if exact path doesn't exist
            if not path.exists():
                # Extract episode number from torrent_name for strict validation
                # This prevents matching "S3 - 04" when looking for "S3 - 06"
                episode_in_torrent = None
                ep_match = re.search(rf's0*{season}\s*[-_.\s]*\s*(?:e)?0*(\d+)', torrent_name.lower())
                if ep_match:
                    episode_in_torrent = int(ep_match.group(1))
                else:
                    # Try absolute episode number pattern for anime
                    ep_match = re.search(rf'-\s*0*(\d+)(?:\s|$|\.)', torrent_name)
                    if ep_match:
                        episode_in_torrent = int(ep_match.group(1))
                
                # Search for folders that match
                best_match = None
                best_score = 0
                
                try:
                    for item in subdir_path.iterdir():
                        if not item.is_dir():
                            continue
                        
                        item_norm = normalize(item.name)
                        item_words = set(item_norm.split())
                        
                        # CRITICAL: If we know the episode number, the folder SHOULD contain it,
                        # UNLESS it is a Season Pack folder (e.g. "Season 01")
                        if episode_in_torrent is not None:
                            # Check if folder contains this exact episode number
                            folder_ep = None
                            folder_ep_match = re.search(rf's0*{season}\s*[-_.\s]*\s*(?:e)?0*(\d+)', item.name.lower())
                            if folder_ep_match:
                                folder_ep = int(folder_ep_match.group(1))
                            else:
                                # Try absolute episode number for anime folders
                                folder_ep_match = re.search(rf'-\s*0*(\d+)(?:\s|$)', item.name)
                                if folder_ep_match:
                                    folder_ep = int(folder_ep_match.group(1))
                            
                            # If folder has episode number, it MUST match
                            if folder_ep is not None and folder_ep != episode_in_torrent:
                                continue
                                
                            # If folder has NO episode number, check if it's a Season Pack folder
                            # (matches "Season X", "Complete", "Batch", or just "Show Name S01")
                            if folder_ep is None:
                                is_season_pack = False
                                if re.search(rf'season\s*0*{season}', item.name.lower()):
                                    is_season_pack = True
                                elif re.search(rf's0*{season}\b(?!e)', item.name.lower()):
                                    is_season_pack = True
                                elif 'complete' in item.name.lower() or 'batch' in item.name.lower():
                                    is_season_pack = True
                                    
                                if not is_season_pack:
                                    # If not a season pack and no episode number, it's ambiguous. 
                                    # But we might still want to check it if word score is high.
                                    pass
                        
                        # Calculate word overlap score
                        if torrent_words and item_words:
                            common = len(torrent_words & item_words)
                            score = common / max(len(torrent_words), len(item_words))
                            
                            # Require at least 50% word match
                            if score > 0.5 and score > best_score:
                                best_match = item
                                best_score = score
                except Exception as e:
                    logger.debug(f"Error scanning {subdir_path}: {e}")
                
                if best_match:
                    logger.debug(f"Fuzzy matched '{torrent_name}' to '{best_match.name}' (score: {best_score:.2f})")
                    path = best_match
            
            if not path.exists():
                continue
            
            # CASE 1: Single-file torrent - the torrent_name IS the video file
            if path.is_file():
                if path.suffix.lower() in video_exts:
                    logger.info(f"Found single-file torrent: {path.name}")
                    # CRITICAL FIX for ANIME:
                    # If we scraped using absolute numbering (e.g. 1155) for S09E320, 
                    # the file will look like "One Piece - 1155.mkv".
                    # But our `patterns` are looking for S09E320.
                    # We need to be flexible: if it's a single file and we found it by exact name match 
                    # from the scraping result, we should TRUST it.
                    
                    # Try patterns first (safest)
                    filename_lower = path.name.lower()
                    for pattern in patterns:
                        if re.search(pattern, filename_lower, re.IGNORECASE):
                            logger.info(f"Single-file match (pattern): {path.name}")
                            return path
                    
                    # If patterns fail, check if the file contains the absolute episode number?
                    # Or just trust it because `path` comes from `torrent_name` which was selected by scraper.
                    logger.info(f"Single-file match (trusted source): {path.name}")
                    return path
                continue
            
            # CASE 2: Multi-file torrent - search inside the folder
            logger.info(f"Checking folder: {path}")
            try:
                # DEBUG: List all files to see what's actually there
                logger.debug(f"Listing contents of {path}...")
                all_files_count = 0
                for item in path.rglob("*"):
                    if item.is_file():
                        all_files_count += 1
                        logger.debug(f" - Found file: {item.name} (size: {item.stat().st_size} bytes)")
                
                if all_files_count == 0:
                    logger.warning(f"Total files found in {path}: 0 (Empty folder?)")

                for video_file in path.rglob("*"):
                    if not video_file.is_file():
                        continue
                    if video_file.suffix.lower() not in video_exts:
                        continue
                        
                    # EXPLICIT EXCLUSION: Skip "Movie" files when looking for regular episodes
                    # We are in find_episode_in_torrent, strictly looking for Show Episodes.
                    # Ignore "Movie" files even if torrent name implies it's a pack.
                    if "movie" in video_file.name.lower():
                        logger.debug(f"Skipping potential movie file: {video_file.name}")
                        continue
                        
                    found_files.append(video_file)
            except Exception as e:
                logger.error(f"Error listing files in {path}: {e}")

        if not found_files:
            logger.warning(f"No video files found in torrent folders for {torrent_name}")
            return None
            
        # Sort files by size (largest first) to prefer higher quality/main files over samples or low-res duplicates
        found_files.sort(key=lambda x: x.stat().st_size, reverse=True)
            
        logger.info(f"Found {len(found_files)} potential video files (sorted by size): {[f.name for f in found_files[:10]]}...")

        # Check for matches
        for file in found_files:
            filename_lower = file.name.lower()
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    logger.info(f"Match found: {file.name} with pattern {pattern}")
                    return file
        
        logger.debug(f"Episode S{season:02d}E{episode:02d} not found in {torrent_name}")
        return None
    
    async def find_episode(self, show_title: str, season: int, episode: int, 
                     alternative_titles: list = None,
                     absolute_episode_number: Optional[int] = None) -> Optional[Path]:
        """
        Find a specific episode file in the mount.
        Searches for S01E01/s01e01/1x01 patterns.
        Uses alternative titles for better matching.
        Supports absolute episode numbering for Anime.
        """
        import re
        
        # Build list of all titles to try
        titles_to_try = [show_title]
        if alternative_titles:
            titles_to_try.extend(alternative_titles)
        
        # STRICT patterns - must match EXACT season AND episode
        # This prevents S04E18 from matching S02E18 files!
        # IMPORTANT: Use negative lookbehind (?<!E\d) to prevent matching 
        # the second episode in double-episode files like S03E01E02
        strict_patterns = [
            rf'(?<![eE]\d)(?<![eE]\d\d)s0*{season}e0*{episode}(?![\d])',   # S03E02 but NOT part of S03E01E02
            rf'(?<![xX]\d)(?<![xX]\d\d){season}x{episode:02d}(?![\d])',     # 3x02 but not 3x01x02
            rf'season\s*{season}[^0-9]+episode\s*{episode}\b',  # Season 3 Episode 2
            rf's0*{season}\s*-\s*0*{episode}(?![\d])',  # S3 - 04 format (common in anime releases)
        ]
        
        # Fallback patterns for anime (STRICT - only use if folder clearly matches season)
        # These patterns only match episode number, so require extra validation
        # IMPORTANT: Patterns must NOT match numbers in quality strings like "DDP5 1 Atmos"
        anime_patterns = [
            rf'(?:e|ep|episode)\.?\s*0*{episode}(?!\d)',  # Episode 018 (requires 'e' prefix)
            rf'(?:^|\[)\s*0*{episode}(?:\s*\]|\s*-)',     # [018] or [18 - at START only
            rf'^\s*-?\s*0*{episode}\s*(?:\[|\-|$)',       # " - 18 " at start only
        ]
        
        # Add absolute numbering patterns if available
        absolute_patterns = []
        if absolute_episode_number:
            logger.info(f"Using absolute episode number {absolute_episode_number} for fallback search")
            absolute_patterns = [
                rf'(?:e|ep|episode)\.?\s*0*{absolute_episode_number}\b',     # Episode 328
                rf'(?:^|[\s\-\.\[\(])0*{absolute_episode_number}(?:[\s\-\.\]\)]|$)', # " - 328 ", "[328]"
                rf'^{absolute_episode_number}\b', # Starts with 328 (e.g. "328 - Title.mkv")
            ]
        
        logger.info(f"Searching for episode: {show_title} S{season:02d}E{episode:02d} (Abs: {absolute_episode_number})")
        if alternative_titles:
            logger.debug(f"Also trying alternative titles: {alternative_titles[:3]}...")
        
        matches = []
        
        for subdir in ["__all__", "shows", "anime"]:
            search_path = self.mount_path / subdir
            if not search_path.exists():
                continue
            
            # FORCE REFRESH: Explicitly list directory to update Zurg/fuse cache
            # Run in thread pool to avoid blocking the event loop
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                # Wrap the blocking I/O
                await loop.run_in_executor(None, lambda: list(os.scandir(str(search_path))))
            except Exception:
                pass

            for item in search_path.iterdir():
                item_name_lower = item.name.lower()
                
                # Use PTN to parse folder/file name and extract title
                title_match = False
                extracted_folder_title = None
                
                if PTN:
                    try:
                        parsed = PTN.parse(item.name)
                        extracted_folder_title = parsed.get('title', '').lower().strip()
                    except Exception as e:
                        logger.debug(f"PTN parse failed for {item.name}: {e}")
                
                # Normalize function for comparison
                def normalize(s):
                    return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()
                
                if extracted_folder_title:
                    # PTN extracted a title - use strict comparison
                    folder_title_norm = normalize(extracted_folder_title)
                    
                    for title in titles_to_try:
                        title_norm = normalize(title)
                        
                        # Exact match
                        if folder_title_norm == title_norm:
                            title_match = True
                            logger.debug(f"PTN exact match: '{extracted_folder_title}' == '{title}'")
                            break
                        
                        # One contains the other (for abbreviated titles like "MASHLE")
                        if folder_title_norm in title_norm or title_norm in folder_title_norm:
                            title_match = True
                            logger.debug(f"PTN substring match: '{extracted_folder_title}' ~ '{title}'")
                            break
                        
                        # Significant word overlap (at least 60% of words)
                        folder_words = set(folder_title_norm.split())
                        title_words_set = set(title_norm.split())
                        
                        # Remove short words (the, of, a, etc)
                        folder_words = {w for w in folder_words if len(w) > 2}
                        title_words_set = {w for w in title_words_set if len(w) > 2}
                        
                        if folder_words and title_words_set:
                            common = folder_words & title_words_set
                            min_words = min(len(folder_words), len(title_words_set))
                            
                            if len(common) >= min_words * 0.6:
                                title_match = True
                                logger.debug(f"PTN word overlap match: '{extracted_folder_title}' ~ '{title}' (common: {common})")
                                break
                else:
                    # PTN failed - fallback to strict word matching
                    clean_item = re.sub(r'[^a-zA-Z0-9\s]', ' ', item_name_lower)
                    clean_item_words = set(clean_item.split())
                    
                    for title in titles_to_try:
                        clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower())
                        title_words = [w for w in clean_title.split() if len(w) > 2]
                        
                        if not title_words:
                            if clean_title.strip() in clean_item:
                                title_match = True
                                break
                            continue
                        
                        # ALL significant title words must be present
                        if all(w in clean_item_words for w in title_words):
                            title_match = True
                            logger.debug(f"Word match: all words of '{title}' in '{item.name}'")
                            break

                if not title_match:
                    continue
                
                # Log which folder matched
                logger.debug(f"Folder matched: {item.name} for show: {show_title}")

                # Check if folder indicates a specific season (for anime patterns validation)
                folder_season = self._extract_season_from_name(item_name_lower)
                
                # Helper to validate filename also contains the show title
                def file_title_valid(filename: str) -> bool:
                    """
                    STRICT validation using PTN parser.
                    Parse the filename to extract the title, then compare with show title.
                    This prevents 'The.Middle.S07E02' from matching 'Game of Thrones'.
                    """
                    # Use PTN to parse the filename
                    if PTN:
                        try:
                            parsed = PTN.parse(filename)
                            extracted_title = parsed.get('title', '').lower().strip()
                            
                            if extracted_title:
                                # Normalize both titles for comparison
                                def normalize(s):
                                    return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()
                                
                                extracted_norm = normalize(extracted_title)
                                
                                for title in titles_to_try:
                                    title_norm = normalize(title)
                                    
                                    # Check for exact match or significant overlap
                                    if extracted_norm == title_norm:
                                        return True
                                    
                                    # Check if one contains the other (for abbreviated titles)
                                    if extracted_norm in title_norm or title_norm in extracted_norm:
                                        return True
                                    
                                    # Check significant word overlap (at least 50% of shorter title)
                                    ext_words = set(extracted_norm.split())
                                    title_words_set = set(title_norm.split())
                                    common = ext_words & title_words_set
                                    
                                    # Remove short words
                                    common = {w for w in common if len(w) > 2}
                                    min_words = min(len(ext_words), len(title_words_set))
                                    
                                    if min_words > 0 and len(common) >= min_words * 0.5:
                                        return True
                                
                                # No match found via PTN
                                return False
                        except Exception as e:
                            logger.debug(f"PTN parsing failed for {filename}: {e}")
                    
                    # Fallback to word matching if PTN fails
                    clean_fn = re.sub(r'[^a-zA-Z0-9\s]', ' ', filename.lower())
                    fn_words = set(clean_fn.split())
                    
                    for title in titles_to_try:
                        clean_t = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower())
                        t_words = [w for w in clean_t.split() if len(w) > 3]
                        
                        if not t_words:
                            continue
                        
                        matches_count = sum(1 for w in t_words if w in fn_words)
                        
                        if len(t_words) >= 2:
                            if matches_count >= 2:
                                return True
                        else:
                            if clean_fn.startswith(t_words[0]):
                                return True
                    
                    return False
                
                # Now check for episode match
                if item.is_file():
                    # For standalone files, require title in filename
                    if (self._file_matches_episode(item.name, season, episode, strict_patterns, anime_patterns, folder_season, absolute_patterns)
                            and file_title_valid(item.name)):
                        matches.append(item)
                            
                elif item.is_dir():
                    # CRITICAL: Even for files inside folders, we MUST validate title
                    # to prevent Game of Thrones matching The Middle files
                    try:
                        video_files = self._find_video_files(item)
                        for vf in video_files:
                            if self._file_matches_episode(vf.name, season, episode, strict_patterns, anime_patterns, folder_season, absolute_patterns):
                                # Check if filename contains title OR if folder is an EXACT season match
                                # (e.g., "My Hero Academia S04/" folder with "S04E01-Title.mkv" files)
                                folder_has_show_in_name = file_title_valid(item.name)
                                file_has_show_in_name = file_title_valid(vf.name)
                                
                                if folder_has_show_in_name or file_has_show_in_name:
                                    matches.append(vf)
                                else:
                                    logger.debug(f"Rejected {vf.name} - no title match in folder or file")
                    except Exception as e:
                        logger.error(f"Error scanning folder {item}: {e}")
        
        if not matches:
            logger.warning(f"No episode match for: {show_title} S{season:02d}E{episode:02d}")
            return None
        
        # Return largest match (most likely to be the correct quality)
        matches.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        logger.info(f"Found episode: {matches[0].name}")
        return matches[0]
    
    def _find_video_files(self, directory: Path) -> list[Path]:
        """Find video files in directory, sorted by size (largest first)"""
        video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.m4v'}
        
        video_files = [
            f for f in directory.rglob("*")
            if f.is_file() and f.suffix.lower() in video_extensions
        ]
        
        # Sort by size, largest first
        video_files.sort(key=lambda p: p.stat().st_size, reverse=True)
        
        return video_files
    
    def _extract_season_from_name(self, name: str) -> Optional[int]:
        """Extract season number from folder/file name, if present"""
        import re
        name_lower = name.lower()
        
        # "Season 2", "Season 02", "S02", "S2"
        match = re.search(r'season\s*0*(\d+)', name_lower)
        if match:
            return int(match.group(1))
        
        match = re.search(r'\bs0*(\d+)(?!e)', name_lower)  # S02 but not S02E01
        if match:
            return int(match.group(1))
        
        return None
    
    def _file_matches_episode(self, filename: str, target_season: int, target_episode: int,
                               strict_patterns: list, anime_patterns: list, 
                               folder_season: Optional[int],
                               absolute_patterns: list = None) -> bool:
        """
        Check if a filename matches the target season and episode.
        Uses strict patterns first, then anime patterns with season validation.
        Also checks absolute numbering patterns if provided.
        """
        import re
        filename_lower = filename.lower()
        
        # EXPLICIT EXCLUSION: Skip "Movie" files when looking for regular episodes
        # This prevents "One Piece Movie 02" from matching "Episode 2"
        if "movie" in filename_lower:
            # But wait, what if the episode title contains "Movie"? (Rare but possible)
            # Safe bet: start with exclusion.
            return False
        
        # First try strict patterns (they include season, so no extra check needed)
        for pattern in strict_patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                return True
        
        # Check absolute numbering patterns (High trust)
        if absolute_patterns:
            for pattern in absolute_patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    # Verify it doesn't look like a different season
                    # e.g. "S02 - 13" should NOT match absolute 13 (which is S01E13)
                    # But usually absolute number is unique.
                    return True
        
        # For anime patterns, we need to validate the season separately
        # because these patterns only match episode number
        for pattern in anime_patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                # Check if file explicitly has wrong season
                file_season = self._extract_season_from_filename(filename_lower)
                if file_season is not None:
                    # File has explicit season - must match!
                    if file_season == target_season:
                        return True
                    else:
                        continue  # Wrong season, skip this file
                
                # No explicit season in file - use folder season if available
                if folder_season is not None:
                    if folder_season == target_season:
                        return True
                    else:
                        continue  # Folder is for wrong season
                
                # No season info anywhere - only match for season 1
                if target_season == 1:
                    return True
        
        return False
    
    def _extract_season_from_filename(self, filename: str) -> Optional[int]:
        """Extract season from filename if explicitly present like S02E01"""
        import re
        match = re.search(r's0*(\d+)e\d+', filename.lower())
        if match:
            return int(match.group(1))
        
        match = re.search(r'(\d+)x\d+', filename.lower())
        if match:
            return int(match.group(1))
        
        return None
    
    def delete_symlinks_for_item(self, media_item: MediaItem) -> int:
        """
        Delete all symlinks created for a media item.
        Returns the number of deleted symlinks.
        """
        deleted_count = 0
        
        try:
            # Determine the directory where symlinks would be created
            dest_dir = self.paths.get(media_item.type, self.paths[MediaType.MOVIE])
            clean_name = self._clean_filename(media_item.title)
            
            # For movies, delete the single symlink
            if media_item.type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
                for ext in ['.mkv', '.mp4', '.avi', '.mov', '.m4v']:
                    if media_item.year:
                        symlink_path = dest_dir / f"{clean_name} ({media_item.year}){ext}"
                    else:
                        symlink_path = dest_dir / f"{clean_name}{ext}"
                    
                    if symlink_path.exists() and symlink_path.is_symlink():
                        symlink_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted symlink: {symlink_path}")
            
            # For TV shows, delete the entire show folder
            else:
                if media_item.year:
                    show_folder = dest_dir / f"{clean_name} ({media_item.year})"
                else:
                    show_folder = dest_dir / clean_name
                
                if show_folder.exists():
                    import shutil
                    # Count symlinks before deletion
                    for f in show_folder.rglob("*"):
                        if f.is_symlink():
                            deleted_count += 1
                    
                    shutil.rmtree(show_folder)
                    logger.info(f"Deleted show folder with {deleted_count} symlinks: {show_folder}")
        
        except Exception as e:
            logger.error(f"Error deleting symlinks for {media_item.title}: {e}")
        
        return deleted_count

    
    def create_symlink(
        self,
        media_item: MediaItem,
        source_path: Path,
        season: Optional[int] = None,
        episode: Optional[int] = None
    ) -> Tuple[bool, Optional[Path]]:
        """
        Create a symlink for a media item.
        Returns (success, symlink_path)
        """
        try:
            # Determine destination directory
            dest_dir = self.paths.get(media_item.type, self.paths[MediaType.MOVIE])
            
            # Generate clean filename
            clean_name = self._clean_filename(media_item.title)
            
            if media_item.type in [MediaType.SHOW, MediaType.ANIME_SHOW]:
                # TV Show structure: Show Name/Season XX/Show Name - SXXEXX.ext
                show_dir = dest_dir / f"{clean_name} ({media_item.year or 'Unknown'})"
                
                if season is not None:
                    season_dir = show_dir / f"Season {season:02d}"
                    season_dir.mkdir(parents=True, exist_ok=True)
                    
                    if episode is not None:
                        filename = f"{clean_name} - S{season:02d}E{episode:02d}{source_path.suffix}"
                        dest_path = season_dir / filename
                    else:
                        # Full season pack
                        dest_path = season_dir / source_path.name
                else:
                    show_dir.mkdir(parents=True, exist_ok=True)
                    dest_path = show_dir / source_path.name
            else:
                # Movie structure: Movie Name (Year)/Movie Name (Year).ext
                movie_dir = dest_dir / f"{clean_name} ({media_item.year or 'Unknown'})"
                movie_dir.mkdir(parents=True, exist_ok=True)
                
                filename = f"{clean_name} ({media_item.year or 'Unknown'}){source_path.suffix}"
                dest_path = movie_dir / filename
            
            # Remove existing symlink if present
            if dest_path.exists() or dest_path.is_symlink():
                dest_path.unlink()
            
            # Create symlink
            dest_path.symlink_to(source_path)
            
            logger.info(f"Created symlink: {dest_path} -> {source_path}")
            return True, dest_path
            
        except Exception as e:
            logger.error(f"Failed to create symlink: {e}")
            return False, None
    
    def _clean_filename(self, name: str) -> str:
        """Remove invalid characters from filename"""
        # Remove characters that are invalid in filenames
        clean = re.sub(r'[<>:"/\\|?*]', '', name)
        # Replace multiple spaces with single space
        clean = re.sub(r'\s+', ' ', clean)
        # Trim whitespace
        clean = clean.strip()
        return clean
    
    def remove_symlink(self, symlink_path: Path) -> bool:
        """Remove a symlink"""
        try:
            if symlink_path.is_symlink():
                symlink_path.unlink()
                logger.info(f"Removed symlink: {symlink_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove symlink: {e}")
            return False
    
    def verify_mount(self) -> bool:
        """Check if mount is accessible and contains data"""
        if not self.mount_path.exists():
            return False
        
        # Check if mount has any content
        try:
            contents = list(self.mount_path.iterdir())
            return len(contents) > 0
        except Exception:
            return False


# Singleton instance
symlink_service = SymlinkService()
