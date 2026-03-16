# Quick Start Guide

## Prerequisites

- Python 3.10+
- SQLite 3.35+ (with FTS5)
- Flask: `pip install flask`

## Installation

```bash
git clone <repo-url> ean-agentos
cd ean-agentos

# Install Python dependencies
pip install flask

# Initialize the database
python3 scripts/init_db.py
```

This creates `global.db` in the project root with all required tables.

## First Steps

### 1. Record your first decision

```bash
python3 scripts/mem decide "Use PostgreSQL for production" \
  -d "Better suited for concurrent writes and complex queries" \
  -c technical
```

### 2. Learn a fact

```bash
python3 scripts/mem learn "API rate limit is 100 requests per minute" \
  -t convention -c api
```

### 3. Set a goal

```bash
python3 scripts/mem goal "Complete user authentication module" -p high
```

### 4. Add tasks

```bash
python3 scripts/mem task "Implement JWT token generation" -p high --goal 1
python3 scripts/mem task "Write auth middleware" -p high --goal 1
python3 scripts/mem task "Add password hashing" -p medium --goal 1
```

### 5. View your memory context

```bash
# Compact view (default)
python3 scripts/mem context

# Full view with all details
python3 scripts/mem context --full

# JSON output for programmatic use
python3 scripts/mem context --json
```

### 6. Start the web dashboard

```bash
python3 scripts/web_server.py
```

Open http://localhost:19876 in your browser.

## Using with AI Agents

### Claude Code

Add to your project's `CLAUDE.md`:

```markdown
## Memory System

Before starting work, load context:
\`\`\`bash
python3 scripts/mem context --compact
\`\`\`

After making decisions:
\`\`\`bash
python3 scripts/mem decide "Description" -c technical
\`\`\`
```

### Via API

Start the server and point your agent at it:

```bash
python3 scripts/web_server.py &

# Your agent can now use:
curl http://localhost:19876/api/v1/context?project=/my/project
```

### Via Python Client

```python
from scripts.clients.universal_memory_client import UniversalMemoryClient

client = UniversalMemoryClient(
    base_url="http://localhost:19876",
    project_path="/my/project",
    cli_name="my-agent",
    agent_name="coder",
    provider="anthropic",
    model_name="claude-opus-4"
)

# Store knowledge
client.create_decision("Use async handlers", category="technical")
client.create_fact("Max connections is 100", fact_type="convention")

# Retrieve context
ctx = client.get_context(mode="compact")
print(ctx["context_text"])
```

## Working with Branches

```bash
# Create a branch for experimental work
python3 scripts/mem branch create experiment-redis -d "Evaluating Redis integration"

# Switch to it
python3 scripts/mem branch switch experiment-redis

# Work normally — entities go to this branch
python3 scripts/mem decide "Use Redis for session cache" -c technical
python3 scripts/mem learn "Redis needs port 6379 open" -t technical

# Compare with main
python3 scripts/mem branch compare main experiment-redis

# Happy with results? Merge back
python3 scripts/mem branch merge experiment-redis --into main

# Switch back to main
python3 scripts/mem branch switch main
```

## Setting Intent

Intent optimizes which entities appear in context:

```bash
python3 scripts/mem intent set debugging
# Now context prioritizes error-related knowledge
```

Valid intents: `debugging`, `feature`, `refactor`, `deploy`, `docs`, `review`, `explore`

## Next Steps

- [API Reference](api.md) — full endpoint documentation
- [Architecture](architecture.md) — system design
- [Branches](branches.md) — branching model details
- [Adapters](adapters.md) — integrate with other AI tools
- [Configuration](configuration.md) — environment variables and settings
