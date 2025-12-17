# Torbox Plex Manager

This project is a self-hosted automation stack designed to manage your media library by integrating **Plex**, **Prowlarr**, and **Torbox**. It replaces solutions like Zurg/Riven with a lightweight, custom Python application.

## Features

*   **Plex Watchlist Sync**: Automatically fetches items from your Plex Watchlist.
*   **Automated Search**: Uses **Prowlarr** to search for torrents.
*   **Torbox Integration**:
    *   Checks Torbox cache for instant availability.
    *   Adds magnets to Torbox.
    *   Mounts Torbox WebDAV via **Rclone**.
*   **Smart Symlinking**: Automatically creates organized symlinks (e.g., `/mnt/media/movies/Avatar (2009)/Avatar.mkv`) pointing to the Rclone mount, ready for Plex to scan.
*   **Web Interface**: A clean dashboard to view status, search TMDB, and manually request items.
*   **Anime Support**: Preferentially selects "Dual-Audio" or "Dubbed" releases for detected Anime content.

## Prerequisites

*   **Docker & Docker Compose** installed on your Linux VPS.
*   **Torbox Account** (with API Key).
*   **TMDB Account** (with API Key).
*   **Prowlarr** instance (managed within this stack or external).

## Installation

1.  **Clone the Repository** (or copy files to your VPS).
2.  **Configure Rclone**:
    *   Create a folder `config/rclone`.
    *   Create `config/rclone/rclone.conf`.
    *   Add your Torbox WebDAV configuration:
        ```ini
        [torbox]
        type = webdav
        url = https://webdav.torbox.app/
        vendor = other
        user = <YOUR_EMAIL>
        pass = <YOUR_WEBDAV_PASSWORD_ENCRYPTED_BY_RCLONE>
        ```
    *   *Tip*: Run `rclone config` locally to generate this block if needed.

3.  **Configure Environment**:
    *   Create `config/config.yaml` (optional, or rely on UI/Defaults).
    *   The app will generate a default config on first run in `config/config.yaml`.
    *   You need to edit `config/config.yaml` to set your API keys:
        ```yaml
        torbox_api_key: "your_key"
        tmdb_api_key: "your_key"
        plex_token: "your_token"
        prowlarr_url: "http://prowlarr:9696"
        prowlarr_api_key: "your_prowlarr_key"
        quality_profile: "1080p" # or 4k
        ```

4.  **Start the Stack**:
    ```bash
    docker-compose up -d
    ```

5.  **Setup Prowlarr**:
    *   Access Prowlarr at `http://<your-ip>:9696`.
    *   Add your indexers (e.g., Torrentio, 1337x, etc.).
    *   Get your API Key from Settings -> General.
    *   Update `config/config.yaml` with the API key and restart the app container.

## Workflow

1.  **Request**: Add a movie/show to your **Plex Watchlist** OR search and request via the **Web UI** (`http://<your-ip>:8000`).
2.  **Search**: The system detects the new item, determines if it is Anime (to prefer Dual-Audio/Dub), and searches Prowlarr.
3.  **Cache Check**: It checks if the best results are already cached on Torbox.
4.  **Download/Cache**: It adds the magnet to Torbox.
5.  **Symlink**: Once the file is ready (cached or downloaded), it creates a symlink in `/mnt/media`.
6.  **Watch**: Plex scans the `/mnt/media` folder and the content appears in your library.

## Troubleshooting

*   **Logs**: `docker-compose logs -f app`
*   **Startup Crash**: Ensure `config/rclone/rclone.conf` exists and is valid.
*   **No Results**: Check Prowlarr indexers and Prowlarr connectivity.
