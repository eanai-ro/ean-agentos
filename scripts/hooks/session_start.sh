#!/usr/bin/env bash
# Hook wrapper: SessionStart
# Called by Claude Code at the start of each session.
# Sets MEMORY_DIR so memory_daemon.py writes to ean-agentos's own DB.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export MEMORY_DIR="${MEMORY_DIR:-$PROJECT_ROOT}"
mkdir -p "$MEMORY_DIR/sessions"

exec python3 "$PROJECT_ROOT/scripts/memory_daemon.py" session_start
