# Installation Guide

## Quick Start

```bash
# 1. Install integration for your agent
./ean-memory install claude    # Claude Code (MCP + config)
./ean-memory install gemini    # Gemini CLI (adapter + client)
./ean-memory install codex     # Codex CLI (adapter + client)

# 2. Start the memory server
./ean-memory start

# 3. Verify everything works
./ean-memory test
```

## Commands

### Install / Uninstall

```bash
./ean-memory install claude    # Configure MCP server in ~/.claude/.mcp.json
./ean-memory install gemini    # Copy adapter + client to ~/.gemini/
./ean-memory install codex     # Copy adapter + client to ~/.codex/

./ean-memory uninstall claude  # Remove MCP config (keeps data)
./ean-memory uninstall gemini  # Remove adapter files
./ean-memory uninstall codex   # Remove adapter files
```

### Runtime

```bash
./ean-memory start             # Start server on port 19876
./ean-memory start --port 8080 # Custom port
./ean-memory stop              # Stop server gracefully
./ean-memory status            # Show server, agents, integrations
```

### Diagnostics

```bash
./ean-memory test              # Quick check: server, API, DB, adapters
./ean-memory doctor            # Detailed: files, tables, config, agents
```

## What Each Installer Does

### Claude Code (`install claude`)

1. Backs up existing `~/.claude/.mcp.json`
2. Adds `universal-memory` MCP server entry
3. Verifies database and client availability

After install: restart Claude Code to detect the new MCP server.

### Gemini CLI (`install gemini`)

1. Copies `gemini_cli_adapter.py` to `~/.gemini/`
2. Copies `universal_memory_client.py` (dependency)
3. Creates `memory_config.json` with defaults

After install: reference the adapter in your Gemini instructions.

### Codex CLI (`install codex`)

1. Copies `codex_cli_adapter.py` to `~/.codex/`
2. Copies `universal_memory_client.py` (dependency)
3. Creates `memory_config.json` with defaults

After install: configure Codex to use the adapter.

## Safety

- All config modifications create timestamped backups
- Existing integrations are detected and not duplicated
- Uninstall removes integration files but keeps memory data
- The database is never deleted by uninstall

## Reverting

To undo an installation:

```bash
# Option 1: Use uninstall
./ean-memory uninstall claude

# Option 2: Restore backup manually
cp ~/.claude/.mcp.backup_YYYYMMDD_HHMMSS.json ~/.claude/.mcp.json
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Connection refused` | Run `./ean-memory start` first |
| Port already in use | `./ean-memory status` to check, or use `--port` |
| MCP not detected | Restart Claude Code after install |
| Adapter import error | Run `./ean-memory install gemini` to refresh files |

## Requirements

- Python 3.10+
- Flask (`pip install flask`)
- For MCP: `pip install mcp` (optional)
