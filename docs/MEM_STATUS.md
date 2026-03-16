# mem status - Memory Observability Dashboard

## Descriere

`mem status` este dashboard-ul de observabilitate pentru EAN AgentOS. Oferă o vizualizare **one-screen** a stării generale a sistemului + activitatea ultimelor 24 de ore.

## Filozofie: Single Pane of Glass

Dashboard-ul e conceput pentru a răspunde rapid la întrebări precum:
- Totul e OK cu memoria?
- Cât spațiu ocupă DB-ul?
- Câte mesaje noi în ultimele 24h?
- Scrubbing-ul funcționează?
- Când a fost ultimul backup/panic/doctor?

**Output rapid**: sub 1s pentru DB de 500MB+

## Comanda

```bash
# Text output (human-readable)
mem status

# JSON output (pentru automation/scripting)
mem status --json
```

## Ce Afișează

### 📊 GENERAL

Statistici de bază despre memoria permanentă:

```
DB Path:     /path/to/ean-agentos/global.db
DB Size:     538.5 MB
WAL Mode:    No
Messages:    422,188
Sessions:    2,603
Tool Calls:  28,526
Errors:      3,211
Quarantine:  4
```

**Ce înseamnă fiecare metric:**
- **DB Size**: Dimensiunea fișierului global.db (MB/GB)
- **WAL Mode**: Yes dacă WAL mode e activ (global.db-wal există)
- **Messages**: Total mesaje în DB (user + assistant + system)
- **Sessions**: Total sesiuni înregistrate
- **Tool Calls**: Total tool calls (Bash, Read, Edit, Write, etc.)
- **Errors**: Total erori înregistrate în errors_solutions
- **Quarantine**: Număr de entries blocate de guard

### 🕒 LAST 24 HOURS

Activitate recentă pentru a vedea schimbări:

```
Messages:    4,277 new
Scrubbed:    3
Detections:  0
Quarantined: 0
Audit Events:0
```

**Ce înseamnă fiecare metric:**
- **Messages**: Mesaje noi inserate în ultimele 24h
- **Scrubbed**: Mesaje cu pattern-uri REDACTED (scrubbing activ)
- **Detections**: Events în detection_events (scrub/guard detecții)
- **Quarantined**: Entries noi blocate de guard
- **Audit Events**: Events în audit_log (scrub/guard/quarantine/panic)

**Interpretare:**
- `Scrubbed > 0` → Scrubbing-ul a detectat și mascat secrete (bun!)
- `Quarantined > 0` → Guard a blocat ceva DUPĂ scrubbing (investigare necesară)
- `Detections` include toate detectările (scrub + guard + panic)

### 🔧 OPERATIONS

Status ultimelor operații de mentenanță:

```
Last Backup: 45m ago (9 total)
Last Panic:  54m ago (1 in 30d)
Last Doctor: Unknown (status: unknown)
```

**Ce înseamnă fiecare metric:**
- **Last Backup**: Când a fost ultimul snapshot (mem backup)
- **Last Panic**: Când a fost ultimul panic scan (mem panic)
- **Last Doctor**: Când a fost ultimul health check (mem doctor)

**Recomandări:**
- Backup > 7 zile → `mem backup` recomandat
- Panic > 30 zile → audit periodic recomandat (opcional)
- Doctor = Unknown → rulează `mem doctor` pentru baseline

### 📦 AUTO-COMPACT

Status compactare automată context:

```
Last Compact:Never
ENV Override:100
```

**Ce înseamnă:**
- **Last Compact**: Când a fost ultimul compact_boundary detectat
- **ENV Override**: Valoarea `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (100 = disabled)

**Interpretare:**
- `Never` + `Override: 100` → Auto-compact dezactivat (recomandat)
- `Last Compact: <time>` → Auto-compact activ (risc pierdere context)

### 🔍 FTS5 SEARCH

Sanity check pentru full-text search:

```
Status:      OK
```

**Status-uri posibile:**
- `OK` → FTS5 funcțional, search rapid disponibil
- `ERROR: <mesaj>` → FTS5 corrupt sau lipsă, repară cu `mem doctor --fix`

## JSON Output

Pentru automation și scripting:

```bash
mem status --json | jq '.general.total_messages'
# 422188

mem status --json | jq '.last_24h.scrubbed'
# 3

mem status --json | jq '.fts.fts_status'
# "OK"
```

**Structură JSON:**
```json
{
  "general": {
    "db_size": 564977664,
    "db_size_human": "538.9 MB",
    "wal_present": false,
    "total_messages": 422188,
    "total_sessions": 2603,
    "total_tool_calls": 28526,
    "total_errors": 3211,
    "quarantine_entries": 4
  },
  "last_24h": {
    "messages_24h": 4277,
    "scrubbed_24h": 3,
    "detections_24h": 0,
    "quarantined_24h": 0,
    "audit_events_24h": 0
  },
  "panic": {
    "panic_scans_30d": 1,
    "last_panic_time": "2026-02-08T00:05:30+02:00",
    "last_panic_age": "54m ago"
  },
  "backup": {
    "last_backup_time": "2026-02-08T00:20:15+02:00",
    "last_backup_age": "45m ago",
    "total_backups": 9
  },
  "doctor": {
    "last_doctor_time": null,
    "last_doctor_age": "Unknown",
    "last_doctor_status": "unknown"
  },
  "compact": {
    "last_compact_time": null,
    "last_compact_age": "Never",
    "autocompact_override": "100"
  },
  "fts": {
    "fts_functional": true,
    "fts_status": "OK"
  }
}
```

## Cazuri de Utilizare

### 1. Daily Health Check

```bash
# Verificare rapid dimineața
mem status

# Dacă vezi warning-uri:
mem doctor        # Health check detaliat
mem backup        # Dacă backup > 7 zile
```

### 2. Debugging Issue

```bash
# User: "Memoria nu salvează nimic"
mem status

# Verifică:
# - Messages 24h = 0? → Daemon oprit sau crash
# - FTS5 status = ERROR? → DB corrupt
# - Quarantine > 10? → Guard prea agresiv
```

### 3. Automation / Monitoring

```bash
#!/bin/bash
# Script zilnic pentru monitoring

STATUS=$(mem status --json)

# Check DB size
DB_SIZE=$(echo "$STATUS" | jq -r '.general.db_size')
if [ $DB_SIZE -gt 1000000000 ]; then  # > 1GB
    echo "⚠️  DB size > 1GB, consider cleanup"
fi

# Check new messages
NEW_MSG=$(echo "$STATUS" | jq -r '.last_24h.messages_24h')
if [ $NEW_MSG -eq 0 ]; then
    echo "❌ No new messages in 24h - daemon issue?"
fi

# Check FTS
FTS=$(echo "$STATUS" | jq -r '.fts.fts_status')
if [ "$FTS" != "OK" ]; then
    echo "❌ FTS5 not functional, run mem doctor --fix"
fi
```

### 4. Pre-Deployment Check

```bash
# Înainte de deploy/migrare
mem status
mem doctor
mem backup

# Verifică că totul e OK (status: OK, FTS: OK, backup recent)
```

## Limitări

### Ce NU Oferă

❌ **Metrici detaliate** - Pentru detalii: `mem audit stats`, `mem fp stats`
❌ **Istoric trend** - Dashboard e snapshot current, nu time-series
❌ **Alerting** - Nu trimite notificări (use cron + scripting pentru asta)
❌ **Performance metrics** - Nu include query speed, cache hit rate

### Soluții Complementare

Pentru monitoring avansat:
- **Audit trail**: `mem audit tail` și `mem audit stats`
- **FP scoring**: `mem fp stats` și `mem fp top`
- **Error tracking**: `mem err` și `error_db search`
- **Logs**: `mem trace` pentru compact/warnings

## Performance

- **Timp execuție**: <1s pentru DB de 500MB+
- **Overhead**: Minimal, doar SELECT queries (no writes)
- **Frecvență recomandată**: 1x/zi pentru daily check, on-demand pentru debugging

## Troubleshooting

### Dashboard arată 0 mesaje în 24h

**Cauze:**
1. Daemon-ul memory nu rulează → Check: `pgrep -f memory_daemon`
2. Hooks dezactivate → Check: `~/.claude/settings.json`
3. DB corrupt → Check: `mem doctor`

**Soluție:**
```bash
# Restart daemon
pkill -f memory_daemon
python3 scripts/memory_daemon.py &

# Verifică health
mem doctor
```

### FTS5 status = ERROR

**Cauză**: Index FTS5 corrupt sau tabele lipsă

**Soluție:**
```bash
mem doctor --fix  # PRAGMA optimize + rebuild index
```

### DB size crește rapid

**Cauză**: Auto-compact dezactivat + sesiuni lungi

**Soluție:**
```bash
# Check auto-compact status
mem status | grep "AUTO-COMPACT"

# Dacă override = 100 → e normal (compactare manuală cu /clear)
# Dacă override != 100 → auto-compact activ (verifică logs)
```

## Vezi și

- **mem audit** - Audit trail pentru trasabilitate
- **mem fp** - False positive scoring
- **mem doctor** - Health check detaliat
- **mem backup** - Backup complet
- **mem panic** - Incident response

---

**Versiune**: 1.0 (implementat în P6)
**Data**: Februarie 2026
**Status**: Production-ready, observability dashboard
