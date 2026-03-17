# EAN AgentOS — Instructions for Claude Code

## About This Project

EAN AgentOS is a persistent memory system for AI coding agents. It captures decisions, facts, errors, and solutions across sessions so agents don't repeat work.

## Memory System

This project has its own persistent memory in `global.db` (SQLite). **Do NOT confuse this with Claude Code's internal memory** (`/.claude/projects/.../memory/`).

### How to check memory

When the user asks about "memory" or "what do you remember", check the EAN AgentOS database:

```bash
# Check what's stored
python3 scripts/mem status
python3 scripts/mem decisions
python3 scripts/mem facts
python3 scripts/mem search "keyword"
python3 scripts/mem suggest "error message"
```

Or query directly:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('global.db')
for table in ['sessions', 'messages', 'decisions', 'learned_facts', 'error_resolutions']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    if count > 0: print(f'{table}: {count} rows')
conn.close()
"
```

### How to save to memory

```bash
# Save a decision
python3 scripts/mem decide -t "Decision title" -d "Why we decided this" -c "technical context"

# Save a fact
python3 scripts/mem learn "Important fact about this project"

# Search past solutions
python3 scripts/mem suggest "CORS error"
```

## Key Commands

| Command | What it does |
|---------|-------------|
| `mem status` | Overview of memory |
| `mem suggest "error"` | Find past solutions |
| `mem decisions` | List active decisions |
| `mem facts` | List learned facts |
| `mem search "keyword"` | Search across all memory |

## Important

- Memory is stored in `global.db` in the project root
- Hooks capture sessions, messages, and tool calls automatically
- Use `mem suggest` to find solutions from past sessions
- The web dashboard runs on port 19876: `python3 scripts/web_server.py`
