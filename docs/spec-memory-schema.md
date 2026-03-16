# Memory Schema Specification v1.0

This document defines the official schema for all memory entities in Universal Agent Memory.

---

## 1. Decision

**Purpose:** Records architectural, technical, or process decisions made during agent sessions.

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| title | TEXT | yes | — | Short decision summary |
| description | TEXT | yes | — | Full decision description |
| category | TEXT | no | `"technical"` | One of: `technical`, `architectural`, `tooling`, `convention`, `process` |
| status | TEXT | no | `"active"` | One of: `active`, `superseded`, `reconsidered`, `archived` |
| confidence | TEXT | no | `"high"` | One of: `confirmed`, `high`, `medium`, `low` |
| rationale | TEXT | no | null | Why this decision was made |
| alternatives_considered | TEXT | no | null | JSON array of alternatives |
| superseded_by | INTEGER | no | null | FK to decisions.id |
| stale_after_days | INTEGER | no | 90 | Auto-aging threshold |
| project_path | TEXT | no | null | Project scope |
| source_session | TEXT | no | null | Session that created it |
| created_by | TEXT | no | `"user"` | Creator identifier |
| model_used | TEXT | no | null | AI model that produced it |
| provider | TEXT | no | null | Model provider |
| branch | TEXT | no | `"main"` | Memory branch |
| created_at | TIMESTAMP | auto | now | Creation time |
| updated_at | TIMESTAMP | auto | now | Last modification |

**Relationships:**
- `superseded_by` → self-referential (points to newer decision)
- Scoped by `project_path` and `branch`

**Example JSON (API POST /api/v1/decisions):**
```json
{
  "title": "Use PostgreSQL for production",
  "description": "Chose PostgreSQL over MySQL for JSONB support and better concurrency",
  "category": "architectural",
  "confidence": "high",
  "rationale": "Need JSONB columns for flexible metadata storage",
  "cli_name": "claude-code",
  "agent_name": "claude-opus",
  "model_name": "claude-opus-4",
  "provider": "anthropic",
  "project_path": "/home/user/myproject"
}
```

---

## 2. Learned Fact

**Purpose:** Stores knowledge discovered during sessions — technical facts, preferences, conventions, gotchas.

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| fact | TEXT | yes | — | The fact content |
| fact_type | TEXT | no | `"technical"` | One of: `technical`, `preference`, `convention`, `environment`, `gotcha` |
| category | TEXT | no | null | Free-form category |
| confidence | TEXT | no | `"high"` | One of: `confirmed`, `high`, `medium`, `low` |
| is_pinned | INTEGER | no | 0 | Pinned facts survive context trimming |
| is_active | INTEGER | no | 1 | Soft-delete flag |
| source | TEXT | no | null | Where the fact came from |
| superseded_by | INTEGER | no | null | FK to learned_facts.id |
| project_path | TEXT | no | null | Project scope |
| source_session | TEXT | no | null | Session that created it |
| created_by | TEXT | no | `"user"` | Creator identifier |
| model_used | TEXT | no | null | AI model |
| provider | TEXT | no | null | Model provider |
| branch | TEXT | no | `"main"` | Memory branch |
| created_at | TIMESTAMP | auto | now | Creation time |
| updated_at | TIMESTAMP | auto | now | Last modification |

**Relationships:**
- `superseded_by` → self-referential
- Pinning (`is_pinned=1`) ensures fact appears in all context modes

**Example JSON:**
```json
{
  "fact": "This project uses Tailwind CSS v3 with JIT mode enabled",
  "fact_type": "technical",
  "category": "frontend",
  "confidence": "confirmed",
  "is_pinned": true,
  "source": "package.json analysis"
}
```

---

## 3. Goal

**Purpose:** Tracks high-level objectives that may span multiple sessions.

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| title | TEXT | yes | — | Goal title |
| description | TEXT | no | null | Detailed description |
| priority | TEXT | no | `"medium"` | One of: `critical`, `high`, `medium`, `low` |
| status | TEXT | no | `"active"` | One of: `active`, `completed`, `paused`, `abandoned` |
| target_date | TEXT | no | null | YYYY-MM-DD format |
| completed_at | TIMESTAMP | no | null | When completed |
| project_path | TEXT | no | null | Project scope |
| source_session | TEXT | no | null | Session that created it |
| created_by | TEXT | no | `"user"` | Creator identifier |
| branch | TEXT | no | `"main"` | Memory branch |
| created_at | TIMESTAMP | auto | now | Creation time |
| updated_at | TIMESTAMP | auto | now | Last modification |

**Relationships:**
- Has many `tasks` (via tasks.goal_id)

**Example JSON:**
```json
{
  "title": "Migrate authentication to OAuth2",
  "description": "Replace custom JWT auth with OAuth2 + PKCE flow",
  "priority": "high",
  "target_date": "2026-04-01"
}
```

---

## 4. Task

**Purpose:** Concrete work items, optionally linked to a goal.

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| goal_id | INTEGER | no | null | FK to goals.id |
| title | TEXT | yes | — | Task title |
| description | TEXT | no | null | Detailed description |
| priority | TEXT | no | `"medium"` | One of: `critical`, `high`, `medium`, `low` |
| status | TEXT | no | `"todo"` | One of: `todo`, `in_progress`, `done`, `blocked`, `cancelled` |
| blocked_by | TEXT | no | null | Description of blocker |
| resolved_at | TIMESTAMP | no | null | When resolved |
| assigned_session | TEXT | no | null | Session assigned to |
| project_path | TEXT | no | null | Project scope |
| source_session | TEXT | no | null | Session that created it |
| created_by | TEXT | no | `"user"` | Creator identifier |
| branch | TEXT | no | `"main"` | Memory branch |
| created_at | TIMESTAMP | auto | now | Creation time |
| updated_at | TIMESTAMP | auto | now | Last modification |

**Relationships:**
- Belongs to `goal` (optional, via goal_id)

**Status transitions:**
```
todo → in_progress → done
todo → blocked → in_progress → done
todo → cancelled
in_progress → blocked → in_progress
```

**Example JSON:**
```json
{
  "title": "Add rate limiting middleware",
  "description": "Implement express-rate-limit with Redis store",
  "priority": "high",
  "status": "todo",
  "goal_id": 3
}
```

---

## 5. Error Resolution

**Purpose:** Records how errors were diagnosed and resolved, enabling reuse across sessions.

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| error_id | INTEGER | no | null | FK to legacy errors_solutions table |
| error_fingerprint | TEXT | no | null | Normalized error signature |
| error_summary | TEXT | no | null | Human-readable error description |
| resolution | TEXT | yes | — | How the error was resolved |
| resolution_code | TEXT | no | null | Code snippet of the fix |
| resolution_type | TEXT | no | `"fix"` | One of: `fix`, `workaround`, `config_change`, `dependency`, `rollback` |
| model_used | TEXT | no | null | AI model that resolved it |
| provider | TEXT | no | null | Model provider |
| agent_name | TEXT | no | null | Agent that resolved it |
| project_path | TEXT | no | null | Project scope |
| source_session | TEXT | no | null | Session |
| created_by | TEXT | no | `"user"` | Creator |
| worked | INTEGER | no | 1 | 1=confirmed working, 0=failed, null=unknown |
| reuse_count | INTEGER | no | 0 | Times this resolution was reused |
| branch | TEXT | no | `"main"` | Memory branch |
| created_at | TEXT | auto | now | Creation time |
| updated_at | TEXT | auto | now | Last modification |

**Example JSON:**
```json
{
  "error_summary": "ModuleNotFoundError: No module named 'xyz'",
  "resolution": "Install missing dependency with pip install xyz",
  "resolution_type": "dependency",
  "resolution_code": "pip install xyz",
  "worked": true
}
```

---

## 6. Memory Checkpoint

**Purpose:** Snapshot of memory state at a point in time, enabling restore/rollback.

**Fields (memory_checkpoints):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| project_path | TEXT | yes | — | Project scope |
| name | TEXT | yes | — | Checkpoint name |
| description | TEXT | no | null | Description |
| created_at | TEXT | auto | now | Creation time |
| model | TEXT | no | null | Current model at time of checkpoint |
| intent | TEXT | no | null | Current intent |
| context_mode | TEXT | no | null | Current context mode |
| decisions_count | INTEGER | no | 0 | Count at checkpoint time |
| facts_count | INTEGER | no | 0 | Count at checkpoint time |
| goals_count | INTEGER | no | 0 | Count at checkpoint time |
| tasks_count | INTEGER | no | 0 | Count at checkpoint time |
| patterns_count | INTEGER | no | 0 | Count at checkpoint time |
| restored_count | INTEGER | no | 0 | Number of times restored |

**Fields (checkpoint_data):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| checkpoint_id | INTEGER | yes | — | FK to memory_checkpoints.id |
| entity_type | TEXT | yes | — | One of: `decision`, `fact`, `goal`, `task`, `pattern` |
| entity_id | INTEGER | yes | — | Original entity ID |
| snapshot_json | TEXT | yes | — | Full entity state as JSON |

---

## 7. Memory Branch

**Purpose:** Git-like branching for memory isolation and experimentation.

**Fields (memory_branches):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| name | TEXT | yes | — | Branch name (unique per project) |
| project_path | TEXT | yes | — | Project scope |
| parent_branch | TEXT | no | `"main"` | Branch this was created from |
| description | TEXT | no | null | Branch description |
| created_at | TEXT | auto | now | Creation time |
| created_by | TEXT | no | `"user"` | Creator |
| is_active | INTEGER | no | 1 | Soft-delete flag |

**UNIQUE constraint:** `(name, project_path)`

**Note:** The `main` branch is implicit — it has no row in `memory_branches`. All entities with `branch=NULL` or `branch='main'` belong to main.

---

## 8. Agent Activity Log

**Purpose:** Semantic audit trail of agent actions across sessions.

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| id | INTEGER | auto | autoincrement | Primary key |
| session_id | TEXT | no | null | Session identifier |
| project_path | TEXT | no | null | Project scope |
| agent_name | TEXT | no | null | Agent identifier |
| model_id | TEXT | no | null | Model used |
| provider | TEXT | no | null | Model provider |
| action_type | TEXT | yes | — | One of: `session_start`, `decision`, `fix`, `code_gen`, `review`, `query`, `learn`, `resolve`, `checkpoint`, `goal`, `task`, `profile` |
| action_summary | TEXT | yes | — | What was done |
| entity_type | TEXT | no | null | Affected entity type |
| entity_id | INTEGER | no | null | Affected entity ID |
| success | INTEGER | no | 1 | 1=success, 0=failure |
| error_message | TEXT | no | null | Error details if failed |
| duration_ms | INTEGER | no | null | Operation duration |
| tokens_used | INTEGER | no | null | Token consumption |
| metadata_json | TEXT | no | null | Additional structured data |
| created_at | TIMESTAMP | auto | now | Creation time |

---

## 9. Agent Event

**Purpose:** Fine-grained execution/observability stream for agent operations.

See [spec-events.md](spec-events.md) for full event specification.

---

## Common Metadata Fields

All write operations accept these optional metadata fields:

| Field | Description |
|-------|-------------|
| cli_name | CLI tool identifier (e.g., `"claude-code"`, `"gemini-cli"`) |
| agent_name | Agent identifier (e.g., `"claude-opus"`, `"glm-5"`) |
| provider | Model provider (e.g., `"anthropic"`, `"google"`, `"openai"`) |
| model_name | Model identifier (e.g., `"claude-opus-4"`, `"gemini-2.5-pro"`) |
| session_id | Session identifier |
| project_path | Project scope path |
| branch | Target memory branch (default: current branch or `"main"`) |

---

## Entity Lifecycle

```
Created → Active → [Superseded | Archived | Completed | Abandoned]
                     ↓
              (can be restored from checkpoint)
```

All entities support:
- **Branch scoping** — entities belong to a specific branch
- **Project scoping** — entities belong to a specific project path
- **Model attribution** — track which AI model created the entity
- **Session tracking** — track which session created the entity
