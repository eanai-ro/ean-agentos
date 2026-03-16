# Compatibility Matrix v1.0

Feature support across all clients and integrations.

---

## Client Overview

| Client | Type | File | Transport |
|--------|------|------|-----------|
| **Claude Code** | Native (direct DB) | `scripts/v2_common.py` + CLI | SQLite direct |
| **Gemini CLI** | Adapter | `scripts/adapters/gemini_cli_adapter.py` | HTTP REST |
| **Codex CLI** | Adapter | `scripts/adapters/codex_cli_adapter.py` | HTTP REST |
| **UniversalMemoryClient** | SDK | `scripts/clients/universal_memory_client.py` | HTTP REST |
| **MCP Server** | Bridge | `mcp_server/server.py` + `tools.py` | MCP over stdio |
| **Web Dashboard** | UI | `web/index.html` + `app.js` | HTTP REST |

---

## Feature Matrix

### Core Memory Operations

| Feature | Claude Code | Gemini CLI | Codex CLI | Python SDK | MCP Server | Web UI |
|---------|:-----------:|:----------:|:---------:|:----------:|:----------:|:------:|
| Create decision | direct | via API | via API | via API | via API | — |
| Create fact | direct | via API | via API | via API | via API | — |
| Create goal | direct | via API | via API | via API | via API | — |
| Create task | direct | via API | via API | via API | via API | — |
| Create resolution | direct | via API | via API | via API | via API | — |
| Read decisions | direct | — | — | — | — | via API |
| Read facts | direct | — | — | — | — | via API |
| Read goals/tasks | direct | — | — | — | — | via API |
| Pin/unpin facts | direct | — | — | — | — | via API |
| Promote facts | direct | — | — | — | — | via API |
| Update task status | direct | — | — | — | — | via API |

### Context & Session

| Feature | Claude Code | Gemini CLI | Codex CLI | Python SDK | MCP Server | Web UI |
|---------|:-----------:|:----------:|:---------:|:----------:|:----------:|:------:|
| Get context | direct | via API | via API | via API | via API | via API |
| Context modes (compact/full/survival/delta) | all | all | all | all | all | compact/full/survival |
| Intent-aware context | yes | yes | yes | yes | yes | yes |
| Start session | direct | via API | via API | via API | — | — |
| Session tracking | yes | yes | yes | yes | — | — |
| Set intent | direct | — | — | — | — | via API |
| Set model | direct | — | — | — | — | via API |

### Observability

| Feature | Claude Code | Gemini CLI | Codex CLI | Python SDK | MCP Server | Web UI |
|---------|:-----------:|:----------:|:---------:|:----------:|:----------:|:------:|
| Activity logging | direct | via API | via API | via API | via API | read-only |
| Send events | direct | via API | via API | via API | — | — |
| Agent events | direct | — | — | via API | — | read-only |
| Health check | direct | via API | via API | via API | via API | via API |
| Timeline | direct | — | — | — | via API | via API |

### Branches

| Feature | Claude Code | Gemini CLI | Codex CLI | Python SDK | MCP Server | Web UI |
|---------|:-----------:|:----------:|:---------:|:----------:|:----------:|:------:|
| Create branch | CLI | — | — | — | — | — |
| Switch branch | CLI | — | — | — | via API | via API |
| List branches | CLI | — | — | — | via API | via API |
| Compare branches | CLI | — | — | — | via API | via API |
| Merge branches | CLI | — | — | — | via API | via API |
| Replay branch | CLI | — | — | — | — | via API |
| Delete branch | CLI | — | — | — | — | — |
| Branch-scoped writes | yes | yes* | yes* | yes* | — | — |

\* Gemini/Codex/SDK writes go to whichever branch is active on the server

### Checkpoints

| Feature | Claude Code | Gemini CLI | Codex CLI | Python SDK | MCP Server | Web UI |
|---------|:-----------:|:----------:|:---------:|:----------:|:----------:|:------:|
| Create checkpoint | CLI | — | — | — | — | via API |
| Restore checkpoint | CLI | — | — | — | — | via API |
| List checkpoints | CLI | — | — | — | — | via API |

### Events UI

| Feature | Claude Code | Gemini CLI | Codex CLI | Python SDK | MCP Server | Web UI |
|---------|:-----------:|:----------:|:---------:|:----------:|:----------:|:------:|
| View events | CLI | — | — | — | — | full UI |
| Filter events | CLI | — | — | via API | — | full UI |
| Event detail | — | — | — | — | — | modal |
| Agent replay | — | — | — | — | — | visual |

---

## API Coverage

### Universal API (`/api/v1/...`)

| Endpoint | Method | Gemini | Codex | Python SDK | MCP |
|----------|--------|:------:|:-----:|:----------:|:---:|
| `/api/v1/context` | GET | yes | yes | yes | yes |
| `/api/v1/decisions` | POST | yes | yes | yes | yes |
| `/api/v1/facts` | POST | yes | yes | yes | yes |
| `/api/v1/goals` | POST | yes | yes | yes | yes |
| `/api/v1/tasks` | POST | yes | yes | yes | yes |
| `/api/v1/resolutions` | POST | yes | yes | yes | yes |
| `/api/v1/events` | POST | yes | yes | yes | — |
| `/api/v1/agent-events` | POST | — | — | yes | — |
| `/api/v1/agent-events` | GET | — | — | yes | — |
| `/api/v1/activity` | GET | yes | yes | yes | — |
| `/api/v1/health` | GET | yes | yes | yes | — |

### Dashboard API (`/api/...`)

| Endpoint | Method | MCP | Web UI |
|----------|--------|:---:|:------:|
| `/api/dashboard` | GET | — | yes |
| `/api/decisions` | GET | — | yes |
| `/api/facts` | GET | — | yes |
| `/api/goals` | GET | — | yes |
| `/api/tasks` | GET | — | yes |
| `/api/timeline` | GET | yes | yes |
| `/api/activity` | GET | yes | yes |
| `/api/health` | GET | yes | yes |
| `/api/events` | GET | — | yes |
| `/api/branches` | GET | yes | yes |
| `/api/branches/compare` | GET | yes | yes |
| `/api/branches/replay` | GET | — | yes |
| `/api/branches/switch` | POST | yes | yes |
| `/api/branches/merge` | POST | yes | yes |
| `/api/checkpoints` | GET | — | yes |
| `/api/checkpoints/create` | POST | — | yes |
| `/api/checkpoints/restore` | POST | — | yes |
| `/api/errors` | GET | — | yes |

---

## Default Metadata by Client

| Client | cli_name | agent_name | provider | model_name |
|--------|----------|------------|----------|------------|
| Gemini CLI | `gemini-cli` | `gemini-agent` | `google` | `gemini-2.5-pro` |
| Codex CLI | `codex-cli` | `codex` | `openai` | `o3` |
| Python SDK | `python-client` | `generic` | `unknown` | `unknown` |
| MCP Server | env `MEMORY_AGENT_NAME` | env-configured | env-configured | env-configured |

---

## Requirements

| Component | Python | SQLite | Flask | Other |
|-----------|--------|--------|-------|-------|
| Core | 3.10+ | 3.35+ (FTS5) | — | — |
| API Server | 3.10+ | 3.35+ | 3.0+ | — |
| MCP Server | 3.10+ | — | — | `mcp` package |
| Adapters | 3.10+ | — | — | stdlib only |
| Web UI | — | — | — | Modern browser |
