#!/usr/bin/env bash
# Hook wrapper: Stop
# Finalizes the session, extracts assistant responses from transcript.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export MEMORY_DIR="${MEMORY_DIR:-$PROJECT_ROOT}"

exec python3 "$PROJECT_ROOT/scripts/memory_daemon.py" session_end
