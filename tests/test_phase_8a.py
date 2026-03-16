#!/usr/bin/env python3
"""
Teste Faza 8A: Codex CLI Adapter

T1-T6:   Codex adapter functions (start_session, get_context, create_*, log_activity)
T7-T9:   Verificare date Codex în DB
T10-T15: Gemini adapter regression (ambii adaptori coexistă)
T16-T24: Regresie generală (dashboard, context, CLI, UI, integrity)
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_8a_")
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
print("\n\U0001f310 Setup Flask + adapters...")

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

server = make_server("127.0.0.1", 19877, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

BASE_URL = "http://127.0.0.1:19877"

# Create Codex adapter
sys.path.insert(0, str(SCRIPTS_DIR / "adapters"))
from codex_cli_adapter import CodexMemoryAdapter
from gemini_cli_adapter import GeminiMemoryAdapter

codex = CodexMemoryAdapter(
    base_url=BASE_URL,
    project_path=pp,
    cli_name="codex-cli",
    agent_name="codex",
    provider="openai",
    model_name="o3",
)

gemini = GeminiMemoryAdapter(
    base_url=BASE_URL,
    project_path=pp,
    cli_name="gemini-cli",
    agent_name="gemini-planner",
    provider="google",
    model_name="gemini-2.5-pro",
)


# ===== T1-T6: Codex Adapter functions =====
print("\n\U0001f4cb T1-T6: Codex adapter functions")

def t1_start_session():
    r = codex.start_session("Test session from Codex CLI adapter")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
    assert r.get("event_type") == "session_start"
run("T1: start_session → event saved", t1_start_session)

def t2_get_context():
    r = codex.get_context(mode="compact", intent="debugging")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert "meta" in r or "decisions" in r or "facts" in r
run("T2: get_context → valid context", t2_get_context)

def t3_create_decision():
    r = codex.create_decision(
        "Use async/await pattern",
        description="Better error handling in Node.js",
        category="technical",
        rationale="Cleaner code flow",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T3: create_decision → saved", t3_create_decision)

def t4_create_fact():
    r = codex.create_fact(
        "Project uses ESM modules",
        fact_type="convention",
        category="javascript",
        source="codex analysis",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T4: create_fact → saved", t4_create_fact)

def t5_create_task():
    r = codex.create_task(
        "Implement retry logic",
        description="Add exponential backoff for API calls",
        priority="high",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
    assert r.get("status") == "todo"
run("T5: create_task → saved", t5_create_task)

def t6_log_activity():
    r = codex.log_activity("Refactored error handling in main module")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
run("T6: log_activity → saved", t6_log_activity)


# ===== T7-T9: Database verification =====
print("\n\U0001f4cb T7-T9: Codex DB verification")

def t7_codex_events_in_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM universal_events WHERE cli_name='codex-cli'")
    count = c.fetchone()[0]
    conn.close()
    assert count >= 2, f"Expected >=2 codex-cli events, got {count}"
run("T7: codex-cli events exist in universal_events", t7_codex_events_in_db)

def t8_codex_metadata_correct():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM universal_events WHERE cli_name='codex-cli' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    assert row is not None, "No codex-cli events found"
    assert row["agent_name"] == "codex"
    assert row["provider"] == "openai"
    assert row["model_name"] == "o3"
    assert row["session_id"] == codex.session_id
run("T8: codex-cli metadata correct", t8_codex_metadata_correct)

def t9_codex_session_id_prefix():
    assert codex.session_id.startswith("codex_"), f"Session ID should start with codex_, got {codex.session_id}"
run("T9: session_id starts with codex_", t9_codex_session_id_prefix)


# ===== T10-T15: Gemini adapter regression =====
print("\n\U0001f4cb T10-T15: Gemini adapter regression (coexistență)")

def t10_gemini_start_session():
    r = gemini.start_session("Gemini regression test")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
run("T10: Gemini start_session still works", t10_gemini_start_session)

def t11_gemini_create_decision():
    r = gemini.create_decision("Use Cloud Functions", description="Serverless backend")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T11: Gemini create_decision still works", t11_gemini_create_decision)

def t12_gemini_create_fact():
    r = gemini.create_fact("Project uses Firestore", fact_type="technical")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T12: Gemini create_fact still works", t12_gemini_create_fact)

def t13_gemini_events_separate():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM universal_events WHERE cli_name='gemini-cli'")
    gemini_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM universal_events WHERE cli_name='codex-cli'")
    codex_count = c.fetchone()[0]
    conn.close()
    assert gemini_count >= 1, f"Expected >=1 gemini events, got {gemini_count}"
    assert codex_count >= 2, f"Expected >=2 codex events, got {codex_count}"
    # Both coexist
run("T13: Gemini & Codex events coexist in DB", t13_gemini_events_separate)

def t14_gemini_context():
    r = gemini.get_context(mode="full")
    assert r.get("ok") is True
    meta = r.get("meta", {})
    assert meta.get("requesting_agent") == "gemini-planner"
run("T14: Gemini context has correct agent_name", t14_gemini_context)

def t15_codex_context_agent():
    r = codex.get_context(mode="full")
    assert r.get("ok") is True
    meta = r.get("meta", {})
    assert meta.get("requesting_agent") == "codex"
run("T15: Codex context has correct agent_name", t15_codex_context_agent)


# ===== T16-T24: General regression =====
print("\n\U0001f4cb T16-T24: Regresie generală")

def t16_dashboard():
    r = codex._get("/api/dashboard", {"project": pp})
    assert "summary" in r
    assert "decisions" in r
    assert "facts" in r
run("T16: /api/dashboard still works", t16_dashboard)

def t17_old_context():
    r = codex._get("/api/context", {"project": pp, "mode": "compact"})
    assert "meta" in r or "decisions" in r or "facts" in r
run("T17: /api/context still works", t17_old_context)

def t18_mem_context():
    output = run_mem("context", "--mode", "compact")
    assert len(output) > 5, f"Empty: {output}"
run("T18: mem context CLI", t18_mem_context)

def t19_mem_strategy():
    output = run_mem("strategy")
    assert len(output) > 5, f"Empty: {output}"
run("T19: mem strategy CLI", t19_mem_strategy)

def t20_mem_activity():
    output = run_mem("activity")
    assert len(output) > 0
run("T20: mem activity CLI", t20_mem_activity)

def t21_mem_dashboard():
    output = run_mem("dashboard")
    assert len(output) > 0
run("T21: mem dashboard CLI", t21_mem_dashboard)

def t22_web_ui():
    html = (WEB_DIR / "index.html").read_text()
    assert "Memory Control Center" in html
    assert "tab-errors" in html
    js = (WEB_DIR / "app.js").read_text()
    assert "loadDashboard" in js
    assert "loadErrorsTab" in js
run("T22: Web UI files intact", t22_web_ui)

def t23_codex_activity_visible():
    r = codex.get_activity(limit=10)
    assert r.get("ok") is True
    assert r.get("count", 0) >= 1, f"Expected activity, got count={r.get('count')}"
run("T23: Codex activity visible via API", t23_codex_activity_visible)

def t24_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity check failed: {result}"
run("T24: PRAGMA integrity_check", t24_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 8A Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
