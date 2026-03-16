#!/usr/bin/env python3
"""
mem_fp.py - False Positive Scoring CLI
Vizualizare scoring pattern-uri și detecții pentru reducere false positives
"""

import sys
import os
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

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
    except:
        return ts_str[:19]

def confidence_emoji(confidence):
    """Emoji pentru confidence level."""
    mapping = {
        "HIGH": "🔴",
        "MED": "🟡",
        "LOW": "🟢"
    }
    return mapping.get(confidence, "")

def decision_emoji(decision):
    """Emoji pentru decision."""
    mapping = {
        "quarantine": "🔒",
        "scrub": "🧹",
        "report": "📝",
        "allow": "✅"
    }
    return mapping.get(decision, "")

def cmd_stats(args):
    """Overview statistici detecții."""
    conn = get_db()
    cursor = conn.cursor()

    # Total detections
    cursor.execute("SELECT COUNT(*) FROM detection_events")
    total = cursor.fetchone()[0]

    # By category
    cursor.execute("""
        SELECT category, COUNT(*) as cnt, AVG(score) as avg_score
        FROM detection_events
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 10
    """)
    by_category = cursor.fetchall()

    # By confidence
    cursor.execute("""
        SELECT confidence, COUNT(*) as cnt
        FROM detection_events
        GROUP BY confidence
        ORDER BY cnt DESC
    """)
    by_confidence = cursor.fetchall()

    # By decision
    cursor.execute("""
        SELECT decision, COUNT(*) as cnt
        FROM detection_events
        GROUP BY decision
        ORDER BY cnt DESC
    """)
    by_decision = cursor.fetchall()

    # By source
    cursor.execute("""
        SELECT source, COUNT(*) as cnt
        FROM detection_events
        GROUP BY source
        ORDER BY cnt DESC
    """)
    by_source = cursor.fetchall()

    # Last 24h
    cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM detection_events WHERE ts >= ?", (cutoff_24h,))
    last_24h = cursor.fetchone()[0]

    # Last 7d
    cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM detection_events WHERE ts >= ?", (cutoff_7d,))
    last_7d = cursor.fetchone()[0]

    # Average score
    cursor.execute("SELECT AVG(score) FROM detection_events")
    avg_score = cursor.fetchone()[0] or 0

    conn.close()

    if args.json:
        # JSON output
        output = {
            "total": total,
            "last_24h": last_24h,
            "last_7d": last_7d,
            "avg_score": round(avg_score, 2),
            "by_category": [{"category": c, "count": cnt, "avg_score": round(s, 2)} for c, cnt, s in by_category],
            "by_confidence": [{"confidence": conf, "count": cnt} for conf, cnt in by_confidence],
            "by_decision": [{"decision": d, "count": cnt} for d, cnt in by_decision],
            "by_source": [{"source": s, "count": cnt} for s, cnt in by_source]
        }
        print(json.dumps(output, indent=2))
    else:
        # Text output
        print("\n📊 FALSE POSITIVE SCORING - STATISTICS")
        print("=" * 70)
        print(f"Total detections: {total:,}")
        print(f"Last 24h:         {last_24h:,}")
        print(f"Last 7 days:      {last_7d:,}")
        print(f"Average score:    {avg_score:.1f}/100")

        print("\n🎯 By Category (Top 10):")
        print("-" * 70)
        for category, cnt, avg_s in by_category:
            print(f"  {category:<20} {cnt:>6,} detections  (avg score: {avg_s:.1f})")

        print("\n⚠️  By Confidence:")
        print("-" * 70)
        for confidence, cnt in by_confidence:
            icon = confidence_emoji(confidence)
            print(f"  {icon} {confidence:<10} {cnt:>6,}")

        print("\n🎬 By Decision:")
        print("-" * 70)
        for decision, cnt in by_decision:
            icon = decision_emoji(decision)
            print(f"  {icon} {decision:<15} {cnt:>6,}")

        print("\n📡 By Source:")
        print("-" * 70)
        for source, cnt in by_source:
            print(f"  {source:<20} {cnt:>6,}")

        print("=" * 70)

def cmd_top(args):
    """Top 10 categories by detection count."""
    conn = get_db()
    cursor = conn.cursor()

    limit = args.limit or 10

    cursor.execute("""
        SELECT category, COUNT(*) as cnt,
               AVG(score) as avg_score,
               MIN(score) as min_score,
               MAX(score) as max_score
        FROM detection_events
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("✅ Nicio detecție înregistrată.")
        return

    if args.json:
        categories = []
        for row in rows:
            categories.append({
                "category": row[0],
                "count": row[1],
                "avg_score": round(row[2], 2),
                "min_score": row[3],
                "max_score": row[4]
            })
        print(json.dumps({"top_categories": categories}, indent=2))
    else:
        print(f"\n🏆 TOP {limit} CATEGORIES by Detection Count")
        print("=" * 80)
        print(f"{'Category':<20} {'Count':>8} {'Avg Score':>10} {'Min':>6} {'Max':>6}")
        print("-" * 80)

        for category, cnt, avg_s, min_s, max_s in rows:
            print(f"{category:<20} {cnt:>8,} {avg_s:>10.1f} {min_s:>6} {max_s:>6}")

        print("=" * 80)

def cmd_rules(args):
    """Lista reguli active."""
    conn = get_db()
    cursor = conn.cursor()

    if args.pattern:
        # Detalii pentru o regulă specifică
        cursor.execute("""
            SELECT pattern_id, category, weight, description, enabled
            FROM detection_rules
            WHERE pattern_id = ?
        """, (args.pattern,))

        row = cursor.fetchone()
        if not row:
            print(f"❌ Regulă nu a fost găsită: {args.pattern}")
            conn.close()
            return

        pattern_id, category, weight, description, enabled = row

        # Detecții pentru această regulă
        cursor.execute("""
            SELECT COUNT(*) FROM detection_events WHERE pattern_id = ?
        """, (pattern_id,))
        detection_count = cursor.fetchone()[0]

        conn.close()

        if args.json:
            output = {
                "pattern_id": pattern_id,
                "category": category,
                "weight": weight,
                "description": description,
                "enabled": bool(enabled),
                "detection_count": detection_count
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"\n📋 RULE DETAILS: {pattern_id}")
            print("=" * 70)
            print(f"Category:     {category}")
            print(f"Weight:       {weight}/100")
            print(f"Enabled:      {'✅ Yes' if enabled else '❌ No'}")
            print(f"Description:  {description}")
            print(f"Detections:   {detection_count:,}")
            print("=" * 70)
    else:
        # Lista toate regulile
        cursor.execute("""
            SELECT pattern_id, category, weight, description, enabled
            FROM detection_rules
            ORDER BY weight DESC, category
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("✅ Nicio regulă configurată.")
            return

        if args.json:
            rules = []
            for row in rows:
                rules.append({
                    "pattern_id": row[0],
                    "category": row[1],
                    "weight": row[2],
                    "description": row[3],
                    "enabled": bool(row[4])
                })
            print(json.dumps({"rules": rules, "count": len(rules)}, indent=2))
        else:
            print(f"\n📋 DETECTION RULES ({len(rows)} total)")
            print("=" * 90)
            print(f"{'Pattern ID':<25} {'Category':<15} {'Weight':>7} {'Enabled':^8} {'Description':<30}")
            print("-" * 90)

            for pattern_id, category, weight, description, enabled in rows:
                enabled_str = "✅" if enabled else "❌"
                desc_short = (description or "")[:30]
                print(f"{pattern_id:<25} {category:<15} {weight:>7} {enabled_str:^8} {desc_short:<30}")

            print("=" * 90)

def cmd_recent(args):
    """Ultimele N detecții."""
    limit = args.limit or 20

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, ts, source, pattern_id, category,
               score, confidence, decision, table_name, excerpt
        FROM detection_events
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("✅ Nicio detecție înregistrată.")
        return

    if args.json:
        events = []
        for row in rows:
            events.append({
                "id": row[0],
                "ts": row[1],
                "source": row[2],
                "pattern_id": row[3],
                "category": row[4],
                "score": row[5],
                "confidence": row[6],
                "decision": row[7],
                "table_name": row[8],
                "excerpt": row[9]
            })
        print(json.dumps({"events": events, "count": len(events)}, indent=2))
    else:
        print(f"\n🔍 RECENT DETECTIONS - Ultimele {limit}")
        print("=" * 120)
        print(f"{'ID':>5} {'Timestamp':<19} {'Source':<10} {'Category':<15} {'Score':>5} {'Conf':^6} {'Dec':^6} {'Table':<15} {'Excerpt':<25}")
        print("-" * 120)

        for row in rows:
            id_, ts, source, pattern, category, score, conf, decision, table, excerpt = row
            ts_fmt = format_timestamp(ts)
            conf_icon = confidence_emoji(conf)
            dec_icon = decision_emoji(decision)
            excerpt_short = (excerpt or "")[:25]

            print(f"{id_:>5} {ts_fmt:<19} {source:<10} {category:<15} {score:>5} {conf_icon:^6} {dec_icon:^6} {table:<15} {excerpt_short:<25}")

        print(f"\nTotal: {len(rows)} detections")

def cmd_search(args):
    """Caută în detection_events."""
    if not args.query:
        print("❌ Folosire: mem fp search <query>")
        return

    query = args.query
    conn = get_db()
    cursor = conn.cursor()

    # Caută în pattern_id, category, table_name, excerpt
    cursor.execute("""
        SELECT id, ts, source, pattern_id, category,
               score, confidence, decision, table_name, excerpt
        FROM detection_events
        WHERE pattern_id LIKE ?
           OR category LIKE ?
           OR table_name LIKE ?
           OR excerpt LIKE ?
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
                "source": row[2],
                "pattern_id": row[3],
                "category": row[4],
                "score": row[5],
                "confidence": row[6],
                "decision": row[7],
                "table_name": row[8],
                "excerpt": row[9]
            })
        print(json.dumps({"query": query, "events": events, "count": len(events)}, indent=2))
    else:
        print(f"\n🔍 SEARCH RESULTS - '{query}'")
        print("=" * 120)
        print(f"{'ID':>5} {'Timestamp':<19} {'Source':<10} {'Category':<15} {'Score':>5} {'Conf':^6} {'Dec':^6} {'Table':<15} {'Excerpt':<25}")
        print("-" * 120)

        for row in rows:
            id_, ts, source, pattern, category, score, conf, decision, table, excerpt = row
            ts_fmt = format_timestamp(ts)
            conf_icon = confidence_emoji(conf)
            dec_icon = decision_emoji(decision)
            excerpt_short = (excerpt or "")[:25]

            print(f"{id_:>5} {ts_fmt:<19} {source:<10} {category:<15} {score:>5} {conf_icon:^6} {dec_icon:^6} {table:<15} {excerpt_short:<25}")

        print(f"\nTotal: {len(rows)} results")

def main():
    parser = argparse.ArgumentParser(
        description="mem_fp - False Positive Scoring CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mem fp stats              # Overview statistici
  mem fp top                # Top 10 categories
  mem fp rules              # Lista reguli active
  mem fp rules --pattern bearer_auth  # Detalii regulă
  mem fp recent             # Ultimele 20 detecții
  mem fp search "api_key"   # Caută detecții
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Comenzi disponibile")

    # stats
    parser_stats = subparsers.add_parser("stats", help="Overview statistici detecții")
    parser_stats.add_argument("--json", action="store_true", help="Output JSON")

    # top
    parser_top = subparsers.add_parser("top", help="Top categories by detection count")
    parser_top.add_argument("-n", "--limit", type=int, default=10, help="Număr categories (default: 10)")
    parser_top.add_argument("--json", action="store_true", help="Output JSON")

    # rules
    parser_rules = subparsers.add_parser("rules", help="Lista reguli active")
    parser_rules.add_argument("--pattern", help="Pattern ID pentru detalii")
    parser_rules.add_argument("--json", action="store_true", help="Output JSON")

    # recent
    parser_recent = subparsers.add_parser("recent", help="Ultimele N detecții")
    parser_recent.add_argument("-n", "--limit", type=int, default=20, help="Număr detecții (default: 20)")
    parser_recent.add_argument("--json", action="store_true", help="Output JSON")

    # search
    parser_search = subparsers.add_parser("search", help="Caută în detection_events")
    parser_search.add_argument("query", help="Text de căutat")
    parser_search.add_argument("-n", "--limit", type=int, default=50, help="Limită rezultate (default: 50)")
    parser_search.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "stats":
        cmd_stats(args)
    elif args.command == "top":
        cmd_top(args)
    elif args.command == "rules":
        cmd_rules(args)
    elif args.command == "recent":
        cmd_recent(args)
    elif args.command == "search":
        cmd_search(args)

if __name__ == "__main__":
    main()
