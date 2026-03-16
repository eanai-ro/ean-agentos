#!/usr/bin/env bash
# Hook wrapper: PostToolUse (.*)
# Saves every tool call result to DB. Detects errors automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export MEMORY_DIR="${MEMORY_DIR:-$PROJECT_ROOT}"

exec python3 "$PROJECT_ROOT/scripts/memory_daemon.py" post_tool
