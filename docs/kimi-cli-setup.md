# Kimi CLI — Setup Guide

Conectează Kimi CLI (Moonshot AI) la Universal Agent Memory pentru memorie persistentă între sesiuni.

## Cerințe

- Python 3.10+
- Universal Agent Memory server pornit (`python3 scripts/web_server.py`)
- Kimi CLI instalat (`pip install kimi-cli` sau conform [documentației oficiale](https://github.com/MoonshotAI/kimi-cli))

## Setup rapid (MCP — recomandat)

Kimi CLI suportă MCP nativ. Nu ai nevoie de adapter separat — conectezi direct la MCP server-ul existent.

### 1. Pornește serverul

```bash
cd /path/to/ean-agentos
python3 scripts/web_server.py
# Server runs on http://localhost:19876
```

### 2. Adaugă MCP server

```bash
kimi mcp add --transport stdio \
  -e "MEMORY_BASE_URL=http://localhost:19876" \
  -e "MEMORY_PROJECT_PATH=/path/to/your/project" \
  -e "MEMORY_AGENT_NAME=kimi-cli" \
  -e "MEMORY_MODEL_NAME=kimi-k2.5" \
  -e "MEMORY_PROVIDER=moonshot" \
  universal-memory \
  -- python3 /path/to/ean-agentos/mcp_server/server.py
```

### 3. Verifică conexiunea

```bash
kimi mcp test universal-memory
```

Output așteptat:
```
Testing connection to 'universal-memory'...
✓ Connected to 'universal-memory'
  Available tools: 13
```

### 4. Verifică lista

```bash
kimi mcp list
```

## Configurare manuală (alternativă)

Editează `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "universal-memory": {
      "command": "python3",
      "args": ["/path/to/ean-agentos/mcp_server/server.py"],
      "env": {
        "MEMORY_BASE_URL": "http://localhost:19876",
        "MEMORY_PROJECT_PATH": "/path/to/your/project",
        "MEMORY_AGENT_NAME": "kimi-cli",
        "MEMORY_MODEL_NAME": "kimi-k2.5",
        "MEMORY_PROVIDER": "moonshot"
      }
    }
  }
}
```

## Tools disponibile (13)

Odată conectat, Kimi CLI are acces la toate tool-urile MCP:

### Context
| Tool | Descriere |
|------|-----------|
| `memory_get_context` | Încarcă contextul — decizii, fapte, obiective, task-uri, rezoluții |

### Scriere memorie
| Tool | Descriere |
|------|-----------|
| `memory_create_decision` | Înregistrează o decizie arhitecturală/tehnică |
| `memory_create_fact` | Salvează un fapt sau o cunoștință |
| `memory_create_goal` | Creează un obiectiv de nivel înalt |
| `memory_create_task` | Creează un task concret |
| `memory_create_resolution` | Înregistrează cum a fost rezolvată o eroare |

### Branch-uri
| Tool | Descriere |
|------|-----------|
| `memory_list_branches` | Listează branch-urile de memorie |
| `memory_switch_branch` | Schimbă branch-ul activ |
| `memory_compare_branches` | Compară două branch-uri |
| `memory_merge_branch` | Merge un branch în target |

### Observabilitate
| Tool | Descriere |
|------|-----------|
| `memory_get_health` | Metrici de sănătate |
| `memory_get_activity` | Jurnal de activitate |
| `memory_get_timeline` | Timeline cronologic |

## Utilizare în sesiune

După configurare, Kimi CLI va avea acces automat la tool-urile de memorie. Exemple de comenzi naturale:

```
# Încarcă context din sesiunile anterioare
"Încarcă contextul memoriei pentru proiectul curent"

# Salvează o decizie
"Salvează decizia: folosim PostgreSQL pentru baza de date principală"

# Salvează un fact
"Notează: API-ul extern are rate limit de 100 req/min"

# Înregistrează rezolvarea unei erori
"Am rezolvat eroarea TypeError prin adăugarea verificării None"

# Verifică starea memoriei
"Arată-mi health-ul memoriei"
```

## Context modes

| Mode | Când să-l folosești |
|------|---------------------|
| `compact` | Default — rezumat concis |
| `full` | Tot contextul disponibil |
| `survival` | Doar informațiile critice |
| `delta` | Doar ce s-a schimbat recent |

## Gestionare MCP

```bash
# Listează servere MCP
kimi mcp list

# Elimină serverul
kimi mcp remove universal-memory

# Re-testează conexiunea
kimi mcp test universal-memory
```

## Troubleshooting

| Problemă | Soluție |
|----------|---------|
| `Connection refused` | Verifică că serverul web rulează: `python3 scripts/web_server.py` |
| `No tools available` | Rulează `kimi mcp test universal-memory` pentru diagnostic |
| Context gol | Normal la prima utilizare — memoria se construiește în timp |
| Timeout | Verifică că portul 19876 nu e blocat de firewall |

## Diferențe față de alte CLI-uri

| Aspect | Claude Code | Gemini CLI | Codex CLI | Kimi CLI |
|--------|-------------|------------|-----------|----------|
| Integrare | Hooks + MCP | Hooks + Adapter | Watcher + Adapter | **MCP nativ** |
| Auto-capture | Da (hooks) | Da (hooks) | Da (JSONL watcher) | Via MCP tools |
| Config | `~/.claude/.mcp.json` | `~/.gemini/settings.json` | `~/.codex/` | `~/.kimi/mcp.json` |

## Vezi și

- [MCP Server](mcp.md) — detalii protocol MCP
- [API Reference](api.md) — endpoints REST
- [Architecture](architecture.md) — design-ul sistemului
