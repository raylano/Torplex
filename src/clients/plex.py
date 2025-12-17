import requests
import xml.etree.ElementTree as ET
from src.config import config

class PlexClient:
    def get_watchlist(self, token):
        # https://metadata.provider.plex.tv/library/sections/watchlist/all?X-Plex-Token={token}
        url = f"https://metadata.provider.plex.tv/library/sections/watchlist/all"
        headers = {
            "Accept": "application/json",
            "X-Plex-Token": token
        }
        try:
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            # Plex returns XML by default for some endpoints, but JSON if requested.
            # Watchlist endpoint often returns XML even with Accept: json in some older versions,
            # but let's assume JSON first.
            return resp.json()
        except Exception as e:
            print(f"Plex Watchlist Error: {e}")
            return None
