#!/usr/bin/env python3
"""
Branch Manager — Memory Branches CLI.

Comenzi:
    branch create <name> [-d "description"] [--from <parent>]
    branch list
    branch current
    branch switch <name>
    branch diff <branch_a> <branch_b>
    branch compare <branch_a> <branch_b>
    branch replay <name> [--days N] [--limit N]
    branch merge <source> [--into <target>] [--strategy merge|replace]
    branch conflicts <branch_a> <branch_b>
    branch delete <name>
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import (
    get_db, get_current_project_path, get_current_branch, set_current_branch,
    clear_current_branch, BRANCH_ENTITY_TABLES, truncate, format_timestamp,
)


def _project():
    return get_current_project_path()


def _ensure_branch_exists(conn, name, project):
    """Verifică că un branch există. Returnează True/False."""
    if name == "main":
        return True  # main există implicit
    c = conn.cursor()
    c.execute("SELECT id FROM memory_branches WHERE name=? AND project_path=? AND is_active=1",
              (name, project))
    return c.fetchone() is not None


def cmd_create(args):
    """Creează un branch nou."""
    parser = argparse.ArgumentParser(prog="mem branch create")
    parser.add_argument("name", help="Numele branch-ului")
    parser.add_argument("-d", "--description", default="", help="Descriere")
    parser.add_argument("--from", dest="parent", default=None, help="Branch-ul părinte (default: curent)")
    opts = parser.parse_args(args)

    name = opts.name.strip()
    if not name or name == "main":
        print("❌ Numele branch-ului este invalid sau 'main' (rezervat).")
        return False

    project = _project()
    parent = opts.parent or get_current_branch()

    conn = get_db()
    if not _ensure_branch_exists(conn, parent, project):
        print(f"❌ Branch-ul părinte '{parent}' nu există.")
        conn.close()
        return False

    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO memory_branches (name, project_path, parent_branch, description, created_by)
            VALUES (?, ?, ?, ?, 'user')
        """, (name, project, parent, opts.description or None))
        conn.commit()
        print(f"✅ Branch '{name}' creat (parent: {parent})")
        conn.close()
        return True
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            print(f"❌ Branch '{name}' există deja.")
        else:
            print(f"❌ Eroare: {e}")
        conn.close()
        return False


def cmd_list(args):
    """Listează toate branch-urile."""
    project = _project()
    current = get_current_branch()
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT name, parent_branch, description, created_at
        FROM memory_branches
        WHERE project_path=? AND is_active=1
        ORDER BY created_at
    """, (project,))
    rows = [dict(r) for r in c.fetchall()]

    # Count entities per branch
    branch_counts = {}
    for table in BRANCH_ENTITY_TABLES:
        try:
            c.execute(f"SELECT branch, COUNT(*) FROM {table} WHERE project_path=? GROUP BY branch",
                      (project,))
            for row in c.fetchall():
                b = row[0] or "main"
                branch_counts.setdefault(b, 0)
                branch_counts[b] += row[1]
        except Exception:
            pass

    conn.close()

    # Always show main first
    print(f"\n{'='*50}")
    print(f"  MEMORY BRANCHES — {project.split('/')[-1]}")
    print(f"{'='*50}\n")

    marker = " ← current" if current == "main" else ""
    main_count = branch_counts.get("main", 0)
    print(f"  * main ({main_count} entities){marker}")

    for r in rows:
        marker = " ← current" if r["name"] == current else ""
        count = branch_counts.get(r["name"], 0)
        desc = f" — {truncate(r['description'], 30)}" if r.get("description") else ""
        parent = f" (from: {r['parent_branch']})" if r["parent_branch"] != "main" else ""
        print(f"  * {r['name']} ({count} entities){parent}{desc}{marker}")

    total = len(rows) + 1  # +1 for main
    print(f"\n  Total: {total} branch(es)")
    return True


def cmd_current(args):
    """Afișează branch-ul curent."""
    current = get_current_branch()
    print(f"Branch curent: {current}")
    return True


def cmd_switch(args):
    """Comută pe alt branch."""
    if not args:
        print("❌ Folosire: mem branch switch <name>")
        return False

    name = args[0].strip()
    project = _project()

    if name == "main":
        clear_current_branch()
        print(f"✅ Switch pe branch: main")
        return True

    conn = get_db()
    if not _ensure_branch_exists(conn, name, project):
        print(f"❌ Branch '{name}' nu există. Creează-l cu: mem branch create {name}")
        conn.close()
        return False
    conn.close()

    set_current_branch(name)
    print(f"✅ Switch pe branch: {name}")
    return True


def _title_col(table):
    """Returnează coloana titlu pentru o tabelă entity."""
    if table == "learned_facts":
        return "fact"
    elif table == "error_resolutions":
        return "error_summary"
    return "title"


def _get_branch_entities(cursor, table, branch, project):
    """Returnează entitățile de pe un branch specific."""
    tc = _title_col(table)
    try:
        cursor.execute(f"""
            SELECT id, {tc} as title, created_at FROM {table}
            WHERE project_path=? AND (branch=? OR (branch IS NULL AND ?='main'))
        """, (project, branch, branch))
        return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []


def compare_branches(cursor, branch_a, branch_b, project):
    """Compară două branch-uri și returnează dict structurat pe categorii."""
    result = {"only_a": {}, "only_b": {}, "conflicts": {}, "summary": {}}

    # Same branch → identical by definition
    if branch_a == branch_b:
        result["summary"] = {
            "branch_a": branch_a, "branch_b": branch_b,
            "only_in_a": 0, "only_in_b": 0, "conflicts": 0, "identical": True,
        }
        return result

    total_a = 0
    total_b = 0
    total_conflicts = 0

    for table in BRANCH_ENTITY_TABLES:
        a_items = _get_branch_entities(cursor, table, branch_a, project)
        b_items = _get_branch_entities(cursor, table, branch_b, project)

        # Detect conflicts (same title in both)
        a_titles = {item["title"]: item for item in a_items}
        b_titles = {item["title"]: item for item in b_items}
        common_titles = set(a_titles.keys()) & set(b_titles.keys())

        only_a = [i for i in a_items if i["title"] not in common_titles]
        only_b = [i for i in b_items if i["title"] not in common_titles]
        conflicts = [{"a": a_titles[t], "b": b_titles[t], "title": t} for t in common_titles]

        if only_a:
            result["only_a"][table] = only_a
            total_a += len(only_a)
        if only_b:
            result["only_b"][table] = only_b
            total_b += len(only_b)
        if conflicts:
            result["conflicts"][table] = conflicts
            total_conflicts += len(conflicts)

    result["summary"] = {
        "branch_a": branch_a, "branch_b": branch_b,
        "only_in_a": total_a, "only_in_b": total_b,
        "conflicts": total_conflicts,
        "identical": total_a == 0 and total_b == 0 and total_conflicts == 0,
    }
    return result


def cmd_diff(args):
    """Arată diferențele simple între două branch-uri (format compact)."""
    if len(args) < 2:
        print("❌ Folosire: mem branch diff <branch_a> <branch_b>")
        return False

    branch_a, branch_b = args[0].strip(), args[1].strip()
    project = _project()

    conn = get_db()
    c = conn.cursor()

    # Validate branches
    for b in (branch_a, branch_b):
        if not _ensure_branch_exists(conn, b, project):
            print(f"❌ Branch '{b}' nu există.")
            conn.close()
            return False

    data = compare_branches(c, branch_a, branch_b, project)
    conn.close()

    s = data["summary"]
    if s["identical"]:
        print(f"\n✅ Branch-urile '{branch_a}' și '{branch_b}' sunt identice (nicio diferență).")
        return True

    print(f"\n{'='*55}")
    print(f"  DIFF: {branch_a} ↔ {branch_b}")
    print(f"{'='*55}\n")

    for table, items in data["only_a"].items():
        print(f"  {table} (only in {branch_a}):")
        for i in items:
            print(f"    + #{i['id']} {truncate(i['title'], 45)}")
        print()

    for table, items in data["only_b"].items():
        print(f"  {table} (only in {branch_b}):")
        for i in items:
            print(f"    + #{i['id']} {truncate(i['title'], 45)}")
        print()

    if data["conflicts"]:
        print(f"  ⚠ CONFLICTS:")
        for table, conflicts in data["conflicts"].items():
            for cf in conflicts:
                print(f"    {table}: #{cf['a']['id']} ({branch_a}) ↔ #{cf['b']['id']} ({branch_b}): {truncate(cf['title'], 35)}")
        print()

    print(f"  Summary: {s['only_in_a']} only in {branch_a}, {s['only_in_b']} only in {branch_b}, {s['conflicts']} conflict(s)")
    return True


def cmd_compare(args):
    """Comparare detaliată structurată pe categorii."""
    if len(args) < 2:
        print("❌ Folosire: mem branch compare <branch_a> <branch_b>")
        return False

    branch_a, branch_b = args[0].strip(), args[1].strip()
    project = _project()

    conn = get_db()
    c = conn.cursor()

    for b in (branch_a, branch_b):
        if not _ensure_branch_exists(conn, b, project):
            print(f"❌ Branch '{b}' nu există.")
            conn.close()
            return False

    data = compare_branches(c, branch_a, branch_b, project)
    conn.close()

    s = data["summary"]

    print(f"\n{'='*60}")
    print(f"  COMPARE: {branch_a} ↔ {branch_b}")
    print(f"{'='*60}")

    if s["identical"]:
        print(f"\n  ✅ Identice — nicio diferență între branch-uri.\n")
        return True

    # Per-category display
    TABLE_LABELS = {
        "decisions": "DECISIONS",
        "learned_facts": "FACTS",
        "goals": "GOALS",
        "tasks": "TASKS",
        "error_resolutions": "RESOLUTIONS",
    }

    for table in BRANCH_ENTITY_TABLES:
        label = TABLE_LABELS.get(table, table.upper())
        a_items = data["only_a"].get(table, [])
        b_items = data["only_b"].get(table, [])
        conflicts = data["conflicts"].get(table, [])

        if not a_items and not b_items and not conflicts:
            continue

        print(f"\n  ── {label} {'─'*(50-len(label))}")

        if a_items:
            print(f"    Only in {branch_a}:")
            for i in a_items:
                ts = format_timestamp(i.get("created_at"))
                print(f"      + #{i['id']:>4} {truncate(i['title'], 35):35s}  [{ts}]")

        if b_items:
            print(f"    Only in {branch_b}:")
            for i in b_items:
                ts = format_timestamp(i.get("created_at"))
                print(f"      + #{i['id']:>4} {truncate(i['title'], 35):35s}  [{ts}]")

        if conflicts:
            print(f"    ⚠ Conflicts ({len(conflicts)}):")
            for cf in conflicts:
                print(f"      #{cf['a']['id']} ({branch_a}) ↔ #{cf['b']['id']} ({branch_b}): {truncate(cf['title'], 30)}")

    # Summary
    print(f"\n  {'─'*55}")
    print(f"  Summary:")
    print(f"    {branch_a}: {s['only_in_a']} unique entities")
    print(f"    {branch_b}: {s['only_in_b']} unique entities")
    print(f"    Conflicts: {s['conflicts']}")
    print()
    return True


def replay_branch(cursor, branch, project, since_date=None, limit=50):
    """Colectează evenimentele cronologice de pe un branch."""
    events = []

    time_filter = ""
    time_params = []
    if since_date:
        time_filter = " AND created_at >= ?"
        time_params = [since_date]

    # Decisions
    for row in cursor.execute(f"""
        SELECT id, title, category, status, created_at FROM decisions
        WHERE project_path=? AND (branch=? OR (branch IS NULL AND ?='main')){time_filter}
        ORDER BY created_at
    """, (project, branch, branch, *time_params)).fetchall():
        events.append({
            "date": row["created_at"], "type": "decision",
            "icon": "📋", "entity_id": row["id"],
            "title": f"Decision: {truncate(row['title'], 40)}",
            "detail": f"[{row['category']}] status={row['status']}",
        })

    # Facts
    for row in cursor.execute(f"""
        SELECT id, fact, fact_type, is_pinned, created_at FROM learned_facts
        WHERE project_path=? AND is_active=1 AND (branch=? OR (branch IS NULL AND ?='main')){time_filter}
        ORDER BY created_at
    """, (project, branch, branch, *time_params)).fetchall():
        pin = " ★" if row["is_pinned"] else ""
        events.append({
            "date": row["created_at"], "type": "fact",
            "icon": "💡", "entity_id": row["id"],
            "title": f"Fact{pin}: {truncate(row['fact'], 40)}",
            "detail": f"[{row['fact_type']}]",
        })

    # Goals
    for row in cursor.execute(f"""
        SELECT id, title, priority, status, created_at FROM goals
        WHERE project_path=? AND (branch=? OR (branch IS NULL AND ?='main')){time_filter}
        ORDER BY created_at
    """, (project, branch, branch, *time_params)).fetchall():
        events.append({
            "date": row["created_at"], "type": "goal",
            "icon": "🎯", "entity_id": row["id"],
            "title": f"Goal: {truncate(row['title'], 40)}",
            "detail": f"[{row['priority']}] status={row['status']}",
        })

    # Tasks
    for row in cursor.execute(f"""
        SELECT id, title, priority, status, created_at FROM tasks
        WHERE project_path=? AND (branch=? OR (branch IS NULL AND ?='main')){time_filter}
        ORDER BY created_at
    """, (project, branch, branch, *time_params)).fetchall():
        events.append({
            "date": row["created_at"], "type": "task",
            "icon": "✅", "entity_id": row["id"],
            "title": f"Task: {truncate(row['title'], 40)}",
            "detail": f"[{row['priority']}] status={row['status']}",
        })

    # Resolutions
    for row in cursor.execute(f"""
        SELECT id, error_summary, resolution_type, worked, created_at FROM error_resolutions
        WHERE project_path=? AND (branch=? OR (branch IS NULL AND ?='main')){time_filter}
        ORDER BY created_at
    """, (project, branch, branch, *time_params)).fetchall():
        w = "✓" if row["worked"] else "✗"
        events.append({
            "date": row["created_at"], "type": "resolution",
            "icon": "🔧", "entity_id": row["id"],
            "title": f"Resolution ({w}): {truncate(row['error_summary'], 35)}",
            "detail": f"[{row['resolution_type']}]",
        })

    # Merges involving this branch
    try:
        for row in cursor.execute(f"""
            SELECT id, source_branch, target_branch, strategy, entities_merged, merged_at FROM branch_merge_log
            WHERE project_path=? AND (source_branch=? OR target_branch=?){time_filter.replace('created_at', 'merged_at')}
            ORDER BY merged_at
        """, (project, branch, branch, *time_params)).fetchall():
            events.append({
                "date": row["merged_at"], "type": "merge",
                "icon": "🔀", "entity_id": row["id"],
                "title": f"Merge: {row['source_branch']} → {row['target_branch']}",
                "detail": f"{row['entities_merged']} entities ({row['strategy']})",
            })
    except Exception:
        pass

    events.sort(key=lambda e: e["date"] or "")
    return events[:limit]


def cmd_replay(args):
    """Arată cronologic activitatea pe un branch."""
    parser = argparse.ArgumentParser(prog="mem branch replay")
    parser.add_argument("name", help="Numele branch-ului")
    parser.add_argument("--days", type=int, default=None, help="Ultimele N zile")
    parser.add_argument("--limit", type=int, default=50, help="Limită evenimente (default 50)")
    opts = parser.parse_args(args)

    branch = opts.name.strip()
    project = _project()

    conn = get_db()
    c = conn.cursor()

    if not _ensure_branch_exists(conn, branch, project):
        print(f"❌ Branch '{branch}' nu există.")
        conn.close()
        return False

    since_date = None
    if opts.days:
        since_date = (datetime.now() - __import__('datetime').timedelta(days=opts.days)).isoformat()

    events = replay_branch(c, branch, project, since_date, opts.limit)
    conn.close()

    if not events:
        period = f"ultimele {opts.days} zile" if opts.days else "total"
        print(f"\n  (niciun eveniment pe branch '{branch}' — {period})")
        return True

    print(f"\n{'='*55}")
    print(f"  REPLAY: {branch} ({len(events)} evenimente)")
    print(f"{'='*55}\n")

    current_date = None
    for ev in events:
        ev_date = (ev["date"] or "")[:10]
        if ev_date != current_date:
            current_date = ev_date
            print(f"  {current_date}")
            print(f"  {'─'*50}")

        time_str = (ev["date"] or "")[11:16]
        detail_str = f" — {ev['detail']}" if ev.get("detail") else ""
        print(f"    {time_str} {ev['icon']} {ev['title']}{detail_str}")

    print()
    return True


def cmd_merge(args):
    """Merge branch source în target."""
    parser = argparse.ArgumentParser(prog="mem branch merge")
    parser.add_argument("source", help="Branch sursă")
    parser.add_argument("--into", default="main", help="Branch țintă (default: main)")
    parser.add_argument("--strategy", default="merge", choices=["merge", "replace"],
                        help="Strategie merge (default: merge)")
    opts = parser.parse_args(args)

    source = opts.source.strip()
    target = opts.into.strip()
    project = _project()

    if source == target:
        print("❌ Source și target sunt identice.")
        return False

    conn = get_db()
    c = conn.cursor()

    if not _ensure_branch_exists(conn, source, project):
        print(f"❌ Branch sursă '{source}' nu există.")
        conn.close()
        return False

    if target != "main" and not _ensure_branch_exists(conn, target, project):
        print(f"❌ Branch țintă '{target}' nu există.")
        conn.close()
        return False

    # Detect conflicts (same title in both branches for same table)
    conflicts = _detect_conflicts(c, source, target, project)
    if conflicts:
        print(f"⚠️  {len(conflicts)} conflict(e) detectate:")
        for cf in conflicts:
            print(f"    {cf['table']} #{cf['source_id']} vs #{cf['target_id']}: {truncate(cf['title'], 40)}")
        if opts.strategy != "replace":
            print("  Folosește --strategy replace pentru a suprascrie, sau rezolvă manual.")

    # Merge: move entities from source to target
    total_merged = 0
    for table in BRANCH_ENTITY_TABLES:
        try:
            c.execute(f"UPDATE {table} SET branch=? WHERE branch=? AND project_path=?",
                      (target, source, project))
            total_merged += c.rowcount
        except Exception:
            pass

    # Log merge
    c.execute("""
        INSERT INTO branch_merge_log
        (source_branch, target_branch, project_path, strategy, conflicts_found, entities_merged)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (source, target, project, opts.strategy, len(conflicts), total_merged))

    conn.commit()
    conn.close()

    print(f"✅ Merge completat: {source} → {target} ({total_merged} entities)")
    return True


def _detect_conflicts(cursor, branch_a, branch_b, project):
    """Detectează conflicte: entități cu titlu identic în ambele branch-uri."""
    conflicts = []
    for table in BRANCH_ENTITY_TABLES:
        if table == "learned_facts":
            title_col = "fact"
        elif table == "error_resolutions":
            title_col = "error_summary"
        else:
            title_col = "title"

        try:
            cursor.execute(f"""
                SELECT a.id as a_id, b.id as b_id, a.{title_col} as title
                FROM {table} a
                JOIN {table} b ON a.{title_col} = b.{title_col}
                WHERE a.branch=? AND b.branch=? AND a.project_path=? AND b.project_path=?
            """, (branch_a, branch_b, project, project))
            for row in cursor.fetchall():
                conflicts.append({
                    "table": table,
                    "source_id": row[0],
                    "target_id": row[1],
                    "title": row[2],
                })
        except Exception:
            pass

    return conflicts


def cmd_conflicts(args):
    """Afișează conflictele între două branch-uri."""
    if len(args) < 2:
        print("❌ Folosire: mem branch conflicts <branch_a> <branch_b>")
        return False

    branch_a, branch_b = args[0].strip(), args[1].strip()
    project = _project()

    conn = get_db()
    c = conn.cursor()

    conflicts = _detect_conflicts(c, branch_a, branch_b, project)
    conn.close()

    if not conflicts:
        print(f"✅ Niciun conflict între '{branch_a}' și '{branch_b}'.")
        return True

    print(f"\n⚠️  {len(conflicts)} conflict(e) între '{branch_a}' și '{branch_b}':\n")
    for cf in conflicts:
        print(f"  {cf['table']}: #{cf['source_id']} ({branch_a}) ↔ #{cf['target_id']} ({branch_b})")
        print(f"    Titlu: {truncate(cf['title'], 50)}")
    return True


def cmd_delete(args):
    """Dezactivează un branch (nu șterge entitățile)."""
    if not args:
        print("❌ Folosire: mem branch delete <name>")
        return False

    name = args[0].strip()
    if name == "main":
        print("❌ Nu poți șterge branch-ul 'main'.")
        return False

    project = _project()
    conn = get_db()
    c = conn.cursor()

    # Check for entities still on this branch
    entity_count = 0
    for table in BRANCH_ENTITY_TABLES:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table} WHERE branch=? AND project_path=?",
                      (name, project))
            entity_count += c.fetchone()[0]
        except Exception:
            pass

    if entity_count > 0:
        print(f"⚠️  Branch '{name}' are {entity_count} entități. Merge mai întâi sau folosește --force.")
        conn.close()
        return False

    c.execute("UPDATE memory_branches SET is_active=0 WHERE name=? AND project_path=?",
              (name, project))
    conn.commit()

    # If current branch was deleted, switch to main
    current = get_current_branch()
    if current == name:
        clear_current_branch()
        print(f"  (switch automat pe main)")

    conn.close()
    print(f"✅ Branch '{name}' dezactivat.")
    return True


def main():
    if len(sys.argv) < 2:
        print("❌ Folosire: mem branch <create|list|current|switch|diff|merge|conflicts|delete> [args]")
        return

    subcmd = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "current": cmd_current,
        "switch": cmd_switch,
        "diff": cmd_diff,
        "compare": cmd_compare,
        "replay": cmd_replay,
        "merge": cmd_merge,
        "conflicts": cmd_conflicts,
        "delete": cmd_delete,
    }

    if subcmd in commands:
        commands[subcmd](args)
    else:
        print(f"❌ Subcomandă necunoscută: {subcmd}")
        print("   Valide: create, list, current, switch, diff, compare, replay, merge, conflicts, delete")


if __name__ == "__main__":
    main()
