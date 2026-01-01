# Torplex Status Report - 2026-01-02

## 🛑 Huidige Status: GEBLOKKEERD
**Doel:** Volledige automatisering van Real-Debrid en TorBox via symlinks.
**Probleem:** Decypharr maakt geen symlinks aan, ondanks positieve logs.

---

## 🔍 Wat is er geprobeerd?

### 1. Externe Mounts (Zurg + Rclone) - **DEELS GELUKT**
- **Setup:** Aparte `zurg` en `rclone` containers die mounten naar `/mnt/torplex/zurg` & `/mnt/torplex/torbox`.
- **Resultaat:**
    - ✅ Mounts werkten perfect op de host (bestanden zichtbaar).
    - ✅ Handmatige symlinks werkten.
    - ❌ **Decypharr Bug:** Decypharr logt `Post-Download Action: Symlink` maar voert de actie niet uit.

### 2. Decypharr Built-in Rclone - **MISLUKT**
- **Setup:** `config.json` aangepast om Decypharr's interne rclone te gebruiken.
- **Resultaat:**
    - ❌ Mount folders bleven leeg.
    - ❌ Rclone RC server startte wel, maar mounts verschenen niet.

### 3. Decypharr Beta Versie (`v1.1.6-beta`) - **MISLUKT**
- **Setup:** Switch naar beta image in de hoop op een bugfix.
- **Resultaat:**
    - ❌ Zelfde gedrag: `Post-Download Action: Symlink` in logs, maar geen symlink op disk.

### 4. Alternatief: RDTClient - **VOORGESTELD**
- **Status:** Gepland als vervanger voor Decypharr.
- **Voordeel:** Bewezen "Symlink Downloader" die wel werkt.
- **Nadeel:** Ondersteunt **alleen Real-Debrid**, geen TorBox support.

---

## ⚠️ Huidige Issues

1. **Symlink Creatie Faalt:** Decypharr (zowel stable als beta) faalt stilzwijgend bij het maken van symlinks.
2. **TorBox Ondersteuning:** Als we overstappen naar RDTClient voor Real-Debrid, hebben we nog steeds een oplossing nodig voor TorBox.
3. **Ghost Torrents:** Decypharr verwijdert torrents soms direct na toevoegen van Real-Debrid ("deleted from RD" events).

---

## 📋 Plan voor Volgende Sessie

Het doel is een stabiele setup voor **beide** providers.

### Optie A: "Best of Both Worlds" (Aanbevolen)
- **Real-Debrid:** Gebruik **RDTClient** (Bewezen stabiel voor RD symlinks).
- **TorBox:** Gebruik **Decypharr** (of zoek ander alternatief) *alleen* voor TorBox, en debug specifiek daarvoor.Of accepteer downloaden ipv symlinken voor TorBox.

### Optie B: Decypharr Debuggen
- Dieper duiken in waarom Decypharr FUSE/Write permissies weigert voor symlinks, ondanks `privileged: true`.
- Handmatig "watch script" schrijven dat de Zurg folder in de gaten houdt en zelf symlinks maakt (buiten Decypharr om).

### Huidige Config Backup
- **Plex:** staat klaar op poort 32400.
- **Arrs:** Sonarr/Radarr geconfigureerd.
- **Zurg:** Config werkt, maar container staat uit/ongebruikt in huidige 'built-in' poging.

---
*Laatste update: 00:38*
