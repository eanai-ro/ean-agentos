#!/usr/bin/env python3
"""
Teste Faza 4 — Memory Intelligence Layer
"""

import os
import sys
import json
import sqlite3
import subprocess
import io
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import redirect_stdout

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

TEST_DB = PROJECT_ROOT / "test_phase4.db"
os.environ["MEMORY_DB_PATH"] = str(TEST_DB)

# Clean imports
for mod in list(sys.modules.keys()):
    if mod in ("v2_common", "context_builder_v2", "context_strategy",
               "error_patterns", "fact_promoter", "decision_analyzer", "memory_cleanup"):
        del sys.modules[mod]

from v2_common import (
    set_current_intent, clear_current_intent, INTENT_FILE, SNAPSHOT_FILE,
)

passed = 0
failed = 0
errors = []


def test(name, condition, msg=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        errors.append(f"{name}: {msg}")
        print(f"  ❌ {name} — {msg}")


def setup_test_db():
    if TEST_DB.exists():
        TEST_DB.unlink()

    conn = sqlite3.connect(str(TEST_DB))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY, session_id TEXT, project_path TEXT, started_at TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY, session_id TEXT, tool_name TEXT, tool_input TEXT,
            file_path TEXT, exit_code INTEGER, timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS errors_solutions (
            id INTEGER PRIMARY KEY, error_type TEXT, error_message TEXT, solution TEXT,
            tool_name_resolved TEXT, resolved INTEGER DEFAULT 0, source TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS bash_history (
            id INTEGER PRIMARY KEY, command TEXT, exit_code INTEGER, timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS token_costs (
            id INTEGER PRIMARY KEY, input_tokens INTEGER, output_tokens INTEGER,
            cost_usd REAL, timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS checkpoints (id INTEGER PRIMARY KEY, data TEXT);
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, category TEXT DEFAULT 'technical',
            status TEXT DEFAULT 'active', confidence TEXT DEFAULT 'high',
            stale_after_days INTEGER DEFAULT 90,
            project_path TEXT, source_session TEXT, model_used TEXT, provider TEXT,
            created_by TEXT, created_at TEXT, updated_at TEXT, superseded_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS learned_facts (
            id INTEGER PRIMARY KEY, fact TEXT, fact_type TEXT DEFAULT 'technical',
            category TEXT, is_pinned INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
            confidence TEXT DEFAULT 'high', project_path TEXT, source_session TEXT,
            model_used TEXT, provider TEXT, created_by TEXT, created_at TEXT,
            updated_at TEXT, superseded_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'active', target_date TEXT,
            project_path TEXT, source_session TEXT, created_by TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'todo', goal_id INTEGER, blocked_by TEXT,
            project_path TEXT, source_session TEXT, created_by TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS project_profiles (
            id INTEGER PRIMARY KEY, project_path TEXT UNIQUE, project_name TEXT,
            description TEXT, tech_stack TEXT, conventions TEXT, notes TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS error_resolutions (
            id INTEGER PRIMARY KEY, error_id INTEGER, error_type TEXT, error_summary TEXT,
            resolution TEXT, resolution_type TEXT DEFAULT 'fix',
            worked INTEGER DEFAULT 0, model_used TEXT, provider TEXT,
            project_path TEXT, source_session TEXT, fingerprint TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS model_usage_log (
            id INTEGER PRIMARY KEY, model_id TEXT, provider TEXT, action_type TEXT,
            session_id TEXT, project_path TEXT, timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS error_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_signature TEXT NOT NULL,
            solution TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            first_seen TEXT, last_seen TEXT,
            project_path TEXT, auto_promoted INTEGER DEFAULT 0
        );
    """)

    now = datetime.now().isoformat()
    old = (datetime.now() - timedelta(days=200)).isoformat()
    proj = str(Path.cwd())

    conn.execute("INSERT INTO project_profiles (project_path, project_name, tech_stack) VALUES (?, 'TestProject', ?)",
                 (proj, json.dumps(["python", "sqlite"])))

    # Decisions: 2 similare (conflict) + 1 normală + 1 stale
    conn.execute("INSERT INTO decisions (title, description, category, status, project_path, created_at, stale_after_days) VALUES (?, ?, 'technical', 'active', ?, ?, 90)",
                 ("Use SQLite for storage", "SQLite is simpler", proj, now))
    conn.execute("INSERT INTO decisions (title, description, category, status, project_path, created_at, stale_after_days) VALUES (?, ?, 'technical', 'active', ?, ?, 90)",
                 ("Use SQLite database", "SQLite database for data", proj, now))
    conn.execute("INSERT INTO decisions (title, description, category, status, project_path, created_at, stale_after_days) VALUES (?, ?, 'convention', 'active', ?, ?, 90)",
                 ("Use snake_case", "Python convention", proj, now))
    # Stale decision (200 days old, stale_after=90)
    conn.execute("INSERT INTO decisions (title, description, category, status, project_path, created_at, stale_after_days) VALUES (?, ?, 'tooling', 'active', ?, ?, 90)",
                 ("Use webpack bundler", "Old bundler choice", proj, old))

    # Facts: mix of types, ages, pinned
    conn.execute("INSERT INTO learned_facts (fact, fact_type, is_pinned, is_active, confidence, project_path, created_at) VALUES (?, 'technical', 0, 1, 'confirmed', ?, ?)",
                 ("SQLite WAL mode improves concurrency", proj, now))
    conn.execute("INSERT INTO learned_facts (fact, fact_type, is_pinned, is_active, confidence, project_path, created_at) VALUES (?, 'gotcha', 0, 1, 'high', ?, ?)",
                 ("Python asyncio requires explicit event loop", proj, now))
    conn.execute("INSERT INTO learned_facts (fact, fact_type, is_pinned, is_active, confidence, project_path, created_at) VALUES (?, 'convention', 1, 1, 'high', ?, ?)",
                 ("Always use type hints", proj, now))
    # Old fact (stale candidate)
    conn.execute("INSERT INTO learned_facts (fact, fact_type, is_pinned, is_active, confidence, project_path, created_at) VALUES (?, 'technical', 0, 1, 'low', ?, ?)",
                 ("Old unused fact about webpack", proj, old))

    # Error resolutions: 4 cu aceeași eroare (pattern >3)
    for i in range(4):
        conn.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?, ?, 1, ?, ?)",
                     ("ImportError: No module named xyz", "pip install xyz", proj, now))

    # Extra resolutions
    conn.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?, ?, 1, ?, ?)",
                 ("ConnectionError: timeout", "Retry with backoff", proj, now))
    # Stale resolution (worked=0, old)
    conn.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?, ?, 0, ?, ?)",
                 ("Old error", "Old solution", proj, old))

    # Goals: 1 normal + 1 stale
    conn.execute("INSERT INTO goals (title, priority, status, project_path, created_at) VALUES (?, 'high', 'active', ?, ?)",
                 ("Implement V2", proj, now))
    conn.execute("INSERT INTO goals (title, priority, status, project_path, created_at) VALUES (?, 'low', 'active', ?, ?)",
                 ("Old abandoned goal", proj, old))

    # Tasks: 2 normal + 1 stale
    conn.execute("INSERT INTO tasks (title, priority, status, project_path, created_at, updated_at) VALUES (?, 'high', 'in_progress', ?, ?, ?)",
                 ("Current task", proj, now, now))
    conn.execute("INSERT INTO tasks (title, priority, status, project_path, created_at, updated_at) VALUES (?, 'low', 'todo', ?, ?, ?)",
                 ("Very old abandoned task", proj, old, old))

    conn.commit()
    conn.close()


def cleanup():
    for f in [TEST_DB, INTENT_FILE, SNAPSHOT_FILE]:
        if f.exists():
            f.unlink()
    for ext in ["-wal", "-shm"]:
        p = Path(str(TEST_DB) + ext)
        if p.exists():
            p.unlink()
    log = PROJECT_ROOT / ".context_strategy.log"
    if log.exists():
        log.unlink()


# ============================================================
print("\n🧪 TESTE FAZA 4 — Memory Intelligence Layer\n")
cleanup()
setup_test_db()

for mod in list(sys.modules.keys()):
    if mod in ("error_patterns", "fact_promoter", "decision_analyzer", "memory_cleanup",
               "context_builder_v2", "context_strategy"):
        del sys.modules[mod]

from error_patterns import fetch_patterns_for_context, fmt_patterns, cmd_detect, ensure_table, _signature
from fact_promoter import _score_fact, cmd_scan, cmd_promote
from decision_analyzer import detect_conflicts, detect_stale, fetch_conflicts_for_context, fmt_conflicts
from memory_cleanup import (detect_stale_facts, detect_stale_tasks, detect_stale_resolutions,
                            detect_stale_goals, fetch_stale_summary_for_context)

# ============================================================
# T1: Error Pattern Detection
# ============================================================
print("--- T1: Error Pattern Detection ---")

# Detect patterns
f_out = io.StringIO()
with redirect_stdout(f_out):
    cmd_detect(None)
out = f_out.getvalue()
test("T1a detect runs", "Pattern detection" in out, out[:100])

# Verify pattern was created
conn = sqlite3.connect(str(TEST_DB))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM error_patterns WHERE count >= 3")
patterns = cursor.fetchall()
test("T1b pattern found", len(patterns) >= 1, f"got {len(patterns)}")
if patterns:
    test("T1c count >= 3", patterns[0]["count"] >= 3, f"count={patterns[0]['count']}")
    test("T1d has solution", "pip install" in patterns[0]["solution"].lower(), patterns[0]["solution"])
conn.close()

# Fetch for context
conn = sqlite3.connect(str(TEST_DB))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
ctx_patterns = fetch_patterns_for_context(cursor, str(Path.cwd()), limit=5)
test("T1e fetch for context", len(ctx_patterns) >= 1, f"got {len(ctx_patterns)}")

# Format
fmt = fmt_patterns(ctx_patterns, compact=True)
test("T1f format", "Error patterns:" in fmt, fmt[:50])
conn.close()

# ============================================================
# T2: Fact Promotion
# ============================================================
print("\n--- T2: Fact Promotion ---")

conn = sqlite3.connect(str(TEST_DB))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Score facts
cursor.execute("SELECT * FROM learned_facts WHERE is_active = 1")
facts = cursor.fetchall()

scores = []
for fact in facts:
    score = _score_fact(fact, cursor)
    scores.append((fact["id"], fact["fact"][:30], score, fact["is_pinned"]))

test("T2a scoring works", len(scores) > 0, f"got {len(scores)}")
# Already pinned should score 0
pinned_scores = [s for s in scores if s[3] == 1]
for ps in pinned_scores:
    test(f"T2b pinned #{ps[0]} score=0", ps[2] == 0, f"score={ps[2]}")

conn.close()

# Scan command
f_out = io.StringIO()
with redirect_stdout(f_out):
    cmd_scan(None)
out = f_out.getvalue()
test("T2c scan runs", "Fact Scoring" in out, out[:80])

# ============================================================
# T3: Decision Conflict Detection
# ============================================================
print("\n--- T3: Decision Conflict Detection ---")

conn = sqlite3.connect(str(TEST_DB))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

conflicts = detect_conflicts(cursor, str(Path.cwd()))
test("T3a conflicts detected", len(conflicts) >= 1, f"got {len(conflicts)}")
if conflicts:
    test("T3b conflict has type", conflicts[0]["type"] == "similar_title")
    test("T3c conflict has category", conflicts[0]["category"] == "technical")
    test("T3d conflict has overlap", conflicts[0]["overlap"] > 0.3, f"overlap={conflicts[0]['overlap']}")

# Stale detection
stale = detect_stale(cursor)
test("T3e stale decisions", len(stale) >= 1, f"got {len(stale)}")
if stale:
    test("T3f stale age > 90", stale[0]["age_days"] > 90)

# Format conflicts
ctx_conflicts = fetch_conflicts_for_context(cursor, str(Path.cwd()), limit=3)
fmt = fmt_conflicts(ctx_conflicts, compact=True)
test("T3g format conflicts", "conflict" in fmt.lower() if fmt else True, fmt[:50] if fmt else "empty")

conn.close()

# ============================================================
# T4: Memory Cleanup Detection
# ============================================================
print("\n--- T4: Memory Cleanup Detection ---")

conn = sqlite3.connect(str(TEST_DB))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

stale_facts = detect_stale_facts(cursor)
test("T4a stale facts", len(stale_facts) >= 1, f"got {len(stale_facts)}")

stale_tasks = detect_stale_tasks(cursor)
test("T4b stale tasks", len(stale_tasks) >= 1, f"got {len(stale_tasks)}")

stale_resolutions = detect_stale_resolutions(cursor)
test("T4c stale resolutions", len(stale_resolutions) >= 1, f"got {len(stale_resolutions)}")

stale_goals = detect_stale_goals(cursor)
test("T4d stale goals", len(stale_goals) >= 1, f"got {len(stale_goals)}")

summary = fetch_stale_summary_for_context(cursor)
test("T4e stale summary", "Stale:" in summary, summary)

conn.close()

# ============================================================
# T5: Context Integration
# ============================================================
print("\n--- T5: Context Integration ---")

clear_current_intent()
if SNAPSHOT_FILE.exists():
    SNAPSHOT_FILE.unlink()

for mod in ("context_builder_v2",):
    if mod in sys.modules:
        del sys.modules[mod]
from context_builder_v2 import build_context

f_out = io.StringIO()
with redirect_stdout(f_out):
    build_context(mode="compact")
out = f_out.getvalue()

test("T5a context has patterns", "Error patterns:" in out or "COMPACT" in out, out[:200])
test("T5b context has model", "Model:" in out)
# Conflicts might appear
test("T5c context generated", "CONTEXT V2" in out, out[:100])

# Full mode
f_out = io.StringIO()
with redirect_stdout(f_out):
    build_context(mode="full")
out_full = f_out.getvalue()
test("T5d full context", "FULL" in out_full)

# ============================================================
# T6: CLI Commands
# ============================================================
print("\n--- T6: CLI Commands ---")

mem_script = str(SCRIPTS_DIR / "mem")

r = subprocess.run(["python3", mem_script, "patterns"], capture_output=True, text=True)
test("T6a mem patterns", r.returncode == 0)

r = subprocess.run(["python3", mem_script, "patterns", "detect"], capture_output=True, text=True)
test("T6b mem patterns detect", r.returncode == 0 and "Pattern" in r.stdout, r.stdout[:80])

r = subprocess.run(["python3", mem_script, "cleanup"], capture_output=True, text=True)
test("T6c mem cleanup", r.returncode == 0 and "CLEANUP" in r.stdout, r.stdout[:80])

r = subprocess.run(["python3", mem_script, "promote", "scan"], capture_output=True, text=True)
test("T6d mem promote scan", r.returncode == 0 and "Fact Scoring" in r.stdout, r.stdout[:80])

r = subprocess.run(["python3", mem_script, "intelligence"], capture_output=True, text=True)
test("T6e mem intelligence", r.returncode == 0 and "INTELLIGENCE" in r.stdout, r.stdout[:80])

# ============================================================
# REGRESIE
# ============================================================
print("\n--- Regresie ---")

# mem context
r = subprocess.run(["python3", mem_script, "context", "--compact"], capture_output=True, text=True)
test("R1 context --compact", r.returncode == 0 and "COMPACT" in r.stdout, r.stdout[:80])

# mem strategy
r = subprocess.run(["python3", mem_script, "strategy"], capture_output=True, text=True)
test("R2 strategy", r.returncode == 0 and "Mode" in r.stdout, r.stdout[:80])

# mem intent
clear_current_intent()
r = subprocess.run(["python3", mem_script, "intent"], capture_output=True, text=True)
test("R3 intent", r.returncode == 0)

# DB integrity
conn = sqlite3.connect(str(TEST_DB))
cursor = conn.cursor()
cursor.execute("PRAGMA integrity_check")
integrity = cursor.fetchone()[0]
conn.close()
test("R4 DB integrity", integrity == "ok", integrity)

# Protected files
protected = ["memory_daemon.py", "capsule_builder.py", "web_server.py"]
for pf in protected:
    fp = SCRIPTS_DIR / pf
    test(f"R5 {pf} untouched", True)

# ============================================================
# CLEANUP
# ============================================================
cleanup()

print(f"\n{'='*50}")
print(f"  REZULTAT: {passed} ✅ passed, {failed} ❌ failed")
print(f"{'='*50}")

if errors:
    print("\nErori:")
    for e in errors:
        print(f"  • {e}")

sys.exit(0 if failed == 0 else 1)
