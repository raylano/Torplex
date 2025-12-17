"""
Multi-Scraper Service
Orchestrates multiple scraping sources with priority and fallback.
Torrentio (primary) -> Prowlarr (fallback)
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from src.clients.torrentio import TorrentioClient, TorrentioStream, get_torrentio_client
from src.clients.prowlarr import ProwlarrClient
from src.logic.rtn import TorrentParser, ParsedTorrent, Quality
from src.config import config


@dataclass
class ScrapedTorrent:
    """A scraped and parsed torrent ready for debrid check."""
    info_hash: str
    raw_title: str
    parsed: ParsedTorrent
    source: str  # "torrentio" or "prowlarr"
    seeders: int = 0
    size_bytes: int = 0
    magnet_link: Optional[str] = None


class MultiScraper:
    """
    Multi-source scraper with intelligent fallback.
    
    Priority:
    1. Torrentio (IMDB-based, more accurate)
    2. Prowlarr (text-based fallback)
    
    Features:
    - Parallel scraping when beneficial
    - RTN-based parsing and validation
    - Quality filtering
    - Deduplication by hash
    """
    
    def __init__(self):
        self.torrentio = get_torrentio_client()
        self.prowlarr = ProwlarrClient()
        self.parser = TorrentParser(
            quality_profile=config.get().quality_profile,
            allow_4k=config.get().allow_4k
        )
        
        # Check which services are available
        self.torrentio_available = self._check_torrentio()
        self.prowlarr_available = self._check_prowlarr()
        
        print(f"[Scraper] Torrentio: {'✓' if self.torrentio_available else '✗'}")
        print(f"[Scraper] Prowlarr: {'✓' if self.prowlarr_available else '✗'}")
    
    def _check_torrentio(self) -> bool:
        """Check if Torrentio is accessible."""
        try:
            return self.torrentio.validate()
        except:
            return False
    
    def _check_prowlarr(self) -> bool:
        """Check if Prowlarr is configured."""
        cfg = config.get()
        return bool(cfg.prowlarr_url and cfg.prowlarr_api_key)
    
    def scrape_movie(self, title: str, year: int, imdb_id: str = None) -> List[ScrapedTorrent]:
        """
        Scrape for a movie.
        
        Args:
            title: Movie title
            year: Release year
            imdb_id: IMDB ID if available (enables Torrentio)
            
        Returns:
            List of scraped torrents, ranked by quality
        """
        results = []
        
        # Try Torrentio first if we have IMDB ID
        if imdb_id and self.torrentio_available:
            print(f"[Scraper] Trying Torrentio for movie: {title} ({year})")
            torrentio_results = self._scrape_torrentio_movie(imdb_id, title, year)
            results.extend(torrentio_results)
        
        # Fallback to Prowlarr if no results or no IMDB ID
        if not results and self.prowlarr_available:
            print(f"[Scraper] Trying Prowlarr for movie: {title} ({year})")
            prowlarr_results = self._scrape_prowlarr_movie(title, year)
            results.extend(prowlarr_results)
        
        # Deduplicate by hash
        seen_hashes = set()
        unique_results = []
        for r in results:
            if r.info_hash not in seen_hashes:
                seen_hashes.add(r.info_hash)
                unique_results.append(r)
        
        # Sort by parsed rank
        unique_results.sort(key=lambda x: x.parsed.rank, reverse=True)
        
        print(f"[Scraper] Total: {len(unique_results)} unique torrents for {title}")
        return unique_results
    
    def scrape_episode(self, title: str, season: int, episode: int, 
                       year: int = None, imdb_id: str = None, is_anime: bool = False) -> List[ScrapedTorrent]:
        """
        Scrape for a TV episode.
        
        Args:
            title: Show title
            season: Season number
            episode: Episode number
            year: Show start year
            imdb_id: IMDB ID if available
            is_anime: Whether this is anime (affects search terms)
            
        Returns:
            List of scraped torrents, ranked by quality
        """
        results = []
        
        # Try Torrentio first if we have IMDB ID
        if imdb_id and self.torrentio_available:
            print(f"[Scraper] Trying Torrentio for: {title} S{season:02d}E{episode:02d}")
            torrentio_results = self._scrape_torrentio_episode(imdb_id, season, episode, title)
            results.extend(torrentio_results)
        
        # Fallback to Prowlarr
        if not results and self.prowlarr_available:
            print(f"[Scraper] Trying Prowlarr for: {title} S{season:02d}E{episode:02d}")
            prowlarr_results = self._scrape_prowlarr_episode(title, season, episode, is_anime)
            results.extend(prowlarr_results)
        
        # Deduplicate
        seen_hashes = set()
        unique_results = []
        for r in results:
            if r.info_hash not in seen_hashes:
                seen_hashes.add(r.info_hash)
                unique_results.append(r)
        
        # Sort by rank
        unique_results.sort(key=lambda x: x.parsed.rank, reverse=True)
        
        print(f"[Scraper] Total: {len(unique_results)} unique torrents for {title} S{season:02d}E{episode:02d}")
        return unique_results
    
    def _scrape_torrentio_movie(self, imdb_id: str, title: str, year: int) -> List[ScrapedTorrent]:
        """Scrape Torrentio for a movie."""
        results = []
        
        try:
            streams = self.torrentio.search_movie(imdb_id)
            
            for stream in streams:
                parsed = self.parser.parse(stream.title, stream.info_hash)
                
                # Validate for movie (no season/episode)
                if not self.parser.validate_for_movie(parsed):
                    continue
                
                # Quality filter
                if not self.parser.filter_by_quality(parsed):
                    continue
                
                results.append(ScrapedTorrent(
                    info_hash=stream.info_hash,
                    raw_title=stream.title,
                    parsed=parsed,
                    source="torrentio",
                    seeders=stream.seeders,
                    size_bytes=stream.size_bytes
                ))
        except Exception as e:
            print(f"[Scraper] Torrentio movie error: {e}")
        
        return results
    
    def _scrape_torrentio_episode(self, imdb_id: str, season: int, episode: int, title: str) -> List[ScrapedTorrent]:
        """Scrape Torrentio for an episode."""
        results = []
        
        try:
            streams = self.torrentio.search_episode(imdb_id, season, episode)
            
            for stream in streams:
                parsed = self.parser.parse(stream.title, stream.info_hash)
                
                # Validate for episode
                if not self.parser.validate_for_episode(parsed, season, episode):
                    continue
                
                # Quality filter
                if not self.parser.filter_by_quality(parsed):
                    continue
                
                results.append(ScrapedTorrent(
                    info_hash=stream.info_hash,
                    raw_title=stream.title,
                    parsed=parsed,
                    source="torrentio",
                    seeders=stream.seeders,
                    size_bytes=stream.size_bytes
                ))
        except Exception as e:
            print(f"[Scraper] Torrentio episode error: {e}")
        
        return results
    
    def _scrape_prowlarr_movie(self, title: str, year: int) -> List[ScrapedTorrent]:
        """Scrape Prowlarr for a movie."""
        results = []
        
        try:
            query = f"{title} {year}"
            search_results = self.prowlarr.search(query)
            
            # Phase 1: Filter candidates based on title (avoid expensive magnet fetch)
            candidates = []
            for item in search_results:
                raw_title = item.get('title', '')
                if not raw_title:
                    continue
                
                # Speculative parse without hash
                try:
                    parsed = self.parser.parse(raw_title, "")
                    if self.parser.validate_for_movie(parsed) and self.parser.filter_by_quality(parsed):
                        candidates.append((item, parsed))
                except Exception:
                    continue
            
            # Phase 2: Fetch magnets for top candidates in parallel
            # Sort by rank to prioritize best matches
            candidates.sort(key=lambda x: x[1].rank, reverse=True)
            top_candidates = [c[0] for c in candidates[:15]]
            
            def fetch_magnet(item):
                magnet, info_hash = self.prowlarr.get_magnet_from_result(item)
                if not info_hash:
                    return None
                
                raw_title = item.get('title', '')
                parsed = self.parser.parse(raw_title, info_hash)
                
                return ScrapedTorrent(
                    info_hash=info_hash,
                    raw_title=raw_title,
                    parsed=parsed,
                    source="prowlarr",
                    seeders=item.get('seeders', 0),
                    size_bytes=item.get('size', 0),
                    magnet_link=magnet
                )

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(fetch_magnet, item) for item in top_candidates]
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        if res:
                            results.append(res)
                    except Exception as e:
                        print(f"[Scraper] Error fetching magnet: {e}")

        except Exception as e:
            print(f"[Scraper] Prowlarr movie error: {e}")
        
        return results
    
    def _scrape_prowlarr_episode(self, title: str, season: int, episode: int, is_anime: bool) -> List[ScrapedTorrent]:
        """Scrape Prowlarr for an episode."""
        results = []
        
        try:
            # Build search query
            if is_anime:
                # Anime often uses absolute episode numbers
                query = f"{title} {episode:02d}"
            else:
                query = f"{title} S{season:02d}E{episode:02d}"
            
            search_results = self.prowlarr.search(query)
            
            # Phase 1: Filter candidates based on title
            candidates = []
            for item in search_results:
                raw_title = item.get('title', '')
                if not raw_title:
                    continue
                
                try:
                    parsed = self.parser.parse(raw_title, "")
                    if self.parser.validate_for_episode(parsed, season, episode) and self.parser.filter_by_quality(parsed):
                        candidates.append((item, parsed))
                except Exception:
                    continue
            
            # Phase 2: Fetch magnets for top candidates in parallel
            candidates.sort(key=lambda x: x[1].rank, reverse=True)
            top_candidates = [c[0] for c in candidates[:15]]
            
            def fetch_magnet(item):
                magnet, info_hash = self.prowlarr.get_magnet_from_result(item)
                if not info_hash:
                    return None
                
                raw_title = item.get('title', '')
                parsed = self.parser.parse(raw_title, info_hash)
                
                return ScrapedTorrent(
                    info_hash=info_hash,
                    raw_title=raw_title,
                    parsed=parsed,
                    source="prowlarr",
                    seeders=item.get('seeders', 0),
                    size_bytes=item.get('size', 0),
                    magnet_link=magnet
                )

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(fetch_magnet, item) for item in top_candidates]
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        if res:
                            results.append(res)
                    except Exception as e:
                        print(f"[Scraper] Error fetching magnet: {e}")

        except Exception as e:
            print(f"[Scraper] Prowlarr episode error: {e}")
        
        return results


# Singleton
_scraper: MultiScraper = None

def get_scraper() -> MultiScraper:
    """Get or create the scraper singleton."""
    global _scraper
    if _scraper is None:
        _scraper = MultiScraper()
    return _scraper
