# Debrid Media Stack - Setup Guide

## 🎯 Overzicht

Deze stack automatiseert het hele proces van Plex Watchlist → Download → Plex Library.

```
┌─────────────────┐     ┌──────────┐     ┌────────────────┐
│  Plex Watchlist │────▶│ Pulsarr  │────▶│ Sonarr/Radarr  │
└─────────────────┘     └──────────┘     └───────┬────────┘
                                                  │
        ┌──────────────────────┐                  │
        │      Jellyseerr      │◀─ Requests ──────┘
        │  (voor vrienden/fam) │                  │
        └──────────────────────┘                  ▼
                                          ┌──────────────┐
┌─────────────┐                           │   Prowlarr   │
│    Plex     │◀── Symlinks ──┐          └──────┬───────┘
└─────────────┘               │                 │ Indexers
        ▲                     │                 ▼
        │              ┌──────────────┐   ┌──────────────┐
        │              │  Decypharr   │◀──│   Torrents   │
        │              └──────┬───────┘   │   Usenet     │
        │                     │           └──────────────┘
        │                     ▼
        │              ┌──────────────┐
        └── Mount ─────│RD / TorBox   │
                       │   (cloud)    │
                       └──────────────┘
```

---

## 🚀 Stap 1: Voorbereiding

### 1.1 Kopieer .env.example naar .env
```bash
cd ~/Documents/GitHub/Torplex
cp .env.example .env
nano .env  # Of gebruik je favoriete editor
```

### 1.2 Vul je tokens in
Je hebt nodig:
- **REAL_DEBRID_TOKEN**: https://real-debrid.com/apitoken
- **TORBOX_API_KEY**: https://torbox.app/settings
- **TORBOX_EMAIL**: Je TorBox email
- **PLEX_TOKEN**: https://www.plexopedia.com/plex-media-server/general/plex-token/
- **TMDB_API_KEY**: https://www.themoviedb.org/settings/api

> ⚠️ **De API keys voor Sonarr/Radarr worden pas beschikbaar NA het eerste opstarten!**

---

## 🚀 Stap 2: Eerste Start

```bash
# Start alle containers
docker-compose up -d

# Bekijk logs (optioneel)
docker-compose logs -f
```

Wacht ~2 minuten tot alles is opgestart.

---

## 🔧 Stap 3: Configuratie

### 3.1 Prowlarr → Sonarr/Radarr Koppeling

1. Open **Prowlarr**: http://localhost:9696
2. Ga naar `Settings` → `Apps`
3. Klik `+` om toe te voegen:

**Sonarr**:
| Veld | Waarde |
|------|--------|
| Name | Sonarr |
| Sync Level | Add and Remove Only |
| Prowlarr Server | http://prowlarr:9696 |
| Sonarr Server | http://sonarr:8989 |
| API Key | *(kopieer van Sonarr, zie 3.2)* |

**Radarr**:
| Veld | Waarde |
|------|--------|
| Name | Radarr |
| Sync Level | Add and Remove Only |
| Prowlarr Server | http://prowlarr:9696 |
| Radarr Server | http://radarr:7878 |
| API Key | *(kopieer van Radarr, zie 3.2)* |

---

### 3.2 Sonarr Configuratie

1. Open **Sonarr**: http://localhost:8989
2. **API Key ophalen**: `Settings` → `General` → `Security` → Kopieer API Key
3. **Download Client toevoegen**:
   - Ga naar `Settings` → `Download Clients`
   - Klik `+` → `qBittorrent`
   
| Veld | Waarde |
|------|--------|
| Name | Decypharr |
| Host | decypharr |
| Port | 8282 |
| Username | admin |
| Password | adminadmin |
| Category | tv |

4. **Root Folder instellen**:
   - Ga naar `Settings` → `Media Management`
   - Voeg Root Folder toe: `/data/media/shows`

---

### 3.3 Radarr Configuratie

1. Open **Radarr**: http://localhost:7878
2. **API Key ophalen**: `Settings` → `General` → `Security` → Kopieer API Key
3. **Download Client toevoegen** (zelfde als Sonarr):
   
| Veld | Waarde |
|------|--------|
| Name | Decypharr |
| Host | decypharr |
| Port | 8282 |
| Username | admin |
| Password | adminadmin |
| Category | movies |

4. **Root Folder instellen**: `/data/media/movies`

---

### 3.4 Update .env met API Keys

Nu je de API keys hebt, update je `.env`:
```bash
nano .env
# Vul in:
# SONARR_API_KEY=<jouw key>
# RADARR_API_KEY=<jouw key>
```

---

### 3.5 Pulsarr Configuratie

1. Open **Pulsarr**: http://localhost:3003
2. Volg de setup wizard:
   - Koppel je Plex account
   - Voeg Sonarr toe (http://sonarr:8989 + API key)
   - Voeg Radarr toe (http://radarr:7878 + API key)
   - Stel sync interval in (5 minuten aanbevolen)

---

### 3.6 Jellyseerr Configuratie

1. Open **Jellyseerr**: http://localhost:5055
2. Selecteer **Plex** als media server
3. Login met je Plex account
4. Configureer Sonarr:
   - URL: http://sonarr:8989
   - API Key: jouw Sonarr API key
   - Root Folder: /data/media/shows
   
5. Configureer Radarr:
   - URL: http://radarr:7878
   - API Key: jouw Radarr API key
   - Root Folder: /data/media/movies

---

### 3.7 Plex Library Setup

1. Open **Plex**: http://localhost:32400/web
2. Voeg libraries toe:
   - **Films**: `/data/media/movies`
   - **TV Series**: `/data/media/shows`
   - **Anime**: `/data/media/anime` (optioneel)

---

## ✅ Stap 4: Testen

### Test 1: Watchlist Sync
1. Voeg een film toe aan je Plex Watchlist
2. Wacht 5 minuten (of check Pulsarr logs)
3. Controleer of de film in Radarr staat

### Test 2: Download Test
1. In Radarr, selecteer een film
2. Klik `Search` → selecteer een release
3. Controleer:
   - Decypharr UI (http://localhost:8282)
   - `./data/media/movies/` voor symlinks

### Test 3: Plex Scan
1. Trigger library scan in Plex
2. Film zou moeten verschijnen

---

## 🔌 Poorten Overzicht

| Service | Poort | URL |
|---------|-------|-----|
| Plex | 32400 | http://localhost:32400/web |
| Sonarr | 8989 | http://localhost:8989 |
| Radarr | 7878 | http://localhost:7878 |
| Prowlarr | 9696 | http://localhost:9696 |
| Jellyseerr | 5055 | http://localhost:5055 |
| Pulsarr | 3003 | http://localhost:3003 |
| Decypharr | 8282 | http://localhost:8282 |
| FlareSolverr | 8191 | http://localhost:8191 |
| Zurg | 9999 | http://localhost:9999 |

---

## 🔄 Rollback naar Torplex

Als je terug wilt naar je originele Torplex setup:
```bash
cp docker-compose.yml.backup.torplex docker-compose.yml
docker-compose up -d
```

---

## ❓ Troubleshooting

### Symlinks werken niet
- Controleer of `/mnt/torplex` correct gemount is
- Run: `ls -la /mnt/torplex`

### Decypharr vindt geen bestanden
- Controleer of rclone correct draait: `docker logs torplex_rclone`
- Wacht 60 seconden na container start

### Plex ziet content niet
- Trigger handmatige library scan
- Controleer dat Plex toegang heeft tot `/data/media`
