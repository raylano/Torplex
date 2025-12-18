"""
Torrentio Scraper Service
Fetches torrent streams from Torrentio (Stremio addon)
"""
import httpx
import re
from typing import List, Dict, Optional
from loguru import logger
from dataclasses import dataclass


@dataclass
class TorrentResult:
    """Parsed torrent result"""
    info_hash: str
    title: str
    source: str = "torrentio"
    indexer: Optional[str] = None
    resolution: Optional[str] = None
    quality: Optional[str] = None
    codec: Optional[str] = None
    size_bytes: Optional[int] = None
    seeders: Optional[int] = None
    is_dual_audio: bool = False
    is_dubbed: bool = False
    release_group: Optional[str] = None


class TorrentioScraper:
    """Scraper for Torrentio Stremio addon"""
    
    # Default Torrentio URL with good filters
    BASE_URL = "https://torrentio.strem.fun"
    
    # Quality filters - prioritize quality
    DEFAULT_FILTER = "sort=qualitysize|qualityfilter=480p,scr,cam"
    
    # Patterns for parsing
    RESOLUTION_PATTERN = re.compile(r'(2160p|1080p|720p|480p|4K|UHD)', re.IGNORECASE)
    QUALITY_PATTERN = re.compile(r'(BluRay|BDRip|BRRip|WEB-DL|WEBRip|HDTV|HDRip|DVDRip|REMUX)', re.IGNORECASE)
    CODEC_PATTERN = re.compile(r'(x265|x264|HEVC|H\.?265|H\.?264|AV1|VP9)', re.IGNORECASE)
    SIZE_PATTERN = re.compile(r'(\d+\.?\d*)\s*(GB|MB|TB)', re.IGNORECASE)
    SEEDERS_PATTERN = re.compile(r'👤\s*(\d+)')
    
    # Anime patterns - enhanced for better detection
    DUAL_AUDIO_PATTERN = re.compile(
        r'(dual[\s\-_]?audio|multi[\s\-_]?audio|japanese\s*\+\s*english|'
        r'eng?\s*\+\s*jap|jpn?\s*\+\s*eng|multi[\s\-_]?lang|'
        r'\b(eng|jpn|ita)\s+(eng|jpn|ita)\b)', 
        re.IGNORECASE
    )
    # Prioritize English dubbed releases
    DUBBED_PATTERN = re.compile(
        r'(\beng(lish)?\s*(dub|audio)|\bdub(bed)?\b|'
        r'english\s+dub|\bEMBER\b|\beng\s+audio|funimation)', 
        re.IGNORECASE
    )
    RELEASE_GROUP_PATTERN = re.compile(r'\[([^\]]+)\]')
    
    def __init__(self, custom_url: Optional[str] = None):
        self.url = custom_url or self.BASE_URL
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def scrape_movie(self, imdb_id: str) -> List[TorrentResult]:
        """Scrape torrents for a movie"""
        if not imdb_id:
            return []
        
        url = f"{self.url}/{self.DEFAULT_FILTER}/stream/movie/{imdb_id}.json"
        return await self._fetch_and_parse(url)
    
    async def scrape_episode(self, imdb_id: str, season: int, episode: int) -> List[TorrentResult]:
        """Scrape torrents for a TV episode"""
        if not imdb_id:
            return []
        
        url = f"{self.url}/{self.DEFAULT_FILTER}/stream/series/{imdb_id}:{season}:{episode}.json"
        return await self._fetch_and_parse(url)
    
    async def _fetch_and_parse(self, url: str) -> List[TorrentResult]:
        """Fetch streams from Torrentio and parse results"""
        try:
            response = await self.client.get(url)
            
            if response.status_code == 404:
                logger.debug(f"No streams found at {url}")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            streams = data.get("streams", [])
            results = []
            
            for stream in streams:
                result = self._parse_stream(stream)
                if result:
                    results.append(result)
            
            logger.info(f"Torrentio found {len(results)} streams")
            return results
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Torrentio HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Torrentio scrape failed: {e}")
            return []
    
    def _parse_stream(self, stream: Dict) -> Optional[TorrentResult]:
        """Parse a single stream object"""
        info_hash = stream.get("infoHash")
        if not info_hash:
            return None
        
        # Get raw title (first line before emoji separator)
        full_title = stream.get("title", "")
        title = full_title.split("\n")[0].strip()
        
        # Extract indexer from title (usually after a newline with emoji)
        indexer = None
        if "⚙️" in full_title:
            parts = full_title.split("⚙️")
            if len(parts) > 1:
                indexer = parts[1].split("\n")[0].strip()
        
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
        
        # Release group (usually in brackets)
        release_group = None
        group_match = self.RELEASE_GROUP_PATTERN.search(title)
        if group_match:
            release_group = group_match.group(1)
        
        return TorrentResult(
            info_hash=info_hash.lower(),
            title=title,
            source="torrentio",
            indexer=indexer,
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
torrentio_scraper = TorrentioScraper()
