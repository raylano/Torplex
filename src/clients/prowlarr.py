import requests
import hashlib
import bencodepy
from src.config import config

class ProwlarrClient:
    def __init__(self):
        pass

    def search(self, query, category=None):
        """Search Prowlarr for torrents"""
        base_url = config.get().prowlarr_url
        api_key = config.get().prowlarr_api_key

        if not api_key:
            print("Prowlarr Error: No API key configured")
            return []

        url = f"{base_url}/api/v1/search"
        params = {
            "query": query,
            "apikey": api_key,
            "type": "search",
            "limit": 100
        }

        try:
            resp = requests.get(url, params=params)
            resp.raise_for_status()
            results = resp.json()
            print(f"Prowlarr returned {len(results)} results for '{query}'")
            return results
        except Exception as e:
            print(f"Prowlarr Error: {e}")
            return []

    def download_torrent(self, download_url):
        """
        Download .torrent file via Prowlarr's proxy and extract info_hash.
        Returns tuple: (info_hash, name) or (None, None) on failure.
        """
        try:
            print(f"Downloading torrent from Prowlarr...")
            resp = requests.get(download_url, timeout=30)
            resp.raise_for_status()
            
            # Parse the .torrent file (bencoded data)
            torrent_data = bencodepy.decode(resp.content)
            
            # Extract info dictionary
            info = torrent_data[b'info']
            
            # Calculate info_hash (SHA1 of bencoded info dict)
            info_encoded = bencodepy.encode(info)
            info_hash = hashlib.sha1(info_encoded).hexdigest().upper()
            
            # Get torrent name
            name = info.get(b'name', b'Unknown').decode('utf-8', errors='ignore')
            
            print(f"Extracted hash: {info_hash} for: {name}")
            return info_hash, name
            
        except Exception as e:
            print(f"Torrent download/parse error: {e}")
            return None, None
    
    def get_magnet_from_result(self, result):
        """
        Try to get a magnet link from a search result.
        If no direct magnet, downloads .torrent and constructs one.
        Returns: (magnet_link, info_hash) or (None, None)
        """
        import re
        import urllib.parse
        
        # Helper to extract hash from magnet
        def extract_hash(magnet):
            match = re.search(r'btih:([a-fA-F0-9]{40})', magnet, re.IGNORECASE)
            return match.group(1).upper() if match else None
        
        # First try magnetUrl field
        magnet = result.get('magnetUrl')
        if magnet and magnet.startswith('magnet:'):
            info_hash = extract_hash(magnet)
            if info_hash:
                print(f"Found magnet in magnetUrl: {info_hash}")
                return magnet, info_hash
        
        # Check if downloadUrl is actually a magnet link
        download_url = result.get('downloadUrl')
        if download_url and download_url.startswith('magnet:'):
            info_hash = extract_hash(download_url)
            if info_hash:
                print(f"Found magnet in downloadUrl: {info_hash}")
                return download_url, info_hash
        
        # No magnet - try to download .torrent file
        if not download_url:
            return None, None
        
        info_hash, name = self.download_torrent(download_url)
        if not info_hash:
            return None, None
        
        # Construct magnet link
        title = result.get('title') or name or 'Unknown'
        encoded_title = urllib.parse.quote(title)
        magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={encoded_title}"
        
        return magnet, info_hash
