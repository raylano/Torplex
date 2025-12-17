"""
Abstract Debrid Client Interface
Provides a unified interface for different debrid services (Torbox, RealDebrid, etc.)
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

class DebridClient(ABC):
    """Abstract base class for debrid service clients."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the debrid service."""
        pass
    
    @abstractmethod
    def check_cached(self, hash_list: List[str]) -> Dict[str, bool]:
        """
        Check if hashes are cached in the debrid service.
        
        Args:
            hash_list: List of torrent info hashes
            
        Returns:
            Dictionary mapping hash -> cached status (True/False)
        """
        pass
    
    @abstractmethod
    def add_magnet(self, magnet_link: str) -> Optional[Dict[str, Any]]:
        """
        Add a magnet link to the debrid service.
        
        Args:
            magnet_link: The magnet URI
            
        Returns:
            Response dict with torrent info, or None on failure
        """
        pass
    
    @abstractmethod
    def get_torrents(self) -> List[Dict[str, Any]]:
        """
        Get list of torrents in the debrid service.
        
        Returns:
            List of torrent info dictionaries
        """
        pass
