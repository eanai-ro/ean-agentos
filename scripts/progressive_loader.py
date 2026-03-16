#!/usr/bin/env python3
"""
PROGRESSIVE LOADER - Context loader cu disclosure nivelat.

Încarcă context din memoria permanentă cu diferite niveluri de detaliu.
Permite economisirea semnificativă de tokeni la încărcarea contextului.

Niveluri:
1. minimal   (50 tok)   - ID + timestamp only
2. summary   (150 tok)  - ID + title + type
3. detailed  (500 tok)  - Summary + context
4. full      (2000 tok) - Complete content
5. expanded  (5000 tok) - Full + related items

Usage:
    python3 progressive_loader.py --level 2           # Nivel summary
    python3 progressive_loader.py --level 4 --full    # Full context
    python3 progressive_loader.py --session latest    # Ultima sesiune
    python3 progressive_loader.py --expand 12345      # Expandează un item
"""

import sys
import sqlite3
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"

# Configurație niveluri disclosure
DISCLOSURE_LEVELS = {
    1: {"name": "minimal", "max_tokens": 50},
    2: {"name": "summary", "max_tokens": 150},
    3: {"name": "detailed", "max_tokens": 500},
    4: {"name": "full", "max_tokens": 2000},
    5: {"name": "expanded", "max_tokens": 5000},
}


def get_db_connection() -> sqlite3.Connection:
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def estimate_tokens(text: str) -> int:
    """Estimează numărul de tokeni (aproximativ 4 caractere per token)."""
    if not text:
        return 0
    return len(text) // 4


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Trunchiază textul la un număr maxim de tokeni."""
    if not text:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def format_message_minimal(row: sqlite3.Row) -> str:
    """Format minimal: ID + timestamp."""
    timestamp = row['timestamp'][:16] if row['timestamp'] else "N/A"
    return f"[{row['id']}] {timestamp} - {row['role']}"


def format_message_summary(row: sqlite3.Row) -> str:
    """Format summary: ID + rol + preview conținut."""
    timestamp = row['timestamp'][:16] if row['timestamp'] else "N/A"
    content = row['content'][:100].replace('\n', ' ') if row['content'] else ""
    return f"[{row['id']}] {timestamp} {row['role']}: {content}..."


def format_message_detailed(row: sqlite3.Row) -> str:
    """Format detailed: Summary + context."""
    timestamp = row['timestamp'][:16] if row['timestamp'] else "N/A"
    content = row['content'][:400].replace('\n', ' ') if row['content'] else ""
    project = Path(row['project_path']).name if row['project_path'] else "N/A"
    return f"[{row['id']}] {timestamp} {row['role']} ({project}): {content}"


def format_message_full(row: sqlite3.Row) -> str:
    """Format full: Conținut complet."""
    timestamp = row['timestamp'] if row['timestamp'] else "N/A"
    content = row['content'][:1600] if row['content'] else ""
    project = row['project_path'] or "N/A"
    return f"""[ID: {row['id']}]
Timestamp: {timestamp}
Role: {row['role']}
Project: {project}
Content:
{content}"""


def format_message_expanded(row: sqlite3.Row, related: List = None) -> str:
    """Format expanded: Full + related items."""
    base = format_message_full(row)

    if related:
        base += "\n\n--- Related ---"
        for r in related[:3]:
            base += f"\n  [{r['id']}] {r['content'][:100]}..."

    return base


def get_context_messages(
    level: int = 2,
    session_id: Optional[str] = None,
    project_path: Optional[str] = None,
    limit: int = 20,
    days: int = 7
) -> List[str]:
    """
    Obține mesaje formatate la nivelul specificat.

    Args:
        level: Nivel disclosure (1-5)
        session_id: Filtrează după sesiune
        project_path: Filtrează după proiect
        limit: Număr maxim de mesaje
        days: Ultimele N zile

    Returns:
        Lista de mesaje formatate
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Construiește query
    where_clauses = []
    params = []

    if session_id:
        if session_id == 'latest':
            cursor.execute("SELECT session_id FROM sessions ORDER BY started_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                session_id = row['session_id']
        where_clauses.append("session_id = ?")
        params.append(session_id)

    if project_path:
        where_clauses.append("project_path LIKE ?")
        params.append(f"%{project_path}%")

    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        where_clauses.append("timestamp > ?")
        params.append(cutoff)

    where = " AND ".join(where_clauses) if where_clauses else "1=1"
    params.append(limit)

    cursor.execute(f"""
        SELECT id, session_id, timestamp, role, content, project_path
        FROM messages
        WHERE {where}
        ORDER BY timestamp DESC
        LIMIT ?
    """, params)

    rows = cursor.fetchall()
    conn.close()

    # Formatează la nivel specificat
    formatted = []
    for row in reversed(rows):  # Cronologic
        if level == 1:
            formatted.append(format_message_minimal(row))
        elif level == 2:
            formatted.append(format_message_summary(row))
        elif level == 3:
            formatted.append(format_message_detailed(row))
        elif level == 4:
            formatted.append(format_message_full(row))
        else:  # level 5
            formatted.append(format_message_expanded(row))

    return formatted


def get_context_sessions(level: int = 2, limit: int = 10) -> List[str]:
    """Obține sesiunile recente la nivelul specificat."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.session_id, s.project_path, s.started_at, s.ended_at,
               s.total_messages, s.total_tool_calls, s.summary
        FROM sessions s
        ORDER BY s.started_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    formatted = []
    for row in rows:
        project = Path(row['project_path']).name if row['project_path'] else "N/A"
        started = row['started_at'][:16] if row['started_at'] else "N/A"

        if level == 1:
            formatted.append(f"[{row['session_id'][:20]}] {started}")
        elif level == 2:
            formatted.append(f"[{row['session_id'][:20]}] {started} - {project} ({row['total_messages']} msg)")
        elif level == 3:
            ended = row['ended_at'][:16] if row['ended_at'] else "ongoing"
            formatted.append(f"""Session: {row['session_id'][:30]}
  Project: {project}
  Started: {started} | Ended: {ended}
  Messages: {row['total_messages']} | Tools: {row['total_tool_calls']}""")
        else:
            summary = row['summary'][:500] if row['summary'] else "No summary"
            formatted.append(f"""Session: {row['session_id']}
  Project: {row['project_path']}
  Started: {row['started_at']}
  Ended: {row['ended_at'] or 'ongoing'}
  Messages: {row['total_messages']} | Tool calls: {row['total_tool_calls']}
  Summary: {summary}""")

    return formatted


def get_context_errors(level: int = 2, limit: int = 10) -> List[str]:
    """Obține erorile recente la nivelul specificat."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, error_type, error_message, solution, solution_worked,
               language, file_path, created_at
        FROM errors_solutions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    formatted = []
    for row in rows:
        status = "Resolved" if row['solution_worked'] else "Unresolved"

        if level == 1:
            formatted.append(f"[{row['id']}] {row['error_type']} - {status}")
        elif level == 2:
            error_preview = row['error_message'][:80] if row['error_message'] else "N/A"
            formatted.append(f"[{row['id']}] {row['error_type']}: {error_preview}... ({status})")
        elif level == 3:
            error_preview = row['error_message'][:200] if row['error_message'] else "N/A"
            solution_preview = row['solution'][:200] if row['solution'] else "No solution"
            formatted.append(f"""[{row['id']}] {row['error_type']} ({row['language'] or 'N/A'})
  Error: {error_preview}
  Solution: {solution_preview}
  Status: {status}""")
        else:
            formatted.append(f"""Error #{row['id']} ({row['error_type']})
  Language: {row['language'] or 'N/A'}
  File: {row['file_path'] or 'N/A'}
  Created: {row['created_at']}
  Status: {status}
  Error: {row['error_message']}
  Solution: {row['solution'] or 'None'}""")

    return formatted


def get_full_context(
    level: int = 2,
    session_id: Optional[str] = None,
    project_path: Optional[str] = None,
    include_sessions: bool = True,
    include_messages: bool = True,
    include_errors: bool = True,
    message_limit: int = 20,
    session_limit: int = 5,
    error_limit: int = 5
) -> Dict[str, Any]:
    """
    Obține contextul complet la nivelul specificat.

    Returns:
        Dict cu toate secțiunile și statistici
    """
    context = {
        'level': level,
        'level_name': DISCLOSURE_LEVELS.get(level, {}).get('name', 'unknown'),
        'max_tokens': DISCLOSURE_LEVELS.get(level, {}).get('max_tokens', 1000),
        'sections': {},
        'total_tokens': 0
    }

    if include_sessions:
        sessions = get_context_sessions(level, session_limit)
        context['sections']['sessions'] = sessions
        context['total_tokens'] += sum(estimate_tokens(s) for s in sessions)

    if include_messages:
        messages = get_context_messages(level, session_id, project_path, message_limit)
        context['sections']['messages'] = messages
        context['total_tokens'] += sum(estimate_tokens(m) for m in messages)

    if include_errors:
        errors = get_context_errors(level, error_limit)
        context['sections']['errors'] = errors
        context['total_tokens'] += sum(estimate_tokens(e) for e in errors)

    return context


def expand_item(source_table: str, source_id: int) -> Optional[str]:
    """Expandează un item specific la nivel full."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if source_table == 'messages':
        cursor.execute("""
            SELECT id, session_id, timestamp, role, content, project_path
            FROM messages WHERE id = ?
        """, (source_id,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return format_message_expanded(row)

    elif source_table == 'sessions':
        cursor.execute("""
            SELECT * FROM sessions WHERE session_id = ?
        """, (str(source_id),))
        row = cursor.fetchone()
        if row:
            # Include și mesajele sesiunii
            cursor.execute("""
                SELECT content FROM messages
                WHERE session_id = ?
                ORDER BY timestamp
                LIMIT 10
            """, (row['session_id'],))
            messages = cursor.fetchall()
            conn.close()

            result = f"""Session: {row['session_id']}
Project: {row['project_path']}
Started: {row['started_at']}
Ended: {row['ended_at'] or 'ongoing'}
Summary: {row['summary'] or 'No summary'}

Messages ({row['total_messages']} total):"""
            for m in messages:
                result += f"\n  - {m['content'][:100]}..."
            return result

    conn.close()
    return None


def print_context(context: Dict, output_format: str = 'text'):
    """Afișează contextul formatat."""
    if output_format == 'json':
        print(json.dumps(context, indent=2, ensure_ascii=False))
        return

    level_info = DISCLOSURE_LEVELS.get(context['level'], {})
    print("\n" + "="*60)
    print(f"  CONTEXT - Level {context['level']} ({level_info.get('name', 'unknown')})")
    print(f"  Max tokens: {level_info.get('max_tokens', 'N/A')} | Actual: {context['total_tokens']}")
    print("="*60)

    for section_name, items in context.get('sections', {}).items():
        print(f"\n--- {section_name.upper()} ({len(items)} items) ---")
        for item in items:
            print(f"\n{item}")

    print("\n" + "="*60)
    print(f"  Total tokens estimate: {context['total_tokens']}")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Context loader cu progressive disclosure"
    )
    parser.add_argument("--level", "-l", type=int, default=2, choices=[1, 2, 3, 4, 5],
                        help="Nivel disclosure (1=minimal, 5=expanded). Default: 2")
    parser.add_argument("--session", "-s", type=str,
                        help="Filtrează după session_id (sau 'latest')")
    parser.add_argument("--project", "-p", type=str,
                        help="Filtrează după project_path")
    parser.add_argument("--messages", "-m", type=int, default=20,
                        help="Număr maxim de mesaje (default: 20)")
    parser.add_argument("--sessions-limit", type=int, default=5,
                        help="Număr maxim de sesiuni (default: 5)")
    parser.add_argument("--errors-limit", type=int, default=5,
                        help="Număr maxim de erori (default: 5)")
    parser.add_argument("--expand", "-e", type=str,
                        help="Expandează un item: 'messages:123' sau 'sessions:xyz'")
    parser.add_argument("--no-sessions", action="store_true",
                        help="Exclude sesiunile")
    parser.add_argument("--no-messages", action="store_true",
                        help="Exclude mesajele")
    parser.add_argument("--no-errors", action="store_true",
                        help="Exclude erorile")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output în format JSON")
    parser.add_argument("--compare", "-c", action="store_true",
                        help="Compară toate nivelurile")

    args = parser.parse_args()

    # Expand item specific
    if args.expand:
        parts = args.expand.split(':')
        if len(parts) == 2:
            table, id_str = parts
            try:
                expanded = expand_item(table, int(id_str) if id_str.isdigit() else id_str)
                if expanded:
                    print(expanded)
                else:
                    print(f"Nu s-a găsit {table}:{id_str}")
            except Exception as e:
                print(f"Eroare: {e}")
        else:
            print("Format: --expand table:id (ex: messages:12345)")
        return

    # Comparație niveluri
    if args.compare:
        print("\n" + "="*60)
        print("  COMPARAȚIE NIVELURI DISCLOSURE")
        print("="*60)

        for level in range(1, 6):
            context = get_full_context(
                level=level,
                session_id=args.session,
                project_path=args.project,
                include_sessions=not args.no_sessions,
                include_messages=not args.no_messages,
                include_errors=not args.no_errors,
                message_limit=args.messages,
                session_limit=args.sessions_limit,
                error_limit=args.errors_limit
            )
            level_info = DISCLOSURE_LEVELS[level]
            print(f"\n  Level {level} ({level_info['name']}): ~{context['total_tokens']} tokens")

        print("\n" + "="*60 + "\n")
        return

    # Obține context
    context = get_full_context(
        level=args.level,
        session_id=args.session,
        project_path=args.project,
        include_sessions=not args.no_sessions,
        include_messages=not args.no_messages,
        include_errors=not args.no_errors,
        message_limit=args.messages,
        session_limit=args.sessions_limit,
        error_limit=args.errors_limit
    )

    # Afișează
    print_context(context, 'json' if args.json else 'text')


if __name__ == "__main__":
    main()
