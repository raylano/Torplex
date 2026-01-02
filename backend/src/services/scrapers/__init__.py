"""
Scrapers Package
Provides unified scraping across Torrentio, Prowlarr, and MediaFusion.
"""
from typing import List, Optional
from loguru import logger

from src.services.scrapers.torrentio import torrentio_scraper, TorrentioScraper, TorrentResult
from src.services.scrapers.prowlarr import prowlarr_scraper, ProwlarrScraper
from src.services.scrapers.mediafusion import mediafusion_scraper, MediaFusionScraper


async def scrape_movie(imdb_id: str, title: str = "", year: int = None) -> List[TorrentResult]:
    """
    Scrape all sources for a movie.
    Returns deduplicated list of TorrentResults.
    """
    all_results = []
    
    # Torrentio (primary)
    try:
        results = await torrentio_scraper.scrape_movie(imdb_id)
        all_results.extend(results)
        logger.info(f"Torrentio found {len(results)} streams for movie")
    except Exception as e:
        logger.error(f"Torrentio scrape failed: {e}")
    
    # MediaFusion (secondary)
    try:
        results = await mediafusion_scraper.scrape_movie(imdb_id)
        all_results.extend(results)
        if results:
            logger.info(f"MediaFusion found {len(results)} streams for movie")
    except Exception as e:
        logger.debug(f"MediaFusion scrape failed: {e}")
    
    # Prowlarr (tertiary - if configured)
    if prowlarr_scraper.is_configured:
        try:
            query = f"{title} {year}" if year else title
            results = await prowlarr_scraper.search_movie(query, year=year, imdb_id=imdb_id)
            all_results.extend(results)
            if results:
                logger.info(f"Prowlarr found {len(results)} results for movie")
        except Exception as e:
            logger.debug(f"Prowlarr scrape failed: {e}")
    
    return _deduplicate(all_results)


async def scrape_episode(
    imdb_id: str, 
    season: int, 
    episode: int, 
    title: str = "",
    absolute_episode_number: int = None
) -> List[TorrentResult]:
    """
    Scrape all sources for a TV episode.
    Returns deduplicated list of TorrentResults.
    """
    all_results = []
    
    # Torrentio (primary)
    try:
        results = await torrentio_scraper.scrape_episode(imdb_id, season, episode)
        all_results.extend(results)
        logger.info(f"Torrentio found {len(results)} streams for S{season:02d}E{episode:02d}")
    except Exception as e:
        logger.error(f"Torrentio scrape failed: {e}")
    
    # MediaFusion (secondary)
    try:
        results = await mediafusion_scraper.scrape_episode(imdb_id, season, episode)
        all_results.extend(results)
        if results:
            logger.info(f"MediaFusion found {len(results)} streams for S{season:02d}E{episode:02d}")
    except Exception as e:
        logger.debug(f"MediaFusion scrape failed: {e}")
    
    # Prowlarr (tertiary - if configured)
    if prowlarr_scraper.is_configured:
        try:
            results = await prowlarr_scraper.search_tv(
                title, 
                season=season, 
                episode=episode, 
                imdb_id=imdb_id,
                absolute_episode_number=absolute_episode_number
            )
            all_results.extend(results)
            if results:
                logger.info(f"Prowlarr found {len(results)} results for S{season:02d}E{episode:02d}")
        except Exception as e:
            logger.debug(f"Prowlarr scrape failed: {e}")
    
    return _deduplicate(all_results)


def _deduplicate(results: List[TorrentResult]) -> List[TorrentResult]:
    """Remove duplicate torrents based on info_hash, keeping first occurrence"""
    seen = set()
    unique = []
    for r in results:
        # Handle items without info_hash (e.g. Usenet)
        if not r.info_hash:
            # We can't deduplicate by hash, so we check download_url or just keep it
            # For now, let's just keep them (safer than dropping)
            unique.append(r)
            continue
            
        if r.info_hash.lower() not in seen:
            seen.add(r.info_hash.lower())
            unique.append(r)
    return unique


__all__ = [
    # Scrapers
    "torrentio_scraper",
    "TorrentioScraper",
    "TorrentResult",
    "prowlarr_scraper",
    "ProwlarrScraper",
    "mediafusion_scraper",
    "MediaFusionScraper",
    # Aggregator functions
    "scrape_movie",
    "scrape_episode",
]
