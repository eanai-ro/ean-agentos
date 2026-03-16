# mem doctor - Health Check Rapid

## Descriere

Comanda `mem doctor` oferă un health check rapid (sub 2s) al sistemului de memorie permanentă, verificând 6 aspecte critice:

1. **DB Integrity** - Integritatea bazei de date SQLite
2. **FTS5** - Funcționalitatea full-text search
3. **Reconciler** - Starea reconciler-ului și drift detection
4. **Auto-compact** - Status auto-compact și override-uri
5. **Disk Space** - Spațiul disponibil pe disc
6. **Hooks** - Configurare PreCompact hook

## Utilizare

### Comenzi de bază

```bash
# Health check simplu
mem doctor

# Health check + remedieri automate (PRAGMA optimize)
mem doctor --fix

# Output JSON (pentru scripting)
mem doctor --json

# Combinat
mem doctor --fix --json
```

### Status-uri

Fiecare verificare returnează unul din 3 status-uri:
- ✅ **ok** - Totul funcționează normal
- ⚠️ **warn** - Atenție, dar nu critică
- ❌ **fail** - Eroare critică, necesită intervenție

**Status final**:
- **OK** - Toate verificările sunt verzi (exit code 0)
- **WARN** - Cel puțin un warning (exit code 1)
- **FAIL** - Cel puțin o eroare critică (exit code 1)

### Exemplu Output

```
🏥 DATABASE HEALTH CHECK
============================================================
✅ db_integrity         Integritate DB: OK
✅ fts5                 FTS5 activ: 3 tabele
✅ reconciler           Reconciler: 319 sesiuni tracked
✅ compact              Ultima compact: 2026-02-07 (override: 100% - disabled)
✅ disk                 Spațiu disc: 654G liber (40% folosit)
⚠️ hooks                PreCompact hook: disabled
============================================================
Status final: ⚠️  WARN

💡 Recomandare: Rulează 'mem doctor --fix' pentru remedieri automate safe
```

### JSON Output

```json
{
  "status": "warn",
  "checks": {
    "db_integrity": {
      "status": "ok",
      "message": "Integritate DB: OK"
    },
    "fts5": {
      "status": "ok",
      "message": "FTS5 activ: 3 tabele"
    },
    "reconciler": {
      "status": "ok",
      "message": "Reconciler: 319 sesiuni tracked"
    },
    "compact": {
      "status": "ok",
      "message": "Ultima compact: 2026-02-07 (override: 100% - disabled)"
    },
    "disk": {
      "status": "ok",
      "message": "Spațiu disc: 654G liber (40% folosit)"
    },
    "hooks": {
      "status": "warn",
      "message": "PreCompact hook: disabled"
    }
  }
}
```

## Verificări Detaliate

### 1. DB Integrity

Rulează `PRAGMA quick_check` pentru verificare rapidă a integrității DB.

**Posibile status-uri**:
- ✅ ok - DB valid
- ❌ fail - DB corrupt sau eroare acces

**Remediere manuală** (dacă fail):
```bash
# Backup DB
mem backup

# Încearcă repair
sqlite3 ~/.claude/memory/global.db "PRAGMA integrity_check"

# Dacă nu merge, restore din ultimul backup
cp ~/.claude/memory/backups/$(ls -t ~/.claude/memory/backups | head -1)/global.db ~/.claude/memory/
```

### 2. FTS5 Full-Text Search

Verifică:
- Existența tabelelor FTS (`messages_fts`, `bash_history_fts`, `tool_calls_fts`)
- Funcționalitatea query-urilor FTS

**Posibile status-uri**:
- ✅ ok - FTS5 funcțional
- ⚠️ warn - Tabele FTS lipsă sau query eșuat
- ❌ fail - Eroare critică FTS

**Remediere** (dacă warn/fail):
```bash
# Re-populează FTS
cd ~/.claude/memory
sqlite3 global.db < migrations/002_fts5_search.sql
```

### 3. Reconciler State

Verifică fișierul `.reconciler_state.json` și detectează drift-uri.

**Posibile status-uri**:
- ✅ ok - Reconciler funcțional, fără drift
- ⚠️ warn - State file lipsă sau drift detectat

**Remediere** (dacă warn):
```bash
# Rulează reconciler manual
mem reconcile --force
```

### 4. Auto-Compact Status

Verifică:
- Ultimul compact boundary în DB
- Override-uri `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`

**Posibile status-uri**:
- ✅ ok - Compact funcționează normal

**Info**: Dacă override e 100%, compacting e disabled (voința utilizatorului).

### 5. Disk Space

Verifică spațiul disponibil pe partiția cu memorie permanentă.

**Posibile status-uri**:
- ✅ ok - Mai mult de 10% spațiu liber
- ⚠️ warn - Mai puțin de 10% spațiu liber

**Remediere** (dacă warn):
```bash
# Curățare snapshot-uri vechi
find ~/.claude/memory/backups -type d -name "2*" -mtime +7 -exec rm -rf {} \;

# Verifică dimensiune DB
du -sh ~/.claude/memory/global.db

# Opțional: compact manual (dacă e mare)
sqlite3 ~/.claude/memory/global.db "VACUUM"
```

### 6. PreCompact Hook

Verifică dacă hook-ul `PreCompact` e configurat în `~/.claude/settings.json`.

**Posibile status-uri**:
- ✅ ok - Hook enabled
- ⚠️ warn - Hook disabled sau settings.json lipsă

**Remediere** (dacă warn):
```bash
# Verifică dacă settings.json există
cat ~/.claude/settings.json | jq '.PreCompact'

# Dacă lipsește, adaugă hook
# (vezi documentația P1 pentru configurare PreCompact)
```

## Auto-Fix (--fix)

Când rulezi `mem doctor --fix`, se execută automat:
```sql
PRAGMA optimize;
```

Acest command actualizează statisticile SQLite pentru query optimizer, îmbunătățind performanța FTS5 și index-urilor.

**Safe**: Nu modifică datele, doar statistici interne.

## Când să Folosești

### Zilnic / După Fiecare Sesiune
```bash
# Quick check
mem doctor
```

### Înainte de Backup
```bash
# Verifică că totul e OK
mem doctor && mem backup
```

### După Auto-Compact
```bash
# Verifică integritatea după compact
mem doctor --fix
```

### În Scripturi de Monitoring
```bash
#!/bin/bash
# Monitoring script
if ! mem doctor --json | jq -e '.status == "ok"' > /dev/null; then
    echo "❌ Health check FAILED!"
    mem doctor --json | jq '.checks | to_entries[] | select(.value.status != "ok")'
    exit 1
fi
```

## Performanță

- **Durată**: ~1.5-2.5 secunde
- **Overhead**: Minimal (doar read operations)
- **Safe**: Nu modifică date (doar cu --fix, și atunci doar statistici)

## Limitări

- Nu verifică conținutul mesajelor (doar metadata)
- Nu detectează duplicate sau inconsistențe logice
- `--fix` e limitat la PRAGMA optimize (nu face repair-uri complexe)

## Vezi și

- `mem backup` - Backup complet înainte de remedieri
- `mem stats` - Statistici detaliate despre date
- `mem reconcile` - Reconciler manual pentru drift-uri

---

**Versiune**: 1.0 (implementat în P1+)
**Data**: Februarie 2026
