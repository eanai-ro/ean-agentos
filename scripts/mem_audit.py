#!/usr/bin/env python3
"""
mem_audit.py - Audit Trail CLI
Vizualizare și căutare în audit_log pentru trasabilitate completă
"""

import sys
import os
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_DIR = Path.home() / ".claude" / "memory"
DB_FILE = MEMORY_DIR / "global.db"

def get_db():
    """Conectare DB."""
    return sqlite3.connect(DB_FILE)

def format_timestamp(ts_str):
    """Format timestamp human-readable."""
    if not ts_str:
        return "N/A"

    try:
        ts = datetime.fromisoformat(ts_str)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str[:19]  # Truncate la YYYY-MM-DD HH:MM:SS

def severity_emoji(severity):
    """Emoji pentru severity."""
    mapping = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "WARN": "⚠️",
        "INFO": "ℹ️"
    }
    return mapping.get(severity, "")

def cmd_tail(args):
    """Ultimele N audit events."""
    limit = args.limit or 20

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, ts, action_type, table_name, row_id,
               severity, change_summary, actor
        FROM audit_log
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("✅ Niciun event în audit log.")
        return

    if args.json:
        # JSON output
        events = []
        for row in rows:
            events.append({
                "id": row[0],
                "ts": row[1],
                "action_type": row[2],
                "table_name": row[3],
                "row_id": row[4],
                "severity": row[5],
                "change_summary": row[6],
                "actor": row[7]
            })
        print(json.dumps({"events": events, "count": len(events)}, indent=2))
    else:
        # Text output
        print(f"\n🔍 AUDIT LOG - Ultimele {limit} events")
        print("=" * 120)
        print(f"{'ID':>5} {'Timestamp':<19} {'Action':<20} {'Table':<20} {'Sev':^6} {'Actor':<15} {'Summary':<40}")
        print("-" * 120)

        for row in rows:
            id_, ts, action, table, row_id, sev, summary, actor = row
            ts_fmt = format_timestamp(ts)
            sev_icon = severity_emoji(sev)
            summary_short = (summary or "")[:40]

            print(f"{id_:>5} {ts_fmt:<19} {action:<20} {table:<20} {sev_icon:^6} {actor:<15} {summary_short:<40}")

        print(f"\nTotal: {len(rows)} events")

def cmd_search(args):
    """Caută în audit log."""
    if not args.query:
        print("❌ Folosire: mem audit search <query>")
        return

    query = args.query
    conn = get_db()
    cursor = conn.cursor()

    # Caută în action_type, table_name, change_summary, actor
    cursor.execute("""
        SELECT id, ts, action_type, table_name, row_id,
               severity, change_summary, actor
        FROM audit_log
        WHERE action_type LIKE ?
           OR table_name LIKE ?
           OR change_summary LIKE ?
           OR actor LIKE ?
        ORDER BY id DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", args.limit or 50))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"❌ Niciun rezultat pentru: {query}")
        return

    if args.json:
        events = []
        for row in rows:
            events.append({
                "id": row[0],
                "ts": row[1],
                "action_type": row[2],
                "table_name": row[3],
                "row_id": row[4],
                "severity": row[5],
                "change_summary": row[6],
                "actor": row[7]
            })
        print(json.dumps({"query": query, "events": events, "count": len(events)}, indent=2))
    else:
        print(f"\n🔍 AUDIT LOG - Rezultate pentru: '{query}'")
        print("=" * 120)
        print(f"{'ID':>5} {'Timestamp':<19} {'Action':<20} {'Table':<20} {'Sev':^6} {'Actor':<15} {'Summary':<40}")
        print("-" * 120)

        for row in rows:
            id_, ts, action, table, row_id, sev, summary, actor = row
            ts_fmt = format_timestamp(ts)
            sev_icon = severity_emoji(sev)
            summary_short = (summary or "")[:40]

            print(f"{id_:>5} {ts_fmt:<19} {action:<20} {table:<20} {sev_icon:^6} {actor:<15} {summary_short:<40}")

        print(f"\nTotal: {len(rows)} results")

def cmd_stats(args):
    """Statistici audit log."""
    conn = get_db()
    cursor = conn.cursor()

    # Total events
    cursor.execute("SELECT COUNT(*) FROM audit_log")
    total = cursor.fetchone()[0]

    # By action_type
    cursor.execute("""
        SELECT action_type, COUNT(*) as cnt
        FROM audit_log
        GROUP BY action_type
        ORDER BY cnt DESC
        LIMIT 10
    """)
    by_action = cursor.fetchall()

    # By severity
    cursor.execute("""
        SELECT severity, COUNT(*) as cnt
        FROM audit_log
        GROUP BY severity
        ORDER BY cnt DESC
    """)
    by_severity = cursor.fetchall()

    # By table
    cursor.execute("""
        SELECT table_name, COUNT(*) as cnt
        FROM audit_log
        GROUP BY table_name
        ORDER BY cnt DESC
        LIMIT 10
    """)
    by_table = cursor.fetchall()

    # By actor
    cursor.execute("""
        SELECT actor, COUNT(*) as cnt
        FROM audit_log
        GROUP BY actor
        ORDER BY cnt DESC
        LIMIT 10
    """)
    by_actor = cursor.fetchall()

    # Last 24h
    cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE ts >= ?", (cutoff_24h,))
    last_24h = cursor.fetchone()[0]

    # Last 7d
    cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE ts >= ?", (cutoff_7d,))
    last_7d = cursor.fetchone()[0]

    conn.close()

    if args.json:
        # JSON output
        output = {
            "total": total,
            "last_24h": last_24h,
            "last_7d": last_7d,
            "by_action": [{"action": a, "count": c} for a, c in by_action],
            "by_severity": [{"severity": s, "count": c} for s, c in by_severity],
            "by_table": [{"table": t, "count": c} for t, c in by_table],
            "by_actor": [{"actor": a, "count": c} for a, c in by_actor]
        }
        print(json.dumps(output, indent=2))
    else:
        # Text output
        print("\n📊 AUDIT LOG STATISTICS")
        print("=" * 70)
        print(f"Total events:     {total:,}")
        print(f"Last 24h:         {last_24h:,}")
        print(f"Last 7 days:      {last_7d:,}")

        print("\n🎯 By Action Type (Top 10):")
        print("-" * 70)
        for action, cnt in by_action:
            print(f"  {action:<30} {cnt:>8,}")

        print("\n⚠️  By Severity:")
        print("-" * 70)
        for severity, cnt in by_severity:
            icon = severity_emoji(severity)
            print(f"  {icon} {severity:<15} {cnt:>8,}")

        print("\n📋 By Table (Top 10):")
        print("-" * 70)
        for table, cnt in by_table:
            print(f"  {table:<30} {cnt:>8,}")

        print("\n👤 By Actor (Top 10):")
        print("-" * 70)
        for actor, cnt in by_actor:
            print(f"  {actor:<30} {cnt:>8,}")

        print("=" * 70)

def main():
    parser = argparse.ArgumentParser(
        description="mem_audit - Audit Trail CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mem audit tail              # Ultimele 20 events
  mem audit tail -n 50        # Ultimele 50
  mem audit search scrub      # Caută "scrub" în audit log
  mem audit stats             # Statistici complete
  mem audit stats --json      # JSON output
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Comenzi disponibile")

    # tail
    parser_tail = subparsers.add_parser("tail", help="Ultimele N audit events")
    parser_tail.add_argument("-n", "--limit", type=int, default=20, help="Număr events (default: 20)")
    parser_tail.add_argument("--json", action="store_true", help="Output JSON")

    # search
    parser_search = subparsers.add_parser("search", help="Caută în audit log")
    parser_search.add_argument("query", help="Text de căutat")
    parser_search.add_argument("-n", "--limit", type=int, default=50, help="Limită rezultate (default: 50)")
    parser_search.add_argument("--json", action="store_true", help="Output JSON")

    # stats
    parser_stats = subparsers.add_parser("stats", help="Statistici audit log")
    parser_stats.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "tail":
        cmd_tail(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "stats":
        cmd_stats(args)

if __name__ == "__main__":
    main()
