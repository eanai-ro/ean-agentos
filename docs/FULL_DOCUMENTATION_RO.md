# EAN AgentOS — Documentație Completă

## Cuprins

1. [Prezentare Generală](#1-prezentare-generală)
2. [Instalare](#2-instalare)
3. [Memory Core (Free)](#3-memory-core-free)
4. [Solution Index — "Nu mai rezolva același bug" (Free)](#4-solution-index-free)
5. [Knowledge Extraction (Free)](#5-knowledge-extraction-free)
6. [Context Builder (Free)](#6-context-builder-free)
7. [Experience Graph (Free)](#7-experience-graph-free)
8. [Search & Cognitive Search (Free)](#8-search--cognitive-search-free)
9. [Branch-Aware Memory (Free)](#9-branch-aware-memory-free)
10. [Backup & Recovery (Free)](#10-backup--recovery-free)
11. [Web Dashboard (Free)](#11-web-dashboard-free)
12. [MCP Server (Free)](#12-mcp-server-free)
13. [CLI — `mem` (Free)](#13-cli--mem-free)
14. [Integrări CLI (Free)](#14-integrări-cli-free)
15. [Multi-Agent Orchestration (Pro)](#15-multi-agent-orchestration-pro)
16. [AI Deliberation (Pro)](#16-ai-deliberation-pro)
17. [CLI Launcher (Pro)](#17-cli-launcher-pro)
18. [Auto-Pipeline (Pro)](#18-auto-pipeline-pro)
19. [Intelligence Layer (Pro)](#19-intelligence-layer-pro)
20. [Replay System (Pro)](#20-replay-system-pro)
21. [Peer Review (Pro)](#21-peer-review-pro)
22. [License & Planuri](#22-license--planuri)
23. [API Reference](#23-api-reference)
24. [Troubleshooting](#24-troubleshooting)

---

## 1. Prezentare Generală

EAN AgentOS este un sistem de memorie permanentă și orchestrare pentru agenți AI de programare. Funcționează cu Claude Code, Gemini CLI, Codex CLI și Kimi CLI.

### Versiuni

| Versiune | Ce include | Preț |
|----------|-----------|------|
| **Community (Free)** | Memorie permanentă, solution index, knowledge extraction, experience graph, search, backup, dashboard, MCP | Gratuit (MIT) |
| **Team (Pro)** | + Orchestrare, deliberare, CLI launcher, peer review, replay | $29/lună/seat |
| **Enterprise (Pro)** | + Intelligence layer, skill learning, auto-pipeline, smart routing | $99/lună/seat |

---

## 2. Instalare

### Cerințe

- Python 3.10+
- SQLite 3.35+
- pip (pentru dependențe)
- Cel puțin un CLI AI: Claude Code, Gemini CLI, Codex CLI, sau Kimi CLI

### Instalare automată

```bash
git clone https://github.com/eanai-ro/ean-agentos.git
cd ean-agentos
./install.sh
```

Installer-ul:
1. Instalează dependențe Python
2. Inițializează baza de date (49 tabele)
3. Creează comanda `mem` în PATH
4. Detectează CLI-uri instalate și oferă selector interactiv
5. Configurează hooks și MCP server

### Instalare manuală

```bash
pip install flask flask-cors
python3 scripts/init_db.py
chmod +x scripts/mem
ln -s $(pwd)/scripts/mem ~/.local/bin/mem
python3 scripts/ean_memory.py install claude
```

### Docker

```bash
docker build -t ean-agentos .
docker run -it ean-agentos
```

---

## 3. Memory Core (Free)

### Ce stochează

| Entitate | Tabel | Descriere |
|----------|-------|-----------|
| **Decizii** | `decisions` | Decizii tehnice cu context și motivare |
| **Fapte** | `learned_facts` | Lucruri învățate despre proiect |
| **Obiective** | `goals` | Obiective pe termen lung |
| **Task-uri** | `tasks` | Task-uri de făcut |
| **Erori rezolvate** | `error_resolutions` | Erori + soluții structurate |
| **Sesiuni** | `sessions` | Sesiuni de lucru |
| **Mesaje** | `messages` | Mesaje utilizator + agent |

### Cum funcționează captura

Hooks-urile instalate pentru fiecare CLI capturează automat:
- Sesiuni de lucru (start/stop)
- Mesaje utilizator și răspunsuri agent
- Apeluri de tool (Bash, Edit, Read, Write)
- Erori detectate
- Rezoluții (soluții aplicate)

Totul se salvează în `global.db` (SQLite cu WAL mode).

### Comanda `mem`

```bash
mem status           # Status memorie
mem decisions        # Decizii active
mem facts            # Fapte învățate
mem goals            # Obiective
```

---

## 4. Solution Index — "Nu mai rezolva același bug" (Free)

### Cel mai important feature

```bash
mem suggest "CORS error"
```

Caută în 3 surse:
1. **error_resolutions** — erori rezolvate structurat (V2)
2. **errors_solutions** — erori rezolvate din hook-uri
3. **error_patterns** — pattern-uri recurente

### Scoring

Fiecare rezultat are:
- **Match quality** (0-100%) — cât de similar e cu query-ul
- **Confidence** (0-100%) — cât de sigură e soluția
- **Combined score** — 40% match + 60% confidence

### Exemplu

```
💡 SOLUTIONS FOR: ModuleNotFoundError
══════════════════════════════════════════════

  1. [92pts] ✅ error_resolutions#4
     Problem:  ModuleNotFoundError: No module named 'redis'
     Solution: pip install redis
     Match: 100% | Confidence: 92% | Agent: claude-code
```

---

## 5. Knowledge Extraction (Free)

### Ce face

Extrage automat cunoștințe din sesiunile AI:
- Decizii tehnice
- Fapte despre proiect
- Erori + soluții
- Pattern-uri recurente

### Cum funcționează

```python
# Extractor intern (rulat de daemon)
from knowledge_extractor import KnowledgeExtractor
extractor = KnowledgeExtractor()
results = extractor.extract_from_session(session_id)
```

### Features
- **Pattern compilation** — recunoaștere automată de tipuri de decizii
- **Filtre negative** — excludere spam, salutări, non-tehnic
- **Scoring transparent** — fiecare extracție are scor de încredere
- **Deduplicare** — nu salvează informații duplicate
- **Auto-clasificare** — categorii automate

---

## 6. Context Builder (Free)

### Ce face

Construiește context optimizat pentru LLM din memoria permanentă. La fiecare sesiune nouă, agentul primește cele mai relevante informații.

### Moduri

| Mod | Descriere | Când |
|-----|-----------|------|
| `compact` | Esențialul: decizii active + fapte cheie | Default |
| `full` | Tot: inclusiv históric, task-uri, erori | Sesiuni lungi |
| `survival` | Minim absolut (post-compact) | Context mic |

### Utilizare

```bash
# Agentul primește context automat via MCP
# Sau manual:
python3 scripts/context_builder_v2.py --mode compact
```

---

## 7. Experience Graph (Free)

### Ce face

Conectează probleme cu soluții într-un graf:

```
Problem → Investigation → Solution → Outcome
```

### Comenzi

```bash
mem graph stats          # Statistici graf
mem graph show           # Vizualizare
mem graph build          # Rebuild graf
```

### Tipuri de linkuri
- `error_caused_by` — eroare cauzată de altă eroare
- `resolved_by` — eroare rezolvată de soluție
- `similar_to` — probleme similare
- `depends_on` — dependențe

---

## 8. Search & Cognitive Search (Free)

### Căutare unificată

```bash
mem search "authentication"
```

Caută în: mesaje, comenzi bash, decizii, fapte, obiective, task-uri, rezoluții, erori.

### Cognitive Search

Căutare inteligentă cu scorare:

```bash
python3 scripts/cognitive_search.py "CORS"
```

---

## 9. Branch-Aware Memory (Free)

### Ce face

Memoria se ramifică odată cu git branch-urile. Deciziile luate pe `feature/auth` nu interferează cu `main`.

### Comenzi

```bash
mem branch list          # Listează ramuri
mem branch switch <name> # Schimbă ramură
mem branch compare A B   # Compară două ramuri
mem branch merge A B     # Unește ramuri
```

---

## 10. Backup & Recovery (Free)

### Backup

```bash
mem backup create        # Backup manual
```

Features:
- SQLite backup API (safe, consistent)
- Verificare integritate (PRAGMA integrity_check)
- Retenție configurabilă
- Manifest JSON cu metadata

### Restore

```bash
mem backup restore <file>
```

---

## 11. Web Dashboard (Free)

### Pornire

```bash
python3 scripts/web_server.py
# Deschide: http://localhost:19876
```

### Tab-uri

| Tab | Ce afișează |
|-----|-------------|
| Dashboard | Overview: decizii, fapte, task-uri, erori |
| Decisions | Decizii active cu status, context |
| Facts | Fapte învățate, pinned/unpinned |
| Goals & Tasks | Obiective + task-uri |
| Timeline | Evenimente cronologice |
| Context | Preview context builder |
| Health | Statistici memorie |
| Activity | Log activitate agent |
| Errors | Erori cu pattern-uri |
| Branches | Ramuri de memorie |
| Events | Stream de evenimente |

---

## 12. MCP Server (Free)

### Ce face

Permite integrare nativă cu Claude Code și alte CLI-uri MCP-compatibile.

### Tools disponibile (Free)

| Tool | Descriere |
|------|-----------|
| `memory_search` | Caută în memorie |
| `memory_get_context` | Obține context optimizat |
| `memory_store_decision` | Salvează decizie |
| `memory_store_fact` | Salvează fapt |

### Configurare

Se configurează automat la `install claude`. Manual:

```json
// ~/.claude/.mcp.json
{
  "mcpServers": {
    "universal-memory": {
      "command": "python3",
      "args": ["/path/to/ean-agentos/mcp_server/server.py"]
    }
  }
}
```

---

## 13. CLI — `mem` (Free)

### Comenzi disponibile

```bash
# Memorie
mem status                        # Status general
mem decisions                     # Decizii active
mem facts                         # Fapte
mem goals                         # Obiective
mem search "query"                # Căutare

# Soluții
mem suggest "error message"       # Caută soluții anterioare
mem graph stats                   # Experience graph

# Erori
mem err last                      # Ultimele erori
mem errorlearn                    # Error learning status

# Backup
mem backup create                 # Backup manual

# Branch
mem branch list                   # Listează ramuri
```

---

## 14. Integrări CLI (Free)

### Claude Code

```bash
python3 scripts/ean_memory.py install claude
```

Instalează:
- MCP Server (`universal-memory`)
- Hooks: SessionStart, PostToolUse, UserPromptSubmit

### Gemini CLI

```bash
python3 scripts/ean_memory.py install gemini
```

Instalează hooks în `~/.gemini/settings.json`.

### Codex CLI

```bash
python3 scripts/ean_memory.py install codex
```

Instalează hooks în `~/.codex/settings.json`.

### Kimi CLI

Configurare manuală MCP în `~/.config/kimi/kimi-cli.toml`.

---

## 15. Multi-Agent Orchestration (Pro) 🔒

### Ce face

Coordonează mai mulți agenți AI pe același proiect. Proiecte cu task-uri, lease-based ownership, routing inteligent.

### Comenzi Pro

```bash
mem orch create "Titlu proiect"
mem orch add-task 1 "Titlu" "Descriere"
mem orch tasks --available
mem orch claim 1
mem orch done 1 "Rezumat"
```

### Schema DB

- `orchestration_projects` — proiecte
- `orch_tasks` — task-uri cu lease
- `orch_agents` — agent presence
- `orch_messages` — mesaje inter-agent

### API Endpoints (20)

Toate sub `/api/v1/orch/` — proiecte, task-uri, deliberare, mesaje, agenți, launcher, reviews.

---

## 16. AI Deliberation (Pro) 🔒

### Ce face

Sesiuni structurate de deliberare multi-agent cu runde, voturi și sinteză automată.

### Tipuri sesiuni

| Tip | Runde | Faze |
|-----|-------|------|
| quick | 2 | proposal → synthesis |
| deep | 4 | proposal → analysis → refinement → synthesis |
| expert | 6 | proposal → analysis → critique → refinement → vote → synthesis |

### Sinteză

- **Consensus detection** — Jaccard similarity ≥ 0.25
- **Theme clustering** — 8 categorii (performance, security, scalability, etc.)
- **Agreement matrix** — pairwise similarity
- **Consensus levels** — full/high/moderate/low/none

---

## 17. CLI Launcher (Pro) 🔒

### Ce face

Lansează programatic CLI-uri AI cu un task sau sesiune de deliberare.

```bash
mem orch launch gemini-cli --task 5
mem orch launch claude-code --deliberate 2
```

### Permission modes

| Mod | Descriere |
|-----|-----------|
| safe | Fără bypass (default) |
| auto | Minimul necesar |
| unsafe | Doar explicit |

### Binary discovery portabil

1. Environment variable override
2. `shutil.which()` — caută în PATH
3. Fallback paths

---

## 18. Auto-Pipeline (Pro Enterprise) 🔒🔒

### Ce face

Pipeline automat cu review + auto-fix + conflict escalation.

```bash
mem orch run-project 1 --auto-fix
```

### Flow

```
Task → Execute → Review
                   ├→ approve → next task
                   ├→ changes_requested → re-launch cu feedback (max 2)
                   └→ blocked → mini-deliberare automată
```

---

## 19. Intelligence Layer (Pro Enterprise) 🔒🔒

### Agent Capabilities

Scoruri dinamice per agent per skill, bazate pe:
- Static strengths (CLI_PROFILES)
- Task success rate
- Review approval rate
- Learned skills (din review comments)

### Weighted Voting

Votul unui agent contează mai mult dacă are capabilities relevante.

### Skill Learning

Extragere automată de skill observations din review comments:
- 10 categorii skill
- Sentiment analysis (pozitiv/negativ)
- Blend: 60% static + 40% learned

---

## 20. Replay System (Pro) 🔒

### Ce face

Timeline complete pentru debugging și audit.

```bash
mem orch replay 1           # Timeline proiect
mem orch replay-delib 2     # Timeline deliberare
```

---

## 21. Peer Review (Pro) 🔒

### Workflow

```
Task done → Review request → CLI reviewer execută
         → Verdict: approve | changes_requested | blocked | security_risk
         → Comments salvate în DB
```

### Verdicte

| Verdict | Descriere |
|---------|-----------|
| approve | Cod acceptat |
| changes_requested | Necesită modificări |
| blocked | Blocat — probleme majore |
| security_risk | Risc de securitate |

---

## 22. License & Planuri

### Community (Free)

Gratuit, MIT license. Include tot ce e documentat în secțiunile 3-14.

### Pro

Licența se activează prin:
```
~/.ean-memory/license.key
```

Format: JSON sau JWT.

```json
{
  "email": "user@company.com",
  "plan": "team",
  "expires_at": "2027-01-01T00:00:00"
}
```

**Detalii**: [ean@eanai.ro](mailto:ean@eanai.ro)

---

## 23. API Reference

### Free Endpoints

```
GET  /api/dashboard              Dashboard agregat
GET  /api/decisions              Decizii
GET  /api/facts                  Fapte
GET  /api/goals                  Obiective
GET  /api/tasks                  Task-uri
GET  /api/health                 Health counters
GET  /api/timeline               Evenimente
GET  /api/context                Context builder
GET  /api/activity               Agent activity
GET  /api/errors                 Error intelligence
GET  /api/events                 Event stream
GET  /api/branches               Memory branches
```

### Pro Endpoints 🔒

```
POST/GET  /api/v1/orch/projects
POST/GET  /api/v1/orch/tasks
POST/GET  /api/v1/orch/deliberation
POST/GET  /api/v1/orch/messages
GET       /api/v1/orch/agents
POST      /api/v1/orch/heartbeat
POST      /api/v1/orch/launch
GET       /api/v1/orch/launches
GET       /api/v1/orch/reviews
POST      /api/v1/orch/reviews/request
GET       /api/v1/orch/replay/<id>
GET       /api/v1/orch/capabilities
```

---

## 24. Troubleshooting

### DB nu există

```bash
python3 scripts/init_db.py
```

### mem command not found

```bash
export PATH=$HOME/.local/bin:$PATH
```

### Hooks nu funcționează

```bash
python3 scripts/ean_memory.py test
python3 scripts/ean_memory.py doctor
```

### MCP nu se conectează

Verifică `~/.claude/.mcp.json` — trebuie să aibă `universal-memory` configurat.

### Web dashboard nu pornește

```bash
pip install flask flask-cors
python3 scripts/web_server.py --host 127.0.0.1 --port 19876
```
