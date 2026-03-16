#!/usr/bin/env python3
"""
Teste Faza 7: Gemini CLI Adapter

T1-T6:   Adapter functions (start_session, get_context, create_*, log_activity)
T7-T9:   Verificare date în DB
T10-T17: Regresie (dashboard, context, CLI, UI, integrity)
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_7_")
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

# Populate base data
conn = get_db()
c = conn.cursor()
pp = PROJECT_PATH
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
          ("Use SQLite", "Simplitate", "technical", "active", "confirmed", pp))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("WAL mode required", "convention", "sqlite", "confirmed", 1, 1, pp))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Complete V2", "Full impl", "high", "active", pp))
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


# ===== Setup Flask test server (in-process) =====
print("\n\U0001f310 Setup Flask + adapter...")

from flask import Flask
app = Flask(__name__)
app.config["TESTING"] = True

from dashboard_api import dashboard_bp
from universal_api import universal_bp
app.register_blueprint(dashboard_bp)
app.register_blueprint(universal_bp)

# Start test server in a thread
import threading
from werkzeug.serving import make_server

server = make_server("127.0.0.1", 19876, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

# Now create the adapter pointing at our test server
sys.path.insert(0, str(SCRIPTS_DIR / "adapters"))
from gemini_cli_adapter import GeminiMemoryAdapter

adapter = GeminiMemoryAdapter(
    base_url="http://127.0.0.1:19876",
    project_path=pp,
    cli_name="gemini-cli",
    agent_name="gemini-planner",
    provider="google",
    model_name="gemini-2.5-pro",
)


# ===== T1-T6: Adapter functions =====
print("\n\U0001f4cb T1-T6: Adapter functions")

def t1_start_session():
    r = adapter.start_session("Test session from Gemini CLI adapter")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
    assert r.get("event_type") == "session_start"
run("T1: start_session → event saved", t1_start_session)

def t2_get_context():
    r = adapter.get_context(mode="compact", intent="feature")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    # Should have meta or decisions
    assert "meta" in r or "decisions" in r or "facts" in r
run("T2: get_context → valid context", t2_get_context)

def t3_create_decision():
    r = adapter.create_decision(
        "Use Firestore for mobile",
        description="Better offline support",
        category="architectural",
        rationale="Mobile-first approach",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T3: create_decision → saved", t3_create_decision)

def t4_create_fact():
    r = adapter.create_fact(
        "Project uses React Native",
        fact_type="convention",
        category="mobile",
        source="gemini analysis",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T4: create_fact → saved", t4_create_fact)

def t5_create_task():
    r = adapter.create_task(
        "Setup Firebase integration",
        description="Connect mobile app to Firestore",
        priority="high",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
    assert r.get("status") == "todo"
run("T5: create_task → saved", t5_create_task)

def t6_log_activity():
    r = adapter.log_activity("Analyzed codebase structure for mobile migration")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
run("T6: log_activity → saved", t6_log_activity)


# ===== T7-T9: Database verification =====
print("\n\U0001f4cb T7-T9: Database verification")

def t7_activity_visible():
    r = adapter.get_activity(limit=10)
    assert r.get("ok") is True
    # Activity should have entries from create_decision, create_fact, create_task
    assert r.get("count", 0) >= 1, f"Expected activity, got count={r.get('count')}"
run("T7: Activity visible via /api/v1/activity", t7_activity_visible)

def t8_context_for_different_agent():
    r = adapter.get_context(mode="full")
    assert r.get("ok") is True
    # The requesting_agent should be set
    meta = r.get("meta", {})
    assert meta.get("requesting_agent") == "gemini-planner", f"Expected gemini-planner, got {meta}"
run("T8: Context works for different agent_name", t8_context_for_different_agent)

def t9_events_metadata():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM universal_events WHERE cli_name='gemini-cli' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    assert row is not None, "No gemini-cli events found"
    assert row["agent_name"] == "gemini-planner"
    assert row["provider"] == "google"
    assert row["model_name"] == "gemini-2.5-pro"
    assert row["session_id"] == adapter.session_id
run("T9: universal_events has correct metadata", t9_events_metadata)


# ===== T10-T17: Regression =====
print("\n\U0001f4cb T10-T17: Regression")

def t10_dashboard():
    r = adapter._get("/api/dashboard", {"project": pp})
    assert "summary" in r
    assert "decisions" in r
    assert "facts" in r
run("T10: /api/dashboard still works", t10_dashboard)

def t11_old_context():
    r = adapter._get("/api/context", {"project": pp, "mode": "compact"})
    assert "meta" in r or "decisions" in r or "facts" in r
run("T11: /api/context still works", t11_old_context)

def t12_mem_context():
    output = run_mem("context", "--mode", "compact")
    assert len(output) > 5, f"Empty: {output}"
run("T12: mem context CLI", t12_mem_context)

def t13_mem_strategy():
    output = run_mem("strategy")
    assert len(output) > 5, f"Empty: {output}"
run("T13: mem strategy CLI", t13_mem_strategy)

def t14_mem_activity():
    output = run_mem("activity")
    assert len(output) > 0
run("T14: mem activity CLI", t14_mem_activity)

def t15_mem_dashboard():
    output = run_mem("dashboard")
    assert len(output) > 0
run("T15: mem dashboard CLI", t15_mem_dashboard)

def t16_web_ui():
    html = (WEB_DIR / "index.html").read_text()
    assert "Memory Control Center" in html
    assert "tab-errors" in html
    js = (WEB_DIR / "app.js").read_text()
    assert "loadDashboard" in js
    assert "loadErrorsTab" in js
run("T16: Web UI files intact", t16_web_ui)

def t17_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity check failed: {result}"
run("T17: PRAGMA integrity_check", t17_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 7 Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
