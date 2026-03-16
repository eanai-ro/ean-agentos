# mem backup - Backup Complet

## Descriere

Comanda `mem backup` creează snapshot-uri complete ale sistemului de memorie permanentă, incluzând:
- Baza de date SQLite (global.db) - backup atomic via `.backup`
- Fișierele WAL/SHM (dacă sistemul e în WAL mode)
- Git repository bundle (tot istoricul local)
- State files pentru monitoring și reconciler
- Manifest JSON cu metadata

**Diferențe față de `auto_backup.sh`**:
- `auto_backup.sh` - doar DB + gzip, simplu
- `mem backup` - snapshot complet (DB + git + state + manifest), fără compresie

## Utilizare

### Comenzi de bază

```bash
# Backup simplu (14 zile retenție default)
mem backup

# Backup cu retenție personalizată (30 zile)
mem backup --keep 30

# Output JSON (pentru scripting)
mem backup --json

# Combinat
mem backup --keep 7 --json
```

### Structura snapshot

```
./backups/
└── 20260207_231511/
    ├── global.db                    # Baza de date (atomic backup)
    ├── global.db-wal               # WAL file (dacă există)
    ├── global.db-shm               # SHM file (dacă există)
    ├── repo.bundle                  # Git repository (git bundle --all)
    ├── .reconciler_state.json       # State reconciler
    ├── .monitor_state.json          # State monitor
    ├── .context_monitor_state.json  # State context monitor
    ├── .tg_alert_state.json        # State Telegram alerts (dacă există)
    └── manifest.json                # Metadata snapshot
```

### Manifest JSON

Fiecare snapshot include un `manifest.json` cu:
```json
{
  "timestamp": "2026-02-07T23:15:14+02:00",
  "hostname": "ai",
  "user": "sandu",
  "repo_path": "/path/to/ean-agentos",
  "db_size": 562225152,
  "git_sha": "31fead086db7680fb1a2eb5060ad28b29155b6bd",
  "wal_mode": "wal",
  "snapshot_dir": "/path/to/ean-agentos/backups/20260207_231511",
  "keep_days": 14
}
```

## Restore Manual

### 1. Restore baza de date

```bash
# Stop daemon
pkill -f memory_daemon.py

# Backup DB curent (safety)
cp ./global.db ./global.db.before_restore

# Restore din snapshot
SNAPSHOT="./backups/20260207_231511"
cp $SNAPSHOT/global.db ./global.db

# Restart daemon
python3 scripts/memory_daemon.py &
```

### 2. Restore git repository

```bash
# Clone din bundle într-un dir temporar
SNAPSHOT="./backups/20260207_231511"
git clone $SNAPSHOT/repo.bundle /tmp/memory_restored

# Verifică conținut
cd /tmp/memory_restored
git log --oneline -5

# Dacă e OK, copiază back
rm -rf ./.git
cp -a /tmp/memory_restored/.git ./
```

### 3. Restore state files

```bash
SNAPSHOT="./backups/20260207_231511"

# Backup state-uri curente
cd /path/to/ean-agentos
for f in .reconciler_state.json .monitor_state.json .context_monitor_state.json .tg_alert_state.json; do
    [ -f "$f" ] && cp "$f" "${f}.before_restore"
done

# Restore din snapshot
cp $SNAPSHOT/.reconciler_state.json ./
cp $SNAPSHOT/.monitor_state.json ./
cp $SNAPSHOT/.context_monitor_state.json ./
[ -f "$SNAPSHOT/.tg_alert_state.json" ] && cp $SNAPSHOT/.tg_alert_state.json ./
```

## Automatizare

### Cron job (daily backup)

```bash
# Adaugă în crontab
crontab -e

# Rulează zilnic la 3 AM, păstrează 30 zile
0 3 * * * /path/to/ean-agentos/scripts/mem backup --keep 30 >> /tmp/mem_backup.log 2>&1
```

### Systemd timer

```ini
# /etc/systemd/user/mem-backup.service
[Unit]
Description=EAN AgentOS Backup Service

[Service]
Type=oneshot
ExecStart=/path/to/ean-agentos/scripts/mem_backup.sh 30
StandardOutput=journal
StandardError=journal

# /etc/systemd/user/mem-backup.timer
[Unit]
Description=EAN AgentOS Backup Timer (Daily)

[Timer]
OnCalendar=daily
OnBootSec=10min
Persistent=true

[Install]
WantedBy=timers.target
```

Activare:
```bash
systemctl --user enable mem-backup.timer
systemctl --user start mem-backup.timer
systemctl --user status mem-backup.timer
```

## Verificare Backup

```bash
# Listare snapshot-uri
ls -lth ./backups/

# Verifică ultimul snapshot
LAST=$(ls -t ./backups/ | head -1)
echo "Ultimul backup: $LAST"
cat ./backups/$LAST/manifest.json | jq

# Verifică integritate DB din snapshot
sqlite3 ./backups/$LAST/global.db "PRAGMA integrity_check"

# Verifică git bundle
git bundle verify ./backups/$LAST/repo.bundle
```

## Metrici

- **Durată**: ~3-6 secunde (depinde de dimensiune DB)
- **Spațiu**: ~100-500MB per snapshot (fără compresie)
- **Retenție**: Configurabilă (default 14 zile)

## Limitări

- **Nu e incremental**: Fiecare backup e complet (snapshot-based)
- **Nu e comprimat**: Pentru viteză (spre deosebire de `auto_backup.sh`)
- **Retenția e simplă**: Pe bază de mtime, nu versioning inteligent

## Vezi și

- `auto_backup.sh` - Backup simplu doar DB cu compresie
- `mem doctor` - Health check înainte de restore
- `mem stats` - Verifică starea curentă

---

**Versiune**: 1.0 (implementat în P1+)
**Data**: Februarie 2026
