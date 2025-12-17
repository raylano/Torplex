"""
Torplex Torrent Models
Database models for torrent information and debrid cache status
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.media import MediaItem


class DebridProvider(str, Enum):
    """Supported debrid providers"""
    REAL_DEBRID = "real_debrid"
    TORBOX = "torbox"


class TorrentInfo(Base):
    """
    Torrent information found by scrapers.
    Tracks cache status on debrid providers.
    """
    __tablename__ = "torrents"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Link to media
    media_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("media_items.id"), nullable=False, index=True)
    media_item: Mapped["MediaItem"] = relationship("MediaItem", back_populates="torrents")
    
    # Torrent identification
    info_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    
    # Source info
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "torrentio", "prowlarr"
    indexer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "1337x", "RARBG"
    
    # Quality info
    resolution: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # e.g., "2160p", "1080p"
    quality: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., "BluRay", "WEB-DL"
    codec: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # e.g., "x265", "x264"
    audio: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "DTS-HD", "Atmos"
    
    # Anime-specific
    is_dual_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dubbed: Mapped[bool] = mapped_column(Boolean, default=False)
    release_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Size & Seeds
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    seeders: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Cache status per provider
    cached_on: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)  # ["real_debrid", "torbox"]
    selected_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    debrid_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ID on debrid service
    
    # Ranking
    rank_score: Mapped[int] = mapped_column(Integer, default=0)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<TorrentInfo(hash={self.info_hash[:8]}..., title='{self.title[:50]}...', cached={self.cached_on})>"
    
    @property
    def size_gb(self) -> Optional[float]:
        """Size in gigabytes"""
        if self.size_bytes:
            return round(self.size_bytes / (1024 ** 3), 2)
        return None
    
    @property
    def is_cached(self) -> bool:
        """True if cached on any provider"""
        return bool(self.cached_on)


class DebridDownload(Base):
    """
    Active downloads on debrid services.
    Tracks download progress and file availability.
    """
    __tablename__ = "debrid_downloads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Provider info
    provider: Mapped[DebridProvider] = mapped_column(String(20), nullable=False)
    debrid_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Torrent reference
    info_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "downloading", "downloaded", "error"
    progress: Mapped[float] = mapped_column(default=0.0)
    
    # File info
    filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    download_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<DebridDownload(provider={self.provider}, status={self.status}, progress={self.progress}%)>"
