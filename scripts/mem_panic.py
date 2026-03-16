#!/usr/bin/env python3
"""
mem_panic.py - Incident Response & Secrets Hunt
Emergency tool pentru detectare și remediere secrete în DB/logs
"""

import sys
import os
import json
import sqlite3
import hashlib
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import argparse

MEMORY_DIR = Path.home() / ".claude" / "memory"
DB_FILE = MEMORY_DIR / "global.db"
PANIC_DIR_BASE = Path("/tmp")
PANIC_MODE_FILE = MEMORY_DIR / ".panic_mode.json"
DOCS_DIR = MEMORY_DIR / "docs"

# Pattern-uri de detectare (reuse din guard)
PANIC_PATTERNS = [
    # CRITICAL
    (r'-----BEGIN (?:RSA |EC |OPENSSH |)(?:PRIVATE |)KEY-----', 'CRITICAL', 'pem_private'),
    (r'Authorization:\s*Bearer\s+[A-Za-z0-9\-\._~\+\/]{20,}', 'CRITICAL', 'bearer_auth'),
    (r'(access_token|refresh_token|id_token)[":\s]+[A-Za-z0-9\-_\.]{20,}', 'CRITICAL', 'jwt_token'),

    # HIGH
    (r'sk-[A-Za-z0-9]{20,}', 'HIGH', 'openai_key'),
    (r'ghp_[A-Za-z0-9]{30,}', 'HIGH', 'github_token'),
    (r'github_pat_[A-Za-z0-9_]{20,}', 'HIGH', 'github_pat'),
    (r'AKIA[0-9A-Z]{16}', 'HIGH', 'aws_access_key'),
    (r'AIza[0-9A-Za-z\-_]{20,}', 'HIGH', 'google_key'),
    (r'xox[baprs]-[A-Za-z0-9-]{10,}', 'HIGH', 'slack_token'),

    # MEDIUM (heuristic)
    (r'(?:token|secret|key|password|auth)[":\s=]+[A-Za-z0-9\-_\.]{45,}', 'MEDIUM', 'generic_token'),
]

# Excluderi (allowlist)
PANIC_EXCLUDES = [
    r'toolu_[A-Za-z0-9]+',  # Claude tool IDs
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',  # UUIDs
    r'REDACTED',  # Already scrubbed
    r'[0-9a-f]{64}',  # SHA256 hashes (unless in "token|key" context)
]

def set_panic_mode(enabled: bool, reason: str = None):
    """Setează/dezactivează panic mode."""
    state = {
        "enabled": enabled,
        "timestamp": datetime.now().isoformat(),
        "reason": reason or ("Panic mode activated" if enabled else "Panic mode deactivated")
    }
    PANIC_MODE_FILE.write_text(json.dumps(state, indent=2))

    if enabled:
        print(f"🚨 PANIC MODE: ENABLED")
        print(f"   Reason: {state['reason']}")
    else:
        print(f"✅ PANIC MODE: DISABLED")

def is_panic_mode() -> bool:
    """Verifică dacă panic mode e activ."""
    if not PANIC_MODE_FILE.exists():
        return False
    try:
        state = json.loads(PANIC_MODE_FILE.read_text())
        return state.get("enabled", False)
    except:
        return False

def get_panic_status() -> Dict:
    """Returnează status panic mode."""
    if not PANIC_MODE_FILE.exists():
        return {"enabled": False, "timestamp": None, "reason": None}

    try:
        return json.loads(PANIC_MODE_FILE.read_text())
    except:
        return {"enabled": False, "timestamp": None, "reason": None}

def panic_backup() -> Path:
    """Creează backup atomic în /tmp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = PANIC_DIR_BASE / f"claude_PANIC_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📦 Creating atomic backup...")
    print(f"   Location: {backup_dir}")

    manifest = {
        "timestamp": datetime.now().isoformat(),
        "backup_dir": str(backup_dir),
        "files": {}
    }

    # Backup DB + WAL/SHM
    files_to_backup = [
        ("global.db", DB_FILE),
        ("global.db-wal", MEMORY_DIR / "global.db-wal"),
        ("global.db-shm", MEMORY_DIR / "global.db-shm"),
    ]

    # Backup logs
    for log_file in MEMORY_DIR.glob("*.log"):
        files_to_backup.append((log_file.name, log_file))

    # Backup state files
    for state_file in MEMORY_DIR.glob(".*.json"):
        files_to_backup.append((state_file.name, state_file))

    for dest_name, src_path in files_to_backup:
        if src_path.exists():
            dest_path = backup_dir / dest_name
            shutil.copy2(src_path, dest_path)

            # Calculate SHA256
            sha256 = hashlib.sha256(dest_path.read_bytes()).hexdigest()
            manifest["files"][dest_name] = {
                "size": dest_path.stat().st_size,
                "sha256": sha256,
                "source": str(src_path)
            }
            print(f"   ✓ {dest_name} ({dest_path.stat().st_size} bytes)")

    # Save manifest
    manifest_path = backup_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"   ✓ MANIFEST.json (SHA256 hashes)")

    print(f"\n✅ Backup complete: {len(manifest['files'])} files")
    return backup_dir

# === AUDIT LOGGING pentru PANIC operations ===

def audit_log_write_local(action_type: str, table_name: str = "system",
                           severity: str = "HIGH", change_summary: str = "",
                           actor: str = "mem_panic"):
    """Scrie în audit_log pentru panic operations."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_log
            (ts, action_type, table_name, row_id, fingerprint, severity, change_summary, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            action_type,
            table_name,
            None,
            None,
            severity,
            change_summary,
            actor
        ))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  Audit logging failed: {e}", file=sys.stderr)

def safe_snippet(text: str, max_context: int = 40) -> str:
    """Returnează snippet safe (fără secrete complete)."""
    # Mascare pattern-uri
    for pattern, _, _ in PANIC_PATTERNS:
        matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            matched_text = match.group(0)
            # Păstrează doar primele 4 + ultimele 4
            if len(matched_text) > 12:
                redacted = f"{matched_text[:4]}****REDACTED****{matched_text[-4:]}"
            else:
                redacted = "****REDACTED****"
            text = text.replace(matched_text, redacted)

    # Limitează context
    if len(text) > max_context * 2:
        return f"{text[:max_context]}...{text[-max_context:]}"
    return text

def detect_secrets_in_text(text: str) -> List[Dict]:
    """Detectează secrete în text, returnează lista de hits."""
    if not text:
        return []

    hits = []

    for pattern, severity, secret_type in PANIC_PATTERNS:
        matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            matched_text = match.group(0)

            # Check excludes
            is_excluded = False
            for exc_pattern in PANIC_EXCLUDES:
                if re.search(exc_pattern, matched_text):
                    is_excluded = True
                    break

            if is_excluded:
                continue

            # Fingerprint (hash pe versiunea redacted)
            redacted = safe_snippet(matched_text, max_context=10)
            fingerprint = hashlib.sha256(redacted.encode()).hexdigest()[:16]

            hits.append({
                "type": secret_type,
                "severity": severity,
                "fingerprint": fingerprint,
                "position": match.start(),
                "length": len(matched_text)
            })

    return hits

def panic_scan_table(db_path: Path, table: str, column: str, limit: Optional[int] = None) -> List[Dict]:
    """Scanează o tabelă pentru secrete."""
    results = []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check dacă tabela există
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cursor.fetchone():
            return results

        # Query (cu LIMIT opțional pentru teste)
        query = f"SELECT rowid, {column} FROM {table}"
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            row_id = row[0]
            content = row[1]

            if not content:
                continue

            hits = detect_secrets_in_text(str(content))

            if hits:
                snippet = safe_snippet(str(content), max_context=60)

                results.append({
                    "table": table,
                    "column": column,
                    "row_id": row_id,
                    "hits": hits,
                    "snippet": snippet
                })

        conn.close()

    except Exception as e:
        print(f"❌ Error scanning {table}.{column}: {e}")

    return results

def panic_scan(db_path: Path, scan_only: bool = True) -> Dict:
    """Scan global pentru secrete."""
    print(f"\n🔍 Scanning database for secrets...")
    print(f"   Database: {db_path}")
    print(f"   Mode: {'scan-only' if scan_only else 'full'}")

    all_results = []

    # Tabele și coloane de scanat
    scan_targets = [
        ("messages", "content"),
        ("tool_calls", "tool_input"),
        ("tool_calls", "tool_result"),
        ("bash_history", "command"),
        ("bash_history", "output"),
        ("bash_history", "error_output"),
        ("errors_solutions", "error_message"),
        ("checkpoints", "summary"),
    ]

    for table, column in scan_targets:
        print(f"   Scanning {table}.{column}...", end=" ")
        results = panic_scan_table(db_path, table, column)
        if results:
            print(f"🚨 {len(results)} hits")
            all_results.extend(results)
        else:
            print("✓")

    # Agregare rezultate
    by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": []}
    for result in all_results:
        for hit in result["hits"]:
            severity = hit["severity"]
            by_severity[severity].append(result)

    summary = {
        "total_hits": len(all_results),
        "by_severity": {
            "CRITICAL": len(by_severity["CRITICAL"]),
            "HIGH": len(by_severity["HIGH"]),
            "MEDIUM": len(by_severity["MEDIUM"])
        },
        "results": all_results,
        "scanned_tables": len(scan_targets)
    }

    print(f"\n📊 Scan complete:")
    print(f"   Total hits: {summary['total_hits']}")
    print(f"   CRITICAL: {summary['by_severity']['CRITICAL']}")
    print(f"   HIGH: {summary['by_severity']['HIGH']}")
    print(f"   MEDIUM: {summary['by_severity']['MEDIUM']}")

    return summary

def panic_report(results: Dict, backup_dir: Path) -> Path:
    """Generează raport panic."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = DOCS_DIR / f"PANIC_REPORT_{timestamp}.md"

    report = f"""# PANIC MODE REPORT

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Backup Location**: `{backup_dir}`

## Summary

- **Total Hits**: {results['total_hits']}
- **CRITICAL**: {results['by_severity']['CRITICAL']}
- **HIGH**: {results['by_severity']['HIGH']}
- **MEDIUM**: {results['by_severity']['MEDIUM']}
- **Tables Scanned**: {results['scanned_tables']}

## Findings

"""

    if results['total_hits'] == 0:
        report += "✅ **No secrets detected** - Database appears clean.\n\n"
    else:
        report += "🚨 **Secrets detected** - Review findings below.\n\n"

        # Grupează pe severity
        by_sev = {"CRITICAL": [], "HIGH": [], "MEDIUM": []}
        for r in results['results']:
            for hit in r['hits']:
                by_sev[hit['severity']].append((r, hit))

        for severity in ["CRITICAL", "HIGH", "MEDIUM"]:
            if by_sev[severity]:
                report += f"### {severity} Findings\n\n"

                for i, (r, hit) in enumerate(by_sev[severity][:20], 1):  # Max 20 per severity
                    report += f"**{i}. {r['table']}.{r['column']}** (row_id: {r['row_id']})\n"
                    report += f"- Type: `{hit['type']}`\n"
                    report += f"- Fingerprint: `{hit['fingerprint']}`\n"
                    report += f"- Snippet: `{r['snippet']}`\n\n"

                if len(by_sev[severity]) > 20:
                    report += f"*({len(by_sev[severity]) - 20} more findings omitted)*\n\n"

    report += """## Remediation Steps

"""

    if results['total_hits'] > 0:
        report += """### Option 1: Manual Review
1. Review findings above
2. Verify if they are actual secrets or false positives
3. Update patterns in `PANIC_PATTERNS` if needed

### Option 2: Automated Fix (EXPERIMENTAL)
```bash
# Backup first (already done)
mem panic --fix

# Or with explicit confirmation
MEMORY_PANIC_ALLOW_FIX=1 mem panic --fix
```

**WARNING**: `--fix` will modify database records. Backup is preserved in:
`{backup_dir}`

"""
    else:
        report += "✅ No remediation needed - database is clean.\n\n"

    report += f"""## Backup Manifest

See `{backup_dir}/MANIFEST.json` for SHA256 hashes of backed up files.

---

*Generated by `mem panic` - EAN AgentOS*
"""

    report_path.write_text(report)
    print(f"\n📄 Report saved: {report_path}")

    return report_path

def panic_fix(results: Dict, db_path: Path, dry_run: bool = False) -> Dict:
    """Aplică fix-uri automate (EXPERIMENTAL)."""
    if dry_run:
        print("\n🔧 DRY RUN: Showing what would be fixed...")
    else:
        print("\n🔧 Applying automated fixes...")

    fix_plan = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "fixed": [],
        "errors": []
    }

    if not results['results']:
        print("   No fixes needed")
        return fix_plan

    # Grupează pe table/column
    to_fix = {}
    for r in results['results']:
        key = (r['table'], r['column'])
        if key not in to_fix:
            to_fix[key] = []
        to_fix[key].append(r['row_id'])

    # Aplică fix-uri (reuse scrub logic)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for (table, column), row_ids in to_fix.items():
            print(f"   Fixing {table}.{column}: {len(row_ids)} rows...")

            for row_id in row_ids:
                try:
                    # Fetch current value
                    cursor.execute(f"SELECT {column} FROM {table} WHERE rowid = ?", (row_id,))
                    row = cursor.fetchone()
                    if not row:
                        continue

                    original = row[0]
                    if not original:
                        continue

                    # Apply scrubbing (reuse safe_snippet logic)
                    fixed = safe_snippet(original, max_context=999999)  # No truncation

                    if fixed != original:
                        if not dry_run:
                            cursor.execute(f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                                         (fixed, row_id))

                        fix_plan["fixed"].append({
                            "table": table,
                            "column": column,
                            "row_id": row_id,
                            "changed": True
                        })

                except Exception as e:
                    fix_plan["errors"].append({
                        "table": table,
                        "row_id": row_id,
                        "error": str(e)
                    })

        if not dry_run:
            conn.commit()
        conn.close()

    except Exception as e:
        print(f"❌ Fix error: {e}")
        fix_plan["errors"].append({"error": str(e)})

    print(f"\n✅ Fix complete:")
    print(f"   Fixed: {len(fix_plan['fixed'])}")
    print(f"   Errors: {len(fix_plan['errors'])}")

    return fix_plan

def cmd_panic(args):
    """Main panic command."""
    # Check flags
    scan_only = args.scan_only
    do_fix = args.fix
    dry_run = args.dry_run

    # Guard pentru --fix
    if do_fix and not dry_run:
        allow_fix = os.environ.get("MEMORY_PANIC_ALLOW_FIX", "0") == "1"
        if not allow_fix:
            print("❌ ERROR: --fix requires MEMORY_PANIC_ALLOW_FIX=1 environment variable")
            print("   This is a safety measure to prevent accidental database modifications.")
            print("   Usage: MEMORY_PANIC_ALLOW_FIX=1 mem panic --fix")
            sys.exit(1)

    print("🚨" * 30)
    print("   PANIC MODE - INCIDENT RESPONSE")
    print("🚨" * 30)

    # Step 1: Set panic mode (dacă nu e scan-only)
    if not scan_only:
        set_panic_mode(True, reason="Manual panic initiated")
        audit_log_write_local(
            action_type="panic_freeze",
            severity="CRITICAL",
            change_summary="Panic mode activated - freeze initiated"
        )

    # Step 2: Backup atomic
    backup_dir = panic_backup()
    audit_log_write_local(
        action_type="panic_backup",
        severity="HIGH",
        change_summary=f"Emergency backup created: {backup_dir.name}"
    )

    # Step 3: Scan
    results = panic_scan(DB_FILE, scan_only=True)
    audit_log_write_local(
        action_type="panic_scan",
        severity="HIGH",
        change_summary=f"Scan complete: {results['total_hits']} hits detected"
    )

    # Step 4: Report
    report_path = panic_report(results, backup_dir)

    # Step 5: Fix (dacă requested)
    if do_fix:
        fix_results = panic_fix(results, DB_FILE, dry_run=dry_run)

        # Save fix plan
        fix_plan_path = backup_dir / "FIX_PLAN.json"
        fix_plan_path.write_text(json.dumps(fix_results, indent=2))
        print(f"\n💾 Fix plan saved: {fix_plan_path}")

        # Audit log pentru fix
        severity = "CRITICAL" if not dry_run else "HIGH"
        action = "panic_fix" if not dry_run else "panic_fix_dryrun"
        summary = f"Applied fixes: {fix_results.get('modified', 0)} rows" if not dry_run else f"Dry run: {fix_results.get('would_modify', 0)} rows would be modified"

        audit_log_write_local(
            action_type=action,
            severity=severity,
            change_summary=summary
        )

    # Final summary
    print(f"\n" + "=" * 60)
    print("PANIC MODE COMPLETE")
    print("=" * 60)
    print(f"📦 Backup: {backup_dir}")
    print(f"📄 Report: {report_path}")

    if results['total_hits'] > 0:
        print(f"\n⚠️  {results['total_hits']} potential secrets detected")
        print("   Review report for details and remediation steps")
    else:
        print(f"\n✅ No secrets detected - database appears clean")

    # Dezactivează panic mode la final (dacă nu e scan-only)
    if not scan_only:
        set_panic_mode(False, reason="Panic scan completed")
        audit_log_write_local(
            action_type="panic_resume",
            severity="INFO",
            change_summary="Panic mode deactivated - normal operations resumed"
        )

def cmd_status(args):
    """Afișează status panic mode."""
    status = get_panic_status()

    print("\n🔍 PANIC MODE STATUS")
    print("=" * 60)

    if status["enabled"]:
        print("🚨 Status: ACTIVE")
        print(f"   Since: {status.get('timestamp', 'unknown')}")
        print(f"   Reason: {status.get('reason', 'unknown')}")
    else:
        print("✅ Status: INACTIVE")

    # Ultimele rapoarte
    reports = sorted(DOCS_DIR.glob("PANIC_REPORT_*.md"), reverse=True)[:5]
    if reports:
        print(f"\n📄 Recent Reports ({len(reports)}):")
        for r in reports:
            timestamp = r.stem.replace("PANIC_REPORT_", "")
            print(f"   - {timestamp}: {r}")
    else:
        print("\n📄 No recent reports")

def cmd_resume(args):
    """Repornire din panic mode."""
    if not is_panic_mode():
        print("✅ Panic mode already inactive")
        return

    set_panic_mode(False, reason="Manual resume requested")
    print("✅ Panic mode deactivated - normal operations resumed")

def main():
    parser = argparse.ArgumentParser(description="Incident Response & Secrets Hunt")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # panic command
    panic_parser = subparsers.add_parser('panic', help='Run panic scan')
    panic_parser.add_argument('--scan-only', action='store_true', help='Scan only, no freeze')
    panic_parser.add_argument('--fix', action='store_true', help='Apply automated fixes (requires MEMORY_PANIC_ALLOW_FIX=1)')
    panic_parser.add_argument('--dry-run', action='store_true', help='Dry run for --fix (show what would be changed)')

    # status command
    subparsers.add_parser('status', help='Show panic mode status')

    # resume command
    subparsers.add_parser('resume', help='Deactivate panic mode')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'panic': cmd_panic,
        'status': cmd_status,
        'resume': cmd_resume,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        print(f"❌ Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
