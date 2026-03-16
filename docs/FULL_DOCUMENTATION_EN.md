# EAN AgentOS — Complete Documentation

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Memory Core (Free)](#3-memory-core-free)
4. [Solution Index — "Never Solve the Same Bug Twice" (Free)](#4-solution-index-free)
5. [Knowledge Extraction (Free)](#5-knowledge-extraction-free)
6. [Context Builder (Free)](#6-context-builder-free)
7. [Experience Graph (Free)](#7-experience-graph-free)
8. [Search & Cognitive Search (Free)](#8-search--cognitive-search-free)
9. [Branch-Aware Memory (Free)](#9-branch-aware-memory-free)
10. [Backup & Recovery (Free)](#10-backup--recovery-free)
11. [Web Dashboard (Free)](#11-web-dashboard-free)
12. [MCP Server (Free)](#12-mcp-server-free)
13. [CLI — `mem` (Free)](#13-cli--mem-free)
14. [CLI Integrations (Free)](#14-cli-integrations-free)
15. [Multi-Agent Orchestration (Pro)](#15-multi-agent-orchestration-pro)
16. [AI Deliberation (Pro)](#16-ai-deliberation-pro)
17. [CLI Launcher (Pro)](#17-cli-launcher-pro)
18. [Auto-Pipeline (Pro)](#18-auto-pipeline-pro)
19. [Intelligence Layer (Pro)](#19-intelligence-layer-pro)
20. [Replay System (Pro)](#20-replay-system-pro)
21. [Peer Review (Pro)](#21-peer-review-pro)
22. [License & Plans](#22-license--plans)
23. [API Reference](#23-api-reference)
24. [Troubleshooting](#24-troubleshooting)

---

## 1. Overview

EAN AgentOS is a persistent memory and orchestration system for AI coding agents. Works with Claude Code, Gemini CLI, Codex CLI, and Kimi CLI.

### Editions

| Edition | Includes | Price |
|---------|----------|-------|
| **Community (Free)** | Persistent memory, solution index, knowledge extraction, experience graph, search, backup, dashboard, MCP | Free (MIT) |
| **Team (Pro)** | + Orchestration, deliberation, CLI launcher, peer review, replay | $29/mo/seat |
| **Enterprise (Pro)** | + Intelligence layer, skill learning, auto-pipeline, smart routing | $99/mo/seat |

---

## 2. Installation

### Requirements

- Python 3.10+
- SQLite 3.35+
- pip (for dependencies)
- At least one AI CLI: Claude Code, Gemini CLI, Codex CLI, or Kimi CLI

### Automatic Install

```bash
git clone https://github.com/eanai-ro/ean-agentos.git
cd ean-agentos
./install.sh
```

The installer:
1. Installs Python dependencies
2. Initializes database (49 tables)
3. Creates `mem` command in PATH
4. Detects installed CLIs with interactive selector
5. Configures hooks and MCP server

### Manual Install

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

### What it stores

| Entity | Table | Description |
|--------|-------|-------------|
| **Decisions** | `decisions` | Technical decisions with context and reasoning |
| **Facts** | `learned_facts` | Learned facts about the project |
| **Goals** | `goals` | Long-term objectives |
| **Tasks** | `tasks` | Tasks to do |
| **Resolved errors** | `error_resolutions` | Errors + structured solutions |
| **Sessions** | `sessions` | Work sessions |
| **Messages** | `messages` | User + agent messages |

### How capture works

Hooks installed for each CLI auto-capture:
- Work sessions (start/stop)
- User messages and agent responses
- Tool calls (Bash, Edit, Read, Write)
- Detected errors
- Resolutions (applied solutions)

Everything saved to `global.db` (SQLite with WAL mode).

### The `mem` command

```bash
mem status           # Memory status
mem decisions        # Active decisions
mem facts            # Learned facts
mem goals            # Goals
```

---

## 4. Solution Index — "Never Solve the Same Bug Twice" (Free)

### The most important feature

```bash
mem suggest "CORS error"
```

Searches 3 sources:
1. **error_resolutions** — structured resolved errors (V2)
2. **errors_solutions** — errors resolved from hooks
3. **error_patterns** — recurring patterns

### Scoring

Each result has:
- **Match quality** (0-100%) — how similar to the query
- **Confidence** (0-100%) — how reliable the solution is
- **Combined score** — 40% match + 60% confidence

### Example

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

### What it does

Auto-extracts knowledge from AI sessions:
- Technical decisions
- Project facts
- Errors + solutions
- Recurring patterns

### Features
- **Pattern compilation** — auto-recognition of decision types
- **Negative filters** — exclude spam, greetings, non-technical
- **Transparent scoring** — each extraction has confidence score
- **Deduplication** — no duplicate information
- **Auto-classification** — automatic categories

---

## 6. Context Builder (Free)

### What it does

Builds optimized LLM context from permanent memory. At each new session, the agent receives the most relevant information.

### Modes

| Mode | Description | When |
|------|-------------|------|
| `compact` | Essentials: active decisions + key facts | Default |
| `full` | Everything: including history, tasks, errors | Long sessions |
| `survival` | Absolute minimum (post-compact) | Small context |

---

## 7. Experience Graph (Free)

### What it does

Connects problems with solutions in a graph:

```
Problem → Investigation → Solution → Outcome
```

### Commands

```bash
mem graph stats          # Graph statistics
mem graph show           # Visualization
mem graph build          # Rebuild graph
```

---

## 8. Search & Cognitive Search (Free)

### Unified search

```bash
mem search "authentication"
```

Searches across: messages, bash commands, decisions, facts, goals, tasks, resolutions, errors.

---

## 9. Branch-Aware Memory (Free)

Memory branches with git branches. Decisions made on `feature/auth` don't interfere with `main`.

```bash
mem branch list          # List branches
mem branch switch <name> # Switch branch
mem branch compare A B   # Compare branches
mem branch merge A B     # Merge branches
```

---

## 10. Backup & Recovery (Free)

```bash
mem backup create        # Manual backup
mem backup restore <file># Restore
```

Uses SQLite backup API with integrity verification.

---

## 11. Web Dashboard (Free)

```bash
python3 scripts/web_server.py
# Open: http://localhost:19876
```

Tabs: Dashboard, Decisions, Facts, Goals & Tasks, Timeline, Context, Health, Activity, Errors, Branches, Events.

---

## 12. MCP Server (Free)

Native integration with Claude Code and MCP-compatible CLIs.

### Available tools

| Tool | Description |
|------|-------------|
| `memory_search` | Search memory |
| `memory_get_context` | Get optimized context |
| `memory_store_decision` | Save decision |
| `memory_store_fact` | Save fact |

---

## 13. CLI — `mem` (Free)

```bash
mem status                # General status
mem decisions             # Active decisions
mem facts                 # Facts
mem suggest "error"       # Find past solutions
mem search "keyword"      # Search all memory
mem graph stats           # Experience graph
mem err last              # Recent errors
mem backup create         # Backup
mem branch list           # Memory branches
```

---

## 14. CLI Integrations (Free)

| CLI | Command | What it installs |
|-----|---------|-----------------|
| Claude Code | `python3 scripts/ean_memory.py install claude` | MCP Server + Hooks |
| Gemini CLI | `python3 scripts/ean_memory.py install gemini` | Hooks |
| Codex CLI | `python3 scripts/ean_memory.py install codex` | Hooks |
| Kimi CLI | Manual | MCP config |

---

## 15. Multi-Agent Orchestration (Pro) 🔒

Coordinate multiple AI CLIs on the same project. Projects with tasks, lease-based ownership, intelligent routing.

```bash
mem orch create "Project Title"
mem orch add-task 1 "Title" "Description"
mem orch tasks --available
mem orch claim 1
mem orch done 1 "Summary"
```

### DB Schema
- `orchestration_projects` — projects
- `orch_tasks` — tasks with lease (30 min)
- `orch_agents` — agent presence (online/busy/offline)
- `orch_messages` — inter-agent messages

---

## 16. AI Deliberation (Pro) 🔒

Structured multi-agent deliberation sessions with rounds, voting, and automatic synthesis.

| Type | Rounds | Phases |
|------|--------|--------|
| quick | 2 | proposal → synthesis |
| deep | 4 | proposal → analysis → refinement → synthesis |
| expert | 6 | proposal → analysis → critique → refinement → vote → synthesis |

### Consensus detection
- Jaccard similarity ≥ 0.25 = consensus
- Theme clustering (8 categories)
- Levels: full / high / moderate / low / none

---

## 17. CLI Launcher (Pro) 🔒

Programmatically launch AI CLIs with a task or deliberation session.

```bash
mem orch launch gemini-cli --task 5
mem orch launch claude-code --deliberate 2
```

### Permission modes: safe (default) / auto / unsafe

---

## 18. Auto-Pipeline (Pro Enterprise) 🔒🔒

Automatic pipeline with review + auto-fix + conflict escalation.

```bash
mem orch run-project 1 --auto-fix
```

Flow: Task → Execute → Review → approve/changes_requested/blocked

---

## 19. Intelligence Layer (Pro Enterprise) 🔒🔒

- Agent capabilities from review history + task success
- Weighted voting (expert votes count more)
- Skill learning from review comments (10 categories, sentiment analysis)

---

## 20. Replay System (Pro) 🔒

Complete timelines for debugging and audit.

```bash
mem orch replay 1           # Project timeline
mem orch replay-delib 2     # Deliberation timeline
```

---

## 21. Peer Review (Pro) 🔒

Formal review workflow: review request → CLI reviewer executes → verdict (approve/changes_requested/blocked/security_risk) → comments saved.

---

## 22. License & Plans

### Community (Free)

Free, MIT license. Everything in sections 3-14.

### Pro

License activated via `~/.ean-memory/license.key` (JSON or JWT).

```json
{
  "email": "user@company.com",
  "plan": "team",
  "expires_at": "2027-01-01T00:00:00"
}
```

**Details**: [ean@eanai.ro](mailto:ean@eanai.ro)

---

## 23. API Reference

### Free Endpoints

```
GET  /api/dashboard, /api/decisions, /api/facts, /api/goals
GET  /api/tasks, /api/health, /api/timeline, /api/context
GET  /api/activity, /api/errors, /api/events, /api/branches
```

### Pro Endpoints 🔒

```
POST/GET  /api/v1/orch/projects, /tasks, /deliberation
POST/GET  /api/v1/orch/messages, /agents, /heartbeat
POST/GET  /api/v1/orch/launch, /launches, /reviews
GET       /api/v1/orch/replay/<id>, /capabilities
```

---

## 24. Troubleshooting

| Problem | Solution |
|---------|----------|
| DB not found | `python3 scripts/init_db.py` |
| `mem` not found | `export PATH=$HOME/.local/bin:$PATH` |
| Hooks not working | `python3 scripts/ean_memory.py test` |
| MCP not connecting | Check `~/.claude/.mcp.json` |
| Dashboard won't start | `pip install flask flask-cors` |
