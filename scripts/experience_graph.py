#!/usr/bin/env python3
"""
Experience Graph — model logic pentru problem → attempt → error → resolution → success.

Reutilizează tabelele existente (errors_solutions, error_resolutions, error_patterns)
cu experience_links ca tabel de relații.

CLI: experience_graph.py build | show <table> <id> | path <from_tbl> <from_id> <to_tbl> <to_id> | stats [--json]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from v2_common import get_db, format_timestamp, truncate, VALID_LINK_TYPES


# ============================================================
# BUILD GRAPH — auto-discover links from existing data
# ============================================================

def build_links() -> Dict:
    """Auto-discover and create experience links from existing data relationships."""
    conn = get_db()
    cursor = conn.cursor()
    created = 0
    skipped = 0

    # 1. error_resolutions → errors_solutions (resolved_by / error_caused_by)
    cursor.execute("""
        SELECT er.id as res_id, er.error_id, er.error_fingerprint, er.error_summary
        FROM error_resolutions er
        WHERE er.error_id IS NOT NULL
    """)
    for row in cursor.fetchall():
        # Link: errors_solutions → error_resolutions (resolved_by)
        if _link_exists(cursor, "errors_solutions", row["error_id"], "error_resolutions", row["res_id"]):
            skipped += 1
        else:
            _create_link(cursor, "errors_solutions", row["error_id"],
                        "error_resolutions", row["res_id"], "resolved_by")
            created += 1

        # Reverse: error_resolutions → errors_solutions (error_caused_by)
        if _link_exists(cursor, "error_resolutions", row["res_id"], "errors_solutions", row["error_id"]):
            skipped += 1
        else:
            _create_link(cursor, "error_resolutions", row["res_id"],
                        "errors_solutions", row["error_id"], "error_caused_by")
            created += 1

    # 2. error_resolutions with same fingerprint → attempted_with (alternative attempts)
    cursor.execute("""
        SELECT error_fingerprint, GROUP_CONCAT(id) as ids
        FROM error_resolutions
        WHERE error_fingerprint IS NOT NULL
        GROUP BY error_fingerprint
        HAVING COUNT(*) > 1
    """)
    for row in cursor.fetchall():
        ids = [int(x) for x in row["ids"].split(",")]
        for i, id1 in enumerate(ids):
            for id2 in ids[i+1:]:
                if not _link_exists(cursor, "error_resolutions", id1, "error_resolutions", id2):
                    _create_link(cursor, "error_resolutions", id1,
                                "error_resolutions", id2, "attempted_with")
                    created += 1
                else:
                    skipped += 1

    # 3. error_patterns → errors_solutions (pattern_of)
    # Match patterns to raw errors by normalized signature
    cursor.execute("SELECT id, error_signature FROM error_patterns")
    patterns = cursor.fetchall()
    for pat in patterns:
        # Find matching error_resolutions via fingerprint similarity
        cursor.execute("""
            SELECT id FROM error_resolutions
            WHERE error_fingerprint = ? OR error_summary LIKE ?
            LIMIT 10
        """, (pat["error_signature"][:16], f"%{pat['error_signature'][:30]}%"))
        for res in cursor.fetchall():
            if not _link_exists(cursor, "error_patterns", pat["id"], "error_resolutions", res["id"]):
                _create_link(cursor, "error_patterns", pat["id"],
                            "error_resolutions", res["id"], "pattern_of")
                created += 1
            else:
                skipped += 1

    # 4. agent_events with related_table → infer fact_from_resolution links
    cursor.execute("""
        SELECT ae1.related_id as fact_id, ae2.related_id as res_id
        FROM agent_events ae1
        JOIN agent_events ae2 ON ae1.session_id = ae2.session_id
        WHERE ae1.event_type = 'fact_created'
          AND ae1.related_table = 'learned_facts'
          AND ae2.event_type = 'resolution_created'
          AND ae2.related_table = 'error_resolutions'
          AND ae1.related_id IS NOT NULL
          AND ae2.related_id IS NOT NULL
          AND ae1.created_at > ae2.created_at
    """)
    for row in cursor.fetchall():
        if not _link_exists(cursor, "learned_facts", row["fact_id"],
                           "error_resolutions", row["res_id"]):
            _create_link(cursor, "learned_facts", row["fact_id"],
                        "error_resolutions", row["res_id"], "fact_from_resolution")
            created += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    return {"created": created, "skipped": skipped}


def _link_exists(cursor, from_table, from_id, to_table, to_id) -> bool:
    """Check if a link already exists."""
    cursor.execute("""
        SELECT 1 FROM experience_links
        WHERE from_table = ? AND from_id = ? AND to_table = ? AND to_id = ?
        LIMIT 1
    """, (from_table, from_id, to_table, to_id))
    return cursor.fetchone() is not None


def _create_link(cursor, from_table, from_id, to_table, to_id, link_type, confidence=1.0):
    """Create a new experience link."""
    cursor.execute("""
        INSERT INTO experience_links (from_table, from_id, to_table, to_id, link_type, confidence)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (from_table, from_id, to_table, to_id, link_type, confidence))


# ============================================================
# QUERY GRAPH
# ============================================================

def get_neighbors(table: str, entity_id: int) -> Dict:
    """Get all links from/to an entity."""
    conn = get_db()
    cursor = conn.cursor()

    # Outgoing links
    cursor.execute("""
        SELECT * FROM experience_links
        WHERE from_table = ? AND from_id = ?
        ORDER BY created_at DESC
    """, (table, entity_id))
    outgoing = [dict(r) for r in cursor.fetchall()]

    # Incoming links
    cursor.execute("""
        SELECT * FROM experience_links
        WHERE to_table = ? AND to_id = ?
        ORDER BY created_at DESC
    """, (table, entity_id))
    incoming = [dict(r) for r in cursor.fetchall()]

    # Get entity title
    entity_title = _get_entity_title(cursor, table, entity_id)

    conn.close()

    return {
        "entity": {"table": table, "id": entity_id, "title": entity_title},
        "outgoing": outgoing,
        "incoming": incoming,
        "total_links": len(outgoing) + len(incoming),
    }


def find_path(from_table: str, from_id: int, to_table: str, to_id: int,
              max_depth: int = 5) -> Optional[List[Dict]]:
    """BFS to find path between two entities in the experience graph."""
    conn = get_db()
    cursor = conn.cursor()

    visited = set()
    queue = [[(from_table, from_id)]]

    while queue:
        path = queue.pop(0)
        current = path[-1]

        if current == (to_table, to_id):
            conn.close()
            # Enrich path with titles
            enriched = []
            for tbl, eid in path:
                title = _get_entity_title(cursor, tbl, eid) if conn else "?"
                enriched.append({"table": tbl, "id": eid, "title": title})
            return enriched

        if len(path) > max_depth:
            continue

        ct, ci = current
        if (ct, ci) in visited:
            continue
        visited.add((ct, ci))

        # Get neighbors
        cursor.execute("""
            SELECT to_table, to_id FROM experience_links
            WHERE from_table = ? AND from_id = ?
            UNION
            SELECT from_table, from_id FROM experience_links
            WHERE to_table = ? AND to_id = ?
        """, (ct, ci, ct, ci))

        for row in cursor.fetchall():
            neighbor = (row[0], row[1])
            if neighbor not in visited:
                queue.append(path + [neighbor])

    conn.close()
    return None


def _get_entity_title(cursor, table: str, entity_id: int) -> str:
    """Get a human-readable title for an entity."""
    title_cols = {
        "decisions": "title",
        "learned_facts": "fact",
        "error_resolutions": "error_summary",
        "errors_solutions": "error_message",
        "error_patterns": "error_signature",
        "goals": "title",
        "tasks": "title",
    }
    col = title_cols.get(table, "id")
    try:
        cursor.execute(f"SELECT {col} FROM {table} WHERE id = ?", (entity_id,))
        row = cursor.fetchone()
        return truncate(row[0] if row else "?", 60)
    except Exception:
        return f"#{entity_id}"


def graph_stats() -> Dict:
    """Statistics about the experience graph."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM experience_links")
    total_links = cursor.fetchone()[0]

    cursor.execute("""
        SELECT link_type, COUNT(*) as cnt
        FROM experience_links
        GROUP BY link_type
        ORDER BY cnt DESC
    """)
    by_type = {row["link_type"]: row["cnt"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT from_table, COUNT(DISTINCT from_id) as entities
        FROM experience_links
        GROUP BY from_table
    """)
    from_entities = {row["from_table"]: row["entities"] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT to_table, COUNT(DISTINCT to_id) as entities
        FROM experience_links
        GROUP BY to_table
    """)
    to_entities = {row["to_table"]: row["entities"] for row in cursor.fetchall()}

    # Unique entities involved
    all_tables = set(list(from_entities.keys()) + list(to_entities.keys()))
    unique_entities = {}
    for tbl in all_tables:
        unique_entities[tbl] = max(from_entities.get(tbl, 0), to_entities.get(tbl, 0))

    conn.close()

    return {
        "total_links": total_links,
        "link_types": by_type,
        "unique_entities": unique_entities,
        "total_unique_entities": sum(unique_entities.values()),
    }


# ============================================================
# CLI
# ============================================================

LINK_ICONS = {
    "error_caused_by": "💥→",
    "resolved_by": "✅→",
    "pattern_of": "🔄→",
    "decision_led_to": "⚖️→",
    "decision_resolved_by": "⚖️✅",
    "fact_from_resolution": "💡←🔧",
    "attempted_with": "🔀",
}

ENTITY_ICONS = {
    "decisions": "⚖️", "learned_facts": "💡", "error_resolutions": "🔧",
    "errors_solutions": "❌", "error_patterns": "🔄", "goals": "🎯", "tasks": "📝",
}


def main():
    parser = argparse.ArgumentParser(description="Experience Graph — problem → resolution links")
    sub = parser.add_subparsers(dest="command")

    # build
    p_build = sub.add_parser("build", help="Auto-discover and build experience links")
    p_build.add_argument("--json", action="store_true")

    # show <table> <id>
    p_show = sub.add_parser("show", help="Show neighbors of an entity")
    p_show.add_argument("table", help="Table name")
    p_show.add_argument("entity_id", type=int, help="Entity ID")
    p_show.add_argument("--json", action="store_true")

    # path
    p_path = sub.add_parser("path", help="Find path between two entities")
    p_path.add_argument("from_table")
    p_path.add_argument("from_id", type=int)
    p_path.add_argument("to_table")
    p_path.add_argument("to_id", type=int)
    p_path.add_argument("--json", action="store_true")

    # stats
    p_stats = sub.add_parser("stats", help="Graph statistics")
    p_stats.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "build":
        result = build_links()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n🔗 EXPERIENCE GRAPH BUILD")
            print(f"  Created: {result['created']} new links")
            print(f"  Skipped: {result['skipped']} (already exist)")

    elif args.command == "show":
        data = get_neighbors(args.table, args.entity_id)
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            e = data["entity"]
            icon = ENTITY_ICONS.get(e["table"], "📄")
            print(f"\n{icon} {e['table']}#{e['id']}: {e['title']}")
            print(f"   Total links: {data['total_links']}")

            if data["outgoing"]:
                print(f"\n   → Outgoing ({len(data['outgoing'])}):")
                for link in data["outgoing"]:
                    li = LINK_ICONS.get(link["link_type"], "→")
                    print(f"     {li} [{link['link_type']}] {link['to_table']}#{link['to_id']}")

            if data["incoming"]:
                print(f"\n   ← Incoming ({len(data['incoming'])}):")
                for link in data["incoming"]:
                    li = LINK_ICONS.get(link["link_type"], "←")
                    print(f"     {li} [{link['link_type']}] {link['from_table']}#{link['from_id']}")

    elif args.command == "path":
        path = find_path(args.from_table, args.from_id, args.to_table, args.to_id)
        if args.json:
            print(json.dumps({"path": path}, indent=2, default=str))
        elif path:
            print(f"\n🔗 PATH: {args.from_table}#{args.from_id} → {args.to_table}#{args.to_id}")
            for i, node in enumerate(path):
                icon = ENTITY_ICONS.get(node["table"], "📄")
                arrow = "  → " if i > 0 else "    "
                print(f"{arrow}{icon} {node['table']}#{node['id']}: {node['title']}")
        else:
            print(f"❌ Nu s-a găsit cale între {args.from_table}#{args.from_id} și {args.to_table}#{args.to_id}")

    elif args.command == "stats":
        s = graph_stats()
        if args.json:
            print(json.dumps(s, indent=2))
        else:
            print(f"\n📊 EXPERIENCE GRAPH STATS")
            print(f"  Total links: {s['total_links']}")
            print(f"  Unique entities: {s['total_unique_entities']}")
            if s["link_types"]:
                print(f"\n  Link types:")
                for lt, cnt in s["link_types"].items():
                    print(f"    {LINK_ICONS.get(lt, '→')} {lt}: {cnt}")
            if s["unique_entities"]:
                print(f"\n  Entities by table:")
                for tbl, cnt in s["unique_entities"].items():
                    icon = ENTITY_ICONS.get(tbl, "📄")
                    print(f"    {icon} {tbl}: {cnt}")


if __name__ == "__main__":
    main()
