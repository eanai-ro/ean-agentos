# mem fp - False Positive Scoring System

## Descriere

`mem fp` este sistemul de **scoring pattern-uri și detecții** pentru reducerea false positives în secret detection. Oferă vizibilitate asupra:
- Ce pattern-uri detectează cel mai mult?
- Care e confidence-ul și score-ul fiecărei detecții?
- Ce decizii se iau (scrub/quarantine/report)?
- Ce reguli active există și cu ce weight-uri?

## Filozofie: Bayesian-Inspired Scoring

**Principii:**
- **Pattern rules** - Fiecare pattern are weight 1-100 (importanță)
- **Confidence levels** - HIGH/MED/LOW bazat pe tip pattern
- **Score calculation** - `score = weight × confidence_multiplier`
- **Decision thresholds** - Score-ul determină acțiunea (scrub/quarantine/report)

**Exemplu:**
```
Pattern: bearer_auth
Weight: 95 (din detection_rules)
Confidence: HIGH (pattern foarte specific)
Multiplier: 1.0 (HIGH)
Score: 95 × 1.0 = 95

Decizie: quarantine (score > 80)
```

## Structura Tabelelor

### detection_rules - Pattern Rules

```sql
CREATE TABLE detection_rules (
    pattern_id TEXT PRIMARY KEY,        -- unique ID (ex: "bearer_auth", "openai_key")
    category TEXT NOT NULL,             -- api_key, jwt, bearer, pem, password, etc.
    weight INTEGER NOT NULL,            -- 1-100 (importanță pattern)
    description TEXT,                   -- descriere pattern
    enabled INTEGER NOT NULL DEFAULT 1  -- 0=disabled, 1=enabled
);
```

**Pattern-uri preconfigurate** (din migrația 006):

| pattern_id | category | weight | description |
|------------|----------|--------|-------------|
| pem_private | pem | 100 | PEM private key (-----BEGIN) |
| bearer_auth | bearer | 95 | Authorization: Bearer header |
| jwt_token | jwt | 90 | JWT tokens (access_token, refresh_token) |
| openai_key | api_key | 85 | OpenAI API key (sk-...) |
| github_token | api_key | 85 | GitHub token (ghp_...) |
| github_pat | api_key | 85 | GitHub PAT (github_pat_...) |
| aws_access_key | api_key | 85 | AWS access key (AKIA...) |
| google_key | api_key | 80 | Google API key (AIza...) |
| slack_token | oauth_token | 80 | Slack token (xox...) |
| generic_token | generic | 40 | Generic long token (heuristic) |

### detection_events - Detection Log

```sql
CREATE TABLE detection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                   -- ISO8601
    source TEXT NOT NULL,               -- scrub|guard|panic
    pattern_id TEXT,                    -- FK către detection_rules
    category TEXT,                      -- category din rule
    score INTEGER NOT NULL,             -- 0-100
    confidence TEXT NOT NULL,           -- LOW|MED|HIGH
    table_name TEXT,                    -- unde a fost detectat
    row_id TEXT,                        -- row_id afectat
    excerpt TEXT,                       -- excerpt SCRUBBED (max 80 chars)
    decision TEXT NOT NULL              -- allow|scrub|quarantine|report
);
```

## Comenzi

### 1. mem fp stats - Overview Statistici

```bash
# Text output
mem fp stats

# JSON output
mem fp stats --json
```

**Output:**
```
📊 FALSE POSITIVE SCORING - STATISTICS
======================================================================
Total detections: 1250
Last 24h:         15
Last 7 days:      78
Average score:    72.3/100

🎯 By Category (Top 10):
----------------------------------------------------------------------
  bearer               450 detections  (avg score: 95.0)
  api_key              320 detections  (avg score: 85.0)
  jwt                  180 detections  (avg score: 90.0)
  pem                   45 detections  (avg score: 100.0)
  generic              255 detections  (avg score: 28.0)

⚠️  By Confidence:
----------------------------------------------------------------------
  🔴 HIGH           680
  🟡 MED            420
  🟢 LOW            150

🎬 By Decision:
----------------------------------------------------------------------
  🧹 scrub          980
  🔒 quarantine     220
  📝 report          50
  ✅ allow            0

📡 By Source:
----------------------------------------------------------------------
  scrub            1100
  guard             120
  panic              30
======================================================================
```

**Interpretare:**
- **Average score < 50**: Multe detecții low-confidence (generic tokens)
- **Quarantine > scrub**: Guard foarte agresiv sau scrubbing miss
- **Source = panic**: Detecții din panic scans (historical)

### 2. mem fp top - Top Categories

```bash
# Top 10 categories (default)
mem fp top

# Top 20
mem fp top -n 20

# JSON output
mem fp top --json
```

**Output:**
```
🏆 TOP 10 CATEGORIES by Detection Count
================================================================================
Category             Count     Avg Score     Min    Max
--------------------------------------------------------------------------------
bearer                 450          95.0      95    100
api_key                320          85.0      80     90
generic                255          28.0      10     50
jwt                    180          90.0      90     95
oauth_token            125          80.0      80     85
pem                     45         100.0     100    100
================================================================================
```

**Cazuri de utilizare:**
- Identifică pattern-uri cu detection rate mare
- Compară avg score între pattern-uri (low avg = FP posibil)
- Verifică spread (min-max) pentru consistență

### 3. mem fp rules - Lista Reguli

```bash
# Lista toate regulile
mem fp rules

# Detalii pentru o regulă
mem fp rules --pattern bearer_auth

# JSON output
mem fp rules --json
mem fp rules --pattern openai_key --json
```

**Output (listă):**
```
📋 DETECTION RULES (10 total)
==========================================================================================
Pattern ID                Category         Weight Enabled  Description
------------------------------------------------------------------------------------------
pem_private               pem                 100    ✅     PEM private key (-----BEGIN)
bearer_auth               bearer               95    ✅     Authorization: Bearer header
jwt_token                 jwt                  90    ✅     JWT tokens (access_token, refr
openai_key                api_key              85    ✅     OpenAI API key (sk-...)
generic_token             generic              40    ✅     Generic long token (heuristic,
==========================================================================================
```

**Output (detalii):**
```
📋 RULE DETAILS: bearer_auth
======================================================================
Category:     bearer
Weight:       95/100
Enabled:      ✅ Yes
Description:  Authorization: Bearer header
Detections:   450
======================================================================
```

### 4. mem fp recent - Ultimele Detecții

```bash
# Ultimele 20 detecții (default)
mem fp recent

# Ultimele 50
mem fp recent -n 50

# JSON output
mem fp recent --json
```

**Output:**
```
🔍 RECENT DETECTIONS - Ultimele 20
========================================================================================================================
   ID Timestamp            Source     Category        Score Conf   Dec    Table           Excerpt
------------------------------------------------------------------------------------------------------------------------
  458 2026-02-08 01:32:15  scrub      bearer             95 🔴    🧹    messages         Auth****REDACTED****...
  457 2026-02-08 01:30:42  guard      api_key            85 🟡    🔒    tool_calls       sk-p****REDACTED****...
  456 2026-02-08 01:28:18  scrub      generic            28 🟢    🧹    messages         [SCRUBBED EXCERPT]
  455 2026-02-08 01:25:03  scrub      jwt                90 🔴    🧹    tool_calls       acce****REDACTED****...

Total: 20 detections
```

**Emoji:**
- Confidence: 🔴 HIGH, 🟡 MED, 🟢 LOW
- Decision: 🧹 scrub, 🔒 quarantine, 📝 report, ✅ allow

### 5. mem fp search - Căutare Detecții

```bash
# Caută "bearer"
mem fp search bearer

# Caută "api_key" în ultimele 100 results
mem fp search api_key -n 100

# JSON output
mem fp search openai_key --json
```

**Câmpuri căutate:**
- `pattern_id`: ex: bearer_auth, openai_key
- `category`: ex: bearer, api_key, jwt
- `table_name`: ex: messages, tool_calls
- `excerpt`: (SAFE, redacted)

## Score Calculation

### Formula

```python
score = weight × confidence_multiplier

# Confidence multipliers:
HIGH: 1.0
MED:  0.7
LOW:  0.4
```

### Exemple

| Pattern | Weight | Confidence | Multiplier | Score |
|---------|--------|------------|------------|-------|
| pem_private | 100 | HIGH | 1.0 | 100 |
| bearer_auth | 95 | HIGH | 1.0 | 95 |
| openai_key | 85 | MED | 0.7 | 59.5 |
| generic_token | 40 | LOW | 0.4 | 16 |

### Decision Thresholds (Guard)

Guard folosește score pentru a decide acțiunea:

```python
if score >= 80:
    decision = "quarantine"  # BLOCK, nu ajunge în DB
elif score >= 50:
    decision = "scrub"       # Mascare automată
elif score >= 30:
    decision = "report"      # Log detection, allow
else:
    decision = "allow"       # Ignore (whitelisted sau FP)
```

**Configurare**:
```bash
# Ajustează GUARD_BLOCK_LEVEL
export MEMORY_GUARD_BLOCK_LEVEL=HIGH      # quarantine pentru score >= 80
export MEMORY_GUARD_BLOCK_LEVEL=CRITICAL  # quarantine doar pentru score = 100
export MEMORY_GUARD_BLOCK_LEVEL=MEDIUM    # quarantine pentru score >= 50
```

## Confidence Levels

Confidence-ul e determinat **static** bazat pe tip pattern (nu învață):

### HIGH (1.0)

Pattern-uri foarte specifice, risc FP scăzut:
- `pem_private` - PEM blocks (-----BEGIN PRIVATE KEY-----)
- `bearer_auth` - Authorization: Bearer header
- `jwt_token` - JSON Web Tokens (access_token, refresh_token)

**Caracteristici:**
- Format specific, recunoscut universal
- Aproape imposibil să fie altceva decât secret
- Exemplu: `Authorization: Bearer eyJhbGciOi...`

### MED (0.7)

Pattern-uri cu structură, dar posibile FP:
- `openai_key` - sk-[A-Za-z0-9]{20,}
- `github_token` - ghp_[A-Za-z0-9]{30,}
- `aws_access_key` - AKIA[0-9A-Z]{16}

**Caracteristici:**
- Prefix specific (sk-, ghp_, AKIA)
- Lungime caracteristică
- FP posibile (ex: comentarii în cod cu "sk-example123...")

### LOW (0.4)

Pattern-uri heuristice, risc FP mare:
- `generic_token` - Token/secret/key + string lung (45+ chars)

**Caracteristici:**
- Pattern generic, bazat pe lungime
- FP comune (UUIDs, hashes, tool IDs)
- Exemplu: `token = "550e8400-e29b-41d4-a716-446655440000"` (UUID, nu secret)

## Cazuri de Utilizare

### 1. Ajustare Weight pentru Pattern

**Scenario**: Pattern `generic_token` detectează prea multe FP.

```bash
# 1. Verifică detecții pentru pattern
mem fp search generic_token -n 100

# 2. Verifică stats
mem fp rules --pattern generic_token

# 3. Dacă FP > 80% → Ajustează weight
# Manual în DB sau prin admin tool:
sqlite3 ./global.db "UPDATE detection_rules SET weight = 20 WHERE pattern_id = 'generic_token'"

# 4. Re-test detecții
mem fp search generic_token | head -20
```

### 2. Disable Pattern Temporar

**Scenario**: Pattern `bearer_auth` blochează teste locale (curl localhost).

```bash
# 1. Verifică rule
mem fp rules --pattern bearer_auth

# 2. Disable temporar
sqlite3 ./global.db "UPDATE detection_rules SET enabled = 0 WHERE pattern_id = 'bearer_auth'"

# 3. Verifică
mem fp rules | grep bearer_auth  # Should show ❌

# 4. Re-enable după teste
sqlite3 ./global.db "UPDATE detection_rules SET enabled = 1 WHERE pattern_id = 'bearer_auth'"
```

### 3. Identificare Top False Positives

**Scenario**: Prea multe quarantine entries, probabil FP.

```bash
# 1. Top categories cu detection count mare
mem fp top

# 2. Verifică generic_token (de obicei cel mai multe FP)
mem fp search generic_token -n 50

# 3. Cross-check cu quarantine
mem quarantine list | grep generic_token

# 4. Dacă confirms FP → Reduce weight sau disable
```

### 4. Compliance Report

**Scenario**: Raport anual pentru certificare.

```bash
# 1. Export complete stats
mem fp stats --json > fp_scoring_report_2026.json

# 2. Top pattern rules
mem fp rules --json > detection_rules_2026.json

# 3. Recent detections (sample)
mem fp recent -n 100 --json > recent_detections_sample_2026.json

# 4. Category breakdown
mem fp top -n 20 --json > top_categories_2026.json
```

**Deliverables:**
- `fp_scoring_report_2026.json` - Statistici complete
- `detection_rules_2026.json` - Toate regulile active
- `recent_detections_sample_2026.json` - Sample 100 detecții
- `top_categories_2026.json` - Top 20 categories

## Integrare cu Alte Tools

### Cu mem audit (Audit Trail)

```bash
# 1. Verifică detecții în audit log
mem audit search scrub | grep bearer

# 2. Cross-check cu detection_events
mem fp search bearer

# 3. Comparație count
AUDIT_COUNT=$(mem audit search scrub | grep bearer | wc -l)
FP_COUNT=$(mem fp search bearer | wc -l)
echo "Audit: $AUDIT_COUNT, FP: $FP_COUNT"
```

### Cu mem quarantine (Quarantine)

```bash
# 1. Verifică quarantine entries recent
mem quarantine list | head -20

# 2. Identifică pattern-ul blocat
mem fp search <pattern_id>

# 3. Dacă FP → Ajustează weight/confidence
```

### Cu mem panic (Incident Response)

```bash
# 1. După panic scan, verifică detection breakdown
mem panic status  # Vezi ultimul raport

# 2. Identifică top patterns detectate
mem fp top

# 3. Verifică dacă sunt FP comune
mem fp search <pattern_id> | grep panic
```

## JSON Schema

Pentru automation:

### detection_rules

```json
{
  "rules": [
    {
      "pattern_id": "bearer_auth",
      "category": "bearer",
      "weight": 95,
      "description": "Authorization: Bearer header",
      "enabled": true
    }
  ],
  "count": 10
}
```

### detection_events

```json
{
  "events": [
    {
      "id": 458,
      "ts": "2026-02-08T01:32:15+02:00",
      "source": "scrub",
      "pattern_id": "bearer_auth",
      "category": "bearer",
      "score": 95,
      "confidence": "HIGH",
      "table_name": "messages",
      "row_id": null,
      "excerpt": "Auth****REDACTED****...",
      "decision": "scrub"
    }
  ],
  "count": 20
}
```

## Best Practices

### Pattern Rule Design

1. **Weight assignment**:
   - 90-100: PEM, JWT, Bearer (foarte specifice)
   - 80-89: API keys cu prefix (sk-, ghp-, AKIA)
   - 60-79: OAuth tokens (xox...)
   - 30-59: Heuristic patterns (lungime, context)
   - 1-29: Low-confidence heuristics

2. **Confidence selection**:
   - HIGH: Format fix, standardizat (RFC, spec)
   - MED: Prefix + lungime
   - LOW: Heuristic (keyword + lungime)

3. **Enabled flag**: Disable doar temporar pentru debug

### Detection Event Logging

1. **Excerpt safe**: Întotdeauna mascat (max 80 chars)
2. **Source tracking**: scrub/guard/panic pentru context
3. **Decision consistent**: scrub/quarantine/report/allow

### Performance

- **Overhead**: ~1-2ms per detection event
- **Index**: Pe `pattern_id`, `category`, `score` pentru queries rapide
- **Cleanup**: Consider purge events > 6 luni (după análise)

## Limitări

### Ce NU Face

❌ **Machine Learning**: Scoring-ul e static (rule-based), nu învață
❌ **Auto-tuning**: Weight-urile nu se ajustează automat
❌ **Context-aware**: Nu analizează context (ex: "test data")
❌ **Semantic analysis**: Nu înțelege dacă e secret real sau exemplu

### Workarounds

- **ML scoring**: Export detection_events și train model extern
- **Auto-tuning**: Periodic review + manual adjustment
- **Context**: Whitelist pentru paths/context (ex: `/test/`)
- **Semantic**: Human review pentru FP reduction

## Troubleshooting

### Score-uri inconsistente

**Cauză**: Weight-uri manual modificate sau confidence wrong

**Soluție:**
```bash
# Verifică toate rules
mem fp rules

# Re-calculează scores (aplicabil dacă schimbi weights)
# Nota: detection_events au score static (nu se recalculează automat)
```

### Prea multe detecții generic_token

**Cauză**: Heuristic prea agresiv

**Soluție:**
```bash
# 1. Reduce weight
sqlite3 ./global.db "UPDATE detection_rules SET weight = 20 WHERE pattern_id = 'generic_token'"

# 2. Sau disable temporar
sqlite3 ./global.db "UPDATE detection_rules SET enabled = 0 WHERE pattern_id = 'generic_token'"

# 3. Adaugă excludes în PANIC_EXCLUDES (mem_panic.py) sau GUARD_EXCLUDES (memory_daemon.py)
```

### Detection events lipsă

**Cauză**: Logging nu e aplicat sau scrubbing disabled

**Soluție:**
```bash
# Check scrubbing status
echo $MEMORY_SCRUB_DISABLE  # Trebuie 0 sau nesetat

# Verifică că scrub_text() apelează detection_event_write()
grep -A 20 "def scrub_text" scripts/memory_daemon.py | grep detection_event
```

## Vezi și

- **mem audit** - Audit trail pentru context
- **mem status** - Dashboard overview
- **mem quarantine** - Quarantine management
- **mem panic** - Incident response cu detection

---

**Versiune**: 1.0 (implementat în P6)
**Data**: Februarie 2026
**Status**: Production-ready, FP scoring system
