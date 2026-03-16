#!/usr/bin/env python3
"""
Memory Scoring — calcul transparent de confidence_score pentru entități.

Formula:
  confidence_score = (
      base_confidence     # 0-30: confirmed=30, high=20, medium=10, low=5
    + success_component   # 0-25: worked * 25 (resolutions) sau status=active * 15
    + reuse_component     # 0-20: min(usage_count * 5, 20)
    + agent_weight_adj    # 0-15: agent_reputation.weight * 10 (cap 15)
    + recency_score       # 0-10: 10 dacă <7d, 7 dacă <30d, 3 dacă <90d, 1 altfel
  )
  Total maxim teoretic: 100

Toate componentele sunt explicabile individual.

CLI: memory_scoring.py score <table> <id> | score-all | recalc-agents | show-agents [--json]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from v2_common import get_db, format_timestamp, truncate, DEFAULT_AGENT_WEIGHT


# ============================================================
# AGENT REPUTATION
# ============================================================

def get_agent_weight(agent_name: str) -> float:
    """Get agent weight from reputation table. Default 1.0."""
    if not agent_name:
        return DEFAULT_AGENT_WEIGHT
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT weight FROM agent_reputation WHERE agent_name = ?", (agent_name,))
        row = cursor.fetchone()
        conn.close()
        return row["weight"] if row else DEFAULT_AGENT_WEIGHT
    except Exception:
        return DEFAULT_AGENT_WEIGHT


def recalc_agent_reputation():
    """Recalculate all agent reputations from contributions."""
    conn = get_db()
    cursor = conn.cursor()

    # Gather all agent contributions
    agents = {}

    # From decisions
    cursor.execute("SELECT created_by, status FROM decisions WHERE created_by IS NOT NULL")
    for row in cursor.fetchall():
        agent = row["created_by"]
        if agent in ("user", "api"):
            continue
        if agent not in agents:
            agents[agent] = {"total": 0, "success": 0, "failed": 0, "promoted": 0}
        agents[agent]["total"] += 1
        if row["status"] == "active":
            agents[agent]["success"] += 1
        elif row["status"] in ("superseded", "archived"):
            agents[agent]["failed"] += 1

    # From learned_facts
    cursor.execute("SELECT created_by, is_active, is_pinned, is_global FROM learned_facts WHERE created_by IS NOT NULL")
    for row in cursor.fetchall():
        agent = row["created_by"]
        if agent in ("user", "api"):
            continue
        if agent not in agents:
            agents[agent] = {"total": 0, "success": 0, "failed": 0, "promoted": 0}
        agents[agent]["total"] += 1
        if row["is_active"]:
            agents[agent]["success"] += 1
        else:
            agents[agent]["failed"] += 1
        if row["is_global"]:
            agents[agent]["promoted"] += 1

    # From error_resolutions
    cursor.execute("SELECT agent_name, worked, is_global FROM error_resolutions WHERE agent_name IS NOT NULL")
    for row in cursor.fetchall():
        agent = row["agent_name"]
        if agent in ("user", "api"):
            continue
        if agent not in agents:
            agents[agent] = {"total": 0, "success": 0, "failed": 0, "promoted": 0}
        agents[agent]["total"] += 1
        if row["worked"]:
            agents[agent]["success"] += 1
        else:
            agents[agent]["failed"] += 1
        if row["is_global"]:
            agents[agent]["promoted"] += 1

    # Calculate weights and upsert
    results = []
    for agent, stats in agents.items():
        total = stats["total"]
        success = stats["success"]
        promoted = stats["promoted"]

        # Weight formula: base 1.0 + success_rate_bonus + promotion_bonus
        # success_rate: 0.0 to 0.5 bonus
        # promoted: 0.1 per promoted item, capped at 0.5
        success_rate = success / total if total > 0 else 0
        weight = 1.0 + (success_rate * 0.5) + min(promoted * 0.1, 0.5)
        weight = round(min(weight, 2.0), 3)  # Cap at 2.0

        cursor.execute("""
            INSERT INTO agent_reputation (agent_name, total_contributions, successful_contributions,
                failed_contributions, promoted_count, weight, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(agent_name) DO UPDATE SET
                total_contributions = ?,
                successful_contributions = ?,
                failed_contributions = ?,
                promoted_count = ?,
                weight = ?,
                last_updated = datetime('now')
        """, (agent, total, success, stats["failed"], promoted, weight,
              total, success, stats["failed"], promoted, weight))

        results.append({
            "agent": agent, "total": total, "success": success,
            "failed": stats["failed"], "promoted": promoted,
            "success_rate": round(success_rate * 100, 1),
            "weight": weight,
        })

    conn.commit()
    conn.close()
    return sorted(results, key=lambda x: -x["weight"])


def list_agents() -> List[Dict]:
    """List all agent reputations."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_reputation ORDER BY weight DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ============================================================
# SCORING ENGINE
# ============================================================

def _recency_score(created_at: str) -> Tuple[float, str]:
    """Calculate recency score (0-10) from timestamp."""
    if not created_at:
        return 1.0, ">90d"
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age = datetime.now() - dt.replace(tzinfo=None)
        if age < timedelta(days=7):
            return 10.0, "<7d"
        elif age < timedelta(days=30):
            return 7.0, "<30d"
        elif age < timedelta(days=90):
            return 3.0, "<90d"
        else:
            return 1.0, ">90d"
    except (ValueError, TypeError):
        return 1.0, "unknown"


def score_decision(decision: Dict) -> Dict:
    """Score a decision. Returns breakdown dict."""
    # Base confidence
    conf = decision.get("confidence", "medium")
    base = {"confirmed": 30, "high": 20, "medium": 10, "low": 5}.get(conf, 10)

    # Success: active decisions are successful
    status = decision.get("status", "active")
    success = 15 if status == "active" else (5 if status == "reconsidered" else 0)

    # Reuse: not directly applicable, use 0
    reuse = 0

    # Agent weight
    agent = decision.get("created_by", "user")
    agent_w = get_agent_weight(agent)
    agent_adj = min(round(agent_w * 10, 1), 15)

    # Recency
    recency, recency_label = _recency_score(decision.get("created_at"))

    total = round(base + success + reuse + agent_adj + recency, 1)

    return {
        "total": min(total, 100),
        "base_confidence": base,
        "success_component": success,
        "reuse_component": reuse,
        "agent_weight_adj": agent_adj,
        "recency_score": recency,
        "recency_label": recency_label,
        "agent": agent,
        "agent_raw_weight": agent_w,
    }


def score_fact(fact: Dict) -> Dict:
    """Score a learned fact."""
    conf = fact.get("confidence", "medium")
    base = {"confirmed": 30, "high": 20, "medium": 10, "low": 5}.get(conf, 10)

    # Success: active + pinned = high success
    is_active = fact.get("is_active", 1)
    is_pinned = fact.get("is_pinned", 0)
    success = (15 if is_active else 0) + (10 if is_pinned else 0)
    success = min(success, 25)

    # Reuse: check if referenced in other entities (simplified: pinned = reused)
    reuse = 10 if is_pinned else 0

    # Agent weight
    agent = fact.get("created_by", "user")
    agent_w = get_agent_weight(agent)
    agent_adj = min(round(agent_w * 10, 1), 15)

    # Recency
    recency, recency_label = _recency_score(fact.get("created_at"))

    total = round(base + success + reuse + agent_adj + recency, 1)

    return {
        "total": min(total, 100),
        "base_confidence": base,
        "success_component": success,
        "reuse_component": reuse,
        "agent_weight_adj": agent_adj,
        "recency_score": recency,
        "recency_label": recency_label,
        "agent": agent,
        "agent_raw_weight": agent_w,
    }


def score_resolution(resolution: Dict) -> Dict:
    """Score an error resolution."""
    # Base: worked status as confidence proxy
    worked = resolution.get("worked", 0)
    base = 30 if worked else 5

    # Success: worked directly
    success = 25 if worked else 0

    # Reuse
    reuse_count = resolution.get("reuse_count", 0) or 0
    reuse = min(reuse_count * 5, 20)

    # Agent weight
    agent = resolution.get("agent_name") or resolution.get("created_by", "user")
    agent_w = get_agent_weight(agent)
    agent_adj = min(round(agent_w * 10, 1), 15)

    # Recency
    recency, recency_label = _recency_score(resolution.get("created_at"))

    total = round(base + success + reuse + agent_adj + recency, 1)

    return {
        "total": min(total, 100),
        "base_confidence": base,
        "success_component": success,
        "reuse_component": reuse,
        "agent_weight_adj": agent_adj,
        "recency_score": recency,
        "recency_label": recency_label,
        "agent": agent,
        "agent_raw_weight": agent_w,
    }


SCORERS = {
    "decisions": score_decision,
    "learned_facts": score_fact,
    "error_resolutions": score_resolution,
}


def score_entity(table: str, entity_id: int) -> Optional[Dict]:
    """Score a specific entity by table and ID."""
    if table not in SCORERS:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (entity_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    entity = dict(row)
    breakdown = SCORERS[table](entity)
    breakdown["table"] = table
    breakdown["id"] = entity_id
    breakdown["title"] = (entity.get("title") or entity.get("fact") or
                          entity.get("error_summary") or "?")[:60]
    return breakdown


def score_all(table: str = None, limit: int = 50) -> List[Dict]:
    """Score all entities (or one table). Returns sorted by score."""
    tables = [table] if table and table in SCORERS else list(SCORERS.keys())
    results = []

    conn = get_db()
    cursor = conn.cursor()

    for tbl in tables:
        # Only active/relevant items
        if tbl == "decisions":
            cursor.execute("SELECT * FROM decisions WHERE status = 'active' ORDER BY created_at DESC LIMIT ?", (limit,))
        elif tbl == "learned_facts":
            cursor.execute("SELECT * FROM learned_facts WHERE is_active = 1 ORDER BY created_at DESC LIMIT ?", (limit,))
        elif tbl == "error_resolutions":
            cursor.execute("SELECT * FROM error_resolutions ORDER BY created_at DESC LIMIT ?", (limit,))

        for row in cursor.fetchall():
            entity = dict(row)
            breakdown = SCORERS[tbl](entity)
            breakdown["table"] = tbl
            breakdown["id"] = entity["id"]
            breakdown["title"] = (entity.get("title") or entity.get("fact") or
                                  entity.get("error_summary") or "?")[:60]
            results.append(breakdown)

    conn.close()
    results.sort(key=lambda x: -x["total"])
    return results


# ============================================================
# CLI
# ============================================================

ENTITY_ICONS = {
    "decisions": "⚖️",
    "learned_facts": "💡",
    "error_resolutions": "🔧",
}


def main():
    parser = argparse.ArgumentParser(description="Memory Scoring — calcul confidence transparent")
    sub = parser.add_subparsers(dest="command")

    # score <table> <id>
    p_score = sub.add_parser("score", help="Score a specific entity")
    p_score.add_argument("table", help="Table name")
    p_score.add_argument("entity_id", type=int, help="Entity ID")
    p_score.add_argument("--json", action="store_true")

    # score-all
    p_all = sub.add_parser("score-all", help="Score all active entities")
    p_all.add_argument("--table", help="Filter by table")
    p_all.add_argument("--limit", type=int, default=50)
    p_all.add_argument("--json", action="store_true")

    # recalc-agents
    p_recalc = sub.add_parser("recalc-agents", help="Recalculate agent reputations")
    p_recalc.add_argument("--json", action="store_true")

    # show-agents
    p_agents = sub.add_parser("show-agents", help="Show agent reputations")
    p_agents.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "score":
        result = score_entity(args.table, args.entity_id)
        if not result:
            print(f"❌ {args.table}#{args.entity_id} nu există sau tabel invalid")
            return
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            icon = ENTITY_ICONS.get(args.table, "📄")
            print(f"\n{icon} SCORE: {args.table}#{args.entity_id}")
            print(f"   {result['title']}")
            print(f"   ────────────────────────────────")
            print(f"   Confidence Score: {result['total']}/100")
            print(f"   ├─ Base confidence:   {result['base_confidence']}/30")
            print(f"   ├─ Success component: {result['success_component']}/25")
            print(f"   ├─ Reuse component:   {result['reuse_component']}/20")
            print(f"   ├─ Agent weight adj:  {result['agent_weight_adj']}/15 (agent={result['agent']}, w={result['agent_raw_weight']})")
            print(f"   └─ Recency score:     {result['recency_score']}/10 ({result['recency_label']})")

    elif args.command == "score-all":
        results = score_all(table=args.table, limit=args.limit)
        if args.json:
            print(json.dumps({"scores": results, "count": len(results)}, indent=2, default=str))
        else:
            print(f"\n📊 MEMORY SCORES (top {args.limit})")
            print("=" * 70)
            if not results:
                print("  (nicio entitate)")
            else:
                for r in results:
                    icon = ENTITY_ICONS.get(r["table"], "📄")
                    title = truncate(r["title"], 40)
                    print(f"  {icon} {r['total']:5.1f}  {r['table']}#{r['id']:<4}  {title}")
                print(f"\n  Total: {len(results)} entities scored")

    elif args.command == "recalc-agents":
        results = recalc_agent_reputation()
        if args.json:
            print(json.dumps({"agents": results}, indent=2, default=str))
        else:
            print(f"\n🤖 AGENT REPUTATION RECALCULATED")
            print("=" * 70)
            if not results:
                print("  (niciun agent)")
            else:
                print(f"  {'Agent':<25} {'Weight':>7} {'Success%':>9} {'Total':>6} {'Promoted':>9}")
                print(f"  {'-'*25} {'-'*7} {'-'*9} {'-'*6} {'-'*9}")
                for r in results:
                    print(f"  {r['agent']:<25} {r['weight']:>7.3f} {r['success_rate']:>8.1f}% {r['total']:>6} {r['promoted']:>9}")

    elif args.command == "show-agents":
        agents = list_agents()
        if args.json:
            print(json.dumps({"agents": agents}, indent=2, default=str))
        else:
            print(f"\n🤖 AGENT REPUTATIONS")
            print("=" * 60)
            if not agents:
                print("  (niciun agent — rulează: mem score recalc-agents)")
            else:
                for a in agents:
                    sr = (a["successful_contributions"] / a["total_contributions"] * 100
                          if a["total_contributions"] else 0)
                    print(f"  {a['agent_name']:<25} w={a['weight']:.3f}  "
                          f"{a['successful_contributions']}/{a['total_contributions']} ({sr:.0f}%)  "
                          f"promoted={a['promoted_count']}")


if __name__ == "__main__":
    main()
