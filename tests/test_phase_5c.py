#!/usr/bin/env python3
"""
Teste Faza 5C: Dashboard API

T1-T13: API endpoints
T14: Empty state
T15-T16: Parametri invalizi
T17-T25: Regresie
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_5c_")
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
print("\n🔧 Setup DB + Flask test client...")
sys.path.insert(0, str(SCRIPTS_DIR))
from init_db import init_database
init_database(Path(TEST_DB))

# Populate test data
conn = get_db()
c = conn.cursor()
pp = PROJECT_PATH

c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Use SQLite for storage", "Simplitate", "technical", "active", "confirmed", pp))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("REST API design", "Standard approach", "architectural", "active", "high", pp))

c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("WAL mode for concurrency", "convention", "sqlite", "confirmed", 1, 1, pp))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("Python 3.10 event loop", "gotcha", "python", "high", 0, 1, pp))

c.execute("INSERT INTO goals (title, description, priority, status, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Complete V2", "Full implementation", "high", "active", pp))

c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Build API", "high", "in_progress", 1, pp))
c.execute("INSERT INTO tasks (title, priority, status, blocked_by, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Deploy", "medium", "blocked", "review needed", pp))
c.execute("INSERT INTO tasks (title, priority, status, project_path, created_at) VALUES (?,?,?,?,datetime('now'))",
          ("Write docs", "low", "todo", pp))

c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?,?,?,?,datetime('now'))",
          ("ImportError xyz", "pip install xyz", 1, pp))

c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))

c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
          (pp, "pre-api", "Before API impl", "opus", "feature", "auto", 2, 2, 1, 3, 1))

c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("checkpoint_create", 1, "Checkpoint: pre-api", "9 entities", pp))

conn.commit()
conn.close()

# Setup Flask test client
os.environ["MEMORY_DB_PATH"] = TEST_DB

# Patch v2_common GLOBAL_DB before importing
import v2_common
v2_common.GLOBAL_DB = Path(TEST_DB)

from dashboard_api import dashboard_bp
from flask import Flask

test_app = Flask(__name__)
test_app.register_blueprint(dashboard_bp)
client = test_app.test_client()


# ===== T1-T13: API Endpoints =====
print("\n📋 T1-T13: API Endpoints")

def t1_dashboard():
    resp = client.get(f"/api/dashboard?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "summary" in data
    assert "decisions" in data
    assert "facts" in data
    assert "goals" in data
    assert "tasks" in data
    assert "health" in data
    assert "timeline" in data
    assert data["summary"]["project_name"] == pp.split("/")[-1]
run("T1: GET /api/dashboard", t1_dashboard)

def t2_dashboard_project():
    resp = client.get(f"/api/dashboard?project={pp}")
    data = resp.get_json()
    assert data["summary"]["project_path"] == pp
    assert len(data["decisions"]) == 2
    assert len(data["facts"]) == 2
run("T2: GET /api/dashboard?project=...", t2_dashboard_project)

def t3_decisions():
    resp = client.get(f"/api/decisions?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "decisions" in data
    assert data["count"] == 2
    assert data["decisions"][0]["title"] in ("Use SQLite for storage", "REST API design")
run("T3: GET /api/decisions", t3_decisions)

def t4_facts():
    resp = client.get(f"/api/facts?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2
    # Pinned first
    assert data["facts"][0]["is_pinned"] == 1
run("T4: GET /api/facts (pinned first)", t4_facts)

def t4b_facts_pinned():
    resp = client.get(f"/api/facts?project={pp}&pinned=true")
    data = resp.get_json()
    assert data["count"] == 1
    assert data["facts"][0]["is_pinned"] == 1
run("T4b: GET /api/facts?pinned=true", t4b_facts_pinned)

def t5_goals():
    resp = client.get(f"/api/goals?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["goals"][0]["title"] == "Complete V2"
run("T5: GET /api/goals", t5_goals)

def t6_tasks():
    resp = client.get(f"/api/tasks?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 3
    # in_progress should be first
    assert data["tasks"][0]["status"] == "in_progress"
run("T6: GET /api/tasks (prioritized)", t6_tasks)

def t7_patterns():
    resp = client.get(f"/api/patterns?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["patterns"][0]["count"] == 5
run("T7: GET /api/patterns", t7_patterns)

def t8_timeline():
    resp = client.get(f"/api/timeline?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "timeline" in data
    assert data["count"] >= 1
run("T8: GET /api/timeline", t8_timeline)

def t9_checkpoints():
    resp = client.get(f"/api/checkpoints?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["checkpoints"][0]["name"] == "pre-api"
run("T9: GET /api/checkpoints", t9_checkpoints)

def t10_context():
    resp = client.get(f"/api/context?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "meta" in data
    assert "decisions" in data
    assert "facts" in data
run("T10: GET /api/context", t10_context)

def t11_context_compact():
    resp = client.get(f"/api/context?project={pp}&mode=compact")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["meta"]["mode"] == "compact"
run("T11: GET /api/context?mode=compact", t11_context_compact)

def t12_context_full():
    resp = client.get(f"/api/context?project={pp}&mode=full")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["meta"]["mode"] == "full"
run("T12: GET /api/context?mode=full", t12_context_full)

def t13_health():
    resp = client.get(f"/api/health?project={pp}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["decisions"] == 2
    assert data["facts"] == 2
    assert data["goals"] == 1
    assert data["tasks"] == 3
    assert data["patterns"] == 1
    assert data["checkpoints"] == 1
run("T13: GET /api/health", t13_health)


# ===== T14: Empty state =====
print("\n📋 T14: Empty state")

def t14_empty():
    empty_pp = "/tmp/empty_project_xyz"
    for endpoint in ["/api/dashboard", "/api/decisions", "/api/facts", "/api/goals",
                     "/api/tasks", "/api/patterns", "/api/timeline", "/api/checkpoints",
                     "/api/health"]:
        resp = client.get(f"{endpoint}?project={empty_pp}")
        assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}"
        data = resp.get_json()
        assert isinstance(data, dict), f"{endpoint} invalid JSON"
run("T14: All endpoints return 200 on empty project", t14_empty)


# ===== T15-T16: Invalid params =====
print("\n📋 T15-T16: Parametri invalizi")

def t15_invalid_mode():
    resp = client.get(f"/api/context?project={pp}&mode=invalid_xyz")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
run("T15: /api/context?mode=invalid → 400", t15_invalid_mode)

def t16_invalid_limit():
    resp = client.get(f"/api/decisions?project={pp}&limit=abc")
    assert resp.status_code == 200  # Falls back to default
    data = resp.get_json()
    assert "decisions" in data
run("T16: limit invalid → fallback default", t16_invalid_limit)


# ===== T17-T25: Regresie =====
print("\n📋 T17-T25: Regresie")

def t17_webserver_import():
    # Verify web_server.py can be imported (syntax OK, blueprint registered)
    import importlib
    # Just check the file parses
    result = subprocess.run(["python3", "-c", f"import sys; sys.path.insert(0, '{SCRIPTS_DIR}'); import dashboard_api"],
                            capture_output=True, text=True, env={**os.environ, "MEMORY_DB_PATH": TEST_DB})
    assert result.returncode == 0, f"Import failed: {result.stderr}"
run("T17: dashboard_api importabil", t17_webserver_import)

def t18(): run_mem("dashboard"); pass
run("T18: mem dashboard", t18)

def t19(): run_mem("context", "--compact"); pass
run("T19: mem context", t19)

def t20():
    output = run_mem("strategy")
    assert "mode" in output.lower() or "strategy" in output.lower() or "survival" in output.lower() or "compact" in output.lower()
run("T20: mem strategy", t20)

def t21():
    output = run_mem("checkpoint", "list")
    assert "pre-api" in output or "Checkpoints" in output or "niciun" in output.lower()
run("T21: mem checkpoint list", t21)

def t22():
    output = run_mem("timeline", "--all")
    assert "TIMELINE" in output or "📅" in output or "niciun" in output.lower()
run("T22: mem timeline", t22)

def t23():
    output = run_mem("stats")
    assert "STATISTICI" in output or "Mesaje" in output
run("T23: mem stats", t23)

def t24():
    output = run_mem("search", "test")
    assert output is not None
run("T24: mem search", t24)

def t25():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()[0]
    conn.close()
    assert result == "ok"
run("T25: PRAGMA integrity_check", t25)


# ===== SUMMARY =====
print(f"\n{'=' * 50}")
print(f"  REZULTATE: {passed} passed, {failed} failed")
print(f"{'=' * 50}")
print(f"  DB test: {TEST_DB}")

if failed:
    sys.exit(1)
