#!/usr/bin/env python3
"""
mem_doctor.py - Health check rapid pentru sistemul de EAN AgentOS persistent memory
Target: sub 2s execuție, 6 verificări
"""

import sys
import os
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

MEMORY_DIR = Path.home() / ".claude" / "memory"
DB_FILE = MEMORY_DIR / "global.db"

def check_db_integrity():
    """Check 1: DB Integrity (quick_check pentru viteză)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            return {"status": "ok", "message": "Integritate DB: OK"}
        else:
            return {"status": "fail", "message": f"DB corrupt: {result}"}
    except Exception as e:
        return {"status": "fail", "message": f"Eroare DB: {e}"}

def check_fts5():
    """Check 2: FTS5 funcțional și activ."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Verifică tabele FTS
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'")
        fts_tables = [row[0] for row in cursor.fetchall()]

        if not fts_tables:
            conn.close()
            return {"status": "warn", "message": "Nicio tabelă FTS găsită"}

        # Test query simplu pe messages_fts
        try:
            cursor.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'test' LIMIT 1")
            cursor.fetchone()
        except Exception as e:
            conn.close()
            return {"status": "warn", "message": f"FTS5 eroare query: {e}"}

        conn.close()
        return {"status": "ok", "message": f"FTS5 activ: {len(fts_tables)} tabele"}
    except Exception as e:
        return {"status": "fail", "message": f"FTS5 eroare: {e}"}

def check_reconciler():
    """Check 3: Reconciler state verificare."""
    state_file = MEMORY_DIR / ".reconciler_state.json"
    try:
        if not state_file.exists():
            return {"status": "warn", "message": "Reconciler state lipsă"}

        state = json.loads(state_file.read_text())
        sessions = state.get("sessions", {})

        # Verifică drift
        drift_sessions = [s for s, data in sessions.items() if data.get("drift_detected", False)]

        if drift_sessions:
            return {"status": "warn", "message": f"Drift detectat: {len(drift_sessions)} sesiuni"}

        return {"status": "ok", "message": f"Reconciler: {len(sessions)} sesiuni tracked"}
    except Exception as e:
        return {"status": "warn", "message": f"Reconciler eroare: {e}"}

def check_compact():
    """Check 4: Auto-compact status."""
    try:
        autocompact = os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "")

        # Caută ultimul compact_boundary
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT content, timestamp FROM messages
            WHERE content LIKE '%compact_boundary%'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        conn.close()

        if result:
            ts = result[1][:10] if result[1] else "?"
            msg = f"Ultima compact: {ts}"
        else:
            msg = "Compact: niciun istoric"

        if autocompact == "100":
            msg += " (override: 100% - disabled)"
        elif autocompact:
            msg += f" (override: {autocompact}%)"

        return {"status": "ok", "message": msg}
    except Exception as e:
        return {"status": "warn", "message": f"Compact check eroare: {e}"}

def check_disk_space():
    """Check 5: Spațiu disc disponibil."""
    try:
        result = subprocess.run(
            ["df", "-h", str(MEMORY_DIR)],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            used_pct = parts[4]  # ex: "39%"
            avail = parts[3]     # ex: "655G"

            pct_num = int(used_pct.rstrip('%'))
            if pct_num > 90:
                return {"status": "warn", "message": f"Spațiu disc: {used_pct} folosit, {avail} liber"}
            else:
                return {"status": "ok", "message": f"Spațiu disc: {avail} liber ({used_pct} folosit)"}
        else:
            return {"status": "warn", "message": "Nu pot determina spațiu disc"}
    except Exception as e:
        return {"status": "warn", "message": f"Disc check eroare: {e}"}

def check_hooks():
    """Check 6: PreCompact hook configurat."""
    settings_file = Path.home() / ".claude" / "settings.json"
    try:
        if not settings_file.exists():
            return {"status": "warn", "message": "settings.json lipsă"}

        settings = json.loads(settings_file.read_text())
        has_precompact = "PreCompact" in settings

        if has_precompact:
            return {"status": "ok", "message": "PreCompact hook: enabled"}
        else:
            return {"status": "warn", "message": "PreCompact hook: disabled"}
    except Exception as e:
        return {"status": "warn", "message": f"Hook check eroare: {e}"}

def run_doctor(fix=False, json_output=False):
    """Rulează toate verificările."""
    checks = {
        "db_integrity": check_db_integrity(),
        "fts5": check_fts5(),
        "reconciler": check_reconciler(),
        "compact": check_compact(),
        "disk": check_disk_space(),
        "hooks": check_hooks(),
    }

    # Determine overall status
    has_fail = any(c["status"] == "fail" for c in checks.values())
    has_warn = any(c["status"] == "warn" for c in checks.values())

    if has_fail:
        overall = "FAIL"
    elif has_warn:
        overall = "WARN"
    else:
        overall = "OK"

    # Auto-fix (doar PRAGMA optimize dacă e safe)
    if fix and not has_fail:
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("PRAGMA optimize")
            conn.close()
            checks["auto_fix"] = {"status": "ok", "message": "PRAGMA optimize executat"}
        except Exception as e:
            checks["auto_fix"] = {"status": "fail", "message": f"Fix eroare: {e}"}

    # Output
    if json_output:
        print(json.dumps({"status": overall.lower(), "checks": checks}, indent=2))
    else:
        print("\n🏥 DATABASE HEALTH CHECK")
        print("=" * 60)

        for name, result in checks.items():
            emoji = {"ok": "✅", "warn": "⚠️", "fail": "❌"}[result["status"]]
            print(f"{emoji} {name:20} {result['message']}")

        print("=" * 60)

        if overall == "OK":
            print(f"Status final: ✅ {overall}")
        elif overall == "WARN":
            print(f"Status final: ⚠️  {overall}")
        else:
            print(f"Status final: ❌ {overall}")

        if overall != "OK":
            print("\n💡 Recomandare: Rulează 'mem doctor --fix' pentru remedieri automate safe")

    return 0 if overall == "OK" else 1

if __name__ == "__main__":
    fix = "--fix" in sys.argv
    json_out = "--json" in sys.argv
    sys.exit(run_doctor(fix=fix, json_output=json_out))
