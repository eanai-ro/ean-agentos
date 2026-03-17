#!/usr/bin/env python3
"""
mem_status.py - Memory Observability Dashboard
One-screen view pentru status general + ultimele 24h
"""

import sys
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import argparse

try:
    from v2_common import resolve_db_path
    DB_FILE = resolve_db_path()
except ImportError:
    DB_FILE = Path.home() / ".claude" / "memory" / "global.db"
MEMORY_DIR = DB_FILE.parent

def get_db():
    """Conectare DB."""
    return sqlite3.connect(str(DB_FILE))

def format_size(bytes_size):
    """Format size human-readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def format_age(timestamp_str):
    """Format age human-readable."""
    if not timestamp_str:
        return "N/A"

    try:
        ts = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        delta = now - ts

        if delta.days > 365:
            return f"{delta.days // 365}y ago"
        elif delta.days > 30:
            return f"{delta.days // 30}mo ago"
        elif delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60}m ago"
        else:
            return f"{delta.seconds}s ago"
    except:
        return "N/A"

def get_general_stats(conn):
    """Statistici generale."""
    cursor = conn.cursor()

    stats = {}

    # DB size
    db_size = DB_FILE.stat().st_size
    stats['db_size'] = db_size
    stats['db_size_human'] = format_size(db_size)

    # WAL/SHM
    wal_file = MEMORY_DIR / "global.db-wal"
    shm_file = MEMORY_DIR / "global.db-shm"
    stats['wal_present'] = wal_file.exists()
    stats['shm_present'] = shm_file.exists()

    if stats['wal_present']:
        stats['wal_size'] = format_size(wal_file.stat().st_size)

    # Total counts
    cursor.execute("SELECT COUNT(*) FROM messages")
    stats['total_messages'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sessions")
    stats['total_sessions'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tool_calls")
    stats['total_tool_calls'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM errors_solutions")
    stats['total_errors'] = cursor.fetchone()[0]

    # Quarantine
    quarantine_dir = MEMORY_DIR / "quarantine"
    if quarantine_dir.exists():
        stats['quarantine_entries'] = len(list(quarantine_dir.glob("q_*.json")))
    else:
        stats['quarantine_entries'] = 0

    return stats

def get_last_24h_stats(conn):
    """Statistici ultimele 24h."""
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

    stats = {}

    # Messages inserted last 24h
    cursor.execute("SELECT COUNT(*) FROM messages WHERE timestamp >= ?", (cutoff,))
    stats['messages_24h'] = cursor.fetchone()[0]

    # Scrubbed count (aproximativ - messages cu REDACTED)
    cursor.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '%REDACTED%' AND timestamp >= ?", (cutoff,))
    stats['scrubbed_24h'] = cursor.fetchone()[0]

    # Detection events last 24h
    try:
        cursor.execute("SELECT COUNT(*) FROM detection_events WHERE ts >= ?", (cutoff,))
        stats['detections_24h'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM detection_events WHERE ts >= ? AND decision='quarantine'", (cutoff,))
        stats['quarantined_24h'] = cursor.fetchone()[0]
    except:
        stats['detections_24h'] = 0
        stats['quarantined_24h'] = 0

    # Audit events last 24h
    try:
        cursor.execute("SELECT COUNT(*) FROM audit_log WHERE ts >= ?", (cutoff,))
        stats['audit_events_24h'] = cursor.fetchone()[0]
    except:
        stats['audit_events_24h'] = 0

    return stats

def get_panic_stats(conn):
    """Panic scans info."""
    stats = {}

    # Panic reports în ultimele 30 zile
    docs_dir = MEMORY_DIR / "docs"
    if docs_dir.exists():
        reports = list(docs_dir.glob("PANIC_REPORT_*.md"))
        cutoff_30d = datetime.now() - timedelta(days=30)

        recent_reports = [r for r in reports if datetime.fromtimestamp(r.stat().st_mtime) > cutoff_30d]
        stats['panic_scans_30d'] = len(recent_reports)

        if reports:
            latest = max(reports, key=lambda p: p.stat().st_mtime)
            stats['last_panic_time'] = datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
            stats['last_panic_age'] = format_age(stats['last_panic_time'])
        else:
            stats['last_panic_time'] = None
            stats['last_panic_age'] = "Never"
    else:
        stats['panic_scans_30d'] = 0
        stats['last_panic_time'] = None
        stats['last_panic_age'] = "Never"

    return stats

def get_backup_stats():
    """Last backup info."""
    stats = {}

    backups_dir = MEMORY_DIR / "backups"
    if backups_dir.exists():
        backups = sorted(backups_dir.glob("2*"), key=lambda p: p.stat().st_mtime, reverse=True)

        if backups:
            latest = backups[0]
            stats['last_backup_time'] = datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
            stats['last_backup_age'] = format_age(stats['last_backup_time'])
            stats['total_backups'] = len(backups)
        else:
            stats['last_backup_time'] = None
            stats['last_backup_age'] = "Never"
            stats['total_backups'] = 0
    else:
        stats['last_backup_time'] = None
        stats['last_backup_age'] = "Never"
        stats['total_backups'] = 0

    return stats

def get_doctor_stats():
    """Last doctor run info."""
    # Check în docs pentru PANIC_REPORT (proxy pentru doctor, deocamdată)
    # Ideal ar fi să avem un log separat pentru doctor runs
    # Deocamdată returnăm placeholder
    return {
        'last_doctor_time': None,
        'last_doctor_age': "Unknown",
        'last_doctor_status': "unknown"
    }

def get_compact_stats(conn):
    """Auto-compact info."""
    cursor = conn.cursor()
    stats = {}

    # Last compact_boundary
    try:
        cursor.execute("""
            SELECT timestamp FROM messages
            WHERE message_type = 'system'
            AND content LIKE '%compact_boundary%'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            stats['last_compact_time'] = result[0]
            stats['last_compact_age'] = format_age(result[0])
        else:
            stats['last_compact_time'] = None
            stats['last_compact_age'] = "Never"
    except:
        stats['last_compact_time'] = None
        stats['last_compact_age'] = "Never"

    # ENV override
    stats['autocompact_override'] = os.environ.get('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', 'Not set')

    return stats

def get_fts_stats(conn):
    """FTS5 sanity check."""
    cursor = conn.cursor()
    stats = {}

    try:
        # Quick test query
        cursor.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'test' LIMIT 10")
        stats['fts_functional'] = True
        stats['fts_status'] = "OK"
    except Exception as e:
        stats['fts_functional'] = False
        stats['fts_status'] = f"ERROR: {e}"

    return stats

def cmd_status(args):
    """Main status command."""
    conn = get_db()

    # Collect all stats
    general = get_general_stats(conn)
    last_24h = get_last_24h_stats(conn)
    panic = get_panic_stats(conn)
    backup = get_backup_stats()
    doctor = get_doctor_stats()
    compact = get_compact_stats(conn)
    fts = get_fts_stats(conn)

    conn.close()

    if args.json:
        # JSON output
        output = {
            "general": general,
            "last_24h": last_24h,
            "panic": panic,
            "backup": backup,
            "doctor": doctor,
            "compact": compact,
            "fts": fts
        }
        print(json.dumps(output, indent=2))
    else:
        # Text output (one screen)
        print("\n" + "=" * 70)
        print(" MEMORY OBSERVABILITY DASHBOARD ".center(70))
        print("=" * 70)

        # General
        print(f"\n📊 GENERAL")
        print(f"  DB Path:     {DB_FILE}")
        print(f"  DB Size:     {general['db_size_human']}")
        print(f"  WAL Mode:    {'Yes' if general['wal_present'] else 'No'}", end="")
        if general['wal_present']:
            print(f" ({general.get('wal_size', 'N/A')})")
        else:
            print()
        print(f"  Messages:    {general['total_messages']:,}")
        print(f"  Sessions:    {general['total_sessions']:,}")
        print(f"  Tool Calls:  {general['total_tool_calls']:,}")
        print(f"  Errors:      {general['total_errors']:,}")
        print(f"  Quarantine:  {general['quarantine_entries']}")

        # Last 24h
        print(f"\n🕒 LAST 24 HOURS")
        print(f"  Messages:    {last_24h['messages_24h']:,} new")
        print(f"  Scrubbed:    {last_24h['scrubbed_24h']:,}")
        print(f"  Detections:  {last_24h['detections_24h']:,}")
        print(f"  Quarantined: {last_24h['quarantined_24h']:,}")
        print(f"  Audit Events:{last_24h['audit_events_24h']:,}")

        # Operations
        print(f"\n🔧 OPERATIONS")
        print(f"  Last Backup: {backup['last_backup_age']} ({backup['total_backups']} total)")
        print(f"  Last Panic:  {panic['last_panic_age']} ({panic['panic_scans_30d']} in 30d)")
        print(f"  Last Doctor: {doctor['last_doctor_age']} (status: {doctor['last_doctor_status']})")

        # Compact
        print(f"\n📦 AUTO-COMPACT")
        print(f"  Last Compact:{compact['last_compact_age']}")
        print(f"  ENV Override:{compact['autocompact_override']}")

        # FTS
        print(f"\n🔍 FTS5 SEARCH")
        print(f"  Status:      {fts['fts_status']}")

        print("\n" + "=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Memory Observability Dashboard")
    parser.add_argument('--json', action='store_true', help='Output JSON')

    args = parser.parse_args()
    cmd_status(args)

if __name__ == "__main__":
    main()
