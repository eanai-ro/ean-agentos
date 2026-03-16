#!/usr/bin/env bash
# Hook wrapper: UserPromptSubmit
# Saves the user's prompt to DB automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export MEMORY_DIR="${MEMORY_DIR:-$PROJECT_ROOT}"

exec python3 "$PROJECT_ROOT/scripts/memory_daemon.py" user_prompt
