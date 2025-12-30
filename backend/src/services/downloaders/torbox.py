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
                # Raise exception for retryable errors if needed, but usually logic errors return None
                return None
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"Torbox rate limit (429). Retrying...")
                raise e # Raise to let @retry handle it
                
            logger.error(f"Torbox API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Torbox request failed: {e}")
            raise e # Raise other connection errors for retry
    
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
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
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
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
    async def add_usenet(self, download_url: str, name: Optional[str] = None) -> Optional[int]:
        """
        Add Usenet (NZB) to Torbox via File Upload.
        Since Prowlarr URLs are local/internal, we must download the NZB locally
        and upload the file content to Torbox.
        """
        try:
            # 1. Download NZB content locally
            logger.debug(f"Downloading NZB from Prowlarr: {download_url}")
            # Use a separate client for the download
            async with httpx.AsyncClient(verify=False, timeout=30.0) as dl_client:
                # Handle redirects manually to catch magnet links
                resp = await dl_client.get(download_url, follow_redirects=False)
                
                # Check for redirect to magnet
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    location = resp.headers["location"]
                    if location.startswith("magnet:"):
                        logger.info(f"Prowlarr redirected to magnet link. Switching to add_magnet.")
                        # Extract info_hash from magnet? Or just add raw magnet?
                        # Torbox add_magnet expects info_hash usually, but let's check if we can add by magnet string
                        # actually add_magnet impl constructs magnet from hash.
                        # We should create a new method or extract hash.
                        
                        import re
                        hash_match = re.search(r'btih:([a-zA-Z0-9]+)', location)
                        if hash_match:
                            info_hash = hash_match.group(1)
                            return await self.add_magnet(info_hash, name)
                        else:
                            logger.error("Could not extract hash from magnet link")
                            return None
                            
                    # Follow HTTP redirect
                    resp = await dl_client.get(location, follow_redirects=True)
                
                resp.raise_for_status()
                nzb_resp = resp
                
                # Determine filename
                import cgi
                filename = "download.nzb"
                if "content-disposition" in nzb_resp.headers:
                    _, params = cgi.parse_header(nzb_resp.headers["content-disposition"])
                    if "filename" in params:
                        filename = params["filename"]
                
                if not filename.endswith(".nzb"):
                    # Check if it's a torrent file
                    if filename.endswith(".torrent") or "application/x-bittorrent" in nzb_resp.headers.get("content-type", ""):
                        logger.info(f"Prowlarr returned a .torrent file. Switching to torrent upload.")
                        
                        # Upload .torrent file to Torbox
                        url = f"{self.BASE_URL}/torrents/createtorrent"
                        
                        # Prepare headers for multipart upload (MUST NOT include Content-Type)
                        upload_headers = self.headers.copy()
                        if "Content-Type" in upload_headers:
                            del upload_headers["Content-Type"]
                            
                        response = await self.client.post(
                            url,
                            headers=upload_headers,
                            files={"file": (filename, file_content, "application/x-bittorrent")}
                        )
                        response.raise_for_status()
                        result = response.json()
                        
                        if result.get("success") and result.get("data", {}).get("torrent_id"):
                            t_id = result["data"]["torrent_id"]
                            logger.info(f"Torbox: Uploaded .torrent file -> ID: {t_id}")
                            return t_id
                        return None
                    
                    # Default to appending .nzb if unsure
                    filename += ".nzb"
                    
                file_content = nzb_resp.content

            # 2. Upload file to Torbox (Usenet)
            # Use lower-level client.request to handle multipart properly if needed,
            # but httpx handles 'files' arg nicely.
            
            # Note: We need to use the headers property but EXCLUDE Content-Type 
            # so httpx can set the boundary for multipart/form-data.
            
            url = f"{self.BASE_URL}/usenet/createusenetdownload"
            
            # Prepare headers for multipart upload (MUST NOT include Content-Type)
            upload_headers = self.headers.copy()
            if "Content-Type" in upload_headers:
                del upload_headers["Content-Type"]
            
            response = await self.client.post(
                url,
                headers=upload_headers,
                files={"file": (filename, file_content, "application/x-nzb")}
            )
            
            response.raise_for_status()
            result = response.json()
             
            if result.get("success") and result.get("data", {}).get("usenet_id"):
                usenet_id = result["data"]["usenet_id"]
                logger.info(f"Torbox: Uploaded NZB -> ID: {usenet_id}")
                return usenet_id
            
            error = result.get("error", result.get("detail", "Unknown error"))
            logger.error(f"Torbox NZB upload failed: {error}")
            return None

        except Exception as e:
            # Check for 429 in exception if not caught by retry
            logger.error(f"Failed to process NZB add: {e}")
            raise e # Raise to ensure retry logic catches it!
    
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
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
torbox_service = TorboxService()
