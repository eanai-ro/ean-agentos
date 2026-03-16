#!/usr/bin/env python3
"""
Backup Manager V1 — Faza 17Y
Backup automat, verificare integritate, restore sigur, retenție.

Utilizare:
    python3 backup_manager.py create [--json]
    python3 backup_manager.py list [--json]
    python3 backup_manager.py verify [<file>] [--json]
    python3 backup_manager.py restore <file> [--force]
    python3 backup_manager.py cleanup [--dry-run] [--json]
    python3 backup_manager.py status [--json]

Integrare:
    from backup_manager import create_backup
    result = create_backup(db_path, reason="session_end")
"""

import sys
import os
import json
import shutil
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

# === CONFIGURARE ===

# DB path: env var > proiect root > fallback
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("MEMORY_DB_PATH", str(_PROJECT_ROOT / "global.db")))
BACKUP_DIR = DB_PATH.parent / "backups"
MANIFEST_PATH = BACKUP_DIR / "manifest.json"

# Retenție
MAX_BACKUPS = 10              # Păstrează ultimele N
DAILY_RETENTION_DAYS = 7      # Plus 1/zi pentru ultimele X zile
BACKUP_PREFIX = "global_"
BACKUP_SUFFIX = ".db"


# === MANIFEST ===

def _load_manifest() -> List[Dict]:
    """Încarcă manifest-ul. Returnează listă goală dacă nu există."""
    if MANIFEST_PATH.exists():
        try:
            data = json.loads(MANIFEST_PATH.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_manifest(entries: List[Dict]) -> None:
    """Salvează manifest-ul."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def _add_to_manifest(entry: Dict) -> None:
    """Adaugă o intrare în manifest."""
    entries = _load_manifest()
    entries.append(entry)
    _save_manifest(entries)


def _remove_from_manifest(filename: str) -> None:
    """Șterge o intrare din manifest."""
    entries = _load_manifest()
    entries = [e for e in entries if e.get("filename") != filename]
    _save_manifest(entries)


# === INTEGRITATE ===

def verify_db(db_path: Path) -> Dict[str, Any]:
    """Verifică integritatea unui fișier SQLite.

    Returns:
        {"valid": bool, "size": int, "tables": int, "integrity": str, "error": str|None}
    """
    result = {
        "valid": False,
        "size": 0,
        "tables": 0,
        "integrity": "unknown",
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "File does not exist"
        return result

    result["size"] = db_path.stat().st_size
    if result["size"] == 0:
        result["error"] = "File is empty"
        return result

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # PRAGMA integrity_check
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        result["integrity"] = integrity

        if integrity != "ok":
            result["error"] = f"Integrity check failed: {integrity}"
            conn.close()
            return result

        # Contorizează tabele
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        result["tables"] = cursor.fetchone()[0]

        conn.close()
        result["valid"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def _file_sha256(path: Path) -> str:
    """Calculează SHA-256 al unui fișier."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# === BACKUP CREATE ===

def create_backup(
    db_path: Optional[Path] = None,
    reason: str = "manual",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creează un backup al bazei de date.

    Args:
        db_path: Calea către DB (default: DB_PATH global)
        reason: Motivul backup-ului (manual, session_end, pre_restore, pre_migrate)
        session_id: ID-ul sesiunii curente (opțional)

    Returns:
        {"success": bool, "filename": str, "path": str, "size": int,
         "sha256": str, "verified": bool, "error": str|None}
    """
    db_path = db_path or DB_PATH
    result = {
        "success": False,
        "filename": "",
        "path": "",
        "size": 0,
        "sha256": "",
        "verified": False,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = f"Database not found: {db_path}"
        return result

    # Crează directorul de backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Generează numele fișierului
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{BACKUP_PREFIX}{timestamp}{BACKUP_SUFFIX}"
    backup_path = BACKUP_DIR / filename

    # Evită suprascrierea
    if backup_path.exists():
        filename = f"{BACKUP_PREFIX}{timestamp}_{os.getpid()}{BACKUP_SUFFIX}"
        backup_path = BACKUP_DIR / filename

    try:
        # Folosește SQLite backup API pentru consistență (WAL-safe)
        src_conn = sqlite3.connect(str(db_path))
        dst_conn = sqlite3.connect(str(backup_path))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        result["filename"] = filename
        result["path"] = str(backup_path)
        result["size"] = backup_path.stat().st_size
        result["sha256"] = _file_sha256(backup_path)

        # Verifică backup-ul creat
        verify = verify_db(backup_path)
        result["verified"] = verify["valid"]

        if not verify["valid"]:
            result["error"] = f"Backup verification failed: {verify['error']}"
            # Șterge backup-ul invalid
            backup_path.unlink(missing_ok=True)
            return result

        result["success"] = True

        # Adaugă în manifest
        _add_to_manifest({
            "filename": filename,
            "timestamp": datetime.now().isoformat(),
            "size": result["size"],
            "sha256": result["sha256"],
            "verified": True,
            "reason": reason,
            "session_id": session_id,
            "source_db": str(db_path),
            "tables": verify["tables"],
        })

    except Exception as e:
        result["error"] = str(e)
        # Cleanup pe eroare
        if backup_path.exists():
            backup_path.unlink(missing_ok=True)

    return result


# === BACKUP LIST ===

def list_backups() -> List[Dict]:
    """Listează toate backup-urile din manifest + fișiere orfane."""
    manifest = _load_manifest()
    manifest_files = {e["filename"] for e in manifest}

    # Adaugă fișiere orfane (prezente pe disc dar nu în manifest)
    if BACKUP_DIR.exists():
        for f in sorted(BACKUP_DIR.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}")):
            if f.name not in manifest_files:
                manifest.append({
                    "filename": f.name,
                    "timestamp": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "size": f.stat().st_size,
                    "sha256": "",
                    "verified": False,
                    "reason": "unknown",
                    "orphan": True,
                })

    # Sortează cronologic (cele mai noi primele)
    manifest.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return manifest


# === BACKUP VERIFY ===

def verify_backup(filename: str) -> Dict[str, Any]:
    """Verifică un backup specific."""
    backup_path = BACKUP_DIR / filename
    verify = verify_db(backup_path)

    # Verifică SHA-256 dacă e în manifest
    manifest = _load_manifest()
    for entry in manifest:
        if entry["filename"] == filename and entry.get("sha256"):
            current_sha = _file_sha256(backup_path) if backup_path.exists() else ""
            verify["sha256_match"] = current_sha == entry["sha256"]
            verify["expected_sha256"] = entry["sha256"]
            verify["actual_sha256"] = current_sha
            break

    return verify


# === RESTORE ===

def restore_backup(filename: str, force: bool = False) -> Dict[str, Any]:
    """Restaurează un backup.

    Flow:
    1. Verifică backup-ul selectat
    2. Creează backup al DB-ului curent (pre_restore)
    3. Restaurează backup-ul selectat
    4. Verifică DB-ul restaurat
    """
    result = {
        "success": False,
        "restored_from": filename,
        "pre_restore_backup": "",
        "verified_after": False,
        "error": None,
    }

    backup_path = BACKUP_DIR / filename

    # 1. Verifică backup-ul selectat
    verify = verify_db(backup_path)
    if not verify["valid"]:
        result["error"] = f"Backup invalid: {verify['error']}"
        return result

    if not force:
        result["error"] = "Restore requires --force flag for safety"
        result["needs_force"] = True
        result["backup_info"] = {
            "filename": filename,
            "size": verify["size"],
            "tables": verify["tables"],
            "integrity": verify["integrity"],
        }
        return result

    # 2. Backup al DB-ului curent
    pre_restore = create_backup(reason="pre_restore")
    if pre_restore["success"]:
        result["pre_restore_backup"] = pre_restore["filename"]
    else:
        result["error"] = f"Failed to backup current DB: {pre_restore['error']}"
        return result

    # 3. Restaurează
    try:
        # Folosește SQLite backup API
        src_conn = sqlite3.connect(str(backup_path))
        dst_conn = sqlite3.connect(str(DB_PATH))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
    except Exception as e:
        result["error"] = f"Restore failed: {e}"
        return result

    # 4. Verifică după restore
    post_verify = verify_db(DB_PATH)
    result["verified_after"] = post_verify["valid"]

    if not post_verify["valid"]:
        result["error"] = f"Post-restore verification failed: {post_verify['error']}"
        result["rollback_available"] = result["pre_restore_backup"]
        return result

    result["success"] = True
    return result


# === RETENȚIE / CLEANUP ===

def cleanup_backups(dry_run: bool = False) -> Dict[str, Any]:
    """Aplică politica de retenție.

    Politică:
    - Păstrează ultimele MAX_BACKUPS backup-uri
    - Plus 1/zi pentru ultimele DAILY_RETENTION_DAYS zile
    - Șterge restul
    """
    backups = list_backups()
    now = datetime.now()
    cutoff_daily = now - timedelta(days=DAILY_RETENTION_DAYS)

    to_keep = set()
    to_delete = []

    # 1. Păstrează ultimele MAX_BACKUPS
    for entry in backups[:MAX_BACKUPS]:
        to_keep.add(entry["filename"])

    # 2. Păstrează 1/zi pentru ultimele DAILY_RETENTION_DAYS zile
    daily_kept = {}  # date_str -> filename
    for entry in backups:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff_daily:
            date_str = ts.strftime("%Y-%m-%d")
            if date_str not in daily_kept:
                daily_kept[date_str] = entry["filename"]
                to_keep.add(entry["filename"])

    # 3. Păstrează pre_restore backup-urile (safety)
    for entry in backups:
        if entry.get("reason") == "pre_restore":
            to_keep.add(entry["filename"])

    # 4. Tot ce nu e în to_keep se șterge
    for entry in backups:
        if entry["filename"] not in to_keep:
            to_delete.append(entry)

    deleted = []
    errors = []

    if not dry_run:
        for entry in to_delete:
            path = BACKUP_DIR / entry["filename"]
            try:
                if path.exists():
                    path.unlink()
                _remove_from_manifest(entry["filename"])
                deleted.append(entry["filename"])
            except Exception as e:
                errors.append({"filename": entry["filename"], "error": str(e)})

    return {
        "total_backups": len(backups),
        "kept": len(to_keep),
        "deleted": deleted if not dry_run else [e["filename"] for e in to_delete],
        "delete_count": len(to_delete),
        "dry_run": dry_run,
        "errors": errors,
    }


# === STATUS ===

def backup_status() -> Dict[str, Any]:
    """Returnează statusul general backup."""
    backups = list_backups()

    total_size = 0
    latest = None
    verified_count = 0

    for entry in backups:
        total_size += entry.get("size", 0)
        if entry.get("verified"):
            verified_count += 1

    if backups:
        latest = backups[0]  # Deja sortate desc

    # Verifică DB-ul curent
    db_verify = verify_db(DB_PATH)

    return {
        "db_path": str(DB_PATH),
        "db_size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "db_valid": db_verify["valid"],
        "db_tables": db_verify.get("tables", 0),
        "backup_dir": str(BACKUP_DIR),
        "total_backups": len(backups),
        "verified_backups": verified_count,
        "total_backup_size": total_size,
        "latest_backup": latest,
        "retention_policy": {
            "max_backups": MAX_BACKUPS,
            "daily_retention_days": DAILY_RETENTION_DAYS,
        },
    }


# === CLI ===

def _fmt_size(size_bytes: int) -> str:
    """Formatează dimensiunea în KB/MB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def cli_create(args: List[str]) -> None:
    """CLI: backup create"""
    as_json = "--json" in args
    result = create_backup(reason="manual")

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if result["success"]:
        print(f"Backup creat: {result['filename']}")
        print(f"  Dimensiune: {_fmt_size(result['size'])}")
        print(f"  SHA-256:    {result['sha256'][:16]}...")
        print(f"  Verificat:  {'da' if result['verified'] else 'NU'}")
    else:
        print(f"Backup EȘUAT: {result['error']}")
        sys.exit(1)


def cli_list(args: List[str]) -> None:
    """CLI: backup list"""
    as_json = "--json" in args
    backups = list_backups()

    if as_json:
        print(json.dumps(backups, indent=2))
        return

    if not backups:
        print("Niciun backup disponibil.")
        return

    print(f"\n{'#':>3} {'Fișier':<35} {'Dimensiune':>10} {'Verificat':>9} {'Motiv':<12} {'Data':<20}")
    print("-" * 95)

    for i, entry in enumerate(backups, 1):
        fname = entry["filename"]
        size = _fmt_size(entry.get("size", 0))
        verified = "da" if entry.get("verified") else "nu"
        reason = entry.get("reason", "?")[:12]
        ts = entry.get("timestamp", "?")[:19]
        orphan = " [orfan]" if entry.get("orphan") else ""
        print(f"{i:>3} {fname:<35} {size:>10} {verified:>9} {reason:<12} {ts:<20}{orphan}")

    print(f"\nTotal: {len(backups)} backup-uri")


def cli_verify(args: List[str]) -> None:
    """CLI: backup verify [file]"""
    as_json = "--json" in args
    args_clean = [a for a in args if a != "--json"]

    if args_clean:
        # Verifică un backup specific
        filename = args_clean[0]
        result = verify_backup(filename)

        if as_json:
            print(json.dumps(result, indent=2))
            return

        print(f"Verificare: {filename}")
        print(f"  Valid:      {'da' if result['valid'] else 'NU'}")
        print(f"  Dimensiune: {_fmt_size(result.get('size', 0))}")
        print(f"  Tabele:     {result.get('tables', 0)}")
        print(f"  Integritate: {result.get('integrity', '?')}")
        if result.get("sha256_match") is not None:
            print(f"  SHA-256:    {'match' if result['sha256_match'] else 'MISMATCH!'}")
        if result.get("error"):
            print(f"  Eroare:     {result['error']}")
    else:
        # Verifică toate backup-urile
        backups = list_backups()
        results = []
        for entry in backups:
            r = verify_backup(entry["filename"])
            r["filename"] = entry["filename"]
            results.append(r)

        if as_json:
            print(json.dumps(results, indent=2))
            return

        valid_count = sum(1 for r in results if r["valid"])
        print(f"\nVerificare {len(results)} backup-uri:")
        for r in results:
            status = "OK" if r["valid"] else "INVALID"
            print(f"  [{status:>7}] {r['filename']} ({_fmt_size(r.get('size', 0))})")

        print(f"\n{valid_count}/{len(results)} backup-uri valide")


def cli_restore(args: List[str]) -> None:
    """CLI: backup restore <file> [--force]"""
    force = "--force" in args
    args_clean = [a for a in args if a != "--force"]

    if not args_clean:
        print("Folosire: mem backup restore <filename> [--force]")
        return

    filename = args_clean[0]
    result = restore_backup(filename, force=force)

    if result.get("needs_force"):
        info = result.get("backup_info", {})
        print(f"Restore din: {filename}")
        print(f"  Dimensiune: {_fmt_size(info.get('size', 0))}")
        print(f"  Tabele:     {info.get('tables', 0)}")
        print(f"  Integritate: {info.get('integrity', '?')}")
        print(f"\nAdaugă --force pentru a confirma restore-ul.")
        print(f"  DB-ul curent va fi backup-uit automat înainte.")
        return

    if result["success"]:
        print(f"Restore REUȘIT din: {filename}")
        print(f"  Backup pre-restore: {result['pre_restore_backup']}")
        print(f"  Verificat post-restore: {'da' if result['verified_after'] else 'NU'}")
    else:
        print(f"Restore EȘUAT: {result['error']}")
        if result.get("pre_restore_backup"):
            print(f"  Backup pre-restore disponibil: {result['pre_restore_backup']}")
        sys.exit(1)


def cli_cleanup(args: List[str]) -> None:
    """CLI: backup cleanup [--dry-run]"""
    dry_run = "--dry-run" in args
    as_json = "--json" in args
    result = cleanup_backups(dry_run=dry_run)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    mode = " (DRY RUN)" if dry_run else ""
    print(f"Cleanup backup-uri{mode}:")
    print(f"  Total:    {result['total_backups']}")
    print(f"  Păstrate: {result['kept']}")
    print(f"  Șterse:   {result['delete_count']}")

    if result["deleted"]:
        for f in result["deleted"]:
            print(f"    - {f}")

    if result["errors"]:
        for e in result["errors"]:
            print(f"  EROARE: {e['filename']}: {e['error']}")


def cli_status(args: List[str]) -> None:
    """CLI: backup status"""
    as_json = "--json" in args
    status = backup_status()

    if as_json:
        print(json.dumps(status, indent=2))
        return

    print(f"\nBackup Status")
    print(f"{'=' * 50}")
    print(f"  DB:              {status['db_path']}")
    print(f"  DB dimensiune:   {_fmt_size(status['db_size'])}")
    print(f"  DB validă:       {'da' if status['db_valid'] else 'NU'}")
    print(f"  DB tabele:       {status['db_tables']}")
    print(f"  Backup dir:      {status['backup_dir']}")
    print(f"  Total backup-uri: {status['total_backups']}")
    print(f"  Verificate:      {status['verified_backups']}")
    print(f"  Spațiu total:    {_fmt_size(status['total_backup_size'])}")

    latest = status.get("latest_backup")
    if latest:
        print(f"  Ultimul backup:  {latest['filename']}")
        print(f"    Data:          {latest.get('timestamp', '?')[:19]}")
        print(f"    Motiv:         {latest.get('reason', '?')}")
    else:
        print(f"  Ultimul backup:  NICIUNUL")

    ret = status["retention_policy"]
    print(f"  Retenție:        max {ret['max_backups']} + 1/zi x {ret['daily_retention_days']} zile")


def main():
    if len(sys.argv) < 2:
        print("Folosire: backup_manager.py <command> [args]")
        print("Comenzi: create, list, verify, restore, cleanup, status")
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "create": cli_create,
        "list": cli_list,
        "verify": cli_verify,
        "restore": cli_restore,
        "cleanup": cli_cleanup,
        "status": cli_status,
    }

    if command in commands:
        commands[command](args)
    else:
        print(f"Comandă necunoscută: {command}")
        print("Comenzi: create, list, verify, restore, cleanup, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
