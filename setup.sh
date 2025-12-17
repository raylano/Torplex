#!/bin/bash

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Torbox Plex Manager Setup ===${NC}"

# 1. Create Directories
echo -e "${GREEN}Creating directories...${NC}"
mkdir -p config/rclone
mkdir -p data
mkdir -p media/movies
mkdir -p media/tvshows
mkdir -p media/animeshows
mkdir -p media/animemovies
mkdir -p plex/config
mkdir -p plex/transcode

# 2. Configuration
CONFIG_FILE="config/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${BLUE}Configuring Application...${NC}"
    read -p "Torbox API Key: " TORBOX_KEY
    read -p "TMDB API Key: " TMDB_KEY
    read -p "Plex Token (X-Plex-Token): " PLEX_TOKEN
    read -p "Prowlarr URL (default: http://prowlarr:9696): " PROWLARR_URL
    PROWLARR_URL=${PROWLARR_URL:-http://prowlarr:9696}
    read -p "Prowlarr API Key: " PROWLARR_KEY

    cat > "$CONFIG_FILE" <<EOL
torbox_api_key: "$TORBOX_KEY"
tmdb_api_key: "$TMDB_KEY"
plex_token: "$PLEX_TOKEN"
prowlarr_url: "$PROWLARR_URL"
prowlarr_api_key: "$PROWLARR_KEY"
quality_profile: "1080p"
allow_4k: false
mount_path: "/mnt/torbox"
symlink_path: "/mnt/media"
scan_interval: 15
EOL
    echo -e "${GREEN}Config saved.${NC}"
else
    echo -e "${GREEN}Config file exists, skipping.${NC}"
fi

# 3. Rclone Setup
RCLONE_CONF="config/rclone/rclone.conf"
if [ ! -f "$RCLONE_CONF" ]; then
    echo -e "${BLUE}Configuring Torbox WebDAV (Rclone)...${NC}"
    echo "This requires your Torbox email and WebDAV password."
    read -p "Torbox Email: " TB_USER
    read -s -p "Torbox WebDAV Password: " TB_PASS
    echo ""

    # We need to obscure the password for rclone.
    # We can use a temporary docker container to do this.
    echo -e "${BLUE}Obscuring password...${NC}"
    if command -v docker &> /dev/null; then
        OBSCURED_PASS=$(docker run --rm rclone/rclone:latest obscure "$TB_PASS" 2>/dev/null)
        if [ -z "$OBSCURED_PASS" ]; then
             echo "Failed to obscure password via Docker. Falling back to plain (might not work depending on rclone version/config)."
             OBSCURED_PASS="$TB_PASS"
        fi
    else
        echo "Docker not found (weird, since you need it). Using plain password."
        OBSCURED_PASS="$TB_PASS"
    fi

    cat > "$RCLONE_CONF" <<EOL
[torbox]
type = webdav
url = https://webdav.torbox.app/
vendor = other
user = $TB_USER
pass = $OBSCURED_PASS
EOL
    echo -e "${GREEN}Rclone config generated.${NC}"
else
    echo -e "${GREEN}Rclone config exists, skipping.${NC}"
fi

# 4. Plex Setup
echo -e "${BLUE}Do you want to enable the built-in Plex Media Server? (y/n)${NC}"
read -p "> " INSTALL_PLEX

if [[ "$INSTALL_PLEX" =~ ^[Yy]$ ]]; then
    export ENABLE_PLEX=true
    # Generate a claim token link for convenience
    echo -e "${BLUE}To claim your server, get a token from https://www.plex.tv/claim${NC}"
    read -p "Enter Plex Claim Token (optional, press enter to skip): " PLEX_CLAIM
    export PLEX_CLAIM="$PLEX_CLAIM"

    # We need to write a .env file for docker-compose to pick up conditional profiles or vars
    echo "COMPOSE_PROFILES=plex" > .env
    echo "PLEX_CLAIM=$PLEX_CLAIM" >> .env
else
    echo "COMPOSE_PROFILES=core" > .env
fi

# 5. Start
echo -e "${BLUE}Setup complete. Starting services...${NC}"

# Cleanup old/conflicting containers
echo -e "${BLUE}Cleaning up old containers...${NC}"
docker rm -f prowlarr torplex_prowlarr 2>/dev/null || true
docker rm -f rclone_mount torplex_rclone 2>/dev/null || true
docker rm -f torbox_plex_manager torplex_torbox_plex_manager 2>/dev/null || true

# Cleanup potential stale mounts on host
echo -e "${BLUE}Cleaning up stale mounts...${NC}"
sudo umount -l /mnt/torbox 2>/dev/null || true
sudo fusermount -uz /mnt/torbox 2>/dev/null || true

# Create host mount point for rclone FUSE
echo -e "${BLUE}Creating mount points...${NC}"
sudo mkdir -p /mnt/torbox
sudo chmod 777 /mnt/torbox

docker compose build --no-cache
docker compose up -d

echo -e "${GREEN}Stack is running!${NC}"
echo -e "Manager UI: http://localhost:8000"
echo -e "Prowlarr:   http://localhost:9696"
if [[ "$INSTALL_PLEX" =~ ^[Yy]$ ]]; then
    echo -e "Plex:       http://localhost:32400/web"
fi
