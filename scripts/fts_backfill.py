#!/usr/bin/env python3
"""
Backfill FTS5 tables from existing data (incremental, batched, idempotent).

Acest script populează tabelele FTS5 cu datele existente din:
- messages → messages_fts
- tool_calls → tool_calls_fts
- bash_history → bash_history_fts

Poate fi rulat de mai multe ori fără probleme (idempotent).
Folosește batch-uri și WAL mode pentru a nu bloca baza de date.

Usage:
    python3 fts_backfill.py --batch 10000 --sleep-ms 25 --only all
"""

import argparse
import sqlite3
import time
from pathlib import Path


def connect(db_path: str) -> sqlite3.Connection:
    """Conectare cu setări optimizate pentru backfill."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def table_exists(conn, name: str) -> bool:
    """Verifică dacă o tabelă/view există."""
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE (type='table' OR type='view') AND name=? LIMIT 1",
        (name,),
    )
    return cur.fetchone() is not None


def backfill_messages(conn, batch_size: int, sleep_ms: int):
    """Backfill messages → messages_fts (incremental)."""
    if not table_exists(conn, "messages_fts"):
        raise SystemExit("❌ messages_fts does not exist. Run init_db.py first.")

    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    print(f"[messages] total rows in messages: {total:,}")

    # Găsim ultimul rowid din FTS pentru a continua de acolo
    cur_max = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM messages_fts").fetchone()[0]
    print(f"[messages] current max rowid in messages_fts: {cur_max:,}")

    if cur_max >= total:
        print("[messages] ✓ Already up to date")
        return

    inserted_total = 0
    while True:
        rows = conn.execute(
            """
            SELECT m.id, m.content, m.session_id, m.project_path
            FROM messages m
            WHERE m.id > ?
            ORDER BY m.id
            LIMIT ?
            """,
            (cur_max, batch_size),
        ).fetchall()

        if not rows:
            break

        conn.execute("BEGIN;")
        conn.executemany(
            """
            INSERT INTO messages_fts(rowid, content, session_id, project_path)
            VALUES(?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

        cur_max = rows[-1][0]
        inserted_total += len(rows)
        print(f"[messages] inserted {len(rows):,} (total: {inserted_total:,}) up to id={cur_max:,}")

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    print(f"[messages] ✓ Backfill complete: {inserted_total:,} rows inserted")


def backfill_tool_calls(conn, batch_size: int, sleep_ms: int):
    """Backfill tool_calls → tool_calls_fts (incremental)."""
    if not table_exists(conn, "tool_calls_fts"):
        raise SystemExit("❌ tool_calls_fts does not exist. Run init_db.py first.")

    total = conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
    print(f"[tool_calls] total rows: {total:,}")

    cur_max = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM tool_calls_fts").fetchone()[0]
    print(f"[tool_calls] current max rowid in tool_calls_fts: {cur_max:,}")

    if cur_max >= total:
        print("[tool_calls] ✓ Already up to date")
        return

    inserted_total = 0
    while True:
        rows = conn.execute(
            """
            SELECT t.id, t.tool_name, t.tool_input, t.tool_result, t.session_id, t.project_path, t.file_path
            FROM tool_calls t
            WHERE t.id > ?
            ORDER BY t.id
            LIMIT ?
            """,
            (cur_max, batch_size),
        ).fetchall()

        if not rows:
            break

        conn.execute("BEGIN;")
        conn.executemany(
            """
            INSERT INTO tool_calls_fts(rowid, tool_name, tool_input, tool_result, session_id, project_path, file_path)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

        cur_max = rows[-1][0]
        inserted_total += len(rows)
        print(f"[tool_calls] inserted {len(rows):,} (total: {inserted_total:,}) up to id={cur_max:,}")

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    print(f"[tool_calls] ✓ Backfill complete: {inserted_total:,} rows inserted")


def backfill_bash_history(conn, batch_size: int, sleep_ms: int):
    """Backfill bash_history → bash_history_fts (incremental)."""
    if not table_exists(conn, "bash_history_fts"):
        raise SystemExit("❌ bash_history_fts does not exist. Run init_db.py first.")

    total = conn.execute("SELECT COUNT(*) FROM bash_history").fetchone()[0]
    print(f"[bash_history] total rows: {total:,}")

    cur_max = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM bash_history_fts").fetchone()[0]
    print(f"[bash_history] current max rowid in bash_history_fts: {cur_max:,}")

    if cur_max >= total:
        print("[bash_history] ✓ Already up to date")
        return

    inserted_total = 0
    while True:
        rows = conn.execute(
            """
            SELECT b.id, b.command, b.output, b.error_output, b.session_id, b.project_path, b.working_directory
            FROM bash_history b
            WHERE b.id > ?
            ORDER BY b.id
            LIMIT ?
            """,
            (cur_max, batch_size),
        ).fetchall()

        if not rows:
            break

        conn.execute("BEGIN;")
        conn.executemany(
            """
            INSERT INTO bash_history_fts(rowid, command, output, error_output, session_id, project_path, working_directory)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

        cur_max = rows[-1][0]
        inserted_total += len(rows)
        print(f"[bash_history] inserted {len(rows):,} (total: {inserted_total:,}) up to id={cur_max:,}")

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    print(f"[bash_history] ✓ Backfill complete: {inserted_total:,} rows inserted")


def main():
    ap = argparse.ArgumentParser(
        description="Backfill FTS5 tables from existing data (incremental, batched, idempotent)."
    )
    ap.add_argument(
        "--db",
        default=str(Path.home() / ".claude/memory/global.db"),
        help="Path to database"
    )
    ap.add_argument(
        "--batch",
        type=int,
        default=10000,
        help="Batch size (default: 10000)"
    )
    ap.add_argument(
        "--sleep-ms",
        type=int,
        default=25,
        help="Sleep between batches in ms (default: 25)"
    )
    ap.add_argument(
        "--only",
        choices=["messages", "tool_calls", "bash_history", "all"],
        default="all",
        help="Which table to backfill (default: all)"
    )
    args = ap.parse_args()

    print(f"🔄 FTS5 Backfill Starting")
    print(f"   Database: {args.db}")
    print(f"   Batch size: {args.batch:,}")
    print(f"   Sleep: {args.sleep_ms}ms")
    print(f"   Tables: {args.only}")
    print()

    conn = connect(args.db)
    try:
        if args.only in ("messages", "all"):
            backfill_messages(conn, args.batch, args.sleep_ms)
            print()
        if args.only in ("tool_calls", "all"):
            backfill_tool_calls(conn, args.batch, args.sleep_ms)
            print()
        if args.only in ("bash_history", "all"):
            backfill_bash_history(conn, args.batch, args.sleep_ms)
            print()
        # Rebuild FTS indexes pentru a asigura consistența
        print("🔄 Rebuilding FTS5 indexes...")
        if args.only in ("messages", "all"):
            conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild');")
        if args.only in ("tool_calls", "all"):
            conn.execute("INSERT INTO tool_calls_fts(tool_calls_fts) VALUES('rebuild');")
        if args.only in ("bash_history", "all"):
            conn.execute("INSERT INTO bash_history_fts(bash_history_fts) VALUES('rebuild');")
        conn.commit()

        print("✅ Backfill finished successfully!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
