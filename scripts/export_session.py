#!/usr/bin/env python3
"""
EXPORT SESSION - Exportă sesiuni în format Markdown.

Comenzi:
    export_session list                    # Listează sesiunile disponibile
    export_session export SESSION_ID       # Exportă o sesiune specifică
    export_session export --last           # Exportă ultima sesiune
    export_session export --today          # Exportă sesiunile de azi
    export_session export --all            # Exportă toate sesiunile
    export_session export SESSION_ID -o /path/output.md  # Cu cale personalizată

Utilizare:
    python3 scripts/export_session.py list
    python3 scripts/export_session.py export --last
"""

import sys
import os
import json
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    from v2_common import resolve_db_path
    DB_PATH = resolve_db_path()
except ImportError:
    DB_PATH = Path.home() / ".claude" / "memory" / "global.db"
EXPORT_DIR = Path(__file__).parent.parent / "exports"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_sessions(limit: int = 20):
    """Listează sesiunile disponibile."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.session_id, s.project_path, s.started_at, s.ended_at,
               (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) as msg_count,
               (SELECT COUNT(*) FROM tool_calls t WHERE t.session_id = s.session_id) as tool_count
        FROM sessions s
        ORDER BY s.started_at DESC
        LIMIT ?
    """, (limit,))

    results = cursor.fetchall()

    print(f"\n{'='*70}")
    print("  📋 SESIUNI DISPONIBILE PENTRU EXPORT")
    print('='*70)

    if not results:
        print("\n  Nu există sesiuni.")
    else:
        print(f"\n  {'ID Sesiune':<40} {'Proiect':<15} {'Mesaje':>7} {'Data':>12}")
        print(f"  {'-'*40} {'-'*15} {'-'*7} {'-'*12}")

        for row in results:
            session_id = row['session_id'][:35] + "..." if len(row['session_id']) > 35 else row['session_id']
            project = Path(row['project_path']).name if row['project_path'] else "N/A"
            project = project[:15] if len(project) > 15 else project
            msg_count = row['msg_count'] or 0
            date = row['started_at'][:10] if row['started_at'] else "N/A"

            print(f"  {session_id:<40} {project:<15} {msg_count:>7} {date:>12}")

    print(f"\n{'='*70}")
    print("  Folosește: export_session export <SESSION_ID>")
    print('='*70 + "\n")

    conn.close()


def export_session(session_id: str, output_path: Path = None) -> Path:
    """Exportă o sesiune în format Markdown."""
    conn = get_db()
    cursor = conn.cursor()

    # Obține informații sesiune
    cursor.execute("""
        SELECT session_id, project_path, started_at, ended_at, summary
        FROM sessions
        WHERE session_id = ?
    """, (session_id,))

    session = cursor.fetchone()
    if not session:
        print(f"❌ Sesiune negăsită: {session_id}")
        return None

    # Pregătește output path
    if output_path is None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        date_str = session['started_at'][:10].replace("-", "") if session['started_at'] else "unknown"
        output_path = EXPORT_DIR / f"session_{date_str}_{session_id[:8]}.md"

    # Obține mesaje
    cursor.execute("""
        SELECT timestamp, role, content, message_type
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC
    """, (session_id,))
    messages = cursor.fetchall()

    # Obține tool calls
    cursor.execute("""
        SELECT timestamp, tool_name, tool_input, tool_result, exit_code, file_path
        FROM tool_calls
        WHERE session_id = ?
        ORDER BY timestamp ASC
    """, (session_id,))
    tool_calls = cursor.fetchall()

    # Generează Markdown
    md_content = generate_markdown(session, messages, tool_calls)

    # Scrie fișierul
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content, encoding='utf-8')

    print(f"✅ Sesiune exportată: {output_path}")
    print(f"   📝 {len(messages)} mesaje, {len(tool_calls)} tool calls")

    conn.close()
    return output_path


def generate_markdown(session, messages, tool_calls) -> str:
    """Generează conținut Markdown pentru o sesiune."""
    lines = []

    # Header
    project_name = Path(session['project_path']).name if session['project_path'] else "Unknown"
    lines.append(f"# Sesiune Claude Code")
    lines.append("")
    lines.append(f"**Proiect:** {project_name}")
    lines.append(f"**Cale:** `{session['project_path'] or 'N/A'}`")
    lines.append(f"**Început:** {session['started_at'] or 'N/A'}")
    lines.append(f"**Sfârșit:** {session['ended_at'] or 'În curs'}")
    lines.append(f"**Session ID:** `{session['session_id']}`")
    lines.append("")

    if session['summary']:
        lines.append("## Rezumat")
        lines.append("")
        lines.append(session['summary'])
        lines.append("")

    # Statistici
    lines.append("## Statistici")
    lines.append("")
    lines.append(f"- **Mesaje:** {len(messages)}")
    lines.append(f"- **Tool Calls:** {len(tool_calls)}")

    # Contorizează tipuri tool calls
    tool_types = {}
    for tc in tool_calls:
        tool_name = tc['tool_name']
        tool_types[tool_name] = tool_types.get(tool_name, 0) + 1

    if tool_types:
        lines.append(f"- **Tipuri acțiuni:**")
        for tool_name, count in sorted(tool_types.items(), key=lambda x: -x[1]):
            lines.append(f"  - {tool_name}: {count}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Conversație
    lines.append("## Conversație")
    lines.append("")

    # Combină mesaje și tool calls cronologic
    all_events = []

    for msg in messages:
        all_events.append({
            'type': 'message',
            'timestamp': msg['timestamp'],
            'data': msg
        })

    for tc in tool_calls:
        all_events.append({
            'type': 'tool_call',
            'timestamp': tc['timestamp'],
            'data': tc
        })

    # Sortează după timestamp
    all_events.sort(key=lambda x: x['timestamp'] or '')

    for event in all_events:
        if event['type'] == 'message':
            msg = event['data']
            role = msg['role']
            content = msg['content'] or ''
            timestamp = msg['timestamp'][:16] if msg['timestamp'] else ''

            if role == 'user':
                lines.append(f"### 👤 Utilizator ({timestamp})")
            elif role == 'assistant':
                lines.append(f"### 🤖 Claude ({timestamp})")
            else:
                lines.append(f"### 📌 {role.title()} ({timestamp})")

            lines.append("")
            lines.append(content)
            lines.append("")

        elif event['type'] == 'tool_call':
            tc = event['data']
            tool_name = tc['tool_name']
            exit_code = tc['exit_code']
            timestamp = tc['timestamp'][:16] if tc['timestamp'] else ''

            status = "✅" if exit_code == 0 or exit_code is None else "❌"

            lines.append(f"#### {status} {tool_name} ({timestamp})")
            lines.append("")

            # Parse tool_input
            try:
                tool_input = json.loads(tc['tool_input']) if tc['tool_input'] else {}

                if tool_name == 'Bash' and 'command' in tool_input:
                    lines.append("```bash")
                    lines.append(tool_input['command'])
                    lines.append("```")
                elif tool_name in ('Edit', 'Write') and tc['file_path']:
                    lines.append(f"📁 `{tc['file_path']}`")
                elif tool_name == 'Read' and tc['file_path']:
                    lines.append(f"📖 `{tc['file_path']}`")
                else:
                    # Afișează input JSON formatat
                    input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
                    if len(input_str) > 500:
                        input_str = input_str[:500] + "\n..."
                    lines.append("```json")
                    lines.append(input_str)
                    lines.append("```")

            except:
                if tc['tool_input']:
                    lines.append(f"Input: {tc['tool_input'][:200]}...")

            # Result (trunchiat)
            if tc['tool_result']:
                result = tc['tool_result']
                if len(result) > 500:
                    result = result[:500] + "\n... (trunchiat)"
                lines.append("")
                lines.append("<details>")
                lines.append("<summary>Output</summary>")
                lines.append("")
                lines.append("```")
                lines.append(result)
                lines.append("```")
                lines.append("</details>")

            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Exportat la {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")
    lines.append("*Generat de Claude Code Memory System*")

    return "\n".join(lines)


def export_last_session(output_path: Path = None) -> Path:
    """Exportă ultima sesiune."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT session_id FROM sessions
        ORDER BY started_at DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    if not row:
        print("❌ Nu există sesiuni.")
        return None

    return export_session(row['session_id'], output_path)


def export_today_sessions(output_dir: Path = None) -> list:
    """Exportă toate sesiunile de azi."""
    conn = get_db()
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT session_id FROM sessions
        WHERE started_at LIKE ?
        ORDER BY started_at ASC
    """, (f"{today}%",))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"❌ Nu există sesiuni pentru {today}")
        return []

    exported = []
    for row in rows:
        if output_dir:
            path = export_session(row['session_id'], output_dir / f"session_{row['session_id'][:8]}.md")
        else:
            path = export_session(row['session_id'])
        if path:
            exported.append(path)

    print(f"\n✅ Exportate {len(exported)} sesiuni de azi")
    return exported


def export_all_sessions(output_dir: Path = None) -> list:
    """Exportă toate sesiunile."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT session_id FROM sessions ORDER BY started_at ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("❌ Nu există sesiuni.")
        return []

    exported = []
    for row in rows:
        if output_dir:
            path = export_session(row['session_id'], output_dir / f"session_{row['session_id'][:8]}.md")
        else:
            path = export_session(row['session_id'])
        if path:
            exported.append(path)

    print(f"\n✅ Exportate {len(exported)} sesiuni în total")
    return exported


def main():
    parser = argparse.ArgumentParser(description='Export sesiuni în format Markdown')
    subparsers = parser.add_subparsers(dest='command', help='Comenzi disponibile')

    # List
    list_parser = subparsers.add_parser('list', help='Listează sesiunile')
    list_parser.add_argument('--limit', '-n', type=int, default=20, help='Număr maxim')

    # Export
    export_parser = subparsers.add_parser('export', help='Exportă sesiuni')
    export_parser.add_argument('session_id', nargs='?', help='ID sesiune')
    export_parser.add_argument('--last', '-l', action='store_true', help='Ultima sesiune')
    export_parser.add_argument('--today', '-t', action='store_true', help='Sesiunile de azi')
    export_parser.add_argument('--all', '-a', action='store_true', help='Toate sesiunile')
    export_parser.add_argument('--output', '-o', type=str, help='Cale output')

    args = parser.parse_args()

    if not DB_PATH.exists():
        print("❌ Baza de date nu există!")
        sys.exit(1)

    if args.command == 'list':
        list_sessions(args.limit)
    elif args.command == 'export':
        output_path = Path(args.output) if args.output else None

        if args.last:
            export_last_session(output_path)
        elif args.today:
            export_today_sessions(output_path)
        elif args.all:
            export_all_sessions(output_path)
        elif args.session_id:
            export_session(args.session_id, output_path)
        else:
            print("❌ Specifică: --last, --today, --all sau SESSION_ID")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
