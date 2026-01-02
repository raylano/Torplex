# Torplex v2

> 🎬 **Media Automation Platform** with Real-Debrid & Torbox support

Torplex is a self-hosted media automation system that integrates with debrid services to stream content through Plex. It features automatic content discovery, torrent scraping with quality preferences, and intelligent anime handling.

## ✨ Features

- **Dual Debrid Support**: Real-Debrid and Torbox with automatic fallback
- **Plex Watchlist Sync**: Automatically process items from your Plex Watchlist
- **Smart Scraping**: Torrentio + Prowlarr integration
- **Anime Preferences**: Prioritizes Dual-Audio and Dubbed releases
- **Quality Ranking**: Intelligent torrent selection based on resolution, codec, and source
- **Modern UI**: Beautiful dashboard with TMDB metadata and posters
- **State Machine**: Robust processing pipeline with retry logic

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                    │
│  Dashboard │ Library │ Search │ Settings                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  TMDB    │  │ Scrapers │  │ Debrid   │  │ Symlink  │    │
│  │ Service  │  │Torrentio │  │ RD + TB  │  │ Manager  │    │
│  └──────────┘  │ Prowlarr │  └──────────┘  └──────────┘    │
│                └──────────┘                                  │
│                       State Machine + Scheduler              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  PostgreSQL │ Zurg (WebDAV) │ Rclone (FUSE) │ Symlinks      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                         Plex Media Server
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Linux server with FUSE support
- Real-Debrid and/or Torbox subscription
- TMDB API key

### 1. Clone and Configure

```bash
git clone <repository>
cd Torplex

# Copy and edit environment file
cp .env.example .env
nano .env
```

Add your API keys:
```env
REAL_DEBRID_TOKEN=your_token_here
TORBOX_API_KEY=your_key_here
TMDB_API_KEY=your_tmdb_key
```

### 2. Prepare Host (Linux)

```bash
# Enable FUSE for non-root users
sudo sh -c 'echo "user_allow_other" >> /etc/fuse.conf'

# Create mount directory
sudo mkdir -p /mnt/torplex
sudo mount --bind /mnt/torplex /mnt/torplex
sudo mount --make-shared /mnt/torplex
```

### 3. Start the Stack

```bash
docker-compose up -d

# Watch logs
docker-compose logs -f
```

### 4. Access

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Prowlarr**: http://localhost:9696

## 📁 Project Structure

```
Torplex/
├── backend/              # FastAPI Python backend
│   ├── src/
│   │   ├── main.py       # Application entry
│   │   ├── config.py     # Settings management
│   │   ├── database.py   # SQLAlchemy setup
│   │   ├── models/       # Database models
│   │   ├── services/     # Business logic
│   │   ├── core/         # State machine, scheduler
│   │   └── routers/      # API endpoints
│   └── Dockerfile
│
├── frontend/             # Next.js frontend
│   ├── src/
│   │   ├── app/          # Pages
│   │   ├── components/   # React components
│   │   └── lib/          # API client
│   └── Dockerfile
│
├── config/               # Service configurations
│   ├── zurg/             # Zurg config
│   └── rclone/           # Rclone config
│
└── docker-compose.yml    # Orchestration
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `REAL_DEBRID_TOKEN` | Real-Debrid API token | Recommended |
| `TORBOX_API_KEY` | Torbox API key | Optional |
| `TMDB_API_KEY` | TMDB API key for metadata | Yes |
| `PLEX_TOKEN` | Plex token for watchlist sync | Optional |
| `PROWLARR_API_KEY` | Prowlarr API key | Optional |

### Anime Preferences

The quality ranker automatically detects anime and applies special scoring:
1. **Cached + Dual-Audio**: Highest priority
2. **Cached + Dubbed**: Second priority
3. **Dual-Audio** (non-cached)
4. **Dubbed** (non-cached)
5. **Cached** (any audio)
6. **Best quality** (non-cached)

## 🔄 Processing Pipeline

```
REQUESTED → INDEXED → SCRAPED → DOWNLOADED → SYMLINKED → COMPLETED
    │           │          │          │            │           │
    ▼           ▼          ▼          ▼            ▼           ▼
  Added     Metadata   Torrents    Added to    Symlink     Plex
  to queue   from      found &     debrid      created     refreshed
            TMDB       ranked      service
```

## 🛠️ Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 📝 License

MIT License - see LICENSE file for details.

## 🙏 Credits

- Inspired by [Riven](https://github.com/rivenmedia/riven)
- Uses [Torrentio](https://torrentio.strem.fun) for stream discovery
- TMDB for metadata
