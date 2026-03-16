#!/usr/bin/env python3
"""
GIT MEMORY HOOK - Salvează commit-urile în memoria permanentă.

Acest script poate fi folosit:
1. Ca post-commit hook global: ~/.config/git/hooks/post-commit
2. Ca post-commit hook per-proiect: .git/hooks/post-commit
3. Manual: python3 git_memory_hook.py [commit_hash]

Comenzi:
    git_memory save              # Salvează ultimul commit
    git_memory save abc123       # Salvează commit specific
    git_memory list              # Listează ultimele commit-uri salvate
    git_memory search "mesaj"    # Caută în commit-uri
    git_memory stats             # Statistici commit-uri
"""

import sys
import os
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
import argparse

try:
    from v2_common import resolve_db_path
    DB_PATH = resolve_db_path()
except ImportError:
    DB_PATH = Path.home() / ".claude" / "memory" / "global.db"
SESSION_FILE = Path.home() / ".claude/memory/.current_session"


def get_db():
    return sqlite3.connect(DB_PATH)


def run_git_command(args: list) -> str:
    """Execută o comandă git și returnează output-ul."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        return ""


def get_commit_info(commit_hash: str = "HEAD") -> dict:
    """Obține informații despre un commit."""
    # Format: hash|short|author_name|author_email|date|message
    format_str = "%H|%h|%an|%ae|%aI|%s"
    info = run_git_command(["log", "-1", f"--format={format_str}", commit_hash])

    if not info:
        return None

    parts = info.split("|", 5)
    if len(parts) < 6:
        return None

    # Obține fișierele modificate
    files_output = run_git_command(["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash])
    files_changed = files_output.split("\n") if files_output else []

    # Obține statistici (insertions/deletions)
    stats_output = run_git_command(["diff-tree", "--shortstat", commit_hash])
    insertions = 0
    deletions = 0
    if stats_output:
        import re
        ins_match = re.search(r'(\d+) insertion', stats_output)
        del_match = re.search(r'(\d+) deletion', stats_output)
        if ins_match:
            insertions = int(ins_match.group(1))
        if del_match:
            deletions = int(del_match.group(1))

    return {
        "commit_hash": parts[0],
        "short_hash": parts[1],
        "author_name": parts[2],
        "author_email": parts[3],
        "commit_date": parts[4],
        "message": parts[5],
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions
    }


def save_commit(commit_hash: str = "HEAD", silent: bool = False) -> bool:
    """Salvează un commit în baza de date."""
    info = get_commit_info(commit_hash)

    if not info:
        if not silent:
            print(f"❌ Nu am putut obține informații pentru commit: {commit_hash}")
        return False

    # Obține project path
    project_path = run_git_command(["rev-parse", "--show-toplevel"])

    # Obține session ID dacă există
    session_id = None
    if SESSION_FILE.exists():
        session_id = SESSION_FILE.read_text().strip()

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR IGNORE INTO git_commits
            (commit_hash, short_hash, author_name, author_email, commit_date,
             message, files_changed, insertions, deletions, project_path, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            info["commit_hash"],
            info["short_hash"],
            info["author_name"],
            info["author_email"],
            info["commit_date"],
            info["message"],
            json.dumps(info["files_changed"]),
            info["insertions"],
            info["deletions"],
            project_path,
            session_id
        ))

        conn.commit()

        if cursor.rowcount > 0:
            if not silent:
                print(f"✅ Commit salvat: {info['short_hash']} - {info['message'][:50]}")
                print(f"   📁 {len(info['files_changed'])} fișiere | +{info['insertions']} -{info['deletions']}")
            return True
        else:
            if not silent:
                print(f"ℹ️ Commit deja salvat: {info['short_hash']}")
            return True

    except Exception as e:
        if not silent:
            print(f"❌ Eroare salvare: {e}")
        return False
    finally:
        conn.close()


def list_commits(limit: int = 20, project: str = None):
    """Listează ultimele commit-uri salvate."""
    conn = get_db()
    cursor = conn.cursor()

    sql = """
        SELECT short_hash, message, author_name, commit_date,
               insertions, deletions, project_path
        FROM git_commits
    """
    params = []

    if project:
        sql += " WHERE project_path LIKE ?"
        params.append(f"%{project}%")

    sql += " ORDER BY commit_date DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    results = cursor.fetchall()

    print(f"\n{'='*60}")
    print("  📋 COMMIT-URI SALVATE ÎN MEMORIE")
    print('='*60)

    if not results:
        print("\n  Nu există commit-uri salvate.")
    else:
        for row in results:
            short_hash, message, author, date, ins, dels, project_path = row
            project_name = Path(project_path).name if project_path else "N/A"
            print(f"\n  🔹 {short_hash} | {project_name}")
            print(f"     {message[:60]}...")
            print(f"     👤 {author} | +{ins} -{dels} | {date[:10]}")

    print(f"\n{'='*60}\n")
    conn.close()


def search_commits(query: str, limit: int = 10):
    """Caută în commit-uri."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT short_hash, message, author_name, commit_date,
               files_changed, project_path
        FROM git_commits
        WHERE message LIKE ? OR files_changed LIKE ?
        ORDER BY commit_date DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))

    results = cursor.fetchall()

    print(f"\n{'='*60}")
    print(f"  🔍 CĂUTARE: '{query}'")
    print('='*60)

    if not results:
        print(f"\n  Nu am găsit commit-uri pentru: '{query}'")
    else:
        for row in results:
            short_hash, message, author, date, files_json, project_path = row
            project_name = Path(project_path).name if project_path else "N/A"
            files = json.loads(files_json) if files_json else []

            print(f"\n  🔹 {short_hash} | {project_name}")
            print(f"     {message}")
            if files:
                print(f"     📁 Fișiere: {', '.join(files[:3])}")

    print(f"\n{'='*60}\n")
    conn.close()


def show_stats():
    """Afișează statistici commit-uri."""
    conn = get_db()
    cursor = conn.cursor()

    print(f"\n{'='*60}")
    print("  📊 STATISTICI GIT COMMITS")
    print('='*60)

    cursor.execute("SELECT COUNT(*) FROM git_commits")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(insertions), SUM(deletions) FROM git_commits")
    row = cursor.fetchone()
    total_ins = row[0] or 0
    total_dels = row[1] or 0

    print(f"\n  Total commit-uri: {total}")
    print(f"  Total linii adăugate: +{total_ins}")
    print(f"  Total linii șterse: -{total_dels}")

    # Per proiect
    cursor.execute("""
        SELECT project_path, COUNT(*) as cnt
        FROM git_commits
        GROUP BY project_path
        ORDER BY cnt DESC
        LIMIT 10
    """)

    projects = cursor.fetchall()
    if projects:
        print(f"\n  Per proiect:")
        for project, cnt in projects:
            name = Path(project).name if project else "N/A"
            print(f"    • {name}: {cnt} commit-uri")

    # Top autori
    cursor.execute("""
        SELECT author_name, COUNT(*) as cnt
        FROM git_commits
        GROUP BY author_name
        ORDER BY cnt DESC
        LIMIT 5
    """)

    authors = cursor.fetchall()
    if authors:
        print(f"\n  Top autori:")
        for author, cnt in authors:
            print(f"    • {author}: {cnt}")

    print(f"\n{'='*60}\n")
    conn.close()


def sync_recent_commits(count: int = 10):
    """Sincronizează ultimele N commit-uri din repo-ul curent."""
    hashes = run_git_command(["log", f"-{count}", "--format=%H"]).split("\n")

    saved = 0
    for h in hashes:
        if h and save_commit(h, silent=True):
            saved += 1

    print(f"✅ Sincronizate {saved} commit-uri din ultimele {count}")


def main():
    parser = argparse.ArgumentParser(description='Git Memory Hook - Salvează commit-uri în memorie')
    subparsers = parser.add_subparsers(dest='command', help='Comenzi disponibile')

    # Save
    save_parser = subparsers.add_parser('save', help='Salvează un commit')
    save_parser.add_argument('commit', nargs='?', default='HEAD', help='Hash commit (default: HEAD)')

    # List
    list_parser = subparsers.add_parser('list', help='Listează commit-uri salvate')
    list_parser.add_argument('--limit', '-n', type=int, default=20, help='Număr maxim')
    list_parser.add_argument('--project', '-p', help='Filtrează după proiect')

    # Search
    search_parser = subparsers.add_parser('search', help='Caută în commit-uri')
    search_parser.add_argument('query', help='Text de căutat')
    search_parser.add_argument('--limit', '-n', type=int, default=10, help='Număr maxim')

    # Stats
    subparsers.add_parser('stats', help='Statistici commit-uri')

    # Sync
    sync_parser = subparsers.add_parser('sync', help='Sincronizează ultimele commit-uri')
    sync_parser.add_argument('--count', '-n', type=int, default=10, help='Număr commit-uri')

    args = parser.parse_args()

    if not DB_PATH.exists():
        print("❌ Baza de date nu există!")
        sys.exit(1)

    # Dacă e apelat fără argumente (ca hook), salvează HEAD
    if args.command is None:
        save_commit("HEAD")
    elif args.command == 'save':
        save_commit(args.commit)
    elif args.command == 'list':
        list_commits(args.limit, args.project)
    elif args.command == 'search':
        search_commits(args.query, args.limit)
    elif args.command == 'stats':
        show_stats()
    elif args.command == 'sync':
        sync_recent_commits(args.count)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
