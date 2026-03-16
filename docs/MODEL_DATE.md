# MODEL DE DATE — EAN AgentOS

**Ultima actualizare:** 2026-03-15

---

## Baza de Date

- **Engine:** SQLite 3.35+
- **Mode:** WAL (Write-Ahead Logging)
- **FTS:** FTS5 pentru full-text search
- **Fișier:** `<project_root>/global.db`

---

## Tabele Principale

### `sessions`
Sesiunile CLI-urilor AI.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| session_id | TEXT UNIQUE | UUID sesiune |
| started_at | TIMESTAMP | Start sesiune |
| ended_at | TIMESTAMP | End sesiune |
| cli_name | TEXT | claude-code, gemini-cli, codex-cli, kimi-cli |
| agent_name | TEXT | Nume agent (opțional) |
| provider | TEXT | anthropic, google, openai, moonshot |
| model_name | TEXT | claude-opus-4, gemini-2.0-flash, etc. |
| project_path | TEXT | Calea proiectului |

### `messages`
Mesajele din conversații.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| session_id | TEXT FK | Legătură la sesiune |
| timestamp | TIMESTAMP | Momentul mesajului |
| role | TEXT | user, assistant, system |
| content | TEXT | Conținutul mesajului |
| message_type | TEXT | Tip mesaj |
| project_path | TEXT | Calea proiectului |
| tool_name | TEXT | Numele tool-ului (pentru tool calls) |
| tool_input | TEXT | Input-ul tool-ului (JSON) |
| tool_response | TEXT | Răspunsul tool-ului |

### `decisions`
Decizii arhitecturale / tehnice.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Titlul deciziei |
| description | TEXT | Descriere detaliată |
| rationale | TEXT | Motivația |
| category | TEXT | technical, architectural, process, etc. |
| status | TEXT | active, superseded, deprecated |
| confidence | TEXT | high, medium, low |
| created_at | TIMESTAMP | Data creării |
| updated_at | TIMESTAMP | Data ultimei modificări |
| model_used | TEXT | Modelul AI care a creat decizia |
| superseded_by | INTEGER FK | Decizie care o înlocuiește |
| project_path | TEXT | Calea proiectului |
| branch_name | TEXT | Branch-ul memoriei |
| is_global | INTEGER | 1 = promovat cross-agent |
| promoted_from_agent | TEXT | Agentul care a promovat |

### `learned_facts`
Cunoștințe acumulate.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| fact | TEXT | Conținutul cunoștinței |
| fact_type | TEXT | technical, convention, architecture, etc. |
| source | TEXT | Sursa informației |
| is_pinned | INTEGER | 1 = important, persistent |
| confidence | REAL | Nivel de încredere (0-1) |
| created_at | TIMESTAMP | Data creării |
| project_path | TEXT | Calea proiectului |
| branch_name | TEXT | Branch-ul memoriei |
| is_global | INTEGER | 1 = promovat cross-agent |

### `goals`
Obiective de proiect.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Titlul obiectivului |
| description | TEXT | Descriere |
| priority | TEXT | critical, high, medium, low |
| status | TEXT | active, completed, abandoned |
| target_date | TEXT | Data țintă |
| created_at | TIMESTAMP | Data creării |
| project_path | TEXT | Calea proiectului |

### `tasks`
Task-uri concrete.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Titlul task-ului |
| description | TEXT | Descriere |
| priority | TEXT | critical, high, medium, low |
| status | TEXT | todo, in_progress, done, blocked |
| goal_id | INTEGER FK | Legătură la goal |
| created_at | TIMESTAMP | Data creării |
| project_path | TEXT | Calea proiectului |

### `error_resolutions`
Erori și soluțiile lor.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| error_summary | TEXT | Rezumatul erorii |
| error_type | TEXT | Tipul erorii |
| resolution | TEXT | Cum s-a rezolvat |
| worked | INTEGER | 1 = soluția a funcționat |
| reuse_count | INTEGER | De câte ori a fost reutilizată |
| created_at | TIMESTAMP | Data creării |
| project_path | TEXT | Calea proiectului |
| is_global | INTEGER | 1 = promovat cross-agent |

### `agent_events`
Stream de evenimente agent.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| event_type | TEXT | 18 tipuri (agent_started, decision_made, etc.) |
| title | TEXT | Descriere scurtă |
| description | TEXT | Detalii |
| agent_name | TEXT | Agentul care a generat |
| session_id | TEXT FK | Sesiunea |
| project_path | TEXT | Proiectul |
| branch_name | TEXT | Branch-ul |
| related_table | TEXT | Tabela legată |
| related_id | INTEGER | ID-ul entității legate |
| parent_event_id | INTEGER FK | Event părinte |
| created_at | TIMESTAMP | Data creării |

### `memory_branches`
Branch-uri de memorie.

| Coloană | Tip | Descriere |
|---------|-----|-----------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Numele branch-ului |
| project_path | TEXT | Proiectul |
| parent_branch | TEXT | Branch-ul părinte |
| description | TEXT | Descriere |
| is_active | INTEGER | 1 = activ |
| created_at | TIMESTAMP | Data creării |
| created_by | TEXT | Cine a creat (user, api, merge) |

---

## Tabele FTS5

| Tabelă FTS | Sursa | Coloane indexate |
|------------|-------|-----------------|
| `messages_fts` | messages | content |
| `decisions_fts` | decisions | title, description |
| `facts_fts` | learned_facts | fact |

---

## Relații

```
sessions 1→N messages
goals 1→N tasks
decisions 1→1 decisions (superseded_by)
agent_events N→1 sessions
agent_events N→1 agent_events (parent_event_id)
```

---

## Migrări

| Fișier | Descriere |
|--------|-----------|
| 006_observability_tables.sql | Agent activity, model logging |
| 007_v2_tables.sql | V2 core tables |
| 008_v2c_error_intelligence.sql | Error patterns |
| 009_intelligence_layer.sql | Cognitive layer |
| 010_checkpoints.sql | Save/restore points |
| 011_agent_activity_log.sql | Activity tracking |
| 012_memory_branches.sql | Branch support |
| 013_agent_event_stream.sql | Event stream |
| 014_cross_agent_learning.sql | Cross-agent columns |
| 015_memory_intelligence.sql | Intelligence layer |
