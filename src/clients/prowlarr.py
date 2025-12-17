import requests
from src.config import config

class ProwlarrClient:
    def __init__(self):
        pass

    def search(self, query, category=None):
        # Prowlarr internal search API
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
            if results and len(results) > 0:
                # Debug: show first result structure
                print(f"First result keys: {list(results[0].keys())[:10]}")
            return results
        except Exception as e:
            print(f"Prowlarr Error: {e}")
            return []

