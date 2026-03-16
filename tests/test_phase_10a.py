#!/usr/bin/env python3
"""
Teste Faza 10A: Branch Compare + Replay

T1-T5:   Compare/Diff structured output
T6-T9:   Replay
T10-T12: API endpoints
T13-T15: Edge cases
T16-T23: Regresie
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
import threading
from pathlib import Path
from datetime import datetime

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_10a_")
TEST_DB = os.path.join(TEST_DIR, "test.db")
os.environ["MEMORY_DB_PATH"] = TEST_DB

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
WEB_DIR = Path(__file__).parent.parent / "web"
MEM_CMD = str(SCRIPTS_DIR / "mem")
PROJECT_PATH = str(SCRIPTS_DIR.parent)

passed = 0
failed = 0


def run(label, check_fn):
    global passed, failed
    try:
        check_fn()
        print(f"  \u2705 {label}")
        passed += 1
    except Exception as e:
        print(f"  \u274C {label}: {e}")
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
print("\n\U0001f527 Setup DB...")
sys.path.insert(0, str(SCRIPTS_DIR))
from init_db import init_database
init_database(Path(TEST_DB))

# Populate test data
conn = get_db()
c = conn.cursor()
pp = PROJECT_PATH

# Main branch entities
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Use SQLite", "Simplitate", "technical", "active", "confirmed", pp, "main"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("REST not GraphQL", "Simplitate", "architectural", "active", "high", pp, "main"))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, branch) VALUES (?,?,?,?,?,?,?,?)",
          ("WAL mode required", "convention", "sqlite", "confirmed", 1, 1, pp, "main"))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, branch) VALUES (?,?,?,?,?,?)",
          ("Complete V2", "Full impl", "high", "active", pp, "main"))
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, branch) VALUES (?,?,?,?,?,?)",
          ("Build API", "high", "in_progress", 1, pp, "main"))
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, branch) VALUES (?,?,?,?,?)",
          ("ImportError xyz", "pip install xyz", 1, pp, "main"))

# Feature branch
c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
          ("feature-x", pp, "main", "Feature X"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Use Redis", "Cache layer", "technical", "active", "high", pp, "feature-x"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Redis cluster mode", "HA setup", "architectural", "active", "medium", pp, "feature-x"))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, branch) VALUES (?,?,?,?,?,?,?,?)",
          ("Redis needs port 6379", "technical", "infra", "high", 0, 1, pp, "feature-x"))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, branch) VALUES (?,?,?,?,?,?)",
          ("Add caching", "Redis caching layer", "medium", "active", pp, "feature-x"))
c.execute("INSERT INTO tasks (title, priority, status, project_path, branch) VALUES (?,?,?,?,?)",
          ("Setup Redis", "high", "todo", pp, "feature-x"))
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, branch) VALUES (?,?,?,?,?)",
          ("Redis connection refused", "Start redis-server", 1, pp, "feature-x"))

# Conflict: same title on both branches
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Shared config", "Main version", "convention", "active", "high", pp, "main"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Shared config", "Feature version", "convention", "active", "high", pp, "feature-x"))

# Empty branch
c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
          ("empty-branch", pp, "main", "Empty for testing"))

# Merge log
c.execute("INSERT INTO branch_merge_log (source_branch, target_branch, project_path, strategy, entities_merged, conflicts_found) VALUES (?,?,?,?,?,?)",
          ("old-branch", "main", pp, "merge", 3, 0))

# Timeline + Checkpoints
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))
c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (pp, "pre-test", "Before test", "opus", "feature", "auto", 2, 1, 1, 1, 1))
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path) VALUES (?,?,?,?,?)",
          ("checkpoint_create", 1, "Checkpoint: pre-test", "5 entities", pp))

conn.commit()
conn.close()


# ===== Setup Flask =====
print("\n\U0001f310 Setup Flask...")

from flask import Flask
app = Flask(__name__)
app.config["TESTING"] = True

from dashboard_api import dashboard_bp
from universal_api import universal_bp
app.register_blueprint(dashboard_bp)
app.register_blueprint(universal_bp)

from werkzeug.serving import make_server
server = make_server("127.0.0.1", 19880, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

BASE_URL = "http://127.0.0.1:19880"

from clients.universal_memory_client import UniversalMemoryClient
client = UniversalMemoryClient(base_url=BASE_URL, project_path=pp,
                                cli_name="test-10a", agent_name="tester",
                                provider="test", model_name="test")


# ===== T1-T5: Compare/Diff =====
print("\n\U0001f4cb T1-T5: Compare/Diff structured output")

def t1_diff_structured():
    output = run_mem("branch", "diff", "main", "feature-x")
    assert "main" in output and "feature-x" in output, f"Missing branches: {output}"
    assert "decisions" in output.lower() or "DIFF" in output, f"No structured output: {output}"
    assert "Summary" in output, f"No summary: {output}"
run("T1: mem branch diff main feature-x (structured)", t1_diff_structured)

def t2_compare_decisions():
    output = run_mem("branch", "compare", "main", "feature-x")
    assert "DECISIONS" in output, f"No DECISIONS section: {output}"
    assert "Use SQLite" in output or "Use Redis" in output, f"Missing decision titles: {output}"
    assert "Only in" in output or "only in" in output.lower(), f"No 'Only in' labels: {output}"
run("T2: compare decisions differences", t2_compare_decisions)

def t3_compare_facts():
    output = run_mem("branch", "compare", "main", "feature-x")
    assert "FACTS" in output, f"No FACTS section: {output}"
run("T3: compare facts differences", t3_compare_facts)

def t4_compare_goals_tasks():
    output = run_mem("branch", "compare", "main", "feature-x")
    assert "GOALS" in output or "TASKS" in output, f"No GOALS/TASKS section: {output}"
run("T4: compare goals/tasks differences", t4_compare_goals_tasks)

def t5_compare_resolutions():
    output = run_mem("branch", "compare", "main", "feature-x")
    assert "RESOLUTIONS" in output, f"No RESOLUTIONS section: {output}"
run("T5: compare resolutions differences", t5_compare_resolutions)


# ===== T6-T9: Replay =====
print("\n\U0001f4cb T6-T9: Replay")

def t6_replay_main():
    output = run_mem("branch", "replay", "main")
    assert "REPLAY" in output and "main" in output, f"No REPLAY header: {output}"
    assert "Decision" in output or "Fact" in output or "Goal" in output, \
        f"No events in replay: {output}"
run("T6: mem branch replay main", t6_replay_main)

def t7_replay_feature():
    output = run_mem("branch", "replay", "feature-x")
    assert "feature-x" in output, f"No branch name: {output}"
    assert "Redis" in output, f"No Redis entities in feature-x replay: {output}"
run("T7: mem branch replay feature-x", t7_replay_feature)

def t8_replay_limit():
    output = run_mem("branch", "replay", "main", "--limit", "2")
    # Should have limited output
    assert "REPLAY" in output, f"No REPLAY header: {output}"
run("T8: replay --limit", t8_replay_limit)

def t9_timeline_branch():
    output = run_mem("timeline", "--branch", "main")
    # Should show timeline filtered to main
    assert len(output) > 5, f"Empty timeline: {output}"
run("T9: mem timeline --branch main", t9_timeline_branch)


# ===== T10-T12: API =====
print("\n\U0001f4cb T10-T12: API endpoints")

def t10_api_branches():
    r = client._get("/api/branches", {"project": pp})
    assert "branches" in r, f"No branches key: {r}"
    branches = r["branches"]
    names = [b["name"] for b in branches]
    assert "main" in names, f"main missing: {names}"
    assert "feature-x" in names, f"feature-x missing: {names}"
    assert "current" in r, f"No current field: {r}"
    # Check entity counts
    for b in branches:
        assert "entity_count" in b, f"No entity_count: {b}"
run("T10: GET /api/branches", t10_api_branches)

def t11_api_compare():
    r = client._get("/api/branches/compare", {"project": pp, "a": "main", "b": "feature-x"})
    assert "summary" in r, f"No summary: {r}"
    assert "only_a" in r, f"No only_a: {r}"
    assert "only_b" in r, f"No only_b: {r}"
    assert "conflicts" in r, f"No conflicts: {r}"
    s = r["summary"]
    assert s["branch_a"] == "main", f"Wrong branch_a: {s}"
    assert s["branch_b"] == "feature-x", f"Wrong branch_b: {s}"
    assert s["only_in_a"] > 0, f"Expected entities in a: {s}"
    assert s["only_in_b"] > 0, f"Expected entities in b: {s}"
    assert s["conflicts"] > 0, f"Expected conflicts (Shared config): {s}"
run("T11: GET /api/branches/compare", t11_api_compare)

def t12_api_replay():
    r = client._get("/api/branches/replay", {"project": pp, "branch": "feature-x"})
    assert "events" in r, f"No events: {r}"
    assert "branch" in r and r["branch"] == "feature-x", f"Wrong branch: {r}"
    assert len(r["events"]) > 0, f"No events: {r}"
    # Check event structure
    ev = r["events"][0]
    assert "date" in ev and "type" in ev and "title" in ev, f"Bad event structure: {ev}"
run("T12: GET /api/branches/replay", t12_api_replay)


# ===== T13-T15: Edge cases =====
print("\n\U0001f4cb T13-T15: Edge cases")

def t13_compare_nonexistent():
    r = client._get("/api/branches/compare", {"project": pp, "a": "main", "b": "nonexistent"})
    assert "error" in r, f"Expected error for nonexistent branch: {r}"
run("T13: compare branch inexistent → eroare curată", t13_compare_nonexistent)

def t14_replay_empty():
    output = run_mem("branch", "replay", "empty-branch")
    assert "niciun" in output.lower() or "empty" in output.lower() or "(nici" in output, \
        f"Expected empty state: {output}"
run("T14: replay branch gol → empty state", t14_replay_empty)

def t15_compare_identical():
    # Compare main with itself
    output = run_mem("branch", "diff", "main", "main")
    assert "identice" in output.lower() or "nicio diferență" in output.lower() or "identical" in output.lower(), \
        f"Expected identical message: {output}"
run("T15: compare identice → output clar", t15_compare_identical)


# ===== T16-T23: Regresie =====
print("\n\U0001f4cb T16-T23: Regresie")

def t16_branch_create():
    output = run_mem("branch", "create", "regression-test", "-d", "Regression")
    assert "creat" in output.lower() or "✅" in output, f"Create failed: {output}"
run("T16: mem branch create", t16_branch_create)

def t17_branch_switch():
    output = run_mem("branch", "switch", "regression-test")
    assert "switch" in output.lower() or "✅" in output, f"Switch failed: {output}"
    # Switch back
    run_mem("branch", "switch", "main")
run("T17: mem branch switch", t17_branch_switch)

def t18_branch_merge():
    # Create a branch with entity, then merge
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO memory_branches (name, project_path, parent_branch) VALUES (?,?,?)",
              ("merge-test-10a", pp, "main"))
    c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
              ("Merge10a decision", "Test", "technical", "active", "high", pp, "merge-test-10a"))
    conn.commit()
    conn.close()
    output = run_mem("branch", "merge", "merge-test-10a", "--into", "main")
    assert "completat" in output.lower() or "✅" in output, f"Merge failed: {output}"
run("T18: mem branch merge", t18_branch_merge)

def t19_mem_context():
    output = run_mem("context", "--compact")
    assert len(output) > 10, f"Empty context: {output}"
run("T19: mem context (regression)", t19_mem_context)

def t20_api_v1_context():
    r = client._get("/api/v1/context", {"project": pp, "mode": "compact"})
    assert r.get("ok") is True, f"Expected ok: {r}"
run("T20: /api/v1/context (regression)", t20_api_v1_context)

def t21_mem_dashboard():
    r = client._get("/api/dashboard", {"project": pp})
    assert "summary" in r, f"No summary: {r}"
    assert "decisions" in r, f"No decisions: {r}"
run("T21: /api/dashboard (regression)", t21_mem_dashboard)

def t22_web_ui_loadable():
    web_index = WEB_DIR / "index.html"
    assert web_index.exists(), f"Web UI index.html missing: {web_index}"
    content = web_index.read_text()
    assert "<html" in content.lower() or "<!doctype" in content.lower(), "Invalid HTML"
run("T22: web UI se încarcă (index.html exists)", t22_web_ui_loadable)

def t23_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity failed: {result}"
run("T23: PRAGMA integrity_check", t23_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 10A Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
