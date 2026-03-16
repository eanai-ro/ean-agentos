#!/usr/bin/env python3
"""
AUTO SUMMARIZER - Generează rezumate automate pentru sesiuni.

Creează rezumate la sfârșitul sesiunilor și digest-uri zilnice.
Folosește Z.AI GLM-4.7 pentru generarea rezumatelor.

Funcționalități:
- summarize_session(session_id) - Rezumat sesiune
- extract_key_topics(messages) - Extrage topicuri principale
- daily_digest() - Rezumat zilnic
- compress_to_observation(content, max_tokens) - Compresie

Usage:
    python3 auto_summarizer.py --session latest
    python3 auto_summarizer.py --session abc123
    python3 auto_summarizer.py --daily
    python3 auto_summarizer.py --pending
"""

import sys
import os
import sqlite3
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error

try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"
ZAI_CONFIG = Path("/mnt/lucru/proiecte/claude/.config/zai-api.json")

# Configurație
MAX_MESSAGES_FOR_SUMMARY = 50
MAX_CHARS_PER_MESSAGE = 500
SUMMARY_MAX_TOKENS = 500


def get_db_connection() -> sqlite3.Connection:
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def get_zai_api_key() -> Optional[str]:
    """Citește API key pentru Z.AI."""
    if not ZAI_CONFIG.exists():
        return None

    try:
        with open(ZAI_CONFIG) as f:
            config = json.load(f)
            return config.get('api_key')
    except Exception:
        return None


def call_zai_api(prompt: str, max_tokens: int = 500) -> Optional[str]:
    """
    Apelează Z.AI API pentru generare text.

    Args:
        prompt: Promptul pentru model
        max_tokens: Număr maxim de tokeni în răspuns

    Returns:
        Răspunsul modelului sau None
    """
    api_key = get_zai_api_key()
    if not api_key:
        return None

    url = "https://api.z.ai/api/anthropic/v1/messages"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    data = {
        "model": "glm-4.7",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('content') and len(result['content']) > 0:
                return result['content'][0].get('text', '')
    except urllib.error.HTTPError as e:
        print(f"⚠️ Z.AI API error: {e.code}")
    except Exception as e:
        print(f"⚠️ Z.AI API error: {e}")

    return None


def extract_key_topics(messages: List[str]) -> List[str]:
    """
    Extrage topicuri principale din mesaje folosind euristici.

    Args:
        messages: Lista de mesaje

    Returns:
        Lista de topicuri cheie
    """
    # Keywords și patterns pentru detectare topicuri
    topic_patterns = {
        'docker': r'\b(docker|container|compose|dockerfile)\b',
        'git': r'\b(git|commit|push|pull|branch|merge)\b',
        'database': r'\b(database|sql|postgres|mysql|sqlite|query)\b',
        'api': r'\b(api|endpoint|rest|graphql|request|response)\b',
        'testing': r'\b(test|pytest|jest|unit|integration)\b',
        'deployment': r'\b(deploy|production|staging|ci/cd|pipeline)\b',
        'authentication': r'\b(auth|login|token|jwt|session|password)\b',
        'error_handling': r'\b(error|exception|bug|fix|debug)\b',
        'configuration': r'\b(config|setting|environment|env|variable)\b',
        'frontend': r'\b(react|vue|angular|frontend|ui|component)\b',
        'backend': r'\b(backend|server|fastapi|flask|django|express)\b',
        'ml_ai': r'\b(model|training|neural|embedding|transformer)\b',
        'file_operations': r'\b(file|read|write|edit|create|delete)\b',
        'memory': r'\b(memory|cache|storage|session)\b',
    }

    # Combină toate mesajele
    all_text = ' '.join(messages).lower()

    # Găsește topicuri
    topics = []
    for topic, pattern in topic_patterns.items():
        if re.search(pattern, all_text, re.IGNORECASE):
            topics.append(topic)

    return topics[:10]  # Maxim 10 topicuri


def extract_files_mentioned(messages: List[str]) -> List[str]:
    """Extrage fișierele menționate în mesaje."""
    file_pattern = r'[/\\][\w\-./\\]+\.\w{1,10}'
    files = set()

    for msg in messages:
        matches = re.findall(file_pattern, msg)
        for m in matches:
            if not any(x in m.lower() for x in ['http', 'www', 'example']):
                files.add(m)

    return list(files)[:20]  # Maxim 20 fișiere


def generate_local_summary(messages: List[Dict], session_info: Dict) -> str:
    """
    Generează rezumat local fără API.

    Folosește euristici pentru a extrage informațiile cheie.
    """
    if not messages:
        return "Sesiune fără mesaje."

    # Extrage conținut
    user_msgs = [m['content'] for m in messages if m.get('role') == 'user']
    assistant_msgs = [m['content'] for m in messages if m.get('role') == 'assistant']

    # Statistici
    total = len(messages)
    user_count = len(user_msgs)
    assistant_count = len(assistant_msgs)

    # Topicuri și fișiere
    all_content = [m['content'] for m in messages if m.get('content')]
    topics = extract_key_topics(all_content)
    files = extract_files_mentioned(all_content)

    # Construiește rezumat
    summary_parts = []

    # Header
    project = Path(session_info.get('project_path', '')).name or 'Unknown'
    started = session_info.get('started_at', '')[:16]
    summary_parts.append(f"Sesiune în proiectul {project}, începută la {started}.")

    # Statistici
    summary_parts.append(f"Conține {total} mesaje ({user_count} user, {assistant_count} assistant).")

    # Topicuri
    if topics:
        summary_parts.append(f"Topicuri principale: {', '.join(topics[:5])}.")

    # Fișiere
    if files:
        summary_parts.append(f"Fișiere afectate: {', '.join(files[:5])}.")

    # Preview primul mesaj user
    if user_msgs:
        first_request = user_msgs[0][:200].replace('\n', ' ')
        summary_parts.append(f"Prima cerere: \"{first_request}...\"")

    return ' '.join(summary_parts)


def summarize_session(
    session_id: str,
    use_api: bool = True,
    save_to_db: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Generează rezumat pentru o sesiune.

    Args:
        session_id: ID-ul sesiunii (sau 'latest')
        use_api: Folosește Z.AI API pentru rezumat
        save_to_db: Salvează rezumatul în DB

    Returns:
        Dict cu rezumatul și metadata
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Găsește sesiunea
    if session_id == 'latest':
        cursor.execute("""
            SELECT session_id, project_path, started_at, ended_at,
                   total_messages, total_tool_calls
            FROM sessions
            ORDER BY started_at DESC
            LIMIT 1
        """)
    else:
        cursor.execute("""
            SELECT session_id, project_path, started_at, ended_at,
                   total_messages, total_tool_calls
            FROM sessions
            WHERE session_id = ? OR session_id LIKE ?
        """, (session_id, f"%{session_id}%"))

    session = cursor.fetchone()
    if not session:
        print(f"⚠️ Sesiune negăsită: {session_id}")
        conn.close()
        return None

    actual_session_id = session['session_id']

    # Verifică dacă există deja rezumat
    cursor.execute("""
        SELECT content FROM session_summaries
        WHERE session_id = ? AND summary_type = 'auto'
        ORDER BY created_at DESC
        LIMIT 1
    """, (actual_session_id,))

    existing = cursor.fetchone()
    if existing:
        print(f"ℹ️ Sesiune are deja rezumat auto")

    # Obține mesajele
    cursor.execute("""
        SELECT role, content, timestamp
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp
        LIMIT ?
    """, (actual_session_id, MAX_MESSAGES_FOR_SUMMARY))

    messages = [dict(row) for row in cursor.fetchall()]

    session_info = dict(session)

    # Generează rezumat
    summary_text = None

    if use_api:
        # Pregătește context pentru API
        msg_context = []
        for msg in messages[-20:]:  # Ultimele 20
            role = msg['role']
            content = msg['content'][:MAX_CHARS_PER_MESSAGE] if msg['content'] else ""
            msg_context.append(f"{role}: {content}")

        prompt = f"""Rezumă pe scurt următoarea sesiune de programare în limba română.
Include: ce s-a lucrat, deciziile importante, fișierele modificate.
Maxim 3-4 propoziții.

Proiect: {session_info.get('project_path', 'Unknown')}
Mesaje: {session_info.get('total_messages', 0)}

Conținut:
{chr(10).join(msg_context)}"""

        summary_text = call_zai_api(prompt, SUMMARY_MAX_TOKENS)

    # Fallback la rezumat local
    if not summary_text:
        summary_text = generate_local_summary(messages, session_info)

    # Extrage topicuri și fișiere
    all_content = [m['content'] for m in messages if m.get('content')]
    topics = extract_key_topics(all_content)
    files = extract_files_mentioned(all_content)

    # Numără erori rezolvate
    cursor.execute("""
        SELECT COUNT(*) FROM errors_solutions
        WHERE session_id = ? AND solution_worked = 1
    """, (actual_session_id,))
    errors_resolved = cursor.fetchone()[0]

    # Salvează în DB
    if save_to_db:
        cursor.execute("""
            INSERT INTO session_summaries
            (session_id, summary_type, content, key_topics, files_mentioned,
             errors_resolved, tokens_used, created_by)
            VALUES (?, 'auto', ?, ?, ?, ?, ?, ?)
        """, (
            actual_session_id,
            summary_text,
            json.dumps(topics),
            json.dumps(files),
            errors_resolved,
            len(summary_text) // 4,  # Estimate tokens
            'auto' if not use_api else 'zai'
        ))
        conn.commit()

    conn.close()

    return {
        'session_id': actual_session_id,
        'project': session_info.get('project_path'),
        'started_at': session_info.get('started_at'),
        'ended_at': session_info.get('ended_at'),
        'total_messages': session_info.get('total_messages'),
        'summary': summary_text,
        'topics': topics,
        'files': files,
        'errors_resolved': errors_resolved
    }


def daily_digest(date: str = None, save_to_db: bool = True) -> Dict[str, Any]:
    """
    Generează digest zilnic pentru toate sesiunile din zi.

    Args:
        date: Data în format YYYY-MM-DD (default: azi)
        save_to_db: Salvează în DB

    Returns:
        Dict cu digestul zilnic
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Găsește sesiunile din ziua respectivă
    cursor.execute("""
        SELECT session_id, project_path, started_at, ended_at,
               total_messages, total_tool_calls
        FROM sessions
        WHERE DATE(started_at) = ?
        ORDER BY started_at
    """, (date,))

    sessions = [dict(row) for row in cursor.fetchall()]

    if not sessions:
        conn.close()
        return {
            'date': date,
            'sessions_count': 0,
            'digest': f"Nu există sesiuni pentru {date}"
        }

    # Statistici agregate
    total_messages = sum(s.get('total_messages', 0) or 0 for s in sessions)
    total_tools = sum(s.get('total_tool_calls', 0) or 0 for s in sessions)
    projects = list(set(Path(s.get('project_path', '')).name for s in sessions if s.get('project_path')))

    # Colectează toate mesajele
    all_messages = []
    for s in sessions:
        cursor.execute("""
            SELECT content FROM messages
            WHERE session_id = ? AND content IS NOT NULL
            LIMIT 50
        """, (s['session_id'],))
        all_messages.extend([row['content'] for row in cursor.fetchall()])

    topics = extract_key_topics(all_messages)
    files = extract_files_mentioned(all_messages)

    # Generează digest
    digest_parts = [
        f"Digest pentru {date}:",
        f"- {len(sessions)} sesiuni în {len(projects)} proiecte",
        f"- {total_messages} mesaje, {total_tools} tool calls",
    ]

    if projects:
        digest_parts.append(f"- Proiecte: {', '.join(projects[:5])}")

    if topics:
        digest_parts.append(f"- Topicuri: {', '.join(topics[:5])}")

    digest_text = '\n'.join(digest_parts)

    # Salvează
    if save_to_db:
        # Folosim un session_id special pentru digest
        digest_session_id = f"digest_{date}"

        cursor.execute("""
            INSERT OR REPLACE INTO session_summaries
            (session_id, summary_type, content, key_topics, files_mentioned,
             tokens_used, created_by)
            VALUES (?, 'daily_digest', ?, ?, ?, ?, 'auto')
        """, (
            digest_session_id,
            digest_text,
            json.dumps(topics),
            json.dumps(files),
            len(digest_text) // 4
        ))
        conn.commit()

    conn.close()

    return {
        'date': date,
        'sessions_count': len(sessions),
        'total_messages': total_messages,
        'total_tools': total_tools,
        'projects': projects,
        'topics': topics,
        'files': files[:10],
        'digest': digest_text
    }


def process_pending_sessions(limit: int = 10) -> int:
    """
    Procesează sesiunile care nu au rezumat.

    Returns:
        Numărul de sesiuni procesate
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Găsește sesiuni fără rezumat
    cursor.execute("""
        SELECT s.session_id
        FROM sessions s
        LEFT JOIN session_summaries ss ON s.session_id = ss.session_id AND ss.summary_type = 'auto'
        WHERE ss.id IS NULL
          AND s.ended_at IS NOT NULL
          AND s.total_messages > 0
        ORDER BY s.started_at DESC
        LIMIT ?
    """, (limit,))

    pending = [row['session_id'] for row in cursor.fetchall()]
    conn.close()

    if not pending:
        print("✓ Toate sesiunile au rezumate")
        return 0

    print(f"📝 {len(pending)} sesiuni pending")

    processed = 0
    for session_id in pending:
        print(f"  Processing {session_id[:30]}...")
        result = summarize_session(session_id, use_api=True)
        if result:
            processed += 1
            print(f"  ✓ Done")

    return processed


def print_summary(result: Dict):
    """Afișează rezumatul formatat."""
    print("\n" + "="*60)
    print(f"  REZUMAT SESIUNE")
    print("="*60)

    print(f"\n  Session: {result.get('session_id', 'N/A')[:40]}")
    print(f"  Project: {result.get('project', 'N/A')}")
    print(f"  Started: {result.get('started_at', 'N/A')[:19]}")
    print(f"  Messages: {result.get('total_messages', 0)}")

    print(f"\n  Rezumat:")
    print(f"  {result.get('summary', 'N/A')}")

    if result.get('topics'):
        print(f"\n  Topicuri: {', '.join(result['topics'][:5])}")

    if result.get('files'):
        print(f"  Fișiere: {', '.join(result['files'][:5])}")

    print("\n" + "="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generator automat de rezumate pentru sesiuni"
    )
    parser.add_argument("--session", "-s", type=str,
                        help="Rezumă sesiunea specificată (sau 'latest')")
    parser.add_argument("--daily", "-d", action="store_true",
                        help="Generează digest zilnic")
    parser.add_argument("--date", type=str,
                        help="Data pentru digest (YYYY-MM-DD)")
    parser.add_argument("--pending", "-p", action="store_true",
                        help="Procesează sesiunile fără rezumat")
    parser.add_argument("--limit", "-l", type=int, default=10,
                        help="Limită sesiuni pentru --pending")
    parser.add_argument("--no-api", action="store_true",
                        help="Nu folosi Z.AI API (doar local)")
    parser.add_argument("--no-save", action="store_true",
                        help="Nu salva în DB")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output JSON")

    args = parser.parse_args()

    # Procesează pending
    if args.pending:
        count = process_pending_sessions(args.limit)
        print(f"✓ Procesate {count} sesiuni")
        return

    # Digest zilnic
    if args.daily:
        result = daily_digest(args.date, not args.no_save)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("\n" + "="*60)
            print(f"  DIGEST ZILNIC: {result['date']}")
            print("="*60)
            print(f"\n{result['digest']}")
            print("\n" + "="*60 + "\n")
        return

    # Rezumat sesiune
    if args.session:
        result = summarize_session(
            args.session,
            use_api=not args.no_api,
            save_to_db=not args.no_save
        )
        if result:
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print_summary(result)
        return

    # Help
    parser.print_help()
    print("\nExemple:")
    print("  python3 auto_summarizer.py --session latest")
    print("  python3 auto_summarizer.py --daily")
    print("  python3 auto_summarizer.py --pending")


if __name__ == "__main__":
    main()
