"""
Torplex Media Models
Database models for movies, shows, episodes, and their metadata
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class MediaType(str, Enum):
    """Type of media content"""
    MOVIE = "movie"
    SHOW = "show"
    ANIME_MOVIE = "anime_movie"
    ANIME_SHOW = "anime_show"


class ShowStatus(str, Enum):
    """Aggregate status for TV shows based on episode states"""
    PENDING = "pending"        # No episodes processed yet
    DOWNLOADING = "downloading" # Actively processing episodes
    PARTIAL = "partial"        # Some done, some failed/missing
    COMPLETED = "completed"    # All episodes symlinked
    RUNNING = "running"        # Complete but show still airing
    FAILED = "failed"          # All episodes failed


class MediaState(str, Enum):
    """State in the processing pipeline"""
    REQUESTED = "requested"      # Added to queue
    INDEXED = "indexed"          # Metadata fetched from TMDB
    SCRAPED = "scraped"          # Torrents found
    DOWNLOADING = "downloading"  # Being added to debrid
    DOWNLOADED = "downloaded"    # Available on debrid
    SYMLINKED = "symlinked"      # Symlink created
    COMPLETED = "completed"      # Visible in Plex
    FAILED = "failed"            # Processing failed
    PAUSED = "paused"            # Manually paused


class MediaItem(Base):
    """
    Main media item model.
    Can represent a movie or a TV show (parent of episodes).
    """
    __tablename__ = "media_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # External IDs
    imdb_id: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Basic Info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    alternative_titles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of aliases
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Type & State
    type: Mapped[MediaType] = mapped_column(String(20), nullable=False, index=True)
    state: Mapped[MediaState] = mapped_column(String(20), default=MediaState.REQUESTED, index=True)
    is_anime: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    # TMDB Metadata
    poster_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    backdrop_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    genres: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    vote_average: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    # TV Show specific
    number_of_seasons: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    number_of_episodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., "Returning Series"
    is_airing: Mapped[bool] = mapped_column(Boolean, default=False)  # True if show still releasing episodes
    
    # Processing info
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    symlink_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    episodes: Mapped[List["Episode"]] = relationship("Episode", back_populates="show", cascade="all, delete-orphan")
    torrents: Mapped[List["TorrentInfo"]] = relationship("TorrentInfo", back_populates="media_item", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MediaItem(id={self.id}, title='{self.title}', type={self.type}, state={self.state})>"
    
    @property
    def poster_url(self) -> Optional[str]:
        """Full TMDB poster URL"""
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w500{self.poster_path}"
        return None
    
    @property
    def backdrop_url(self) -> Optional[str]:
        """Full TMDB backdrop URL"""
        if self.backdrop_path:
            return f"https://image.tmdb.org/t/p/w1280{self.backdrop_path}"
        return None
    
    def compute_show_status(self) -> str:
        """
        Calculate aggregate show status from episode states.
        Only applicable for TV shows.
        """
        if self.type not in [MediaType.SHOW, MediaType.ANIME_SHOW]:
            return self.state.value if self.state else "unknown"
        
        if not self.episodes:
            return ShowStatus.PENDING.value
        
        completed = sum(1 for e in self.episodes if e.state == MediaState.COMPLETED)
        failed = sum(1 for e in self.episodes if e.state == MediaState.FAILED)
        total = len(self.episodes)
        
        if completed == total:
            return ShowStatus.RUNNING.value if self.is_airing else ShowStatus.COMPLETED.value
        elif completed > 0:
            return ShowStatus.PARTIAL.value
        elif failed == total:
            return ShowStatus.FAILED.value
        else:
            return ShowStatus.DOWNLOADING.value
    
    def get_episode_stats(self) -> dict:
        """Get episode statistics for API responses"""
        if not self.episodes:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0}
        
        completed = sum(1 for e in self.episodes if e.state == MediaState.COMPLETED)
        failed = sum(1 for e in self.episodes if e.state == MediaState.FAILED)
        pending = sum(1 for e in self.episodes if e.state not in [MediaState.COMPLETED, MediaState.FAILED])
        
        return {
            "total": len(self.episodes),
            "completed": completed,
            "failed": failed,
            "pending": pending
        }


class Episode(Base):
    """
    TV Show Episode model.
    Linked to a parent MediaItem (show).
    """
    __tablename__ = "episodes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Parent show
    show_id: Mapped[int] = mapped_column(Integer, ForeignKey("media_items.id"), nullable=False, index=True)
    show: Mapped["MediaItem"] = relationship("MediaItem", back_populates="episodes")
    
    # Episode info
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    air_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # State
    state: Mapped[MediaState] = mapped_column(String(20), default=MediaState.REQUESTED, index=True)
    
    # File info
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # info_hash or matched file
    symlink_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    torrent_name: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # Torrent folder name in mount
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Episode(show_id={self.show_id}, S{self.season_number:02d}E{self.episode_number:02d}, state={self.state})>"


# Import TorrentInfo from torrent.py to avoid circular imports
from src.models.torrent import TorrentInfo  # noqa: E402, F401
