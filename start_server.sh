#!/bin/bash
# EAN AgentOS — Memory Server + Services Autostart
# Pornește automat: web/API server, Codex watcher
# Usage: bash start_server.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Start web/API server (MCP + dashboard) if not running
if ! curl -s http://localhost:19876/ > /dev/null 2>&1; then
    nohup python3 scripts/web_server.py --host 127.0.0.1 --port 19876 > /dev/null 2>&1 &
    echo "  Started: web server on port 19876"
else
    echo "  Already running: web server on port 19876"
fi

# Start Codex rollout watcher if Codex is installed
if [ -f scripts/codex_rollout_watcher.py ] && command -v codex &>/dev/null; then
    if ! pgrep -f "codex_rollout_watcher" > /dev/null 2>&1; then
        nohup python3 scripts/codex_rollout_watcher.py --watch --interval 10 > /dev/null 2>&1 &
        echo "  Started: Codex rollout watcher (interval 10s)"
    else
        echo "  Already running: Codex rollout watcher"
    fi
fi
