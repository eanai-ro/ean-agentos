# Quarantine Guard - Failsafe Post-Scrubbing

## Descriere

**Quarantine Guard** este ultima linie de apărare împotriva secretelor în memoria permanentă. Funcționează POST-scrubbing ca un safety net:

```
User Input → Scrubbing → GUARD CHECK → DB sau Quarantine
```

**Principiu**: Dacă scrubbing-ul eșuează (miss pattern, bug, etc.), guard-ul detectează și blochează salvarea în DB.

## Arhitectură

### Pipeline Complet

```
┌─────────────┐
│ User Input  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Scrubbing  │ (mascare pattern-uri cunoscute)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Guard Check │ (detectare pattern-uri agresive)
└──────┬──────┘
       │
       ├─── Secret detectat? ───┐
       │                        │
       NO                      YES
       │                        │
       ▼                        ▼
┌─────────────┐        ┌──────────────┐
│   DB Save   │        │  Quarantine  │
└─────────────┘        └──────────────┘
```

### Guard vs Scrub

| Aspect | Scrubbing | Guard |
|--------|-----------|-------|
| **Când** | ÎNAINTE de INSERT | DUPĂ scrubbing, ÎNAINTE de INSERT |
| **Acțiune** | Mascare (replace) | Blocare (reject) |
| **Pattern-uri** | Specifice, precise | Agresive, heuristic |
| **False Positives** | Rare | Acceptabile (pentru siguranță) |
| **Obiectiv** | Curățare date | Protecție ultimă |

## Pattern-uri Guard

### CRITICAL (Bloc întotdeauna)

```
-----BEGIN .*PRIVATE KEY-----     # Orice PEM private key
Authorization:\s*Bearer           # Authorization headers
(access|refresh|id)_token.*[A-Za-z0-9\-_\.]{20,}  # JWT tokens
```

### HIGH (Bloc la GUARD_BLOCK_LEVEL=HIGH)

```
sk-[A-Za-z0-9]{20,}              # OpenAI keys
ghp_[A-Za-z0-9]{30,}             # GitHub tokens
AKIA[0-9A-Z]{16}                 # AWS access keys
```

### MEDIUM (Bloc la GUARD_BLOCK_LEVEL=MEDIUM)

```
[A-Za-z0-9\-_]{45,}              # Generic long tokens (heuristic)
```

**Notă**: Pattern-urile guard sunt mai agresive decât scrub pentru a prinde și secrete "exotice".

## Configurare

### Variabile de Mediu

```bash
# Enable/disable guard (default: enabled)
export MEMORY_GUARD_ENABLE=1      # Enabled
export MEMORY_GUARD_ENABLE=0      # Disabled

# Block level (default: HIGH)
export MEMORY_GUARD_BLOCK_LEVEL=CRITICAL  # Doar CRITICAL
export MEMORY_GUARD_BLOCK_LEVEL=HIGH      # CRITICAL + HIGH
export MEMORY_GUARD_BLOCK_LEVEL=MEDIUM    # Toate (mai multe false positives)
```

### Guard Excludes (Hardcoded)

Pattern-uri excluse automat:
- `toolu_[A-Za-z0-9]+` - Claude tool IDs
- `[UUID format]` - UUIDs standard
- `REDACTED` - Text deja scrubbed

**Pentru exclude custom**: Modifică `GUARD_EXCLUDES` în `memory_daemon.py`.

## Cum Funcționează

### Detectare

În fiecare handler (user_prompt, assistant_response, post_tool):

```python
# După scrubbing
prompt_scrubbed, _ = scrub_text(prompt)

# Guard check
guard_result = guard_detect(prompt_scrubbed)
if guard_result["hits"] and should_block(guard_result["severity"]):
    quarantine_write("user_prompt", {"prompt": prompt_scrubbed}, guard_result)
    return  # NU SALVEAZĂ ÎN DB
```

### Quarantine Write

Când guard blochează:
1. **Scrie în quarantine**: `/home/sandu/.claude/memory/quarantine/q_<timestamp>_<event>.json`
2. **Update state**: `.guard_state.json` cu counters
3. **Log error**: `log_error()` pentru visibility
4. **Return early**: NU face INSERT în DB

### Quarantine Entry Format

```json
{
  "ts": "2026-02-07T23:45:12+02:00",
  "event_type": "user_prompt",
  "session_id": "abc123",
  "project": "/mnt/lucru/proiecte/x",
  "guard": {
    "hits": [
      {
        "type": "bearer_auth",
        "severity": "CRITICAL",
        "field": "content"
      }
    ],
    "severity": "CRITICAL"
  },
  "payload": {
    "scrubbed": true,
    "data": {
      "prompt": "curl -H \"Authorization: Bearer sk-1****REDACTED****cdef\""
    }
  }
}
```

## Management CLI

### Comenzi

```bash
# Listare entries
mem quarantine list           # Ultimele 20
mem quarantine list -l 50     # Ultimele 50

# Detalii entry
mem quarantine show 1         # Entry #1 din listă

# Statistici
mem quarantine stats

# Curățare
mem quarantine purge --all                  # Șterge tot
mem quarantine purge --older-than 30        # Mai vechi de 30 zile
mem quarantine purge --older-than 7 -y      # Fără confirmare
```

### Exemplu Output

```bash
$ mem quarantine list

🔒 QUARANTINE ENTRIES (ultimele 5 din 12)
================================================================================
 ID Timestamp            Event                Severity   Hits
--------------------------------------------------------------------------------
  1 2026-02-07T23:45:12  user_prompt          CRITICAL   1
  2 2026-02-07T22:10:33  post_tool            HIGH       2
  3 2026-02-06T15:22:01  assistant_response   HIGH       1
  4 2026-02-06T10:05:44  user_prompt          MEDIUM     1
  5 2026-02-05T09:12:30  post_tool            CRITICAL   3
--------------------------------------------------------------------------------
Total: 12 entries în quarantine

$ mem quarantine show 1

🔒 QUARANTINE ENTRY #1
================================================================================
File: q_20260207_234512_user_prompt.json
Timestamp: 2026-02-07T23:45:12+02:00
Event Type: user_prompt
Session ID: abc123
Project: /mnt/lucru/proiecte/x

Guard Detection:
  Severity: CRITICAL
  Hits: 1
    - Type: bearer_auth, Severity: CRITICAL

Payload (scrubbed): True
  Data (preview): {"prompt": "curl -H \"Authorization: Bearer sk-1****REDACTED****cdef\""}...
```

## Testare

### Test 1: Verifică Guard Enabled

```bash
# Check env vars
echo $MEMORY_GUARD_ENABLE      # Should be empty or 1
echo $MEMORY_GUARD_BLOCK_LEVEL # Should be empty or HIGH

# Check stats
mem quarantine stats
```

### Test 2: Simulare Blocare (Dev)

Pentru test în dev, poți forța o blocare adăugând un pattern care să treacă scrub dar să fie prins de guard.

**Exemplu**: Un token foarte lung (>45 caractere) care nu match-uiește pattern-urile specifice de scrub:

```bash
# Token custom foarte lung (>45 chars)
echo "test_custom_token_1234567890abcdefghijklmnopqrstuvwxyz_more_text_here" | say
```

Dacă guard e pe MEDIUM, va bloca acest token generic.

### Test 3: Verifică Quarantine

```bash
# După blocare, verifică entries
mem quarantine list

# Verifică stats
mem quarantine stats

# Verifică detalii
mem quarantine show 1
```

### Test 4: Purge

```bash
# Curățare entries vechi
mem quarantine purge --older-than 1

# Verifică că s-au șters
mem quarantine list
```

## Scenarii de Utilizare

### Scenariul 1: Scrubbing Miss

**Situație**: Un pattern nou de API key apare, scrubbing-ul nu îl detectează.

```bash
# User input
say "Folosesc key: new_api_key_format_xyz123abc456def789ghi012jkl345mno678"
```

**Guard acțiune**:
- Detectează pattern generic (>45 caractere)
- Severity: MEDIUM
- Blocare (dacă GUARD_BLOCK_LEVEL=MEDIUM)
- Scriere în quarantine

**Rezolvare**:
1. Verifică `mem quarantine show 1`
2. Identifică pattern-ul nou
3. Adaugă în `SCRUB_PATTERNS` pentru viitor
4. Purge quarantine: `mem quarantine purge --older-than 0 -y`

### Scenariul 2: False Positive

**Situație**: Guard blochează un UUID foarte lung (dar safe).

```bash
# User input
say "Session ID: f47ac10b-58cc-4372-a567-0e02b2c3d479-extended-format-with-more-data"
```

**Guard acțiune**:
- Detectează >45 caractere
- Blocare

**Rezolvare**:
1. Verifică în quarantine: `mem quarantine show 1`
2. Confirmă că e safe
3. Adaugă pattern în `GUARD_EXCLUDES` pentru exclude
4. Sau crește `GUARD_BLOCK_LEVEL` la HIGH (skip MEDIUM)

### Scenariul 3: Audit Post-Deployment

**Situație**: Verifici după deployment că niciun secret nu a scăpat.

```bash
# Check guard stats
mem quarantine stats

# Dacă total_blocked > 0, investighează
mem quarantine list

# Review entries
mem quarantine show 1
mem quarantine show 2

# Dacă toate sunt OK (false positives sau resolved), purge
mem quarantine purge --all -y
```

## Performance

- **Overhead guard**: ~2-5ms per mesaj (după scrubbing)
- **Quarantine write**: ~5-10ms (doar când blochează)
- **False positive rate**: ~1-5% (depinde de BLOCK_LEVEL)

## Limitări

### Ce NU Protejează

❌ **Secrete în forme non-text**:
- Imagini cu text (screenshots cu keys)
- Fișiere binare (encrypted stores)
- Obfuscated secrets (`atob("c2VjcmV0")`)

❌ **Secrete deja salvate**:
- Date anterioare implementării guard
- Secrete în file_versions/
- Secrete în session MD files

### Soluții Complementare

Pentru protecție completă:
1. **Pre-commit hooks** - Scan secrets înainte de git push
2. **Periodic audit** - `mem search` pentru pattern-uri suspect
3. **Backup encrypt** - Encrypt backup-uri cu `mem backup`
4. **Access control** - Permisiuni stricte pe `~/.claude/memory/`

## Troubleshooting

### Prea Multe False Positives

**Simptom**: Guard blochează prea des mesaje legitime.

**Soluție**:
```bash
# Crește block level la HIGH (skip MEDIUM heuristics)
export MEMORY_GUARD_BLOCK_LEVEL=HIGH

# Sau disable complet pentru debug
export MEMORY_GUARD_ENABLE=0
```

### Guard Nu Blochează Nimic

**Simptom**: Secretele ajung în DB, quarantine e gol.

**Verificare**:
```bash
# Check guard enabled
python3 -c "import os; print(os.environ.get('MEMORY_GUARD_ENABLE', '1'))"

# Should print: 1

# Check pattern-uri
grep "GUARD_PATTERNS" ~/.claude/memory/scripts/memory_daemon.py
```

### Quarantine Plin

**Simptom**: Multe entries în quarantine, ocupă spațiu.

**Soluție**:
```bash
# Verifică entries
mem quarantine list -l 100

# Curățare selective
mem quarantine purge --older-than 30

# Sau totală
mem quarantine purge --all -y
```

## Vezi și

- **Scrubbing** (Feature 3) - Prima linie de apărare
- `mem backup` - Backup înainte de modificări
- `mem doctor` - Health check inclusiv guard state

---

**Versiune**: 1.0 (implementat în P1+)
**Data**: Februarie 2026
**Status**: Production-ready, layer de siguranță post-scrub
