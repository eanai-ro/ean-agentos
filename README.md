# 🧠 EAN AgentOS

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Tests: 57 passing](https://img.shields.io/badge/Tests-57%20passing-brightgreen.svg)](test_full.sh)
[![CLIs: Claude · Gemini · Codex · Kimi](https://img.shields.io/badge/CLIs-Claude%20·%20Gemini%20·%20Codex%20·%20Kimi-purple.svg)](#supported-clis)

### Persistent Memory for AI Coding Agents

**Never solve the same bug twice.**

---

## What does EAN AgentOS do?

Your AI agent forgets everything between sessions. EAN AgentOS gives it permanent memory.

### Demo: "Never solve the same bug twice"

```bash
# Session 1: You fix a CORS error
#   Agent saves: error + solution + context

# Session 2 (3 months later): Same CORS error appears
$ mem suggest "CORS error"

💡 SOLUTIONS FOR: CORS error
══════════════════════════════════════════════════════════════

  1. [92pts] ✅ CORS error: blocked by CORS policy
     Solution: Add flask-cors middleware and configure CORS(app)
     Code:     pip install flask-cors && CORS(app)
     Match: 100% | Confidence: 92% | Agent: claude-code

# You also forgot how you fixed Docker permissions last month?
$ mem suggest "docker permission denied"

💡 SOLUTIONS FOR: docker permission denied
══════════════════════════════════════════════════════════════

  1. [87pts] ✅ docker.sock permission denied
     Solution: Add user to docker group and restart session
     Code:     sudo usermod -aG docker $USER && newgrp docker
     Match: 100% | Confidence: 87% | Agent: kimi-cli
```

**Works with Claude Code, Gemini CLI, Codex CLI, and Kimi CLI.** All agents share the same memory.

---

## Features

| Feature | Description |
|---------|-------------|
| 🔁 **Persistent Memory** | Decisions, facts, goals, tasks — persisted across sessions |
| 💡 **`mem suggest`** | Find past solutions: *"Never solve the same bug twice"* |
| 🧬 **Knowledge Extraction** | Auto-extract patterns, scoring, deduplication |
| 🔍 **Cognitive Search** | Search across resolutions, decisions, facts, messages |
| 🌳 **Memory Branches** | Branch-aware memory per git branch |
| 📊 **Experience Graph** | Problem → solution → outcome graph |
| 🔄 **Cross-Agent Learning** | Agents learn from each other's experience |
| 💾 **Backup & Recovery** | Auto backup, restore, integrity verification |
| 🖥️ **Web Dashboard** | Visualize decisions, facts, timeline, health |
| 🔌 **MCP Server** | Native integration with Claude Code + other CLIs |

---

## Quick Install

```bash
git clone https://github.com/eanai-ro/ean-agentos.git
cd ean-agentos
./install.sh
```

The installer auto-detects installed CLIs and lets you choose which to integrate.

### Or manually:

```bash
pip install flask flask-cors
python3 scripts/init_db.py
python3 scripts/ean_memory.py install claude   # or gemini, codex
```

---

## Usage

### Never solve the same bug twice

```bash
mem suggest "CORS error"
```

```
💡 SOLUTIONS FOR: CORS error
══════════════════════════════════════════════════════════════

  1. [92pts] ✅ error_resolutions#5
     Problem:  CORS error: blocked by CORS policy
     Solution: Add flask-cors middleware: CORS(app)
     Match: 100% | Confidence: 92% | Agent: claude-code
```

### Key Commands

```bash
mem suggest "error message"   # Find past solutions
mem search "keyword"          # Search all memory
mem decisions                 # View active decisions
mem status                    # Memory status
mem graph stats               # Experience graph stats
```

### Web Dashboard

```bash
python3 scripts/web_server.py
# Open: http://localhost:19876
```

### MCP Server (for Claude Code)

Configured automatically during install. Your AI agent receives context from permanent memory at every session.

---

## Supported CLIs

| CLI | Integration | Install Command |
|-----|-------------|-----------------|
| **Claude Code** | Hooks + MCP Server | `python3 scripts/ean_memory.py install claude` |
| **Gemini CLI** | Hooks | `python3 scripts/ean_memory.py install gemini` |
| **Codex CLI** | Hooks | `python3 scripts/ean_memory.py install codex` |
| **Kimi CLI** | MCP Server | Manual config |

All CLIs read and write to the same database. What one agent learns is available to all.

---

## How It Works

```
  Claude Code    Gemini CLI    Codex CLI    Kimi CLI
       │              │             │            │
       │     auto-capture (hooks)                │
       └──────────────┬─────────────┬────────────┘
                      │             │
                      ▼             ▼
               ┌──────────────────────────┐
               │       global.db          │
               │                          │
               │  decisions               │
               │  learned_facts           │
               │  error_resolutions       │
               │  experience_graph        │
               │  solution_index          │
               │  ...49 tables            │
               └──────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      REST API    MCP Server    CLI (mem)
       Dashboard   (Claude)     (terminal)
```

1. **Capture**: Hooks auto-capture decisions, errors, solutions from AI sessions
2. **Structure**: Knowledge Extractor classifies, scores, and deduplicates
3. **Retrieve**: At each new session, the agent receives relevant context
4. **Learn**: Solution Index + Experience Graph = memory gets smarter

---

## Project Structure

```
ean-agentos/
├── scripts/
│   ├── mem                      # Main CLI
│   ├── v2_common.py             # Core DB + utilities
│   ├── init_db.py               # DB initialization
│   ├── solution_index.py        # 💡 mem suggest
│   ├── knowledge_extractor.py   # Auto-extraction
│   ├── context_builder_v2.py    # LLM context builder
│   ├── experience_graph.py      # Experience graph
│   ├── search_memory.py         # Unified search
│   ├── backup_manager.py        # Backup & restore
│   ├── web_server.py            # Web dashboard
│   ├── ean_memory.py            # Installer
│   └── ...
├── web/                         # Dashboard HTML/JS/CSS
├── mcp_server/                  # MCP for Claude Code
├── mcp-server/                  # MCP for Kimi CLI
├── migrations/                  # DB schema
├── install.sh                   # Interactive installer
├── test_full.sh                 # Test suite (57 tests)
└── Dockerfile                   # Test container
```

---

## Testing

```bash
./test_full.sh
```

57 tests covering: structure, database, imports, license gate, mem suggest, experience graph, context builder, search, web server, MCP, DB integrity, backup.

---

## EAN AgentOS Pro 🔒

The Pro version adds **multi-agent orchestration** — coordinating multiple AI CLIs on the same project:

| Pro Feature | Description |
|------------|-------------|
| 🤖 **Multi-Agent Orchestration** | Projects with tasks, lease-based ownership |
| 🗣️ **AI Deliberation** | Structured multi-round sessions with synthesis |
| 🚀 **CLI Launcher** | Programmatically launch Claude/Gemini/Codex/Kimi |
| 🔄 **Auto-Pipeline** | Task chaining, auto-review, conflict resolution |
| 🧠 **Intelligence Layer** | Capability scoring, weighted voting, skill learning |
| 📼 **Replay System** | Complete project + deliberation timelines |
| 📋 **Peer Review** | Formal verdicts, auto-fix |

**Details**: [ean@eanai.ro](mailto:ean@eanai.ro)

---

## License

MIT — see [LICENSE](LICENSE)

---

## About

Built by **EAN** (Encean Alexandru Nicolae) 🇷🇴

*Persistent memory for AI agents. Don't forget. Don't repeat. Learn.*
