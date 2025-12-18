"""
Zilean Service
Cache checking via Zilean (DMM hash database)
"""
import httpx
from typing import Optional, List, Dict
from loguru import logger

from src.config import settings


class ZileanService:
    """
    Service for checking torrent cache status via Zilean.
    Zilean indexes DMM (DebridMediaManager) shared hashes and can tell us if
    something is likely cached on Real-Debrid.
    """
    
    def __init__(self):
        self.base_url = getattr(settings, 'zilean_url', None)
        self.client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)
    
    async def check_hash(self, info_hash: str) -> bool:
        """
        Check if a single hash exists in Zilean (likely cached).
        """
        if not self.is_configured:
            return False
        
        try:
            response = await self.client.get(
                f"{self.base_url}/dmm/filtered",
                params={"query": info_hash}
            )
            
            if response.status_code == 200:
                data = response.json()
                # If we get results, the hash is known (likely cached)
                return len(data) > 0
            
        except Exception as e:
            logger.debug(f"Zilean check failed: {e}")
        
        return False
    
    async def check_hashes(self, info_hashes: List[str]) -> Dict[str, bool]:
        """
        Check multiple hashes against Zilean.
        Returns dict mapping hash -> is_cached
        """
        if not self.is_configured or not info_hashes:
            return {h: False for h in info_hashes}
        
        results = {}
        
        # Zilean doesn't have batch endpoint, so check each
        # (In production, you'd want to batch or use torznab search)
        for info_hash in info_hashes[:50]:  # Limit to 50
            results[info_hash.lower()] = await self.check_hash(info_hash)
        
        cached_count = sum(1 for v in results.values() if v)
        if cached_count > 0:
            logger.info(f"Zilean: {cached_count}/{len(info_hashes)} torrents in DMM database")
        
        return results
    
    async def search(self, query: str) -> List[Dict]:
        """
        Search Zilean for torrents by query.
        Returns list of torrent info dicts.
        """
        if not self.is_configured:
            return []
        
        try:
            response = await self.client.get(
                f"{self.base_url}/dmm/filtered",
                params={"query": query}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Zilean found {len(data)} results for: {query}")
                return data
                
        except Exception as e:
            logger.error(f"Zilean search failed: {e}")
        
        return []
    
    async def close(self):
        await self.client.aclose()


# Singleton
zilean_service = ZileanService()
