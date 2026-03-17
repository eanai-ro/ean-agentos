# ⚡ EAN AgentOS — Quick Start Guide

Get started in 60 seconds.

## Step 0: Prerequisites

**Install at least one AI coding CLI first:**

```bash
# Claude Code (recommended)
npm install -g @anthropic-ai/claude-code

# Or Gemini CLI
npm install -g @anthropic-ai/gemini-cli

# Or Codex CLI
npm install -g @openai/codex
```

Without a CLI, EAN AgentOS has nothing to capture. Install one, then:

## Step 1: Install

```bash
git clone https://github.com/eanai-ro/ean-agentos.git
cd ean-agentos
./install.sh
```

The installer will:
- Install Python dependencies
- Create the database
- Set up the `mem` command
- Detect and configure your AI CLIs (Claude Code, Gemini, Codex, Kimi)

## Step 2: Try it

### Find past solutions
```bash
mem suggest "CORS error"
mem suggest "ModuleNotFoundError"
mem suggest "docker permission denied"
```

### Search your memory
```bash
mem search "authentication"
mem search "database"
```

### See what's stored
```bash
mem decisions          # Technical decisions
mem facts              # Learned facts
mem status             # Memory overview
```

### Experience graph
```bash
mem graph stats        # Problem → solution connections
```

## Step 3: Start coding with your AI

Just use your AI CLI as normal (Claude Code, Gemini CLI, etc.). EAN AgentOS hooks capture everything automatically:

- Decisions you make
- Errors you encounter
- Solutions that worked
- Facts about your project

Next session, your AI agent has context from all previous sessions.

## Step 4: Web Dashboard

```bash
python3 scripts/web_server.py
# Open: http://localhost:19876
```

See your memory visually: decisions, facts, timeline, errors, health.

## How it works

```
Your AI CLI (Claude/Gemini/Codex/Kimi)
        │
        │ hooks capture decisions, errors, solutions
        ▼
   ┌──────────┐
   │ global.db │ ← persistent SQLite database
   └──────────┘
        │
   ┌────┼────┐
   ▼    ▼    ▼
  mem  MCP  Dashboard
  CLI  Server  Web UI
```

1. **You code** with your AI agent as usual
2. **Hooks capture** everything important automatically
3. **Next session**, your agent gets context from memory
4. **`mem suggest`** finds past solutions instantly

## What's free

Everything in this repo:
- Persistent memory across sessions
- `mem suggest` — never solve the same bug twice
- Knowledge extraction with pattern detection
- Experience graph, cognitive search
- Branch-aware memory
- Backup & recovery
- Web dashboard + MCP server + CLI

## Need more?

[Pro adds multi-agent orchestration](README.md#free-vs-pro--what-you-get) — coordinate Claude + Gemini + Codex + Kimi on the same project. Contact: ean@eanai.ro
