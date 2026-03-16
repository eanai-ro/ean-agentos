# Secret Scrubbing - Mascare Automată

## Descriere

Sistemul de **scrubbing** protejează memoria permanentă prin mascare automată a secretelor ÎNAINTE de salvare în baza de date. Scrubbing-ul se aplică în pipeline-ul de ingest pentru toate tipurile de date:

- User prompts
- Assistant responses
- Tool calls (input + result + error)
- Bash commands (command + output + stderr)

## Pattern-uri Detectate

### API Keys și Tokens

| Tip Secret | Pattern | Exemplu Mascat |
|------------|---------|----------------|
| OpenAI API key | `sk-[A-Za-z0-9]{20,}` | `sk-1****REDACTED****cdef` |
| Slack token | `xox[baprs]-[A-Za-z0-9-]{10,}` | `xoxb****REDACTED****xyz` |
| Google API key | `AIza[0-9A-Za-z\-_]{20,}` | `AIza****REDACTED****890` |
| GitHub token | `ghp_[A-Za-z0-9]{30,}` | `ghp_****REDACTED****abc` |
| GitHub PAT | `github_pat_[A-Za-z0-9_]+` | `gith****REDACTED****xyz` |
| AWS access key | `AKIA[0-9A-Z]{16}` | `AKIA****REDACTED****MNO` |

### Authorization Headers

```
Authorization: Bearer <token>  →  Authorization: Bearer ****REDACTED****
Bearer eyJhbGc...                →  Bear****REDACTED****xyz
```

### JSON Tokens

```json
{"api_key": "secret123456"}     →  {"api_key": "****REDACTED****"}
{"access_token": "long_token"}  →  {"access_token": "****REDACTED****"}
```

### PEM Private Keys

```
-----BEGIN PRIVATE KEY-----
MIIEvQIBA...
-----END PRIVATE KEY-----
```

Mascat ca: `****REDACTED_PEM****`

## Cum Funcționează

### Pipeline Scrubbing

```
User Input → scrub_text() → Scrubbed Text → DB INSERT
```

**Funcții**:
1. `scrub_text(text)` - Scrubbează un string
2. `scrub_payload(obj)` - Recursiv pentru dict/list/str

**Algoritm**:
1. Aplică toate pattern-urile regex pe text
2. Verifică whitelist pentru exclude
3. Mascare: păstrează primele 4 + ultimele 4 caractere
4. Înlocuiește în text original
5. Returnează (text_scrubbed, metadata)

### Unde Se Aplică

| Handler | Ce se scrubbează |
|---------|------------------|
| `handle_user_prompt` | prompt |
| `handle_assistant_response` | response |
| `handle_post_tool` | tool_input, tool_result, error_output |
| `handle_post_tool` (Bash) | command, stdout, stderr |

## Configurare

### Variabile de Mediu

```bash
# Disable scrubbing complet (pentru debug)
export MEMORY_SCRUB_DISABLE=1

# Activează logging scrubbing
export MEMORY_SCRUB_DEBUG=1

# Folosește scrubbing (default)
unset MEMORY_SCRUB_DISABLE
```

### Whitelist Pattern-uri

Creează fișier whitelist pentru a exclude pattern-uri cunoscute safe:

```bash
# ./scrub_whitelist.txt
toolu_[A-Za-z0-9]+
[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}
test_token_safe
```

**Format**: Câte un regex pattern per linie. Pattern-urile din whitelist NU vor fi mascate.

**Exemplu utilizare**:
```bash
cat > ./scrub_whitelist.txt <<EOF
toolu_[A-Za-z0-9]+
test_api_key_[0-9]+
EOF
```

## Testare

### Test Manual

```bash
# Activează debug
export MEMORY_SCRUB_DEBUG=1

# Trimite prompt cu fake secret
say "Test: sk-1234567890abcdef1234567890abcdef1234567890abcdef"

# Verifică în DB
sqlite3 ./global.db \
  "SELECT content FROM messages WHERE content LIKE '%REDACTED%' ORDER BY id DESC LIMIT 1"

# Output așteptat:
# Test: sk-1****REDACTED****cdef
```

### Test Bash Command

```bash
# Trimite comandă cu fake token
echo 'curl -H "Authorization: Bearer sk-test123456789"' | say

# Verifică în bash_history
sqlite3 ./global.db \
  "SELECT command FROM bash_history WHERE command LIKE '%REDACTED%' ORDER BY id DESC LIMIT 1"
```

### Test Disable

```bash
# Disable scrubbing
export MEMORY_SCRUB_DISABLE=1

# Trimite secret
say "Test disable: sk-fake123456"

# Verifică că NU e scrubbed
sqlite3 ./global.db \
  "SELECT content FROM messages WHERE content LIKE '%fake123456%' ORDER BY id DESC LIMIT 1"

# Re-enable
unset MEMORY_SCRUB_DISABLE
```

## Exemple Reale

### Exemplu 1: API Call cu Token

**Input**:
```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer sk-proj-abc123def456ghi789jkl012mno345"
```

**Salvat în DB**:
```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer sk-p****REDACTED****o345"
```

### Exemplu 2: JSON Config cu Secrets

**Input**:
```json
{
  "api_key": "AIzaSyDxyz123abc456def789",
  "slack_webhook": "xoxb-1234-5678-abcdef",
  "database_url": "postgresql://user:password@host/db"
}
```

**Salvat în DB**:
```json
{
  "api_key": "****REDACTED****",
  "slack_webhook": "****REDACTED****",
  "database_url": "postgresql://user:password@host/db"
}
```

**Notă**: Database URL-ul nu e acoperit de pattern-uri default. Adaugă în whitelist dacă e public sau creează pattern personalizat.

### Exemplu 3: PEM Private Key

**Input**:
```
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890abcdef...
(multiple lines)
-----END RSA PRIVATE KEY-----
```

**Salvat în DB**:
```
****REDACTED_PEM****
```

## Limitări

### Ce NU Detectează (False Negatives)

- **Passwords în plain text** fără pattern specific (ex: "password123")
- **Custom tokens** cu format non-standard
- **Database connection strings** (ex: `postgresql://user:pass@host`)
- **SSH keys** fără header PEM standard

**Soluție**: Adaugă pattern-uri personalizate în cod sau folosește whitelist pentru exclude.

### False Positives

Scrubbing-ul e agresiv pentru siguranță. Posibile false positives:
- String-uri lungi cu format similar (40+ caractere alfanumerice)
- UUID-uri foarte lungi (>50 caractere)

**Soluție**: Adaugă în whitelist pattern-urile safe cunoscute.

## Performance

- **Overhead**: ~5-15ms per mesaj (depinde de dimensiune)
- **Memorie**: Minimal (scrubbing in-place cu regex)
- **DB Size**: Nu crește (secretele mascate sunt mai scurte)

## Securitate

### Ce Protejează

✅ Secrete accidentale în prompts
✅ API keys în comenzi Bash
✅ Tokens în error messages
✅ PEM keys în clipboard paste

### Ce NU Protejează

❌ Secrete deja salvate în DB înainte de scrubbing
❌ Secrete în fișiere versionate (folderele `file_versions/`)
❌ Secrete în session MD files (`sessions/*.md`)

**Notă**: Pentru protecție completă, folosește și **Quarantine Guard** (Feature 4).

## Migration Existing Data

Dacă ai secrete deja în DB, rulează migration:

```bash
# ATENȚIE: Backup DB mai întâi!
mem backup

# Script manual pentru re-scrub date existente
sqlite3 ./global.db <<EOF
-- Nu există migration automată deocamdată
-- Contactează admin pentru script custom
EOF
```

## Vezi și

- **Quarantine Guard** (Feature 4) - Failsafe dacă scrubbing-ul eșuează
- `mem backup` - Backup înainte de modificări
- `error_db` - Erori salvate sunt și ele scrubbed

---

**Versiune**: 1.0 (implementat în P1+)
**Data**: Februarie 2026
**Status**: Production-ready, testat cu 10+ pattern-uri
