# Multi-Agent Orchestration — Complete Documentation

## Overview

The multi-agent orchestration system coordinates 4 AI CLIs (Claude Code, Gemini CLI, Codex CLI, Kimi CLI) through a **peer-to-peer DB-based architecture**. There is no central orchestrator — any CLI can create projects, claim tasks, participate in deliberations, and perform reviews.

### Architecture

```
  Claude Code    Gemini CLI    Codex CLI    Kimi CLI
       │              │             │            │
       │   claim / complete / propose / vote     │
       └──────────────┬─────────────┬────────────┘
                      │             │
                      ▼             ▼
               ┌──────────────────────────┐
               │       global.db          │
               │  (10 orchestration tbl)  │
               └──────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      REST API    MCP Tools    CLI (mem)
       (20 ep)     (6 tools)   (18 cmds)
```

---

## Development Phases

| Phase | Name | What it adds | Tests |
|-------|------|-------------|-------|
| **18D** | Orchestration Engine | Projects, lease-based tasks, deliberation, messaging, agent presence | 25/25 |
| **18E** | Dashboard + Daemon | Web Orchestration tab, automated housekeeping | 15/15 |
| **18F** | CLI Launcher | Programmatic CLI launching (subprocess) | 15/15 |
| **18G** | Auto-Loop | Automated multi-round deliberation, task pipeline | 10/10 |
| **18H** | Peer Review | Formal review workflow: review → verdict → comments | 10/10 |
| **18I** | Auto-Pipeline | Re-run after negative review, conflict escalation | 8/8 |
| **19** | Intelligence + Replay | Dynamic capabilities, weighted voting, timeline replay | 10/10 |
| **20** | Skill Learning | Skill extraction from reviews, sentiment analysis, persistent learning | 8/8 |
| **Total** | | | **101/101** |

---

## Database Schema (10 tables)

### orchestration_projects
Orchestrated projects with status and orchestrator CLI.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Project ID |
| title | TEXT | Title |
| description | TEXT | Description |
| orchestrator_cli | TEXT | CLI that created the project |
| status | TEXT | active / paused / completed / failed |
| project_path | TEXT | Disk path |
| created_at | TEXT | Timestamp |
| completed_at | TEXT | Completion timestamp |

### orch_tasks
Tasks with lease-based ownership and dependencies.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Task ID |
| project_id | INTEGER FK | Parent project |
| title | TEXT | Task title |
| description | TEXT | Description |
| task_type | TEXT | implementation / review / research / fix |
| required_skills | TEXT JSON | Required skills: ["code", "architecture"] |
| priority | TEXT | critical / high / medium / low |
| status | TEXT | pending / assigned / in_progress / done / failed / blocked |
| assigned_cli | TEXT | Working CLI |
| lease_token | TEXT UUID | Ownership token (expires after 30 min) |
| lease_expires_at | TEXT | Lease expiration time |
| depends_on | TEXT JSON | Task IDs this depends on |
| result_summary | TEXT | Result summary (max 5000 chars) |

### orch_sessions
Deliberation sessions with structured rounds.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Session ID |
| topic | TEXT | Deliberation topic |
| session_type | TEXT | quick (2 rounds) / deep (4) / expert (6) |
| current_round | INTEGER | Current round |
| total_rounds | INTEGER | Total rounds |
| participating_clis | TEXT JSON | Participating CLIs |
| consensus_level | TEXT | full / high / moderate / low / none |
| synthesis_result | TEXT JSON | Synthesis result |

### orch_proposals
Proposals per round per CLI.

| Column | Type | Description |
|--------|------|-------------|
| session_id | INTEGER FK | Session |
| round_number | INTEGER | Round number |
| round_phase | TEXT | proposal / analysis / critique / refinement / vote / synthesis |
| cli_name | TEXT | Proposing CLI |
| content | TEXT | Proposal content |
| confidence | REAL | 0.0 - 1.0 |

### orch_votes
Votes with weight (from capabilities).

| Column | Type | Description |
|--------|------|-------------|
| session_id | INTEGER FK | Session |
| cli_name | TEXT | Voter |
| voted_for | TEXT | What they voted for |
| reasoning | TEXT | Reasoning |
| weight | REAL | Vote weight (from capabilities) |

### orch_messages
Inter-agent messages (broadcast or direct).

| Column | Type | Description |
|--------|------|-------------|
| from_cli | TEXT | Sender |
| to_cli | TEXT | Recipient (NULL = broadcast) |
| message_type | TEXT | info / question / answer / review / correction / handoff |
| content | TEXT | Content |
| in_reply_to | INTEGER FK | Reply to another message |

### orch_agents
Agent presence tracking.

| Column | Type | Description |
|--------|------|-------------|
| cli_name | TEXT PK | CLI identifier |
| status | TEXT | online / busy / offline |
| last_seen | TEXT | Last heartbeat |
| current_task_id | INTEGER | Current task |

### orch_reviews
Peer review with formal verdicts.

| Column | Type | Description |
|--------|------|-------------|
| task_id | INTEGER FK | Reviewed task |
| reviewer_cli | TEXT | Reviewer |
| verdict | TEXT | approve / changes_requested / blocked / security_risk |
| comments | TEXT | Detailed comments |
| severity | TEXT | info / warning / critical |
| original_cli | TEXT | Who did the task |

### orch_skill_observations
Skill observations learned from reviews.

| Column | Type | Description |
|--------|------|-------------|
| cli_name | TEXT | Observed agent |
| skill | TEXT | Skill (architecture, code, testing, security, etc.) |
| score | REAL | -1.0 (bad) to +1.0 (excellent) |
| source | TEXT | review / review_text / task / meta |
| evidence | TEXT | Evidence text |

---

## REST API (20 endpoints)

Base URL: `http://localhost:19876`

### Projects
```
POST   /api/v1/orch/projects              Create project
GET    /api/v1/orch/projects              List projects (with task counts)
GET    /api/v1/orch/projects/<id>         Project status + tasks + agents
```

### Tasks
```
POST   /api/v1/orch/tasks                Create task
GET    /api/v1/orch/tasks                List (?available=1&cli=X&mine=1)
POST   /api/v1/orch/tasks/<id>/claim     Claim with lease (30 min)
POST   /api/v1/orch/tasks/<id>/complete  Complete (?failed=1 for fail)
```

### Deliberation
```
GET    /api/v1/orch/deliberation          List sessions
POST   /api/v1/orch/deliberation          Create session
GET    /api/v1/orch/deliberation/<id>     Status + round context
POST   /api/v1/orch/deliberation/<id>/respond  propose / vote / advance / synthesize
```

### Messages
```
POST   /api/v1/orch/messages              Send message
GET    /api/v1/orch/messages              Read (?to=X&unread=1)
```

### Agents
```
GET    /api/v1/orch/agents                Agent status (online/offline)
POST   /api/v1/orch/heartbeat            Heartbeat + sync
```

### Launcher
```
POST   /api/v1/orch/launch               Launch CLI (task/session/prompt)
GET    /api/v1/orch/launches              Active launches
```

### Reviews
```
GET    /api/v1/orch/reviews               List reviews (?task_id=X&verdict=Y)
POST   /api/v1/orch/reviews/request       Launch review on task
```

### Intelligence + Replay
```
GET    /api/v1/orch/replay/<project_id>   Complete project timeline
GET    /api/v1/orch/capabilities          Capabilities leaderboard
```

---

## CLI (mem orch)

### Projects & Tasks
```bash
mem orch create "Title" [description]             # Create project
mem orch status [project_id]                      # Status
mem orch add-task <proj> "title" "desc"            # Add task
mem orch tasks [--mine|--available]                # List tasks
mem orch claim <task_id>                          # Claim with lease
mem orch done <task_id> [summary]                 # Mark done
```

### Deliberation
```bash
mem orch deliberate "topic" [--type deep]          # Start manual deliberation
mem orch propose <session_id> "text"               # Proposal
mem orch vote <session_id> <option>                # Vote
mem orch deliberate-auto "question" [--type deep]  # Auto deliberation (all CLIs)
```

### Communication
```bash
mem orch send <to|all> "message"                  # Send inter-agent message
mem orch messages [--unread]                      # Read messages
mem orch agents                                   # Who's online
```

### Launcher
```bash
mem orch launch <cli> --task <id>                 # Launch CLI for task
mem orch launch <cli> --deliberate <session_id>   # Launch for deliberation
mem orch launch <cli> --prompt "text"             # Custom prompt
mem orch launches                                 # List active launches
```

### Review & Pipeline
```bash
mem orch review <task_id> --by <cli>              # Peer review on task
mem orch reviews [--task X] [--verdict approve]   # List reviews
mem orch run-project <id> [--review] [--auto-fix] # Full pipeline with review
```

### Intelligence
```bash
mem orch capabilities                             # CLI capabilities leaderboard
mem orch skills [cli_name]                        # Learned skills per CLI
mem orch replay <project_id>                      # Project timeline
mem orch replay-delib <session_id>                # Deliberation timeline
mem orch daemon [--once]                          # Housekeeping daemon
```

---

## MCP Tools (6)

| Tool | Description |
|------|-------------|
| `orch_project_create` | Create orchestrated project |
| `orch_tasks` | Task management (create/claim/complete/fail/list) |
| `orch_deliberation` | Deliberation (create/propose/vote/advance/synthesize) |
| `orch_messaging` | Send/read inter-agent messages |
| `orch_agent_heartbeat` | Heartbeat + status sync |
| `orch_launch_cli` | Launch CLI for task/deliberation/prompt |

---

## CLI Profiles

| CLI | Strengths | Command |
|-----|-----------|---------|
| **claude-code** | architecture, complex_code, review, debugging | `claude --print "prompt"` |
| **gemini-cli** | code, research, docs, testing | `gemini -p "prompt"` |
| **codex-cli** | code, fix, refactor | `codex exec "prompt"` |
| **kimi-cli** | reasoning, research, math, analysis | `kimi --print --prompt "prompt"` |

### Binary Discovery (portable)
1. Environment variable: `ORCH_CLAUDE_CODE_PATH`, `ORCH_GEMINI_CLI_PATH`, etc.
2. `shutil.which()` — searches PATH
3. Fallback paths: `~/.local/bin/`

### Permission Modes
| Mode | Description | Default |
|------|-------------|---------|
| `safe` | No bypass. CLI may ask for confirmation. | **Yes** |
| `auto` | Minimum required (Claude: `--permission-mode auto`) | No |
| `unsafe` | Full bypass (only explicit with `--unsafe`) | No |

---

## Deliberation Session Types

| Type | Rounds | Phases |
|------|--------|--------|
| **quick** | 2 | proposal → synthesis |
| **deep** | 4 | proposal → analysis → refinement → synthesis |
| **expert** | 6 | proposal → analysis → critique → refinement → vote → synthesis |

### Consensus Levels
| Level | Condition |
|-------|-----------|
| full | ≥90% agreement |
| high | ≥75% |
| moderate | ≥50% |
| low | ≥25% |
| none | <25% |

---

## Intelligence Layer

### Capability Scoring (5 sources)
1. **Static** — CLI_PROFILES.strengths (baseline 0.5)
2. **Task success** — Rate per task_type from orch_tasks
3. **Review approval** — How often output is approved
4. **Review accuracy** — How often reviews are correct
5. **Learned skills** — From orch_skill_observations (keyword + sentiment)

### Skill Learning
The daemon automatically extracts observations from review comments:
- **10 skill categories:** architecture, code, testing, security, performance, debugging, concurrency, documentation, refactoring, review
- **Sentiment analysis:** positive/negative from keywords
- **Blend:** 60% existing capabilities + 40% learned skills

### Weighted Voting
An agent's vote counts more if they have relevant capabilities for the topic.
- Weight: 0.5 (min) — 2.0 (max)
- Calculated from capabilities match on topic keywords

---

## Auto-Pipeline

### Complete Flow
```
1. mem orch run-project <id> --auto-fix
2. Task #1 → route_task() → claude-code (best match)
3. launch_for_task() → subprocess → result
4. Auto-review: gemini-cli reviews output
   → approve → next task
   → changes_requested → re-launch with feedback (max 2 retries)
   → blocked/security_risk → automatic mini-deliberation
5. Task #2 → depends_on #1 resolved → launch
6. Repeat until all tasks done/failed
```

---

## Housekeeping Daemon

Runs periodically (default 60s) or single-pass (cron-friendly):
```bash
python3 orch_daemon.py          # Continuous loop
python3 orch_daemon.py --once   # Single pass
```

### What it does:
1. **Stale leases** — expired task leases → revert to pending
2. **Agent offline** — last_seen > 5 min → mark offline
3. **Auto-advance** — sessions where all responded → advance round
4. **Skill learning** — extract observations from new reviews
5. **Capabilities update** — recalculate scores in agent_reputation

---

## Replay System

### Project Timeline
```bash
mem orch replay <project_id>
```
Shows chronologically: project creation, tasks created/claimed/completed, reviews, deliberations, messages.

### Deliberation Timeline
```bash
mem orch replay-delib <session_id>
```
Shows: session start, proposals per round per CLI, votes, final synthesis.

---

## Web Dashboard

"Orchestration" tab with 6 sub-views:
1. **Projects** — cards with status, task counts, click for details
2. **Tasks** — grouped by status (in_progress, pending, done, failed)
3. **Agents** — 4 cards with status indicator (green/yellow/gray)
4. **Deliberation** — sessions with rounds, expandable for proposals/votes
5. **Messages** — chat format, from → to, message type badge
6. **Reviews** — verdict badges (approve/changes_requested/blocked)

---

## Statistics

| Metric | Value |
|--------|-------|
| Orchestration code (scripts/) | ~4,600 lines |
| Web frontend | ~2,500 lines |
| New DB tables | 10 |
| API endpoints | 20 |
| CLI commands | 18 |
| MCP tools | 6 |
| Total tests | 101/101 |
| Phases implemented | 8 (18D → 20) |
