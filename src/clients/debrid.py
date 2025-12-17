"""
Debrid Service Factory
Returns the appropriate debrid client based on configuration.
"""
from src.config import config
from src.clients.debrid_base import DebridClient
from src.clients.torbox import TorboxClient
from src.clients.realdebrid import RealDebridClient

def get_debrid_client() -> DebridClient:
    """
    Factory function to get the configured debrid client.
    
    Returns:
        DebridClient instance based on config.debrid_service setting
    """
    service = config.get().debrid_service.lower()
    
    if service == 'realdebrid':
        print(f"[Debrid] Using RealDebrid")
        return RealDebridClient()
    else:
        # Default to Torbox
        print(f"[Debrid] Using Torbox")
        return TorboxClient()

# Singleton instance - refreshed when needed
_client: DebridClient = None

def get_client() -> DebridClient:
    """Get or create the debrid client singleton."""
    global _client
    if _client is None:
        _client = get_debrid_client()
    return _client

def refresh_client():
    """Force refresh of the debrid client (after settings change)."""
    global _client
    _client = get_debrid_client()
