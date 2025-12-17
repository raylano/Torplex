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
    
    def find_by_infohash(self, info_hash: str) -> Optional[Path]:
        """
        Find file by searching for info hash in mount.
        Zurg organizes files by torrent which often contains the hash.
        """
        # Search in typical Zurg structure
        for subdir in ["movies", "shows", "anime", "__all__"]:
            search_path = self.mount_path / subdir
            if not search_path.exists():
                continue
            
            # Look for directories/files containing the hash
            for item in search_path.iterdir():
                if info_hash.lower() in item.name.lower():
                    if item.is_file():
                        return item
                    elif item.is_dir():
                        # Find largest video file in directory
                        video_files = self._find_video_files(item)
                        if video_files:
                            return video_files[0]
        
        return None
    
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
