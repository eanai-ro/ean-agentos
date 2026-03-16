#!/usr/bin/env python3
"""
Dashboard CLI - Vedere rapidă asupra stării memoriei proiectului curent.

Utilizare:
    dashboard_cli.py              Dashboard text (default)
    dashboard_cli.py --json       Output JSON
    dashboard_cli.py --project P  Dashboard pentru alt proiect
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import (
    get_db, truncate, format_timestamp, get_current_project_path,
    get_current_model, get_current_intent, SNAPSHOT_FILE,
)


def _age_str(ts_str):
    """Timestamp → '2h ago', '3d ago', etc."""
    if not ts_str:
        return "—"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = datetime.now() - dt.replace(tzinfo=None)
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        return f"{days // 30}mo ago"
    except (ValueError, TypeError):
        return "—"


def _snapshot_status():
    """Status snapshot cache."""
    if not SNAPSHOT_FILE.exists():
        return "none"
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        gen_at = data.get("meta", {}).get("generated_at")
        if gen_at:
            return _age_str(gen_at)
    except Exception:
        pass
    return "invalid"


def build_dashboard(project_path=None, output_json=False):
    """Construiește și afișează dashboard-ul."""
    project_path = project_path or get_current_project_path()
    proj_name = project_path.split("/")[-1] if "/" in project_path else project_path

    conn = get_db()
    cursor = conn.cursor()

    result = {}

    # === 1. PROJECT SUMMARY ===
    model_id, provider = get_current_model()
    intent = get_current_intent()

    # Last checkpoint
    last_chk = None
    try:
        cursor.execute(
            "SELECT id, name, created_at FROM memory_checkpoints WHERE project_path=? ORDER BY created_at DESC LIMIT 1",
            (project_path,))
        row = cursor.fetchone()
        if row:
            last_chk = {"id": row["id"], "name": row["name"], "age": _age_str(row["created_at"])}
    except Exception:
        pass

    result["summary"] = {
        "project_name": proj_name,
        "project_path": project_path,
        "model": model_id,
        "intent": intent or "none",
        "last_checkpoint": last_chk,
        "snapshot": _snapshot_status(),
    }

    # === 2. ACTIVE DECISIONS ===
    cursor.execute("""
        SELECT d.id, d.title, d.category, d.confidence, d.created_at
        FROM decisions d
        WHERE d.status='active' AND d.project_path=?
        ORDER BY d.created_at DESC LIMIT 5
    """, (project_path,))
    decisions = [dict(r) for r in cursor.fetchall()]

    # Conflict check (simple: same category, word overlap)
    conflict_ids = set()
    try:
        from decision_analyzer import detect_conflicts
        conflicts = detect_conflicts(cursor, project_path)
        for c in conflicts:
            conflict_ids.add(c.get("id_a"))
            conflict_ids.add(c.get("id_b"))
    except Exception:
        pass

    for d in decisions:
        d["has_conflict"] = d["id"] in conflict_ids

    result["decisions"] = decisions

    # === 3. PINNED / PROMOTED FACTS ===
    cursor.execute("""
        SELECT id, fact, fact_type, is_pinned, confidence
        FROM learned_facts
        WHERE is_active=1 AND project_path=?
        ORDER BY is_pinned DESC, created_at DESC LIMIT 8
    """, (project_path,))
    result["facts"] = [dict(r) for r in cursor.fetchall()]

    # === 4. GOALS ===
    cursor.execute("""
        SELECT g.id, g.title, g.priority, g.target_date,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id) as total_tasks,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id AND t.status='done') as done_tasks
        FROM goals g
        WHERE g.status='active' AND g.project_path=?
        ORDER BY CASE g.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT 5
    """, (project_path,))
    result["goals"] = [dict(r) for r in cursor.fetchall()]

    # === 5. TASKS ===
    cursor.execute("""
        SELECT id, title, priority, status, goal_id, blocked_by
        FROM tasks
        WHERE status IN ('in_progress','blocked','todo') AND project_path=?
        ORDER BY
            CASE status WHEN 'in_progress' THEN 0 WHEN 'blocked' THEN 1 WHEN 'todo' THEN 2 END,
            CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT 8
    """, (project_path,))
    result["tasks"] = [dict(r) for r in cursor.fetchall()]

    # === 6. ERROR INTELLIGENCE ===
    # Recent resolutions
    cursor.execute("""
        SELECT id, error_summary, resolution, worked
        FROM error_resolutions
        WHERE project_path=? AND worked=1
        ORDER BY created_at DESC LIMIT 3
    """, (project_path,))
    result["resolutions"] = [dict(r) for r in cursor.fetchall()]

    # Error patterns
    cursor.execute("""
        SELECT id, error_signature, solution, count
        FROM error_patterns
        WHERE project_path=?
        ORDER BY count DESC LIMIT 3
    """, (project_path,))
    result["patterns"] = [dict(r) for r in cursor.fetchall()]

    # === 6B. AGENT ACTIVITY RECENT ===
    try:
        cursor.execute("""
            SELECT agent_name, model_id, action_type, action_summary, success, created_at
            FROM agent_activity_log
            WHERE project_path=? AND created_at>=?
            ORDER BY created_at DESC LIMIT 5
        """, (project_path, since))
        result["activity_recent"] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        result["activity_recent"] = []

    # === 7. TIMELINE RECENT ===
    events = []
    since = (datetime.now() - timedelta(days=7)).isoformat()

    try:
        cursor.execute(
            "SELECT event_type, title, created_at FROM timeline_events WHERE project_path=? AND created_at>=? ORDER BY created_at DESC LIMIT 5",
            (project_path, since))
        for r in cursor.fetchall():
            events.append({"type": r["event_type"], "title": r["title"], "date": r["created_at"]})
    except Exception:
        pass

    cursor.execute(
        "SELECT title, created_at FROM decisions WHERE project_path=? AND created_at>=? ORDER BY created_at DESC LIMIT 3",
        (project_path, since))
    for r in cursor.fetchall():
        events.append({"type": "decision", "title": f"Decision: {r['title']}", "date": r["created_at"]})

    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    result["timeline"] = events[:8]

    # === 8. MEMORY HEALTH ===
    health = {}
    for table, col, where in [
        ("decisions", "status='active'", "project_path=?"),
        ("learned_facts", "is_active=1", "project_path=?"),
        ("goals", "status='active'", "project_path=?"),
        ("tasks", "status IN ('todo','in_progress','blocked')", "project_path=?"),
    ]:
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} AND {where}", (project_path,))
        health[table] = cursor.fetchone()[0]

    try:
        cursor.execute("SELECT COUNT(*) FROM error_patterns WHERE project_path=?", (project_path,))
        health["error_patterns"] = cursor.fetchone()[0]
    except Exception:
        health["error_patterns"] = 0

    try:
        cursor.execute("SELECT COUNT(*) FROM memory_checkpoints WHERE project_path=?", (project_path,))
        health["checkpoints"] = cursor.fetchone()[0]
    except Exception:
        health["checkpoints"] = 0

    # Stale counts
    stale = {}
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM learned_facts WHERE is_active=1 AND is_pinned=0 AND project_path=? AND created_at < datetime('now', '-180 days')",
            (project_path,))
        stale["facts"] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='todo' AND project_path=? AND created_at < datetime('now', '-90 days')",
            (project_path,))
        stale["tasks"] = cursor.fetchone()[0]
    except Exception:
        pass
    health["stale"] = stale

    result["health"] = health

    conn.close()

    # === OUTPUT ===
    if output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return result

    _print_dashboard(result)
    return result


def _print_dashboard(data):
    """Afișare text dashboard."""
    W = 60

    # Header
    s = data["summary"]
    print(f"\n{'═' * W}")
    print(f"  📊 MEMORY DASHBOARD — {s['project_name']}")
    print(f"{'═' * W}")
    print(f"  Model: {s['model']:<20} Intent: {s['intent']}")
    chk = s.get("last_checkpoint")
    chk_str = f"{chk['name']} ({chk['age']})" if chk else "none"
    print(f"  Checkpoint: {chk_str:<22} Snapshot: {s['snapshot']}")
    print()

    # Decisions
    decisions = data.get("decisions", [])
    if decisions:
        print(f"  📋 Decisions ({len(decisions)})")
        print(f"  {'─' * (W - 2)}")
        for d in decisions:
            conflict = " ⚠" if d.get("has_conflict") else ""
            print(f"    #{d['id']:>3} [{d['category'][:4]}] {truncate(d['title'], 38)}{conflict}")
        print()

    # Facts
    facts = data.get("facts", [])
    if facts:
        print(f"  ⭐ Facts ({len(facts)})")
        print(f"  {'─' * (W - 2)}")
        for f in facts:
            pin = "📌" if f["is_pinned"] else "  "
            print(f"    #{f['id']:>3} {pin} [{f['fact_type'][:4]}] {truncate(f['fact'], 38)}")
        print()

    # Goals
    goals = data.get("goals", [])
    if goals:
        print(f"  🎯 Goals ({len(goals)})")
        print(f"  {'─' * (W - 2)}")
        for g in goals:
            total = g.get("total_tasks") or 0
            done = g.get("done_tasks") or 0
            prog = f" ({done}/{total})" if total else ""
            print(f"    #{g['id']:>3} [{g['priority'][:3]}] {truncate(g['title'], 35)}{prog}")
        print()

    # Tasks
    tasks = data.get("tasks", [])
    if tasks:
        icons = {"in_progress": "▶", "blocked": "⛔", "todo": "○"}
        print(f"  ✅ Tasks ({len(tasks)})")
        print(f"  {'─' * (W - 2)}")
        for t in tasks:
            icon = icons.get(t["status"], "?")
            print(f"    #{t['id']:>3} {icon} [{t['priority'][:3]}] {truncate(t['title'], 36)}")
        print()

    # Error Intelligence
    resolutions = data.get("resolutions", [])
    patterns = data.get("patterns", [])
    if resolutions or patterns:
        print(f"  🔍 Error Intelligence")
        print(f"  {'─' * (W - 2)}")
        for r in resolutions:
            err = truncate(r.get("error_summary") or "?", 18)
            fix = truncate(r["resolution"], 28)
            print(f"    ✓ {err} → {fix}")
        for p in patterns:
            print(f"    ↻ x{p['count']} {truncate(p['error_signature'], 38)}")
        print()

    # Activity
    activity = data.get("activity_recent", [])
    if activity:
        print(f"  🤖 Agent Activity ({len(activity)})")
        print(f"  {'─' * (W - 2)}")
        for a in activity:
            ok = "✓" if a.get("success") else "✗"
            agent = a.get("agent_name") or a.get("model_id") or "?"
            print(f"    {ok} [{agent[:10]}] {truncate(a.get('action_summary', ''), 38)}")
        print()

    # Timeline
    timeline = data.get("timeline", [])
    if timeline:
        ticons = {"checkpoint_create": "📌", "checkpoint_restore": "♻️",
                  "decision": "📋", "fact_promoted": "⭐", "pattern_detected": "🔍"}
        print(f"  📅 Recent (7d)")
        print(f"  {'─' * (W - 2)}")
        for ev in timeline[:6]:
            icon = ticons.get(ev["type"], "•")
            date = (ev.get("date") or "")[:10]
            print(f"    {date} {icon} {truncate(ev['title'], 40)}")
        print()

    # Health
    h = data.get("health", {})
    stale = h.get("stale", {})
    stale_str = ""
    stale_items = [(k, v) for k, v in stale.items() if v > 0]
    if stale_items:
        stale_str = " | stale: " + ", ".join(f"{v} {k}" for k, v in stale_items)

    print(f"  💊 Health")
    print(f"  {'─' * (W - 2)}")
    print(f"    decisions: {h.get('decisions', 0)}  facts: {h.get('learned_facts', 0)}  goals: {h.get('goals', 0)}  tasks: {h.get('tasks', 0)}")
    print(f"    patterns: {h.get('error_patterns', 0)}  checkpoints: {h.get('checkpoints', 0)}{stale_str}")

    print(f"\n{'═' * W}\n")


def main():
    parser = argparse.ArgumentParser(description="Memory Dashboard")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--project", "-p", help="Path proiect (default: curent)")
    args = parser.parse_args()

    build_dashboard(project_path=args.project, output_json=args.json)


if __name__ == "__main__":
    main()
