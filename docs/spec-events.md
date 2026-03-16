# Event Specification v1.0

This document defines the official event taxonomy for the Agent Event Stream in EAN AgentOS.

---

## Overview

There are three event/logging tables, each serving a different purpose:

| Table | Purpose | Use case |
|-------|---------|----------|
| `universal_events` | Generic integration events | External tool notifications, session lifecycle |
| `agent_activity_log` | Semantic audit trail | What agents did and whether it succeeded |
| `agent_events` | Fine-grained execution stream | Detailed observability, replay, debugging |

This spec covers `agent_events` — the primary observability layer.

---

## Event Types (18 total)

### Agent Lifecycle

| Type | Description | Typical phase flow |
|------|-------------|--------------------|
| `agent_started` | Agent session begins | start → end |
| `agent_finished` | Agent session ends normally | end |
| `agent_error` | Agent encountered an error | error |

### Context Operations

| Type | Description | Typical phase flow |
|------|-------------|--------------------|
| `context_requested` | Agent requests memory context | start → end |
| `context_received` | Context delivered to agent | end |

### Entity Creation

| Type | Description | Related table |
|------|-------------|---------------|
| `decision_created` | New decision recorded | decisions |
| `fact_created` | New fact learned | learned_facts |
| `goal_created` | New goal set | goals |
| `task_created` | New task created | tasks |
| `task_updated` | Task status changed | tasks |
| `resolution_created` | Error resolution recorded | error_resolutions |

### Branch Operations

| Type | Description |
|------|-------------|
| `branch_switched` | Active branch changed |
| `branch_compared` | Two branches compared |
| `branch_merged` | Branch merge completed |

### Checkpoint Operations

| Type | Description |
|------|-------------|
| `checkpoint_created` | Memory checkpoint saved |
| `checkpoint_restored` | Memory restored from checkpoint |

### Generic

| Type | Description |
|------|-------------|
| `api_call` | Generic API call logged |
| `ui_action` | User action from web UI |

---

## Event Phases

Each event can go through phases:

| Phase | Meaning |
|-------|---------|
| `start` | Operation beginning |
| `progress` | Operation in progress (optional, for long-running ops) |
| `end` | Operation completed (default) |
| `error` | Operation failed |

Most events only have `end` phase. Use `start` + `end` pairs for operations where you need duration tracking.

---

## Event Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| event_type | TEXT | **yes** | — | One of the 18 types above |
| event_phase | TEXT | no | `"end"` | One of: `start`, `progress`, `end`, `error` |
| title | TEXT | no | null | Human-readable event title |
| summary | TEXT | no | null | Brief summary of what happened |
| detail | TEXT | no | null | Extended detail (log output, stack traces, etc.) |
| status | TEXT | no | `"completed"` | Free-form status string |
| success_flag | INTEGER | no | 1 | 1=success, 0=failure |
| duration_ms | INTEGER | no | null | Duration in milliseconds |
| started_at | TEXT | no | null | ISO timestamp when started |
| finished_at | TEXT | no | null | ISO timestamp when finished |
| parent_event_id | INTEGER | no | null | FK to parent event (for nesting) |
| related_table | TEXT | no | null | Entity table affected |
| related_id | INTEGER | no | null | Entity ID affected |
| metadata_json | TEXT | no | null | Arbitrary JSON metadata |

Plus all [common metadata fields](spec-memory-schema.md#common-metadata-fields): `project_path`, `session_id`, `branch_name`, `cli_name`, `agent_name`, `provider`, `model_name`.

---

## Success Flag

| Value | Meaning |
|-------|---------|
| 1 | Operation succeeded (default) |
| 0 | Operation failed |

Failed events (`success_flag=0`) are visually highlighted in the UI and can be filtered via `?failed=true`.

---

## Parent Events

Events can be nested using `parent_event_id`. This enables hierarchical event structures:

```
agent_started (id=1)
  ├── context_requested (parent_event_id=1)
  ├── decision_created (parent_event_id=1)
  ├── fact_created (parent_event_id=1)
  └── agent_finished (parent_event_id=1)
```

---

## Branch-Aware Behavior

- Events carry `branch_name` to indicate which branch was active when the event occurred
- Branch operations (`branch_switched`, `branch_merged`) always record the branch context
- Events are queryable by branch: `GET /api/events?branch=feature-x`

---

## Auto-Fill Behavior

When using the `log_agent_event()` helper or the API, certain fields are auto-filled if not provided:

| Field | Auto-fill source |
|-------|------------------|
| project_path | `v2_common.get_project_path()` or state file |
| session_id | Current session state file |
| branch_name | `v2_common.get_current_branch()` |
| model_name | Current model state file |
| provider | Current provider state file |
| created_at | `datetime('now')` |

---

## API Endpoints

### Ingest events

```
POST /api/v1/agent-events
Content-Type: application/json

{
  "event_type": "decision_created",
  "title": "Chose PostgreSQL",
  "summary": "Selected PostgreSQL over MySQL for JSONB support",
  "event_phase": "end",
  "success_flag": 1,
  "duration_ms": 150,
  "related_table": "decisions",
  "related_id": 42,
  "agent_name": "claude-opus",
  "model_name": "claude-opus-4"
}
```

### Query events

```
GET /api/events?agent=claude-opus&type=decision_created&branch=main&failed=false&limit=50
GET /api/v1/agent-events?project=/path&type=agent_error&limit=20
```

Both endpoints return:
```
{"ok": true, "events": [...], "count": 5}
```

---

## Timeline Integration

Only significant events appear in the unified timeline to avoid noise:
- `agent_error`
- `branch_merged`
- `checkpoint_created`
- `checkpoint_restored`

---

## Example Payloads

### Agent session with error

```json
[
  {"event_type": "agent_started", "title": "GLM-5 session", "agent_name": "glm-5", "session_id": "sess_001"},
  {"event_type": "context_requested", "title": "Get project context", "parent_event_id": 1},
  {"event_type": "agent_error", "title": "OOM during inference", "success_flag": 0, "detail": "CUDA out of memory", "parent_event_id": 1},
  {"event_type": "agent_finished", "title": "Session ended with error", "success_flag": 0, "duration_ms": 5000, "parent_event_id": 1}
]
```

### Branch merge event

```json
{
  "event_type": "branch_merged",
  "title": "Merge feature-auth into main",
  "summary": "12 entities merged, 0 conflicts",
  "metadata": {"source": "feature-auth", "target": "main", "entities_merged": 12, "conflicts": 0}
}
```
