"""
Torbox Downloader Service
Handles cache checking and torrent management on Torbox
"""
import httpx
from typing import Optional, List, Dict, Any
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings


class TorboxService:
    """Service for interacting with Torbox API"""
    
    BASE_URL = "https://api.torbox.app/v1/api"
    
    def __init__(self):
        self.api_key = settings.torbox_api_key
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
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Make request to Torbox API"""
        if not self.is_configured:
            logger.warning("Torbox API key not configured")
            return None
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = await self.client.request(
                method,
                url,
                headers=self.headers,
                data=data,
                params=params,
                json=json_data
            )
            
            if response.status_code == 401:
                logger.error("Torbox: Invalid API key")
                return None
            
            response.raise_for_status()
            
            result = response.json()
            
            # Torbox returns success/data structure
            if result.get("success"):
                return result.get("data", {})
            else:
                error = result.get("error", result.get("detail", "Unknown error"))
                logger.error(f"Torbox API error: {error}")
                return None
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Torbox API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Torbox request failed: {e}")
            return None
    
    async def get_user_info(self) -> Optional[Dict]:
        """Get user account info"""
        return await self._request("GET", "/user/me")
    
    async def check_instant_availability(self, info_hashes: List[str]) -> Dict[str, bool]:
        """
        Check if torrents are instantly available (cached).
        Returns dict mapping info_hash -> is_cached
        """
        if not info_hashes:
            return {}
        
        cached_status = {}
        
        # Torbox checks hashes one by one or in small batches
        for info_hash in info_hashes:
            result = await self._request(
                "GET",
                "/torrents/checkcached",
                params={"hash": info_hash.lower()}
            )
            
            # If result is truthy and contains the hash, it's cached
            if result and isinstance(result, list) and len(result) > 0:
                cached_status[info_hash.lower()] = True
            else:
                cached_status[info_hash.lower()] = False
        
        cached_count = sum(1 for v in cached_status.values() if v)
        logger.debug(f"Torbox: {cached_count}/{len(info_hashes)} torrents cached")
        
        return cached_status
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def add_magnet(self, info_hash: str, name: Optional[str] = None) -> Optional[int]:
        """
        Add magnet link to Torbox.
        Returns the torrent ID if successful.
        """
        magnet = f"magnet:?xt=urn:btih:{info_hash}"
        if name:
            magnet += f"&dn={name}"
        
        result = await self._request(
            "POST",
            "/torrents/createtorrent",
            data={"magnet": magnet}
        )
        
        if result and "torrent_id" in result:
            logger.info(f"Torbox: Added torrent {info_hash[:8]}... -> ID: {result['torrent_id']}")
            return result["torrent_id"]
        
        return None
    
    async def get_torrent_info(self, torrent_id: int) -> Optional[Dict]:
        """Get torrent info including files"""
        result = await self._request("GET", "/torrents/mylist", params={"id": torrent_id})
        return result
    
    async def get_torrents(self) -> List[Dict]:
        """Get list of user's torrents"""
        result = await self._request("GET", "/torrents/mylist")
        return result if result and isinstance(result, list) else []
    
    async def delete_torrent(self, torrent_id: int) -> bool:
        """Delete a torrent"""
        result = await self._request(
            "POST",
            "/torrents/controltorrent",
            data={"torrent_id": torrent_id, "operation": "delete"}
        )
        return result is not None
    
    async def get_download_link(self, torrent_id: int, file_id: Optional[int] = None) -> Optional[str]:
        """
        Get download/streaming link for a torrent file.
        """
        params = {"torrent_id": torrent_id, "token": self.api_key}
        if file_id:
            params["file_id"] = file_id
        
        result = await self._request("GET", "/torrents/requestdl", params=params)
        
        if result and isinstance(result, str):
            return result
        elif result and "url" in result:
            return result["url"]
        
        return None
    
    async def add_and_wait_for_ready(self, info_hash: str, name: Optional[str] = None) -> Optional[Dict]:
        """
        Add a cached torrent and return info when ready.
        """
        torrent_id = await self.add_magnet(info_hash, name)
        if not torrent_id:
            return None
        
        # Get torrent info
        info = await self.get_torrent_info(torrent_id)
        return info
    
    # ==========================================================================
    # USENET METHODS
    # ==========================================================================
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def add_usenet(self, link: str, name: Optional[str] = None) -> Optional[int]:
        """
        Add a usenet download from NZB link.
        Supports direct NZB URLs from indexers like NZBgeek, Spottarr, etc.
        Returns the usenet download ID if successful.
        """
        form_data = {"link": link}
        if name:
            form_data["name"] = name
        
        result = await self._request(
            "POST",
            "/usenet/createusenetdownload",
            data=form_data
        )
        
        if result and "usenetdownload_id" in result:
            logger.info(f"Torbox: Added usenet download -> ID: {result['usenetdownload_id']}")
            return result["usenetdownload_id"]
        
        # Handle alternative response format
        if result and "id" in result:
            logger.info(f"Torbox: Added usenet download -> ID: {result['id']}")
            return result["id"]
        
        return None
    
    async def get_usenet_info(self, usenet_id: int) -> Optional[Dict]:
        """Get usenet download info including files"""
        result = await self._request("GET", "/usenet/mylist", params={"id": usenet_id})
        return result
    
    async def get_usenet_list(self) -> List[Dict]:
        """Get list of user's usenet downloads"""
        result = await self._request("GET", "/usenet/mylist")
        return result if result and isinstance(result, list) else []
    
    async def delete_usenet(self, usenet_id: int) -> bool:
        """Delete a usenet download"""
        result = await self._request(
            "POST",
            "/usenet/controlusenetdownload",
            json_data={"usenet_id": usenet_id, "operation": "delete"}
        )
        return result is not None
    
    async def check_usenet_cached(self, hashes: List[str]) -> Dict[str, bool]:
        """
        Check if usenet downloads are cached on Torbox.
        Returns dict mapping hash -> is_cached
        """
        if not hashes:
            return {}
        
        cached_status = {}
        
        for hash_val in hashes:
            result = await self._request(
                "GET",
                "/usenet/checkcached",
                params={"hash": hash_val}
            )
            
            if result and isinstance(result, list) and len(result) > 0:
                cached_status[hash_val] = True
            else:
                cached_status[hash_val] = False
        
        cached_count = sum(1 for v in cached_status.values() if v)
        logger.debug(f"Torbox: {cached_count}/{len(hashes)} usenet downloads cached")
        
        return cached_status
    
    async def get_usenet_download_link(self, usenet_id: int, file_id: Optional[int] = None) -> Optional[str]:
        """
        Get download/streaming link for a usenet file.
        """
        params = {"usenet_id": usenet_id, "token": self.api_key}
        if file_id:
            params["file_id"] = file_id
        
        result = await self._request("GET", "/usenet/requestdl", params=params)
        
        if result and isinstance(result, str):
            return result
        elif result and "url" in result:
            return result["url"]
        
        return None
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
torbox_service = TorboxService()
