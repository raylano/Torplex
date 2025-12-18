"""
Settings Router
Configuration management
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from src.config import settings as app_settings
from src.services.downloaders import real_debrid_service, torbox_service

router = APIRouter()


class ProviderStatus(BaseModel):
    name: str
    configured: bool
    connected: bool
    username: Optional[str] = None
    premium: bool = False
    premium_expires: Optional[str] = None


class SettingsResponse(BaseModel):
    providers: dict
    paths: dict
    intervals: dict


@router.get("/settings")
async def get_settings() -> SettingsResponse:
    """Get current settings (hides sensitive values)"""
    return SettingsResponse(
        providers={
            "real_debrid": {
                "configured": app_settings.has_real_debrid,
                "token_preview": app_settings.real_debrid_token[:8] + "..." if app_settings.real_debrid_token else None,
            },
            "torbox": {
                "configured": app_settings.has_torbox,
                "key_preview": app_settings.torbox_api_key[:8] + "..." if app_settings.torbox_api_key else None,
            },
            "tmdb": {
                "configured": bool(app_settings.tmdb_api_key),
            },
            "plex": {
                "configured": app_settings.has_plex,
                "url": app_settings.plex_url,
            },
            "prowlarr": {
                "configured": app_settings.has_prowlarr,
                "url": app_settings.prowlarr_url,
            },
        },
        paths={
            "mount_path": app_settings.mount_path,
            "symlink_path": app_settings.symlink_path,
        },
        intervals={
            "watchlist_scan_interval": app_settings.watchlist_scan_interval,
            "library_scan_interval": app_settings.library_scan_interval,
        },
    )


@router.get("/settings/providers/status")
async def get_provider_status():
    """Get connection status of all providers"""
    providers = []
    
    # Real-Debrid
    if app_settings.has_real_debrid:
        user_info = await real_debrid_service.get_user_info()
        if user_info:
            providers.append(ProviderStatus(
                name="Real-Debrid",
                configured=True,
                connected=True,
                username=user_info.get("username"),
                premium=user_info.get("premium", 0) > 0,
                premium_expires=user_info.get("expiration"),
            ))
        else:
            providers.append(ProviderStatus(
                name="Real-Debrid",
                configured=True,
                connected=False,
            ))
    else:
        providers.append(ProviderStatus(
            name="Real-Debrid",
            configured=False,
            connected=False,
        ))
    
    # Torbox
    if app_settings.has_torbox:
        user_info = await torbox_service.get_user_info()
        if user_info:
            providers.append(ProviderStatus(
                name="Torbox",
                configured=True,
                connected=True,
                username=user_info.get("email"),
                premium=user_info.get("plan", 0) > 0,
            ))
        else:
            providers.append(ProviderStatus(
                name="Torbox",
                configured=True,
                connected=False,
            ))
    else:
        providers.append(ProviderStatus(
            name="Torbox",
            configured=False,
            connected=False,
        ))
    
    return {"providers": [p.model_dump() for p in providers]}
