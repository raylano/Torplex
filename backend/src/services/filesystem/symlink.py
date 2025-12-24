"""
Filesystem Service
Handles symlink creation and media organization
"""
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

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
    
    def find_episode_in_torrent(self, torrent_name: str, season: int, episode: int) -> Optional[Path]:
        """
        Find specific episode file within a known torrent folder.
        Uses the stored torrent_name for direct path construction.
        """
        import re
        
        if not torrent_name:
            return None
        
        # Patterns to match episode numbers
        # IMPORTANT: Prevent matching S03E01E02 as S03E02 using negative lookbehind
        patterns = [
            rf'(?<![eE]\d)(?<![eE]\d\d)s0*{season}e0*{episode}(?![\d])',  # S1E1, S01E01, but NOT S03E01E02
            rf'(?<![xX]\d)(?<![xX]\d\d){season}x0*{episode}(?![\d])',      # 1x01
            # Anime specific patterns (when we are inside the torrent, we can be looser)
            rf'(?:e|ep|episode)\.?\s*0*{episode}\b', # Episode 001
            rf'(?:^|[\s\-\.\[\(])0*{episode}(?:[\s\-\.\]\)]|$)', # Standalone number: " 001 ", " 01 "
        ]
        
        logger.info(f"Searching for S{season:02d}E{episode:02d} in torrent: {torrent_name}")
        
        video_exts = {'.mkv', '.mp4', '.avi', '.mov', '.m4v'}
        found_files = []
        
        # Search in standard mount locations
        search_locations = ["__all__", "shows", "anime"]
        
        for subdir in search_locations:
            path = self.mount_path / subdir / torrent_name
            
            if not path.exists():
                continue
            
            # CASE 1: Single-file torrent - the torrent_name IS the video file
            if path.is_file():
                if path.suffix.lower() in video_exts:
                    logger.info(f"Found single-file torrent: {path.name}")
                    # Check if this file matches the episode pattern
                    filename_lower = path.name.lower()
                    for pattern in patterns:
                        if re.search(pattern, filename_lower, re.IGNORECASE):
                            logger.info(f"Single-file match: {path.name}")
                            return path
                    # Even if pattern doesn't match exactly, the torrent was selected for this episode
                    # so return it (the scraper already determined this is the right file)
                    logger.info(f"Returning single-file torrent (trusted): {path.name}")
                    return path
                continue
            
            # CASE 2: Multi-file torrent - search inside the folder
            logger.info(f"Checking folder: {path}")
            try:
                for video_file in path.rglob("*"):
                    if not video_file.is_file():
                        continue
                    if video_file.suffix.lower() not in video_exts:
                        continue
                    found_files.append(video_file)
            except Exception as e:
                logger.error(f"Error listing files in {path}: {e}")

        if not found_files:
            logger.warning(f"No video files found in torrent folders for {torrent_name}")
            return None
            
        logger.info(f"Found {len(found_files)} potential video files: {[f.name for f in found_files]}")

        # Check for matches
        for file in found_files:
            filename_lower = file.name.lower()
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    logger.info(f"Match found: {file.name} with pattern {pattern}")
                    return file
        
        logger.debug(f"Episode S{season:02d}E{episode:02d} not found in {torrent_name}")
        return None
    
    def find_episode(self, show_title: str, season: int, episode: int, 
                     alternative_titles: list = None) -> Optional[Path]:
        """
        Find a specific episode file in the mount.
        Searches for S01E01/s01e01/1x01 patterns.
        Uses alternative titles for better matching.
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
        ]
        
        # Fallback patterns for anime (only use if folder clearly matches season)
        # These patterns only match episode number, so require extra validation
        anime_patterns = [
            rf'(?:e|ep|episode)\.?\s*0*{episode}\b', # Episode 018, Episode 18
            rf'(?:^|[\s\-\.\[\(])0*{episode}(?:[\s\-\.\]\)]|$)', # Standalone: " 018 ", "[18]"
            rf' - 0*{episode}(?:\s|\.|$)',        # " - 18 " common in anime
        ]
        
        logger.info(f"Searching for episode: {show_title} S{season:02d}E{episode:02d}")
        if alternative_titles:
            logger.debug(f"Also trying alternative titles: {alternative_titles[:3]}...")
        
        matches = []
        
        for subdir in ["__all__", "shows", "anime"]:
            search_path = self.mount_path / subdir
            if not search_path.exists():
                continue
            
            for item in search_path.iterdir():
                item_name_lower = item.name.lower()
                clean_item = re.sub(r'[^a-zA-Z0-9\s]', ' ', item_name_lower)
                
                # Check if ANY of our titles matches the folder/file
                title_match = False
                for title in titles_to_try:
                    clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower())
                    title_words = [w for w in clean_title.split() if len(w) > 2][:3]
                    
                    if title_words:
                        if all(w in clean_item for w in title_words):
                            title_match = True
                            break
                    else:
                        if clean_title in clean_item:
                            title_match = True
                            break

                if not title_match:
                    continue

                # Check if folder indicates a specific season (for anime patterns validation)
                folder_season = self._extract_season_from_name(item_name_lower)
                
                # Now check for episode match
                if item.is_file():
                    if self._file_matches_episode(item.name, season, episode, strict_patterns, anime_patterns, folder_season):
                        matches.append(item)
                            
                elif item.is_dir():
                    try:
                        video_files = self._find_video_files(item)
                        for vf in video_files:
                            if self._file_matches_episode(vf.name, season, episode, strict_patterns, anime_patterns, folder_season):
                                matches.append(vf)
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
                               folder_season: Optional[int]) -> bool:
        """
        Check if a filename matches the target season and episode.
        Uses strict patterns first, then anime patterns with season validation.
        """
        import re
        filename_lower = filename.lower()
        
        # First try strict patterns (they include season, so no extra check needed)
        for pattern in strict_patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
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
