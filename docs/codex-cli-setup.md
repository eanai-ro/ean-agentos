# Codex CLI — Setup Guide

Conectează Codex CLI (OpenAI) la EAN AgentOS pentru memorie persistentă între sesiuni.

## Cerințe

- Python 3.10+
- EAN AgentOS server pornit (`python3 scripts/web_server.py`)
- Codex CLI instalat

## Setup rapid

### 1. Pornește serverul

```bash
cd /path/to/universal-agent-memory
python3 scripts/web_server.py
# Server runs on http://localhost:19876
```

### 2. Copiază adaptorul

```bash
cp scripts/adapters/codex_cli_adapter.py ~/.codex/
```

### 3. Folosește în cod

```python
from codex_cli_adapter import CodexMemoryAdapter

mem = CodexMemoryAdapter(
    base_url="http://localhost:19876",
    project_path="/path/to/your/project",
    model_name="o3",
)

# Start session
mem.start_session("Working on feature X")

# Load context from previous sessions
ctx = mem.get_context(mode="compact", intent="debugging")
print(ctx.get("context_text", ""))

# Save a decision
mem.create_decision("Use async handlers", description="Better performance")

# Save a fact
mem.create_fact("API rate limit is 100 req/min", fact_type="gotcha")

# Save error resolution
mem.create_resolution(
    "TypeError: None not subscriptable",
    "Added None check before dict access",
    resolution_type="fix"
)

# Log activity
mem.log_activity("Analyzed codebase structure")

# Check server health
mem.get_health()
```

## Toate metodele disponibile

| Metodă | Ce face |
|--------|---------|
| `start_session(title)` | Începe o sesiune nouă |
| `get_context(mode, intent)` | Primește context din memoria anterioară |
| `create_decision(title, description, category)` | Salvează o decizie |
| `create_fact(fact, fact_type, category)` | Salvează un fact/cunoștință |
| `create_goal(title, description, priority)` | Creează un obiectiv |
| `create_task(title, description, priority)` | Creează un task |
| `create_resolution(error_summary, resolution)` | Salvează rezolvarea unei erori |
| `log_activity(summary, payload)` | Loghează o activitate |
| `send_event(event_type, title, payload)` | Trimite un eveniment |
| `get_activity(limit)` | Listează activitățile recente |
| `get_health()` | Verifică starea serverului |

## Context modes

| Mode | Când să-l folosești |
|------|---------------------|
| `compact` | Default — rezumat concis, ideal pentru prompt injection |
| `full` | Tot contextul disponibil, pentru analiză detaliată |
| `survival` | Doar informațiile critice (erori, decizii blocante) |
| `delta` | Doar ce s-a schimbat de la ultima cerere |

## Codex-specific: System prompt injection

Codex CLI folosește un system prompt. Poți injecta contextul din memorie:

```python
ctx = mem.get_context(mode="compact")
system_prompt = f"""## Project Memory (auto-loaded)
{ctx.get('context_text', '')}
## End Memory"""
```

## Auto-capture cu JSONL Rollout Watcher

Codex CLI nu are hooks ca Claude Code sau Gemini CLI, dar generează fișiere JSONL în `~/.codex/sessions/`. Un watcher incremental le procesează automat.

### Instalare watcher (systemd)

```bash
python3 scripts/ean_memory.py install codex
```

Aceasta:
1. Copiază adaptorul în `~/.codex/`
2. Inițializează DB-ul (`~/.ean-memory/global.db`)
3. Importă istoricul existent (`--once`)
4. Creează și pornește un serviciu systemd user care monitorizează JSONL-urile

### Verificare status

```bash
systemctl --user status ean-codex-watcher
python3 scripts/codex_rollout_watcher.py --status
```

### Dezinstalare

```bash
python3 scripts/ean_memory.py uninstall codex
```

### Procesare manuală (fără systemd)

```bash
# O singură rulare
python3 scripts/codex_rollout_watcher.py --once

# Monitorizare continuă
python3 scripts/codex_rollout_watcher.py --watch --interval 10
```

## Vezi și

- [Exemplu complet](examples/codex_adapter_usage.py)
- [API Reference](api.md)
- [Adapters Spec](spec-adapters.md)
- [Kimi CLI Setup](kimi-cli-setup.md) — alternativă cu MCP nativ
