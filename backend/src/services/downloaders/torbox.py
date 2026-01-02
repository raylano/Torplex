"""
Torbox Downloader Service
Handles cache checking and torrent management on Torbox
"""
import httpx
from typing import Optional, List, Dict, Any
from loguru import logger
import httpx # Still needed for downloading NZB from Prowlarr
from tenacity import retry, stop_after_attempt, wait_exponential
import aiohttp # Needed for FormData in add_usenet

from src.config import settings
from src.services.api.client import RateLimitedClient


class TorboxService(RateLimitedClient):
    """
    Service for interacting with Torbox API.
    Inherits concurrency limiting and backoff logic from RateLimitedClient.
    """
    
    BASE_URL = "https://api.torbox.app/v1/api"
    
    def __init__(self):
        self.api_key = settings.torbox_api_key
        # Initialize RateLimitedClient with name and concurrency limit
        # Torbox limit is usually strict -> limit to 2 concurrent requests
        super().__init__(name="Torbox", max_concurrent=2, base_url=self.BASE_URL)
    
    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}
    
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def _request_api(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None, # For form data (aiohttp)
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None, # For JSON body (aiohttp)
        form_data: Optional[aiohttp.FormData] = None # For multipart form data (aiohttp)
    ) -> Optional[Any]:
        """Wrapper for RateLimitedClient.request with Torbox-specific error handling"""
        if not self.is_configured:
            logger.warning("Torbox API key not configured")
            return None
            
        try:
            # Prepare headers
            req_headers = self.headers.copy()
            
            # Prepare args for aiohttp
            # aiohttp uses 'json' for json body, 'data' for form/multipart
            kwargs = {"headers": req_headers, "params": params}
            if json_data:
                kwargs["json"] = json_data
            if data: # For simple form-urlencoded data
                kwargs["data"] = data
            if form_data: # For aiohttp.FormData (multipart)
                kwargs["data"] = form_data
                
            response_data = await self.request(method, endpoint, **kwargs)
            
            if response_data is None: # RateLimitedClient.request returns None on HTTP errors
                return None
                
            # Torbox returns {'success': ..., 'data': ...} or {'detail': ...} for errors
            # RateLimitedClient already parses JSON
            
            # If it's a list (some endpoints return raw lists?) check first item
            if isinstance(response_data, list):
                return response_data
                
            if isinstance(response_data, dict):
                # Handle API-level errors (200 OK but success: false)
                if response_data.get("success") is False:
                    error = response_data.get("error", response_data.get("detail", "Unknown error"))
                    logger.error(f"Torbox API logical error: {error}")
                    return None
                    
                # Return 'data' field if present, otherwise the whole dict
                return response_data.get("data", response_data)
                
            return response_data

        except Exception as e:
            logger.error(f"Torbox request failed: {e}")
            return None
    
    async def get_user_info(self) -> Optional[Dict]:
        """Get user account info"""
        return await self._request_api("GET", "/user/me")
    
    async def check_instant_availability(self, info_hashes: List[str]) -> Dict[str, bool]:
        """Check if torrents are instantly available (cached)."""
        if not info_hashes:
            return {}
        
        cached_status = {}
        for info_hash in info_hashes:
            # This is the loop causing issues. RateLimitedClient will slow it down.
            result = await self._request_api(
                "GET",
                "/torrents/checkcached",
                params={"hash": info_hash.lower()}
            )
            
            # Torbox checkcached returns boolean list or similar truthy value?
            # It usually returns: { "data": { "hash": true/false }, "success": true } OR list
            # Based on previous code: "if result and isinstance(result, list)..."
            # Let's stricter check:
            # API documentation says it returns list of cached hashes? 
            # Or map?
            # Previous implementation:
            # if result and isinstance(result, list) and len(result) > 0: -> True
            is_cached = False
            if result: 
                if isinstance(result, list) and len(result) > 0:
                    is_cached = True
                elif isinstance(result, dict) and result.get(info_hash.lower()) is True:
                    is_cached = True
                elif result is True: # If API returns raw boolean
                    is_cached = True
                     
            cached_status[info_hash.lower()] = is_cached
        
        cached_count = sum(1 for v in cached_status.values() if v)
        logger.debug(f"Torbox: {cached_count}/{len(info_hashes)} torrents cached")
        return cached_status

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=20))
    async def add_magnet(self, info_hash: str, name: Optional[str] = None) -> Optional[int]:
        """Add magnet link to Torbox."""
        magnet = f"magnet:?xt=urn:btih:{info_hash}"
        if name:
            magnet += f"&dn={name}"
        
        # Using form data
        result = await self._request_api(
            "POST",
            "/torrents/createtorrent",
            data={"magnet": magnet}
        )
        
        if result and isinstance(result, dict) and "torrent_id" in result:
            logger.info(f"Torbox: Added torrent {info_hash[:8]}... -> ID: {result['torrent_id']}")
            return result["torrent_id"]
        return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=20))
    async def add_usenet(self, download_url: str, name: Optional[str] = None) -> Optional[int]:
        """
        Add Usenet (NZB) to Torbox via File Upload.
        This uses `httpx` for the *download* part (not IO bound/rate limited by Torbox),
        but then implementation uploads to Torbox.
        """
        try:
            # 1. Download NZB content locally (from Prowlarr)
            # Use raw httpx for this as it's not Torbox API
            logger.debug(f"Downloading NZB from Prowlarr: {download_url}")
            async with httpx.AsyncClient(verify=False, timeout=30.0) as dl_client:
                # Handle redirects manually to catch magnet links
                resp = await dl_client.get(download_url, follow_redirects=False)
                
                # Check for redirect to magnet
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    location = resp.headers["location"]
                    if location.startswith("magnet:"):
                        logger.info(f"Prowlarr redirected to magnet link. Switching to add_magnet.")
                        import re
                        hash_match = re.search(r'btih:([a-zA-Z0-9]+)', location)
                        if hash_match:
                            return await self.add_magnet(hash_match.group(1), name)
                        return None
                            
                    # Follow HTTP redirect
                    resp = await dl_client.get(location, follow_redirects=True)
                
                resp.raise_for_status()
                file_content = resp.content
                
                # Determine filename
                filename = "download.nzb"
                if name:
                     safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
                     filename = f"{safe_name}.nzb" if not safe_name.lower().endswith(".nzb") else safe_name

            # 2. Upload file to Torbox (Usenet) using new RateLimitedClient
            # Since RateLimitedClient uses aiohttp, we pass 'data' with MultipartWriter logic or simple FormData
            
            # Prepare MultiPart
            form_data = aiohttp.FormData()
            
            # Determine correct endpoint based on file type (nzb or torrent)
            target_url = "/usenet/createusenetdownload"
            field_name = "file"
            
            is_torrent = False
            # Basic check for torrent file signature 'd8:announce' or filename
            if filename.endswith(".torrent") or file_content.startswith(b'd8:announce'):
                logger.info("Detected .torrent file from Prowlarr, switching to torrent upload")
                target_url = "/torrents/createtorrent"
                is_torrent = True
                
            # Add file field
            form_data.add_field(field_name, file_content, filename=filename, content_type='application/x-nzb' if not is_torrent else 'application/x-bittorrent')
            
            if name and not is_torrent: # Name is not directly supported for torrent file upload
                form_data.add_field("name", name)
                
            # Use raw request to handle FormData correctly if needed, or update _request_api
            # _request_api handles 'data' kwarg which aiohttp accepts for FormData
            result = await self._request_api("POST", target_url, form_data=form_data)
            
            if result:
                # Handle differenct ID fields
                t_id = result.get("torrent_id") or result.get("usenetdownload_id") or result.get("id")
                if t_id:
                     logger.info(f"Torbox: Uploaded file -> ID: {t_id}")
                     return t_id
            
            return None

        except Exception as e:
            logger.error(f"Failed to process NZB add: {e}")
            raise e # Re-raise to allow @retry to catch it
    
    async def get_torrent_info(self, torrent_id: int) -> Optional[Dict]:
        """Get torrent info including files"""
        result = await self._request_api("GET", "/torrents/mylist", params={"id": torrent_id})
        # The API returns a list even for a single ID query, so we need to extract the first item
        if isinstance(result, list) and result:
            return result[0]
        return None
    
    async def get_torrents(self) -> List[Dict]:
        """Get list of user's torrents"""
        result = await self._request_api("GET", "/torrents/mylist")
        # Ensure list
        if isinstance(result, list): return result
        return []
    
    async def delete_torrent(self, torrent_id: int) -> bool:
        """Delete a torrent"""
        result = await self._request_api(
            "POST",
            "/torrents/controltorrent",
            data={"torrent_id": str(torrent_id), "operation": "delete"}
        )
        return result is not None
    
    async def get_download_link(self, torrent_id: int, file_id: Optional[int] = None) -> Optional[str]:
        """
        Get download/streaming link for a torrent file.
        """
        params = {"torrent_id": torrent_id, "token": self.api_key}
        if file_id:
            params["file_id"] = file_id
        
        # Use simple request since this returns string/url usually
        # But _request_api expects JSON/Dict...
        # Let's bypass _request_api for this specific text return if needed, but RateLimitedClient returns text if not json
        # Our _request_api wrapper tries to handle JSON structure.
        # Assuming requestdl returns JSON with 'data' = url or 'url' key?
        # Documentation: usually returns JSON { success: true, data: "url" }
        result = await self._request_api("GET", "/torrents/requestdl", params=params)
        
        if isinstance(result, str): return result
        if isinstance(result, dict): return result.get("url") or result.get("data")
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

    async def cleanup_stale_torrents(self, max_age_hours: int = 24) -> int:
        """
        Delete torrents stuck at 0% progress for longer than max_age_hours.
        Returns the number of deleted torrents.
        """
        from datetime import datetime, timezone
        from dateutil.parser import parse as parse_datetime
        
        if not self.is_configured:
            return 0
        
        torrents = await self.get_torrents()
        if not torrents:
            return 0
        
        deleted_count = 0
        now = datetime.now(timezone.utc)
        
        for torrent in torrents:
            try:
                # Torbox structure might differ, checking common fields
                progress = torrent.get("progress", 0)
                
                # Only check torrents at 0% progress or "error" state
                if progress != 0 and torrent.get("download_state") != "error":
                    continue
                
                # Parse the added date
                added_str = torrent.get("created_at") or torrent.get("updated_at")
                if not added_str:
                    continue
                
                added_time = parse_datetime(added_str)
                if added_time.tzinfo is None:
                    added_time = added_time.replace(tzinfo=timezone.utc)
                
                # Calculate age in hours
                age_hours = (now - added_time).total_seconds() / 3600
                
                if age_hours > max_age_hours:
                    torrent_id = torrent.get("id")
                    name = torrent.get("name", "unknown")[:50]
                    
                    success = await self.delete_torrent(torrent_id)
                    if success:
                        deleted_count += 1
                        logger.info(f"Cleaned up stale Torbox torrent (stuck {age_hours:.1f}h): {name}...")
                        
            except Exception as e:
                logger.debug(f"Error checking Torbox torrent for cleanup: {e}")
        
        return deleted_count
    
    # ==========================================================================
    # USENET METHODS
    # ==========================================================================
    
    async def get_usenet_info(self, usenet_id: int) -> Optional[Dict]:
        """Get usenet download info including files"""
        result = await self._request_api("GET", "/usenet/mylist", params={"id": usenet_id})
        # The API returns a list even for a single ID query, so we need to extract the first item
        if isinstance(result, list) and result:
            return result[0]
        return None
    
    async def get_usenet_list(self) -> List[Dict]:
        """Get list of user's usenet downloads"""
        result = await self._request_api("GET", "/usenet/mylist")
        return result if result and isinstance(result, list) else []
    
    async def delete_usenet(self, usenet_id: int) -> bool:
        """Delete a usenet download"""
        result = await self._request_api(
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
            result = await self._request_api(
                "GET",
                "/usenet/checkcached",
                params={"hash": hash_val}
            )
            
            is_cached = False
            if result:
                if isinstance(result, list) and len(result) > 0:
                    is_cached = True
                elif isinstance(result, dict) and result.get(hash_val) is True:
                    is_cached = True
                elif result is True:
                    is_cached = True
            
            cached_status[hash_val] = is_cached
        
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
        
        result = await self._request_api("GET", "/usenet/requestdl", params=params)
        
        if isinstance(result, str):
            return result
        elif result and "url" in result:
            return result["url"]
        
        return None
    
    async def close(self):
        """Close HTTP client"""
        await super().close()


# Singleton instance
torbox_service = TorboxService()
