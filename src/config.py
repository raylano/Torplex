import os
import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import Optional

class Settings(BaseModel):
    torbox_api_key: str = ""
    realdebrid_api_key: str = ""
    debrid_service: str = "torbox"  # 'torbox' or 'realdebrid'
    tmdb_api_key: str = ""
    plex_token: str = ""
    prowlarr_url: str = "http://prowlarr:9696"
    prowlarr_api_key: str = ""
    mount_path: str = "/mnt/torbox"
    symlink_path: str = "/mnt/media"

    # Advanced settings
    scan_interval: int = 15  # minutes
    quality_profile: str = "hd"  # 'hd', 'fhd', 'uhd'
    allow_4k: bool = False

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
                    self.settings = self.settings.model_copy(update=data)
        else:
            self.save()

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self.settings.model_dump(), f)

    def get(self) -> Settings:
        return self.settings

    def update(self, new_values: dict):
        """Update settings from a dictionary and save."""
        # Filter out empty strings for optional fields
        filtered = {k: v for k, v in new_values.items() if v != "" or k in ['plex_token', 'realdebrid_api_key']}
        self.settings = self.settings.model_copy(update=filtered)
        self.save()
        print(f"Config saved: {self.config_path}")

config = ConfigManager()

