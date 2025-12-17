"""
Plex Client - using plexapi library like Riven
"""
import requests
from typing import List, Dict, Optional
from src.config import config

# Try to use plexapi for better watchlist support
try:
    from plexapi.myplex import MyPlexAccount
    PLEXAPI_AVAILABLE = True
except ImportError:
    PLEXAPI_AVAILABLE = False
    print("[Plex] plexapi not installed, using fallback API")


class PlexClient:
    """
    Plex client with proper watchlist support.
    Uses plexapi library like Riven for reliable watchlist fetching.
    """
    
    def __init__(self):
        self.account = None
        self._init_account()
    
    def _init_account(self):
        """Initialize Plex account if token available."""
        token = config.get().plex_token
        if not token:
            return
        
        if PLEXAPI_AVAILABLE:
            try:
                self.account = MyPlexAccount(token=token)
                print(f"[Plex] Authenticated as: {self.account.username}")
            except Exception as e:
                print(f"[Plex] Auth failed: {e}")
                self.account = None
    
    def get_watchlist(self, token: str = None) -> List[Dict]:
        """
        Fetch watchlist items with TMDB/TVDB/IMDB IDs.
        
        Returns list of dicts: [
            {'type': 'movie', 'title': 'X', 'year': 2024, 'tmdb_id': '123', 'imdb_id': 'tt1234'},
            {'type': 'show', 'title': 'Y', 'year': 2024, 'tvdb_id': '456', 'imdb_id': 'tt5678'},
        ]
        """
        # Reinit if token changed
        if token and token != config.get().plex_token:
            self.account = None
            if PLEXAPI_AVAILABLE:
                try:
                    self.account = MyPlexAccount(token=token)
                except:
                    pass
        
        if PLEXAPI_AVAILABLE and self.account:
            return self._get_watchlist_plexapi()
        else:
            return self._get_watchlist_http(token or config.get().plex_token)
    
    def _get_watchlist_plexapi(self) -> List[Dict]:
        """Fetch watchlist using plexapi library (like Riven)."""
        items = []
        
        try:
            watchlist = self.account.watchlist()
            print(f"[Plex] Found {len(watchlist)} items in watchlist")
            
            for item in watchlist:
                try:
                    item_data = {
                        'type': 'movie' if item.TYPE == 'movie' else 'show',
                        'title': item.title,
                        'year': getattr(item, 'year', None),
                        'tmdb_id': None,
                        'tvdb_id': None,
                        'imdb_id': None,
                    }
                    
                    # Extract IDs from guids
                    if hasattr(item, 'guids') and item.guids:
                        for guid in item.guids:
                            guid_id = guid.id if hasattr(guid, 'id') else str(guid)
                            
                            if 'tmdb://' in guid_id:
                                item_data['tmdb_id'] = guid_id.split('tmdb://')[-1]
                            elif 'tvdb://' in guid_id:
                                item_data['tvdb_id'] = guid_id.split('tvdb://')[-1]
                            elif 'imdb://' in guid_id:
                                item_data['imdb_id'] = guid_id.split('imdb://')[-1]
                    
                    # Only add if we have at least one ID
                    if item_data['tmdb_id'] or item_data['tvdb_id'] or item_data['imdb_id']:
                        items.append(item_data)
                        print(f"  [+] {item_data['title']} ({item_data['year']})")
                    else:
                        print(f"  [-] {item.title}: No usable IDs found")
                        
                except Exception as e:
                    print(f"  [!] Error parsing {getattr(item, 'title', 'unknown')}: {e}")
                    
        except Exception as e:
            print(f"[Plex] Watchlist error: {e}")
            
        return items
    
    def _get_watchlist_http(self, token: str) -> List[Dict]:
        """Fallback: Fetch watchlist using HTTP API."""
        if not token:
            print("[Plex] No token provided")
            return []
        
        items = []
        
        # Try the discover API
        url = "https://discover.provider.plex.tv/library/sections/watchlist/all"
        headers = {
            "Accept": "application/json",
            "X-Plex-Token": token
        }
        
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            metadata = data.get('MediaContainer', {}).get('Metadata', [])
            print(f"[Plex HTTP] Found {len(metadata)} items")
            
            for item in metadata:
                item_data = {
                    'type': 'movie' if item.get('type') == 'movie' else 'show',
                    'title': item.get('title'),
                    'year': item.get('year'),
                    'tmdb_id': None,
                    'tvdb_id': None,
                    'imdb_id': None,
                }
                
                # Extract from Guid array
                for guid in item.get('Guid', []):
                    guid_id = guid.get('id', '')
                    if 'tmdb://' in guid_id:
                        item_data['tmdb_id'] = guid_id.replace('tmdb://', '')
                    elif 'tvdb://' in guid_id:
                        item_data['tvdb_id'] = guid_id.replace('tvdb://', '')
                    elif 'imdb://' in guid_id:
                        item_data['imdb_id'] = guid_id.replace('imdb://', '')
                
                if item_data['tmdb_id'] or item_data['tvdb_id']:
                    items.append(item_data)
                    
        except Exception as e:
            print(f"[Plex HTTP] Error: {e}")
            
        return items
