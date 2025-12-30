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
    
    async def search_movie(self, query: str, year: int = None, imdb_id: str = None) -> List[TorrentResult]:
        """Search for a movie"""
        # 2000 = Movies
        search_query = f"{query} {year}" if year else query
        return await self.search(search_query, categories=[2000], imdb_id=imdb_id)

    async def search_tv(self, title: str, season: int, episode: int, imdb_id: str = None) -> List[TorrentResult]:
        """
        Search for a TV episode.
        Includes heuristics for Anime Cour 2 mapping (e.g. S01E13 -> S02E01).
        """
        # 5000 = TV, 5070 = Anime
        categories = [5000, 5070]
        
        # Standard SxxExx search
        s_ex = f"S{season:02d}E{episode:02d}"
        query = f"{title} {s_ex}"
        
        results = await self.search(query, categories=categories, imdb_id=imdb_id)
        
        # ANIME FALLBACK LOGIC
        # If no results found, and it looks like a Cour 2 situation (Season 1, Ep > 12)
        if not results and season == 1 and episode > 12:
            logger.info(f"Prowlarr: No results for {s_ex}, trying Anime Cour 2 fallbacks...")
            
            # Fallback 1: Absolute Numbering (e.g. "Dan Da Dan 13")
            # We enforce 2+ digits padding
            abs_query = f"{title} {episode:02d}"
            logger.debug(f"Trying absolute search: {abs_query}")
            abs_results = await self.search(abs_query, categories=[5070], imdb_id=imdb_id)
            if abs_results:
                results.extend(abs_results)
            
            # Fallback 2: Cour 2 / Season 2 Mapping (e.g. S01E13 -> S02E01)
            # 13 -> 1, 14 -> 2, etc.
            s2_ep = episode - 12
            s2_query = f"{title} S02E{s2_ep:02d}"
            logger.debug(f"Trying S2 mapping: {s2_query}")
            s2_results = await self.search(s2_query, categories=[5070], imdb_id=imdb_id)
            if s2_results:
                results.extend(s2_results)
                
        return results
    
    async def search_movie(self, query: str, year: int = None, imdb_id: str = None) -> List[TorrentResult]:
        """Search for a movie"""
        # 2000 = Movies
        search_query = f"{query} {year}" if year else query
        return await self.search(search_query, categories=[2000], imdb_id=imdb_id)

    async def search_tv(
        self, 
        title: str, 
        season: int, 
        episode: int, 
        imdb_id: str = None,
        absolute_episode_number: int = None
    ) -> List[TorrentResult]:
        """
        Search for a TV episode sequentially across indexers.
        Includes heuristics for Anime Cour 2 mapping, Absolute Numbering, and early exit optimization.
        """
        # Get indexers first
        indexers = await self.get_indexers()
        
        if not indexers:
            logger.warning("No indexers configured in Prowlarr")
            return []
            
        # Sort by priority
        sorted_indexers = sorted(indexers, key=lambda x: x.get("priority", 25))
        
        all_results = []
        
        # We need to construct queries first
        queries = []
        
        # 1. Absolute Numbering (Highest Priority for Anime if known)
        if absolute_episode_number:
            logger.info(f"Prowlarr: Searching with Absolute Number {absolute_episode_number} for {title}")
            # Try specific "Title 145" format
            queries.append(f"{title} {absolute_episode_number:02d}")
            # Try "Title - 145" format
            queries.append(f"{title} - {absolute_episode_number:02d}")
        
        # 2. Standard SxxExx search
        s_ex = f"S{season:02d}E{episode:02d}"
        queries.append(f"{title} {s_ex}")
        
        # 3. Anime Fallback Logic pre-calculation (guessing if absolute num missing)
        is_anime_cour2 = season == 1 and episode > 12
        if is_anime_cour2 and not absolute_episode_number:
            # Absolute Numbering guess
            queries.append(f"{title} {episode:02d}")
            # Season 2 Mapping
            queries.append(f"{title} S02E{episode-12:02d}")
            
        # Categories: 5000 (TV), 5070 (Anime)
        categories = [5000, 5070]
        
        logger.info(f"Sequential Prowlarr Search: {len(sorted_indexers)} indexers, {len(queries)} queries")
        
        for indexer in sorted_indexers:
            indexer_id = indexer.get("id")
            indexer_name = indexer.get("name")
            
            layer_results = []
            
            for q in queries:
                try:
                    params = {
                        "query": q,
                        "type": "search",
                        "categories": categories,
                        "indexerIds": [indexer_id]
                    }
                    
                    url = f"{self.url}/api/v1/search"
                    resp = await self.client.get(url, headers=self.headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    for item in data:
                        res = self._parse_result(item)
                        if res:
                            layer_results.append(res)
                            
                except Exception as e:
                    logger.debug(f"Indexer {indexer_name} failed: {e}")
                    continue
            
            if not layer_results:
                continue
                
            all_results.extend(layer_results)
            
            # EARLY EXIT CHECK
            # Strict logic: "gebruik nogsteeds dubbel / english / dual audio als drijfveer"
            has_good_match = False
            for r in layer_results:
                if r.is_dual_audio or r.is_dubbed:
                    has_good_match = True
                    break
            
            if has_good_match:
                logger.info(f"Prowlarr: Found good match (Dub/Dual) on {indexer_name}, stopping sequential search.")
                return self._filter_results(all_results, season, episode, absolute_episode_number)
                
            if len(all_results) >= 10:
                logger.info(f"Prowlarr: Found {len(all_results)} results, stopping sequential search.")
                return self._filter_results(all_results, season, episode, absolute_episode_number)
                
        return self._filter_results(all_results, season, episode, absolute_episode_number)

    def _filter_results(self, results: List[TorrentResult], season: int, episode: int, absolute_number: Optional[int]) -> List[TorrentResult]:
        """Strictly filter results to ensure they match the requested episode"""
        filtered = []
        for r in results:
            if self._is_valid_match(r.title, season, episode, absolute_number):
                filtered.append(r)
            else:
                logger.debug(f"Prowlarr: Discarded invalid match: {r.title}")
        return filtered

    def _is_valid_match(self, title: str, season: int, episode: int, absolute_number: Optional[int]) -> bool:
        """Check if title strictly matches the target episode"""
        import re
        title_lower = title.lower()
        
        # 1. Absolute Number Check (Highest Priority)
        # MUST match the number as a whole word (e.g. "109" matches "109" but NOT "1097")
        if absolute_number:
            # Check for "109" bounded by non-digits
            if re.search(rf'(?<!\d){absolute_number}(?!\d)', title_lower):
                 return True
        
        # 2. Standard SxxExx Check
        # Must match S4E109, 4x109, etc.
        # Strict checking:
        if re.search(rf's0*{season}\s*e0*{episode}(?!\d)', title_lower):
            return True
        if re.search(rf'\b{season}x{episode:02d}\b', title_lower):
            return True
            
        # 3. Special Case: Anime Cour 2 (e.g. "Title 13" for S01E13)
        # Handled by absolute number check usually, but if absolute_number wasn't passed...
        
        return False
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
prowlarr_scraper = ProwlarrScraper()
