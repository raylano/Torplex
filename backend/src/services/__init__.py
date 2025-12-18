"""
Services Package
"""
from src.services.content import tmdb_service, plex_service
from src.services.scrapers import torrentio_scraper, prowlarr_scraper
from src.services.scrapers.zilean import zilean_service
from src.services.downloaders import real_debrid_service, torbox_service, downloader
from src.services.filesystem import symlink_service

__all__ = [
    # Content
    "tmdb_service",
    "plex_service",
    # Scrapers
    "torrentio_scraper",
    "prowlarr_scraper",
    "zilean_service",
    # Downloaders
    "real_debrid_service",
    "torbox_service",
    "downloader",
    # Filesystem
    "symlink_service",
]

