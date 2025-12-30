"""
Plex Watchlist Service
Fetches items from Plex Watchlist for automatic processing
"""
import httpx
from typing import List, Dict, Optional
from loguru import logger

from src.config import settings


class PlexWatchlistService:
    """Service for interacting with Plex Watchlist"""
    
    DISCOVER_URL = "https://discover.provider.plex.tv"
    METADATA_URL = "https://metadata.provider.plex.tv"
    
    def __init__(self):
        self.token = settings.plex_token
        self.plex_url = settings.plex_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Plex-Token": self.token,
            "Accept": "application/json",
        }
    
    async def get_watchlist(self) -> List[Dict]:
        """Fetch ALL items from Plex Watchlist (with pagination)"""
        if not self.token:
            logger.warning("Plex token not configured")
            return []
        
        all_items = []
        offset = 0
        page_size = 50  # Plex supports up to 50 per page
        
        try:
            while True:
                url = f"{self.DISCOVER_URL}/library/sections/watchlist/all"
                params = {
                    "X-Plex-Container-Start": str(offset),
                    "X-Plex-Container-Size": str(page_size),
                }
                
                response = await self.client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                container = data.get("MediaContainer", {})
                items = container.get("Metadata", [])
                total_size = container.get("totalSize", 0)
                
                if not items:
                    break
                
                all_items.extend(items)
                offset += len(items)
                
                logger.debug(f"Fetched {len(items)} watchlist items, total: {len(all_items)}/{total_size}")
                
                # Check if we got all items
                if len(all_items) >= total_size or len(items) < page_size:
                    break
            
            logger.info(f"Found {len(all_items)} items in Plex Watchlist")
            return all_items
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Plex API error: {e.response.status_code}")
            return all_items  # Return what we got
        except Exception as e:
            logger.error(f"Failed to fetch Plex Watchlist: {e}")
            return all_items
    
    async def get_item_details(self, rating_key: str) -> Optional[Dict]:
        """Get detailed metadata for a watchlist item"""
        if not self.token:
            return None
        
        try:
            url = f"{self.METADATA_URL}/library/metadata/{rating_key}"
            response = await self.client.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            metadata = data.get("MediaContainer", {}).get("Metadata", [])
            return metadata[0] if metadata else None
            
        except Exception as e:
            logger.error(f"Failed to get Plex item details: {e}")
            return None
    
    def extract_ids(self, item: Dict) -> Dict[str, Optional[str]]:
        """Extract IMDB/TMDB/TVDB IDs from Plex item"""
        guids = item.get("Guid", [])
        
        ids = {
            "imdb_id": None,
            "tmdb_id": None,
            "tvdb_id": None,
        }
        
        for guid in guids:
            guid_id = guid.get("id", "")
            if guid_id.startswith("imdb://"):
                ids["imdb_id"] = guid_id.replace("imdb://", "")
            elif guid_id.startswith("tmdb://"):
                ids["tmdb_id"] = guid_id.replace("tmdb://", "")
            elif guid_id.startswith("tvdb://"):
                ids["tvdb_id"] = guid_id.replace("tvdb://", "")
        
        return ids
    
    async def refresh_library(self, library_key: Optional[str] = None):
        """Trigger a Plex library refresh"""
        if not self.token or not self.plex_url:
            logger.warning("Plex not configured for library refresh")
            return False
        
        try:
            if library_key:
                url = f"{self.plex_url}/library/sections/{library_key}/refresh"
            else:
                # Refresh all libraries
                url = f"{self.plex_url}/library/sections/all/refresh"
            
            response = await self.client.get(
                url,
                headers={"X-Plex-Token": self.token}
            )
            response.raise_for_status()
            logger.info("Plex library refresh triggered")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh Plex library: {e}")
            return False
    
    async def get_libraries(self) -> List[Dict]:
        """Get list of Plex libraries"""
        if not self.token or not self.plex_url:
            return []
        
        try:
            url = f"{self.plex_url}/library/sections"
            response = await self.client.get(
                url,
                headers={"X-Plex-Token": self.token, "Accept": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("MediaContainer", {}).get("Directory", [])
            
        except Exception as e:
            logger.error(f"Failed to get Plex libraries: {e}")
            return []
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
plex_service = PlexWatchlistService()
