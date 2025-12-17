# Torbox Plex Manager

This project is a self-hosted automation stack designed to manage your media library by integrating **Plex**, **Prowlarr**, and **Torbox**. It replaces solutions like Zurg/Riven with a lightweight, custom Python application.

## Features

*   **Plex Watchlist Sync**: Automatically fetches items from your Plex Watchlist.
*   **Automated Search**: Uses **Prowlarr** to search for torrents.
*   **Torbox Integration**:
    *   Checks Torbox cache for instant availability.
    *   Adds magnets to Torbox.
    *   Mounts Torbox WebDAV via **Rclone**.
*   **Smart Symlinking**: Automatically creates organized symlinks in `/mnt/media` (Movies, TV, Anime) pointing to the Rclone mount.
*   **Web Interface**: A clean dashboard to view status, search TMDB, and manually request items.
*   **Anime Support**: Preferentially selects "Dual-Audio" or "Dubbed" releases and organizes them into separate folders.
*   **Plex Media Server**: Optional built-in Plex server integration.

## Quick Start

The easiest way to get started is using the included setup script.

1.  **Clone the Repository**:
    ```bash
    git clone <repo_url>
    cd <repo_folder>
    ```

2.  **Run Setup**:
    ```bash
    ./setup.sh
    ```
    This script will:
    *   Create necessary directories.
    *   Ask for your API keys (Torbox, TMDB, Plex, Prowlarr).
    *   Configure Rclone for Torbox WebDAV (automatically obfuscating your password).
    *   Ask if you want to install/run the Plex Media Server container.
    *   Start the stack.

3.  **Access the UI**:
    *   **Manager Dashboard**: `http://<your-ip>:8000`
    *   **Prowlarr**: `http://<your-ip>:9696` (Configure indexers here first!)
    *   **Plex**: `http://<your-ip>:32400/web` (If enabled)

## Manual Configuration (Advanced)

If you prefer not to use the script, you can manually configure the stack.

1.  **Directories**: Create `config/rclone`, `data`, `media` folders.
2.  **Rclone**: Create `config/rclone/rclone.conf` with your Torbox WebDAV details.
3.  **App Config**: The app generates `config/config.yaml` on first run. Edit it to add your API keys.
4.  **Docker**: Run `docker-compose up -d`. Use `--profile plex` to include Plex.

## Workflow

1.  **Request**: Add a movie/show to your **Plex Watchlist** OR search and request via the **Web UI**.
2.  **Search**: The system detects the new item, checks if it's Anime, and searches Prowlarr.
3.  **Cache/Download**: It adds the best magnet to Torbox (preferring cached).
4.  **Symlink**: Once ready, it symlinks the file to:
    *   `/media/movies`
    *   `/media/tvshows`
    *   `/media/animemovies`
    *   `/media/animeshows`
5.  **Watch**: Plex scans the `/data/media` folder.

## Troubleshooting

*   **Logs**: `docker-compose logs -f app`
*   **Startup Crash**: Ensure `config/rclone/rclone.conf` exists.
*   **Prowlarr**: Ensure you have added indexers (like Torrentio) in Prowlarr and synced the API key.
