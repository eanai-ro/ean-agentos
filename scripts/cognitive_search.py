#!/usr/bin/env python3
"""
Cognitive Search — Unified search across raw + structured memory.

Caută coerent în toate sursele de date:
  - messages (raw conversation)
  - tool_calls (raw tool usage)
  - bash_history (raw commands)
  - errors_solutions (raw errors)
  - decisions (structured)
  - learned_facts (structured)
  - goals / tasks (structured)
  - error_resolutions (structured)
  - agent_events (structured)

Usage:
    cognitive_search.py "query"                   # Search all sources
    cognitive_search.py "query" --scope raw        # Only raw data
    cognitive_search.py "query" --scope structured  # Only structured
    cognitive_search.py "query" --scope errors      # Only errors+resolutions
    cognitive_search.py "query" -l 20              # Limit results
    cognitive_search.py "query" --json             # JSON output
"""

import sys
import os
import json
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

# DB path
try:
    from v2_common import resolve_db_path
    DB_PATH = str(resolve_db_path())
except ImportError:
    DB_PATH = os.environ.get("MEMORY_DB_PATH",
        str(Path.home() / ".claude" / "memory" / "global.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ts(row, key="timestamp"):
    """Extract and format timestamp."""
    val = row[key] if key in row.keys() else None
    if not val:
        return ""
    if isinstance(val, str):
        return val[:19]
    return str(val)[:19]


def _trunc(text, maxlen=120):
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) > maxlen:
        return text[:maxlen] + "..."
    return text


# === SEARCH SOURCES ===

def search_messages(cursor, query, limit):
    """Search raw messages using FTS5."""
    try:
        cursor.execute("""
            SELECT m.id, m.timestamp, m.role, m.content, m.session_id, m.project_path
            FROM messages_fts fts
            JOIN messages m ON m.id = fts.rowid
            WHERE messages_fts MATCH ?
            ORDER BY m.id DESC
            LIMIT ?
        """, (query, limit))
        return [{"source": "message", "id": r["id"], "timestamp": _ts(r),
                 "role": r["role"], "text": _trunc(r["content"], 150),
                 "session": r["session_id"], "project": r["project_path"]}
                for r in cursor.fetchall()]
    except Exception:
        # Fallback to LIKE if FTS fails
        cursor.execute("""
            SELECT id, timestamp, role, content, session_id, project_path
            FROM messages WHERE content LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (f"%{query}%", limit))
        return [{"source": "message", "id": r["id"], "timestamp": _ts(r),
                 "role": r["role"], "text": _trunc(r["content"], 150),
                 "session": r["session_id"], "project": r["project_path"]}
                for r in cursor.fetchall()]


def search_tool_calls(cursor, query, limit):
    """Search raw tool calls using FTS5."""
    try:
        cursor.execute("""
            SELECT t.id, t.timestamp, t.tool_name, t.tool_input, t.tool_result,
                   t.exit_code, t.success, t.error_message, t.session_id, t.project_path
            FROM tool_calls_fts fts
            JOIN tool_calls t ON t.id = fts.rowid
            WHERE tool_calls_fts MATCH ?
            ORDER BY t.id DESC
            LIMIT ?
        """, (query, limit))
        results = []
        for r in cursor.fetchall():
            text = r["tool_input"] or r["tool_result"] or ""
            results.append({"source": "tool_call", "id": r["id"], "timestamp": _ts(r),
                            "tool": r["tool_name"], "text": _trunc(text, 150),
                            "success": bool(r["success"]),
                            "error": _trunc(r["error_message"], 80) if r["error_message"] else None,
                            "session": r["session_id"]})
        return results
    except Exception:
        cursor.execute("""
            SELECT id, timestamp, tool_name, tool_input, tool_result, success, error_message, session_id
            FROM tool_calls WHERE tool_input LIKE ? OR tool_result LIKE ? OR error_message LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        results = []
        for r in cursor.fetchall():
            text = r["tool_input"] or r["tool_result"] or ""
            results.append({"source": "tool_call", "id": r["id"], "timestamp": _ts(r),
                            "tool": r["tool_name"], "text": _trunc(text, 150),
                            "success": bool(r["success"]),
                            "error": _trunc(r["error_message"], 80) if r["error_message"] else None,
                            "session": r["session_id"]})
        return results


def search_bash_history(cursor, query, limit):
    """Search bash command history using FTS5."""
    try:
        cursor.execute("""
            SELECT b.id, b.timestamp, b.command, b.exit_code, b.output,
                   b.error_output, b.working_directory, b.session_id
            FROM bash_history_fts fts
            JOIN bash_history b ON b.id = fts.rowid
            WHERE bash_history_fts MATCH ?
            ORDER BY b.id DESC
            LIMIT ?
        """, (query, limit))
        return [{"source": "bash", "id": r["id"], "timestamp": _ts(r),
                 "command": _trunc(r["command"], 100),
                 "exit_code": r["exit_code"],
                 "output": _trunc(r["output"], 80) if r["output"] else None,
                 "error": _trunc(r["error_output"], 80) if r["error_output"] else None,
                 "cwd": r["working_directory"]}
                for r in cursor.fetchall()]
    except Exception:
        cursor.execute("""
            SELECT id, timestamp, command, exit_code, output, error_output, working_directory, session_id
            FROM bash_history WHERE command LIKE ? OR output LIKE ? OR error_output LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        return [{"source": "bash", "id": r["id"], "timestamp": _ts(r),
                 "command": _trunc(r["command"], 100),
                 "exit_code": r["exit_code"],
                 "output": _trunc(r["output"], 80) if r["output"] else None,
                 "error": _trunc(r["error_output"], 80) if r["error_output"] else None,
                 "cwd": r["working_directory"]}
                for r in cursor.fetchall()]


def search_errors_raw(cursor, query, limit):
    """Search raw errors from errors_solutions."""
    cursor.execute("""
        SELECT id, error_type, error_message, file_path, language, framework,
               solution, solution_worked, resolved, created_at, resolved_at,
               project_path, source
        FROM errors_solutions
        WHERE error_message LIKE ? OR solution LIKE ? OR error_type LIKE ?
           OR file_path LIKE ? OR tags LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit))
    return [{"source": "error_raw", "id": r["id"], "timestamp": _ts(r, "created_at"),
             "error_type": r["error_type"],
             "error": _trunc(r["error_message"], 120),
             "solution": _trunc(r["solution"], 120) if r["solution"] else None,
             "worked": bool(r["solution_worked"]) if r["solution_worked"] is not None else None,
             "resolved": bool(r["resolved"]),
             "file": r["file_path"], "language": r["language"]}
            for r in cursor.fetchall()]


def search_decisions(cursor, query, limit):
    """Search structured decisions."""
    cursor.execute("""
        SELECT id, title, description, category, confidence, status, created_at
        FROM decisions
        WHERE title LIKE ? OR description LIKE ? OR rationale LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
    return [{"source": "decision", "id": r["id"], "timestamp": _ts(r, "created_at"),
             "text": r["title"], "detail": _trunc(r["description"], 80),
             "category": r["category"], "status": r["status"]}
            for r in cursor.fetchall()]


def search_facts(cursor, query, limit):
    """Search structured facts."""
    cursor.execute("""
        SELECT id, fact, fact_type, category, confidence, is_pinned, created_at
        FROM learned_facts
        WHERE fact LIKE ? OR category LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))
    return [{"source": "fact", "id": r["id"], "timestamp": _ts(r, "created_at"),
             "text": r["fact"], "type": r["fact_type"],
             "pinned": bool(r["is_pinned"])}
            for r in cursor.fetchall()]


def search_goals_tasks(cursor, query, limit):
    """Search structured goals and tasks."""
    results = []
    cursor.execute("""
        SELECT id, title, description, priority, status, created_at
        FROM goals WHERE title LIKE ? OR description LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))
    for r in cursor.fetchall():
        results.append({"source": "goal", "id": r["id"], "timestamp": _ts(r, "created_at"),
                        "text": r["title"], "priority": r["priority"], "status": r["status"]})

    cursor.execute("""
        SELECT id, title, description, priority, status, created_at
        FROM tasks WHERE title LIKE ? OR description LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))
    for r in cursor.fetchall():
        results.append({"source": "task", "id": r["id"], "timestamp": _ts(r, "created_at"),
                        "text": r["title"], "priority": r["priority"], "status": r["status"]})
    return results


def search_resolutions(cursor, query, limit):
    """Search structured error resolutions."""
    cursor.execute("""
        SELECT id, error_summary, resolution, resolution_type, model_used,
               provider, agent_name, worked, reuse_count, created_at
        FROM error_resolutions
        WHERE error_summary LIKE ? OR resolution LIKE ? OR resolution_code LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
    return [{"source": "resolution", "id": r["id"], "timestamp": _ts(r, "created_at"),
             "error": _trunc(r["error_summary"], 80),
             "resolution": _trunc(r["resolution"], 100),
             "type": r["resolution_type"],
             "model": r["model_used"], "worked": bool(r["worked"]) if r["worked"] is not None else None,
             "reuse_count": r["reuse_count"]}
            for r in cursor.fetchall()]


def search_events(cursor, query, limit):
    """Search agent events."""
    cursor.execute("""
        SELECT id, event_type, title, agent_name, model_name, provider,
               success_flag, created_at
        FROM agent_events
        WHERE title LIKE ? OR event_type LIKE ? OR agent_name LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
    return [{"source": "event", "id": r["id"], "timestamp": _ts(r, "created_at"),
             "event_type": r["event_type"], "text": r["title"],
             "agent": r["agent_name"], "model": r["model_name"]}
            for r in cursor.fetchall()]


# === MAIN SEARCH ===

SCOPE_MAP = {
    "all": ["messages", "tool_calls", "bash", "errors_raw", "decisions",
            "facts", "goals_tasks", "resolutions", "events"],
    "raw": ["messages", "tool_calls", "bash", "errors_raw"],
    "structured": ["decisions", "facts", "goals_tasks", "resolutions", "events"],
    "errors": ["errors_raw", "resolutions"],
}

SEARCH_FNS = {
    "messages": search_messages,
    "tool_calls": search_tool_calls,
    "bash": search_bash_history,
    "errors_raw": search_errors_raw,
    "decisions": search_decisions,
    "facts": search_facts,
    "goals_tasks": search_goals_tasks,
    "resolutions": search_resolutions,
    "events": search_events,
}

SOURCE_LABELS = {
    "message": "💬 Message",
    "tool_call": "🔧 Tool Call",
    "bash": "⌨️  Bash",
    "error_raw": "🔴 Error",
    "decision": "📋 Decision",
    "fact": "📚 Fact",
    "goal": "🎯 Goal",
    "task": "📝 Task",
    "resolution": "✅ Resolution",
    "event": "⚡ Event",
}


def unified_search(query, scope="all", limit=30):
    """Run unified search across all sources."""
    conn = get_db()
    cursor = conn.cursor()

    sources = SCOPE_MAP.get(scope, SCOPE_MAP["all"])
    per_source_limit = max(5, limit // len(sources) + 2)

    all_results = []
    source_counts = {}

    for source_name in sources:
        fn = SEARCH_FNS[source_name]
        try:
            results = fn(cursor, query, per_source_limit)
            all_results.extend(results)
            if results:
                # Count by actual source type
                for r in results:
                    src = r["source"]
                    source_counts[src] = source_counts.get(src, 0) + 1
        except Exception:
            pass  # Skip sources that fail (e.g., missing tables)

    conn.close()

    # Sort by timestamp descending (most recent first)
    def sort_key(r):
        ts = r.get("timestamp", "")
        return ts if ts else "0000"

    all_results.sort(key=sort_key, reverse=True)

    return all_results[:limit], source_counts


def print_results(results, source_counts, query, scope):
    """Pretty-print search results."""
    if not results:
        print(f"\n  Niciun rezultat pentru: '{query}' (scope: {scope})")
        return

    print(f"\n{'='*80}")
    print(f"  UNIFIED SEARCH: '{query}' (scope: {scope})")
    print(f"  {len(results)} rezultate din {len(source_counts)} surse")
    # Source breakdown
    parts = [f"{SOURCE_LABELS.get(k, k)}: {v}" for k, v in sorted(source_counts.items())]
    if parts:
        print(f"  [{', '.join(parts)}]")
    print(f"{'='*80}\n")

    for r in results:
        label = SOURCE_LABELS.get(r["source"], r["source"])
        ts = r.get("timestamp", "")[:16]

        # Format based on source type
        if r["source"] == "message":
            role = r.get("role", "?")
            print(f"  {label} [{ts}] ({role})")
            print(f"    {r['text']}")

        elif r["source"] == "tool_call":
            tool = r.get("tool", "?")
            success = "✅" if r.get("success") else "❌"
            print(f"  {label} [{ts}] {tool} {success}")
            print(f"    {r['text']}")
            if r.get("error"):
                print(f"    ⚠️ {r['error']}")

        elif r["source"] == "bash":
            exit_code = r.get("exit_code", "?")
            icon = "✅" if exit_code == 0 else f"❌({exit_code})"
            print(f"  {label} [{ts}] {icon}")
            print(f"    $ {r['command']}")
            if r.get("error"):
                print(f"    ⚠️ {r['error']}")

        elif r["source"] == "error_raw":
            worked = "✅" if r.get("worked") else ("❌" if r.get("worked") is False else "?")
            resolved = "RESOLVED" if r.get("resolved") else "OPEN"
            print(f"  {label} [{ts}] [{resolved}] {r.get('error_type', '?')}")
            print(f"    {r['error']}")
            if r.get("solution"):
                print(f"    → Soluție ({worked}): {r['solution']}")

        elif r["source"] == "decision":
            print(f"  {label} [{ts}] [{r.get('category', '?')}] {r.get('status', '?')}")
            print(f"    {r['text']}")
            if r.get("detail"):
                print(f"    {r['detail']}")

        elif r["source"] == "fact":
            pin = "📌" if r.get("pinned") else ""
            print(f"  {label} [{ts}] [{r.get('type', '?')}] {pin}")
            print(f"    {r['text']}")

        elif r["source"] in ("goal", "task"):
            print(f"  {label} [{ts}] [{r.get('priority', '?')}] {r.get('status', '?')}")
            print(f"    {r['text']}")

        elif r["source"] == "resolution":
            worked = "✅" if r.get("worked") else ("❌" if r.get("worked") is False else "?")
            model = r.get("model") or "?"
            print(f"  {label} [{ts}] [{r.get('type', '?')}] {worked} (model: {model})")
            print(f"    Eroare: {r['error']}")
            print(f"    Soluție: {r['resolution']}")

        elif r["source"] == "event":
            print(f"  {label} [{ts}] {r.get('event_type', '?')} ({r.get('agent', '?')})")
            if r.get("text"):
                print(f"    {r['text']}")

        print()


def main():
    parser = argparse.ArgumentParser(description="Unified Cognitive Search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--scope", "-s", choices=["all", "raw", "structured", "errors"],
                        default="all", help="Search scope (default: all)")
    parser.add_argument("-l", "--limit", type=int, default=30, help="Max results (default: 30)")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    results, counts = unified_search(args.query, scope=args.scope, limit=args.limit)

    if args.json:
        print(json.dumps({"query": args.query, "scope": args.scope,
                           "total": len(results), "source_counts": counts,
                           "results": results}, indent=2, default=str))
    else:
        print_results(results, counts, args.query, args.scope)


if __name__ == "__main__":
    main()
