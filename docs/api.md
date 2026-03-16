# API Reference

Universal Agent Memory exposes two API layers: the **Universal API** for agent communication and the **Dashboard API** for UI and management.

Default server: `http://localhost:19876`

## Universal API (`/api/v1/*`)

### Agent Metadata

All POST endpoints accept these optional fields for attribution:

```json
{
  "cli_name": "gemini-cli",
  "agent_name": "researcher",
  "provider": "google",
  "model_name": "gemini-2.0-flash",
  "session_id": "sess_abc123",
  "project_path": "/path/to/project",
  "branch": "feature-x"
}
```

### POST /api/v1/decisions

Store a technical or architectural decision.

```json
{
  "title": "Use PostgreSQL",
  "description": "Better for concurrent writes",
  "category": "technical",
  "confidence": "high",
  "rationale": "Benchmarks show 3x throughput vs SQLite",
  "project_path": "/my/project"
}
```

**Response:**
```json
{
  "ok": true,
  "id": 42,
  "message": "Decision recorded: Use PostgreSQL"
}
```

**Categories:** `technical`, `architectural`, `convention`, `process`, `security`, `performance`

**Confidence levels:** `confirmed`, `high`, `medium`, `low`, `speculative`

### POST /api/v1/facts

Store a learned fact.

```json
{
  "fact": "API rate limit is 100 req/min",
  "fact_type": "convention",
  "category": "api",
  "confidence": "confirmed",
  "source": "API docs v2.1",
  "project_path": "/my/project"
}
```

**Response:**
```json
{
  "ok": true,
  "id": 15,
  "message": "Fact learned: API rate limit is 100 req/min"
}
```

**Fact types:** `technical`, `convention`, `preference`, `constraint`, `observation`

### POST /api/v1/goals

Store a goal.

```json
{
  "title": "Complete authentication module",
  "description": "JWT-based auth with refresh tokens",
  "priority": "high",
  "target_date": "2026-04-01",
  "project_path": "/my/project"
}
```

**Priority:** `critical`, `high`, `medium`, `low`

### POST /api/v1/tasks

Store a task, optionally linked to a goal.

```json
{
  "title": "Write JWT token generator",
  "description": "RS256 signing with 1h expiry",
  "priority": "high",
  "goal_id": 1,
  "project_path": "/my/project"
}
```

### POST /api/v1/resolve

Store an error resolution.

```json
{
  "error_summary": "ImportError: no module named 'cryptography'",
  "resolution": "pip install cryptography",
  "worked": true,
  "resolution_type": "dependency",
  "error_type": "ImportError",
  "project_path": "/my/project"
}
```

### GET /api/v1/context

Retrieve assembled memory context.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `project` | string | current | Project path |
| `mode` | string | `compact` | Mode: compact, full, survival, delta |
| `branch` | string | current | Branch name |
| `budget` | int | — | Token budget limit |

**Response:**
```json
{
  "ok": true,
  "context_text": "## Memory Context\n...",
  "meta": {
    "mode": "compact",
    "model": "claude-opus-4",
    "intent": "feature",
    "branch": "main"
  },
  "counts": {
    "decisions": 5,
    "facts": 8,
    "goals": 3,
    "tasks": 5,
    "resolutions": 3
  }
}
```

### POST /api/v1/events

Log a universal event.

```json
{
  "event_type": "session_start",
  "event_data": {"intent": "debugging"},
  "project_path": "/my/project"
}
```

---

## Dashboard API (`/api/*`)

### GET /api/dashboard

Aggregated dashboard with summary, recent entities, health, timeline.

**Query:** `?project=/path`

### GET /api/decisions

**Query:** `?project=/path&status=active&limit=10`

Status: `active`, `all`, `superseded`, `archived`

### GET /api/facts

**Query:** `?project=/path&pinned=true&limit=10`

### GET /api/goals

**Query:** `?project=/path&status=active&limit=10`

### GET /api/tasks

**Query:** `?project=/path&status=in_progress&limit=10`

### GET /api/timeline

**Query:** `?project=/path&days=30&limit=20`

### GET /api/health

Memory health counters: entity counts, stale items, conflicts.

### GET /api/activity

**Query:** `?project=/path&type=decision&failed=true&limit=30`

---

## Branches API

### GET /api/branches

List all branches with entity counts.

**Response:**
```json
{
  "branches": [
    {"name": "main", "entity_count": 15, "parent_branch": null},
    {"name": "feature-x", "entity_count": 5, "parent_branch": "main", "description": "Feature X"}
  ],
  "current": "main",
  "count": 2
}
```

### GET /api/branches/compare

**Query:** `?project=/path&a=main&b=feature-x`

**Response:**
```json
{
  "summary": {
    "branch_a": "main",
    "branch_b": "feature-x",
    "only_in_a": 3,
    "only_in_b": 5,
    "conflicts": 1,
    "identical": false
  },
  "only_a": {"decisions": [{"id": 1, "title": "..."}]},
  "only_b": {"decisions": [{"id": 5, "title": "..."}]},
  "conflicts": {"decisions": [{"a": {...}, "b": {...}, "title": "Shared config"}]}
}
```

### GET /api/branches/replay

**Query:** `?project=/path&branch=feature-x&days=30&limit=50`

**Response:**
```json
{
  "branch": "feature-x",
  "events": [
    {"date": "2026-03-12T10:00:00", "type": "decision", "title": "Decision: Use Redis", "icon": "..."}
  ],
  "count": 5
}
```

### POST /api/branches/switch

```json
{"branch": "feature-x", "project": "/path"}
```

### POST /api/branches/merge

**Step 1 — Preview (without confirm):**
```json
{"source": "feature-x", "target": "main", "project": "/path"}
```
Returns `needs_confirm: true` with preview data.

**Step 2 — Execute (with confirm):**
```json
{"source": "feature-x", "target": "main", "confirm": true, "project": "/path"}
```

---

## Checkpoints API

### POST /api/checkpoints/create

```json
{"name": "before-refactor", "description": "Snapshot before major changes", "project": "/path"}
```

### POST /api/checkpoints/restore

**Step 1:** `{"id": 1}` — returns confirmation prompt
**Step 2:** `{"id": 1, "confirm": true}` — executes restore

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request (missing/invalid parameters) |
| 404 | Entity or branch not found |
| 500 | Server error |
