# Orchestrare Multi-Agent — Documentație Completă

## Prezentare Generală

Sistemul de orchestrare multi-agent permite coordonarea a 4 CLI-uri AI (Claude Code, Gemini CLI, Codex CLI, Kimi CLI) printr-o arhitectură **peer-to-peer bazată pe DB**. Nu există orchestrator central — orice CLI poate crea proiecte, claim task-uri, participa la deliberări și face review.

### Arhitectură

```
  Claude Code    Gemini CLI    Codex CLI    Kimi CLI
       │              │             │            │
       │   claim / complete / propose / vote     │
       └──────────────┬─────────────┬────────────┘
                      │             │
                      ▼             ▼
               ┌──────────────────────────┐
               │       global.db          │
               │  (10 tabele orchestrare) │
               └──────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      REST API    MCP Tools    CLI (mem)
       (20 ep)     (6 tools)   (18 comenzi)
```

---

## Faze de Dezvoltare

| Fază | Nume | Ce adaugă | Teste |
|------|------|-----------|-------|
| **18D** | Orchestration Engine | Proiecte, task-uri cu lease, deliberare, messaging, agent presence | 25/25 |
| **18E** | Dashboard + Daemon | Tab web Orchestration, housekeeping automat | 15/15 |
| **18F** | CLI Launcher | Lansare programatică a CLI-urilor (subprocess) | 15/15 |
| **18G** | Auto-Loop | Deliberare automată multi-round, task pipeline | 10/10 |
| **18H** | Peer Review | Workflow formal: review → verdict → comments | 10/10 |
| **18I** | Auto-Pipeline | Re-run după review negativ, conflict escalation | 8/8 |
| **19** | Intelligence + Replay | Capabilities dinamice, weighted voting, timeline replay | 10/10 |
| **20** | Skill Learning | Extragere skills din reviews, sentiment analysis, learning persistent | 8/8 |
| **Total** | | | **101/101** |

---

## Schema Database (10 tabele)

### orchestration_projects
Proiecte orchestrate cu status și CLI orchestrator.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | ID proiect |
| title | TEXT | Titlu |
| description | TEXT | Descriere |
| orchestrator_cli | TEXT | CLI-ul care a creat proiectul |
| status | TEXT | active / paused / completed / failed |
| project_path | TEXT | Cale pe disk |
| created_at | TEXT | Timestamp |
| completed_at | TEXT | Timestamp completare |

### orch_tasks
Task-uri cu lease-based ownership și dependențe.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | ID task |
| project_id | INTEGER FK | Proiect părinte |
| title | TEXT | Titlu task |
| description | TEXT | Descriere |
| task_type | TEXT | implementation / review / research / fix |
| required_skills | TEXT JSON | Skills necesare: ["code", "architecture"] |
| priority | TEXT | critical / high / medium / low |
| status | TEXT | pending / assigned / in_progress / done / failed / blocked |
| assigned_cli | TEXT | CLI-ul care lucrează |
| lease_token | TEXT UUID | Token de ownership (expiră după 30 min) |
| lease_expires_at | TEXT | Când expiră lease-ul |
| depends_on | TEXT JSON | IDs de task-uri de care depinde |
| result_summary | TEXT | Rezumatul rezultatului (max 5000 chars) |

### orch_sessions
Sesiuni de deliberare cu runde structurate.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | ID sesiune |
| topic | TEXT | Subiectul deliberării |
| session_type | TEXT | quick (2 runde) / deep (4) / expert (6) |
| current_round | INTEGER | Runda curentă |
| total_rounds | INTEGER | Total runde |
| participating_clis | TEXT JSON | CLI-uri participante |
| consensus_level | TEXT | full / high / moderate / low / none |
| synthesis_result | TEXT JSON | Rezultat sinteză |

### orch_proposals
Propuneri per rundă per CLI.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| session_id | INTEGER FK | Sesiune |
| round_number | INTEGER | Număr rundă |
| round_phase | TEXT | proposal / analysis / critique / refinement / vote / synthesis |
| cli_name | TEXT | CLI-ul care propune |
| content | TEXT | Conținut propunere |
| confidence | REAL | 0.0 - 1.0 |

### orch_votes
Voturi cu weight (din capabilities).

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| session_id | INTEGER FK | Sesiune |
| cli_name | TEXT | Cine votează |
| voted_for | TEXT | Ce votează |
| reasoning | TEXT | Motivare |
| weight | REAL | Greutate vot (din capabilities) |

### orch_messages
Mesaje inter-agent (broadcast sau direct).

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| from_cli | TEXT | Expeditor |
| to_cli | TEXT | Destinatar (NULL = broadcast) |
| message_type | TEXT | info / question / answer / review / correction / handoff |
| content | TEXT | Conținut |
| in_reply_to | INTEGER FK | Reply la alt mesaj |

### orch_agents
Agent presence tracking.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| cli_name | TEXT PK | Identificator CLI |
| status | TEXT | online / busy / offline |
| last_seen | TEXT | Ultimul heartbeat |
| current_task_id | INTEGER | Task curent |

### orch_reviews
Peer review cu verdicte formale.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| task_id | INTEGER FK | Task reviewuit |
| reviewer_cli | TEXT | Cine face review |
| verdict | TEXT | approve / changes_requested / blocked / security_risk |
| comments | TEXT | Comentarii detaliate |
| severity | TEXT | info / warning / critical |
| original_cli | TEXT | Cine a făcut task-ul |

### orch_skill_observations
Observații de skill învățate din reviews.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| cli_name | TEXT | Agent observat |
| skill | TEXT | Skill (architecture, code, testing, security, etc.) |
| score | REAL | -1.0 (slab) la +1.0 (excelent) |
| source | TEXT | review / review_text / task / meta |
| evidence | TEXT | Text dovadă |

---

## API REST (20 endpoint-uri)

Base URL: `http://localhost:19876`

### Proiecte
```
POST   /api/v1/orch/projects              Creează proiect
GET    /api/v1/orch/projects              Listează proiecte (cu task counts)
GET    /api/v1/orch/projects/<id>         Status proiect + tasks + agents
```

### Task-uri
```
POST   /api/v1/orch/tasks                Creează task
GET    /api/v1/orch/tasks                Listează (?available=1&cli=X&mine=1)
POST   /api/v1/orch/tasks/<id>/claim     Claim cu lease (30 min)
POST   /api/v1/orch/tasks/<id>/complete  Complete (?failed=1 pentru fail)
```

### Deliberare
```
GET    /api/v1/orch/deliberation          Listează sesiuni
POST   /api/v1/orch/deliberation          Creează sesiune
GET    /api/v1/orch/deliberation/<id>     Status + context rundă
POST   /api/v1/orch/deliberation/<id>/respond  propose / vote / advance / synthesize
```

### Mesaje
```
POST   /api/v1/orch/messages              Trimite mesaj
GET    /api/v1/orch/messages              Citește (?to=X&unread=1)
```

### Agenți
```
GET    /api/v1/orch/agents                Status agenți (online/offline)
POST   /api/v1/orch/heartbeat            Heartbeat + sync
```

### Launcher
```
POST   /api/v1/orch/launch               Lansează CLI (task/session/prompt)
GET    /api/v1/orch/launches              Launch-uri active
```

### Reviews
```
GET    /api/v1/orch/reviews               Listează reviews (?task_id=X&verdict=Y)
POST   /api/v1/orch/reviews/request       Lansează review pe task
```

### Intelligence + Replay
```
GET    /api/v1/orch/replay/<project_id>   Timeline complet proiect
GET    /api/v1/orch/capabilities          Leaderboard capabilities
```

---

## CLI (mem orch)

### Proiecte & Task-uri
```bash
mem orch create "Titlu" [descriere]              # Creează proiect
mem orch status [project_id]                     # Status
mem orch add-task <proj> "titlu" "desc"           # Adaugă task
mem orch tasks [--mine|--available]               # Listează task-uri
mem orch claim <task_id>                         # Claim cu lease
mem orch done <task_id> [summary]                # Marchează done
```

### Deliberare
```bash
mem orch deliberate "topic" [--type deep]         # Pornește deliberare manuală
mem orch propose <session_id> "text"              # Propunere
mem orch vote <session_id> <option>               # Votează
mem orch deliberate-auto "întrebare" [--type deep] # Deliberare automată (toate CLI-urile)
```

### Comunicare
```bash
mem orch send <to|all> "mesaj"                   # Trimite mesaj inter-agent
mem orch messages [--unread]                     # Citește mesaje
mem orch agents                                  # Cine e online
```

### Launcher
```bash
mem orch launch <cli> --task <id>                # Lansează CLI pentru task
mem orch launch <cli> --deliberate <session_id>  # Lansează pentru deliberare
mem orch launch <cli> --prompt "text"            # Prompt custom
mem orch launches                                # Listează launch-uri active
```

### Review & Pipeline
```bash
mem orch review <task_id> --by <cli>             # Peer review pe un task
mem orch reviews [--task X] [--verdict approve]  # Listează reviews
mem orch run-project <id> [--review] [--auto-fix] # Pipeline complet cu review
```

### Intelligence
```bash
mem orch capabilities                            # Leaderboard CLI capabilities
mem orch skills [cli_name]                       # Skills învățate per CLI
mem orch replay <project_id>                     # Timeline proiect
mem orch replay-delib <session_id>               # Timeline deliberare
mem orch daemon [--once]                         # Housekeeping daemon
```

---

## MCP Tools (6)

| Tool | Descriere |
|------|-----------|
| `orch_project_create` | Creează proiect orchestrat |
| `orch_tasks` | Management task-uri (create/claim/complete/fail/list) |
| `orch_deliberation` | Deliberare (create/propose/vote/advance/synthesize) |
| `orch_messaging` | Trimite/citește mesaje inter-agent |
| `orch_agent_heartbeat` | Heartbeat + status sync |
| `orch_launch_cli` | Lansează CLI pentru task/deliberare/prompt |

---

## CLI Profiles

| CLI | Strengths | Command |
|-----|-----------|---------|
| **claude-code** | architecture, complex_code, review, debugging | `claude --print "prompt"` |
| **gemini-cli** | code, research, docs, testing | `gemini -p "prompt"` |
| **codex-cli** | code, fix, refactor | `codex exec "prompt"` |
| **kimi-cli** | reasoning, research, math, analysis | `kimi --print --prompt "prompt"` |

### Binary Discovery (portabil)
1. Environment variable: `ORCH_CLAUDE_CODE_PATH`, `ORCH_GEMINI_CLI_PATH`, etc.
2. `shutil.which()` — caută în PATH
3. Fallback paths: `~/.local/bin/`

### Permission Modes
| Mod | Descriere | Default |
|-----|-----------|---------|
| `safe` | Fără bypass. CLI-ul poate cere confirmare. | **Da** |
| `auto` | Minim necesar (Claude: `--permission-mode auto`) | Nu |
| `unsafe` | Bypass total (doar explicit cu `--unsafe`) | Nu |

---

## Tipuri de Sesiuni Deliberare

| Tip | Runde | Faze |
|-----|-------|------|
| **quick** | 2 | proposal → synthesis |
| **deep** | 4 | proposal → analysis → refinement → synthesis |
| **expert** | 6 | proposal → analysis → critique → refinement → vote → synthesis |

### Consensus Levels
| Nivel | Condiție |
|-------|---------|
| full | ≥90% agreement |
| high | ≥75% |
| moderate | ≥50% |
| low | ≥25% |
| none | <25% |

---

## Intelligence Layer

### Capability Scoring (5 surse)
1. **Static** — CLI_PROFILES.strengths (baseline 0.5)
2. **Task success** — Rate per task_type din orch_tasks
3. **Review approval** — Cât de des e approved output-ul
4. **Review accuracy** — Cât de des dă review corect
5. **Learned skills** — Din orch_skill_observations (keyword + sentiment)

### Skill Learning
Daemon-ul extrage automat observații din review comments:
- **10 categorii skill:** architecture, code, testing, security, performance, debugging, concurrency, documentation, refactoring, review
- **Sentiment analysis:** positive/negative din cuvinte cheie
- **Blend:** 60% capabilities existente + 40% skills învățate

### Weighted Voting
Votul unui agent contează mai mult dacă are capabilities relevante pe topic.
- Weight: 0.5 (min) — 2.0 (max)
- Calculat din capabilities match pe topic keywords

---

## Auto-Pipeline

### Flow complet
```
1. mem orch run-project <id> --auto-fix
2. Task #1 → route_task() → claude-code (best match)
3. launch_for_task() → subprocess → result
4. Auto-review: gemini-cli reviewuiește
   → approve → next task
   → changes_requested → re-launch cu feedback (max 2 retries)
   → blocked/security_risk → mini-deliberare automată
5. Task #2 → depends_on #1 rezolvat → lansare
6. Repetă până toate task-urile done/failed
```

---

## Daemon Housekeeping

Rulează periodic (default 60s) sau single-pass (cron):
```bash
python3 orch_daemon.py          # Loop continuu
python3 orch_daemon.py --once   # Single pass
```

### Ce face:
1. **Stale leases** — task-uri cu lease expirat → revert la pending
2. **Agent offline** — last_seen > 5 min → marchează offline
3. **Auto-advance** — sesiuni unde toți au răspuns → avansează runda
4. **Skill learning** — extrage observații din reviews noi
5. **Capabilities update** — recalculează scoruri în agent_reputation

---

## Replay System

### Timeline Proiect
```bash
mem orch replay <project_id>
```
Afișează cronologic: creare proiect, task-uri create/claimed/completate, reviews, deliberări, mesaje.

### Timeline Deliberare
```bash
mem orch replay-delib <session_id>
```
Afișează: start sesiune, propuneri per rundă per CLI, voturi, sinteză finală.

---

## Dashboard Web

Tab "Orchestration" cu 6 sub-view-uri:
1. **Projects** — carduri cu status, task counts, click pentru detalii
2. **Tasks** — grupate pe status (in_progress, pending, done, failed)
3. **Agents** — 4 carduri cu status indicator (verde/galben/gri)
4. **Deliberation** — sesiuni cu runde, expandabil pentru propuneri/voturi
5. **Messages** — format chat, from → to, message type badge
6. **Reviews** — verdict badges (approve/changes_requested/blocked)

---

## Statistici

| Metric | Valoare |
|--------|---------|
| Linii cod orchestrare (scripts/) | ~4,600 |
| Linii web frontend | ~2,500 |
| Tabele DB noi | 10 |
| API endpoints | 20 |
| CLI commands | 18 |
| MCP tools | 6 |
| Teste totale | 101/101 |
| Faze implementate | 8 (18D → 20) |
