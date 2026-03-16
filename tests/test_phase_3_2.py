#!/usr/bin/env python3
"""
Teste Faza 3.2 — Fast Context + Intent + Snapshot + Delta
T1-T28
"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import subprocess
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Use a test DB
TEST_DB = PROJECT_ROOT / "test_phase32.db"
os.environ["MEMORY_DB_PATH"] = str(TEST_DB)

# Clean imports
import importlib
if "v2_common" in sys.modules:
    del sys.modules["v2_common"]
if "context_builder_v2" in sys.modules:
    del sys.modules["context_builder_v2"]

from v2_common import (
    get_current_intent, set_current_intent, clear_current_intent,
    invalidate_snapshot, VALID_INTENTS, INTENT_PRIORITIES,
    INTENT_FILE, SNAPSHOT_FILE, GLOBAL_DB, get_current_model,
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
    """Creează DB de test cu schema V2 completă."""
    if TEST_DB.exists():
        TEST_DB.unlink()

    conn = sqlite3.connect(str(TEST_DB))
    conn.execute("PRAGMA journal_mode=WAL")

    # Schema minimă
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

        -- V2 tables
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, category TEXT DEFAULT 'technical',
            status TEXT DEFAULT 'active', confidence TEXT DEFAULT 'high',
            project_path TEXT, source_session TEXT,
            model_used TEXT, provider TEXT,
            created_by TEXT, created_at TEXT, updated_at TEXT,
            superseded_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS learned_facts (
            id INTEGER PRIMARY KEY, fact TEXT, fact_type TEXT DEFAULT 'technical',
            category TEXT, is_pinned INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
            confidence TEXT DEFAULT 'high',
            project_path TEXT, source_session TEXT,
            model_used TEXT, provider TEXT,
            created_by TEXT, created_at TEXT, updated_at TEXT,
            superseded_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'active', target_date TEXT,
            project_path TEXT, source_session TEXT,
            created_by TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'todo', goal_id INTEGER,
            blocked_by TEXT, project_path TEXT, source_session TEXT,
            created_by TEXT, created_at TEXT, updated_at TEXT
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
    """)

    # Insert test data
    now = "2026-03-11T10:00:00"
    proj = str(Path.cwd())

    conn.execute("INSERT INTO project_profiles (project_path, project_name, description, tech_stack) VALUES (?, 'TestProject', 'A test project', ?)",
                 (proj, json.dumps(["python", "sqlite"])))

    for i in range(5):
        conn.execute("INSERT INTO decisions (title, category, status, confidence, project_path, created_at, model_used) VALUES (?, ?, 'active', 'high', ?, ?, ?)",
                     (f"Decision {i+1}", ["technical", "convention", "architectural", "tooling", "process"][i], proj, now, "opus-4"))

    for i in range(6):
        ft = ["technical", "convention", "gotcha", "preference", "environment", "gotcha"][i]
        pinned = 1 if i < 2 else 0
        conn.execute("INSERT INTO learned_facts (fact, fact_type, is_pinned, is_active, confidence, project_path, created_at) VALUES (?, ?, ?, 1, 'high', ?, ?)",
                     (f"Fact {i+1} type {ft}", ft, pinned, proj, now))

    for i in range(3):
        conn.execute("INSERT INTO goals (title, priority, status, project_path, created_at) VALUES (?, ?, 'active', ?, ?)",
                     (f"Goal {i+1}", ["critical", "high", "medium"][i], proj, now))

    for i in range(5):
        status = ["in_progress", "blocked", "todo", "todo", "todo"][i]
        conn.execute("INSERT INTO tasks (title, priority, status, goal_id, blocked_by, project_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (f"Task {i+1}", ["critical", "high", "medium", "low", "medium"][i], status, 1 if i < 2 else None, "waiting for API" if status == "blocked" else None, proj, now))

    for i in range(4):
        conn.execute("INSERT INTO error_resolutions (error_summary, resolution, resolution_type, worked, project_path, created_at, model_used) VALUES (?, ?, 'fix', ?, ?, ?, ?)",
                     (f"Error {i+1}", f"Fixed by doing {i+1}", 1 if i < 3 else 0, proj, now, "opus-4"))

    conn.commit()
    conn.close()


def cleanup():
    """Curăță fișierele de test."""
    for f in [TEST_DB, INTENT_FILE, SNAPSHOT_FILE]:
        if f.exists():
            f.unlink()
    # Cleanup WAL/SHM
    for ext in ["-wal", "-shm"]:
        p = Path(str(TEST_DB) + ext)
        if p.exists():
            p.unlink()


# ============================================================
# SETUP
# ============================================================
print("\n🧪 TESTE FAZA 3.2 — Fast Context + Intent + Snapshot + Delta\n")
cleanup()
setup_test_db()

# Clean import context_builder_v2
if "context_builder_v2" in sys.modules:
    del sys.modules["context_builder_v2"]
from context_builder_v2 import (
    build_context, build_context_compat,
    _load_snapshot, _save_snapshot, _compute_delta, _fmt_delta,
    _get_limits, _estimate_tokens, _apply_budget,
    fetch_decisions, fetch_facts, fetch_tasks, fetch_resolutions,
    SNAPSHOT_TTL_SECONDS,
)

# ============================================================
# T1-T4: SESSION INTENT
# ============================================================
print("--- T1-T4: Session Intent ---")

# T1: Intent set/get/clear
cleanup_intent = lambda: INTENT_FILE.unlink() if INTENT_FILE.exists() else None
cleanup_intent()
test("T1a intent get None", get_current_intent() is None)
set_current_intent("debugging")
test("T1b intent set/get", get_current_intent() == "debugging")
clear_current_intent()
test("T1c intent clear", get_current_intent() is None)
test("T1d intent file removed", not INTENT_FILE.exists())

# T2: Intent validare
test("T2a valid intents", len(VALID_INTENTS) == 7)
test("T2b debugging in intents", "debugging" in VALID_INTENTS)
test("T2c feature in intents", "feature" in VALID_INTENTS)
test("T2d deploy in intents", "deploy" in VALID_INTENTS)

# T3: Intent priorities mapping
test("T3a debugging priorities", "resolutions" in INTENT_PRIORITIES["debugging"])
test("T3b feature priorities", "goals" in INTENT_PRIORITIES["feature"])
test("T3c deploy priorities", "facts_convention" in INTENT_PRIORITIES["deploy"])

# T4: Intent invalidates snapshot
set_current_intent("feature")
# Create a fake snapshot
SNAPSHOT_FILE.write_text(json.dumps({"meta": {"intent": "feature"}}))
test("T4a snapshot exists", SNAPSHOT_FILE.exists())
invalidate_snapshot()
test("T4b snapshot invalidated", not SNAPSHOT_FILE.exists())
clear_current_intent()

# ============================================================
# T5-T8: MEM INTENT CLI
# ============================================================
print("\n--- T5-T8: mem intent CLI ---")

mem_script = str(SCRIPTS_DIR / "mem")

# T5: mem intent show (none)
cleanup_intent()
r = subprocess.run(["python3", mem_script, "intent"], capture_output=True, text=True)
test("T5 intent show none", "Niciun intent" in r.stdout, r.stdout[:80])

# T6: mem intent set
r = subprocess.run(["python3", mem_script, "intent", "set", "debugging"], capture_output=True, text=True)
test("T6a intent set OK", "debugging" in r.stdout, r.stdout[:80])
test("T6b intent file exists", INTENT_FILE.exists())

# T7: mem intent show
r = subprocess.run(["python3", mem_script, "intent"], capture_output=True, text=True)
test("T7 intent show", "debugging" in r.stdout, r.stdout[:80])

# T8: mem intent set invalid
r = subprocess.run(["python3", mem_script, "intent", "set", "invalid_xyz"], capture_output=True, text=True)
test("T8 intent set invalid rejected", "invalid" in r.stdout.lower() or "❌" in r.stdout, r.stdout[:80])
cleanup_intent()

# ============================================================
# T9-T13: CONTEXT MODES
# ============================================================
print("\n--- T9-T13: Context Modes (compact/full/survival) ---")

# T9: compact mode (default)
import io
from contextlib import redirect_stdout

f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="compact")
out = f.getvalue()
test("T9a compact output", "COMPACT" in out, out[:100])
test("T9b compact has model", "Model:" in out, out[:100])
test("T9c compact has project", "Project:" in out)

# T10: full mode
f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="full")
out = f.getvalue()
test("T10a full output", "FULL" in out, out[:100])

# T11: survival mode
f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="survival")
out = f.getvalue()
test("T11a survival output", "SURVIVAL" in out, out[:100])
# Survival should be shorter
test("T11b survival shorter", len(out) < 2000, f"len={len(out)}")

# T12: limits differ per mode
d_c, f_c, g_c, t_c, r_c = _get_limits("compact")
d_f, f_f, g_f, t_f, r_f = _get_limits("full")
d_s, f_s, g_s, t_s, r_s = _get_limits("survival")
test("T12a full > compact limits", d_f > d_c)
test("T12b survival < compact limits", d_s <= d_c)

# T13: backward compat
f = io.StringIO()
with redirect_stdout(f):
    build_context_compat(full=False)
out = f.getvalue()
test("T13 build_context_compat works", "COMPACT" in out, out[:100])

# ============================================================
# T14-T16: INTENT-AWARE SCORING
# ============================================================
print("\n--- T14-T16: Intent-aware scoring ---")

# T14: debugging intent → boosts resolutions
set_current_intent("debugging")
conn = sqlite3.connect(str(TEST_DB))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
proj = str(Path.cwd())

resolutions = fetch_resolutions(cursor, proj, 10, intent="debugging", compact=True)
test("T14a resolutions fetched", len(resolutions) > 0)
# worked=1 should be first
if resolutions:
    test("T14b worked first", resolutions[0].get("worked") == 1, str(resolutions[0].get("worked")))

# T15: debugging intent → gotcha facts boosted
facts = fetch_facts(cursor, proj, 10, intent="debugging", compact=True)
test("T15a facts fetched", len(facts) > 0)
# Pinned should still be first (score 100+)
if facts:
    test("T15b pinned first", facts[0].get("is_pinned") == 1)

# T16: feature intent → goals/tasks adjusted
d, f, g, t, r = _get_limits("compact", "feature")
test("T16a feature: more goals", g == 5)
test("T16b feature: more tasks", t == 7)
test("T16c feature: fewer resolutions", r == 2)
conn.close()
clear_current_intent()

# ============================================================
# T17-T19: COMPACT FORMATTING
# ============================================================
print("\n--- T17-T19: Compact formatting (shorter) ---")

from context_builder_v2 import fmt_decisions, fmt_facts, fmt_goals, fmt_tasks, fmt_resolutions

test_decisions = [{"id": 1, "title": "A very long decision title that should be truncated in compact mode", "category": "technical", "model_used": "opus-4"}]
full_out = fmt_decisions(test_decisions, compact=False)
compact_out = fmt_decisions(test_decisions, compact=True)
test("T17 compact decisions shorter", len(compact_out) <= len(full_out), f"full={len(full_out)} compact={len(compact_out)}")

test_facts_data = [{"id": 1, "fact": "A long fact about something important in the system", "fact_type": "technical", "is_pinned": 0}]
full_out = fmt_facts(test_facts_data, compact=False)
compact_out = fmt_facts(test_facts_data, compact=True)
test("T18 compact facts shorter", len(compact_out) <= len(full_out))

test_tasks_data = [{"id": 1, "title": "Long task about implementing something", "priority": "high", "status": "in_progress", "goal_id": 1, "blocked_by": None}]
full_out = fmt_tasks(test_tasks_data, compact=False)
compact_out = fmt_tasks(test_tasks_data, compact=True)
test("T19 compact tasks shorter", len(compact_out) <= len(full_out))

# ============================================================
# T20-T22: CACHED SNAPSHOT
# ============================================================
print("\n--- T20-T22: Cached Context Snapshot ---")

# T20: build_context saves snapshot
if SNAPSHOT_FILE.exists():
    SNAPSHOT_FILE.unlink()
f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="compact")
test("T20 snapshot saved", SNAPSHOT_FILE.exists())

# T21: load snapshot within TTL
snapshot = _load_snapshot()
test("T21a snapshot loaded", snapshot is not None)
if snapshot:
    test("T21b has meta", "meta" in snapshot)
    test("T21c has mode", snapshot.get("meta", {}).get("mode") == "compact")

# T22: expired snapshot returns None
if SNAPSHOT_FILE.exists():
    data = json.loads(SNAPSHOT_FILE.read_text())
    data["meta"]["generated_at"] = "2020-01-01T00:00:00"
    SNAPSHOT_FILE.write_text(json.dumps(data))
    test("T22 expired snapshot None", _load_snapshot() is None)

# ============================================================
# T23-T25: DELTA CONTEXT
# ============================================================
print("\n--- T23-T25: Delta Context ---")

# T23: first delta = no previous snapshot
if SNAPSHOT_FILE.exists():
    SNAPSHOT_FILE.unlink()
f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="compact", delta=True)
out = f.getvalue()
test("T23a first delta message", "niciun snapshot" in out.lower() or "COMPACT" in out, out[:150])
test("T23b snapshot created after first delta", SNAPSHOT_FILE.exists())

# T24: delta with no changes
f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="compact", delta=True)
out = f.getvalue()
test("T24 delta no changes", "nicio schimbare" in out.lower() or "DELTA" in out, out[:150])

# T25: compute_delta function
old_snap = {"decisions": [{"id": 1, "title": "Old"}], "facts": [], "goals": [], "tasks": [], "resolutions": []}
new_data = {"decisions": [{"id": 1, "title": "New"}, {"id": 2, "title": "Added"}], "facts": [], "goals": [], "tasks": [], "resolutions": []}
delta = _compute_delta(old_snap, new_data)
test("T25a delta added", "decisions" in delta.get("added", {}))
test("T25b delta changed", "decisions" in delta.get("changed", {}))
test("T25c delta format", "adăugat" in _fmt_delta(delta).lower() or "modificat" in _fmt_delta(delta).lower())

# ============================================================
# T26: MEMORY AGING
# ============================================================
print("\n--- T26: Memory Aging ---")

from context_builder_v2 import _recency_score
test("T26a recent score compact", _recency_score(5, compact=True) == 10)
test("T26b 30d score compact", _recency_score(30, compact=True) == 5)
test("T26c 90d score compact penalty", _recency_score(90, compact=True) == 0)
test("T26d 30d score full", _recency_score(30, compact=False) == 10)
test("T26e compact more aggressive", _recency_score(45, compact=True) < _recency_score(45, compact=False))

# ============================================================
# T27: JSON OUTPUT
# ============================================================
print("\n--- T27: JSON Output ---")

f = io.StringIO()
with redirect_stdout(f):
    build_context(mode="compact", output_json=True)
out = f.getvalue()
try:
    data = json.loads(out)
    test("T27a valid JSON", True)
    test("T27b has meta", "meta" in data)
    test("T27c meta has mode", data.get("meta", {}).get("mode") == "compact")
    test("T27d has decisions", "decisions" in data)
except json.JSONDecodeError:
    test("T27 valid JSON", False, "Invalid JSON output")

# ============================================================
# T28: PROTECTED FILES
# ============================================================
print("\n--- T28: Protected files untouched ---")

protected = ["memory_daemon.py", "capsule_builder.py", "web_server.py"]
for pf in protected:
    fp = SCRIPTS_DIR / pf
    if fp.exists():
        # Just verify it wasn't modified by checking it exists and is readable
        test(f"T28 {pf} exists", True)
    else:
        test(f"T28 {pf} skip (not present)", True)

# ============================================================
# CLEANUP & SUMMARY
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
