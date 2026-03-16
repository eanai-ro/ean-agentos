#!/usr/bin/env python3
"""
ERROR DATABASE - Gestionare erori și soluții.

Comenzi:
    error_db search "mesaj eroare"     # Caută soluții pentru o eroare
    error_db add                        # Adaugă eroare nouă (interactiv)
    error_db add --error "..." --solution "..." --language python
    error_db list                       # Listează ultimele erori
    error_db stats                      # Statistici erori

Utilizare automată:
    Când întâmpini o eroare, rulează:
    python3 ~/.claude/memory/scripts/error_db.py search "textul erorii"
"""

import sqlite3
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from v2_common import resolve_db_path
    DB_PATH = resolve_db_path()
except ImportError:
    DB_PATH = Path.home() / ".claude" / "memory" / "global.db"


def get_db():
    return sqlite3.connect(DB_PATH)


def search_error(query, language=None, limit=10):
    """Caută erori similare și soluțiile lor."""
    conn = get_db()
    cursor = conn.cursor()

    # Căutare în error_message, error_type, stack_trace, tags
    sql = """
        SELECT id, error_type, error_message, solution, solution_code,
               solution_worked, language, framework, file_path, resolved_at
        FROM errors_solutions
        WHERE (error_message LIKE ? OR error_type LIKE ? OR stack_trace LIKE ? OR tags LIKE ?)
    """
    params = [f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"]

    if language:
        sql += " AND language = ?"
        params.append(language)

    sql += " ORDER BY solution_worked DESC, resolved_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    results = cursor.fetchall()

    if not results:
        print(f"\n❌ Nu am găsit erori similare cu: '{query}'")
        print("   Dacă rezolvi această eroare, salvează soluția cu:")
        print(f'   error_db add --error "{query}" --solution "descriere soluție"')
        conn.close()
        return []

    print(f"\n{'='*60}")
    print(f"  🔍 SOLUȚII GĂSITE PENTRU: {query[:50]}...")
    print('='*60)

    for row in results:
        id, err_type, err_msg, solution, solution_code, worked, lang, framework, file_path, resolved = row

        status = "✅ FUNCȚIONEAZĂ" if worked else "⚠️ Parțial"

        print(f"\n--- Eroare #{id} [{lang or 'N/A'}] {status} ---")
        print(f"  Tip: {err_type}")
        print(f"  Mesaj: {err_msg[:200]}...")

        if solution:
            print(f"\n  💡 SOLUȚIE:")
            print(f"  {solution}")

        if solution_code:
            print(f"\n  📝 COD:")
            print(f"  {solution_code[:300]}")

        if framework:
            print(f"  Framework: {framework}")

    print(f"\n{'='*60}\n")
    conn.close()
    return results


def add_error(error_type=None, error_message=None, solution=None, solution_code=None,
              language=None, framework=None, file_path=None, line_number=None,
              stack_trace=None, tags=None, worked=True):
    """Adaugă o eroare și soluția ei în baza de date."""
    conn = get_db()
    cursor = conn.cursor()

    # Obține session_id curent dacă există
    session_id = None
    session_file = Path.home() / ".claude/memory/.current_session"
    if session_file.exists():
        session_id = session_file.read_text().strip()

    # Obține project_path
    project_path = str(Path.cwd())

    cursor.execute("""
        INSERT INTO errors_solutions
        (error_type, error_message, stack_trace, file_path, line_number,
         language, framework, solution, solution_code, solution_worked,
         resolved_at, session_id, project_path, tags, resolved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        error_type or "general_error",
        error_message,
        stack_trace,
        file_path,
        line_number,
        language,
        framework,
        solution,
        solution_code,
        worked,
        datetime.now().isoformat() if solution else None,
        session_id,
        project_path,
        json.dumps(tags) if tags else None,
        1 if solution else 0  # resolved = 1 dacă are soluție
    ))

    conn.commit()
    error_id = cursor.lastrowid
    conn.close()

    print(f"\n✅ Eroare salvată cu ID: {error_id}")
    print(f"   Tip: {error_type}")
    print(f"   Limbaj: {language}")
    if solution:
        print(f"   Soluție: {solution[:100]}...")
    print()

    return error_id


def list_errors(limit=20, language=None, unsolved=False):
    """Listează ultimele erori."""
    conn = get_db()
    cursor = conn.cursor()

    sql = "SELECT id, error_type, substr(error_message, 1, 80), language, solution_worked, created_at FROM errors_solutions"
    params = []

    conditions = []
    if language:
        conditions.append("language = ?")
        params.append(language)
    if unsolved:
        conditions.append("(solution IS NULL OR solution_worked = 0)")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    results = cursor.fetchall()

    print(f"\n{'='*60}")
    print("  📋 ULTIMELE ERORI ÎNREGISTRATE")
    print('='*60)

    if not results:
        print("\n  Nu există erori înregistrate.")
    else:
        for row in results:
            id, err_type, err_msg, lang, worked, created = row
            status = "✅" if worked else "❌"
            print(f"\n  {status} #{id} [{lang or 'N/A'}] {err_type}")
            print(f"     {err_msg}...")
            print(f"     {created[:16]}")

    print(f"\n{'='*60}\n")
    conn.close()


def resolve_error(error_id, solution, solution_code=None):
    """Marchează o eroare ca rezolvată cu soluția dată."""
    conn = get_db()
    cursor = conn.cursor()

    # Verifică dacă eroarea există
    cursor.execute("SELECT id, error_message FROM errors_solutions WHERE id = ?", (error_id,))
    row = cursor.fetchone()
    if not row:
        print(f"❌ Eroarea cu ID {error_id} nu există!")
        conn.close()
        return False

    # Actualizează eroarea
    cursor.execute("""
        UPDATE errors_solutions
        SET solution = ?,
            solution_code = ?,
            solution_worked = 1,
            resolved = 1,
            resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (solution, solution_code, error_id))

    conn.commit()
    conn.close()

    print(f"\n✅ Eroare #{error_id} marcată ca REZOLVATĂ!")
    print(f"   Eroare: {row[1][:80]}...")
    print(f"   Soluție: {solution[:100]}...")
    print()
    return True


def show_stats():
    """Afișează statistici despre erori."""
    conn = get_db()
    cursor = conn.cursor()

    print(f"\n{'='*60}")
    print("  📊 STATISTICI ERORI")
    print('='*60)

    cursor.execute("SELECT COUNT(*) FROM errors_solutions")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE solution_worked = 1")
    solved = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE solution IS NULL OR solution_worked = 0")
    unsolved = cursor.fetchone()[0]

    print(f"\n  Total erori: {total}")
    print(f"  Rezolvate: {solved}")
    print(f"  Nerezolvate: {unsolved}")

    # Per limbaj
    cursor.execute("""
        SELECT language, COUNT(*) as cnt
        FROM errors_solutions
        WHERE language IS NOT NULL
        GROUP BY language
        ORDER BY cnt DESC
        LIMIT 10
    """)

    langs = cursor.fetchall()
    if langs:
        print(f"\n  Per limbaj:")
        for lang, cnt in langs:
            print(f"    • {lang}: {cnt}")

    # Cele mai frecvente tipuri de erori
    cursor.execute("""
        SELECT error_type, COUNT(*) as cnt
        FROM errors_solutions
        GROUP BY error_type
        ORDER BY cnt DESC
        LIMIT 5
    """)

    types = cursor.fetchall()
    if types:
        print(f"\n  Tipuri frecvente:")
        for err_type, cnt in types:
            print(f"    • {err_type}: {cnt}")

    print(f"\n{'='*60}\n")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Gestionare erori și soluții')
    subparsers = parser.add_subparsers(dest='command', help='Comenzi disponibile')

    # Search
    search_parser = subparsers.add_parser('search', help='Caută soluții pentru o eroare')
    search_parser.add_argument('query', help='Textul erorii de căutat')
    search_parser.add_argument('--language', '-l', help='Filtrează după limbaj')
    search_parser.add_argument('--limit', '-n', type=int, default=10, help='Număr maxim rezultate')

    # Add
    add_parser = subparsers.add_parser('add', help='Adaugă eroare și soluție')
    add_parser.add_argument('--error', '-e', required=True, help='Mesajul erorii')
    add_parser.add_argument('--type', '-t', default='general_error', help='Tipul erorii')
    add_parser.add_argument('--solution', '-s', help='Soluția')
    add_parser.add_argument('--code', '-c', help='Codul soluției')
    add_parser.add_argument('--language', '-l', help='Limbajul (python, javascript, etc.)')
    add_parser.add_argument('--framework', '-f', help='Framework-ul')
    add_parser.add_argument('--file', help='Fișierul unde a apărut eroarea')
    add_parser.add_argument('--tags', nargs='+', help='Tag-uri pentru căutare')
    add_parser.add_argument('--worked', action='store_true', default=True, help='Soluția a funcționat')

    # List
    list_parser = subparsers.add_parser('list', help='Listează erorile')
    list_parser.add_argument('--limit', '-n', type=int, default=20, help='Număr maxim')
    list_parser.add_argument('--language', '-l', help='Filtrează după limbaj')
    list_parser.add_argument('--unsolved', '-u', action='store_true', help='Doar nerezolvate')

    # Stats
    subparsers.add_parser('stats', help='Statistici erori')

    # Resolve - marchează o eroare ca rezolvată
    resolve_parser = subparsers.add_parser('resolve', help='Marchează o eroare ca rezolvată')
    resolve_parser.add_argument('id', type=int, help='ID-ul erorii de rezolvat')
    resolve_parser.add_argument('--solution', '-s', required=True, help='Soluția care a funcționat')
    resolve_parser.add_argument('--code', '-c', help='Codul soluției (opțional)')

    args = parser.parse_args()

    if not DB_PATH.exists():
        print("❌ Baza de date nu există!")
        sys.exit(1)

    if args.command == 'search':
        search_error(args.query, args.language, args.limit)
    elif args.command == 'add':
        add_error(
            error_type=args.type,
            error_message=args.error,
            solution=args.solution,
            solution_code=args.code,
            language=args.language,
            framework=args.framework,
            file_path=args.file,
            tags=args.tags,
            worked=args.worked
        )
    elif args.command == 'list':
        list_errors(args.limit, args.language, args.unsolved)
    elif args.command == 'stats':
        show_stats()
    elif args.command == 'resolve':
        resolve_error(args.id, args.solution, args.code)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
