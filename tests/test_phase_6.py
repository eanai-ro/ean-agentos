#!/usr/bin/env python3
"""
Teste Faza 6: Universal Agent Memory API

T1-T6:   POST endpoints (events, decisions, facts, goals, tasks, resolutions)
T7-T10:  GET endpoints (context, context?mode=compact, activity, health)
T11-T14: Validare (payload invalid, project lipsă, agent fields, context robust)
T15-T24: Regresie (dashboard, context, CLI, UI, integrity)
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_6_")
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
          ("WAL mode for concurrency", "convention", "sqlite", "high", 1, 1, pp))
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


# ===== Setup Flask test client with BOTH blueprints =====
print("\n\U0001f310 Setup Flask test client...")
from flask import Flask

app = Flask(__name__)
app.config["TESTING"] = True

from dashboard_api import dashboard_bp
from universal_api import universal_bp
app.register_blueprint(dashboard_bp)
app.register_blueprint(universal_bp)
client = app.test_client()


# ===== T1-T6: POST endpoints =====
print("\n\U0001f4cb T1-T6: Universal POST endpoints")

def t1_post_events():
    r = client.post("/api/v1/events", json={
        "event_type": "session_start",
        "title": "New session from gemini-cli",
        "cli_name": "gemini-cli",
        "agent_name": "planner",
        "provider": "google",
        "model_name": "gemini-2.5-pro",
        "session_id": "sess-001",
        "project_path": pp,
        "payload": {"some": "data"},
    })
    data = r.get_json()
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {data}"
    assert data["ok"] is True
    assert data["event_id"] > 0
    assert data["event_type"] == "session_start"
    # Verify in DB
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM universal_events WHERE id=?", (data["event_id"],))
    row = c.fetchone()
    conn.close()
    assert row is not None
    assert row["cli_name"] == "gemini-cli"
    assert row["agent_name"] == "planner"
    assert row["model_name"] == "gemini-2.5-pro"
run("T1: POST /api/v1/events", t1_post_events)

def t2_post_decisions():
    r = client.post("/api/v1/decisions", json={
        "title": "Use PostgreSQL for production",
        "description": "SQLite for dev, Postgres for prod",
        "category": "architectural",
        "confidence": "high",
        "rationale": "Scalability needs",
        "cli_name": "codex-cli",
        "agent_name": "architect",
        "provider": "openai",
        "model_name": "o3",
        "project_path": pp,
    })
    data = r.get_json()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {data}"
    assert data["ok"] is True
    assert data["id"] > 0
    # Verify in DB
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM decisions WHERE id=?", (data["id"],))
    row = c.fetchone()
    conn.close()
    assert row["model_used"] == "o3"
    assert row["provider"] == "openai"
    assert row["created_by"] == "architect"
run("T2: POST /api/v1/decisions", t2_post_decisions)

def t3_post_facts():
    r = client.post("/api/v1/facts", json={
        "fact": "Project uses WAL mode for SQLite",
        "fact_type": "convention",
        "category": "database",
        "confidence": "confirmed",
        "is_pinned": True,
        "source": "codex agent",
        "cli_name": "codex-cli",
        "agent_name": "learner",
        "provider": "openai",
        "model_name": "o3",
        "project_path": pp,
    })
    data = r.get_json()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {data}"
    assert data["ok"] is True
    assert data["id"] > 0
    # Verify pinned
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_pinned FROM learned_facts WHERE id=?", (data["id"],))
    assert c.fetchone()["is_pinned"] == 1
    conn.close()
run("T3: POST /api/v1/facts", t3_post_facts)

def t4_post_goals():
    r = client.post("/api/v1/goals", json={
        "title": "Complete multi-agent integration",
        "description": "Make memory work with any CLI",
        "priority": "high",
        "target_date": "2026-04-01",
        "cli_name": "gemini-cli",
        "agent_name": "planner",
        "project_path": pp,
    })
    data = r.get_json()
    assert r.status_code == 201
    assert data["ok"] is True
    assert data["id"] > 0
run("T4: POST /api/v1/goals", t4_post_goals)

def t5_post_tasks():
    r = client.post("/api/v1/tasks", json={
        "title": "Implement API auth",
        "description": "Add token-based auth",
        "priority": "high",
        "status": "todo",
        "cli_name": "claude-code",
        "agent_name": "engineer",
        "project_path": pp,
    })
    data = r.get_json()
    assert r.status_code == 201
    assert data["ok"] is True
    assert data["id"] > 0
    assert data["status"] == "todo"
run("T5: POST /api/v1/tasks", t5_post_tasks)

def t6_post_resolutions():
    r = client.post("/api/v1/resolutions", json={
        "error_summary": "ModuleNotFoundError: no module named flask",
        "resolution": "pip install flask",
        "resolution_type": "fix",
        "resolution_code": "pip install flask",
        "worked": True,
        "cli_name": "codex-cli",
        "agent_name": "debugger",
        "provider": "openai",
        "model_name": "o3",
        "project_path": pp,
    })
    data = r.get_json()
    assert r.status_code == 201
    assert data["ok"] is True
    assert data["id"] > 0
run("T6: POST /api/v1/resolutions", t6_post_resolutions)


# ===== T7-T10: GET endpoints =====
print("\n\U0001f4cb T7-T10: Universal GET endpoints")

def t7_get_context():
    r = client.get(f"/api/v1/context?project={pp}")
    data = r.get_json()
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {data}"
    assert data.get("ok") is True
    # Should have some structure
    assert "meta" in data or "decisions" in data or "facts" in data
run("T7: GET /api/v1/context", t7_get_context)

def t8_get_context_compact():
    r = client.get(f"/api/v1/context?project={pp}&mode=compact&intent=debugging&agent_name=planner&model_name=gemini-2.5")
    data = r.get_json()
    assert r.status_code == 200
    assert data.get("ok") is True
run("T8: GET /api/v1/context?mode=compact (with agent params)", t8_get_context_compact)

def t9_get_activity():
    r = client.get(f"/api/v1/activity?project={pp}")
    data = r.get_json()
    assert r.status_code == 200
    assert data["ok"] is True
    assert "activity" in data
    assert data["count"] >= 0
run("T9: GET /api/v1/activity", t9_get_activity)

def t10_get_health():
    r = client.get(f"/api/v1/health?project={pp}")
    data = r.get_json()
    assert r.status_code == 200
    assert data["ok"] is True
    assert "decisions" in data
    assert "facts" in data
    assert "events" in data
    assert data["decisions"] >= 1
    assert data["facts"] >= 1
run("T10: GET /api/v1/health", t10_get_health)


# ===== T11-T14: Validare =====
print("\n\U0001f4cb T11-T14: Validation")

def t11_invalid_payload():
    # No JSON body
    r = client.post("/api/v1/events", data="not json", content_type="text/plain")
    assert r.status_code == 400
    data = r.get_json()
    assert data["ok"] is False
    # Missing required field
    r2 = client.post("/api/v1/decisions", json={"description": "no title"})
    assert r2.status_code == 400
    data2 = r2.get_json()
    assert data2["ok"] is False
    assert "title" in data2.get("error", "")
run("T11: Invalid payload → clean error", t11_invalid_payload)

def t12_minimal_data():
    # Minimal decision — only title
    r = client.post("/api/v1/decisions", json={"title": "Minimal decision"})
    data = r.get_json()
    assert r.status_code == 201
    assert data["ok"] is True
    # Health with missing project — should still work
    r2 = client.get("/api/v1/health")
    assert r2.status_code == 200
    assert r2.get_json()["ok"] is True
run("T12: Minimal data / missing project → graceful", t12_minimal_data)

def t13_agent_fields_saved():
    conn = get_db()
    c = conn.cursor()
    # Check universal_events has cli_name, agent_name, model_name
    c.execute("SELECT cli_name, agent_name, model_name, provider FROM universal_events WHERE cli_name='gemini-cli'")
    row = c.fetchone()
    conn.close()
    assert row is not None, "Event with gemini-cli not found"
    assert row["agent_name"] == "planner"
    assert row["model_name"] == "gemini-2.5-pro"
    assert row["provider"] == "google"
run("T13: Agent metadata fields saved correctly", t13_agent_fields_saved)

def t14_context_new_agent():
    # Context with unknown agent/model — should not crash
    r = client.get(f"/api/v1/context?project={pp}&agent_name=new_agent_xyz&model_name=totally-new-model-99")
    data = r.get_json()
    assert r.status_code == 200
    assert data.get("ok") is True
run("T14: Context with new agent/model → no crash", t14_context_new_agent)


# ===== T15-T24: Regresie =====
print("\n\U0001f4cb T15-T24: Regression")

def t15_dashboard():
    r = client.get(f"/api/dashboard?project={pp}")
    assert r.status_code == 200
    data = r.get_json()
    assert "summary" in data
    assert "decisions" in data
    assert "facts" in data
run("T15: /api/dashboard still works", t15_dashboard)

def t16_old_context():
    r = client.get(f"/api/context?project={pp}&mode=compact")
    data = r.get_json()
    assert r.status_code == 200
    # Old context endpoint doesn't have "ok" field — that's fine
    assert "meta" in data or "decisions" in data or "facts" in data
run("T16: /api/context (dashboard) still works", t16_old_context)

def t17_mem_context():
    output = run_mem("context", "--mode", "compact")
    assert "decisions" in output.lower() or "context" in output.lower() or "meta" in output.lower(), f"Unexpected: {output[:200]}"
run("T17: mem context CLI", t17_mem_context)

def t18_mem_strategy():
    output = run_mem("strategy")
    # strategy should output something about mode
    assert len(output) > 5, f"Empty output: {output}"
run("T18: mem strategy CLI", t18_mem_strategy)

def t19_mem_checkpoint():
    output = run_mem("checkpoint", "list")
    assert "pre-api" in output or "checkpoint" in output.lower() or "niciun" in output.lower(), f"Unexpected: {output[:200]}"
run("T19: mem checkpoint list CLI", t19_mem_checkpoint)

def t20_mem_timeline():
    output = run_mem("timeline")
    assert len(output) > 0, "Empty timeline output"
run("T20: mem timeline CLI", t20_mem_timeline)

def t21_mem_activity():
    output = run_mem("activity")
    assert len(output) > 0, "Empty activity output"
run("T21: mem activity CLI", t21_mem_activity)

def t22_mem_dashboard():
    output = run_mem("dashboard")
    assert len(output) > 0, "Empty dashboard output"
run("T22: mem dashboard CLI", t22_mem_dashboard)

def t23_web_ui():
    html = (WEB_DIR / "index.html").read_text()
    assert "Memory Control Center" in html
    js = (WEB_DIR / "app.js").read_text()
    assert "loadDashboard" in js
    css = (WEB_DIR / "styles.css").read_text()
    assert ".toast" in css
run("T23: Web UI files intact", t23_web_ui)

def t24_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity check failed: {result}"
run("T24: PRAGMA integrity_check", t24_integrity)


# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 6 Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
