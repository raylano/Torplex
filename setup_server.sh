#!/bin/bash
#
# Torplex v2 - Snelle Server Setup
# Server: 159.195.20.247
#
# Gebruik: 
#   chmod +x setup_server.sh
#   sudo ./setup_server.sh
#

set -e

# Kleuren voor output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           Torplex v2 - Server Setup               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

# =====================================
# 1. STOP OUDE SERVICES
# =====================================
echo -e "${YELLOW}[1/7] Stoppen oude services...${NC}"

# Stop oude Docker containers (if any)
if docker ps -q 2>/dev/null | grep -q .; then
    echo "  Stoppen actieve containers..."
    docker stop $(docker ps -q) 2>/dev/null || true
fi

# Verwijder oude Torplex containers specifiek
for container in torplex_app torplex_rclone torplex_torbox_plex_manager rclone zurg; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "  Verwijderen oude container: $container"
        docker rm -f $container 2>/dev/null || true
    fi
done

# =====================================
# 2. UNMOUNT OUDE MOUNTS
# =====================================
echo -e "${YELLOW}[2/7] Unmounten oude mounts...${NC}"

# Check en unmount mogelijke oude mount points
MOUNT_POINTS=("/mnt/torbox" "/mnt/torplex" "/mnt/zurg" "/mnt/realdebrid" "/mnt/debrid")

for mount_point in "${MOUNT_POINTS[@]}"; do
    if mountpoint -q "$mount_point" 2>/dev/null; then
        echo "  Unmounting: $mount_point"
        fusermount -uz "$mount_point" 2>/dev/null || umount -l "$mount_point" 2>/dev/null || true
        sleep 1
    fi
done

# Kill eventuele rclone processen
pkill -9 rclone 2>/dev/null || true

echo -e "${GREEN}  ✓ Oude mounts verwijderd${NC}"

# =====================================
# 3. FUSE CONFIGURATIE
# =====================================
echo -e "${YELLOW}[3/7] Configureren FUSE...${NC}"

# Zorg dat user_allow_other is ingeschakeld
if ! grep -q "user_allow_other" /etc/fuse.conf 2>/dev/null; then
    echo "user_allow_other" >> /etc/fuse.conf
    echo "  Toegevoegd: user_allow_other aan /etc/fuse.conf"
fi

# Controleer of fuse module is geladen
if ! lsmod | grep -q fuse; then
    modprobe fuse
    echo "  Geladen: FUSE kernel module"
fi

echo -e "${GREEN}  ✓ FUSE geconfigureerd${NC}"

# =====================================
# 4. DIRECTORIES AANMAKEN
# =====================================
echo -e "${YELLOW}[4/7] Aanmaken directories...${NC}"

# Maak mount directory
mkdir -p /mnt/torplex
chmod 755 /mnt/torplex

# Bind mount voor Docker propagation
mount --bind /mnt/torplex /mnt/torplex 2>/dev/null || true
mount --make-shared /mnt/torplex 2>/dev/null || true

# Project directory
INSTALL_DIR="/opt/torplex"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Media directories
mkdir -p data/{postgres,media/{movies,tvshows,anime_movies,anime_shows}}
mkdir -p config/{zurg,rclone,prowlarr,plex}

echo -e "${GREEN}  ✓ Directories aangemaakt${NC}"

# =====================================
# 5. CONFIGURATIE BESTANDEN
# =====================================
echo -e "${YELLOW}[5/7] Schrijven configuratie bestanden...${NC}"

# .env bestand met API keys
cat > .env << 'EOF'
# Database
DB_PASSWORD=torplex_secure_2024_prod

# Debrid Services
REAL_DEBRID_TOKEN=3OD7IJCMQMDCY5RONRDSCGKWCA4JGOQJU3KJVVYUYET5WA7FBVKA
TORBOX_API_KEY=

# Media APIs
TMDB_API_KEY=f25bb463a5d9808acf4d1cc527f36884
PLEX_TOKEN=
PLEX_URL=http://localhost:32400

# Prowlarr (vul in na eerste start)
PROWLARR_URL=http://prowlarr:9696
PROWLARR_API_KEY=

# Paths
MOUNT_PATH=/mnt/zurg
SYMLINK_PATH=/mnt/media

# Environment
TZ=Europe/Amsterdam
PUID=1000
PGID=1000
EOF

echo "  ✓ .env aangemaakt"

# Zurg configuratie
cat > config/zurg/config.yml << 'EOF'
zurg: v1

# Real-Debrid Token (wordt overschreven door env var)
token: "3OD7IJCMQMDCY5RONRDSCGKWCA4JGOQJU3KJVVYUYET5WA7FBVKA"

# Server Configuration
host: "[::]"
port: 9999
concurrent_workers: 8
check_for_changes_every_secs: 15

# Naming Options
retain_rd_torrent_name: false
retain_folder_name_extension: false
ignore_renames: true

# Directory Structure with Priority-Based Filtering
directories:
  # Anime Detection (highest priority)
  anime:
    group: media
    group_order: 10
    filters:
      - regex: /\[([A-Fa-f0-9]{8})\]/
      - any_file_inside_regex: /\[([A-Fa-f0-9]{8})\]/
      - regex: /\[(SubsPlease|Erai-raws|ASW|Judas|Ember|EMBER)\]/i
      - any_file_inside_regex: /\[(SubsPlease|Erai-raws|ASW|Judas|Ember|EMBER)\]/i

  # TV Shows (second priority)
  shows:
    group: media
    group_order: 20
    filters:
      - has_episodes: true

  # Movies (lowest priority, catch-all)
  movies:
    group: media
    group_order: 30
    only_show_the_biggest_file: true
    filters:
      - regex: /.*/
EOF

echo "  ✓ Zurg config aangemaakt"

# Rclone configuratie
cat > config/rclone/rclone.conf << 'EOF'
[zurg]
type = webdav
url = http://zurg:9999/dav
vendor = other
EOF

echo "  ✓ Rclone config aangemaakt"

echo -e "${GREEN}  ✓ Configuratie bestanden geschreven${NC}"

# =====================================
# 6. DOCKER COMPOSE
# =====================================
echo -e "${YELLOW}[6/7] Schrijven docker-compose.yml...${NC}"

cat > docker-compose.yml << 'DOCKEREOF'
services:
  # ============================================================================
  # DATABASE
  # ============================================================================
  postgres:
    image: postgres:16-alpine
    container_name: torplex_db
    restart: unless-stopped
    environment:
      POSTGRES_USER: torplex
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: torplex
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U torplex"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - torplex_net

  # ============================================================================
  # ZURG - Real-Debrid WebDAV Gateway
  # ============================================================================
  zurg:
    image: ghcr.io/debridmediamanager/zurg-testing:latest
    container_name: torplex_zurg
    restart: unless-stopped
    ports:
      - "9999:9999"
    volumes:
      - ./config/zurg:/app/config
      - ./data/zurg:/app/data
    environment:
      - ZURG_TOKEN=${REAL_DEBRID_TOKEN}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9999/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - torplex_net

  # ============================================================================
  # RCLONE - FUSE Mount Provider
  # ============================================================================
  rclone:
    image: rclone/rclone:latest
    container_name: torplex_rclone
    restart: unless-stopped
    devices:
      - /dev/fuse:/dev/fuse
    cap_add:
      - SYS_ADMIN
    security_opt:
      - apparmor:unconfined
    environment:
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
    volumes:
      - ./config/rclone:/config/rclone
      - /mnt/torplex:/data:rshared
      - /etc/passwd:/etc/passwd:ro
      - /etc/group:/etc/group:ro
    command: >
      mount zurg: /data
      --allow-other
      --allow-non-empty
      --vfs-cache-mode full
      --vfs-cache-max-size 50G
      --vfs-read-ahead 128M
      --dir-cache-time 1000h
      --buffer-size 32M
      --log-level INFO
    depends_on:
      zurg:
        condition: service_healthy
    networks:
      - torplex_net

  # ============================================================================
  # BACKEND - FastAPI Application
  # ============================================================================
  backend:
    image: python:3.11-slim
    container_name: torplex_backend
    restart: unless-stopped
    working_dir: /app
    environment:
      - DATABASE_URL=postgresql+asyncpg://torplex:${DB_PASSWORD}@postgres:5432/torplex
      - REAL_DEBRID_TOKEN=${REAL_DEBRID_TOKEN}
      - TORBOX_API_KEY=${TORBOX_API_KEY}
      - TMDB_API_KEY=${TMDB_API_KEY}
      - PLEX_TOKEN=${PLEX_TOKEN}
      - PLEX_URL=${PLEX_URL}
      - PROWLARR_URL=${PROWLARR_URL}
      - PROWLARR_API_KEY=${PROWLARR_API_KEY}
      - MOUNT_PATH=/mnt/zurg
      - SYMLINK_PATH=/mnt/media
      - TZ=${TZ:-Europe/Amsterdam}
    volumes:
      - ./backend:/app
      - /mnt/torplex:/mnt/zurg:rslave
      - ./data/media:/mnt/media
    ports:
      - "8000:8000"
    command: >
      bash -c "pip install -q -r requirements.txt && 
               python -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
    depends_on:
      postgres:
        condition: service_healthy
      rclone:
        condition: service_started
    networks:
      - torplex_net

  # ============================================================================
  # FRONTEND - Next.js Application
  # ============================================================================
  frontend:
    image: node:20-alpine
    container_name: torplex_frontend
    restart: unless-stopped
    working_dir: /app
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    volumes:
      - ./frontend:/app
    ports:
      - "3000:3000"
    command: >
      sh -c "npm install && npm run dev"
    depends_on:
      - backend
    networks:
      - torplex_net

  # ============================================================================
  # PROWLARR - Indexer Manager
  # ============================================================================
  prowlarr:
    image: lscr.io/linuxserver/prowlarr:latest
    container_name: torplex_prowlarr
    restart: unless-stopped
    environment:
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
      - TZ=${TZ:-Europe/Amsterdam}
    volumes:
      - ./config/prowlarr:/config
    ports:
      - "9696:9696"
    networks:
      - torplex_net

  # ============================================================================
  # FLARESOLVERR - Cloudflare Bypass
  # ============================================================================
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: torplex_flaresolverr
    restart: unless-stopped
    environment:
      - LOG_LEVEL=info
    ports:
      - "8191:8191"
    networks:
      - torplex_net

networks:
  torplex_net:
    driver: bridge
DOCKEREOF

echo -e "${GREEN}  ✓ docker-compose.yml geschreven${NC}"

# =====================================
# 7. STARTEN
# =====================================
echo -e "${YELLOW}[7/7] Starten Torplex stack...${NC}"

# Pull images
echo "  Pullen Docker images..."
docker-compose pull

# Start services
echo "  Starten services..."
docker-compose up -d

# Wacht even
sleep 5

# Status check
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  STATUS                           ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

docker-compose ps

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Torplex v2 is gestart!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Frontend:${NC}    http://$(hostname -I | awk '{print $1}'):3000"
echo -e "  ${BLUE}Backend API:${NC} http://$(hostname -I | awk '{print $1}'):8000"
echo -e "  ${BLUE}API Docs:${NC}    http://$(hostname -I | awk '{print $1}'):8000/docs"
echo -e "  ${BLUE}Prowlarr:${NC}    http://$(hostname -I | awk '{print $1}'):9696"
echo -e "  ${BLUE}Zurg:${NC}        http://$(hostname -I | awk '{print $1}'):9999"
echo ""
echo -e "${YELLOW}📝 Volgende stappen:${NC}"
echo "  1. Open Prowlarr en configureer indexers"
echo "  2. Kopieer Prowlarr API key naar .env"
echo "  3. Voeg optioneel Plex Token toe"
echo "  4. Herstart: docker-compose restart backend"
echo ""
echo -e "${YELLOW}📁 Logs bekijken:${NC}"
echo "  docker-compose logs -f"
echo "  docker-compose logs -f backend"
echo ""
echo -e "${YELLOW}🔧 Mount controleren:${NC}"
echo "  ls -la /mnt/torplex/"
echo ""
