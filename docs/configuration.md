# Configuration

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_DB_PATH` | Path to SQLite database file | `<project_root>/global.db` |
| `MEMORY_API_PORT` | Web server port | `19876` |

### Database Path

By default, the database is `global.db` in the project root. Override with:

```bash
export MEMORY_DB_PATH="/path/to/custom.db"
```

This is useful for:
- Running tests with isolated databases
- Multiple projects with separate memory
- Custom deployment locations

### API Port

```bash
export MEMORY_API_PORT=8080
python3 scripts/web_server.py
```

## Runtime State Files

These files are created in the project root and track current session state:

| File | Purpose | Content |
|------|---------|---------|
| `.current_session` | Active session ID | JSON: `{"session_id": "..."}` |
| `.current_model` | Active AI model | JSON: `{"model_id": "...", "provider": "..."}` |
| `.current_intent` | Current work intent | JSON: `{"intent": "debugging"}` |
| `.current_branch` | Current memory branch | JSON: `{"branch": "feature-x"}` |
| `.context_snapshot.json` | Cached context output | JSON snapshot |
| `.context_strategy.log` | Strategy decision log | Text log |

These files are gitignored and should not be committed.

## Intent System

Intents optimize context retrieval for specific work types.

### Valid Intents

| Intent | Boosts | Description |
|--------|--------|-------------|
| `debugging` | Error resolutions, error patterns | Troubleshooting sessions |
| `feature` | Decisions, goals, tasks | Building new features |
| `refactor` | Decisions, conventions | Code improvement |
| `deploy` | Tasks, conventions, errors | Deployment work |
| `docs` | Facts, decisions | Documentation writing |
| `review` | Decisions, conventions | Code review |
| `explore` | Facts, goals | Codebase exploration |

### Setting Intent

```bash
# CLI
python3 scripts/mem intent set debugging

# API
curl -X POST http://localhost:19876/api/intent/set \
  -H "Content-Type: application/json" \
  -d '{"intent": "debugging"}'
```

## Context Modes

| Mode | Purpose | Entity Limits |
|------|---------|---------------|
| `compact` | Daily use, default | 5/8/3/5/3 |
| `full` | Deep sessions | 20/30/10/20/10 |
| `survival` | Post-compaction | 3/5/2/3/2 |
| `delta` | Incremental | 3/3/2/3/2 (recent only) |

Limits are: decisions / facts / goals / tasks / resolutions.

## Database Schema

The database is auto-initialized by `scripts/init_db.py`. Migration files in `migrations/` document schema evolution:

| Migration | Content |
|-----------|---------|
| `007_v2_tables.sql` | Core entity tables |
| `008_v2c_error_intelligence.sql` | Error resolution + model attribution |
| `009_intelligence_layer.sql` | Error patterns |
| `010_checkpoints.sql` | Checkpoints + timeline |
| `011_agent_activity_log.sql` | Agent activity tracking |
| `012_memory_branches.sql` | Branch tables + branch column |

### Reinitializing

```bash
# Safe — only creates missing tables, never drops existing
python3 scripts/init_db.py
```

## Web Dashboard

Start with:

```bash
python3 scripts/web_server.py
```

The dashboard runs at `http://localhost:19876` and provides:

- Overview cards (entity counts, health)
- Decisions, Facts, Goals & Tasks tabs
- Timeline view
- Context preview
- Health metrics
- Agent activity log
- Branch management
- Search
- Checkpoint management

### Dashboard Tabs

| Tab | Endpoint | Content |
|-----|----------|---------|
| Dashboard | `/api/dashboard` | Aggregated overview |
| Decisions | `/api/decisions` | Decision list with filters |
| Facts | `/api/facts` | Facts with pin/unpin/promote |
| Goals & Tasks | `/api/goals`, `/api/tasks` | Goals with progress, tasks with status |
| Timeline | `/api/timeline` | Chronological events |
| Context | `/api/context` | Context preview by mode |
| Health | `/api/health` | Memory health metrics |
| Activity | `/api/activity` | Agent action log |
| Errors | `/api/errors` | Error solutions database |
| Branches | `/api/branches` | Branch management |
| Sessions | Legacy | Session browser |
| Search | Legacy | Memory search |
