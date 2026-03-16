# Writing Adapters

Adapters connect AI CLI tools to Universal Agent Memory. An adapter translates between the tool's hook/plugin system and the memory API.

## How Adapters Work

```
AI CLI Tool (Gemini, Codex, etc.)
    │
    ▼
Adapter (translates to API calls)
    │
    ▼
Universal Memory API (/api/v1/*)
    │
    ▼
SQLite Database
```

## Included Adapters

### Gemini CLI Adapter

**Location:** `scripts/adapters/gemini_cli_adapter.py`

Integrates with Google's Gemini CLI by:
1. Loading memory context on session start
2. Reporting decisions and facts back to memory
3. Tracking agent activity

### Codex CLI Adapter

**Location:** `scripts/adapters/codex_cli_adapter.py`

Integrates with OpenAI's Codex CLI with the same pattern.

## Writing a New Adapter

### Step 1: Use UniversalMemoryClient

```python
from scripts.clients.universal_memory_client import UniversalMemoryClient

client = UniversalMemoryClient(
    base_url="http://localhost:19876",
    project_path="/path/to/project",
    cli_name="my-tool",           # Your CLI tool's name
    agent_name="default",         # Agent identity within the tool
    provider="my-provider",       # AI provider (openai, google, etc.)
    model_name="model-id"         # Model being used
)
```

### Step 2: Load Context on Session Start

```python
def on_session_start():
    """Call this when your agent starts a new session."""
    ctx = client.get_context(mode="compact")
    if ctx and ctx.get("ok"):
        # Inject ctx["context_text"] into your agent's system prompt
        system_prompt = ctx["context_text"]
        return system_prompt
    return ""
```

### Step 3: Store Knowledge During Work

```python
def on_decision_made(title, description, category="technical"):
    """Call this when the agent makes an architectural decision."""
    client.create_decision(title, description=description, category=category)

def on_fact_learned(fact, fact_type="observation"):
    """Call this when the agent learns something new."""
    client.create_fact(fact, fact_type=fact_type)

def on_error_resolved(error, solution, worked=True):
    """Call this when an error is resolved."""
    client.create_resolution(error, solution, worked=worked)
```

### Step 4: Track Activity

```python
def on_action(action_type, summary, success=True):
    """Call this to log agent activity."""
    client.log_activity(summary, payload={
        "action_type": action_type,
        "success": success
    })
```

## Client API Reference

### UniversalMemoryClient Methods

```python
# Decisions
client.create_decision(title, description=None, category="technical",
                       confidence="high", rationale=None)

# Facts
client.create_fact(fact, fact_type="technical", category=None,
                   confidence="high", source=None)

# Goals
client.create_goal(title, description=None, priority="medium",
                   target_date=None)

# Tasks
client.create_task(title, description=None, priority="medium",
                   goal_id=None)

# Error Resolutions
client.create_resolution(error_summary, resolution, worked=True,
                         resolution_type="fix")

# Context
client.get_context(mode="compact", intent=None)

# Activity
client.log_activity(summary, payload=None)

# Events
client.send_event(event_type, title=None, payload=None)

# Low-level
client._get(path, params)   # GET request
client._post(path, data)    # POST request
```

## Integration Patterns

### Pattern 1: System Prompt Injection

Load context at session start and prepend to system prompt:

```python
context = client.get_context(mode="compact")
system_prompt = f"""You are an AI coding assistant.

## Project Memory
{context['context_text']}

## Instructions
..."""
```

### Pattern 2: Hook-Based

If your tool supports hooks (pre/post actions):

```python
# Pre-session hook
def pre_session_hook():
    ctx = client.get_context()
    inject_to_agent(ctx["context_text"])

# Post-action hook
def post_action_hook(action_type, result):
    if action_type == "decision":
        client.create_decision(result["title"], category=result.get("category"))
```

### Pattern 3: Periodic Sync

For tools without hooks, poll periodically:

```python
import time

while agent_is_running:
    # Check for new context every 5 minutes
    ctx = client.get_context(mode="delta")
    if ctx.get("counts", {}).get("decisions", 0) > 0:
        update_agent_context(ctx)
    time.sleep(300)
```

## Branch-Aware Adapters

To support memory branches:

```python
# Switch branch before loading context
client._post("/api/branches/switch", {"branch": "feature-x"})

# Get branch-specific context
ctx = client.get_context(branch="feature-x")

# Store on specific branch
client.create_decision("Use Redis")
```
