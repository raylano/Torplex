"""
Torrentio Scraper Client
Uses Stremio addon API for precise IMDB-based torrent discovery.
"""
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass
from src.config import config


@dataclass
class TorrentioStream:
    """A stream result from Torrentio."""
    info_hash: str
    title: str
    seeders: int = 0
    size_bytes: int = 0
    source: str = ""  # The tracker/source


class TorrentioClient:
    """
    Client for Torrentio Stremio addon.
    
    Torrentio provides pre-aggregated torrent results indexed by IMDB ID,
    making it much more reliable than text-based search.
    """
    
    # Public Torrentio instance
    BASE_URL = "https://torrentio.strem.fun"
    
    # Filter configuration - customize for quality preferences
    # Format: providers|qualityfilter|sort
    # Common: sort=qualitysize for best quality first
    DEFAULT_FILTER = "sort=qualitysize|qualityfilter=480p,scr,cam"
    
    def __init__(self, custom_url: str = None, custom_filter: str = None):
        self.base_url = custom_url or self.BASE_URL
        self.filter = custom_filter or self.DEFAULT_FILTER
        self.timeout = 15
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    def _build_url(self, media_type: str, imdb_id: str, season: int = None, episode: int = None) -> str:
        """Build the Torrentio API URL."""
        # Format: /filter/stream/type/imdb_id[:season:episode].json
        url = f"{self.base_url}/{self.filter}/stream/{media_type}/{imdb_id}"
        
        if season is not None and episode is not None:
            url += f":{season}:{episode}"
        
        return f"{url}.json"
    
    def search_movie(self, imdb_id: str) -> List[TorrentioStream]:
        """
        Search for a movie by IMDB ID.
        
        Args:
            imdb_id: IMDB ID (e.g., "tt1234567")
            
        Returns:
            List of TorrentioStream results
        """
        if not imdb_id or not imdb_id.startswith("tt"):
            print(f"[Torrentio] Invalid IMDB ID: {imdb_id}")
            return []
        
        url = self._build_url("movie", imdb_id)
        return self._fetch_streams(url, f"movie {imdb_id}")
    
    def search_episode(self, imdb_id: str, season: int, episode: int) -> List[TorrentioStream]:
        """
        Search for a TV episode by IMDB ID, season, and episode.
        
        Args:
            imdb_id: IMDB ID of the TV show (e.g., "tt1234567")
            season: Season number
            episode: Episode number
            
        Returns:
            List of TorrentioStream results
        """
        if not imdb_id or not imdb_id.startswith("tt"):
            print(f"[Torrentio] Invalid IMDB ID: {imdb_id}")
            return []
        
        url = self._build_url("series", imdb_id, season, episode)
        return self._fetch_streams(url, f"S{season:02d}E{episode:02d} of {imdb_id}")
    
    def _fetch_streams(self, url: str, description: str) -> List[TorrentioStream]:
        """Fetch and parse streams from Torrentio."""
        print(f"[Torrentio] Searching: {description}")
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code == 404:
                print(f"[Torrentio] No results for {description}")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            streams = []
            for stream in data.get("streams", []):
                # Extract info hash
                info_hash = stream.get("infoHash", "")
                if not info_hash:
                    continue
                
                # Parse title for info
                title = stream.get("title", "")
                
                # Extract seeders from title (format: "👤 123")
                seeders = 0
                if "👤" in title:
                    try:
                        seeder_part = title.split("👤")[1].strip().split()[0]
                        seeders = int(seeder_part)
                    except:
                        pass
                
                # Extract size from title (format: "💾 1.5 GB")
                size_bytes = 0
                if "💾" in title:
                    try:
                        size_part = title.split("💾")[1].strip()
                        size_bytes = self._parse_size(size_part)
                    except:
                        pass
                
                # Get raw title (first line before emoji info)
                raw_title = title.split("\n")[0] if "\n" in title else title
                
                # Source (tracker info usually after newlines)
                source = ""
                if "⚙️" in title:
                    try:
                        source = title.split("⚙️")[1].strip().split("\n")[0]
                    except:
                        pass
                
                streams.append(TorrentioStream(
                    info_hash=info_hash.lower(),
                    title=raw_title,
                    seeders=seeders,
                    size_bytes=size_bytes,
                    source=source
                ))
            
            print(f"[Torrentio] Found {len(streams)} streams for {description}")
            return streams
            
        except requests.exceptions.Timeout:
            print(f"[Torrentio] Timeout for {description}")
            return []
        except requests.exceptions.RequestException as e:
            print(f"[Torrentio] Request error for {description}: {e}")
            return []
        except Exception as e:
            print(f"[Torrentio] Error for {description}: {e}")
            return []
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string like "1.5 GB" to bytes."""
        try:
            parts = size_str.strip().split()
            if len(parts) < 2:
                return 0
            
            value = float(parts[0])
            unit = parts[1].upper()
            
            multipliers = {
                "B": 1,
                "KB": 1024,
                "MB": 1024 ** 2,
                "GB": 1024 ** 3,
                "TB": 1024 ** 4,
            }
            
            return int(value * multipliers.get(unit, 1))
        except:
            return 0
    
    def validate(self) -> bool:
        """Check if Torrentio is accessible."""
        try:
            response = self.session.get(
                f"{self.base_url}/manifest.json",
                timeout=10
            )
            return response.ok
        except:
            return False


# Singleton instance
_client: TorrentioClient = None

def get_torrentio_client() -> TorrentioClient:
    """Get or create the Torrentio client singleton."""
    global _client
    if _client is None:
        _client = TorrentioClient()
    return _client
