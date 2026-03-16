# MANUAL DE UTILIZARE — EAN AgentOS

**Versiune:** v1.3
**Data:** 2026-03-15

---

## 1. Instalare

### Cerințe
- Python 3.10+
- SQLite 3.35+ (cu suport FTS5)

### Pași

```bash
# 1. Clonează / copiază proiectul
cd /path/to/ean-agentos

# 2. Instalează dependențele
pip install -r requirements.txt

# 3. Inițializează baza de date
python3 scripts/init_db.py

# 4. (Opțional) Populează cu date demo
python3 scripts/demo_seed.py
```

---

## 2. CLI — Comanda `mem`

Punctul principal de interacțiune. Rulează din directorul proiectului.

### Operații CRUD

```bash
# Decizii
python3 scripts/mem decide "Folosim PostgreSQL" -d "Mai bun pentru producție" -c technical
python3 scripts/mem decisions                    # Listare
python3 scripts/mem decide-supersede 1 "Folosim MySQL" -d "Schimbare plan"

# Facts
python3 scripts/mem learn "Rate limit API = 100 req/min" -t convention
python3 scripts/mem learn "Port default Redis = 6379" -t technical --pin
python3 scripts/mem facts                        # Listare

# Goals
python3 scripts/mem goal "Finalizare modul auth" -p high
python3 scripts/mem goals                        # Listare
python3 scripts/mem goal-done 1                  # Marcare completat

# Tasks
python3 scripts/mem task "Scrie unit tests" -p high --goal 1
python3 scripts/mem tasks                        # Listare
python3 scripts/mem task-done 1                  # Marcare completat

# Erori rezolvate
python3 scripts/mem resolve "TypeError pe null" -s "Adăugat verificare None"
python3 scripts/mem resolutions                  # Listare
```

### Context

```bash
python3 scripts/mem context --compact     # Context esențial
python3 scripts/mem context --full        # Tot contextul
python3 scripts/mem context --survival    # Minim (după compaction)
python3 scripts/mem context --delta       # Doar schimbări recente
```

### Branches

```bash
python3 scripts/mem branch list
python3 scripts/mem branch create feature-x -d "Explorare feature"
python3 scripts/mem branch switch feature-x
python3 scripts/mem branch compare main feature-x
python3 scripts/mem branch merge feature-x --into main
```

### Alte comenzi

```bash
python3 scripts/mem dashboard             # Status rapid
python3 scripts/mem timeline              # Cronologie
python3 scripts/mem search "redis"        # Căutare full-text
python3 scripts/mem intent set debugging  # Setare intent
python3 scripts/mem health                # Health check
```

---

## 3. Web Dashboard

```bash
# Pornire server
python3 scripts/web_server.py
# sau
./scripts/run_server.sh

# Acces
# http://192.168.205.222:19876 (din rețea)
# http://localhost:19876 (local)
```

Dashboard-ul oferă:
- Vizualizare toate entitățile (decisions, facts, goals, tasks, resolutions)
- Management branches
- Timeline activitate
- Health check
- Checkpoints (save/restore)

---

## 4. REST API

### Universal API (`/api/v1/`)

```bash
# Decisions
POST   /api/v1/decisions          # Creare decizie
GET    /api/v1/decisions          # Listare decizii

# Facts
POST   /api/v1/facts              # Creare fact
GET    /api/v1/facts              # Listare facts

# Goals
POST   /api/v1/goals              # Creare goal
GET    /api/v1/goals              # Listare goals

# Tasks
POST   /api/v1/tasks              # Creare task
GET    /api/v1/tasks              # Listare tasks

# Resolutions
POST   /api/v1/resolve            # Creare rezoluție
GET    /api/v1/resolutions        # Listare rezoluții

# Context
GET    /api/v1/context            # Get context
       ?project=/path&mode=compact

# Health
GET    /api/v1/health             # Health check
```

### Dashboard API (`/api/`)

```bash
GET    /api/dashboard             # Stats generale
GET    /api/health                # Health
GET    /api/activity              # Activity log
GET    /api/branches              # Listare branches
POST   /api/branches              # Creare branch
POST   /api/branches/switch       # Switch branch
POST   /api/branches/merge        # Merge branch
GET    /api/branches/compare      # Compare branches
GET    /api/checkpoints           # Listare checkpoints
POST   /api/checkpoints/save      # Save checkpoint
POST   /api/checkpoints/restore   # Restore checkpoint
```

### Exemplu cURL

```bash
curl -X POST http://localhost:19876/api/v1/decisions \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Folosim SQLite",
    "description": "Simplu, embedded, fără server",
    "category": "technical",
    "project_path": "/mnt/lucru/proiecte/claude/ean-agentos"
  }'
```

---

## 5. Integrare CLI-uri AI

### Claude Code (hooks)

Configurare automată prin `config/hooks.json`. Hooks-urile captează:
- `SessionStart` / `SessionStop`
- `UserPromptSubmit`
- `PreToolUse` / `PostToolUse`
- `PreCompact`

### Gemini CLI (Python hooks)

Configurare în `~/.gemini/settings.json`:
```json
{
  "hooks": {
    "agent_start": {"command": "python3 /path/to/gemini_hook.py session_start"},
    "before_agent": {"command": "python3 /path/to/gemini_hook.py user_prompt"},
    "after_agent": {"command": "python3 /path/to/gemini_hook.py assistant_response"},
    "before_tool": {"command": "python3 /path/to/gemini_hook.py pre_tool"},
    "after_tool": {"command": "python3 /path/to/gemini_hook.py post_tool"}
  }
}
```

### Codex CLI (JSONL Watcher)

```bash
# Rulare o dată
python3 scripts/codex_rollout_watcher.py --once

# Watch continuu
python3 scripts/codex_rollout_watcher.py --watch

# Status
python3 scripts/codex_rollout_watcher.py --status
```

### Kimi CLI (MCP native)

```bash
kimi mcp add --transport stdio \
  -e "MEMORY_BASE_URL=http://localhost:19876" \
  -e "MEMORY_AGENT_NAME=kimi-cli" \
  universal-memory \
  -- python3 /path/to/mcp_server/server.py
```

---

## 6. MCP Server

Serverul MCP expune 13 tool-uri pentru agenți AI:

| Tool | Descriere |
|------|-----------|
| `memory_get_context` | Obține context |
| `memory_store_decision` | Salvează decizie |
| `memory_store_fact` | Salvează fact |
| `memory_store_goal` | Salvează goal |
| `memory_store_task` | Salvează task |
| `memory_resolve_error` | Salvează rezoluție eroare |
| `memory_search` | Căutare full-text |
| `memory_health` | Health check |
| `memory_list_branches` | Listare branches |
| `memory_switch_branch` | Switch branch |
| `memory_timeline` | Timeline cronologic |
| `memory_checkpoint_save` | Salvare checkpoint |
| `memory_checkpoint_restore` | Restaurare checkpoint |

```bash
# Pornire
./scripts/run_mcp.sh
# sau
python3 mcp_server/server.py
```

---

## 7. Backup & Restore

```bash
# Backup manual
./scripts/mem_backup.sh

# Auto backup (cron recomandat)
./scripts/auto_backup.sh

# Restore
python3 scripts/restore_version.py <backup_file>
```

---

## 8. Troubleshooting

### DB locked
Cauză: Altă instanță accesează DB-ul simultan.
Soluție: `kill` procesele vechi sau restartează serverul.

### Context gol
Cauză: DB-ul pointat este gol sau nu există.
Soluție: Verifică `MEMORY_DB_PATH` env var.

### Server nu pornește
Cauză: Portul 19876 ocupat.
Soluție: `ss -ltn | grep 19876` apoi `kill <PID>`.
