"""
Real-Debrid Downloader Service
Handles cache checking and torrent management on Real-Debrid
"""
import httpx
from typing import Optional, List, Dict, Any
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings


class RealDebridService:
    """Service for interacting with Real-Debrid API"""
    
    BASE_URL = "https://api.real-debrid.com/rest/1.0"
    
    def __init__(self):
        self.api_key = settings.real_debrid_token
        self.client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}
    
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Make request to Real-Debrid API"""
        if not self.is_configured:
            logger.warning("Real-Debrid API key not configured")
            return None
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = await self.client.request(
                method,
                url,
                headers=self.headers,
                data=data,
                params=params
            )
            
            if response.status_code == 401:
                logger.error("Real-Debrid: Invalid API key")
                return None
            
            response.raise_for_status()
            
            if response.text:
                return response.json()
            return {}
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Real-Debrid API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Real-Debrid request failed: {e}")
            return None
    
    async def get_user_info(self) -> Optional[Dict]:
        """Get user account info"""
        return await self._request("GET", "/user")
    
    async def check_instant_availability(self, info_hashes: List[str]) -> Dict[str, bool]:
        """
        Check if torrents are instantly available (cached).
        Returns dict mapping info_hash -> is_cached
        
        NOTE: Real-Debrid disabled this endpoint in 2024.
        We skip the check and just try to add torrents directly.
        Cached torrents will complete instantly anyway.
        """
        if not info_hashes:
            return {}
        
        # Skip cache check - endpoint disabled by Real-Debrid
        # All torrents will be tried, cached ones will complete instantly
        logger.debug(f"Skipping cache check (endpoint disabled) for {len(info_hashes)} hashes")
        return {h.lower(): False for h in info_hashes}

    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def add_magnet(self, info_hash: str) -> Optional[str]:
        """
        Add magnet link to Real-Debrid.
        Returns the torrent ID if successful.
        """
        magnet = f"magnet:?xt=urn:btih:{info_hash}"
        
        result = await self._request("POST", "/torrents/addMagnet", data={"magnet": magnet})
        
        if result and "id" in result:
            logger.info(f"Real-Debrid: Added torrent {info_hash[:8]}... -> ID: {result['id']}")
            return result["id"]
        
        return None
    
    async def get_torrent_info(self, torrent_id: str) -> Optional[Dict]:
        """Get torrent info including files"""
        return await self._request("GET", f"/torrents/info/{torrent_id}")
    
    async def select_files(self, torrent_id: str, file_ids: str = "all") -> bool:
        """
        Select files to download.
        file_ids: comma-separated list or "all"
        """
        result = await self._request(
            "POST",
            f"/torrents/selectFiles/{torrent_id}",
            data={"files": file_ids}
        )
        return result is not None
    
    async def get_torrents(self) -> List[Dict]:
        """Get list of user's torrents"""
        result = await self._request("GET", "/torrents")
        return result if result else []
    
    async def delete_torrent(self, torrent_id: str) -> bool:
        """Delete a torrent"""
        result = await self._request("DELETE", f"/torrents/delete/{torrent_id}")
        return result is not None
    
    async def unrestrict_link(self, link: str) -> Optional[Dict]:
        """
        Unrestrict a link to get direct download URL.
        Usually used for getting streaming links.
        """
        return await self._request("POST", "/unrestrict/link", data={"link": link})
    
    async def add_and_wait_for_cache(self, info_hash: str, timeout: int = 30) -> Optional[Dict]:
        """
        Add a cached torrent and wait for it to be ready.
        Returns torrent info with download links if successful.
        """
        torrent_id = await self.add_magnet(info_hash)
        if not torrent_id:
            return None
        
        # Get torrent info
        info = await self.get_torrent_info(torrent_id)
        if not info:
            return None
        
        # Select all files
        if info.get("status") == "waiting_files_selection":
            await self.select_files(torrent_id)
            info = await self.get_torrent_info(torrent_id)
        
        # For cached torrents, status should quickly become "downloaded"
        if info and info.get("status") == "downloaded":
            return info
        
        return info
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
real_debrid_service = RealDebridService()
