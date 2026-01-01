# Torplex Status Report - 2026-01-01

## 🎯 Doelstelling
Volledige automatisering van Usenet (TorBox) en Torrent (Real-Debrid/TorBox) workflows binnen het Torplex ecosysteem.

## ✅ FIXES TOEGEPAST (2026-01-01 22:30)

### 1. Decypharr Config Fix
**Probleem**: Real-Debrid `mount_folder` was `/mnt/debrid/__all__` maar Zurg creëert submappen (`anime/`, `shows/`, `movies/`), niet `__all__`.
**Fix**: Gewijzigd naar `/mnt/debrid` zodat Decypharr in alle Zurg submappen kan zoeken.

### 2. Rclone Mount Propagatie Fix
**Probleem**: Host `/mnt/torplex` zag bestanden niet die container wel zag.
**Fixes**:
- `privileged: true` toegevoegd aan rclone container voor betere FUSE permissies
- Mount propagatie gewijzigd van `rshared` naar `shared` voor bidirectionele propagatie
- Decypharr mount gewijzigd naar `rslave` (ontvangt mount updates van rclone)

## ⏭️ Herstart Instructies

```bash
# 1. Stop alle containers
docker compose down

# 2. Unmount eventuele zombie mounts op de host
sudo umount -l /mnt/torplex 2>/dev/null || true

# 3. Maak mount point aan met juiste permissies
sudo mkdir -p /mnt/torplex
sudo chmod 755 /mnt/torplex

# 4. Start services opnieuw
docker compose up -d

# 5. Wacht ~90 seconden (60s Zurg init + 30s rclone mount)
sleep 90

# 6. Controleer mount op host
ls -la /mnt/torplex/

# 7. Check Decypharr logs voor symlink creatie
docker logs torplex_decypharr --tail 50
```

## 📊 Wat wél werkt (Technische Backend)
- **Zurg**: ✅ Ingelogd & Library Sync werkt (4800+ torrents).
- **TorBox API**: ✅ Connectie werkt (`rclone lsd` geeft geen fout).
- **Interne Rclone Link**: ✅ Container ziet *wel* alle bestanden (`rclone ls combined` toont alles).

## 🔑 API Keys (In gebruik)
| Service | Key / Config |
| :--- | :--- |
| **Real-Debrid** | `3OD7IJCMQMDCY5RONRDSCGKWCA4JGOQJU3KJVVYUYET5WA7FBVKA` |
| **TorBox API** | `82e025a0-193a-4d67-ab3d-4cd935502ba9` |
| **TorBox Email** | `sir.re4per@gmail.com` |
| **Plex Token** | `s34Tt9zWemQMRGzU9RB2` |
| **Sonarr API** | `b50da35e35784b80a802eee4fac1d07c` |
| **Radarr API** | `094b3624fdb54527a7f2d6e460ecef89` |

---
*Status: FIXES TOEGEPAST - Wacht op herstart om te valideren.*
