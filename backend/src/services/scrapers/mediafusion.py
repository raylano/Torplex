"""
MediaFusion Scraper Service
Fetches torrent streams from MediaFusion Stremio addon
"""
import httpx
import re
from typing import List, Optional
from loguru import logger
from dataclasses import dataclass

from src.config import settings
from src.services.scrapers.torrentio import TorrentResult


class MediaFusionScraper:
    """Scraper for MediaFusion Stremio addon"""
    
    # Default public instance
    BASE_URL = "https://mediafusion.elfhosted.com"
    
    # Patterns for parsing
    RESOLUTION_PATTERN = re.compile(r'(2160p|1080p|720p|480p|4K|UHD)', re.IGNORECASE)
    QUALITY_PATTERN = re.compile(r'(BluRay|BDRip|BRRip|WEB-DL|WEBRip|HDTV|HDRip|DVDRip|REMUX)', re.IGNORECASE)
    CODEC_PATTERN = re.compile(r'(x265|x264|HEVC|H\.?265|H\.?264|AV1|VP9)', re.IGNORECASE)
    SIZE_PATTERN = re.compile(r'(\d+\.?\d*)\s*(GB|MB|TB)', re.IGNORECASE)
    SEEDERS_PATTERN = re.compile(r'👤\s*(\d+)')
    DUAL_AUDIO_PATTERN = re.compile(r'(dual[\s\-_]?audio|multi[\s\-_]?audio)', re.IGNORECASE)
    DUBBED_PATTERN = re.compile(r'(dubbed|dub|english\s*dub)', re.IGNORECASE)
    RELEASE_GROUP_PATTERN = re.compile(r'\[([^\]]+)\]')
    
    def __init__(self, custom_url: Optional[str] = None):
        self.url = (custom_url or getattr(settings, 'mediafusion_url', None) or self.BASE_URL).rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def is_configured(self) -> bool:
        """MediaFusion is always available via public instance"""
        return True
    
    async def scrape_movie(self, imdb_id: str) -> List[TorrentResult]:
        """Scrape torrents for a movie"""
        if not imdb_id:
            return []
        
        url = f"{self.url}/stream/movie/{imdb_id}.json"
        return await self._fetch_and_parse(url)
    
    async def scrape_episode(self, imdb_id: str, season: int, episode: int) -> List[TorrentResult]:
        """Scrape torrents for a TV episode"""
        if not imdb_id:
            return []
        
        url = f"{self.url}/stream/series/{imdb_id}:{season}:{episode}.json"
        return await self._fetch_and_parse(url)
    
    async def _fetch_and_parse(self, url: str) -> List[TorrentResult]:
        """Fetch streams from MediaFusion and parse results"""
        try:
            response = await self.client.get(url)
            
            if response.status_code == 404:
                logger.debug(f"MediaFusion: No streams found at {url}")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            streams = data.get("streams", [])
            results = []
            
            for stream in streams:
                result = self._parse_stream(stream)
                if result:
                    results.append(result)
            
            if results:
                logger.info(f"MediaFusion found {len(results)} streams")
            return results
            
        except httpx.HTTPStatusError as e:
            logger.debug(f"MediaFusion HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.debug(f"MediaFusion scrape failed: {e}")
            return []
    
    def _parse_stream(self, stream: dict) -> Optional[TorrentResult]:
        """Parse a single stream object"""
        # MediaFusion uses infoHash directly
        info_hash = stream.get("infoHash")
        
        # Some streams use behaviorHints
        if not info_hash:
            hints = stream.get("behaviorHints", {})
            info_hash = hints.get("infoHash")
        
        if not info_hash:
            return None
        
        # Get title from name or description
        full_title = stream.get("title", "") or stream.get("name", "")
        title = full_title.split("\n")[0].strip()
        
        if not title:
            return None
        
        # Parse quality info
        resolution = self._extract_pattern(title, self.RESOLUTION_PATTERN)
        quality = self._extract_pattern(title, self.QUALITY_PATTERN)
        codec = self._extract_pattern(title, self.CODEC_PATTERN)
        
        # Parse size
        size_bytes = self._parse_size(full_title)
        
        # Parse seeders
        seeders = None
        seeders_match = self.SEEDERS_PATTERN.search(full_title)
        if seeders_match:
            seeders = int(seeders_match.group(1))
        
        # Anime-specific parsing
        is_dual_audio = bool(self.DUAL_AUDIO_PATTERN.search(title))
        is_dubbed = bool(self.DUBBED_PATTERN.search(title))
        
        # Release group
        release_group = None
        group_match = self.RELEASE_GROUP_PATTERN.search(title)
        if group_match:
            release_group = group_match.group(1)
        
        return TorrentResult(
            info_hash=info_hash.lower(),
            title=title,
            source="mediafusion",
            indexer=None,
            resolution=resolution,
            quality=quality,
            codec=codec,
            size_bytes=size_bytes,
            seeders=seeders,
            is_dual_audio=is_dual_audio,
            is_dubbed=is_dubbed,
            release_group=release_group,
        )
    
    def _extract_pattern(self, text: str, pattern: re.Pattern) -> Optional[str]:
        """Extract first match from pattern"""
        match = pattern.search(text)
        return match.group(1) if match else None
    
    def _parse_size(self, text: str) -> Optional[int]:
        """Parse size string to bytes"""
        match = self.SIZE_PATTERN.search(text)
        if not match:
            return None
        
        value = float(match.group(1))
        unit = match.group(2).upper()
        
        multipliers = {
            "TB": 1024 ** 4,
            "GB": 1024 ** 3,
            "MB": 1024 ** 2,
        }
        
        return int(value * multipliers.get(unit, 1))
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
mediafusion_scraper = MediaFusionScraper()
