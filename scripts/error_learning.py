#!/usr/bin/env python3
"""
Error Learning Engine — Stage 1.

Combină errors_solutions (raw, captate automat) cu error_resolutions (structured, V2)
pentru a oferi:
  - căutare unificată de erori similare
  - reutilizare de rezolvări
  - pattern matching simplu (fingerprint + text similarity)
  - metadata cine/model/agent a rezolvat

Usage:
    error_learning.py find "TypeError: None"       # Găsește erori similare + soluții
    error_learning.py similar <error_id>            # Erori similare cu ID-ul dat
    error_learning.py stats                         # Statistici error learning
    error_learning.py top                           # Top erori recurente
    error_learning.py resolve "error msg" -s "fix"  # Salvează rezolvare unificată
"""

import sys
import os
import json
import sqlite3
import hashlib
import argparse
from pathlib import Path
from collections import Counter

try:
    from v2_common import resolve_db_path
    DB_PATH = str(resolve_db_path())
except ImportError:
    DB_PATH = os.environ.get("MEMORY_DB_PATH",
        str(Path.home() / ".claude" / "memory" / "global.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _trunc(text, maxlen=100):
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:maxlen] + "..." if len(text) > maxlen else text


def _fingerprint(error_type, error_message, file_path=None):
    """Generate a simple fingerprint for error matching."""
    # Normalize: lowercase, strip numbers/paths, keep structure
    msg = (error_message or "").lower().strip()
    # Remove specific values but keep structure
    import re
    msg = re.sub(r"'[^']*'", "'X'", msg)  # Replace quoted strings
    msg = re.sub(r'"[^"]*"', '"X"', msg)  # Replace double-quoted
    msg = re.sub(r'\b\d+\b', 'N', msg)    # Replace numbers
    msg = re.sub(r'/[\w/.]+', '/PATH', msg)  # Replace file paths
    key = f"{(error_type or 'unknown').lower()}::{msg}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _similarity_score(query, text):
    """Simple word-overlap similarity score (0-100)."""
    if not query or not text:
        return 0
    q_words = set(query.lower().split())
    t_words = set(text.lower().split())
    if not q_words:
        return 0
    overlap = len(q_words & t_words)
    return int(100 * overlap / len(q_words))


# === COMMANDS ===

def cmd_find(args):
    """Find similar errors and their solutions."""
    conn = get_db()
    cursor = conn.cursor()
    query = args.query
    limit = args.limit or 20

    print(f"\n{'='*80}")
    print(f"  ERROR LEARNING: Find similar errors for '{_trunc(query, 60)}'")
    print(f"{'='*80}")

    # 1. Search in error_resolutions (V2 structured, with model/agent info)
    cursor.execute("""
        SELECT id, error_summary, resolution, resolution_type, model_used,
               provider, agent_name, worked, reuse_count, created_at
        FROM error_resolutions
        WHERE error_summary LIKE ? OR resolution LIKE ?
        ORDER BY worked DESC, reuse_count DESC, created_at DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))
    v2_results = cursor.fetchall()

    # 2. Search in errors_solutions (old system, raw capture)
    cursor.execute("""
        SELECT id, error_type, error_message, file_path, language, framework,
               solution, solution_code, solution_worked, resolved,
               created_at, resolved_at, project_path, source
        FROM errors_solutions
        WHERE error_message LIKE ? OR solution LIKE ? OR error_type LIKE ?
        ORDER BY resolved DESC, solution_worked DESC, created_at DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
    raw_results = cursor.fetchall()

    # 3. Fingerprint-based match
    fp = _fingerprint("unknown", query)
    cursor.execute("""
        SELECT id, error_summary, resolution, resolution_type, model_used, worked
        FROM error_resolutions WHERE error_fingerprint = ?
        LIMIT 10
    """, (fp,))
    fp_results = cursor.fetchall()

    # Also check old system fingerprints
    cursor.execute("""
        SELECT id, error_type, error_message, solution, solution_worked
        FROM errors_solutions WHERE fingerprint = ?
        LIMIT 10
    """, (fp,))
    fp_raw_results = cursor.fetchall()

    conn.close()

    # Display results
    total = len(v2_results) + len(raw_results) + len(fp_results) + len(fp_raw_results)
    if total == 0:
        print(f"\n  Nicio eroare similară găsită pentru: '{_trunc(query, 60)}'")
        print("  Sugestie: folosește cuvinte cheie mai generale")
        return

    # V2 Resolutions (structured, with model info)
    if v2_results:
        print(f"\n  --- Rezolvări structurate ({len(v2_results)}) ---")
        for r in v2_results:
            worked = "✅" if r["worked"] else ("❌" if r["worked"] == 0 else "?")
            model = r["model_used"] or "?"
            agent = r["agent_name"] or "?"
            reuse = r["reuse_count"] or 0
            print(f"\n  #{r['id']} [{r['resolution_type']}] {worked} (model: {model}, agent: {agent}, reuse: {reuse})")
            print(f"    Eroare:   {_trunc(r['error_summary'], 100)}")
            print(f"    Soluție:  {_trunc(r['resolution'], 100)}")

    # Fingerprint matches
    seen_ids = set()
    fp_all = list(fp_results) + list(fp_raw_results)
    if fp_all:
        print(f"\n  --- Potriviri fingerprint ({len(fp_all)}) ---")
        for r in fp_all:
            r = dict(r)
            rid = r["id"]
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            if "resolution" in r:
                worked = "✅" if r.get("worked") else "?"
                print(f"    #{rid} {worked} {_trunc(r.get('error_summary', r.get('error_message', '')), 80)}")
                print(f"      → {_trunc(r.get('resolution', r.get('solution', '')), 80)}")
            else:
                worked = "✅" if r.get("solution_worked") else "?"
                print(f"    #{rid} {worked} {_trunc(r.get('error_message', ''), 80)}")
                if r.get("solution"):
                    print(f"      → {_trunc(r['solution'], 80)}")

    # Raw errors (old system)
    if raw_results:
        print(f"\n  --- Erori raw ({len(raw_results)}) ---")
        for r in raw_results[:10]:  # Cap display
            resolved = "RESOLVED" if r["resolved"] else "OPEN"
            worked = "✅" if r["solution_worked"] else ("❌" if r["solution_worked"] == 0 else "—")
            lang = r["language"] or ""
            print(f"\n  #{r['id']} [{r['error_type']}] [{resolved}] {lang}")
            print(f"    {_trunc(r['error_message'], 100)}")
            if r["solution"]:
                print(f"    → Soluție ({worked}): {_trunc(r['solution'], 100)}")
            if r["file_path"]:
                print(f"    📁 {r['file_path']}")

    print(f"\n  Total: {total} rezultate")
    print()


def cmd_similar(args):
    """Find errors similar to a given error ID."""
    conn = get_db()
    cursor = conn.cursor()

    # Try to find the error in both tables
    cursor.execute("SELECT error_message, error_type, file_path FROM errors_solutions WHERE id = ?",
                   (args.error_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("SELECT error_summary FROM error_resolutions WHERE id = ?",
                       (args.error_id,))
        row2 = cursor.fetchone()
        if row2:
            query = row2["error_summary"]
            fp = _fingerprint("unknown", query)
        else:
            print(f"❌ Eroarea #{args.error_id} nu există în nicio tabelă.")
            conn.close()
            return
    else:
        query = row["error_message"]
        fp = _fingerprint(row["error_type"], row["error_message"], row["file_path"])

    print(f"\n{'='*80}")
    print(f"  ERORI SIMILARE CU #{args.error_id}")
    print(f"  Fingerprint: {fp}")
    print(f"{'='*80}")

    # Find by fingerprint
    cursor.execute("""
        SELECT id, error_message, solution, solution_worked, created_at
        FROM errors_solutions WHERE fingerprint = ? AND id != ?
        ORDER BY created_at DESC LIMIT 20
    """, (fp, args.error_id))
    fp_matches = cursor.fetchall()

    # Find by text similarity
    words = query.split()[:5]  # Use first 5 words
    like_pattern = "%" + "%".join(words[:3]) + "%"
    cursor.execute("""
        SELECT id, error_type, error_message, solution, solution_worked, created_at
        FROM errors_solutions WHERE error_message LIKE ? AND id != ?
        ORDER BY created_at DESC LIMIT 20
    """, (like_pattern, args.error_id))
    text_matches = cursor.fetchall()

    # Resolutions
    cursor.execute("""
        SELECT id, error_summary, resolution, worked, model_used
        FROM error_resolutions WHERE error_fingerprint = ?
        ORDER BY worked DESC LIMIT 10
    """, (fp,))
    resolution_matches = cursor.fetchall()

    conn.close()

    if fp_matches:
        print(f"\n  --- Potriviri exacte (fingerprint): {len(fp_matches)} ---")
        for r in fp_matches[:10]:
            worked = "✅" if r["solution_worked"] else "?"
            print(f"    #{r['id']} {worked} {_trunc(r['error_message'], 80)}")
            if r["solution"]:
                print(f"      → {_trunc(r['solution'], 80)}")

    if text_matches:
        print(f"\n  --- Potriviri text: {len(text_matches)} ---")
        for r in text_matches[:10]:
            score = _similarity_score(query, r["error_message"])
            worked = "✅" if r["solution_worked"] else "?"
            print(f"    #{r['id']} (sim: {score}%) {worked} {_trunc(r['error_message'], 80)}")
            if r["solution"]:
                print(f"      → {_trunc(r['solution'], 80)}")

    if resolution_matches:
        print(f"\n  --- Rezolvări structurate: {len(resolution_matches)} ---")
        for r in resolution_matches:
            worked = "✅" if r["worked"] else "?"
            print(f"    #{r['id']} {worked} (model: {r['model_used'] or '?'})")
            print(f"      {_trunc(r['resolution'], 80)}")

    if not fp_matches and not text_matches and not resolution_matches:
        print("\n  Nicio eroare similară găsită.")

    print()


def cmd_stats(args):
    """Error learning statistics."""
    conn = get_db()
    cursor = conn.cursor()

    print(f"\n{'='*60}")
    print(f"  ERROR LEARNING — STATISTICI")
    print(f"{'='*60}")

    # Raw errors
    cursor.execute("SELECT COUNT(*) FROM errors_solutions")
    total_raw = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE resolved = 1")
    resolved_raw = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE solution IS NOT NULL AND solution != ''")
    with_solution = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE solution_worked = 1")
    worked_raw = cursor.fetchone()[0]

    print(f"\n  Erori raw (errors_solutions):")
    print(f"    Total:        {total_raw:>8}")
    print(f"    Resolved:     {resolved_raw:>8} ({100*resolved_raw//max(1,total_raw)}%)")
    print(f"    Cu soluție:   {with_solution:>8} ({100*with_solution//max(1,total_raw)}%)")
    print(f"    Funcționează: {worked_raw:>8}")

    # V2 resolutions
    cursor.execute("SELECT COUNT(*) FROM error_resolutions")
    total_v2 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM error_resolutions WHERE worked = 1")
    worked_v2 = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(reuse_count) FROM error_resolutions")
    reuse_total = cursor.fetchone()[0] or 0

    print(f"\n  Rezolvări structurate (error_resolutions):")
    print(f"    Total:        {total_v2:>8}")
    print(f"    Funcționează: {worked_v2:>8}")
    print(f"    Reutilizări:  {reuse_total:>8}")

    # Top error types
    cursor.execute("""
        SELECT error_type, COUNT(*) as cnt
        FROM errors_solutions
        GROUP BY error_type ORDER BY cnt DESC LIMIT 10
    """)
    top_types = cursor.fetchall()
    if top_types:
        print(f"\n  Top tipuri de erori:")
        for r in top_types:
            print(f"    {r['cnt']:>6}x  {r['error_type']}")

    # Top resolvers (models)
    cursor.execute("""
        SELECT model_used, COUNT(*) as cnt, SUM(CASE WHEN worked THEN 1 ELSE 0 END) as ok
        FROM error_resolutions WHERE model_used IS NOT NULL
        GROUP BY model_used ORDER BY cnt DESC LIMIT 5
    """)
    top_models = cursor.fetchall()
    if top_models:
        print(f"\n  Top modele care rezolvă erori:")
        for r in top_models:
            print(f"    {r['model_used']:>20s}  {r['cnt']} rezolvări ({r['ok']} funcționează)")

    # Fingerprint coverage
    cursor.execute("SELECT COUNT(DISTINCT fingerprint) FROM errors_solutions WHERE fingerprint IS NOT NULL")
    unique_fp = cursor.fetchone()[0]
    print(f"\n  Fingerprints unice: {unique_fp}")
    print(f"  Acoperire:          {100*unique_fp//max(1,total_raw)}% din erori raw")

    conn.close()
    print()


def cmd_top(args):
    """Show top recurring errors."""
    conn = get_db()
    cursor = conn.cursor()
    limit = args.limit or 15

    print(f"\n{'='*80}")
    print(f"  TOP ERORI RECURENTE")
    print(f"{'='*80}")

    cursor.execute("""
        SELECT fingerprint, error_type,
               substr(error_message, 1, 100) as msg,
               COUNT(*) as cnt,
               SUM(CASE WHEN resolved THEN 1 ELSE 0 END) as resolved_cnt,
               MAX(created_at) as last_seen
        FROM errors_solutions
        WHERE fingerprint IS NOT NULL
        GROUP BY fingerprint
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()

    if not rows:
        print("\n  Nicio eroare recurentă detectată.")
        conn.close()
        return

    for r in rows:
        resolved_pct = 100 * r["resolved_cnt"] // r["cnt"]
        print(f"\n  [{r['cnt']}x] [{r['error_type']}] (resolved: {resolved_pct}%)")
        print(f"    {_trunc(r['msg'], 100)}")
        print(f"    Fingerprint: {r['fingerprint']} | Ultima: {r['last_seen'][:10] if r['last_seen'] else '?'}")

        # Check if we have resolutions for this fingerprint
        cursor.execute("""
            SELECT resolution, worked, model_used
            FROM error_resolutions WHERE error_fingerprint = ?
            ORDER BY worked DESC LIMIT 3
        """, (r["fingerprint"],))
        resolutions = cursor.fetchall()
        if resolutions:
            for res in resolutions:
                w = "✅" if res["worked"] else "?"
                print(f"    → {w} {_trunc(res['resolution'], 80)} (model: {res['model_used'] or '?'})")

    conn.close()
    print()


def cmd_resolve(args):
    """Save a unified resolution linking raw error to structured resolution."""
    conn = get_db()
    cursor = conn.cursor()

    error_msg = args.error
    solution = args.solution
    res_type = args.type or "fix"
    model = args.model
    agent = args.agent

    fp = _fingerprint("manual", error_msg)

    # Insert into error_resolutions (V2 structured)
    cursor.execute("""
        INSERT INTO error_resolutions
        (error_fingerprint, error_summary, resolution, resolution_type,
         model_used, agent_name, created_by, worked, branch)
        VALUES (?, ?, ?, ?, ?, ?, 'user', 1, 'main')
    """, (fp, error_msg, solution, res_type, model, agent))

    conn.commit()
    res_id = cursor.lastrowid
    conn.close()

    print(f"✅ Rezolvare #{res_id} salvată")
    print(f"   Eroare:     {_trunc(error_msg, 60)}")
    print(f"   Soluție:    {_trunc(solution, 60)}")
    print(f"   Fingerprint: {fp}")
    print(f"   Tip:        {res_type}")


def main():
    parser = argparse.ArgumentParser(description="Error Learning Engine")
    subparsers = parser.add_subparsers(dest="command")

    # find
    find_p = subparsers.add_parser("find", help="Find similar errors + solutions")
    find_p.add_argument("query", help="Error text to search")
    find_p.add_argument("-l", "--limit", type=int, default=20)

    # similar
    sim_p = subparsers.add_parser("similar", help="Find errors similar to ID")
    sim_p.add_argument("error_id", type=int, help="Error ID from errors_solutions")

    # stats
    subparsers.add_parser("stats", help="Error learning statistics")

    # top
    top_p = subparsers.add_parser("top", help="Top recurring errors")
    top_p.add_argument("-l", "--limit", type=int, default=15)

    # resolve
    res_p = subparsers.add_parser("resolve", help="Save a resolution")
    res_p.add_argument("error", help="Error message/summary")
    res_p.add_argument("-s", "--solution", required=True, help="Solution applied")
    res_p.add_argument("-t", "--type", default="fix", help="Resolution type")
    res_p.add_argument("--model", help="Model that resolved")
    res_p.add_argument("--agent", help="Agent name")

    args = parser.parse_args()
    commands = {
        "find": cmd_find,
        "similar": cmd_similar,
        "stats": cmd_stats,
        "top": cmd_top,
        "resolve": cmd_resolve,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
