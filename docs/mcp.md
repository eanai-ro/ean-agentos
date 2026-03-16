# MCP Bridge — Model Context Protocol

Universal Agent Memory expune un server MCP (Model Context Protocol) care permite oricărui agent AI compatibil să acceseze memoria persistentă prin protocol standardizat.

## Ce este MCP?

[Model Context Protocol](https://modelcontextprotocol.io/) este un standard deschis creat de Anthropic pentru comunicarea între aplicații AI și surse de date externe. MCP folosește transport stdio (stdin/stdout) sau streamable-http, permițând integrare directă cu:

- **Claude Code** / **Claude Desktop**
- **Gemini CLI** (Google)
- **Codex CLI** (OpenAI)
- **Kimi CLI** (Moonshot AI)
- **Cursor IDE**
- **VSCode AI extensions**
- **LangGraph**, **CrewAI**, **AutoGen**
- **OpenAI Agents SDK**
- Orice client MCP compatibil

## Pornire server

```bash
# Direct
python mcp_server/server.py

# Sau via mcp CLI
mcp run mcp_server/server.py
```

Serverul folosește transport **stdio** (implicit) — nu deschide porturi, comunică prin stdin/stdout.

> **Prerequisite:** API-ul memory trebuie să ruleze (`python scripts/memory_daemon.py`).

## Configurare

Variabile de mediu:

| Variabilă | Default | Descriere |
|-----------|---------|-----------|
| `MEMORY_BASE_URL` | `http://localhost:19876` | URL-ul API-ului memory |
| `MEMORY_PROJECT_PATH` | directorul curent | Calea proiectului |
| `MEMORY_AGENT_NAME` | `mcp-agent` | Numele agentului |
| `MEMORY_MODEL_NAME` | `unknown` | Modelul AI folosit |
| `MEMORY_PROVIDER` | `mcp` | Providerul AI |

## Configurare per CLI

### Claude Code (`~/.claude/.mcp.json`)

```json
{
  "mcpServers": {
    "universal-memory": {
      "command": "python3",
      "args": ["/path/to/ean-agentos/mcp_server/server.py"],
      "env": {
        "MEMORY_BASE_URL": "http://localhost:19876",
        "MEMORY_PROJECT_PATH": "/home/user",
        "MEMORY_AGENT_NAME": "claude-code",
        "MEMORY_MODEL_NAME": "claude-opus-4-6",
        "MEMORY_PROVIDER": "anthropic"
      }
    }
  }
}
```

### Gemini CLI (`~/.gemini/settings.json`)

Gemini CLI folosește hooks (nu MCP) pentru auto-capture. Vezi [Gemini CLI Setup](gemini-cli-setup.md).

MCP poate fi adăugat suplimentar dacă Gemini CLI suportă secțiunea `mcpServers` în settings.

### Codex CLI

Codex CLI folosește JSONL watcher + adapter pentru auto-capture. Vezi [Codex CLI Setup](codex-cli-setup.md).

### Kimi CLI (`~/.kimi/mcp.json`)

```bash
kimi mcp add --transport stdio \
  -e "MEMORY_BASE_URL=http://localhost:19876" \
  -e "MEMORY_PROJECT_PATH=/path/to/project" \
  -e "MEMORY_AGENT_NAME=kimi-cli" \
  -e "MEMORY_MODEL_NAME=kimi-k2.5" \
  -e "MEMORY_PROVIDER=moonshot" \
  universal-memory \
  -- python3 /path/to/ean-agentos/mcp_server/server.py
```

Sau manual în `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "universal-memory": {
      "command": "python3",
      "args": ["/path/to/ean-agentos/mcp_server/server.py"],
      "env": {
        "MEMORY_BASE_URL": "http://localhost:19876",
        "MEMORY_PROJECT_PATH": "/path/to/project",
        "MEMORY_AGENT_NAME": "kimi-cli",
        "MEMORY_MODEL_NAME": "kimi-k2.5",
        "MEMORY_PROVIDER": "moonshot"
      }
    }
  }
}
```

Verificare: `kimi mcp test universal-memory`

## Tools disponibile (13)

### Context
| Tool | Descriere |
|------|-----------|
| `memory_get_context` | Încarcă contextul memoriei — decizii, fapte, obiective, task-uri, rezoluții |

### Scriere memorie
| Tool | Descriere |
|------|-----------|
| `memory_create_decision` | Înregistrează o decizie arhitecturală/tehnică |
| `memory_create_fact` | Salvează un fapt sau o cunoștință învățată |
| `memory_create_goal` | Creează un obiectiv de nivel înalt |
| `memory_create_task` | Creează un task concret |
| `memory_create_resolution` | Înregistrează cum a fost rezolvată o eroare |

### Branch-uri
| Tool | Descriere |
|------|-----------|
| `memory_list_branches` | Listează branch-urile de memorie cu contoare |
| `memory_switch_branch` | Schimbă branch-ul activ |
| `memory_compare_branches` | Compară două branch-uri |
| `memory_merge_branch` | Merge un branch sursă în target |

### Observabilitate
| Tool | Descriere |
|------|-----------|
| `memory_get_health` | Metrici de sănătate — contoare entități, items stale |
| `memory_get_activity` | Jurnal de activitate recentă |
| `memory_get_timeline` | Timeline cronologic al evenimentelor |

## Utilizare în agenți

### Python (direct)

```python
from mcp_server.tools import get_context, create_decision

# Încarcă context
ctx = get_context(mode="compact", project_path="/my/project")
print(ctx["context_text"])

# Salvează o decizie
create_decision("Use Redis for caching",
                description="Better performance for hot data",
                category="architectural",
                project_path="/my/project")
```

### LangGraph / CrewAI / AutoGen

Acești framework-uri suportă MCP nativ sau prin adaptoare. Configurează serverul ca subprocess:

```python
# LangGraph exemplu
from langchain_mcp import MCPToolkit

toolkit = MCPToolkit(
    server_command="python",
    server_args=["/path/to/mcp_server/server.py"],
    env={"MEMORY_BASE_URL": "http://localhost:19876"}
)
tools = toolkit.get_tools()
```

### OpenAI Agents SDK

```python
from agents import Agent
from agents.mcp import MCPServerStdio

memory_server = MCPServerStdio(
    command="python",
    args=["/path/to/mcp_server/server.py"],
    env={"MEMORY_BASE_URL": "http://localhost:19876"}
)

agent = Agent(
    name="coding-agent",
    tools=memory_server.tools(),
)
```

## Arhitectură

```
Agent AI  ←→  MCP Server (stdio)  ←→  REST API  ←→  SQLite DB
                 server.py              memory_daemon.py
                 tools.py               dashboard_api.py
                 config.py              universal_api.py
```

MCP server-ul este un **layer de delegare** — nu conține logică de business. Toate operațiile trec prin `UniversalMemoryClient` → HTTP API → SQLite.
