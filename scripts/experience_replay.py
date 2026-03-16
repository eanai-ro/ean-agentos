#!/usr/bin/env python3
"""
Experience Replay — replay bogat care intercalează agent_events + entități cronologic.

Replay per sesiune, agent sau branch, cu merge/dedup pentru entități referite de events.

CLI: experience_replay.py session|agent|branch [args] [--days N] [--limit N] [--json]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from v2_common import get_db, format_timestamp, truncate, BRANCH_ENTITY_TABLES


# ============================================================
# ENTITY FETCHERS
# ============================================================

ENTITY_QUERIES = {
    "decisions": """
        SELECT id, title, description, category, status, confidence,
               created_at, created_by, branch, agent_name as _agent,
               is_global, promoted_from_agent
        FROM decisions WHERE {where} ORDER BY created_at ASC
    """,
    "learned_facts": """
        SELECT id, fact, fact_type, category, confidence, is_pinned, is_active,
               created_at, created_by, branch,
               is_global, promoted_from_agent
        FROM learned_facts WHERE {where} ORDER BY created_at ASC
    """,
    "error_resolutions": """
        SELECT id, error_summary, resolution, resolution_type, worked, reuse_count,
               agent_name as _agent, created_at, created_by, branch,
               is_global, promoted_from_agent
        FROM error_resolutions WHERE {where} ORDER BY created_at ASC
    """,
    "goals": """
        SELECT id, title, description, priority, status,
               created_at, created_by, branch
        FROM goals WHERE {where} ORDER BY created_at ASC
    """,
    "tasks": """
        SELECT id, title, description, priority, status,
               created_at, created_by, branch
        FROM tasks WHERE {where} ORDER BY created_at ASC
    """,
}

ENTITY_ICONS = {
    "decisions": "⚖️",
    "learned_facts": "💡",
    "error_resolutions": "🔧",
    "goals": "🎯",
    "tasks": "📝",
}


def _fetch_entities(table: str, session_id=None, agent_name=None,
                    branch=None, days=None) -> List[Dict]:
    """Fetch entities from a table with filters."""
    conditions = ["1=1"]
    params = []

    if session_id:
        conditions.append("source_session = ?")
        params.append(session_id)
    if branch:
        conditions.append("branch = ?")
        params.append(branch)
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conditions.append("created_at >= ?")
        params.append(cutoff)

    # agent_name filter only for tables that have it
    if agent_name and table in ("error_resolutions",):
        conditions.append("agent_name = ?")
        params.append(agent_name)
    elif agent_name and table in ("decisions", "learned_facts"):
        conditions.append("created_by = ?")
        params.append(agent_name)

    query_template = ENTITY_QUERIES.get(table)
    if not query_template:
        return []

    where = " AND ".join(conditions)
    query = query_template.format(where=where)

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for r in rows:
            r["_source"] = table
        return rows
    except Exception:
        return []


def _fetch_events(session_id=None, agent_name=None, branch=None,
                  days=None, limit=200) -> List[Dict]:
    """Fetch agent_events with filters."""
    conn = get_db()
    cursor = conn.cursor()

    conditions = ["1=1"]
    params = []

    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if agent_name:
        conditions.append("agent_name = ?")
        params.append(agent_name)
    if branch:
        conditions.append("branch_name = ?")
        params.append(branch)
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conditions.append("created_at >= ?")
        params.append(cutoff)

    where = " AND ".join(conditions)
    query = f"SELECT * FROM agent_events WHERE {where} ORDER BY created_at ASC LIMIT {min(limit, 500)}"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["_source"] = "agent_events"
    return rows


# ============================================================
# MERGE + DEDUP
# ============================================================

def _merge_timeline(events: List[Dict], entities: List[Dict]) -> List[Dict]:
    """Merge events and entities chronologically, dedup where event references entity."""
    # Build set of (table, id) referenced by events
    referenced = set()
    for e in events:
        t = e.get("related_table")
        i = e.get("related_id")
        if t and i:
            referenced.add((t, i))

    # Enrich events that reference entities
    entity_index = {}
    for ent in entities:
        key = (ent["_source"], ent["id"])
        entity_index[key] = ent

    enriched_events = []
    for e in events:
        t = e.get("related_table")
        i = e.get("related_id")
        if t and i and (t, i) in entity_index:
            e["_entity"] = entity_index[(t, i)]
        enriched_events.append(e)

    # Filter out entities that are already represented by events
    standalone_entities = [
        ent for ent in entities
        if (ent["_source"], ent["id"]) not in referenced
    ]

    # Merge all into timeline
    timeline = enriched_events + standalone_entities
    timeline.sort(key=lambda x: x.get("created_at", ""))

    return timeline


# ============================================================
# REPLAY FUNCTIONS
# ============================================================

def replay_session(session_id: str, limit=200) -> List[Dict]:
    """Full replay of a session: events + entities interleaved."""
    events = _fetch_events(session_id=session_id, limit=limit)

    all_entities = []
    for table in BRANCH_ENTITY_TABLES:
        all_entities.extend(_fetch_entities(table, session_id=session_id))

    return _merge_timeline(events, all_entities)


def replay_agent(agent_name: str, days=7, limit=200) -> List[Dict]:
    """Replay of an agent's activity across sessions."""
    events = _fetch_events(agent_name=agent_name, days=days, limit=limit)

    all_entities = []
    for table in BRANCH_ENTITY_TABLES:
        all_entities.extend(_fetch_entities(table, agent_name=agent_name, days=days))

    return _merge_timeline(events, all_entities)


def replay_branch_rich(branch: str, days=30, limit=200) -> List[Dict]:
    """Rich branch replay: events + entities on a specific branch."""
    events = _fetch_events(branch=branch, days=days, limit=limit)

    all_entities = []
    for table in BRANCH_ENTITY_TABLES:
        all_entities.extend(_fetch_entities(table, branch=branch, days=days))

    return _merge_timeline(events, all_entities)


# ============================================================
# FORMAT
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


def format_replay(timeline: List[Dict]) -> str:
    """Format timeline for terminal display."""
    if not timeline:
        return "  (niciun eveniment)"

    lines = []
    for item in timeline:
        source = item.get("_source", "?")
        ts = format_timestamp(item.get("created_at"))

        if source == "agent_events":
            icon = EVENT_ICONS.get(item.get("event_type", ""), "•")
            title = truncate(item.get("title") or item.get("event_type", "?"), 50)
            agent = item.get("agent_name") or "?"
            success = "✅" if item.get("success_flag", 1) else "❌"
            line = f"  {icon} {ts} [{agent}] {title} {success}"
            lines.append(line)

            # Show enriched entity
            entity = item.get("_entity")
            if entity:
                tbl = entity.get("_source", "?")
                ename = (entity.get("title") or entity.get("fact") or
                         entity.get("error_summary") or "?")
                lines.append(f"     └─ {tbl}#{entity['id']}: {truncate(ename, 45)}")
        else:
            # Standalone entity
            icon = ENTITY_ICONS.get(source, "📄")
            ename = (item.get("title") or item.get("fact") or
                     item.get("error_summary") or "?")
            lines.append(f"  {icon} {ts} [{source}#{item['id']}] {truncate(ename, 50)}")

    return "\n".join(lines)


def replay_summary(timeline: List[Dict]) -> Dict:
    """Summary statistics for a replay."""
    events = [i for i in timeline if i.get("_source") == "agent_events"]
    entities = [i for i in timeline if i.get("_source") != "agent_events"]

    event_types = {}
    for e in events:
        t = e.get("event_type", "unknown")
        event_types[t] = event_types.get(t, 0) + 1

    entity_types = {}
    for e in entities:
        t = e.get("_source", "unknown")
        entity_types[t] = entity_types.get(t, 0) + 1

    agents = set(e.get("agent_name") for e in events if e.get("agent_name"))
    success = sum(1 for e in events if e.get("success_flag", 1))

    return {
        "total_items": len(timeline),
        "events": len(events),
        "entities": len(entities),
        "event_types": event_types,
        "entity_types": entity_types,
        "agents": sorted(agents),
        "success_events": success,
        "failed_events": len(events) - success,
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Experience Replay — replay cronologic bogat")
    sub = parser.add_subparsers(dest="command")

    # session
    p_session = sub.add_parser("session", help="Replay a session")
    p_session.add_argument("session_id", help="Session ID")
    p_session.add_argument("--limit", type=int, default=200)
    p_session.add_argument("--json", action="store_true")

    # agent
    p_agent = sub.add_parser("agent", help="Replay an agent's activity")
    p_agent.add_argument("agent_name", help="Agent name")
    p_agent.add_argument("--days", type=int, default=7)
    p_agent.add_argument("--limit", type=int, default=200)
    p_agent.add_argument("--json", action="store_true")

    # branch
    p_branch = sub.add_parser("branch", help="Replay a branch (rich)")
    p_branch.add_argument("branch_name", help="Branch name")
    p_branch.add_argument("--days", type=int, default=30)
    p_branch.add_argument("--limit", type=int, default=200)
    p_branch.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "session":
        timeline = replay_session(args.session_id, limit=args.limit)
    elif args.command == "agent":
        timeline = replay_agent(args.agent_name, days=args.days, limit=args.limit)
    elif args.command == "branch":
        timeline = replay_branch_rich(args.branch_name, days=args.days, limit=args.limit)
    else:
        parser.print_help()
        return

    if not timeline:
        print("(niciun eveniment găsit)")
        return

    if args.json:
        summary = replay_summary(timeline)
        # Clean items for JSON serialization
        clean = []
        for item in timeline:
            c = {k: v for k, v in item.items() if not k.startswith("_") or k == "_entity"}
            if "_entity" in c:
                c["entity"] = {k: v for k, v in c.pop("_entity").items() if not k.startswith("_")}
            c["source"] = item.get("_source", "?")
            clean.append(c)

        output = {"replay": clean, "summary": summary}
        print(json.dumps(output, indent=2, default=str))
    else:
        summary = replay_summary(timeline)
        print(f"\n🔄 EXPERIENCE REPLAY ({args.command})")
        print("=" * 60)
        print(format_replay(timeline))
        print(f"\n--- Summary ---")
        print(f"  Total: {summary['total_items']} items ({summary['events']} events, {summary['entities']} entities)")
        print(f"  Events: ✅ {summary['success_events']} / ❌ {summary['failed_events']}")
        print(f"  Agents: {', '.join(summary['agents']) or '—'}")
        if summary["entity_types"]:
            print(f"  Entities: {', '.join(f'{t}({c})' for t, c in summary['entity_types'].items())}")


if __name__ == "__main__":
    main()
