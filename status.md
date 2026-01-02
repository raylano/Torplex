# Torplex Status Report - 2026-01-02

## ✅ Huidige Status: WERKEND
**Doel:** Volledige automatisering van Real-Debrid en TorBox via symlinks.
**Status:** Symlinks werken correct met Decypharr + externe rclone mounts.

---

## 🏗️ Architectuur

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    Zurg     │────▶│   rclone    │────▶│ /mnt/torplex│
│  (RD WebDAV)│     │ (FUSE mount)│     │   (host)    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │ rslave
┌─────────────┐     ┌─────────────┐     ┌──────▼──────┐
│   Radarr/   │◀────│  Decypharr  │◀────│ /mnt/torplex│
│   Sonarr    │     │ (symlinks)  │     │ (container) │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## 🔄 Herstart Procedures

### Complete Stack Herstart
```bash
cd ~/Torplex

# 1. Stop alles
docker compose down

# 2. Unmount stale FUSE mounts
sudo fusermount -uz /mnt/torplex/zurg
sudo fusermount -uz /mnt/torplex/torbox

# 3. Start alles
docker compose up -d

# 4. Wacht op rclone init (60 sec)
sleep 75

# 5. Verifieer mounts
ls /mnt/torplex/zurg/__all__/ | head -5
```

### Alleen rclone Herstart (bij mount problemen)
```bash
sudo fusermount -uz /mnt/torplex/zurg
sudo fusermount -uz /mnt/torplex/torbox
docker restart torplex_rclone
sleep 75
ls /mnt/torplex/zurg/__all__/ | head -5
```

### Alleen Arrs Herstart (config wijzigingen)
```bash
docker compose up -d --force-recreate sonarr radarr sonarr-anime radarr-anime plex
```

---

## ⚠️ Bekende Problemen & Oplossingen

### 1. "Transport endpoint is not connected" / "Socket not connected"
**Oorzaak:** FUSE mount is gecrashed maar mount punt is nog geregistreerd.
```bash
sudo fusermount -uz /mnt/torplex/zurg
sudo fusermount -uz /mnt/torplex/torbox
docker restart torplex_rclone
sleep 75
```

### 2. Decypharr logt "Post-Download Action: Symlink" maar maakt geen symlink
**Oorzaak:** `folder` pad in config.json matcht niet met waar bestanden verschijnen.
**Fix:** Zorg dat `folder` wijst naar exacte locatie (bijv. `/mnt/torplex/zurg/__all__`).

### 3. Radarr/Sonarr ziet lege folder waar symlink zou moeten zijn
**Oorzaak A:** Container niet herstart na docker-compose wijziging.
```bash
docker compose up -d --force-recreate radarr sonarr
```
**Oorzaak B:** Symlink gemaakt maar Radarr database niet geüpdate.
- Ga naar film → klik 🔄 Refresh & Scan

### 4. Symlinks wijzen naar verkeerd pad
**Oorzaak:** Verschillende containers gebruiken verschillende mount paden.
**Fix:** Alle containers moeten zelfde pad gebruiken: `/mnt/torplex:/mnt/torplex`

### 5. Folder naming mismatch (Decypharr vs Radarr)
**Oorzaak:** Decypharr gebruikt torrent-naam, Radarr verwacht "Film (Jaar)" formaat.
**Workaround:** Handmatig hernoemen of in Radarr het pad aanpassen.

---

## 📋 Configuratie Referentie

### config/decypharr/config.json (kritieke velden)
```json
{
    "debrids": [
        {
            "name": "realdebrid",
            "folder": "/mnt/torplex/zurg/__all__"
        },
        {
            "name": "torbox", 
            "folder": "/mnt/torplex/torbox"
        }
    ],
    "rclone": {
        "enabled": false
    },
    "symlink": {
        "source": "/mnt/torplex/zurg/__all__",
        "destination": "/data/media"
    }
}
```

### docker-compose.yml (kritieke volumes)
```yaml
rclone:
  volumes:
    - /mnt/torplex:/data:rshared  # FUSE mount met propagation

decypharr:
  volumes:
    - /mnt/torplex:/mnt/torplex:rslave  # Ontvangt mount updates

plex/radarr/sonarr:
  volumes:
    - /mnt/torplex:/mnt/torplex:ro  # Leestoegang tot mounts
```

---

## 🌐 Applicatie URLs
| App | Poort | URL |
|-----|-------|-----|
| Plex | 32400 | `http://IP:32400/web` |
| Jellyseerr | 5055 | `http://IP:5055` |
| Radarr | 7878 | `http://IP:7878` |
| Radarr Anime | 7879 | `http://IP:7879` |
| Sonarr | 8989 | `http://IP:8989` |
| Sonarr Anime | 8990 | `http://IP:8990` |
| Prowlarr | 9696 | `http://IP:9696` |
| Decypharr | 8282 | `http://IP:8282` |

---
*Laatste update: 2026-01-02 11:25*

