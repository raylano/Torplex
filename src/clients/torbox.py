import requests
from typing import List, Dict, Optional, Any
from src.config import config
from src.clients.debrid_base import DebridClient

class TorboxClient(DebridClient):
    """Torbox debrid service client."""
    
    def __init__(self):
        self.base_url = "https://api.torbox.app/v1/api"

    @property
    def name(self) -> str:
        return "Torbox"

    def _headers(self):
        return {
            "Authorization": f"Bearer {config.get().torbox_api_key}",
            "Content-Type": "application/json"
        }

    def check_cached(self, hash_list: List[str]) -> Dict[str, bool]:
        """Check if hashes are cached in Torbox."""
        if not hash_list:
            return {}
            
        url = f"{self.base_url}/torrents/checkcached"
        hashes_str = ",".join(hash_list)
        params = {"hash": hashes_str, "format": "list"}

        try:
            resp = requests.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            
            # Torbox returns list of cached hashes
            # Robustly handle response format (list of strings or dicts)
            cached_hashes = set()
            result_data = data.get('data')
            
            if isinstance(result_data, list):
                for h in result_data:
                    if isinstance(h, str):
                        cached_hashes.add(h.lower())
                    elif isinstance(h, dict) and 'hash' in h:
                        cached_hashes.add(h['hash'].lower())
            
            return {h.lower(): h.lower() in cached_hashes for h in hash_list}
        except Exception as e:
            print(f"Torbox Check Cache Error: {e}")
            # Return False for all if check fails, so we don't block logic
            # Ensure h is string before calling lower()
            return {str(h).lower(): False for h in hash_list}

    def add_magnet(self, magnet_link: str) -> Optional[Dict[str, Any]]:
        """Add a magnet link to Torbox."""
        url = f"{self.base_url}/torrents/createtorrent"
        
        form_data = {
            "magnet": magnet_link,
            "seed": "1",
            "allow_zip": "false"
        }
        
        headers = {"Authorization": f"Bearer {config.get().torbox_api_key}"}
        
        print(f"[Torbox] Adding magnet: {magnet_link[:80]}...")
        
        try:
            resp = requests.post(url, data=form_data, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            print(f"[Torbox] Added successfully")
            return result
        except requests.exceptions.HTTPError as e:
            print(f"[Torbox] Add Error: {e}")
            print(f"[Torbox] Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"[Torbox] Add Error: {e}")
            return None

    def get_torrents(self) -> List[Dict[str, Any]]:
        """Get list of torrents from Torbox."""
        url = f"{self.base_url}/torrents/mylist"
        try:
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', []) if isinstance(data, dict) else data
        except Exception as e:
            print(f"[Torbox] List Error: {e}")
            return []

