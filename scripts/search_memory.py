#!/usr/bin/env python3
"""
Căutare în memoria permanentă Claude Code.

Permite căutare în:
- Mesaje (conversații)
- Comenzi Bash
- Erori și soluții
- Patterns/module
- Tool calls

Suportă memorie per proiect sau globală:
    --global   : Caută doar în memoria globală
    --project  : Caută doar în memoria proiectului curent
    --both     : Caută în ambele (default)

Usage:
    python3 search_memory.py "text de căutat"
    python3 search_memory.py --errors "ModuleNotFoundError"
    python3 search_memory.py --commands "docker"
    python3 search_memory.py --patterns "authentication"
    python3 search_memory.py --files "config.py"
    python3 search_memory.py --global "docker"
    python3 search_memory.py --project "config"
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"
PROJECT_MEMORY_DIR = ".claude-memory"
PROJECT_DB_NAME = "project.db"


def get_project_db_path() -> Optional[Path]:
    """Găsește DB-ul specific proiectului dacă există."""
    cwd = Path.cwd()
    for _ in range(5):
        project_db = cwd / PROJECT_MEMORY_DIR / PROJECT_DB_NAME
        if project_db.exists():
            return project_db
        if cwd.parent == cwd:
            break
        cwd = cwd.parent
    return None


def get_connection(db_path: Path = None):
    """Obține conexiune la baza de date specificată sau globală."""
    if db_path is None:
        db_path = GLOBAL_DB
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_dbs_to_search(scope: str) -> List[tuple]:
    """Returnează lista de DB-uri de căutat în funcție de scope."""
    dbs = []
    project_db = get_project_db_path()

    if scope == "project":
        if project_db:
            dbs.append((project_db, "PROJECT"))
        else:
            print("⚠️  Nu există memorie de proiect în directorul curent.")
            print("   Folosește: python3 ~/.claude/memory/scripts/init_project_memory.py")
    elif scope == "global":
        dbs.append((GLOBAL_DB, "GLOBAL"))
    else:  # both
        if project_db:
            dbs.append((project_db, "PROJECT"))
        dbs.append((GLOBAL_DB, "GLOBAL"))

    return dbs


def search_messages(query: str, limit: int = 20, db_path: Path = None) -> List[Dict]:
    """Caută în mesaje/conversații folosind FTS5 pentru performanță."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Folosim FTS5 pentru căutare rapidă
    cursor.execute("""
        SELECT m.*, s.project_path as session_project
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        LEFT JOIN sessions s ON m.session_id = s.session_id
        WHERE messages_fts MATCH ?
        ORDER BY m.timestamp DESC
        LIMIT ?
    """, (query, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_bash_commands(query: str, limit: int = 20, db_path: Path = None) -> List[Dict]:
    """Caută în comenzile Bash folosind FTS5 pentru performanță."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Folosim FTS5 pentru căutare rapidă
    cursor.execute("""
        SELECT b.*
        FROM bash_history_fts
        JOIN bash_history b ON bash_history_fts.rowid = b.rowid
        WHERE bash_history_fts MATCH ?
        ORDER BY b.timestamp DESC
        LIMIT ?
    """, (query, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_errors(query: str, limit: int = 20, db_path: Path = None) -> List[Dict]:
    """Caută în erori și soluții."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM errors_solutions
        WHERE error_message LIKE ?
           OR error_type LIKE ?
           OR solution LIKE ?
           OR stack_trace LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_patterns(query: str, limit: int = 20, db_path: Path = None) -> List[Dict]:
    """Caută în patterns/module."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM patterns
        WHERE pattern_name LIKE ?
           OR description LIKE ?
           OR pattern_type LIKE ?
           OR code LIKE ?
        ORDER BY usage_count DESC, created_at DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_file_history(file_path: str, limit: int = 20, db_path: Path = None) -> List[Dict]:
    """Caută în istoricul versiunilor pentru un fișier."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, file_path, content_hash, size_bytes, timestamp,
               session_id, change_type, project_path,
               LENGTH(content) as content_length
        FROM file_versions
        WHERE file_path LIKE ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (f"%{file_path}%", limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_all(query: str, limit: int = 10, db_path: Path = None) -> Dict[str, List[Dict]]:
    """Căutare globală în toate tabelele."""
    return {
        "messages": search_messages(query, limit, db_path),
        "commands": search_bash_commands(query, limit, db_path),
        "errors": search_errors(query, limit, db_path),
        "patterns": search_patterns(query, limit, db_path),
    }


def print_results(results: List[Dict], category: str):
    """Afișează rezultatele formatate."""
    if not results:
        print(f"\n  Nu s-au găsit rezultate în {category}.")
        return

    print(f"\n{'=' * 60}")
    print(f"  {category.upper()} ({len(results)} rezultate)")
    print(f"{'=' * 60}")

    for i, row in enumerate(results, 1):
        print(f"\n--- Rezultat {i} ---")
        for key, value in row.items():
            if value is not None:
                # Limitează valorile lungi
                str_val = str(value)
                if len(str_val) > 200:
                    str_val = str_val[:200] + "..."
                print(f"  {key}: {str_val}")


def get_stats(db_path: Path = None, label: str = ""):
    """Afișează statistici despre memoria stocată."""
    if db_path is None:
        db_path = GLOBAL_DB

    if not db_path.exists():
        print(f"\n⚠️  Baza de date nu există: {db_path}")
        return

    conn = get_connection(db_path)
    cursor = conn.cursor()

    header = f"STATISTICI MEMORIE CLAUDE CODE {label}".strip()
    print("\n" + "=" * 60)
    print(f"  {header}")
    print(f"  DB: {db_path}")
    print("=" * 60)

    # Sesiuni
    cursor.execute("SELECT COUNT(*) as total FROM sessions")
    print(f"\n  Sesiuni totale: {cursor.fetchone()['total']}")

    # Mesaje
    cursor.execute("SELECT COUNT(*) as total FROM messages")
    print(f"  Mesaje salvate: {cursor.fetchone()['total']}")

    # Tool calls
    cursor.execute("SELECT COUNT(*) as total FROM tool_calls")
    print(f"  Tool calls: {cursor.fetchone()['total']}")

    # Versiuni fișiere
    cursor.execute("SELECT COUNT(*) as total FROM file_versions")
    print(f"  Versiuni fișiere: {cursor.fetchone()['total']}")

    # Erori
    cursor.execute("SELECT COUNT(*) as total FROM errors_solutions")
    print(f"  Erori înregistrate: {cursor.fetchone()['total']}")

    cursor.execute("SELECT COUNT(*) as total FROM errors_solutions WHERE solution_worked = 1")
    print(f"  Erori rezolvate: {cursor.fetchone()['total']}")

    # Patterns
    cursor.execute("SELECT COUNT(*) as total FROM patterns")
    print(f"  Patterns/module: {cursor.fetchone()['total']}")

    # Comenzi Bash
    cursor.execute("SELECT COUNT(*) as total FROM bash_history")
    print(f"  Comenzi Bash: {cursor.fetchone()['total']}")

    # Dimensiune bază de date
    db_size = db_path.stat().st_size
    if db_size < 1024:
        size_str = f"{db_size} B"
    elif db_size < 1024 * 1024:
        size_str = f"{db_size / 1024:.1f} KB"
    else:
        size_str = f"{db_size / (1024 * 1024):.1f} MB"
    print(f"\n  Dimensiune bază de date: {size_str}")

    # Ultima sesiune
    cursor.execute("""
        SELECT session_id, project_path, started_at
        FROM sessions
        ORDER BY started_at DESC
        LIMIT 1
    """)
    last = cursor.fetchone()
    if last:
        print(f"\n  Ultima sesiune: {last['started_at']}")
        print(f"  Proiect: {last['project_path']}")

    conn.close()
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Căutare în memoria permanentă Claude Code"
    )
    parser.add_argument("query", nargs="?", help="Text de căutat")
    parser.add_argument("--messages", "-m", action="store_true",
                        help="Caută doar în mesaje")
    parser.add_argument("--commands", "-c", action="store_true",
                        help="Caută doar în comenzi Bash")
    parser.add_argument("--errors", "-e", action="store_true",
                        help="Caută doar în erori")
    parser.add_argument("--patterns", "-p", action="store_true",
                        help="Caută doar în patterns")
    parser.add_argument("--files", "-f", action="store_true",
                        help="Caută în istoricul fișierelor")
    parser.add_argument("--stats", "-s", action="store_true",
                        help="Afișează statistici")
    parser.add_argument("--limit", "-l", type=int, default=20,
                        help="Număr maxim de rezultate (default: 20)")

    # Search mode options
    search_mode = parser.add_mutually_exclusive_group()
    search_mode.add_argument("--vector", "-v", action="store_true",
                             help="Căutare semantică (necesită embeddings)")
    search_mode.add_argument("--hybrid", "-H", action="store_true",
                             help="Căutare hibridă keyword + vector (recomandat)")

    # Scope options
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument("--global", "-g", dest="scope_global", action="store_true",
                             help="Caută doar în memoria globală")
    scope_group.add_argument("--project", "-P", dest="scope_project", action="store_true",
                             help="Caută doar în memoria proiectului curent")
    scope_group.add_argument("--both", "-b", action="store_true",
                             help="Caută în ambele (default)")

    args = parser.parse_args()

    # Determină scope-ul
    if args.scope_global:
        scope = "global"
    elif args.scope_project:
        scope = "project"
    else:
        scope = "both"

    if args.stats:
        dbs = get_dbs_to_search(scope)
        for db_path, label in dbs:
            get_stats(db_path, f"[{label}]")
        return

    if not args.query:
        parser.print_help()
        print("\nExemple:")
        print("  python3 search_memory.py 'docker compose'")
        print("  python3 search_memory.py --errors 'ImportError'")
        print("  python3 search_memory.py --commands 'git'")
        print("  python3 search_memory.py --global 'docker'        # doar global")
        print("  python3 search_memory.py --project 'config'       # doar proiect")
        print("  python3 search_memory.py --vector 'authentication' # semantic search")
        print("  python3 search_memory.py --hybrid 'docker'        # keyword + vector")
        print("  python3 search_memory.py --stats")
        print("  python3 search_memory.py --stats --project")
        return

    query = args.query
    dbs = get_dbs_to_search(scope)

    if not dbs:
        print("Nu s-au găsit baze de date pentru căutare.")
        return

    # Handle vector and hybrid search modes
    if args.vector:
        try:
            from vector_search import semantic_search, get_full_content
            print(f"\n🔍 Căutare semantică: '{query}'")
            results = semantic_search(query, limit=args.limit)
            print(f"\n{'='*60}")
            print(f"  CĂUTARE SEMANTICĂ - {len(results)} rezultate")
            print(f"{'='*60}")
            for i, r in enumerate(results, 1):
                print(f"\n--- Rezultat {i} (scor: {r['score']:.3f}) ---")
                print(f"  Sursă: {r['source_table']} #{r['source_id']}")
                content = r.get('document', '')[:300]
                print(f"  Conținut: {content}...")
            return
        except ImportError:
            print("❌ vector_search.py nu este disponibil")
            return

    if args.hybrid:
        try:
            from hybrid_search import hybrid_search
            print(f"\n🔍 Căutare hibridă: '{query}'")
            results = hybrid_search(query, limit=args.limit)
            print(f"\n{'='*60}")
            print(f"  CĂUTARE HIBRIDĂ - {len(results)} rezultate")
            print(f"{'='*60}")
            for i, r in enumerate(results, 1):
                scores = r.get('scores', {})
                print(f"\n--- Rezultat {i} (scor: {scores.get('final', 0):.3f}) ---")
                print(f"  Sursă: {r['source_table']} #{r['id']}")
                print(f"  Scoruri: K={scores.get('keyword', 0):.2f} V={scores.get('vector', 0):.2f}")
                content = r.get('content', '')[:300]
                print(f"  Conținut: {content}...")
            return
        except ImportError:
            print("❌ hybrid_search.py nu este disponibil")
            return

    for db_path, label in dbs:
        print(f"\n🔍 Căutare în [{label}]: {db_path}")

        if args.messages:
            results = search_messages(query, args.limit, db_path)
            print_results(results, f"Mesaje [{label}]")
        elif args.commands:
            results = search_bash_commands(query, args.limit, db_path)
            print_results(results, f"Comenzi Bash [{label}]")
        elif args.errors:
            results = search_errors(query, args.limit, db_path)
            print_results(results, f"Erori și Soluții [{label}]")
        elif args.patterns:
            results = search_patterns(query, args.limit, db_path)
            print_results(results, f"Patterns/Module [{label}]")
        elif args.files:
            results = search_file_history(query, args.limit, db_path)
            print_results(results, f"Versiuni Fișiere [{label}]")
        else:
            # Căutare globală
            all_results = search_all(query, args.limit, db_path)
            for category, results in all_results.items():
                print_results(results, f"{category} [{label}]")


if __name__ == "__main__":
    main()
