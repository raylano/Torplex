"""
Torplex Configuration Management
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://torplex:torplex@localhost:5432/torplex",
        alias="DATABASE_URL"
    )
    
    # Debrid Services
    real_debrid_token: str = Field(default="", alias="REAL_DEBRID_TOKEN")
    torbox_api_key: str = Field(default="", alias="TORBOX_API_KEY")
    
    # Media APIs
    tmdb_api_key: str = Field(default="", alias="TMDB_API_KEY")
    plex_token: str = Field(default="", alias="PLEX_TOKEN")
    plex_url: str = Field(default="http://localhost:32400", alias="PLEX_URL")
    
    # Prowlarr
    prowlarr_url: str = Field(default="http://prowlarr:9696", alias="PROWLARR_URL")
    prowlarr_api_key: str = Field(default="", alias="PROWLARR_API_KEY")
    
    # Zilean (optional cache checker)
    zilean_url: str = Field(default="", alias="ZILEAN_URL")
    
    # Paths
    mount_path: str = Field(default="/mnt/zurg", alias="MOUNT_PATH")
    symlink_path: str = Field(default="/mnt/media", alias="SYMLINK_PATH")
    
    # Scheduler intervals (in seconds)
    watchlist_scan_interval: int = Field(default=300)  # 5 minutes
    library_scan_interval: int = Field(default=60)     # 1 minute
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
    
    @property
    def has_real_debrid(self) -> bool:
        return bool(self.real_debrid_token)
    
    @property
    def has_torbox(self) -> bool:
        return bool(self.torbox_api_key)
    
    @property
    def has_plex(self) -> bool:
        return bool(self.plex_token)
    
    @property
    def has_prowlarr(self) -> bool:
        return bool(self.prowlarr_api_key)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
