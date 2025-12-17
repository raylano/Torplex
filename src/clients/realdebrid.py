"""
RealDebrid Client Implementation
"""
import requests
from typing import List, Dict, Optional, Any
from src.config import config
from src.clients.debrid_base import DebridClient

class RealDebridClient(DebridClient):
    """RealDebrid debrid service client."""
    
    def __init__(self):
        self.base_url = "https://api.real-debrid.com/rest/1.0"

    @property
    def name(self) -> str:
        return "RealDebrid"

    def _headers(self):
        return {
            "Authorization": f"Bearer {config.get().realdebrid_api_key}"
        }

    def check_cached(self, hash_list: List[str]) -> Dict[str, bool]:
        """Check if hashes are cached in RealDebrid."""
        if not hash_list:
            return {}
            
        url = f"{self.base_url}/torrents/instantAvailability/{'/'.join(hash_list)}"
        
        try:
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            
            # RealDebrid returns {hash: {rd: [{...}]}} for cached, empty dict for uncached
            result = {}
            for h in hash_list:
                h_lower = h.lower()
                # Check if hash exists and has 'rd' key with content
                if h_lower in data and data[h_lower].get('rd'):
                    result[h_lower] = True
                else:
                    result[h_lower] = False
            return result
        except Exception as e:
            print(f"[RealDebrid] Check Cache Error: {e}")
            return {h.lower(): False for h in hash_list}

    def add_magnet(self, magnet_link: str) -> Optional[Dict[str, Any]]:
        """Add a magnet link to RealDebrid."""
        url = f"{self.base_url}/torrents/addMagnet"
        
        print(f"[RealDebrid] Adding magnet: {magnet_link[:80]}...")
        
        try:
            # Step 1: Add magnet
            resp = requests.post(url, data={"magnet": magnet_link}, headers=self._headers())
            resp.raise_for_status()
            result = resp.json()
            torrent_id = result.get('id')
            
            if not torrent_id:
                print(f"[RealDebrid] No torrent ID returned")
                return None
            
            # Step 2: Get torrent info to get file list
            info_url = f"{self.base_url}/torrents/info/{torrent_id}"
            info_resp = requests.get(info_url, headers=self._headers())
            info_resp.raise_for_status()
            info = info_resp.json()
            
            # Step 3: Select all files
            select_url = f"{self.base_url}/torrents/selectFiles/{torrent_id}"
            files = info.get('files', [])
            file_ids = ",".join(str(f['id']) for f in files) if files else "all"
            select_resp = requests.post(select_url, data={"files": file_ids}, headers=self._headers())
            select_resp.raise_for_status()
            
            print(f"[RealDebrid] Added successfully, ID: {torrent_id}")
            
            # Return in similar format to Torbox
            return {
                'success': True,
                'data': {
                    'torrent_id': torrent_id,
                    'hash': info.get('hash', '').lower()
                }
            }
        except requests.exceptions.HTTPError as e:
            print(f"[RealDebrid] Add Error: {e}")
            if hasattr(e, 'response'):
                print(f"[RealDebrid] Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"[RealDebrid] Add Error: {e}")
            return None

    def get_torrents(self) -> List[Dict[str, Any]]:
        """Get list of torrents from RealDebrid."""
        url = f"{self.base_url}/torrents"
        try:
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            torrents = resp.json()
            
            # Normalize to match Torbox format
            normalized = []
            for t in torrents:
                # Map RD status to our standard statuses
                rd_status = t.get('status', '')
                if rd_status == 'downloaded':
                    status = 'completed'
                elif rd_status in ('queued', 'downloading'):
                    status = 'downloading'
                elif rd_status == 'magnet_conversion':
                    status = 'downloading'
                else:
                    status = rd_status
                
                normalized.append({
                    'id': t.get('id'),
                    'hash': t.get('hash', '').lower(),
                    'name': t.get('filename', ''),
                    'download_state': status,
                    'files': [],  # Would need separate call
                    'size': t.get('bytes', 0),
                    'progress': t.get('progress', 0)
                })
            
            return normalized
        except Exception as e:
            print(f"[RealDebrid] List Error: {e}")
            return []
