#!/usr/bin/env python3
"""
Reasoning Trace — reconstituie lanțul operațional din agent_events.

Construiește graf de cauzalitate prin parent_event_id + adjacență temporală,
îmbogățește cu entități via related_table/related_id.

CLI: reasoning_trace.py session|agent|entity [args] [--branch X] [--limit N] [--json]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from v2_common import get_db, format_timestamp, truncate


# ============================================================
# CORE: Build trace from agent_events
# ============================================================

def _fetch_events(session_id=None, agent_name=None, branch=None, limit=100) -> List[Dict]:
    """Query agent_events with filters, return as list of dicts."""
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM agent_events WHERE 1=1"
    params = []

    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    if branch:
        query += " AND branch_name = ?"
        params.append(branch)

    query += f" ORDER BY created_at ASC LIMIT {min(limit, 500)}"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _enrich_event(event: Dict) -> Dict:
    """Enrich event with related entity data if related_table/related_id set."""
    table = event.get("related_table")
    rid = event.get("related_id")
    if not table or not rid:
        return event

    valid_tables = {
        "decisions": "SELECT id, title, description, category, status, confidence FROM decisions WHERE id=?",
        "learned_facts": "SELECT id, fact, fact_type, confidence, is_pinned, is_active FROM learned_facts WHERE id=?",
        "error_resolutions": "SELECT id, error_summary, resolution, resolution_type, worked, reuse_count FROM error_resolutions WHERE id=?",
        "goals": "SELECT id, title, description, priority, status FROM goals WHERE id=?",
        "tasks": "SELECT id, title, description, priority, status FROM tasks WHERE id=?",
    }

    if table not in valid_tables:
        return event

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(valid_tables[table], (rid,))
        row = cursor.fetchone()
        conn.close()
        if row:
            event["_entity"] = dict(row)
            event["_entity"]["_table"] = table
    except Exception:
        pass

    return event


def build_trace(session_id=None, agent_name=None, branch=None, limit=100) -> List[Dict]:
    """Build reasoning trace — enriched events with tree structure."""
    events = _fetch_events(session_id, agent_name, branch, limit)

    # Index by id for parent lookup
    by_id = {}
    for e in events:
        e = _enrich_event(e)
        e["_children"] = []
        by_id[e["id"]] = e

    # Build tree via parent_event_id
    roots = []
    for e in events:
        pid = e.get("parent_event_id")
        if pid and pid in by_id:
            by_id[pid]["_children"].append(e)
        else:
            roots.append(e)

    return roots


def find_trace_for_entity(table: str, entity_id: int) -> List[Dict]:
    """Reverse lookup: find the event that created an entity, then build full trace."""
    conn = get_db()
    cursor = conn.cursor()

    # Find the event that created this entity
    cursor.execute("""
        SELECT * FROM agent_events
        WHERE related_table = ? AND related_id = ?
        ORDER BY created_at ASC LIMIT 1
    """, (table, entity_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return []

    event = dict(row)

    # Walk up to root
    root_id = event["id"]
    visited = {root_id}
    current = event
    while current.get("parent_event_id"):
        pid = current["parent_event_id"]
        if pid in visited:
            break
        cursor.execute("SELECT * FROM agent_events WHERE id = ?", (pid,))
        parent = cursor.fetchone()
        if not parent:
            break
        current = dict(parent)
        root_id = current["id"]
        visited.add(root_id)

    # Now get all descendants from root's session
    session_id = current.get("session_id")
    agent_name = current.get("agent_name")
    conn.close()

    # Build full trace for that session/agent
    return build_trace(session_id=session_id, agent_name=agent_name)


# ============================================================
# FORMAT: Tree and flat views
# ============================================================

EVENT_ICONS = {
    "agent_started": "🚀", "agent_finished": "🏁", "agent_error": "💥",
    "context_requested": "📋", "context_received": "📦",
    "decision_created": "⚖️", "fact_created": "💡", "goal_created": "🎯",
    "task_created": "📝", "task_updated": "✏️", "resolution_created": "🔧",
    "branch_switched": "🔀", "branch_compared": "🔍", "branch_merged": "🔗",
    "checkpoint_created": "💾", "checkpoint_restored": "♻️",
    "api_call": "🌐", "ui_action": "🖱️", "learning_promoted": "🌟",
}


def format_trace_tree(roots: List[Dict], indent=0) -> str:
    """Format trace as indented tree."""
    lines = []
    for event in roots:
        icon = EVENT_ICONS.get(event.get("event_type", ""), "•")
        prefix = "  " * indent
        ts = format_timestamp(event.get("created_at"))
        title = truncate(event.get("title") or event.get("event_type", "?"), 60)
        status = event.get("status", "")
        success = "✅" if event.get("success_flag", 1) else "❌"

        line = f"{prefix}{icon} [{event['id']}] {ts} {title} ({status}) {success}"
        lines.append(line)

        # Show entity if enriched
        entity = event.get("_entity")
        if entity:
            tbl = entity.get("_table", "?")
            ename = entity.get("title") or entity.get("fact") or entity.get("error_summary") or "?"
            lines.append(f"{prefix}  └─ {tbl}#{entity['id']}: {truncate(ename, 50)}")

        # Recurse children
        children = event.get("_children", [])
        if children:
            lines.append(format_trace_tree(children, indent + 1))

    return "\n".join(lines)


def format_trace_flat(roots: List[Dict]) -> str:
    """Format trace as flat chronological list."""
    # Flatten all events
    all_events = []

    def _flatten(events):
        for e in events:
            all_events.append(e)
            _flatten(e.get("_children", []))

    _flatten(roots)
    all_events.sort(key=lambda x: x.get("created_at", ""))

    lines = []
    for e in all_events:
        icon = EVENT_ICONS.get(e.get("event_type", ""), "•")
        ts = format_timestamp(e.get("created_at"))
        title = truncate(e.get("title") or e.get("event_type", "?"), 50)
        agent = e.get("agent_name") or "?"
        success = "✅" if e.get("success_flag", 1) else "❌"
        lines.append(f"{icon} {ts} [{agent}] {title} {success}")

    return "\n".join(lines)


def trace_summary(roots: List[Dict]) -> Dict:
    """Compute summary statistics from trace."""
    all_events = []

    def _flatten(events):
        for e in events:
            all_events.append(e)
            _flatten(e.get("_children", []))

    _flatten(roots)

    total = len(all_events)
    success = sum(1 for e in all_events if e.get("success_flag", 1))
    failed = total - success

    type_counts = {}
    for e in all_events:
        t = e.get("event_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    agents = set(e.get("agent_name") for e in all_events if e.get("agent_name"))

    return {
        "total_events": total,
        "success": success,
        "failed": failed,
        "success_rate": round(success / total * 100, 1) if total else 0,
        "event_types": type_counts,
        "agents": sorted(agents),
        "entities_created": sum(1 for e in all_events if e.get("_entity")),
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Reasoning Trace — reconstituie lanțul operațional")
    sub = parser.add_subparsers(dest="command")

    # session
    p_session = sub.add_parser("session", help="Trace for a session")
    p_session.add_argument("session_id", help="Session ID")
    p_session.add_argument("--branch", help="Filter by branch")
    p_session.add_argument("--limit", type=int, default=100)
    p_session.add_argument("--json", action="store_true")
    p_session.add_argument("--flat", action="store_true", help="Flat chronological view")

    # agent
    p_agent = sub.add_parser("agent", help="Trace for an agent")
    p_agent.add_argument("agent_name", help="Agent name")
    p_agent.add_argument("--branch", help="Filter by branch")
    p_agent.add_argument("--limit", type=int, default=100)
    p_agent.add_argument("--json", action="store_true")
    p_agent.add_argument("--flat", action="store_true")

    # entity
    p_entity = sub.add_parser("entity", help="Trace for an entity")
    p_entity.add_argument("table", help="Table name (decisions, learned_facts, etc.)")
    p_entity.add_argument("entity_id", type=int, help="Entity ID")
    p_entity.add_argument("--json", action="store_true")
    p_entity.add_argument("--flat", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "session":
        roots = build_trace(session_id=args.session_id, branch=args.branch, limit=args.limit)
    elif args.command == "agent":
        roots = build_trace(agent_name=args.agent_name, branch=args.branch, limit=args.limit)
    elif args.command == "entity":
        roots = find_trace_for_entity(args.table, args.entity_id)
    else:
        parser.print_help()
        return

    if not roots:
        print("(niciun eveniment găsit)")
        return

    if args.json:
        summary = trace_summary(roots)
        # Serialize roots without _children circular refs
        def _clean(events):
            result = []
            for e in events:
                ec = {k: v for k, v in e.items() if k != "_children"}
                children = e.get("_children", [])
                if children:
                    ec["children"] = _clean(children)
                result.append(ec)
            return result

        output = {"trace": _clean(roots), "summary": summary}
        print(json.dumps(output, indent=2, default=str))
    else:
        summary = trace_summary(roots)
        print(f"\n🔍 REASONING TRACE ({args.command})")
        print("=" * 60)

        if getattr(args, "flat", False):
            print(format_trace_flat(roots))
        else:
            print(format_trace_tree(roots))

        print(f"\n--- Summary ---")
        print(f"  Events: {summary['total_events']} (✅ {summary['success']} / ❌ {summary['failed']})")
        print(f"  Success rate: {summary['success_rate']}%")
        print(f"  Agents: {', '.join(summary['agents']) or '—'}")
        print(f"  Entities created: {summary['entities_created']}")
        if summary["event_types"]:
            top = sorted(summary["event_types"].items(), key=lambda x: -x[1])[:5]
            print(f"  Top types: {', '.join(f'{t}({c})' for t, c in top)}")


if __name__ == "__main__":
    main()
