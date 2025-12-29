"""
Prowlarr Scraper Service
Searches indexers configured in Prowlarr
"""
import httpx
import re
from typing import List, Optional
from loguru import logger

from src.config import settings
from src.services.scrapers.torrentio import TorrentResult


class ProwlarrScraper:
    """Scraper using Prowlarr as indexer aggregator"""
    
    # Patterns for parsing (reuse from torrentio)
    RESOLUTION_PATTERN = re.compile(r'(2160p|1080p|720p|480p|4K|UHD)', re.IGNORECASE)
    QUALITY_PATTERN = re.compile(r'(BluRay|BDRip|BRRip|WEB-DL|WEBRip|HDTV|HDRip|DVDRip|REMUX)', re.IGNORECASE)
    CODEC_PATTERN = re.compile(r'(x265|x264|HEVC|H\.?265|H\.?264|AV1|VP9)', re.IGNORECASE)
    DUAL_AUDIO_PATTERN = re.compile(r'(dual[\s\-_]?audio|multi[\s\-_]?audio)', re.IGNORECASE)
    DUBBED_PATTERN = re.compile(r'(dubbed|dub|english\s*dub)', re.IGNORECASE)
    RELEASE_GROUP_PATTERN = re.compile(r'\[([^\]]+)\]')
    
    def __init__(self):
        self.url = settings.prowlarr_url.rstrip("/")
        self.api_key = settings.prowlarr_api_key
        self.client = httpx.AsyncClient(timeout=60.0)
    
    @property
    def headers(self):
        return {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }
    
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def search(
        self,
        query: str,
        imdb_id: Optional[str] = None,
        categories: Optional[List[int]] = None
    ) -> List[TorrentResult]:
        """
        Search Prowlarr for torrents and NZBs.
        
        Categories:
        - 2000: Movies
        - 5000: TV
        - 5070: Anime
        - 8000: Other (often used for Usenet)
        """
        if not self.is_configured:
            logger.warning("Prowlarr API key not configured")
            return []
        
        try:
            # Build search params
            params = {
                "query": query,
                "type": "search",
            }
            
            if categories:
                # Add typical Usenet categories if generic movie/tv search
                if 2000 in categories and 5000 in categories:
                    # General search, include everything
                    pass 
                params["categories"] = categories
            
            url = f"{self.url}/api/v1/search"
            response = await self.client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            results = response.json()
            items = []
            
            for item in results:
                parsed_item = self._parse_result(item)
                if parsed_item:
                    items.append(parsed_item)
            
            logger.info(f"Prowlarr found {len(items)} results for '{query}'")
            return items
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Prowlarr HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Prowlarr search failed: {e}")
            return []

    def _parse_result(self, item: dict) -> Optional[TorrentResult]:
        """Parse Prowlarr search result to TorrentResult"""
        # Get identifier (Hash for torrent, GUID/URL for Usenet)
        info_hash = item.get("infoHash")
        magnet_url = item.get("magnetUrl", "")
        download_url = item.get("downloadUrl", "")
        guid = item.get("guid", "")
        
        # Determine if Usenet (no hash, but has download/guid)
        is_usenet = False
        
        # Extract hash from magnet if not provided
        if not info_hash and magnet_url:
            match = re.search(r'btih:([a-fA-F0-9]+)', magnet_url)
            if match:
                info_hash = match.group(1)
        
        # If no hash but has download URL (and protocol is Usenet or just no hash)
        if not info_hash and download_url:
            indexer_flags = item.get("indexerFlags", [])
            # Heuristic: If it has Usenet flag, or protocol is usenet, or just has downloadUrl and no hash
            # Prowlarr results usually have protocol field
            protocol = item.get("protocol")
            if protocol == "usenet" or not info_hash:
                is_usenet = True
        
        if not info_hash and not is_usenet:
            return None
            
        title = item.get("title", "")
        
        # Parse quality
        resolution = self._extract_pattern(title, self.RESOLUTION_PATTERN)
        quality = self._extract_pattern(title, self.QUALITY_PATTERN)
        codec = self._extract_pattern(title, self.CODEC_PATTERN)
        
        # Anime detection
        is_dual_audio = bool(self.DUAL_AUDIO_PATTERN.search(title))
        is_dubbed = bool(self.DUBBED_PATTERN.search(title))
        
        # Release group
        release_group = None
        group_match = self.RELEASE_GROUP_PATTERN.search(title)
        if group_match:
            release_group = group_match.group(1)
        
        return TorrentResult(
            info_hash=info_hash.lower() if info_hash else None,
            title=title,
            source="prowlarr",
            indexer=item.get("indexer"),
            resolution=resolution,
            quality=quality,
            codec=codec,
            size_bytes=item.get("size"),
            seeders=item.get("seeders") if not is_usenet else 100,  # Fake seeders for Usenet
            is_dual_audio=is_dual_audio,
            is_dubbed=is_dubbed,
            release_group=release_group,
            download_url=download_url,
            guid=guid,
            is_usenet=is_usenet
        )
    
    def _extract_pattern(self, text: str, pattern: re.Pattern) -> Optional[str]:
        """Extract first match from pattern"""
        match = pattern.search(text)
        return match.group(1) if match else None
    
    async def get_indexers(self) -> List[dict]:
        """Get list of configured indexers"""
        if not self.is_configured:
            return []
        
        try:
            url = f"{self.url}/api/v1/indexer"
            response = await self.client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get Prowlarr indexers: {e}")
            return []
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
prowlarr_scraper = ProwlarrScraper()
