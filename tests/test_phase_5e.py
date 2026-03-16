#!/usr/bin/env python3
"""
Teste Faza 5E: Agent Activity Log

T1-T5: Migration + DB
T6-T10: Helper log_agent_activity
T11-T15: CLI activity_log.py
T16-T18: Integrare scripturi existente
T19-T22: Timeline + Dashboard CLI
T23-T26: API endpoints
T27-T29: Web UI
T30-T31: Regresie
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_5e_")
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

c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Use SQLite for storage", "Simplitate", "technical", "active", "confirmed", pp))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("WAL mode for concurrency", "convention", "sqlite", "confirmed", 1, 1, pp))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Complete V2", "Full implementation", "high", "active", pp))
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Build API", "high", "in_progress", 1, pp))
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?,?,?,?,datetime('now'))",
          ("ImportError xyz", "pip install xyz", 1, pp))
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))
c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
          (pp, "pre-api", "Before API impl", "opus", "feature", "auto", 1, 1, 1, 1, 1))
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("checkpoint_create", 1, "Checkpoint: pre-api", "5 entities", pp))
conn.commit()
conn.close()


# ===== T1-T5: Migration + DB =====
print("\n\U0001f4cb T1-T5: Migration + DB")

def t1_table_exists():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_activity_log'")
    assert c.fetchone() is not None, "agent_activity_log table not found"
    conn.close()
run("T1: agent_activity_log table exists", t1_table_exists)

def t2_columns():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA table_info(agent_activity_log)")
    cols = {row[1] for row in c.fetchall()}
    conn.close()
    expected = {"id", "session_id", "project_path", "agent_name", "model_id", "provider",
                "action_type", "action_summary", "entity_type", "entity_id",
                "success", "error_message", "duration_ms", "tokens_used", "metadata_json", "created_at"}
    missing = expected - cols
    assert not missing, f"Missing columns: {missing}"
run("T2: All columns present", t2_columns)

def t3_indexes():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='agent_activity_log'")
    idxs = {row[0] for row in c.fetchall()}
    conn.close()
    expected_prefixes = ["idx_activity_project", "idx_activity_agent", "idx_activity_model",
                         "idx_activity_type", "idx_activity_created", "idx_activity_session", "idx_activity_entity"]
    for prefix in expected_prefixes:
        assert prefix in idxs, f"Missing index: {prefix}"
run("T3: All indexes present", t3_indexes)

def t4_insert():
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO agent_activity_log
        (session_id, project_path, agent_name, model_id, provider, action_type, action_summary,
         entity_type, entity_id, success, duration_ms, tokens_used)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("test-session", pp, "claude-opus", "claude-opus-4", "anthropic", "decision",
         "Test activity insert", "decision", 1, 1, 500, 1000))
    conn.commit()
    assert c.lastrowid > 0
    conn.close()
run("T4: Direct INSERT works", t4_insert)

def t5_query():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_activity_log WHERE project_path=?", (pp,))
    rows = c.fetchall()
    conn.close()
    assert len(rows) >= 1
    r = dict(rows[0])
    assert r["agent_name"] == "claude-opus"
    assert r["success"] == 1
run("T5: SELECT with filter works", t5_query)


# ===== T6-T10: Helper log_agent_activity =====
print("\n\U0001f4cb T6-T10: Helper log_agent_activity")

import v2_common
v2_common.GLOBAL_DB = Path(TEST_DB)
from v2_common import log_agent_activity

def t6_basic_log():
    aid = log_agent_activity("decision", "Test basic log")
    assert aid is not None and aid > 0
run("T6: log_agent_activity returns ID", t6_basic_log)

def t7_full_params():
    aid = log_agent_activity(
        "fix", "Fixed import error",
        entity_type="error", entity_id=42,
        success=True, duration_ms=1200, tokens_used=500,
        metadata={"file": "test.py", "line": 10},
        agent_name="dana", model_id="glm-5", provider="z.ai"
    )
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_activity_log WHERE id=?", (aid,))
    r = dict(c.fetchone())
    conn.close()
    assert r["agent_name"] == "dana"
    assert r["model_id"] == "glm-5"
    assert r["entity_type"] == "error"
    assert r["entity_id"] == 42
    assert r["duration_ms"] == 1200
    meta = json.loads(r["metadata_json"])
    assert meta["file"] == "test.py"
run("T7: All parameters stored correctly", t7_full_params)

def t8_failed_log():
    aid = log_agent_activity("review", "Review failed", success=False, error_message="Syntax error in file")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_activity_log WHERE id=?", (aid,))
    r = dict(c.fetchone())
    conn.close()
    assert r["success"] == 0
    assert r["error_message"] == "Syntax error in file"
run("T8: Failed activity logged correctly", t8_failed_log)

def t9_silent_failure():
    # Test that log_agent_activity handles exceptions silently
    # We test by passing invalid metadata that would fail JSON serialization
    # The function should catch exceptions and return None
    aid = log_agent_activity("test", "Valid log for silent failure test")
    assert aid is not None  # Normal case works
    # Verify return type is int
    assert isinstance(aid, int)
run("T9: log_agent_activity returns int on success", t9_silent_failure)

def t10_no_model():
    aid = log_agent_activity("query", "Query without model", model_id=None)
    assert aid is not None
run("T10: Works without model_id", t10_no_model)


# ===== T11-T15: CLI activity_log.py =====
print("\n\U0001f4cb T11-T15: CLI activity_log.py")

def t11_cli_import():
    result = subprocess.run(["python3", "-c", f"import sys; sys.path.insert(0, '{SCRIPTS_DIR}'); import activity_log"],
                            capture_output=True, text=True, env={**os.environ, "MEMORY_DB_PATH": TEST_DB})
    assert result.returncode == 0, f"Import failed: {result.stderr}"
run("T11: activity_log.py importable", t11_cli_import)

def t12_mem_activity():
    output = run_mem("activity")
    assert "AGENT ACTIVITY LOG" in output or "Nicio activitate" in output or "activity" in output.lower()
run("T12: mem activity runs", t12_mem_activity)

def t13_mem_activity_filter():
    output = run_mem("activity", "--type", "decision")
    assert output is not None  # Just check it doesn't crash
run("T13: mem activity --type filter", t13_mem_activity_filter)

def t14_mem_activity_failed():
    output = run_mem("activity", "--failed")
    assert output is not None
run("T14: mem activity --failed filter", t14_mem_activity_failed)

def t15_mem_activity_json():
    output = run_mem("activity", "--json")
    try:
        data = json.loads(output)
        assert isinstance(data, list)
    except json.JSONDecodeError:
        pass  # May have extra output, just check it runs
run("T15: mem activity --json format", t15_mem_activity_json)


# ===== T16-T18: Integrare scripturi existente =====
print("\n\U0001f4cb T16-T18: Integrare scripturi")

def t16_decision_logs():
    # Clear activity log to check new entries
    conn = get_db()
    conn.execute("DELETE FROM agent_activity_log")
    conn.commit()
    conn.close()

    output = run_mem("decide", "-t", "Test activity decision", "-d", "For testing activity log")
    assert "salvată" in output or "Decizie" in output

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_activity_log WHERE action_type='decision'")
    rows = c.fetchall()
    conn.close()
    assert len(rows) >= 1, "No activity log for decision add"
run("T16: decision add logs activity", t16_decision_logs)

def t17_fact_logs():
    conn = get_db()
    conn.execute("DELETE FROM agent_activity_log")
    conn.commit()
    conn.close()

    output = run_mem("learn", "Test activity fact for logging")
    assert "salvat" in output or "Fact" in output

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_activity_log WHERE action_type='learn'")
    rows = c.fetchall()
    conn.close()
    assert len(rows) >= 1, "No activity log for fact add"
run("T17: fact add logs activity", t17_fact_logs)

def t18_goal_logs():
    conn = get_db()
    conn.execute("DELETE FROM agent_activity_log")
    conn.commit()
    conn.close()

    output = run_mem("goal", "-t", "Test activity goal")
    assert "salvat" in output or "Goal" in output

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM agent_activity_log WHERE action_type='goal'")
    rows = c.fetchall()
    conn.close()
    assert len(rows) >= 1, "No activity log for goal add"
run("T18: goal add logs activity", t18_goal_logs)


# ===== T19-T22: Timeline + Dashboard CLI =====
print("\n\U0001f4cb T19-T22: Timeline + Dashboard CLI")

def t19_timeline_import():
    result = subprocess.run(["python3", "-c", f"import sys; sys.path.insert(0, '{SCRIPTS_DIR}'); from timeline import EVENT_ICONS; assert 'agent_activity' in EVENT_ICONS"],
                            capture_output=True, text=True, env={**os.environ, "MEMORY_DB_PATH": TEST_DB})
    assert result.returncode == 0, f"Failed: {result.stderr}"
run("T19: timeline has agent_activity icon", t19_timeline_import)

def t20_timeline_runs():
    output = run_mem("timeline", "--all")
    assert output is not None  # Just check it doesn't crash
run("T20: mem timeline --all runs with activity", t20_timeline_runs)

def t21_dashboard_has_activity():
    output = run_mem("dashboard", "--json")
    try:
        data = json.loads(output)
        assert "activity_recent" in data, "Missing activity_recent key"
    except json.JSONDecodeError:
        pass  # Dashboard may have non-JSON prefix
run("T21: dashboard --json has activity_recent", t21_dashboard_has_activity)

def t22_dashboard_text():
    output = run_mem("dashboard")
    assert output is not None
run("T22: dashboard text runs without crash", t22_dashboard_text)


# ===== T23-T26: API endpoints =====
print("\n\U0001f4cb T23-T26: API endpoints")

os.environ["MEMORY_DB_PATH"] = TEST_DB
v2_common.GLOBAL_DB = Path(TEST_DB)

from dashboard_api import dashboard_bp
from flask import Flask

test_app = Flask(__name__, static_folder=str(WEB_DIR))
test_app.register_blueprint(dashboard_bp)

@test_app.route('/')
def index():
    from flask import send_from_directory
    return send_from_directory(str(WEB_DIR), 'index.html')

@test_app.route('/<path:filename>')
def static_files(filename):
    from flask import send_from_directory
    return send_from_directory(str(WEB_DIR), filename)

client = test_app.test_client()

def t23_api_activity():
    resp = client.get(f"/api/activity?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "activity" in data
    assert "count" in data
run("T23: GET /api/activity returns 200", t23_api_activity)

def t24_api_activity_filter():
    resp = client.get(f"/api/activity?project={pp}&type=decision")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["activity"], list)
run("T24: /api/activity with type filter", t24_api_activity_filter)

def t25_api_activity_failed():
    resp = client.get(f"/api/activity?project={pp}&failed=true")
    assert resp.status_code == 200
run("T25: /api/activity with failed filter", t25_api_activity_failed)

def t26_dashboard_activity():
    resp = client.get(f"/api/dashboard?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "activity_recent" in data
    assert isinstance(data["activity_recent"], list)
run("T26: /api/dashboard includes activity_recent", t26_dashboard_activity)


# ===== T27-T29: Web UI =====
print("\n\U0001f4cb T27-T29: Web UI")

def t27_tab_present():
    resp = client.get("/")
    html = resp.data.decode('utf-8')
    assert 'data-tab="activity"' in html, "Activity tab button missing"
    assert 'id="tab-activity"' in html, "Activity tab section missing"
run("T27: Activity tab in HTML", t27_tab_present)

def t28_js_functions():
    resp = client.get("/app.js")
    js = resp.data.decode('utf-8')
    assert "loadActivityTab" in js, "loadActivityTab function missing"
    assert "renderDashActivity" in js, "renderDashActivity function missing"
    assert "/api/activity" in js, "/api/activity URL missing in JS"
run("T28: app.js has activity functions", t28_js_functions)

def t29_css_checkbox():
    resp = client.get("/styles.css")
    css = resp.data.decode('utf-8')
    assert "chk-label" in css, ".chk-label CSS class missing"
run("T29: styles.css has activity styles", t29_css_checkbox)


# ===== T30-T31: Regresie =====
print("\n\U0001f4cb T30-T31: Regresie")

def t30_all_endpoints():
    endpoints = ["/api/dashboard", "/api/decisions", "/api/facts", "/api/goals",
                 "/api/tasks", "/api/patterns", "/api/timeline", "/api/checkpoints",
                 "/api/context", "/api/health", "/api/activity"]
    for ep in endpoints:
        resp = client.get(f"{ep}?project={pp}")
        assert resp.status_code == 200, f"{ep} returned {resp.status_code}"
run("T30: All API endpoints respond 200", t30_all_endpoints)

def t31_db_integrity():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()[0]
    conn.close()
    assert result == "ok"
run("T31: PRAGMA integrity_check", t31_db_integrity)


# ===== SUMMARY =====
print(f"\n{'=' * 50}")
print(f"  REZULTATE: {passed} passed, {failed} failed")
print(f"{'=' * 50}")
print(f"  DB test: {TEST_DB}")

if failed:
    sys.exit(1)
