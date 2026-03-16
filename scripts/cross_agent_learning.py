#!/usr/bin/env python3
"""
Cross-Agent Learning — identifică și promovează experiențe reutilizabile.

Scoring:
  worked(+3), reuse_count>=2(+2), confirmed(+3), pinned(+2),
  multi-agent(+2), longevity 7d(+1) / 30d(+2). Threshold >= 5.

CLI: cross_agent_learning.py scan|promote|promote-auto|suggest|list|stats [--json]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from v2_common import (
    get_db, format_timestamp, truncate, log_agent_event,
    CROSS_AGENT_TABLES,
)


DEFAULT_THRESHOLD = 5


# ============================================================
# SCORING
# ============================================================

def _score_decision(row: Dict) -> Tuple[int, List[str]]:
    """Score a decision for cross-agent promotion."""
    score = 0
    reasons = []

    # Confidence
    if row.get("confidence") == "confirmed":
        score += 3
        reasons.append("confirmed(+3)")
    elif row.get("confidence") == "high":
        score += 1
        reasons.append("high_confidence(+1)")

    # Status active
    if row.get("status") == "active":
        score += 1
        reasons.append("active(+1)")

    # Longevity
    created = row.get("created_at", "")
    if created:
        try:
            age = datetime.now() - datetime.fromisoformat(created.replace("Z", "+00:00"))
            if age > timedelta(days=30):
                score += 2
                reasons.append("longevity_30d(+2)")
            elif age > timedelta(days=7):
                score += 1
                reasons.append("longevity_7d(+1)")
        except (ValueError, TypeError):
            pass

    # Multi-agent: check if other agents reference similar decisions
    # (simplified: if created_by is not default)
    if row.get("created_by") and row["created_by"] not in ("user", "api"):
        score += 2
        reasons.append("agent_created(+2)")

    return score, reasons


def _score_fact(row: Dict) -> Tuple[int, List[str]]:
    """Score a learned fact for cross-agent promotion."""
    score = 0
    reasons = []

    # Pinned
    if row.get("is_pinned"):
        score += 2
        reasons.append("pinned(+2)")

    # Confidence
    if row.get("confidence") == "confirmed":
        score += 3
        reasons.append("confirmed(+3)")
    elif row.get("confidence") == "high":
        score += 1
        reasons.append("high_confidence(+1)")

    # Active
    if row.get("is_active"):
        score += 1
        reasons.append("active(+1)")

    # Longevity
    created = row.get("created_at", "")
    if created:
        try:
            age = datetime.now() - datetime.fromisoformat(created.replace("Z", "+00:00"))
            if age > timedelta(days=30):
                score += 2
                reasons.append("longevity_30d(+2)")
            elif age > timedelta(days=7):
                score += 1
                reasons.append("longevity_7d(+1)")
        except (ValueError, TypeError):
            pass

    # Agent-created
    if row.get("created_by") and row["created_by"] not in ("user", "api"):
        score += 2
        reasons.append("agent_created(+2)")

    return score, reasons


def _score_resolution(row: Dict) -> Tuple[int, List[str]]:
    """Score an error resolution for cross-agent promotion."""
    score = 0
    reasons = []

    # Worked
    if row.get("worked"):
        score += 3
        reasons.append("worked(+3)")

    # Reuse count
    reuse = row.get("reuse_count", 0) or 0
    if reuse >= 2:
        score += 2
        reasons.append(f"reuse_count={reuse}(+2)")

    # Agent-created
    if row.get("agent_name"):
        score += 2
        reasons.append("agent_created(+2)")

    # Longevity
    created = row.get("created_at", "")
    if created:
        try:
            age = datetime.now() - datetime.fromisoformat(created.replace("Z", "+00:00"))
            if age > timedelta(days=30):
                score += 2
                reasons.append("longevity_30d(+2)")
            elif age > timedelta(days=7):
                score += 1
                reasons.append("longevity_7d(+1)")
        except (ValueError, TypeError):
            pass

    return score, reasons


SCORERS = {
    "decisions": _score_decision,
    "learned_facts": _score_fact,
    "error_resolutions": _score_resolution,
}


# ============================================================
# CORE FUNCTIONS
# ============================================================

def scan_candidates(threshold=DEFAULT_THRESHOLD) -> List[Dict]:
    """Scan all tables for promotion candidates. Returns scored items."""
    candidates = []
    conn = get_db()
    cursor = conn.cursor()

    # Decisions
    cursor.execute("""
        SELECT * FROM decisions
        WHERE (is_global IS NULL OR is_global = 0) AND status = 'active'
    """)
    for row in cursor.fetchall():
        d = dict(row)
        score, reasons = _score_decision(d)
        if score >= threshold:
            candidates.append({
                "table": "decisions", "id": d["id"],
                "title": d.get("title", "?"),
                "score": score, "reasons": reasons,
                "agent": d.get("created_by"),
            })

    # Learned facts
    cursor.execute("""
        SELECT * FROM learned_facts
        WHERE (is_global IS NULL OR is_global = 0) AND is_active = 1
    """)
    for row in cursor.fetchall():
        d = dict(row)
        score, reasons = _score_fact(d)
        if score >= threshold:
            candidates.append({
                "table": "learned_facts", "id": d["id"],
                "title": truncate(d.get("fact", "?"), 60),
                "score": score, "reasons": reasons,
                "agent": d.get("created_by"),
            })

    # Error resolutions
    cursor.execute("""
        SELECT * FROM error_resolutions
        WHERE (is_global IS NULL OR is_global = 0)
    """)
    for row in cursor.fetchall():
        d = dict(row)
        score, reasons = _score_resolution(d)
        if score >= threshold:
            candidates.append({
                "table": "error_resolutions", "id": d["id"],
                "title": truncate(d.get("error_summary") or d.get("resolution", "?"), 60),
                "score": score, "reasons": reasons,
                "agent": d.get("agent_name"),
            })

    conn.close()

    # Sort by score descending
    candidates.sort(key=lambda x: -x["score"])
    return candidates


def promote(table: str, entity_id: int) -> bool:
    """Promote a single item to global. Returns True if successful."""
    if table not in CROSS_AGENT_TABLES:
        print(f"❌ Tabel invalid: {table}. Valid: {', '.join(CROSS_AGENT_TABLES)}")
        return False

    conn = get_db()
    cursor = conn.cursor()

    # Get agent name for the item
    if table == "error_resolutions":
        cursor.execute(f"SELECT agent_name FROM {table} WHERE id = ?", (entity_id,))
    else:
        cursor.execute(f"SELECT created_by FROM {table} WHERE id = ?", (entity_id,))

    row = cursor.fetchone()
    if not row:
        print(f"❌ {table}#{entity_id} nu există")
        conn.close()
        return False

    agent = row[0] or "unknown"

    cursor.execute(f"""
        UPDATE {table}
        SET is_global = 1, promoted_from_agent = ?
        WHERE id = ?
    """, (agent, entity_id))
    conn.commit()
    conn.close()

    # Log event
    log_agent_event(
        "learning_promoted",
        title=f"Promoted {table}#{entity_id} to global",
        summary=f"Agent: {agent}",
        related_table=table,
        related_id=entity_id,
    )

    return True


def promote_auto(threshold=DEFAULT_THRESHOLD) -> List[Dict]:
    """Auto-promote all candidates above threshold. Returns promoted items."""
    candidates = scan_candidates(threshold)
    promoted = []

    for c in candidates:
        if promote(c["table"], c["id"]):
            promoted.append(c)

    return promoted


def suggest_for_agent(agent_name: str) -> List[Dict]:
    """Return global items promoted by OTHER agents — useful suggestions."""
    conn = get_db()
    cursor = conn.cursor()
    suggestions = []

    # Decisions
    cursor.execute("""
        SELECT id, title, description, category, confidence, promoted_from_agent
        FROM decisions
        WHERE is_global = 1 AND promoted_from_agent != ? AND status = 'active'
        ORDER BY created_at DESC LIMIT 20
    """, (agent_name,))
    for row in cursor.fetchall():
        d = dict(row)
        d["_table"] = "decisions"
        suggestions.append(d)

    # Facts
    cursor.execute("""
        SELECT id, fact, fact_type, confidence, is_pinned, promoted_from_agent
        FROM learned_facts
        WHERE is_global = 1 AND promoted_from_agent != ? AND is_active = 1
        ORDER BY created_at DESC LIMIT 20
    """, (agent_name,))
    for row in cursor.fetchall():
        d = dict(row)
        d["_table"] = "learned_facts"
        suggestions.append(d)

    # Resolutions
    cursor.execute("""
        SELECT id, error_summary, resolution, resolution_type, worked, reuse_count, promoted_from_agent
        FROM error_resolutions
        WHERE is_global = 1 AND promoted_from_agent != ?
        ORDER BY reuse_count DESC, created_at DESC LIMIT 20
    """, (agent_name,))
    for row in cursor.fetchall():
        d = dict(row)
        d["_table"] = "error_resolutions"
        suggestions.append(d)

    conn.close()
    return suggestions


def list_promoted() -> List[Dict]:
    """List all globally promoted items."""
    conn = get_db()
    cursor = conn.cursor()
    items = []

    for table, title_col in [
        ("decisions", "title"),
        ("learned_facts", "fact"),
        ("error_resolutions", "error_summary"),
    ]:
        cursor.execute(f"""
            SELECT id, {title_col} as title, promoted_from_agent, created_at
            FROM {table}
            WHERE is_global = 1
            ORDER BY created_at DESC
        """)
        for row in cursor.fetchall():
            d = dict(row)
            d["_table"] = table
            items.append(d)

    conn.close()
    return items


def stats() -> Dict:
    """Cross-agent learning statistics."""
    conn = get_db()
    cursor = conn.cursor()
    result = {}

    for table in CROSS_AGENT_TABLES:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE is_global = 1")
            promoted = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            total = cursor.fetchone()[0]

            # Unique agents that promoted
            cursor.execute(f"""
                SELECT COUNT(DISTINCT promoted_from_agent)
                FROM {table}
                WHERE is_global = 1 AND promoted_from_agent IS NOT NULL
            """)
            agents = cursor.fetchone()[0]

            result[table] = {
                "total": total,
                "promoted": promoted,
                "promotion_rate": round(promoted / total * 100, 1) if total else 0,
                "unique_agents": agents,
            }
        except Exception:
            result[table] = {"total": 0, "promoted": 0, "promotion_rate": 0, "unique_agents": 0}

    conn.close()

    table_stats = {k: v for k, v in result.items() if k in CROSS_AGENT_TABLES}
    result["total_promoted"] = sum(v["promoted"] for v in table_stats.values())
    result["total_items"] = sum(v["total"] for v in table_stats.values())

    return result


# ============================================================
# CLI
# ============================================================

ENTITY_ICONS = {
    "decisions": "⚖️",
    "learned_facts": "💡",
    "error_resolutions": "🔧",
}


def main():
    parser = argparse.ArgumentParser(description="Cross-Agent Learning — promovare experiențe reutilizabile")
    sub = parser.add_subparsers(dest="command")

    # scan
    p_scan = sub.add_parser("scan", help="Scan promotion candidates")
    p_scan.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    p_scan.add_argument("--json", action="store_true")

    # promote
    p_promote = sub.add_parser("promote", help="Promote a specific item")
    p_promote.add_argument("table", help="Table name")
    p_promote.add_argument("entity_id", type=int, help="Entity ID")

    # promote-auto
    p_auto = sub.add_parser("promote-auto", help="Auto-promote all candidates >= threshold")
    p_auto.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    p_auto.add_argument("--json", action="store_true")

    # suggest
    p_suggest = sub.add_parser("suggest", help="Suggest global items for an agent")
    p_suggest.add_argument("agent_name", help="Agent name")
    p_suggest.add_argument("--json", action="store_true")

    # list
    p_list = sub.add_parser("list", help="List all promoted items")
    p_list.add_argument("--json", action="store_true")

    # stats
    p_stats = sub.add_parser("stats", help="Cross-agent learning statistics")
    p_stats.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "scan":
        candidates = scan_candidates(threshold=args.threshold)
        if args.json:
            print(json.dumps({"candidates": candidates, "count": len(candidates)}, indent=2, default=str))
        else:
            print(f"\n🔍 PROMOTION CANDIDATES (threshold ≥ {args.threshold})")
            print("=" * 70)
            if not candidates:
                print("  (niciun candidat)")
            else:
                for c in candidates:
                    icon = ENTITY_ICONS.get(c["table"], "📄")
                    print(f"  {icon} {c['table']}#{c['id']} [{c['score']}pts] {c['title']}")
                    print(f"     Reasons: {', '.join(c['reasons'])}")
                print(f"\n  Total: {len(candidates)} candidates")

    elif args.command == "promote":
        if promote(args.table, args.entity_id):
            print(f"✅ {args.table}#{args.entity_id} promovat la global")
        else:
            print(f"❌ Promovare eșuată")

    elif args.command == "promote-auto":
        promoted = promote_auto(threshold=args.threshold)
        if args.json:
            print(json.dumps({"promoted": promoted, "count": len(promoted)}, indent=2, default=str))
        else:
            print(f"\n🌟 AUTO-PROMOTE (threshold ≥ {args.threshold})")
            print("=" * 60)
            if not promoted:
                print("  (nimic de promovat)")
            else:
                for p in promoted:
                    icon = ENTITY_ICONS.get(p["table"], "📄")
                    print(f"  {icon} {p['table']}#{p['id']} [{p['score']}pts] {p['title']}")
                print(f"\n  ✅ {len(promoted)} items promovate")

    elif args.command == "suggest":
        suggestions = suggest_for_agent(args.agent_name)
        if args.json:
            print(json.dumps({"suggestions": suggestions, "count": len(suggestions)}, indent=2, default=str))
        else:
            print(f"\n💡 SUGGESTIONS FOR: {args.agent_name}")
            print("=" * 60)
            if not suggestions:
                print("  (nicio sugestie)")
            else:
                for s in suggestions:
                    icon = ENTITY_ICONS.get(s["_table"], "📄")
                    title = s.get("title") or s.get("fact") or s.get("error_summary") or "?"
                    from_agent = s.get("promoted_from_agent", "?")
                    print(f"  {icon} {s['_table']}#{s['id']}: {truncate(title, 50)} (from: {from_agent})")
                print(f"\n  Total: {len(suggestions)} suggestions")

    elif args.command == "list":
        items = list_promoted()
        if args.json:
            print(json.dumps({"promoted": items, "count": len(items)}, indent=2, default=str))
        else:
            print(f"\n🌟 GLOBALLY PROMOTED ITEMS")
            print("=" * 60)
            if not items:
                print("  (nimic promovat)")
            else:
                for item in items:
                    icon = ENTITY_ICONS.get(item["_table"], "📄")
                    title = truncate(item.get("title", "?"), 50)
                    from_agent = item.get("promoted_from_agent", "?")
                    ts = format_timestamp(item.get("created_at"))
                    print(f"  {icon} {item['_table']}#{item['id']} {title} (from: {from_agent}, {ts})")
                print(f"\n  Total: {len(items)} items")

    elif args.command == "stats":
        s = stats()
        if args.json:
            print(json.dumps(s, indent=2, default=str))
        else:
            print(f"\n📊 CROSS-AGENT LEARNING STATS")
            print("=" * 60)
            for table in CROSS_AGENT_TABLES:
                t = s.get(table, {})
                icon = ENTITY_ICONS.get(table, "📄")
                print(f"  {icon} {table}: {t['promoted']}/{t['total']} promoted ({t['promotion_rate']}%), {t['unique_agents']} agents")
            print(f"\n  Total: {s['total_promoted']}/{s['total_items']} items promoted globally")


if __name__ == "__main__":
    main()
