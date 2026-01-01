# Torplex Status Report - 2026-01-01

## 🎯 Doelstelling
Volledige automatisering van Usenet (TorBox) en Torrent (Real-Debrid/TorBox) workflows binnen het Torplex ecosysteem.

## 🔴 CRITIQUE PROBLEMEN (Huidige situatie)
Hier loopt het systeem momenteel vast:
1.  **Mount Problemen op Host**: ❌
    - De `/mnt/torplex` map toont op de host nog **niet** de TorBox bestanden, ook al ziet de container ze wel. Dit blokkeert alles.
2.  **Geen Symlinks**: ❌
    - Decypharr maakt **geen symlinks** aan. Omdat hij de bestanden niet (goed) ziet via de mount, kan hij ze niet verwerken.
3.  **Plex is Leeg**: ❌
    - Gevolg van punt 1 en 2: Plex ziet geen films/series en de library blijft leeg.

## 📊 Wat wél werkt (Technische Backend)
Deze onderdelen zijn gerepareerd en staan klaar, maar wachten op de mount-fix:
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

## ⏭️ Volgende Acties (Bij herstart)
Het probleem zit in de **synchronisatie tussen Docker en de Host pc**.
1.  **Rclone Herstarten**: Forceer de mount om te verversen (`docker compose restart rclone`).
2.  **Mount Controleren**: Check of `/mnt/torplex` op de host nu wél de bestanden toont.
3.  **Decypharr Logs**: Zodra de mount werkt, checken of Decypharr begint met "Creating symlink...".

---
*Status: CRITISCH - Core functionaliteit (media afspelen) werkt nog niet.*
