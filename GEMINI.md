# EAN AgentOS — Instructions for Gemini CLI

## About This Project

EAN AgentOS is a persistent memory system for AI coding agents. It captures decisions, facts, errors, and solutions across sessions so agents don't repeat work.

## Memory System

This project has persistent memory in `global.db` (SQLite). Use the `mem` CLI or query directly.

### Check memory
```bash
python3 scripts/mem status
python3 scripts/mem decisions
python3 scripts/mem facts
python3 scripts/mem suggest "error message"
python3 scripts/mem search "keyword"
```

### Save to memory
```bash
python3 scripts/mem decide -t "Decision title" -d "Why" -c "context"
python3 scripts/mem learn "Important fact"
```

### Query database directly
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('global.db')
for t in ['sessions','messages','decisions','learned_facts','error_resolutions']:
    c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    if c > 0: print(f'{t}: {c}')
conn.close()
"
```

## Key Feature: mem suggest

When you encounter an error, check if it was solved before:
```bash
python3 scripts/mem suggest "CORS error"
```

## Important

- Memory is in `global.db` in the project root
- Hooks capture sessions and tool calls automatically
- Web dashboard: `python3 scripts/web_server.py` → http://localhost:19876
