import os
import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import Optional

class Settings(BaseModel):
    torbox_api_key: str = ""
    tmdb_api_key: str = ""
    plex_token: str = ""
    prowlarr_url: str = "http://prowlarr:9696"
    prowlarr_api_key: str = ""
    mount_path: str = "/mnt/torbox"
    symlink_path: str = "/mnt/media"

    # Advanced settings
    scan_interval: int = 15  # minutes
    quality_profile: str = "1080p" # Default target. If '1080p', avoids 4K.
    allow_4k: bool = False # Specific override

class ConfigManager:
    def __init__(self):
        self.config_path = Path(os.getenv("CONFIG_PATH", "./config")) / "config.yaml"
        self.settings = Settings()
        self.load()

    def load(self):
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    self.settings = self.settings.copy(update=data)
        else:
            self.save()

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self.settings.dict(), f)

    def get(self) -> Settings:
        return self.settings

config = ConfigManager()
