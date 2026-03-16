# Demo Walkthrough

A complete end-to-end demonstration of Universal Agent Memory.

---

## Prerequisites

```bash
pip install flask
python3 scripts/init_db.py
```

## 1. Start the Server

```bash
./scripts/run_server.sh
# Server starts on http://localhost:19876
```

## 2. Seed Demo Data (optional)

```bash
# In a new terminal:
python3 scripts/demo_seed.py
# Creates 3 decisions, 4 facts, 2 goals, 5 tasks, 2 resolutions, 5 events
```

## 3. Explore via CLI

```bash
# View dashboard
python3 scripts/mem dashboard

# Check context (what an agent receives)
python3 scripts/mem context --compact

# List decisions
python3 scripts/mem decide --list

# View timeline
python3 scripts/mem timeline

# Check health
python3 scripts/mem health
```

## 4. Create Memory Entities

```bash
# Record a decision
python3 scripts/mem decide "Use WebSocket for real-time updates" \
  -d "Chose WebSocket over SSE for bidirectional communication" \
  -c architectural --confidence high

# Learn a fact
python3 scripts/mem learn "Max upload size is 10MB" -t convention --pin

# Set a goal
python3 scripts/mem goal "Implement real-time notifications" -p high

# Add a task
python3 scripts/mem task "Design WebSocket message protocol" -p high --goal 1

# Record a resolution
python3 scripts/mem resolve "Connection refused on port 5432" \
  "Start PostgreSQL: sudo systemctl start postgresql" \
  --type config_change
```

## 5. Set Intent and Model

```bash
# Set current work intent (optimizes context retrieval)
python3 scripts/mem intent set feature

# View current intent
python3 scripts/mem intent
```

## 6. Work with Branches

```bash
# Create an experimental branch
python3 scripts/mem branch create auth-experiment -d "Exploring OAuth2 vs JWT"

# Switch to it
python3 scripts/mem branch switch auth-experiment

# Create decisions on the branch
python3 scripts/mem decide "Use OAuth2 with PKCE" \
  -d "More secure than plain JWT for SPA" -c architectural

python3 scripts/mem learn "OAuth2 requires redirect URI registration" -t gotcha

# Compare with main
python3 scripts/mem branch compare main auth-experiment

# If satisfied, merge back
python3 scripts/mem branch merge auth-experiment --into main

# Switch back
python3 scripts/mem branch switch main
```

## 7. View in Web Dashboard

Open http://localhost:19876 in your browser.

Explore the tabs:
- **Dashboard** — overview cards, active decisions, key facts, goals, tasks
- **Decisions** — filter by status, see rationale and confidence
- **Facts** — pin/unpin, promote facts to decisions
- **Goals & Tasks** — track progress, update task status
- **Timeline** — chronological view of all memory operations
- **Branches** — visualize branches, compare, merge
- **Events** — agent event stream with filtering and replay

## 8. View Events and Agent Replay

```bash
# View recent events via CLI
python3 scripts/mem events

# Filter by type
python3 scripts/mem events --type agent_error

# Filter by agent
python3 scripts/mem events --agent claude-opus
```

In the web dashboard:
1. Click the **Events** tab
2. Use the filters: type, agent name, model, branch, failed-only
3. Click any event to see full details
4. Click **Agent Replay** buttons to see chronological execution flow

## 9. Use via Python Client

```python
from scripts.clients.universal_memory_client import UniversalMemoryClient

client = UniversalMemoryClient(
    base_url="http://localhost:19876",
    project_path="/my/project",
    cli_name="my-tool",
    agent_name="researcher",
    provider="openai",
    model_name="gpt-4"
)

# Get context (inject into your agent's system prompt)
ctx = client.get_context(mode="compact")
print(ctx)

# Store a decision
client.create_decision("Use GraphQL for API", category="architectural")

# Check health
health = client.get_health()
print(health)
```

## 10. Use via MCP (for Claude Desktop / Cursor)

```bash
# Start MCP server (requires memory API server running)
./scripts/run_mcp.sh
```

Configure in Claude Desktop (see `docs/examples/mcp_config_claude.json`):
```json
{
  "mcpServers": {
    "universal-memory": {
      "command": "python3",
      "args": ["mcp_server/server.py"],
      "env": {
        "MEMORY_BASE_URL": "http://localhost:19876",
        "MEMORY_PROJECT_PATH": "/my/project"
      }
    }
  }
}
```

Then use in Claude: "Use the memory tools to check context" or "Save this decision to memory".

## 11. Create a Checkpoint

```bash
# Save current state
python3 scripts/mem checkpoint create "Before refactor" -d "Stable state pre-auth changes"

# ... make changes ...

# Restore if needed
python3 scripts/mem checkpoint list
python3 scripts/mem checkpoint restore 1
```

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `mem dashboard` | CLI dashboard |
| `mem context --compact` | View compact context |
| `mem decide "..."` | Record decision |
| `mem learn "..."` | Learn fact |
| `mem goal "..."` | Set goal |
| `mem task "..."` | Create task |
| `mem resolve "err" "fix"` | Record resolution |
| `mem branch list` | List branches |
| `mem events` | View event stream |
| `mem health` | Health check |
| `mem timeline` | Timeline view |
