# Ghid de Utilizare - Memorie Permanentă Claude Code

## 🚀 Quick Start

### Comenzi de bază

```bash
# Statistici generale
mem stats

# Căutare globală
mem search "text de căutat"

# Căutare erori
mem err "TypeError"

# Ultimele 50 operații
mem trace

# Reconciliere erori din transcript
mem reconcile

# Reîncărcare context după auto-compact
mem reload
```

## 📖 Comenzi Detaliate

### 1. mem stats

Afișează statistici generale despre memoria permanentă.

```bash
mem stats
```

**Output:**
- Mesaje totale
- Sesiuni totale
- Tool calls
- Comenzi Bash
- Erori (totale, rezolvate, din reconciler)
- Checkpoints
- Dimensiune DB
- AUTOCOMPACT_OVERRIDE status

### 2. mem search

Căutare globală în toate tabelele (messages, commands, errors, patterns).

```bash
# Căutare simplă
mem search "oauth"

# Limitare rezultate
mem search "oauth" --limit 10

# Căutare în toate DB-urile (global + project)
mem search "error" --scope both
```

**Scope-uri disponibile:**
- `global` (default) - Doar DB global
- `project` - Doar DB proiect curent
- `both` - Ambele

**Performanță:**
- Simplu: ~90-110ms
- Complex: ~80-100ms (FTS5 optimizat)

### 3. mem err

Căutare specifică în erori și soluții.

```bash
# Toate erorile
mem err

# Căutare eroare specifică
mem err "ModuleNotFoundError"

# Doar erori nerezolvate
mem err --unresolved

# Limitare rezultate
mem err --limit 20
```

**Output:** Tabel formatat cu:
- ID eroare
- Data
- Tool
- Status (rezolvat/nerezolvat)
- Mesaj eroare (trunchiat)

### 4. mem trace

Afișează ultimele 50 operații din compact_trace.log.

```bash
mem trace
```

**Informații afișate:**
- Timestamp
- Event type (post_tool, pre_compact, session_start, etc.)
- Session ID
- Project path
- Monitor stats (context_pct, threshold)
- Reconciler stats

### 5. mem reconcile

Reconciliază erori din transcript curent în DB.

```bash
mem reconcile
```

**Funcție:**
- Citește transcript-ul sesiunii curente
- Extrage tool_use cu is_error=true
- Salvează în DB dacă nu există deja
- Previne duplicate prin fingerprinting

**Output JSON:**
```json
{
  "status": "ok",
  "new_errors": 2,
  "lines_processed": 150,
  "drift_detected": false
}
```

### 6. mem reload

Reîncarcă context din memoria permanentă (folosit după auto-compact).

```bash
mem reload
```

**Output:**
- Statistici generale
- Ultimele sesiuni
- Proiecte recent lucrate
- Ultimele conversații
- Comenzi recente
- Fișiere modificate
- Decizii și configurări
- Erori înregistrate

**Când să folosești:**
- După auto-compact (context window reset)
- După `/clear` command
- Când vrei refresh context complet

## 🔧 Configurare Avansată

### Environment Variables

```bash
# Previne compactări frecvente (recomandat 100)
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=100

# Telegram alerts (opțional)
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

### Hook-uri Active

Hook-urile sunt configurate în `~/.claude/settings.json`:

- **PostToolUse** - Salvare automată după fiecare tool call
- **UserPromptSubmit** - Salvare prompt utilizator
- **SessionStart** - Tracking început sesiune
- **Stop** - Salvare stats la final sesiune + Telegram notify
- **PreCompact** - Alert și salvare stats înainte de compact

## 📊 Use Cases Comune

### 1. Căutare eroare specific

```bash
# Găsește toate erorile de import
mem err "ImportError"

# Găsește erori nerezolvate
mem err --unresolved

# Căutare în toate mesajele
mem search "ModuleNotFoundError"
```

### 2. Tracking sesiuni și proiecte

```bash
# Vezi statistici generale
mem stats

# Vezi ultimele operații
mem trace

# Reîncarcă context după multe sesiuni
mem reload
```

### 3. Debugging și troubleshooting

```bash
# Reconciliază erori din sesiunea curentă
mem reconcile

# Verifică ce erori au fost salvate
mem err --limit 50

# Caută context specific
mem search "problema mea"
```

### 4. Verificare performanță

```bash
# Testează viteza căutării
time mem search "test"

# Verifică dimensiune DB
mem stats | grep "Dimensiune DB"

# Vezi statistici reconciler
mem trace | grep "reconciler"
```

## 🎯 Best Practices

### 1. După Auto-Compact
```bash
# Întotdeauna rulează reload după auto-compact
mem reload
```

### 2. Debugging Erori
```bash
# Mai întâi caută dacă eroarea e cunoscută
mem err "eroarea mea"

# Apoi reconciliază erori noi
mem reconcile
```

### 3. Menținere DB
```bash
# Periodic rulează optimize (safe)
~/.claude/memory/scripts/p2_safe_optimize.sh
```

### 4. Backup
```bash
# Backup manual DB
cp ~/.claude/memory/global.db ~/backups/global_$(date +%Y%m%d).db
```

## ⚡ Tips & Tricks

### Căutări Rapide

```bash
# Alias-uri utile în .bashrc
alias ms='mem search'
alias me='mem err'
alias mt='mem trace'
alias mr='mem reload'
```

### Monitoring Context

```bash
# Verifică când a fost ultimul compact
mem search "compact_boundary" --limit 1

# Vezi context_pct curent
mem trace | grep context_pct | tail -1
```

### Statistici Rapide

```bash
# Câte mesaje avem?
mem stats | grep "Mesaje totale"

# Câte erori nerezolvate?
mem err --unresolved | wc -l
```

## 🐛 Troubleshooting

Vezi [TROUBLESHOOTING.md](TROUBLESHOOTING.md) pentru probleme comune și soluții.

## 📚 Documentație Suplimentară

- [README.md](README.md) - Overview complet
- [DOCUMENTATION.md](DOCUMENTATION.md) - Arhitectură tehnică
- [DEV_LOG.md](DEV_LOG.md) - Istoric dezvoltare
- [CHANGELOG.md](CHANGELOG.md) - Istoric schimbări

---

**🎉 Happy Searching!**
