# Troubleshooting - Probleme Comune și Soluții

## 🔍 Probleme Frecvente

### 1. "mem: command not found"

**Problemă:** CLI-ul `mem` nu e în PATH.

**Soluție:**
```bash
# Verifică dacă scriptul există
ls -la scripts/mem

# Verifică dacă e executabil
chmod +x scripts/mem

# Adaugă în PATH (în ~/.bashrc sau ~/.zshrc)
export PATH="$HOME/.claude/memory/scripts:$PATH"

# Reîncarcă shell
source ~/.bashrc  # sau source ~/.zshrc
```

### 2. "Database is locked"

**Problemă:** Altă sesiune Claude Code folosește DB-ul.

**Soluție:**
```bash
# Verifică procese care folosesc DB-ul
lsof ./global.db

# Dacă nu e niciun proces legitim, șterge lock-ul
rm -f ./global.db-wal
rm -f ./global.db-shm

# Verifică integritate după
sqlite3 ./global.db "PRAGMA quick_check;"
```

### 3. "mem search" foarte lent (>1s)

**Problemă:** FTS5 nu e folosit sau DB-ul e corupt.

**Diagnostic:**
```bash
# Verifică dacă FTS5 există
sqlite3 ./global.db "SELECT COUNT(*) FROM messages_fts;"

# Verifică query plan
sqlite3 ./global.db "EXPLAIN QUERY PLAN SELECT * FROM messages_fts WHERE messages_fts MATCH 'test';"
```

**Soluție:**
```bash
# Re-run optimize
scripts/p2_safe_optimize.sh

# Dacă e necesar, rebuild FTS5
scripts/fts_backfill.py
```

### 4. "AUTOCOMPACT se declanșează tot timpul"

**Problemă:** CLAUDE_AUTOCOMPACT_PCT_OVERRIDE nu e setat.

**Soluție:**
```bash
# Verifică variabila
echo $CLAUDE_AUTOCOMPACT_PCT_OVERRIDE

# Dacă lipsește, adaugă în ~/.bashrc
echo 'export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=100' >> ~/.bashrc
source ~/.bashrc

# Verifică în toate launcher-ele
grep AUTOCOMPACT ~/.local/bin/claude*
```

### 5. "Telegram alerts nu funcționează"

**Problemă:** Token sau Chat ID greșit/lipsă.

**Diagnostic:**
```bash
# Verifică variabilele
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID

# Test manual
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
```

**Soluție:**
```bash
# Setează variabilele corect
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# Sau în ~/.claude/.env
echo "TELEGRAM_BOT_TOKEN=your_token" >> ~/.claude/.env
echo "TELEGRAM_CHAT_ID=your_chat_id" >> ~/.claude/.env
```

### 6. "mem reconcile" găsește prea multe erori

**Problemă:** Reconciler-ul detectează false positives.

**Soluție:**
```bash
# Verifică log-ul reconciler
tail -100 ./daemon_debug.log | grep RECONCILER

# Verifică drift detection
mem reconcile | jq '.drift_detected'

# Dacă e drift persistent, restart daemon
# (se va reporni automat la următorul hook)
```

### 7. "DB prea mare" (>1GB)

**Problemă:** DB-ul crește foarte mult.

**Diagnostic:**
```bash
# Verifică dimensiune
du -sh ./global.db

# Verifică ce ocupă spațiu
sqlite3 ./global.db "
SELECT name, COUNT(*) as rows 
FROM sqlite_master m JOIN (
  SELECT 'messages' as name, COUNT(*) as cnt FROM messages
  UNION SELECT 'tool_calls', COUNT(*) FROM tool_calls
  UNION SELECT 'bash_history', COUNT(*) FROM bash_history
) t ON m.name = t.name
GROUP BY name ORDER BY rows DESC;
"
```

**Soluție (opțional - cu backup!):**
```bash
# Backup mai întâi
cp ./global.db ~/backup_$(date +%Y%m%d).db

# VACUUM (eliberează spațiu)
sqlite3 ./global.db "VACUUM;"

# Verifică integritate
sqlite3 ./global.db "PRAGMA integrity_check;"
```

### 8. "Git repo corupt"

**Problemă:** Git repo are probleme.

**Diagnostic:**
```bash
cd /path/to/ean-agentos
git status
git fsck
```

**Soluție:**
```bash
# Backup repo
tar -czf ~/git_backup_$(date +%Y%m%d).tar.gz .git

# Repară
git fsck --full
git gc --aggressive --prune=now

# Dacă e necesar, re-init
# (ATENȚIE: pierzi istoricul!)
rm -rf .git
git init
git add .
git commit -m "Re-init after corruption"
```

## 🔧 Maintenance Rutină

### Lunar

```bash
# 1. Backup DB
cp ./global.db ~/backups/global_$(date +%Y%m%d).db

# 2. Optimize DB
scripts/p2_safe_optimize.sh

# 3. Verifică integritate
sqlite3 ./global.db "PRAGMA integrity_check;"

# 4. Git commit dacă ai modificări
cd /path/to/ean-agentos
git add -A
git commit -m "Monthly update $(date +%Y-%m-%d)"
```

### După Update Claude Code

```bash
# 1. Verifică hooks
cat ~/.claude/settings.json | jq '.hooks'

# 2. Test mem CLI
mem stats

# 3. Verifică FTS5
sqlite3 ./global.db "SELECT COUNT(*) FROM messages_fts;"

# 4. Test reconciler
mem reconcile
```

## 📊 Performance Debugging

### Identificare Query Lente

```bash
# Enable query timing
sqlite3 ./global.db

.timer on
SELECT * FROM messages WHERE content LIKE '%test%' LIMIT 10;
.quit
```

### Verificare Indexuri

```bash
# Listează indexuri
sqlite3 ./global.db "
SELECT name, tbl_name 
FROM sqlite_master 
WHERE type='index' 
ORDER BY tbl_name, name;
"

# Verifică dacă indexurile sunt folosite
sqlite3 ./global.db "
EXPLAIN QUERY PLAN 
SELECT * FROM messages WHERE session_id = 'test';
"
```

### Profilare Completă

```bash
# Rulează profilare
scripts/p2a2_profile_mem.sh

# Analizează rezultatele
cat /tmp/claude_P2A2_profile_*/run.txt
```

## 🚨 Erori Critice

### "Database is malformed"

**CRICTIC!** DB-ul e corupt.

```bash
# 1. NU continua să folosești DB-ul!

# 2. Restaurează din backup
cp ~/backups/global_YYYYMMDD.db ./global.db

# 3. Verifică integritate
sqlite3 ./global.db "PRAGMA integrity_check;"

# 4. Dacă nu ai backup, recovery
sqlite3 ./global.db ".recover" | sqlite3 recovered.db
```

### "Out of memory"

**Problemă:** Query prea mare sau sistem low memory.

```bash
# 1. Verifică memoria sistem
free -h

# 2. Limitează query-uri
mem search "text" --limit 10  # nu 1000!

# 3. Cleanup procese
pkill -f "claude"
```

## 📞 Support

### Log-uri Utile

```bash
# Daemon log
tail -100 ./daemon_debug.log

# Compact trace
tail -100 ./compact_trace.log

# Realtime monitor
tail -100 ./realtime_monitor.log
```

### Informații de Debug

```bash
# Colectează info pentru debugging
cat > ~/debug_info.txt << EOF
=== System Info ===
$(uname -a)
$(date)

=== Claude Code Version ===
$(claude --version)

=== Mem Stats ===
$(mem stats)

=== DB Size ===
$(du -sh ./global.db)

=== Env Vars ===
AUTOCOMPACT: $CLAUDE_AUTOCOMPACT_PCT_OVERRIDE
CLAUDECODE: $CLAUDECODE

=== Recent Errors ===
$(mem err --limit 5)
