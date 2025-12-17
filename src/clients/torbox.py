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
        """Check if hashes are cached in Torbox using batching."""
        if not hash_list:
            return {}
            
        results = {}
        # Batch size of 40 keeps URL length safe (~2000 chars)
        BATCH_SIZE = 40
        
        for i in range(0, len(hash_list), BATCH_SIZE):
            batch = hash_list[i:i + BATCH_SIZE]
            url = f"{self.base_url}/torrents/checkcached"
            hashes_str = ",".join(batch)
            params = {"hash": hashes_str, "format": "list"}

            try:
                resp = requests.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                
                cached_hashes = set()
                result_data = data.get('data')
                
                if isinstance(result_data, list):
                    for h in result_data:
                        if isinstance(h, str):
                            cached_hashes.add(h.lower())
                        elif isinstance(h, dict) and 'hash' in h:
                            cached_hashes.add(h['hash'].lower())
                
                # Update main results dict
                for h in batch:
                    results[h.lower()] = h.lower() in cached_hashes
                    
            except Exception as e:
                print(f"Torbox Check Cache Error (batch {i}): {e}")
                # Mark batch as failed/false
                for h in batch:
                    results[str(h).lower()] = False
                    
        return results

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

