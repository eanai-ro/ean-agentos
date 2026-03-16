# Gemini CLI — Setup Guide

Conectează Gemini CLI la Universal Agent Memory pentru a avea memorie persistentă între sesiuni.

## Cerințe

- Python 3.10+
- Universal Agent Memory server pornit (`python3 scripts/web_server.py`)
- Gemini CLI instalat

## Setup rapid

### 1. Pornește serverul

```bash
cd /path/to/universal-agent-memory
python3 scripts/web_server.py
# Server runs on http://localhost:19876
```

### 2. Copiază adaptorul

```bash
cp scripts/adapters/gemini_cli_adapter.py ~/.gemini/
```

### 3. Folosește în cod

```python
from gemini_cli_adapter import GeminiMemoryAdapter

mem = GeminiMemoryAdapter(
    base_url="http://localhost:19876",
    project_path="/path/to/your/project",
    model_name="gemini-2.5-pro",
)

# Start session
mem.start_session("Working on feature X")

# Load context from previous sessions
ctx = mem.get_context(mode="compact", intent="feature")
print(ctx.get("context_text", ""))

# Save a decision
mem.create_decision("Use PostgreSQL", description="For JSONB support")

# Save a fact
mem.create_fact("API rate limit is 100 req/min", fact_type="gotcha")

# Save a task
mem.create_task("Write auth tests", priority="high")

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

## Intent-uri pentru context inteligent

Adaugă `intent` pentru a primi context relevant automat:

```python
ctx = mem.get_context(mode="compact", intent="debugging")   # prioritizează erori
ctx = mem.get_context(mode="compact", intent="feature")     # prioritizează decizii
ctx = mem.get_context(mode="compact", intent="deploy")      # prioritizează configurări
```

## Branch-uri de memorie

Lucrezi pe o idee experimentală? Folosește branch-uri:

```python
# Creează branch (via CLI — nu există endpoint API)
# mem branch create experiment-redis

# Switch pe branch
mem._post("/api/branches/switch", {"branch": "experiment-redis"})

# Lucrează normal — totul se salvează pe branch
mem.create_decision("Use Redis for cache")

# Compară cu main
diff = mem._get("/api/branches/compare", {"branch1": "main", "branch2": "experiment-redis"})

# Merge înapoi
mem._post("/api/branches/merge", {"source": "experiment-redis", "target": "main", "confirm": True})
```

## Server pe alt host

Dacă serverul rulează pe altă mașină:

```python
mem = GeminiMemoryAdapter(
    base_url="http://192.168.1.100:19876",
    project_path="/path/to/project",
)
```

## Troubleshooting

| Problemă | Soluție |
|----------|---------|
| `Connection refused` | Verifică că serverul e pornit: `python3 scripts/web_server.py` |
| Context gol | Normal la prima utilizare — memoria se construiește în timp |
| Timeout | Crește timeout: `UniversalMemoryClient(..., timeout=30)` |

## Auto-capture cu Hooks

Gemini CLI suportă hooks native (similar cu Claude Code). Configurarea se face în `~/.gemini/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py session_start"}]}],
    "BeforeAgent": [{"hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py user_prompt"}]}],
    "AfterAgent": [{"hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py assistant_response"}]}],
    "BeforeTool": [{"matcher": "replace|write_file|multi_edit", "hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py pre_tool"}]}],
    "AfterTool": [{"matcher": ".*", "hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py post_tool"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py session_end"}]}],
    "PreCompress": [{"hooks": [{"type": "command", "command": "python3 /path/to/scripts/hooks/gemini/gemini_hook.py pre_compact"}]}]
  }
}
```

Hook-ul `gemini_hook.py` traduce payload-urile Gemini CLI în formatul așteptat de `memory_daemon.py` (tool names, response keys, etc.) și trimite totul la baza de date.

### Instalare hooks

```bash
python3 scripts/ean_memory.py install gemini
```

## Vezi și

- [Exemplu complet](examples/gemini_adapter_usage.py)
- [API Reference](api.md)
- [Adapters Spec](spec-adapters.md)
- [Branch-uri](branches.md)
- [Kimi CLI Setup](kimi-cli-setup.md) — alternativă cu MCP nativ
