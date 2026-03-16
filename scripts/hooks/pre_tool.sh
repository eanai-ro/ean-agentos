#!/usr/bin/env bash
# Hook wrapper: PreToolUse (Edit|Write|MultiEdit)
# Backs up files before they are modified.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export MEMORY_DIR="${MEMORY_DIR:-$PROJECT_ROOT}"
mkdir -p "$MEMORY_DIR/file_versions"

exec python3 "$PROJECT_ROOT/scripts/memory_daemon.py" pre_tool
