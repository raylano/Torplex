import requests
from src.config import config

class ProwlarrClient:
    def __init__(self):
        pass

    def search(self, query, category=None):
        # Torznab search via Prowlarr
        # Endpoint: http://prowlarr:9696/api/v1/search?query={query}&apikey={key}
        # Actually Prowlarr provides torznab endpoints for apps, but also has an internal API.
        # It's easier to use the Prowlarr internal API to search all indexers, OR use the aggregate Torznab endpoint.
        # Prowlarr aggregate endpoint: /prowlarr/api/v1/search?query=... matches internal search.
        # Torznab aggregate is usually /prowlarr/[id]/api?t=search...

        # Let's use the internal search API which is more powerful for "manual" searching logic.

        base_url = config.get().prowlarr_url
        api_key = config.get().prowlarr_api_key

        if not api_key:
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
            return resp.json()
        except Exception as e:
            print(f"Prowlarr Error: {e}")
            return []
