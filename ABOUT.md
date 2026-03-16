# EAN AgentOS

## Ce este?

EAN AgentOS este un sistem de memorie persistentă pentru agenți AI de coding. Dă agenților (Claude Code, Gemini CLI, Codex CLI și alții) capacitatea de a **reține și partaja cunoștințe între sesiuni**.

## Problema

Agenții AI pierd tot contextul când sesiunea se încheie. Asta înseamnă că:

- Repetă aceleași greșeli
- Uită deciziile luate anterior
- Nu pot colabora între ei pe același proiect
- Trebuie re-explicat contextul de fiecare dată

## Soluția

O bază de date SQLite structurată, cu un CLI complet, un API REST universal și un dashboard web. Orice agent poate stoca și citi:

| Ce stochează | Exemplu |
|-------------|---------|
| **Decizii** | "Am ales PostgreSQL pentru suport JSONB" |
| **Cunoștințe** | "Rate limit-ul API-ului e 100 req/min" |
| **Obiective** | "Finalizare modul autentificare" |
| **Task-uri** | "Scrie teste unitare pentru auth" |
| **Rezolvări erori** | "TypeError X → adaugă verificare None" |

## Cum funcționează

```
  Agent A (Claude)  ──┐
  Agent B (Gemini)  ──┤──→  Universal Memory API  ──→  SQLite DB
  Agent C (Codex)   ──┤        ↕
  Agent D (custom)  ──┘   Web Dashboard
```

1. **Agentul scrie** — salvează o decizie, un fact, un goal, un task sau o rezolvare
2. **Memoria reține** — totul e persistent, structurat și atribuit (cine, când, cu ce model)
3. **Agentul citește** — primește context relevant, filtrat inteligent, gata de injectat în prompt

## Ce îl face diferit

### Branch-uri de memorie
Ca în git, dar pentru cunoștințe. Poți crea un branch experimental, lucra pe el fără să afectezi memoria principală, compara diferențele, și merge înapoi când ești mulțumit.

```bash
mem branch create experiment-redis
mem branch switch experiment-redis
mem decide -t "Folosim Redis pentru cache" -d "Test de performanță"
mem branch compare main experiment-redis
mem branch merge experiment-redis --into main
```

### Context inteligent
Nu primești tot — primești ce contează. Sistemul de context are 4 moduri și se adaptează automat la ce faci:

- Debugging? → Prioritizează rezolvări de erori anterioare
- Feature nou? → Prioritizează decizii arhitecturale și goals
- Deploy? → Prioritizează convenții și configurări

### Multi-agent
Orice agent se poate conecta. Vine cu adaptori gata făcuți pentru Gemini CLI și Codex CLI, plus un client Python generic. Fiecare acțiune e atribuită: ce agent, ce model, ce provider.

### Dashboard web
Interfață vizuală cu 13 tab-uri: decizii, cunoștințe, obiective, task-uri, timeline, evenimente, branch-uri, health și altele. Dark theme.

## Mod de utilizare

### CLI
```bash
# Salvează o decizie
mem decide -t "SQLite nu PostgreSQL" -d "Simplitate și portabilitate"

# Învață ceva
mem learn "Python 3.10 nu creează event loop implicit" -t gotcha

# Setează un obiectiv
mem goal -t "Finalizare modul auth" -p high

# Adaugă un task
mem task -t "Teste unitare auth" -p high --goal 1

# Vezi contextul (gata de injectat în agent)
mem context --compact
```

### API
```bash
# Stochează o decizie via API
curl -X POST http://localhost:19876/api/v1/decisions \
  -H "Content-Type: application/json" \
  -d '{"title": "Folosim Redis", "category": "technical"}'

# Primește context
curl "http://localhost:19876/api/v1/context?mode=compact"
```

### Python client
```python
from universal_memory_client import UniversalMemoryClient

client = UniversalMemoryClient(
    base_url="http://localhost:19876",
    project_path="/my/project",
    cli_name="my-agent"
)

client.create_decision("Folosim Redis pentru cache", category="technical")
ctx = client.get_context(mode="compact")
```

## Arhitectură

```
┌─────────────────────────────────────────┐
│              AI Agents                  │
│  Claude │ Gemini │ Codex │ Custom       │
└────┬────┴───┬────┴───┬───┴──────┬───────┘
     │        │        │          │
     ▼        ▼        ▼          ▼
┌─────────────────────────────────────────┐
│         Universal Memory API            │
│    REST endpoints + MCP bridge          │
├─────────────────────────────────────────┤
│            Core Engine                  │
│  Context Builder │ Branch Manager       │
│  Checkpoints │ Intelligence Layer       │
├─────────────────────────────────────────┤
│         SQLite + WAL Mode               │
│    Structured tables + FTS5 search      │
└─────────────────────────────────────────┘
```

## Cerințe

- Python 3.10+
- SQLite 3.35+
- Flask (instalat via `pip install -r requirements.txt`)

## Pornire rapidă

```bash
# 1. Instalează dependențele
pip install -r requirements.txt

# 2. Pornește serverul (inițializează automat baza de date)
./scripts/run_server.sh

# 3. Deschide dashboard-ul
# http://localhost:19876

# 4. Sau folosește CLI-ul direct
python3 scripts/mem context --compact
```

## Status

**v2.0-rc1** — Release Candidate

- 14 faze de dezvoltare finalizate
- 200+ teste automate, toate trecute
- Documentație completă (13 documente + 5 specificații)
- Adapteri pentru Gemini CLI și Codex CLI
- MCP bridge funcțional (18 tool-uri)
- Dashboard web cu 13 tab-uri

## Roadmap

| Versiune | Funcționalitate |
|----------|----------------|
| v2.1 | Auto-cleanup și aging avansat |
| v2.2 | Coordonare multi-agent (voting, shared context) |
| v2.3 | Căutare semantică (vector embeddings) |
| v2.4 | Export/import memorie (JSON, YAML, migrare) |

## Documentație

Documentația completă se găsește în directorul [`docs/`](docs/):

- [Quick Start](docs/quickstart.md) — Instalare și primii pași
- [Demo](docs/demo.md) — Walkthrough end-to-end
- [Arhitectură](docs/architecture.md) — Design-ul sistemului
- [API Reference](docs/api.md) — Endpoint-uri REST
- [MCP Server](docs/mcp.md) — Integrare Model Context Protocol
- [Specificații](docs/spec-memory-schema.md) — Definiții entități, evenimente, adaptori

## Licență

Vezi [LICENSE](LICENSE).

---

Construit de **EAN** (Encean Alexandru Nicolae) — unelte de dezvoltare AI-native.
