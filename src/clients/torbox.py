import requests
from src.config import config

class TorboxClient:
    def __init__(self):
        self.base_url = "https://api.torbox.app/v1/api"
        # API requires 'api_version' in path.
        # Based on docs: /{api_version}/api/torrents/...
        # But wait, docs say `/{api_version}/api/torrents/createtorrent`
        # and example base url is `https://api.torbox.app`.
        # So it should be `https://api.torbox.app/v1/api/torrents/...`

    def _headers(self):
        return {
            "Authorization": f"Bearer {config.get().torbox_api_key}",
            "Content-Type": "application/json"
        }

    def check_cached(self, hash_list):
        """
        Checks if hashes are cached in Torbox.
        Takes a list of hashes (strings).
        Returns list of cached hashes (or object depending on format).
        """
        url = f"{self.base_url}/torrents/checkcached"
        # API Docs: ?hash=XXXX,XXXX&format=list

        hashes_str = ",".join(hash_list)
        params = {
            "hash": hashes_str,
            "format": "list"
        }

        try:
            resp = requests.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            # If format=list, it returns a dict where keys are hashes?
            # Or list of cached hashes?
            # Docs say: "Options are either object or list. List is the most performant option"
            # If it's a list, it probably just returns the ones that ARE cached?
            # Or a list of booleans?
            # Usually debrid services return { "hash": boolean } or { "hash": { ... } }
            # Let's assume it returns a dictionary if we used object, but list might be just [hash1, hash2]
            # Safest is to return the raw data and let logic handle it, but I need to normalize.
            # I'll use object format to be safe and clear.
            return data
        except Exception as e:
            print(f"Torbox Check Cache Error: {e}")
            return {}

    def add_magnet(self, magnet_link):
        """
        Adds a magnet link to Torbox.
        """
        url = f"{self.base_url}/torrents/createtorrent"
        data = {
            "magnet": magnet_link,
            "seed": 1,
            "allow_zip": 0
        }
        try:
            resp = requests.post(url, json=data, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Torbox Add Error: {e}")
            return None

    def get_torrents(self):
        url = f"{self.base_url}/torrents/mylist"
        try:
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Torbox List Error: {e}")
            return []
