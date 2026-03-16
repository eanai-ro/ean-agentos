#!/usr/bin/env python3
"""
Teste Faza 9: Memory Branches

T1-T5:   Branch basics (create, list, current, switch, delete)
T6-T10:  Branch-aware writes (decisions, facts, goals, tasks, resolutions pe branch)
T11-T14: Diff & Merge
T15-T17: Context & Checkpoint branch-aware
T18-T20: API branch support
T21-T25: CLI integration
T26-T29: Regresie generală
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_9_")
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

# Populate base data on main branch
conn = get_db()
c = conn.cursor()
pp = PROJECT_PATH
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("Use SQLite", "Simplitate", "technical", "active", "confirmed", pp, "main"))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, branch, created_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
          ("WAL mode required", "convention", "sqlite", "confirmed", 1, 1, pp, "main"))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, branch, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Complete V2", "Full impl", "high", "active", pp, "main"))
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, branch, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Build API", "high", "in_progress", 1, pp, "main"))
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, branch, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("ImportError xyz", "pip install xyz", 1, pp, "main"))
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))
c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
          (pp, "pre-branch", "Before branch impl", "opus", "feature", "auto", 1, 1, 1, 1, 1))
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("checkpoint_create", 1, "Checkpoint: pre-branch", "5 entities", pp))
conn.commit()
conn.close()


# ===== Setup Flask test server =====
print("\n\U0001f310 Setup Flask + clients...")

from flask import Flask
app = Flask(__name__)
app.config["TESTING"] = True

from dashboard_api import dashboard_bp
from universal_api import universal_bp
app.register_blueprint(dashboard_bp)
app.register_blueprint(universal_bp)

import threading
from werkzeug.serving import make_server

server = make_server("127.0.0.1", 19879, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

BASE_URL = "http://127.0.0.1:19879"

from clients.universal_memory_client import UniversalMemoryClient

client = UniversalMemoryClient(
    base_url=BASE_URL,
    project_path=pp,
    cli_name="branch-test",
    agent_name="test-agent",
    provider="test",
    model_name="test-model",
)


# ===== T1-T5: Branch basics =====
print("\n\U0001f4cb T1-T5: Branch basics")

def t1_create_branch():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
              ("feature-x", pp, "main", "Feature X branch"))
    conn.commit()
    c.execute("SELECT * FROM memory_branches WHERE name='feature-x' AND project_path=?", (pp,))
    row = c.fetchone()
    conn.close()
    assert row is not None, "Branch not created"
    assert row["parent_branch"] == "main"
    assert row["is_active"] == 1
run("T1: Create branch in DB", t1_create_branch)

def t2_create_branch_cli():
    output = run_mem("branch", "create", "experiment-1", "-d", "Test experiment")
    assert "creat" in output.lower() or "✅" in output, f"Unexpected: {output}"
run("T2: Create branch via CLI", t2_create_branch_cli)

def t3_list_branches():
    output = run_mem("branch", "list")
    assert "main" in output, f"main missing: {output}"
    assert "feature-x" in output, f"feature-x missing: {output}"
    assert "experiment-1" in output, f"experiment-1 missing: {output}"
run("T3: List branches", t3_list_branches)

def t4_switch_branch():
    from v2_common import set_current_branch, get_current_branch, clear_current_branch
    set_current_branch("feature-x")
    assert get_current_branch() == "feature-x"
    clear_current_branch()
    assert get_current_branch() == "main"
run("T4: Switch branch (helpers)", t4_switch_branch)

def t5_current_branch():
    output = run_mem("branch", "current")
    assert "main" in output.lower(), f"Expected main: {output}"
run("T5: Current branch CLI", t5_current_branch)


# ===== T6-T10: Branch-aware writes =====
print("\n\U0001f4cb T6-T10: Branch-aware writes")

def t6_decision_on_branch():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
              ("Use Redis", "Cache layer", "technical", "active", "high", pp, "feature-x"))
    conn.commit()
    # Verify it's on feature-x
    c.execute("SELECT branch FROM decisions WHERE title='Use Redis'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x"
run("T6: Decision on branch", t6_decision_on_branch)

def t7_fact_on_branch():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, branch) VALUES (?,?,?,?,?,?,?,?)",
              ("Redis needs port 6379", "technical", "infra", "high", 0, 1, pp, "feature-x"))
    conn.commit()
    c.execute("SELECT branch FROM learned_facts WHERE fact LIKE '%Redis%'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x"
run("T7: Fact on branch", t7_fact_on_branch)

def t8_goal_on_branch():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO goals (title, description, priority, status, project_path, branch) VALUES (?,?,?,?,?,?)",
              ("Add caching", "Redis caching layer", "medium", "active", pp, "feature-x"))
    conn.commit()
    c.execute("SELECT branch FROM goals WHERE title='Add caching'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x"
run("T8: Goal on branch", t8_goal_on_branch)

def t9_task_on_branch():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO tasks (title, priority, status, project_path, branch) VALUES (?,?,?,?,?)",
              ("Setup Redis", "high", "todo", pp, "feature-x"))
    conn.commit()
    c.execute("SELECT branch FROM tasks WHERE title='Setup Redis'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x"
run("T9: Task on branch", t9_task_on_branch)

def t10_resolution_on_branch():
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, branch) VALUES (?,?,?,?,?)",
              ("Redis connection refused", "Start redis-server", 1, pp, "feature-x"))
    conn.commit()
    c.execute("SELECT branch FROM error_resolutions WHERE error_summary LIKE '%Redis%'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x"
run("T10: Resolution on branch", t10_resolution_on_branch)


# ===== T11-T14: Diff & Merge =====
print("\n\U0001f4cb T11-T14: Diff & Merge")

def t11_diff_branches():
    output = run_mem("branch", "diff", "main", "feature-x")
    assert "main" in output and "feature-x" in output, f"Diff missing branches: {output}"
    # Should show entities from both
    assert "decisions" in output.lower() or "Use" in output, f"No entities in diff: {output}"
run("T11: Diff between branches", t11_diff_branches)

def t12_detect_conflicts():
    # Create same-title decision on both branches
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
              ("Shared Decision", "On main", "technical", "active", "high", pp, "main"))
    c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
              ("Shared Decision", "On feature-x", "technical", "active", "high", pp, "feature-x"))
    conn.commit()
    conn.close()
    output = run_mem("branch", "conflicts", "main", "feature-x")
    assert "conflict" in output.lower() or "Shared Decision" in output, f"Conflict not detected: {output}"
run("T12: Detect conflicts", t12_detect_conflicts)

def t13_merge_branch():
    # Create a separate branch for merge test
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
              ("merge-test", pp, "main", "For merge testing"))
    c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
              ("Merge-only decision", "Test", "technical", "active", "high", pp, "merge-test"))
    c.execute("INSERT INTO learned_facts (fact, fact_type, confidence, is_active, project_path, branch) VALUES (?,?,?,?,?,?)",
              ("Merge fact", "technical", "high", 1, pp, "merge-test"))
    conn.commit()
    conn.close()

    output = run_mem("branch", "merge", "merge-test", "--into", "main")
    assert "completat" in output.lower() or "✅" in output, f"Merge failed: {output}"

    # Verify entities moved to main
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT branch FROM decisions WHERE title='Merge-only decision'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "main", f"Expected main, got {row['branch']}"
run("T13: Merge branch into main", t13_merge_branch)

def t14_merge_log():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM branch_merge_log WHERE source_branch='merge-test' AND target_branch='main'")
    row = c.fetchone()
    conn.close()
    assert row is not None, "Merge not logged"
    assert row["entities_merged"] >= 2, f"Expected >=2 entities merged, got {row['entities_merged']}"
run("T14: Merge log recorded", t14_merge_log)


# ===== T15-T17: Context & checkpoint branch-aware =====
print("\n\U0001f4cb T15-T17: Context branch-aware")

def t15_context_main_branch():
    """Context pe main nu include entități de pe feature-x."""
    from context_builder_v2 import fetch_decisions, fetch_facts
    conn = get_db()
    cursor = conn.cursor()
    decisions = fetch_decisions(cursor, pp, 50, branch="main")
    facts = fetch_facts(cursor, pp, 50, branch="main")
    conn.close()
    # Should NOT have feature-x specific items
    decision_titles = [d["title"] for d in decisions]
    fact_texts = [f["fact"] for f in facts]
    assert "Use Redis" not in decision_titles, f"feature-x decision leaked to main: {decision_titles}"
    assert not any("Redis" in f and "port" in f for f in fact_texts), f"feature-x fact leaked to main"
run("T15: Context on main excludes feature-x entities", t15_context_main_branch)

def t16_context_feature_branch():
    """Context pe feature-x include doar entitățile sale."""
    from context_builder_v2 import fetch_decisions, fetch_facts
    conn = get_db()
    cursor = conn.cursor()
    decisions = fetch_decisions(cursor, pp, 50, branch="feature-x")
    facts = fetch_facts(cursor, pp, 50, branch="feature-x")
    conn.close()
    decision_titles = [d["title"] for d in decisions]
    assert "Use Redis" in decision_titles, f"feature-x decision missing: {decision_titles}"
    # Should NOT have main-only items
    assert "Use SQLite" not in decision_titles, f"main decision leaked to feature-x: {decision_titles}"
run("T16: Context on feature-x shows only its entities", t16_context_feature_branch)

def t17_context_cli_with_branch():
    output = run_mem("context", "--compact", "--branch", "main")
    assert len(output) > 10, f"Empty context: {output}"
run("T17: Context CLI with --branch", t17_context_cli_with_branch)


# ===== T18-T20: API branch support =====
print("\n\U0001f4cb T18-T20: API branch support")

def t18_api_create_decision_with_branch():
    r = client._post("/api/v1/decisions", {
        "title": "API branch decision",
        "description": "Created via API on branch",
        "project_path": pp,
        "branch": "feature-x",
        "cli_name": "branch-test",
        "agent_name": "test-agent",
    })
    assert r.get("ok") is True, f"Expected ok: {r}"
    assert r.get("id") > 0

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT branch FROM decisions WHERE title='API branch decision'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x", f"Expected feature-x, got {row['branch']}"
run("T18: API create decision with branch", t18_api_create_decision_with_branch)

def t19_api_create_fact_with_branch():
    r = client._post("/api/v1/facts", {
        "fact": "API branch fact",
        "fact_type": "technical",
        "project_path": pp,
        "branch": "feature-x",
        "cli_name": "branch-test",
        "agent_name": "test-agent",
    })
    assert r.get("ok") is True, f"Expected ok: {r}"
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT branch FROM learned_facts WHERE fact='API branch fact'")
    row = c.fetchone()
    conn.close()
    assert row["branch"] == "feature-x"
run("T19: API create fact with branch", t19_api_create_fact_with_branch)

def t20_api_context_with_branch():
    r = client._get("/api/v1/context", {
        "project": pp,
        "mode": "compact",
        "branch": "feature-x",
    })
    assert r.get("ok") is True, f"Expected ok: {r}"
    # Should have feature-x entities
    decision_titles = [d["title"] for d in r.get("decisions", [])]
    assert any("Redis" in t or "API branch" in t for t in decision_titles), \
        f"feature-x decisions missing from context: {decision_titles}"
run("T20: API context with branch filter", t20_api_context_with_branch)


# ===== T21-T25: CLI integration =====
print("\n\U0001f4cb T21-T25: CLI integration")

def t21_branch_create_duplicate():
    output = run_mem("branch", "create", "feature-x")
    assert "există" in output.lower() or "❌" in output, f"Duplicate not detected: {output}"
run("T21: Cannot create duplicate branch", t21_branch_create_duplicate)

def t22_branch_switch_nonexistent():
    output = run_mem("branch", "switch", "nonexistent-branch")
    assert "nu există" in output.lower() or "❌" in output, f"Expected error: {output}"
run("T22: Cannot switch to nonexistent branch", t22_branch_switch_nonexistent)

def t23_branch_delete_with_entities():
    # feature-x has entities, should warn
    output = run_mem("branch", "delete", "feature-x")
    assert "entități" in output.lower() or "⚠" in output or "entities" in output.lower(), \
        f"Expected warning about entities: {output}"
run("T23: Delete branch with entities warns", t23_branch_delete_with_entities)

def t24_branch_delete_empty():
    # Create empty branch and delete it
    run_mem("branch", "create", "empty-branch")
    output = run_mem("branch", "delete", "empty-branch")
    assert "dezactivat" in output.lower() or "✅" in output, f"Delete failed: {output}"
    # Verify it's inactive
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_active FROM memory_branches WHERE name='empty-branch' AND project_path=?", (pp,))
    row = c.fetchone()
    conn.close()
    assert row["is_active"] == 0, "Branch still active"
run("T24: Delete empty branch", t24_branch_delete_empty)

def t25_branch_delete_main_forbidden():
    output = run_mem("branch", "delete", "main")
    assert "❌" in output or "nu poți" in output.lower(), f"Expected error: {output}"
run("T25: Cannot delete main branch", t25_branch_delete_main_forbidden)


# ===== T26-T29: Regresie generală =====
print("\n\U0001f4cb T26-T29: Regresie generală")

def t26_api_v1_context():
    r = client._get("/api/v1/context", {"project": pp, "mode": "compact"})
    assert r.get("ok") is True
run("T26: /api/v1/context (regression)", t26_api_v1_context)

def t27_api_v1_activity():
    r = client._get("/api/v1/activity", {"project": pp, "limit": "5"})
    assert r.get("ok") is True
run("T27: /api/v1/activity (regression)", t27_api_v1_activity)

def t28_mem_context():
    output = run_mem("context", "--mode", "compact")
    assert len(output) > 5, f"Empty: {output}"
run("T28: mem context CLI (regression)", t28_mem_context)

def t29_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity check failed: {result}"
run("T29: PRAGMA integrity_check", t29_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 9 Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
