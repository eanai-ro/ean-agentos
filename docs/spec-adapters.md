# Adapter Specification v1.0

This document defines the contract for building adapters that connect AI CLI tools to EAN AgentOS.

---

## What is an Adapter?

An adapter is a thin client that translates a specific AI tool's workflow into EAN AgentOS API calls. It handles:

1. **Metadata injection** — automatically attaches cli_name, agent_name, provider, model_name, session_id, project_path to every request
2. **Session management** — generates and tracks session IDs
3. **API abstraction** — provides clean method calls instead of raw HTTP

---

## Required Metadata

Every adapter MUST provide these fields with every write operation:

| Field | Description | Example |
|-------|-------------|---------|
| `cli_name` | The CLI tool identifier | `"gemini-cli"`, `"codex-cli"`, `"claude-code"` |
| `agent_name` | The agent/assistant name | `"gemini-agent"`, `"codex"`, `"claude-opus"` |
| `provider` | Model provider | `"google"`, `"openai"`, `"anthropic"` |
| `model_name` | Specific model ID | `"gemini-2.5-pro"`, `"o3"`, `"claude-opus-4"` |
| `session_id` | Unique session identifier | `"gemini_20260312_143022_a1b2c3d4"` |
| `project_path` | Project directory path | `"/home/user/myproject"` |

### Session ID Format

Recommended format: `{prefix}_{YYYYMMDD_HHMMSS}_{8hex}`

Example: `gemini_20260312_143022_a1b2c3d4`

---

## Minimum Required Methods

Every adapter MUST implement these methods:

### Session Lifecycle

| Method | API Call | Description |
|--------|----------|-------------|
| `start_session(title=None)` | POST `/api/v1/events` | Emit `session_start` event |
| `get_context(mode, intent)` | GET `/api/v1/context` | Retrieve memory context |

### Entity Creation

| Method | API Call | Description |
|--------|----------|-------------|
| `create_decision(title, description, ...)` | POST `/api/v1/decisions` | Record a decision |
| `create_fact(fact, fact_type, ...)` | POST `/api/v1/facts` | Record a learned fact |
| `create_goal(title, description, ...)` | POST `/api/v1/goals` | Create a goal |
| `create_task(title, description, ...)` | POST `/api/v1/tasks` | Create a task |
| `create_resolution(error_summary, resolution, ...)` | POST `/api/v1/resolutions` | Record error resolution |

### Observability

| Method | API Call | Description |
|--------|----------|-------------|
| `send_event(event_type, title, payload)` | POST `/api/v1/events` | Emit integration event |
| `get_activity(limit)` | GET `/api/v1/activity` | Read activity log |
| `get_health()` | GET `/api/v1/health` | Check system health |

### Optional Methods

| Method | API Call | Description |
|--------|----------|-------------|
| `send_agent_event(event_type, ...)` | POST `/api/v1/agent-events` | Emit fine-grained event |
| `get_agent_events(limit, ...)` | GET `/api/v1/agent-events` | Query event stream |
| `log_activity(summary, payload)` | POST `/api/v1/events` | Convenience wrapper |

---

## Constructor Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| base_url | no | `http://localhost:19876` | Memory API base URL |
| project_path | no | `""` | Default project path |
| cli_name | yes | — | CLI tool identifier |
| agent_name | yes | — | Agent identifier |
| provider | yes | — | Model provider |
| model_name | yes | — | Model identifier |
| session_id | no | auto-generated | Override session ID |
| timeout | no | 10 | HTTP timeout in seconds |

---

## Implementation Pattern

The recommended implementation pattern is to wrap `UniversalMemoryClient`:

```python
from universal_memory_client import UniversalMemoryClient

class MyToolAdapter:
    def __init__(self, base_url="http://localhost:19876", project_path="",
                 model_name="my-model-v1"):
        self._client = UniversalMemoryClient(
            base_url=base_url,
            project_path=project_path,
            cli_name="my-tool",
            agent_name="my-agent",
            provider="my-provider",
            model_name=model_name,
            session_prefix="mytool",
        )

    def start_session(self, title=None):
        return self._client.start_session(title)

    def get_context(self, mode="compact", intent=None):
        return self._client.get_context(mode=mode, intent=intent)

    def create_decision(self, title, description="", **kwargs):
        return self._client.create_decision(title, description, **kwargs)

    # ... delegate all other methods
```

### Direct HTTP (no dependency on client library)

If you cannot use the Python client, make raw HTTP calls:

```python
import urllib.request, json

def _post(url, data):
    req = urllib.request.Request(url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

# Create a decision
_post("http://localhost:19876/api/v1/decisions", {
    "title": "Use Redis for caching",
    "description": "Redis chosen over Memcached for data structures support",
    "cli_name": "my-tool",
    "agent_name": "my-agent",
    "provider": "my-provider",
    "model_name": "my-model-v1",
    "session_id": "sess_001",
    "project_path": "/home/user/project"
})
```

---

## Existing Adapters

### GeminiMemoryAdapter

- File: `scripts/adapters/gemini_cli_adapter.py`
- Defaults: `cli_name="gemini-cli"`, `provider="google"`, `model_name="gemini-2.5-pro"`
- Pattern: Thin wrapper over `UniversalMemoryClient`

### CodexMemoryAdapter

- File: `scripts/adapters/codex_cli_adapter.py`
- Defaults: `cli_name="codex-cli"`, `provider="openai"`, `model_name="o3"`
- Pattern: Thin wrapper over `UniversalMemoryClient`

### MCP Server

- Files: `mcp_server/server.py`, `mcp_server/tools.py`
- Exposes 13 MCP tools via FastMCP
- Uses `UniversalMemoryClient` internally for entity operations
- Branch/observability operations call dashboard API directly (`/api/...`)
- Configured via environment variables

---

## Best Practices

1. **Always start a session** before making write calls — this establishes the session_id context
2. **Get context first** — call `get_context()` at session start to load existing memory
3. **Use appropriate confidence levels** — don't mark everything as `confirmed`
4. **Include rationale** for decisions — future agents benefit from understanding *why*
5. **Pin important facts** — pinned facts survive context trimming
6. **Check health** periodically — `get_health()` reveals stale data or errors
7. **Handle errors silently** — adapter failures should never crash the host tool
8. **Use branch-aware operations** when working on experimental features

---

## Error Handling

Adapters should follow the "silent failure" pattern:

```python
def create_decision(self, title, description=""):
    try:
        return self._client.create_decision(title, description)
    except Exception:
        return None  # Memory failure should never crash the host tool
```

The Memory API returns:
- `200` — Success, response body contains result
- `400` — Validation error (missing required fields, invalid values)
- `500` — Server error

All responses include a JSON body with at least `{"ok": true/false}` or `{"id": N, "message": "..."}`.
