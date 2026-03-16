# mem audit - Audit Trail & Trasabilitate

## Descriere

`mem audit` oferă **trasabilitate completă** pentru toate modificările automate în memoria permanentă. Fiecare operație de scrubbing, quarantine, panic sau backup e înregistrată în `audit_log` cu timestamp, actor, severity și summary.

## Filozofie: Append-Only Audit Trail

**Principii:**
- **Append-only**: Niciodată nu se șterg entries (trasabilitate permanentă)
- **Tamper-evident**: Fiecare entry are timestamp ISO8601 + actor
- **Severity-based**: Clasificare CRITICAL/HIGH/WARN/INFO pentru prioritizare
- **Actionable**: Change summary include context pentru remediere

## Structura Tabelului audit_log

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                   -- ISO8601 timestamp
    action_type TEXT NOT NULL,          -- scrub, quarantine, panic_fix, restore, backup, etc.
    table_name TEXT NOT NULL,           -- messages, tool_calls, errors, quarantine, system, etc.
    row_id TEXT,                        -- ID-ul rândului afectat (string generic)
    fingerprint TEXT,                   -- optional, pentru corelare (ex: error fingerprint)
    severity TEXT,                      -- INFO/WARN/HIGH/CRITICAL
    change_summary TEXT,                -- text scurt: ce s-a schimbat
    actor TEXT NOT NULL                 -- "system", "mem_panic", "guard", "scrubbing", etc.
);
```

## Comenzi

### 1. mem audit tail - Ultimele N Events

```bash
# Ultimele 20 events (default)
mem audit tail

# Ultimele 50
mem audit tail -n 50

# JSON output
mem audit tail --json
mem audit tail -n 100 --json | jq '.events[0]'
```

**Output format:**
```
🔍 AUDIT LOG - Ultimele 20 events
====================================================================================================================
   ID Timestamp            Action               Table                Sev    Actor           Summary
--------------------------------------------------------------------------------------------------------------------
  158 2026-02-08 01:05:23  panic_scan           system               🟠     mem_panic       Scan complete: 426 hits detected
  157 2026-02-08 01:05:18  panic_backup         system               🟠     mem_panic       Emergency backup created: claude_PANIC_
  156 2026-02-08 01:05:15  panic_freeze         system               🔴     mem_panic       Panic mode activated - freeze initiated
  155 2026-02-08 00:58:12  scrub                messages             ℹ️     scrubbing       Scrubbed 3 secrets: bearer_token: 2, ope
  154 2026-02-08 00:45:30  quarantine           quarantine           ⚠️     guard           Blocked user_prompt: 2 hits detected

Total: 20 events
```

**Emoji severity:**
- 🔴 CRITICAL - Acțiuni critice (panic_freeze, panic_fix)
- 🟠 HIGH - Acțiuni importante (panic_backup, panic_scan, doctor_fix)
- ⚠️  WARN - Warnings (quarantine, detection_high_score)
- ℹ️  INFO - Info (scrub, backup, doctor_check)

### 2. mem audit search - Căutare în Audit Log

```bash
# Caută "scrub" în orice câmp
mem audit search scrub

# Caută "panic"
mem audit search panic

# Caută "quarantine"
mem audit search quarantine -n 100

# JSON output
mem audit search panic --json | jq '.count'
```

**Câmpuri căutate:**
- `action_type`: ex: scrub, quarantine, panic_freeze
- `table_name`: ex: messages, quarantine, system
- `change_summary`: ex: "Scrubbed 3 secrets"
- `actor`: ex: scrubbing, guard, mem_panic

**Output**:
```
🔍 AUDIT LOG - Rezultate pentru: 'panic'
====================================================================================================================
   ID Timestamp            Action               Table                Sev    Actor           Summary
--------------------------------------------------------------------------------------------------------------------
  158 2026-02-08 01:05:23  panic_scan           system               🟠     mem_panic       Scan complete: 426 hits detected
  157 2026-02-08 01:05:18  panic_backup         system               🟠     mem_panic       Emergency backup created: claude_PANIC_
  156 2026-02-08 01:05:15  panic_freeze         system               🔴     mem_panic       Panic mode activated - freeze initiated

Total: 3 results
```

### 3. mem audit stats - Statistici Complete

```bash
# Text output (human-readable)
mem audit stats

# JSON output (pentru scripting)
mem audit stats --json
```

**Output format:**
```
📊 AUDIT LOG STATISTICS
======================================================================
Total events:     158
Last 24h:         45
Last 7 days:      98

🎯 By Action Type (Top 10):
----------------------------------------------------------------------
  scrub                              85
  panic_scan                          5
  panic_backup                        5
  quarantine                         12
  panic_freeze                        5
  backup                              8
  doctor_check                       18
  panic_resume                        5

⚠️  By Severity:
----------------------------------------------------------------------
  ℹ️  INFO                            95
  ⚠️  WARN                            35
  🟠 HIGH                             18
  🔴 CRITICAL                         10

📋 By Table (Top 10):
----------------------------------------------------------------------
  messages                           85
  system                             38
  quarantine                         12
  tool_calls                         15
  errors                              8

👤 By Actor (Top 10):
----------------------------------------------------------------------
  scrubbing                          85
  mem_panic                          20
  guard                              12
  system                             18
  mem_backup                          8
======================================================================
```

## Actori (Actors)

Fiecare entry în audit_log are un **actor** care identifică sursa modificării:

| Actor | Descriere | Acțiuni tipice |
|-------|-----------|----------------|
| `scrubbing` | Pipeline scrubbing automat | scrub |
| `guard` | Post-scrub guard failsafe | quarantine |
| `mem_panic` | Incident response tool | panic_freeze, panic_backup, panic_scan, panic_fix, panic_resume |
| `mem_backup` | Backup automation | backup |
| `mem_doctor` | Health check tool | doctor_check, doctor_fix |
| `system` | Sistem generic | restore, cleanup, optimize |

## Severity Levels

Clasificare events pentru prioritizare:

| Severity | Icon | Când se folosește | Exemple |
|----------|------|-------------------|---------|
| **CRITICAL** | 🔴 | Modificări critice DB, operații ireversibile | panic_freeze, panic_fix, restore_from_backup |
| **HIGH** | 🟠 | Operații importante, impact mare | panic_backup, panic_scan, doctor_fix, quarantine_purge |
| **WARN** | ⚠️  | Detecții, blocări, warnings | quarantine, detection_high_score, guard_block |
| **INFO** | ℹ️  | Operații normale, logging informativ | scrub, backup, doctor_check |

## Cazuri de Utilizare

### 1. Post-Mortem Analysis

**Scenario**: Ai observat că un secret a ajuns în DB acum 2 săptămâni.

```bash
# 1. Verifică scrubbing în perioada respectivă
mem audit search scrub | grep "2026-01-25"

# 2. Verifică quarantine (poate a fost blocat)
mem audit search quarantine | grep "2026-01-25"

# 3. Verifică panic scans
mem audit search panic_scan
```

**Întrebări pe care le răspunde:**
- Scrubbing-ul era activ în ziua respectivă?
- Guard a blocat ceva similar?
- Când a fost ultimul panic scan?

### 2. Compliance Audit

**Scenario**: Audit anual pentru certificare securitate.

```bash
# 1. Generează raport complet
mem audit stats --json > audit_report_2026.json

# 2. Verifică frecvența panic scans (recomandat: lunar)
mem audit search panic_scan

# 3. Verifică toate quarantine events
mem audit search quarantine

# 4. Raport scrubbing (proof că masking funcționează)
mem audit search scrub | wc -l  # Total events scrubbing
```

**Livrabile pentru audit:**
- `audit_report_2026.json` - Statistici complete
- `panic_scans_2026.log` - Lista panic scans efectuate
- `quarantine_log_2026.txt` - Toate blocările guard

### 3. Debugging Guard False Positives

**Scenario**: Guard blochează prea multe mesaje false positive.

```bash
# 1. Verifică toate quarantine events recent
mem audit search quarantine -n 100

# 2. Identifică pattern-urile blocate des
mem audit search quarantine | grep "hits detected"

# 3. Cross-check cu detection_events pentru scoring
mem fp search <pattern_id>
```

**Acțiuni:**
- Ajustează `GUARD_BLOCK_LEVEL` (CRITICAL/HIGH/MEDIUM)
- Adaugă pattern-uri în `GUARD_EXCLUDES`
- Review pattern weights în `detection_rules`

### 4. Performance Monitoring

**Scenario**: Monitorizare zilnică scrubbing/quarantine rate.

```bash
#!/bin/bash
# Script zilnic

# Verifică ultimele 24h
STATS=$(mem audit stats --json)

# Scrubbing events
SCRUB=$(echo "$STATS" | jq -r '.by_action[] | select(.action=="scrub") | .count')
echo "Scrubbing events 24h: $SCRUB"

# Quarantine events
QUAR=$(echo "$STATS" | jq -r '.by_action[] | select(.action=="quarantine") | .count')
echo "Quarantine events 24h: $QUAR"

# Alert dacă quarantine > 10 (posibil FP sau attack)
if [ $QUAR -gt 10 ]; then
    echo "⚠️  WARNING: High quarantine rate ($QUAR events)"
fi
```

## Integrare cu Alte Tools

### Cu mem fp (False Positive Scoring)

```bash
# 1. Identifică pattern blocat frecvent în audit
mem audit search quarantine | grep "bearer_auth"

# 2. Check scoring pentru pattern
mem fp rules --pattern bearer_auth

# 3. Vezi detection events pentru acel pattern
mem fp search bearer_auth

# 4. Ajustează weight dacă e FP
# (manual în detection_rules sau prin admin tool)
```

### Cu mem panic (Incident Response)

```bash
# 1. După un panic scan, verifică audit trail
mem audit search panic

# 2. Vezi ce s-a găsit și ce s-a făcut
mem audit tail -n 50 | grep panic

# 3. Verifică dacă fix-ul a fost aplicat
mem audit search panic_fix
```

### Cu mem status (Dashboard)

```bash
# Dashboard arată "Audit Events: 45 (24h)"
mem status

# Vezi detalii despre acele 45 events
mem audit tail -n 45

# Breakdown by action type
mem audit stats
```

## JSON Schema

Pentru automation și integrare:

```json
{
  "events": [
    {
      "id": 158,
      "ts": "2026-02-08T01:05:23+02:00",
      "action_type": "panic_scan",
      "table_name": "system",
      "row_id": null,
      "severity": "HIGH",
      "change_summary": "Scan complete: 426 hits detected",
      "actor": "mem_panic"
    }
  ],
  "count": 20
}
```

**Câmpuri:**
- `id`: INTEGER - ID unic, autoincrement
- `ts`: TEXT - Timestamp ISO8601 cu timezone
- `action_type`: TEXT - Tip acțiune (scrub, quarantine, etc.)
- `table_name`: TEXT - Tabelul afectat
- `row_id`: TEXT | null - ID rând afectat (dacă aplicabil)
- `severity`: TEXT - CRITICAL/HIGH/WARN/INFO
- `change_summary`: TEXT - Descriere scurtă modificare
- `actor`: TEXT - Actorul care a făcut modificarea

## Best Practices

### Pentru Developers

1. **Logging consistent**: Folosește severity levels correct
   - CRITICAL = DB changes irreversibile
   - HIGH = Operații importante cu impact
   - WARN = Detecții, blocări
   - INFO = Logging normal

2. **Change summary descriptiv**:
   ```python
   # ❌ BAD
   audit_log_write("scrub", "messages", severity="INFO", change_summary="scrubbed")

   # ✅ GOOD
   audit_log_write("scrub", "messages", severity="INFO",
                   change_summary=f"Scrubbed {count} secrets: bearer_token: 2, openai_key: 1")
   ```

3. **Actor specific**: Nu folosi "system" pentru totul
   - Specifică tool-ul: `mem_panic`, `guard`, `scrubbing`

### Pentru Operations

1. **Review zilnic**: `mem audit tail` pentru ultimele events
2. **Alerting**: Script pentru quarantine rate > threshold
3. **Compliance**: Export JSON lunar pentru arhivare
4. **Retention**: audit_log e append-only, consider cleanup după 1 an

## Limitări

### Ce NU Face

❌ **Nu oferă time-series**: Pentru trend analysis, export JSON și procesare externă
❌ **Nu are rollback**: Audit trail e read-only, pentru restore folosește `mem backup`
❌ **Nu are alerting**: Trebuie implementat extern (cron + scripting)
❌ **Nu auditează read operations**: Doar write/modify/delete

### Workarounds

- **Time-series**: Export zilnic JSON și agregare în InfluxDB/Prometheus
- **Alerting**: Cron job cu `mem audit stats --json` și check threshold-uri
- **Rollback**: Folosește `mem backup` pentru snapshots periodice

## Performance

- **Overhead**: Minimal (~1-2ms per entry)
- **Index**: Pe `ts`, `action_type`, `table_name`, `severity` pentru queries rapide
- **Cleanup**: Consideră purge entries > 1 an (optional, după compliance)

## Troubleshooting

### Audit log gol

**Cauză**: Logging nu e activat sau tabelul nu există

**Soluție:**
```bash
# Verifică dacă tabelul există
sqlite3 ./global.db "SELECT COUNT(*) FROM audit_log"

# Dacă eroare → aplică migrația 006
sqlite3 ./global.db < ./migrations/006_observability_tables.sql
```

### Events lipsă pentru scrubbing

**Cauză**: Scrubbing dezactivat sau logging nu e aplicat

**Soluție:**
```bash
# Check scrubbing status
echo $MEMORY_SCRUB_DISABLE  # Trebuie 0 sau nesetat

# Verifică că scrub_text() apelează audit_log_write()
grep -A 10 "def scrub_text" scripts/memory_daemon.py | grep audit_log
```

### JSON parsing erori

**Cauză**: Caractere speciale în change_summary

**Soluție:** Escape JSON în code când scrieți în DB
```python
change_summary = json.dumps(summary_text)  # Escape automat
```

## Vezi și

- **mem fp** - False positive scoring (detection_events)
- **mem status** - Dashboard observability
- **mem panic** - Incident response
- **mem backup** - Backup și restore

---

**Versiune**: 1.0 (implementat în P6)
**Data**: Februarie 2026
**Status**: Production-ready, audit trail system
