#!/usr/bin/env python3
"""
Plex Bulk Downloader
Downloads entire seasons from a Plex server
"""

import os
import sys
import requests
from pathlib import Path

# Configuration
PLEX_URL = "http://65.21.127.114:42418"
PLEX_TOKEN = "7XsBgMyRZG3bbXpoUh4t"
DOWNLOAD_DIR = Path("/root/downloads")

def get_libraries():
    """List all libraries on the server."""
    url = f"{PLEX_URL}/library/sections?X-Plex-Token={PLEX_TOKEN}"
    r = requests.get(url, headers={"Accept": "application/json"})
    data = r.json()
    
    libs = []
    for lib in data.get("MediaContainer", {}).get("Directory", []):
        libs.append({
            "key": lib["key"],
            "title": lib["title"],
            "type": lib["type"]
        })
    return libs

def search_show(library_key, query):
    """Search for a show in a library."""
    url = f"{PLEX_URL}/library/sections/{library_key}/search?query={query}&X-Plex-Token={PLEX_TOKEN}"
    r = requests.get(url, headers={"Accept": "application/json"})
    data = r.json()
    
    shows = []
    for item in data.get("MediaContainer", {}).get("Metadata", []):
        if item.get("type") == "show":
            shows.append({
                "key": item["ratingKey"],
                "title": item["title"],
                "year": item.get("year", "")
            })
    return shows

def get_seasons(show_key):
    """Get all seasons of a show."""
    url = f"{PLEX_URL}/library/metadata/{show_key}/children?X-Plex-Token={PLEX_TOKEN}"
    r = requests.get(url, headers={"Accept": "application/json"})
    data = r.json()
    
    seasons = []
    for item in data.get("MediaContainer", {}).get("Metadata", []):
        seasons.append({
            "key": item["ratingKey"],
            "title": item["title"],
            "index": item.get("index", 0)
        })
    return seasons

def get_episodes(season_key):
    """Get all episodes of a season."""
    url = f"{PLEX_URL}/library/metadata/{season_key}/children?X-Plex-Token={PLEX_TOKEN}"
    r = requests.get(url, headers={"Accept": "application/json"})
    data = r.json()
    
    episodes = []
    for item in data.get("MediaContainer", {}).get("Metadata", []):
        # Get the download URL
        media = item.get("Media", [{}])[0]
        part = media.get("Part", [{}])[0]
        file_path = part.get("key", "")
        
        episodes.append({
            "key": item["ratingKey"],
            "title": item.get("title", f"Episode {item.get('index', '?')}"),
            "index": item.get("index", 0),
            "file_key": file_path,
            "container": part.get("container", "mkv")
        })
    return episodes

def download_episode(episode, show_name, season_num):
    """Download a single episode."""
    if not episode["file_key"]:
        print(f"  ❌ No file found for: {episode['title']}")
        return False
    
    # Create download URL
    download_url = f"{PLEX_URL}{episode['file_key']}?X-Plex-Token={PLEX_TOKEN}"
    
    # Create filename
    safe_show = "".join(c for c in show_name if c.isalnum() or c in " -_").strip()
    filename = f"{safe_show} - S{season_num:02d}E{episode['index']:02d} - {episode['title']}.{episode['container']}"
    filename = "".join(c for c in filename if c.isalnum() or c in " -_.").strip()
    
    # Create directory
    output_dir = DOWNLOAD_DIR / safe_show / f"Season {season_num:02d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    
    if output_path.exists():
        print(f"  ⏭️  Already exists: {filename}")
        return True
    
    print(f"  ⬇️  Downloading: {filename}")
    
    try:
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192*1024):  # 8MB chunks
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = (downloaded / total) * 100
                        print(f"\r  ⬇️  {filename}: {pct:.1f}%", end="", flush=True)
            print()
        return True
    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        if output_path.exists():
            output_path.unlink()
        return False

def download_season(show_name, season_index, library_key=None):
    """Download an entire season."""
    print(f"\n🔍 Searching for '{show_name}'...")
    
    # Find the library
    if library_key is None:
        libs = get_libraries()
        for lib in libs:
            if lib["type"] == "show":
                library_key = lib["key"]
                break
    
    if not library_key:
        print("❌ No TV library found!")
        return
    
    # Search for the show
    shows = search_show(library_key, show_name)
    if not shows:
        print(f"❌ Show '{show_name}' not found!")
        return
    
    show = shows[0]  # Take first match
    print(f"✅ Found: {show['title']} ({show['year']})")
    
    # Get seasons
    seasons = get_seasons(show["key"])
    target_season = None
    for s in seasons:
        if s["index"] == season_index:
            target_season = s
            break
    
    if not target_season:
        print(f"❌ Season {season_index} not found!")
        print(f"   Available seasons: {[s['index'] for s in seasons]}")
        return
    
    print(f"📺 {target_season['title']}")
    
    # Get episodes
    episodes = get_episodes(target_season["key"])
    print(f"📝 Found {len(episodes)} episodes")
    
    # Download each episode
    success = 0
    for ep in sorted(episodes, key=lambda x: x["index"]):
        if download_episode(ep, show["title"], season_index):
            success += 1
    
    print(f"\n✅ Downloaded {success}/{len(episodes)} episodes")
    print(f"📁 Saved to: {DOWNLOAD_DIR / show['title']}")

def list_shows(library_key=None):
    """List all shows in the library."""
    libs = get_libraries()
    
    for lib in libs:
        if lib["type"] == "show":
            print(f"\n📚 Library: {lib['title']}")
            # This would need pagination for large libraries
            # For now just show the library exists
    
    print("\n💡 Use: python3 plex_downloader.py 'Show Name' <season_number>")

if __name__ == "__main__":
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    if len(sys.argv) < 2:
        print("🎬 Plex Bulk Downloader")
        print("=" * 40)
        print("\nUsage:")
        print("  python3 plex_downloader.py 'One Piece' 17")
        print("  python3 plex_downloader.py 'One Piece' 17 'Anime TV (Dubs)'")
        print("\nLibraries:")
        for lib in get_libraries():
            print(f"  - {lib['title']} ({lib['type']}) [key={lib['key']}]")
        sys.exit(0)
    
    show_name = sys.argv[1]
    season = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    library_name = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Find specific library if specified
    library_key = None
    if library_name:
        for lib in get_libraries():
            if lib["title"].lower() == library_name.lower():
                library_key = lib["key"]
                print(f"📚 Using library: {lib['title']}")
                break
        if not library_key:
            print(f"❌ Library '{library_name}' not found!")
            sys.exit(1)
    
    download_season(show_name, season, library_key)
