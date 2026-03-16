# Architecture

## Overview

Universal Agent Memory is a structured, persistent memory system for AI coding agents. It stores knowledge as typed entities (decisions, facts, goals, tasks, error resolutions) in a SQLite database and exposes them through CLI, REST API, and web dashboard.

## System Layers

```
┌─────────────────────────────────────────┐
│           Presentation Layer            │
│  Web Dashboard │ CLI │ Agent Adapters   │
├─────────────────────────────────────────┤
│              API Layer                  │
│  Universal API    │  Dashboard API      │
│  /api/v1/*        │  /api/*             │
├─────────────────────────────────────────┤
│           Business Logic                │
│  Context Builder │ Branch Manager       │
│  Decision Analyzer │ Error Patterns     │
│  Checkpoint Manager │ Timeline          │
│  Fact Promoter │ Context Strategy       │
├─────────────────────────────────────────┤
│            Data Layer                   │
│  v2_common.py (DB connection, utils)    │
│  SQLite + WAL mode + FTS5              │
└─────────────────────────────────────────┘
```

## Data Model

### Entity Tables

| Table | Key Columns | Branch-Aware |
|-------|-------------|:---:|
| `decisions` | title, description, category, status, confidence, rationale | Yes |
| `learned_facts` | fact, fact_type, category, is_pinned, is_active, confidence | Yes |
| `goals` | title, description, priority, status, target_date | Yes |
| `tasks` | title, priority, status, goal_id, blocked_by | Yes |
| `error_resolutions` | error_summary, resolution, worked, resolution_type | Yes |

All entity tables include:
- `project_path` — multi-project isolation
- `branch TEXT DEFAULT 'main'` — memory branching
- `created_at`, `updated_at` — timestamps
- `model_used`, `provider` — model attribution

### System Tables

| Table | Purpose |
|-------|---------|
| `memory_branches` | Branch registry (name, parent, description) |
| `branch_merge_log` | Merge history |
| `memory_checkpoints` | Checkpoint metadata |
| `checkpoint_data` | Checkpoint entity snapshots |
| `timeline_events` | System events (checkpoints, restores) |
| `agent_activity_log` | Agent action tracking |
| `error_patterns` | Aggregated error signatures |
| `project_profiles` | Per-project metadata |
| `model_usage_log` | Model usage statistics |

### FTS5 Tables

Full-text search indexes on `messages`, `bash_history`, and `tool_calls` for fast historical search.

## Context Builder

The context builder (`context_builder_v2.py`) assembles relevant memory into a prompt-injectable format.

### How It Works

1. **Reads current state**: project path, branch, intent, model
2. **Fetches entities**: decisions, facts, goals, tasks, resolutions
3. **Applies limits**: based on mode (compact/full/survival/delta) and intent
4. **Formats output**: text (for injection) or JSON (for API)

### Context Modes

| Mode | Decisions | Facts | Goals | Tasks | Resolutions |
|------|:---------:|:-----:|:-----:|:-----:|:-----------:|
| compact | 5 | 8 | 3 | 5 | 3 |
| full | 20 | 30 | 10 | 20 | 10 |
| survival | 3 | 5 | 2 | 3 | 2 |
| delta | 3 | 3 | 2 | 3 | 2 |

### Intent Boosting

When an intent is set (e.g., `debugging`), entity categories matching that intent get priority. For example, `debugging` intent prioritizes error resolutions and error-related decisions.

## Branching Model

Memory branches work like git branches but for structured knowledge:

```
main ─────────────────────────────────────►
  │
  ├── feature-auth ──── decisions, facts ──►
  │        │
  │        └── merge back to main
  │
  └── experiment-redis ── decisions ──►
```

### Branch Operations

| Operation | Description |
|-----------|-------------|
| `create` | New branch from current (or specified parent) |
| `switch` | Change current branch (writes `.current_branch` file) |
| `list` | Show all branches with entity counts |
| `compare` | Structured diff per category |
| `diff` | Compact diff summary |
| `replay` | Chronological activity on a branch |
| `merge` | Move all entities from source to target branch |
| `conflicts` | Detect same-title entities on both branches |
| `delete` | Soft-delete (deactivate) a branch |

### Branch Isolation

Entity queries filter by branch:
```sql
WHERE (branch = ? OR (branch IS NULL AND ? = 'main'))
```

This ensures `main` always includes entities with `NULL` branch (backward compatibility).

## API Architecture

### Universal API (`/api/v1/*`)

Designed for agent-to-memory communication:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/decisions` | Store a decision |
| POST | `/api/v1/facts` | Store a fact |
| POST | `/api/v1/goals` | Store a goal |
| POST | `/api/v1/tasks` | Store a task |
| POST | `/api/v1/resolve` | Store an error resolution |
| GET | `/api/v1/context` | Get assembled context |
| POST | `/api/v1/events` | Log a universal event |

All POST endpoints accept agent metadata: `cli_name`, `agent_name`, `provider`, `model_name`, `session_id`, `project_path`, `branch`.

### Dashboard API (`/api/*`)

Designed for UI consumption:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Aggregated dashboard data |
| GET | `/api/branches` | List branches with counts |
| GET | `/api/branches/compare` | Compare two branches |
| GET | `/api/branches/replay` | Branch activity replay |
| POST | `/api/branches/switch` | Switch current branch |
| POST | `/api/branches/merge` | Merge branches (2-step) |
| POST | `/api/checkpoints/create` | Create checkpoint |
| POST | `/api/checkpoints/restore` | Restore checkpoint |
| GET | `/api/health` | Memory health metrics |

## File Organization

```
scripts/
├── mem                     # CLI entry point (routes commands)
├── v2_common.py            # Shared: DB, paths, formatting, constants
├── init_db.py              # Schema creation and migration
├── context_builder_v2.py   # Context assembly engine
├── context_strategy.py     # Auto mode selection
├── branch_manager.py       # Branch operations
├── checkpoint_manager.py   # Checkpoint save/restore
├── dashboard_api.py        # Flask blueprint: dashboard endpoints
├── universal_api.py        # Flask blueprint: agent API endpoints
├── web_server.py           # Flask app bootstrap
├── timeline.py             # Event timeline
├── decision_tracker.py     # Decision CRUD
├── decision_analyzer.py    # Conflict detection
├── learned_facts.py        # Facts CRUD
├── fact_promoter.py        # Promotion logic
├── goal_tracker.py         # Goals CRUD
├── error_resolution.py     # Resolution CRUD
├── error_patterns.py       # Pattern aggregation
├── activity_log.py         # Activity tracking
├── adapters/               # Agent CLI adapters
│   ├── gemini_cli_adapter.py
│   └── codex_cli_adapter.py
└── clients/                # Client libraries
    └── universal_memory_client.py
```

## Database Configuration

- **Engine**: SQLite 3.35+
- **Journal mode**: WAL (Write-Ahead Logging) for concurrent reads
- **Row factory**: `sqlite3.Row` for dict-like access
- **Path resolution**: `MEMORY_DB_PATH` env var or `./global.db`
- **FTS5**: Full-text search on historical data tables
