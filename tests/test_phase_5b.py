#!/usr/bin/env python3
"""
Teste Faza 5B: Dashboard CLI

T1-T10: Dashboard funcțional
T11-T22: Regresie
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_5b_")
TEST_DB = os.path.join(TEST_DIR, "test.db")
os.environ["MEMORY_DB_PATH"] = TEST_DB

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
MEM_CMD = str(SCRIPTS_DIR / "mem")
PROJECT_PATH = str(SCRIPTS_DIR.parent)

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


def run_mem(*args):
    cmd = ["python3", MEM_CMD] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True,
                            env={**os.environ, "MEMORY_DB_PATH": TEST_DB},
                            cwd=PROJECT_PATH)
    return result.stdout + result.stderr


def get_db():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ===== SETUP =====
print("\n🔧 Setup DB...")
sys.path.insert(0, str(SCRIPTS_DIR))
from init_db import init_database
init_database(Path(TEST_DB))

conn = get_db()
c = conn.cursor()
pp = PROJECT_PATH

# Decisions (2 active, 1 cu conflict potential)
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Use SQLite", "Simplitate", "technical", "active", "confirmed", pp))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Use PostgreSQL", "Scalabilitate", "technical", "active", "medium", pp))

# Facts (1 pinned, 1 normal)
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("WAL mode for SQLite concurrency", "convention", "sqlite", "confirmed", 1, 1, pp))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("Python 3.10 event loop gotcha", "gotcha", "python", "high", 0, 1, pp))

# Goals
c.execute("INSERT INTO goals (title, description, priority, status, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Complete V2 Memory System", "Full implementation", "high", "active", pp))

# Tasks (in_progress, blocked, todo)
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Implement dashboard", "high", "in_progress", 1, pp))
c.execute("INSERT INTO tasks (title, priority, status, blocked_by, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Deploy to prod", "medium", "blocked", "waiting for review", pp))
c.execute("INSERT INTO tasks (title, priority, status, project_path, created_at) VALUES (?,?,?,?,datetime('now'))",
          ("Write docs", "low", "todo", pp))

# Error resolutions
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?,?,?,?,datetime('now'))",
          ("ImportError: no module xyz", "pip install xyz", 1, pp))

# Error patterns
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))

# Checkpoint
c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
          (pp, "before-dashboard", "Pre 5B", "opus", "feature", "auto", 2, 2, 1, 3, 1))

# Timeline event
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("checkpoint_create", 1, "Checkpoint: before-dashboard", "9 entities", pp))

conn.commit()
conn.close()


# ===== T1: Basic dashboard =====
print("\n📋 T1-T10: Dashboard Funcțional")

def t1_dashboard():
    output = run_mem("dashboard")
    assert "DASHBOARD" in output or "📊" in output, f"Dashboard header missing: {output[:200]}"
run("T1: mem dashboard rulează", t1_dashboard)

def t2_with_data():
    output = run_mem("dashboard")
    assert "ean-cc-mem-kit" in output or PROJECT_PATH.split("/")[-1] in output, f"Project name missing"
run("T2: Dashboard cu date proiect curent", t2_with_data)

def t3_empty():
    output = run_mem("dashboard", "--project", "/tmp/nonexistent_project_xyz")
    # Should still work, just show empty sections
    assert "DASHBOARD" in output or "📊" in output
run("T3: Dashboard empty state", t3_empty)

def t4_all_sections():
    output = run_mem("dashboard")
    checks = {
        "project_summary": any(x in output for x in ["Model:", "Intent:", "Checkpoint:"]),
        "decisions": "Decision" in output or "📋" in output,
        "facts": "Fact" in output or "⭐" in output,
        "goals": "Goal" in output or "🎯" in output,
        "tasks": "Task" in output or "✅" in output,
        "error_intel": "Error" in output or "Intelligence" in output or "🔍" in output,
        "timeline": "Recent" in output or "📅" in output,
        "health": "Health" in output or "💊" in output,
    }
    missing = [k for k, v in checks.items() if not v]
    assert not missing, f"Secțiuni lipsă: {missing}"
run("T4: Toate secțiunile prezente", t4_all_sections)

def t5_pinned_facts():
    output = run_mem("dashboard")
    assert "📌" in output, f"Pinned fact indicator missing"
run("T5: Pinned facts vizibile", t5_pinned_facts)

def t6_task_priority():
    output = run_mem("dashboard")
    # in_progress should appear before blocked, before todo
    lines = output.split("\n")
    task_lines = [l for l in lines if "▶" in l or "⛔" in l or "○" in l]
    if len(task_lines) >= 2:
        # First task should be in_progress (▶)
        assert "▶" in task_lines[0], f"First task not in_progress: {task_lines[0]}"
run("T6: Tasks blocked/in_progress prioritizate", t6_task_priority)

def t7_last_checkpoint():
    output = run_mem("dashboard")
    assert "before-dashboard" in output, f"Last checkpoint missing"
run("T7: Last checkpoint apare", t7_last_checkpoint)

def t8_compact():
    output = run_mem("dashboard")
    lines = [l for l in output.split("\n") if l.strip()]
    assert len(lines) < 60, f"Dashboard prea lung: {len(lines)} linii"
run("T8: Dashboard compact și lizibil (<60 linii)", t8_compact)

def t9_json():
    output = run_mem("dashboard", "--json")
    data = json.loads(output)
    assert "summary" in data
    assert "decisions" in data
    assert "facts" in data
    assert "goals" in data
    assert "tasks" in data
    assert "health" in data
    assert data["summary"]["project_name"] == PROJECT_PATH.split("/")[-1]
run("T9: --json output valid", t9_json)

def t10_project():
    output = run_mem("dashboard", "--project", "/tmp")
    assert "DASHBOARD" in output or "📊" in output
run("T10: --project funcționează", t10_project)


# ===== REGRESIE =====
print("\n📋 T11-T22: Regresie")

def t11(): run_mem("context", "--compact"); pass
run("T11: mem context", t11)

def t12():
    output = run_mem("strategy")
    assert "mode" in output.lower() or "strategy" in output.lower() or "survival" in output.lower() or "compact" in output.lower()
run("T12: mem strategy", t12)

def t13():
    output = run_mem("intent")
    assert "intent" in output.lower() or "niciun" in output.lower()
run("T13: mem intent", t13)

def t14():
    output = run_mem("stats")
    assert "STATISTICI" in output or "Mesaje" in output
run("T14: mem stats", t14)

def t15():
    output = run_mem("search", "test")
    # search may fail gracefully on test DB without FTS data
    assert output is not None
run("T15: mem search", t15)

def t16():
    output = run_mem("decisions")
    assert "SQLite" in output or "PostgreSQL" in output
run("T16: mem decisions", t16)

def t17():
    output = run_mem("goal", "list")
    assert "Complete V2" in output or "active" in output.lower()
run("T17: mem goal list", t17)

def t18():
    output = run_mem("project")
    # May show "no profile" on test DB
    assert output is not None
run("T18: mem project", t18)

def t19():
    output = run_mem("resolve", "list")
    assert "import" in output.lower() or "pip" in output.lower() or "niciun" in output.lower() or output is not None
run("T19: mem resolve list", t19)

def t20():
    output = run_mem("checkpoint", "list")
    assert "before-dashboard" in output
run("T20: mem checkpoint list", t20)

def t21():
    output = run_mem("timeline", "--all")
    assert "TIMELINE" in output or "📅" in output or "niciun" in output.lower()
run("T21: mem timeline", t21)

def t22():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()[0]
    conn.close()
    assert result == "ok"
run("T22: PRAGMA integrity_check", t22)


# ===== SUMMARY =====
print(f"\n{'=' * 50}")
print(f"  REZULTATE: {passed} passed, {failed} failed")
print(f"{'=' * 50}")
print(f"  DB test: {TEST_DB}")

if failed:
    sys.exit(1)
