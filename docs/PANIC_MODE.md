# mem panic - Incident Response & Secrets Hunt

## Descriere

`mem panic` este tool-ul de **incident response** pentru situații de criză când bănuiești că un secret a ajuns în baza de date. Oferă un workflow **sigur, repetabil, atomic** pentru detectare și remediere.

## Filosofie: Safe by Default

- **Nu printează NICIODATĂ** valoarea completă a unui secret
- **Backup atomic** ÎNAINTE de orice modificare
- **Scan-only** default (fix doar cu flag explicit + env var guard)
- **Fingerprint SHA256** pentru tracking (pe versiunea redacted)
- **Safe snippet** (max 120 chars, toate secretele mascate)

## Când Să Folosești

### ✅ Cazuri de Utilizare

1. **Post-mortem**: "Am trimis accidental un token săptămâna trecută, e în DB?"
2. **Audit periodic**: Verificare lunară/trimestrială pentru siguranță
3. **Pre-share**: Înainte de a împărti backup cu cineva, verifică că e curat
4. **Pre-migration**: Înainte de migrare la alt sistem, audit complet
5. **Compliance**: Pentru rapoarte de securitate/audit

### ❌ Când NU E Necesar

- Scrubbing + Guard funcționează normal → scanare proactivă NU e necesară
- `mem doctor` + `mem quarantine stats` sunt suficiente pentru verificări zilnice
- `mem panic` e pentru situații **excepționale** sau audit periodic

## Comenzi

### 1. mem panic panic - Scan Complet

**Default mode** (scan-only, fără fix):

```bash
mem panic panic
# sau
mem panic panic --scan-only
```

**Ce face**:
1. **Freeze** (optional) - setează panic mode (blochează scrieri noi)
2. **Backup atomic** în `/tmp/claude_PANIC_<timestamp>/`
   - DB + WAL/SHM
   - Logs (*.log)
   - State files (.*.json)
   - Manifest cu SHA256 hashes
3. **Scan global** în toate tabelele:
   - `messages.content`
   - `tool_calls.tool_input`, `tool_calls.tool_result`
   - `bash_history.command`, `bash_history.output`, `bash_history.error_output`
   - `errors_solutions.error_message`
   - `checkpoints.summary` (dacă există)
4. **Generează raport** `PANIC_REPORT_<timestamp>.md`:
   - Total hits by severity (CRITICAL/HIGH/MEDIUM)
   - Top findings cu locație (table, row_id, column)
   - Fingerprint SHA256 (pe versiune redacted)
   - Safe snippet (fără secrete complete)
5. **Dezactivează panic mode** la final

**Output**:
```
🚨 PANIC MODE - INCIDENT RESPONSE

📦 Backup: /tmp/claude_PANIC_20260207_234649
📊 Total hits: 426
   CRITICAL: 110
   HIGH: 140
   MEDIUM: 219

📄 Report: ./docs/PANIC_REPORT_20260207_234725.md
```

### 2. mem panic panic --fix - Automated Remediation (EXPERIMENTAL)

**⚠️  ATENȚIE**: Modifică baza de date! Backup atomic e făcut automat, dar e **EXPERIMENTAL**.

**Guard obligatoriu**:
```bash
# Trebuie să setezi env var explicit
MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix
```

**Ce face**:
- Reuse funcția `safe_snippet()` pentru a masca secretele în DB
- Update atomic cu transaction
- Generează `FIX_PLAN.json` cu lista row_id-urilor modificate
- Păstrează backup-ul în `/tmp/`

**Dry run** (vezi ce ar face, fără modificări):
```bash
MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix --dry-run
```

### 3. mem panic status - Verifică Status

```bash
mem panic status
```

**Output**:
```
🔍 PANIC MODE STATUS
============================================================
✅ Status: INACTIVE

📄 Recent Reports (2):
   - 20260207_234725: ./docs/PANIC_REPORT_20260207_234725.md
   - 20260207_120530: ./docs/PANIC_REPORT_20260207_120530.md
```

### 4. mem panic resume - Repornire din Panic Mode

Dacă ai lăsat panic mode activ și vrei să repornești normal:

```bash
mem panic resume
```

## Pattern-uri Detectate

### CRITICAL (Always flag)

| Pattern | Tip | Exemplu |
|---------|-----|---------|
| `-----BEGIN .*PRIVATE KEY-----` | PEM private key | RSA/EC/OpenSSH keys |
| `Authorization: Bearer <token>` | Bearer auth | OAuth2, JWT |
| `access_token|refresh_token|id_token` | JWT tokens | JSON payloads |

### HIGH (Default flag)

| Pattern | Tip | Exemplu |
|---------|-----|---------|
| `sk-[A-Za-z0-9]{20,}` | OpenAI key | sk-proj-abc123... |
| `ghp_[A-Za-z0-9]{30,}` | GitHub token | ghp_xyz789... |
| `github_pat_[A-Za-z0-9_]{20,}` | GitHub PAT | github_pat_... |
| `AKIA[0-9A-Z]{16}` | AWS access key | AKIA... |
| `AIza[0-9A-Za-z\-_]{20,}` | Google API key | AIza... |
| `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack token | xoxb-... |

### MEDIUM (Heuristic, false positives posibile)

| Pattern | Tip | Risc False Positive |
|---------|-----|---------------------|
| `<token|secret|key>.*[A-Za-z0-9\-_\.]{45,}` | Generic long token | HIGH (poate fi UUID, path, etc.) |

### Excluderi (Allowlist)

Următoarele pattern-uri sunt **excluse automat**:

- `toolu_[A-Za-z0-9]+` - Claude tool IDs
- `[UUID format]` - UUIDs standard
- `REDACTED` - Text deja scrubbed
- `[0-9a-f]{64}` - SHA256 hashes (dacă nu e în context "token|key")

## Structura Backup

```
/tmp/claude_PANIC_20260207_234649/
├── global.db                    # DB backup (atomic via SQLite .backup)
├── global.db-wal               # WAL file (dacă există)
├── global.db-shm               # SHM file (dacă există)
├── *.log                        # Toate logurile
├── .*.json                      # Toate state files
├── MANIFEST.json                # SHA256 hashes pentru fiecare fișier
└── FIX_PLAN.json               # (dacă ai rulat --fix)
```

**MANIFEST.json** exemplu:
```json
{
  "timestamp": "2026-02-07T23:46:49+02:00",
  "backup_dir": "/tmp/claude_PANIC_20260207_234649",
  "files": {
    "global.db": {
      "size": 562991104,
      "sha256": "abc123...",
      "source": "/home/sandu/.claude/memory/global.db"
    },
    ...
  }
}
```

## Raport PANIC_REPORT.md

Exemplu raport:

```markdown
# PANIC MODE REPORT

**Generated**: 2026-02-07 23:47:25
**Backup Location**: `/tmp/claude_PANIC_20260207_234649`

## Summary

- **Total Hits**: 426
- **CRITICAL**: 110
- **HIGH**: 140
- **MEDIUM**: 219
- **Tables Scanned**: 8

## Findings

### CRITICAL Findings

**1. tool_calls.tool_input** (row_id: 970)
- Type: `bearer_auth`
- Fingerprint: `3072a33b90106d96`
- Snippet: `{"command": "curl -s \"http://...**REDACTED**...}`

### HIGH Findings

...

### MEDIUM Findings

...

## Remediation Steps

### Option 1: Manual Review
1. Review findings above
2. Verify if they are actual secrets or false positives
3. Update patterns in `PANIC_PATTERNS` if needed

### Option 2: Automated Fix (EXPERIMENTAL)
MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix
```

## False Positives

**Comune**:

1. **Curl commands cu localhost/IPs private**: Pattern `Authorization: Bearer` detectează header-e în curl
   - **Soluție**: Dacă sunt API-uri interne (192.168.x.x, localhost), probabil safe

2. **UUIDs lungi în context "token"**: Heuristic MEDIUM prinde UUID-uri lungi
   - **Soluție**: Verifică în raport, dacă e UUID → false positive

3. **Tool IDs deja în allowlist**: `toolu_xxx` e exclus automat

**Cum reduci false positives**:
- Review raportul PANIC_REPORT.md
- Identifică pattern-uri comune false positive
- Adaugă în `PANIC_EXCLUDES` în `mem_panic.py`

## Workflow Recomandat

### Audit Lunar (Proactiv)

```bash
# 1. Rulează scan
mem panic panic --scan-only

# 2. Review raport
cat ./docs/PANIC_REPORT_$(ls -t ./docs/PANIC_REPORT_*.md | head -1 | xargs basename)

# 3. Dacă ai găsit secrete reale:
#    - Identifică cum au trecut de scrubbing/guard
#    - Update pattern-uri în scrub/guard
#    - Rulează fix (dacă necesar)

MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix --dry-run  # Preview
MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix             # Apply
```

### Incident Response (Reactiv)

```bash
# Situație: Ai realizat că ai trimis un secret în prompt acum 2 zile

# 1. PANIC IMEDIAT
mem panic panic

# 2. Review findings în raport
#    - Caută fingerprint-ul secretului (dacă îl știi)
#    - Sau caută în snippet-uri

# 3. Dacă găsit → fix
MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix

# 4. Verifică că a fost remediat
mem panic panic --scan-only  # Re-scan

# 5. Rotează secretul real (în serviciu extern)
#    Ex: regenerează API key în dashboard OpenAI/GitHub/AWS
```

## Recovery din Backup

Dacă `--fix` strica ceva (foarte rar):

```bash
# 1. Găsește backup-ul
ls -lth /tmp/claude_PANIC_*/

# 2. Stop daemon
pkill -f memory_daemon.py

# 3. Restore DB
BACKUP_DIR="/tmp/claude_PANIC_20260207_234649"
cp $BACKUP_DIR/global.db ./global.db
cp $BACKUP_DIR/global.db-wal ./global.db-wal  # dacă există
cp $BACKUP_DIR/global.db-shm ./global.db-shm  # dacă există

# 4. Verifică integritate
sqlite3 ./global.db "PRAGMA integrity_check"

# 5. Restart daemon
python3 scripts/memory_daemon.py &
```

## Limitări

### Ce NU Face

❌ **Nu scanează**:
- Fișierele versionate în `file_versions/` (doar DB)
- Session MD files în `sessions/` (doar DB)
- Quarantine entries (doar DB principal)

❌ **Nu detectează**:
- Secrete obfuscate (`atob("c2VjcmV0")`)
- Secrete în imagini (screenshots cu text)
- Secrete în fișiere binare

❌ **Nu garantează** 100% acuratețe:
- False positives (mai ales MEDIUM heuristics)
- Pattern-uri custom neprevăzute

### Soluții Complementare

Pentru protecție completă:

1. **Pre-commit hooks** - git pre-commit cu `gitleaks` sau `truffleHog`
2. **Regular audits** - `mem panic panic --scan-only` lunar
3. **Secret rotation** - Rotește secretele periodic (best practice)
4. **Access control** - Permisiuni stricte pe `./`

## Performance

- **Scan time**: ~30-60s pentru DB de 500MB
- **Backup time**: ~5-10s (atomic copy)
- **Memory usage**: Minimal (stream processing)
- **Disk space**: ~500MB per backup (temporar în /tmp)

## Troubleshooting

### Prea multe false positives

**Simptom**: 400+ hits, majoritatea curl commands locale

**Soluție**:
1. Review PANIC_REPORT.md
2. Identifică pattern-uri comune
3. Adaugă în `PANIC_EXCLUDES`:
```python
# În mem_panic.py
PANIC_EXCLUDES = [
    r'toolu_[A-Za-z0-9]+',
    r'[0-9a-f]{8}-[0-9a-f]{4}...',
    r'192\.168\.\d+\.\d+',  # IPs private (NOU)
    r'localhost:\d+',       # Localhost endpoints (NOU)
]
```

### Fix nu modifică nimic

**Simptom**: `mem panic panic --fix` rulează dar 0 records modified

**Verificare**:
```bash
# Check env var
echo $MEMORY_PANIC_ALLOW_FIX  # Trebuie "1"

# Check dry-run
MEMORY_PANIC_ALLOW_FIX=1 mem panic panic --fix --dry-run
```

### Backup prea mare în /tmp

**Simptom**: /tmp se umple rapid

**Soluție**:
```bash
# Curățare backups vechi din /tmp
find /tmp -type d -name "claude_PANIC_*" -mtime +7 -exec rm -rf {} \;

# Sau modifică PANIC_DIR_BASE în mem_panic.py
PANIC_DIR_BASE = Path("/mnt/backup")  # Alt disk
```

## Vezi și

- **Scrubbing** (Feature 3) - Prima linie de apărare
- **Guard** (Feature 4) - Failsafe post-scrub
- `mem backup` - Backup complet programat
- `mem doctor` - Health check rapid

---

**Versiune**: 1.0 (implementat în P5)
**Data**: Februarie 2026
**Status**: Production-ready, incident response tool
