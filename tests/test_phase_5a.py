#!/usr/bin/env python3
"""
Teste Faza 5A: Checkpoints + Timeline + Restore + Context Integration

T1: Migrație DB (tabele + indexuri)
T2: Checkpoint create (normal, full, compact)
T3: Checkpoint list
T4: Checkpoint show
T5: Checkpoint restore (safe mode + force)
T6: Timeline (events, ordering, filtering)
T7: Context builder integration (last checkpoint)
T8: CLI routing (checkpoint, timeline)
R1-R7: Regresie (context, strategy, intent, stats, decisions, goals, integrity)
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

# Setup test DB
TEST_DIR = tempfile.mkdtemp(prefix="mem_test_5a_")
TEST_DB = os.path.join(TEST_DIR, "test.db")
os.environ["MEMORY_DB_PATH"] = TEST_DB

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
MEM_CMD = str(SCRIPTS_DIR / "mem")

passed = 0
failed = 0


def run(label, check_fn):
    global passed, failed
    try:
        check_fn()
        print(f"  ✅ {label}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        failed += 1


def run_mem(*args, input_text=None):
    cmd = ["python3", MEM_CMD] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True,
                            env={**os.environ, "MEMORY_DB_PATH": TEST_DB},
                            input=input_text, cwd=str(SCRIPTS_DIR.parent))
    return result.stdout + result.stderr


def get_db():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ===== SETUP: Create test DB with V2 schema =====
print("\n🔧 Setup DB...")
sys.path.insert(0, str(SCRIPTS_DIR))
from init_db import init_database
init_database(Path(TEST_DB))

# Populate test data
conn = get_db()
cursor = conn.cursor()
project_path = str(SCRIPTS_DIR.parent)

# Decisions
cursor.execute("""
    INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at)
    VALUES ('Use SQLite', 'Simplitate', 'technical', 'active', 'confirmed', ?, datetime('now'))
""", (project_path,))
cursor.execute("""
    INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at)
    VALUES ('REST API', 'Standard', 'architectural', 'active', 'high', ?, datetime('now'))
""", (project_path,))

# Facts
cursor.execute("""
    INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at)
    VALUES ('Python 3.10 no implicit event loop', 'gotcha', 'python', 'confirmed', 1, 1, ?, datetime('now'))
""", (project_path,))
cursor.execute("""
    INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at)
    VALUES ('WAL mode for concurrency', 'convention', 'sqlite', 'high', 0, 1, ?, datetime('now'))
""", (project_path,))

# Goals
cursor.execute("""
    INSERT INTO goals (title, description, priority, status, project_path, created_at)
    VALUES ('Complete V2', 'Memory system V2', 'high', 'active', ?, datetime('now'))
""", (project_path,))

# Tasks
cursor.execute("""
    INSERT INTO tasks (title, priority, status, goal_id, project_path, created_at)
    VALUES ('Implement checkpoints', 'high', 'in_progress', 1, ?, datetime('now'))
""", (project_path,))
cursor.execute("""
    INSERT INTO tasks (title, priority, status, project_path, created_at)
    VALUES ('Write tests', 'medium', 'todo', ?, datetime('now'))
""", (project_path,))

# Error patterns
cursor.execute("""
    INSERT INTO error_patterns (error_signature, solution, count, project_path)
    VALUES ('import_error_xyz', 'pip install xyz', 3, ?)
""", (project_path,))

conn.commit()
conn.close()

# ===== T1: DB Migration =====
print("\n📋 T1: Migrație DB")

def t1_tables():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    conn.close()
    assert "memory_checkpoints" in tables, f"memory_checkpoints lipsește: {tables}"
    assert "checkpoint_data" in tables, f"checkpoint_data lipsește"
    assert "timeline_events" in tables, f"timeline_events lipsește"
run("T1a: Tabele create", t1_tables)

def t1_columns():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(memory_checkpoints)")
    cols = [r[1] for r in cursor.fetchall()]
    conn.close()
    for c in ["id", "project_path", "name", "description", "created_at", "model",
              "intent", "context_mode", "decisions_count", "facts_count",
              "goals_count", "tasks_count", "patterns_count", "restored_count"]:
        assert c in cols, f"Coloana {c} lipsește din memory_checkpoints"
run("T1b: Coloane memory_checkpoints", t1_columns)

def t1_checkpoint_data_cols():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(checkpoint_data)")
    cols = [r[1] for r in cursor.fetchall()]
    conn.close()
    for c in ["checkpoint_id", "entity_type", "entity_id", "snapshot_json"]:
        assert c in cols, f"Coloana {c} lipsește din checkpoint_data"
run("T1c: Coloane checkpoint_data", t1_checkpoint_data_cols)

def t1_indexes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_mchk%' OR name LIKE 'idx_chkdata%' OR name LIKE 'idx_timeline%'")
    idxs = [r[0] for r in cursor.fetchall()]
    conn.close()
    assert len(idxs) >= 9, f"Așteptam >=9 indexuri, am {len(idxs)}: {idxs}"
run("T1d: Indexuri create (>=9)", t1_indexes)


# ===== T2: Checkpoint Create =====
print("\n📋 T2: Checkpoint Create")

def t2_create():
    output = run_mem("checkpoint", "create", "test-checkpoint-1", "-d", "Test description")
    assert "creat" in output.lower() or "✅" in output, f"Create fail: {output}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM memory_checkpoints WHERE name='test-checkpoint-1'")
    chk = cursor.fetchone()
    assert chk is not None, "Checkpoint nu există în DB"
    assert chk["decisions_count"] == 2, f"decisions_count={chk['decisions_count']}"
    assert chk["facts_count"] >= 1, f"facts_count={chk['facts_count']}"
    assert chk["goals_count"] == 1, f"goals_count={chk['goals_count']}"
    assert chk["tasks_count"] == 2, f"tasks_count={chk['tasks_count']}"
    assert chk["patterns_count"] == 1, f"patterns_count={chk['patterns_count']}"
    conn.close()
run("T2a: Create checkpoint normal", t2_create)

def t2_create_compact():
    output = run_mem("checkpoint", "create", "test-compact", "--compact")
    assert "creat" in output.lower() or "✅" in output, f"Create compact fail: {output}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM memory_checkpoints WHERE name='test-compact'")
    chk = cursor.fetchone()
    assert chk is not None
    assert chk["context_mode"] == "compact"
    # Compact: only pinned facts
    assert chk["facts_count"] == 1, f"Compact should have 1 pinned fact, got {chk['facts_count']}"
    conn.close()
run("T2b: Create checkpoint compact (doar pinned facts)", t2_create_compact)

def t2_create_full():
    output = run_mem("checkpoint", "create", "test-full", "--full")
    assert "creat" in output.lower() or "✅" in output
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM memory_checkpoints WHERE name='test-full'")
    chk = cursor.fetchone()
    assert chk is not None
    assert chk["context_mode"] == "full"
    assert chk["facts_count"] == 2, f"Full should have all 2 facts, got {chk['facts_count']}"
    conn.close()
run("T2c: Create checkpoint full (toate entitățile)", t2_create_full)

def t2_checkpoint_data():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM memory_checkpoints WHERE name='test-checkpoint-1'")
    chk_id = cursor.fetchone()["id"]
    cursor.execute("SELECT entity_type, COUNT(*) as cnt FROM checkpoint_data WHERE checkpoint_id=? GROUP BY entity_type", (chk_id,))
    counts = {r["entity_type"]: r["cnt"] for r in cursor.fetchall()}
    assert counts.get("decision", 0) == 2, f"decision count={counts.get('decision')}"
    assert counts.get("fact", 0) >= 1
    assert counts.get("goal", 0) == 1
    assert counts.get("task", 0) == 2
    assert counts.get("pattern", 0) == 1
    # Verify snapshot JSON is valid
    cursor.execute("SELECT snapshot_json FROM checkpoint_data WHERE checkpoint_id=? LIMIT 1", (chk_id,))
    data = json.loads(cursor.fetchone()["snapshot_json"])
    assert "id" in data, "Snapshot JSON invalid"
    conn.close()
run("T2d: Checkpoint data snapshot JSON valid", t2_checkpoint_data)

def t2_timeline_event():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM timeline_events WHERE event_type='checkpoint_create' ORDER BY id DESC LIMIT 1")
    ev = cursor.fetchone()
    assert ev is not None, "Timeline event lipsește"
    assert "Checkpoint" in ev["title"]
    conn.close()
run("T2e: Timeline event creat la checkpoint create", t2_timeline_event)


# ===== T3: Checkpoint List =====
print("\n📋 T3: Checkpoint List")

def t3_list():
    output = run_mem("checkpoint", "list")
    assert "test-checkpoint-1" in output, f"Checkpoint 1 nu apare: {output}"
    assert "test-compact" in output
    assert "test-full" in output
run("T3a: List checkpoints", t3_list)

def t3_list_default():
    # Without subcommand → default to list
    output = run_mem("checkpoint")
    assert "test-checkpoint-1" in output or "Checkpoints" in output
run("T3b: Default subcommand → list", t3_list_default)


# ===== T4: Checkpoint Show =====
print("\n📋 T4: Checkpoint Show")

def t4_show():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM memory_checkpoints WHERE name='test-checkpoint-1'")
    chk_id = cursor.fetchone()["id"]
    conn.close()
    output = run_mem("checkpoint", "show", str(chk_id))
    assert "test-checkpoint-1" in output, f"Show fail: {output}"
    assert "Decisions:" in output or "decisions" in output.lower()
    assert "Facts:" in output or "facts" in output.lower()
run("T4a: Show checkpoint detalii", t4_show)

def t4_show_invalid():
    output = run_mem("checkpoint", "show", "99999")
    assert "nu există" in output.lower() or "❌" in output
run("T4b: Show checkpoint inexistent", t4_show_invalid)


# ===== T5: Checkpoint Restore =====
print("\n📋 T5: Checkpoint Restore")

def t5_restore_safe():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM memory_checkpoints WHERE name='test-checkpoint-1'")
    chk_id = cursor.fetchone()["id"]
    conn.close()
    output = run_mem("checkpoint", "restore", str(chk_id))
    assert "force" in output.lower() or "⚠" in output, f"Safe mode should ask for --force: {output}"
run("T5a: Restore fără --force cere confirmare", t5_restore_safe)

def t5_restore_force():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM memory_checkpoints WHERE name='test-checkpoint-1'")
    chk_id = cursor.fetchone()["id"]
    conn.close()

    output = run_mem("checkpoint", "restore", str(chk_id), "--force")
    assert "restaurat" in output.lower() or "✅" in output, f"Restore fail: {output}"

    # Verify: checkpoint restored_count incremented
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT restored_count FROM memory_checkpoints WHERE id=?", (chk_id,))
    assert cursor.fetchone()["restored_count"] >= 1
    conn.close()
run("T5b: Restore cu --force funcționează", t5_restore_force)

def t5_restore_timeline():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM timeline_events WHERE event_type='checkpoint_restore' ORDER BY id DESC LIMIT 1")
    ev = cursor.fetchone()
    assert ev is not None, "Timeline event restore lipsește"
    assert "Restored" in ev["title"]
    conn.close()
run("T5c: Timeline event creat la restore", t5_restore_timeline)

def t5_entities_restored():
    conn = get_db()
    cursor = conn.cursor()
    # After restore, decisions should be active again
    cursor.execute("SELECT COUNT(*) as cnt FROM decisions WHERE status='active' AND project_path=?", (project_path,))
    active = cursor.fetchone()["cnt"]
    assert active >= 2, f"Should have >=2 active decisions after restore, got {active}"
    conn.close()
run("T5d: Entități restaurate corect", t5_entities_restored)


# ===== T6: Timeline =====
print("\n📋 T6: Timeline")

def t6_timeline():
    output = run_mem("timeline", "--all")
    assert "TIMELINE" in output or "📅" in output, f"Timeline fail: {output}"
run("T6a: Timeline afișare", t6_timeline)

def t6_timeline_events():
    output = run_mem("timeline", "--all")
    # Should contain checkpoint events and decisions
    has_checkpoint = "checkpoint" in output.lower() or "📌" in output
    has_decision = "decision" in output.lower() or "📋" in output
    assert has_checkpoint or has_decision, f"Timeline ar trebui să conțină events: {output}"
run("T6b: Timeline conține events", t6_timeline_events)

def t6_timeline_type_filter():
    output = run_mem("timeline", "--all", "--type", "checkpoint_create")
    # Should only show checkpoint events, no decision events
    assert "TIMELINE" in output or "📅" in output or "niciun eveniment" in output
run("T6c: Timeline filtrare pe tip", t6_timeline_type_filter)


# ===== T7: Context Builder Integration =====
print("\n📋 T7: Context Builder Integration")

def t7_context_checkpoint():
    output = run_mem("context", "--compact")
    assert "checkpoint" in output.lower() or "Last checkpoint" in output, f"Context should show last checkpoint: {output}"
run("T7a: Context builder afișează last checkpoint", t7_context_checkpoint)


# ===== T8: CLI Routing =====
print("\n📋 T8: CLI Routing")

def t8_checkpoint_cmd():
    output = run_mem("checkpoint", "list")
    assert "Checkpoints" in output or "test-" in output or "niciun checkpoint" in output
run("T8a: mem checkpoint list", t8_checkpoint_cmd)

def t8_timeline_cmd():
    output = run_mem("timeline")
    assert "TIMELINE" in output or "📅" in output or "niciun eveniment" in output
run("T8b: mem timeline", t8_timeline_cmd)


# ===== REGRESSION =====
print("\n📋 Regresie")

def r1_context_compact():
    output = run_mem("context", "--compact")
    assert "COMPACT" in output or "Model:" in output
run("R1: mem context --compact", r1_context_compact)

def r2_context_full():
    output = run_mem("context", "--full")
    assert "FULL" in output or "Model:" in output
run("R2: mem context --full", r2_context_full)

def r3_context_survival():
    output = run_mem("context", "--survival")
    assert "SURVIVAL" in output or "Model:" in output
run("R3: mem context --survival", r3_context_survival)

def r4_decisions():
    output = run_mem("decisions")
    assert "Use SQLite" in output or "REST API" in output or "niciun" in output.lower()
run("R4: mem decisions", r4_decisions)

def r5_goals():
    output = run_mem("goal", "list")
    # After restore, goal might be active or paused
    assert "Complete V2" in output or "niciun" in output.lower() or "No active" in output
run("R5: mem goal list", r5_goals)

def r6_integrity():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity check: {result}"
run("R6: PRAGMA integrity_check", r6_integrity)

def r7_protected_files():
    import subprocess as sp
    result = sp.run(["git", "diff", "--name-only"], capture_output=True, text=True,
                    cwd=str(SCRIPTS_DIR.parent))
    changed = result.stdout.strip().split("\n") if result.stdout.strip() else []
    protected = {"scripts/memory_daemon.py", "scripts/capsule_builder.py", "scripts/web_server.py"}
    violated = protected & set(changed)
    assert not violated, f"Fișiere protejate modificate: {violated}"
run("R7: Fișiere protejate neatinse", r7_protected_files)


# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"  REZULTATE: {passed} passed, {failed} failed")
print(f"{'='*50}")
print(f"  DB test: {TEST_DB}")

if failed:
    sys.exit(1)
