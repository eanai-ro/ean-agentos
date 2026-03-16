#!/usr/bin/env python3
"""
Memory Cleanup - Detectează și marchează entries stale.

NU șterge nimic. Doar raportează și opțional marchează stale.

Detectează:
- Facts inactive >180 zile
- Tasks abandonade (todo >90 zile fără activitate)
- Resolutions obsolete (worked=0 >60 zile)
- Goals stagnante (active >180 zile fără progres)

Comenzi:
    memory_cleanup.py report          Raport complet (doar detectare)
    memory_cleanup.py mark            Marchează stale (dezactivează facts, cancel tasks)
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import get_db, truncate, get_current_project_path

# Thresholds (zile)
FACT_STALE_DAYS = 180
TASK_STALE_DAYS = 90
RESOLUTION_STALE_DAYS = 60
GOAL_STALE_DAYS = 180


def _age_days(ts_str):
    if not ts_str:
        return 999
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now() - dt.replace(tzinfo=None)).days
    except (ValueError, TypeError):
        return 999


def detect_stale_facts(cursor):
    """Facts active dar vechi și nepinned."""
    cursor.execute("""
        SELECT id, fact, fact_type, created_at, is_pinned
        FROM learned_facts
        WHERE is_active = 1 AND is_pinned = 0
    """)
    stale = []
    for row in cursor.fetchall():
        age = _age_days(row["created_at"])
        if age > FACT_STALE_DAYS:
            stale.append({"id": row["id"], "fact": row["fact"], "type": row["fact_type"],
                          "age_days": age})
    return stale


def detect_stale_tasks(cursor):
    """Tasks todo >90 zile fără activitate."""
    cursor.execute("""
        SELECT id, title, priority, status, created_at, updated_at
        FROM tasks
        WHERE status = 'todo'
    """)
    stale = []
    for row in cursor.fetchall():
        last_activity = row["updated_at"] or row["created_at"]
        age = _age_days(last_activity)
        if age > TASK_STALE_DAYS:
            stale.append({"id": row["id"], "title": row["title"], "priority": row["priority"],
                          "age_days": age})
    return stale


def detect_stale_resolutions(cursor):
    """Resolutions cu worked=0 >60 zile."""
    cursor.execute("""
        SELECT id, error_summary, resolution, created_at
        FROM error_resolutions
        WHERE worked = 0 OR worked IS NULL
    """)
    stale = []
    for row in cursor.fetchall():
        age = _age_days(row["created_at"])
        if age > RESOLUTION_STALE_DAYS:
            stale.append({"id": row["id"], "error": row["error_summary"],
                          "resolution": row["resolution"], "age_days": age})
    return stale


def detect_stale_goals(cursor):
    """Goals active >180 zile fără progres."""
    cursor.execute("""
        SELECT g.id, g.title, g.priority, g.created_at,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id) as total_tasks,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.status = 'done') as done_tasks
        FROM goals g
        WHERE g.status = 'active'
    """)
    stale = []
    for row in cursor.fetchall():
        age = _age_days(row["created_at"])
        total = row["total_tasks"] or 0
        done = row["done_tasks"] or 0
        # Stale: >180 zile AND (0 tasks OR 0 progress)
        if age > GOAL_STALE_DAYS and (total == 0 or done == 0):
            stale.append({"id": row["id"], "title": row["title"], "priority": row["priority"],
                          "age_days": age, "tasks": f"{done}/{total}"})
    return stale


def cmd_report(args):
    """Raport complet — doar detectare, fără modificări."""
    conn = get_db()
    cursor = conn.cursor()

    stale_facts = detect_stale_facts(cursor)
    stale_tasks = detect_stale_tasks(cursor)
    stale_resolutions = detect_stale_resolutions(cursor)
    stale_goals = detect_stale_goals(cursor)

    conn.close()

    print(f"\n{'='*50}")
    print(f"  MEMORY CLEANUP REPORT")
    print(f"{'='*50}\n")

    total = len(stale_facts) + len(stale_tasks) + len(stale_resolutions) + len(stale_goals)

    if stale_facts:
        print(f"📝 Facts stale ({len(stale_facts)}, >{FACT_STALE_DAYS}d, nepinned):")
        for f in stale_facts[:10]:
            print(f"  #{f['id']} [{f['type']}] {f['age_days']}d: {truncate(f['fact'], 40)}")
    else:
        print("✅ Facts: 0 stale")

    print()

    if stale_tasks:
        print(f"📋 Tasks stale ({len(stale_tasks)}, todo >{TASK_STALE_DAYS}d):")
        for t in stale_tasks[:10]:
            print(f"  #{t['id']} [{t['priority']}] {t['age_days']}d: {truncate(t['title'], 40)}")
    else:
        print("✅ Tasks: 0 stale")

    print()

    if stale_resolutions:
        print(f"🔧 Resolutions stale ({len(stale_resolutions)}, worked=0 >{RESOLUTION_STALE_DAYS}d):")
        for r in stale_resolutions[:10]:
            print(f"  #{r['id']} {r['age_days']}d: {truncate(r['resolution'], 40)}")
    else:
        print("✅ Resolutions: 0 stale")

    print()

    if stale_goals:
        print(f"🎯 Goals stagnante ({len(stale_goals)}, active >{GOAL_STALE_DAYS}d fără progres):")
        for g in stale_goals[:10]:
            print(f"  #{g['id']} [{g['priority']}] {g['age_days']}d ({g['tasks']}): {truncate(g['title'], 35)}")
    else:
        print("✅ Goals: 0 stagnante")

    print(f"\n--- Total: {total} entries stale ---")
    if total > 0:
        print("   Rulează `mem cleanup mark` pentru a marca stale.")

    return {"facts": stale_facts, "tasks": stale_tasks,
            "resolutions": stale_resolutions, "goals": stale_goals}


def cmd_mark(args):
    """Marchează stale: dezactivează facts, cancel tasks."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    stale_facts = detect_stale_facts(cursor)
    stale_tasks = detect_stale_tasks(cursor)

    marked = 0

    for f in stale_facts:
        cursor.execute("UPDATE learned_facts SET is_active = 0, updated_at = ? WHERE id = ?",
                       (now, f["id"]))
        marked += 1

    for t in stale_tasks:
        cursor.execute("UPDATE tasks SET status = 'cancelled', updated_at = ? WHERE id = ?",
                       (now, t["id"]))
        marked += 1

    conn.commit()
    conn.close()

    if marked:
        print(f"✅ {marked} entries marcate stale ({len(stale_facts)} facts dezactivate, {len(stale_tasks)} tasks cancelled)")
    else:
        print("  (nimic de marcat)")


def fetch_stale_summary_for_context(cursor):
    """Sumarizare stale pentru context builder."""
    stale_facts = detect_stale_facts(cursor)
    stale_tasks = detect_stale_tasks(cursor)
    stale_goals = detect_stale_goals(cursor)
    total = len(stale_facts) + len(stale_tasks) + len(stale_goals)
    if total == 0:
        return ""
    return f"Stale: {len(stale_facts)} facts, {len(stale_tasks)} tasks, {len(stale_goals)} goals"


def main():
    parser = argparse.ArgumentParser(description="Memory Cleanup")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("report", help="Raport (doar detectare)")
    sub.add_parser("mark", help="Marchează stale")

    args = parser.parse_args()

    if args.command == "report":
        cmd_report(args)
    elif args.command == "mark":
        cmd_mark(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    main()
