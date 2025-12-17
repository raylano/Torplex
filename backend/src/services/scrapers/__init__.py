"""
Scrapers Package
"""
from src.services.scrapers.torrentio import torrentio_scraper, TorrentioScraper, TorrentResult
from src.services.scrapers.prowlarr import prowlarr_scraper, ProwlarrScraper

__all__ = [
    "torrentio_scraper",
    "TorrentioScraper",
    "TorrentResult",
    "prowlarr_scraper",
    "ProwlarrScraper",
]
