#!/usr/bin/env python3
"""
Restaurare versiuni de fișiere din EAN AgentOS.

Permite:
- Listarea versiunilor disponibile pentru un fișier
- Vizualizarea diferențelor între versiuni
- Restaurarea unei versiuni anterioare
- Compararea cu versiunea curentă

Usage:
    python3 restore_version.py list /path/to/file.py
    python3 restore_version.py show /path/to/file.py --version 3
    python3 restore_version.py diff /path/to/file.py --version 3
    python3 restore_version.py restore /path/to/file.py --version 3
    python3 restore_version.py restore /path/to/file.py --version 3 --dry-run
"""

import sys
import sqlite3
import argparse
import difflib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import shutil

try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"


def get_connection():
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def list_versions(file_path: str, limit: int = 50) -> List[Dict]:
    """Listează toate versiunile disponibile pentru un fișier."""
    conn = get_connection()
    cursor = conn.cursor()

    # Caută după potrivire exactă sau parțială
    cursor.execute("""
        SELECT id, file_path, content_hash, size_bytes, saved_at,
               session_id, change_type, project_path
        FROM file_versions
        WHERE file_path = ? OR file_path LIKE ?
        ORDER BY saved_at DESC
        LIMIT ?
    """, (file_path, f"%{file_path}%", limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_version(version_id: int) -> Optional[Dict]:
    """Obține o versiune specifică după ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM file_versions
        WHERE id = ?
    """, (version_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_version_by_index(file_path: str, index: int) -> Optional[Dict]:
    """Obține o versiune după index (1 = cea mai recentă)."""
    versions = list_versions(file_path)
    if 0 < index <= len(versions):
        version_id = versions[index - 1]['id']
        return get_version(version_id)
    return None


def show_version(file_path: str, version_index: int):
    """Afișează conținutul unei versiuni."""
    version = get_version_by_index(file_path, version_index)
    if not version:
        print(f"Eroare: Versiunea {version_index} nu există pentru {file_path}")
        return

    print(f"\n{'=' * 60}")
    print(f"  VERSIUNE {version_index}")
    print(f"{'=' * 60}")
    print(f"  Fișier: {version['file_path']}")
    print(f"  Salvat: {version['saved_at']}")
    print(f"  Tip: {version['change_type']}")
    print(f"  Dimensiune: {version['size_bytes']} bytes")
    print(f"  Hash: {version['content_hash'][:16]}...")
    print(f"{'=' * 60}\n")
    print(version['content'])


def diff_version(file_path: str, version_index: int):
    """Afișează diferențele între o versiune și fișierul curent."""
    version = get_version_by_index(file_path, version_index)
    if not version:
        print(f"Eroare: Versiunea {version_index} nu există pentru {file_path}")
        return

    # Caută fișierul curent
    current_path = Path(version['file_path'])
    if not current_path.exists():
        print(f"Avertisment: Fișierul curent nu există: {current_path}")
        print("Se afișează conținutul versiunii salvate:")
        print(version['content'])
        return

    with open(current_path, 'r', encoding='utf-8', errors='ignore') as f:
        current_content = f.read()

    old_lines = version['content'].splitlines(keepends=True)
    new_lines = current_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{file_path} (versiune {version_index} din {version['saved_at']})",
        tofile=f"{file_path} (curent)",
        lineterm=''
    )

    diff_text = ''.join(diff)
    if diff_text:
        print(diff_text)
    else:
        print("Fișierele sunt identice.")


def restore_version(file_path: str, version_index: int, dry_run: bool = False, backup: bool = True):
    """Restaurează o versiune anterioară a fișierului."""
    version = get_version_by_index(file_path, version_index)
    if not version:
        print(f"Eroare: Versiunea {version_index} nu există pentru {file_path}")
        return False

    target_path = Path(version['file_path'])

    print(f"\n{'=' * 60}")
    print(f"  RESTAURARE VERSIUNE")
    print(f"{'=' * 60}")
    print(f"  Fișier: {target_path}")
    print(f"  Versiune: {version_index}")
    print(f"  Salvat la: {version['saved_at']}")
    print(f"  Tip modificare: {version['change_type']}")

    if dry_run:
        print(f"\n  [DRY RUN] Nu se va face nicio modificare.")
        print(f"  Conținut care ar fi restaurat ({version['size_bytes']} bytes):")
        print(f"{'=' * 60}\n")
        # Afișează primele 50 de linii
        lines = version['content'].splitlines()
        for i, line in enumerate(lines[:50]):
            print(f"  {i+1:4d} | {line}")
        if len(lines) > 50:
            print(f"\n  ... și încă {len(lines) - 50} linii")
        return True

    # Backup fișierul curent dacă există
    if backup and target_path.exists():
        backup_path = target_path.with_suffix(target_path.suffix + '.backup')
        shutil.copy2(target_path, backup_path)
        print(f"\n  Backup creat: {backup_path}")

    # Creează directorul dacă nu există
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Scrie conținutul
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(version['content'])

    print(f"\n  ✓ Fișier restaurat cu succes!")
    print(f"  Dimensiune: {version['size_bytes']} bytes")

    return True


def compare_versions(file_path: str, version1: int, version2: int):
    """Compară două versiuni între ele."""
    v1 = get_version_by_index(file_path, version1)
    v2 = get_version_by_index(file_path, version2)

    if not v1:
        print(f"Eroare: Versiunea {version1} nu există")
        return
    if not v2:
        print(f"Eroare: Versiunea {version2} nu există")
        return

    old_lines = v1['content'].splitlines(keepends=True)
    new_lines = v2['content'].splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{file_path} (v{version1} din {v1['saved_at']})",
        tofile=f"{file_path} (v{version2} din {v2['saved_at']})",
        lineterm=''
    )

    diff_text = ''.join(diff)
    if diff_text:
        print(diff_text)
    else:
        print("Versiunile sunt identice.")


def print_versions_list(versions: List[Dict], file_path: str):
    """Afișează lista de versiuni formatată."""
    if not versions:
        print(f"\nNu există versiuni salvate pentru: {file_path}")
        return

    print(f"\n{'=' * 80}")
    print(f"  VERSIUNI DISPONIBILE PENTRU: {file_path}")
    print(f"{'=' * 80}")
    print(f"  {'#':>3} | {'Data salvare':<20} | {'Tip':<15} | {'Dimensiune':>10} | Hash")
    print(f"  {'-' * 76}")

    for i, v in enumerate(versions, 1):
        saved = v['saved_at'][:19] if v['saved_at'] else 'N/A'
        size = f"{v['size_bytes']:,}" if v['size_bytes'] else '0'
        hash_short = v['content_hash'][:12] if v['content_hash'] else 'N/A'
        change = v['change_type'] or 'unknown'

        print(f"  {i:>3} | {saved:<20} | {change:<15} | {size:>10} | {hash_short}")

    print(f"\n  Total: {len(versions)} versiuni")
    print(f"\n  Comenzi utile:")
    print(f"    restore_version.py show '{file_path}' --version 1")
    print(f"    restore_version.py diff '{file_path}' --version 1")
    print(f"    restore_version.py restore '{file_path}' --version 1 --dry-run")


def main():
    parser = argparse.ArgumentParser(
        description="Restaurare versiuni de fișiere din memoria Claude Code"
    )

    subparsers = parser.add_subparsers(dest='command', help='Comandă')

    # list
    list_parser = subparsers.add_parser('list', help='Listează versiunile disponibile')
    list_parser.add_argument('file_path', help='Calea fișierului')
    list_parser.add_argument('--limit', '-l', type=int, default=50, help='Număr maxim de rezultate')

    # show
    show_parser = subparsers.add_parser('show', help='Afișează conținutul unei versiuni')
    show_parser.add_argument('file_path', help='Calea fișierului')
    show_parser.add_argument('--version', '-v', type=int, required=True, help='Indexul versiunii (1 = cea mai recentă)')

    # diff
    diff_parser = subparsers.add_parser('diff', help='Afișează diferențele față de fișierul curent')
    diff_parser.add_argument('file_path', help='Calea fișierului')
    diff_parser.add_argument('--version', '-v', type=int, required=True, help='Indexul versiunii de comparat')

    # restore
    restore_parser = subparsers.add_parser('restore', help='Restaurează o versiune')
    restore_parser.add_argument('file_path', help='Calea fișierului')
    restore_parser.add_argument('--version', '-v', type=int, required=True, help='Indexul versiunii de restaurat')
    restore_parser.add_argument('--dry-run', '-n', action='store_true', help='Nu modifica nimic, doar afișează')
    restore_parser.add_argument('--no-backup', action='store_true', help='Nu face backup la fișierul curent')

    # compare
    compare_parser = subparsers.add_parser('compare', help='Compară două versiuni')
    compare_parser.add_argument('file_path', help='Calea fișierului')
    compare_parser.add_argument('--v1', type=int, required=True, help='Prima versiune')
    compare_parser.add_argument('--v2', type=int, required=True, help='A doua versiune')

    args = parser.parse_args()

    if not GLOBAL_DB.exists():
        print("Eroare: Baza de date nu există. Rulați mai întâi init_db.py")
        sys.exit(1)

    if not args.command:
        parser.print_help()
        print("\nExemple:")
        print("  python3 restore_version.py list /path/to/file.py")
        print("  python3 restore_version.py show /path/to/file.py --version 1")
        print("  python3 restore_version.py diff /path/to/file.py --version 2")
        print("  python3 restore_version.py restore /path/to/file.py --version 3 --dry-run")
        print("  python3 restore_version.py compare /path/to/file.py --v1 1 --v2 3")
        return

    if args.command == 'list':
        versions = list_versions(args.file_path, args.limit)
        print_versions_list(versions, args.file_path)

    elif args.command == 'show':
        show_version(args.file_path, args.version)

    elif args.command == 'diff':
        diff_version(args.file_path, args.version)

    elif args.command == 'restore':
        restore_version(args.file_path, args.version, args.dry_run, not args.no_backup)

    elif args.command == 'compare':
        compare_versions(args.file_path, args.v1, args.v2)


if __name__ == "__main__":
    main()
