#!/usr/bin/env python3
"""
Error Pattern Detection - Detectează erori recurente și soluții repetate.

Comenzi:
    error_patterns.py detect          Scanează error_resolutions și actualizează error_patterns
    error_patterns.py list            Listează patternuri detectate
    error_patterns.py show <id>       Detalii pattern
"""

import sys
import os
import re
import json
import hashlib
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import get_db, truncate, get_current_project_path

PATTERN_THRESHOLD = 3  # Minim 3 apariții pentru a fi considerat pattern


def _normalize_error(text):
    """Normalizare text eroare pentru comparație."""
    if not text:
        return ""
    text = re.sub(r'line \d+', 'line N', text)
    text = re.sub(r'/[^\s]+/', '/.../', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', text)
    text = re.sub(r'\d{2}:\d{2}:\d{2}', 'TIME', text)
    text = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', text)
    return text[:200].strip().lower()


def _signature(error_summary, resolution):
    """Generează semnătură unică pentru pereche error+solution."""
    norm_err = _normalize_error(error_summary or "")
    norm_sol = (resolution or "")[:150].strip().lower()
    key = f"{norm_err}::{norm_sol}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def ensure_table(conn):
    """Creează tabela error_patterns dacă nu există."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS error_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_signature TEXT NOT NULL,
            solution TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            first_seen TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now')),
            project_path TEXT,
            auto_promoted INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_error_patterns_sig ON error_patterns(error_signature)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_error_patterns_count ON error_patterns(count DESC)")
    conn.commit()


def cmd_detect(args):
    """Scanează error_resolutions și actualizează/creează patternuri."""
    conn = get_db()
    ensure_table(conn)
    cursor = conn.cursor()

    # Fetch all resolutions
    cursor.execute("""
        SELECT error_summary, resolution, project_path, created_at
        FROM error_resolutions
        WHERE worked = 1 AND resolution IS NOT NULL
        ORDER BY created_at
    """)
    resolutions = cursor.fetchall()

    # Group by signature
    sig_map = {}
    for row in resolutions:
        err, sol, proj, created = row["error_summary"], row["resolution"], row["project_path"], row["created_at"]
        sig = _signature(err, sol)
        if sig not in sig_map:
            sig_map[sig] = {"solution": sol, "project_path": proj, "count": 0,
                            "first_seen": created, "last_seen": created}
        sig_map[sig]["count"] += 1
        sig_map[sig]["last_seen"] = created

    # Upsert patterns
    new_count = 0
    updated_count = 0
    for sig, data in sig_map.items():
        if data["count"] < PATTERN_THRESHOLD:
            continue

        cursor.execute("SELECT id, count FROM error_patterns WHERE error_signature = ?", (sig,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE error_patterns SET count = ?, last_seen = ?, solution = ?
                WHERE error_signature = ?
            """, (data["count"], data["last_seen"], data["solution"], sig))
            updated_count += 1
        else:
            cursor.execute("""
                INSERT INTO error_patterns (error_signature, solution, count, first_seen, last_seen, project_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sig, data["solution"], data["count"], data["first_seen"], data["last_seen"], data["project_path"]))
            new_count += 1

    conn.commit()
    conn.close()

    total = new_count + updated_count
    print(f"✅ Pattern detection: {total} patternuri ({new_count} noi, {updated_count} actualizate)")
    print(f"   Scanate: {len(resolutions)} rezolvări, prag: >={PATTERN_THRESHOLD} apariții")


def cmd_list(args):
    """Listează patternuri detectate."""
    conn = get_db()
    ensure_table(conn)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, error_signature, solution, count, last_seen, project_path
        FROM error_patterns
        ORDER BY count DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("  (niciun pattern detectat — rulează: mem patterns detect)")
        return

    print(f"\n{'ID':>4} {'Count':>5} {'Last Seen':>12} {'Soluție':<50}")
    print("-" * 75)
    for row in rows:
        last = (row["last_seen"] or "")[:10]
        sol = truncate(row["solution"], 50)
        print(f"{row['id']:>4} {row['count']:>5} {last:>12} {sol:<50}")
    print(f"\nTotal: {len(rows)} patternuri")


def cmd_show(args):
    """Detalii pattern."""
    if not args.id:
        print("❌ Folosire: error_patterns.py show <id>")
        return
    conn = get_db()
    ensure_table(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM error_patterns WHERE id = ?", (args.id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"❌ Pattern #{args.id} nu a fost găsit")
        return

    print(f"\n  Pattern #{row['id']}")
    print(f"  Signature:  {row['error_signature']}")
    print(f"  Soluție:    {row['solution']}")
    print(f"  Count:      {row['count']}")
    print(f"  First seen: {row['first_seen']}")
    print(f"  Last seen:  {row['last_seen']}")
    print(f"  Proiect:    {row['project_path'] or 'global'}")


def fetch_patterns_for_context(cursor, project_path, limit=3):
    """Fetch patternuri pentru context builder."""
    ensure_table(cursor.connection)
    cursor.execute("""
        SELECT id, solution, count, last_seen
        FROM error_patterns
        WHERE count >= ?
        ORDER BY
            CASE WHEN project_path = ? THEN 0 ELSE 1 END,
            count DESC
        LIMIT ?
    """, (PATTERN_THRESHOLD, project_path, limit))
    return [dict(r) for r in cursor.fetchall()]


def fmt_patterns(patterns, compact=False):
    """Formatare patternuri pentru context."""
    if not patterns:
        return ""
    trunc = 35 if compact else 50
    lines = ["Error patterns:"]
    for p in patterns:
        lines.append(f"  [{p['count']}x] {truncate(p['solution'], trunc)}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Error Pattern Detection")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("detect", help="Scanează și detectează patternuri")
    sub.add_parser("list", help="Listează patternuri")
    p_show = sub.add_parser("show", help="Detalii pattern")
    p_show.add_argument("id", type=int)

    args = parser.parse_args()

    if args.command == "detect":
        cmd_detect(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
