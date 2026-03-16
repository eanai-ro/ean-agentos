#!/usr/bin/env python3
"""
Error Resolution - Gestionare rezolvări structurate pentru erori.

Comenzi:
    error_resolution.py add --error-id ID -s "rezolvare" [--code "..."] [--type fix] [--model X] [--provider Y]
    error_resolution.py add --summary "eroare" -s "rezolvare"
    error_resolution.py list [--all] [--model X]
    error_resolution.py show <id>
    error_resolution.py search "query"
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import (
    get_db, get_current_session_id, get_current_project_path,
    get_current_model, get_current_branch, error_fingerprint,
    format_timestamp, truncate, format_table, log_agent_activity,
    VALID_RESOLUTION_TYPES,
)


def _get_error_info(cursor, error_id):
    """Preia informații despre eroarea originală din errors_solutions."""
    cursor.execute(
        "SELECT id, error_type, error_message, file_path FROM errors_solutions WHERE id = ?",
        (error_id,),
    )
    return cursor.fetchone()


def cmd_add(args):
    """Adaugă o rezolvare pentru o eroare."""
    conn = get_db()
    cursor = conn.cursor()

    # Validare resolution_type
    res_type = args.type or "fix"
    if res_type not in VALID_RESOLUTION_TYPES:
        print(f"❌ Tip rezolvare invalid: {res_type}")
        print(f"   Valide: {', '.join(VALID_RESOLUTION_TYPES)}")
        conn.close()
        return

    # Determină fingerprint și error_summary
    fp = None
    summary = args.summary

    if args.error_id:
        row = _get_error_info(cursor, args.error_id)
        if not row:
            print(f"❌ Eroarea #{args.error_id} nu există în errors_solutions.")
            conn.close()
            return
        fp = error_fingerprint(row["error_type"], row["error_message"], row["file_path"])
        if not summary:
            summary = truncate(row["error_message"], 200)
    elif summary:
        fp = error_fingerprint("manual", summary)

    # Model: din args, din .current_model, sau NULL
    model = args.model
    provider = args.provider
    if not model:
        m, p = get_current_model()
        if m != "unknown":
            model = m
            provider = provider or p

    branch = get_current_branch()

    cursor.execute("""
        INSERT INTO error_resolutions
        (error_id, error_fingerprint, error_summary,
         resolution, resolution_code, resolution_type,
         model_used, provider, agent_name,
         project_path, source_session, created_by, branch)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', ?)
    """, (
        args.error_id,
        fp,
        summary,
        args.solution,
        args.code,
        res_type,
        model,
        provider,
        args.agent,
        get_current_project_path(),
        get_current_session_id(),
        branch,
    ))

    conn.commit()
    res_id = cursor.lastrowid
    conn.close()

    log_agent_activity("resolve", f"Resolution: {truncate(args.solution, 60)}",
                       "error", res_id, model_id=model, provider=provider)

    print(f"✅ Rezolvare #{res_id} salvată")
    if args.error_id:
        print(f"   Eroare: #{args.error_id}")
    if summary:
        print(f"   Sumar:  {truncate(summary, 60)}")
    print(f"   Soluție: {truncate(args.solution, 60)}")
    print(f"   Tip: {res_type}")
    if model:
        print(f"   Model: {model} ({provider or '?'})")


def cmd_list(args):
    """Listează rezolvări."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT r.id, r.error_id, r.error_summary, r.resolution,
               r.resolution_type, r.model_used, r.worked, r.created_at
        FROM error_resolutions r
        WHERE 1=1
    """
    params = []

    if hasattr(args, "model") and args.model:
        query += " AND r.model_used = ?"
        params.append(args.model)

    query += " ORDER BY r.created_at DESC LIMIT 50"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        print("\n  Nicio rezolvare găsită.")
        return

    print(f"\n{'='*80}")
    print(f"  REZOLVĂRI ERORI ({len(rows)} rezultate)")
    print(f"{'='*80}\n")

    for row in rows:
        row["error_id"] = f"#{row['error_id']}" if row["error_id"] else "—"
        row["error_summary"] = truncate(row["error_summary"], 25)
        row["resolution"] = truncate(row["resolution"], 25)
        row["model_used"] = row["model_used"] or "—"
        row["worked"] = "✅" if row["worked"] else ("❌" if row["worked"] == 0 else "?")
        row["created_at"] = format_timestamp(row["created_at"])

    cols = [
        ("ID", "id", 5),
        ("Err", "error_id", 6),
        ("Eroare", "error_summary", 25),
        ("Rezolvare", "resolution", 25),
        ("Tip", "resolution_type", 13),
        ("Model", "model_used", 15),
        ("OK", "worked", 3),
    ]
    print(format_table(rows, cols))
    print()


def cmd_show(args):
    """Afișează detalii rezolvare."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM error_resolutions WHERE id = ?", (args.id,))
    row = cursor.fetchone()

    if not row:
        print(f"❌ Rezolvarea #{args.id} nu există.")
        conn.close()
        return

    r = dict(row)

    print(f"\n{'='*60}")
    print(f"  REZOLVARE #{r['id']}")
    print(f"{'='*60}")
    if r.get("error_id"):
        print(f"  Eroare:       #{r['error_id']}")
    if r.get("error_summary"):
        print(f"  Sumar eroare: {r['error_summary']}")
    if r.get("error_fingerprint"):
        print(f"  Fingerprint:  {r['error_fingerprint']}")
    print(f"  Rezolvare:    {r['resolution']}")
    if r.get("resolution_code"):
        print(f"  Cod:          {r['resolution_code']}")
    print(f"  Tip:          {r['resolution_type']}")
    if r.get("model_used"):
        print(f"  Model:        {r['model_used']}")
    if r.get("provider"):
        print(f"  Provider:     {r['provider']}")
    if r.get("agent_name"):
        print(f"  Agent:        {r['agent_name']}")
    worked_str = "da" if r["worked"] else ("nu" if r["worked"] == 0 else "necunoscut")
    print(f"  Funcționează: {worked_str}")
    print(f"  Reutilizări:  {r['reuse_count']}")
    print(f"  Creat:        {format_timestamp(r['created_at'])}")
    print(f"  Actualizat:   {format_timestamp(r['updated_at'])}")
    print(f"  Creat de:     {r['created_by']}")
    if r.get("project_path"):
        print(f"  Proiect:      {r['project_path']}")

    conn.close()
    print()


def cmd_search(args):
    """Caută rezolvări după text sau fingerprint."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.error_id, r.error_summary, r.resolution,
               r.resolution_type, r.model_used, r.worked, r.error_fingerprint, r.created_at
        FROM error_resolutions r
        WHERE r.resolution LIKE ?
           OR r.error_summary LIKE ?
           OR r.resolution_code LIKE ?
           OR r.error_fingerprint LIKE ?
        ORDER BY r.created_at DESC
        LIMIT 30
    """, (f"%{args.query}%", f"%{args.query}%", f"%{args.query}%", f"%{args.query}%"))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        print(f"\n  Nicio rezolvare găsită pentru: '{args.query}'")
        return

    print(f"\n{'='*80}")
    print(f"  CĂUTARE REZOLVĂRI: '{args.query}' ({len(rows)} rezultate)")
    print(f"{'='*80}\n")

    for row in rows:
        row["error_id"] = f"#{row['error_id']}" if row["error_id"] else "—"
        row["error_summary"] = truncate(row["error_summary"], 25)
        row["resolution"] = truncate(row["resolution"], 25)
        row["model_used"] = row["model_used"] or "—"
        row["worked"] = "✅" if row["worked"] else ("❌" if row["worked"] == 0 else "?")

    cols = [
        ("ID", "id", 5),
        ("Err", "error_id", 6),
        ("Eroare", "error_summary", 25),
        ("Rezolvare", "resolution", 25),
        ("Model", "model_used", 15),
        ("OK", "worked", 3),
    ]
    print(format_table(rows, cols))
    print()


def main():
    parser = argparse.ArgumentParser(description="Gestionare rezolvări erori")
    subparsers = parser.add_subparsers(dest="command")

    # ADD
    add_p = subparsers.add_parser("add", help="Adaugă rezolvare")
    add_p.add_argument("--error-id", "-e", type=int, help="ID eroare din errors_solutions")
    add_p.add_argument("--summary", help="Sumar eroare (dacă nu ai error_id)")
    add_p.add_argument("-s", "--solution", required=True, help="Rezolvarea aplicată")
    add_p.add_argument("--code", help="Snippet cod soluție")
    add_p.add_argument("--type", "-t", help="Tip rezolvare (fix/workaround/config_change/dependency/rollback)")
    add_p.add_argument("--model", help="Modelul care a rezolvat")
    add_p.add_argument("--provider", help="Provider-ul modelului")
    add_p.add_argument("--agent", help="Numele agentului")

    # LIST
    list_p = subparsers.add_parser("list", help="Listează rezolvări")
    list_p.add_argument("--model", help="Filtrează după model")

    # SHOW
    show_p = subparsers.add_parser("show", help="Detalii rezolvare")
    show_p.add_argument("id", type=int, help="ID rezolvare")

    # SEARCH
    search_p = subparsers.add_parser("search", help="Caută rezolvări")
    search_p.add_argument("query", help="Text de căutat")

    args = parser.parse_args()

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "show": cmd_show,
        "search": cmd_search,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
