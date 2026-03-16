#!/usr/bin/env python3
"""
Teste Faza 8B: Generic Python Client (UniversalMemoryClient)

T1-T10:  UniversalMemoryClient direct usage
T11-T13: Adapter refactor (Gemini + Codex deleghează la client)
T14-T16: DB/API metadata verification
T17-T25: Regresie generală
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_8b_")
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

server = make_server("127.0.0.1", 19878, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

BASE_URL = "http://127.0.0.1:19878"

# Import all three: client, gemini adapter, codex adapter
sys.path.insert(0, str(SCRIPTS_DIR))
from clients.universal_memory_client import UniversalMemoryClient

sys.path.insert(0, str(SCRIPTS_DIR / "adapters"))
from gemini_cli_adapter import GeminiMemoryAdapter
from codex_cli_adapter import CodexMemoryAdapter

# Create direct client
client = UniversalMemoryClient(
    base_url=BASE_URL,
    project_path=pp,
    cli_name="python-test",
    agent_name="test-agent",
    provider="test",
    model_name="test-model",
)

# Create adapters (refactored)
gemini = GeminiMemoryAdapter(
    base_url=BASE_URL,
    project_path=pp,
    cli_name="gemini-cli",
    agent_name="gemini-planner",
    provider="google",
    model_name="gemini-2.5-pro",
)

codex = CodexMemoryAdapter(
    base_url=BASE_URL,
    project_path=pp,
    cli_name="codex-cli",
    agent_name="codex",
    provider="openai",
    model_name="o3",
)


# ===== T1-T10: UniversalMemoryClient direct =====
print("\n\U0001f4cb T1-T10: UniversalMemoryClient direct")

def t1_start_session():
    r = client.start_session("Test direct client session")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
    assert r.get("event_type") == "session_start"
run("T1: start_session", t1_start_session)

def t2_get_context():
    r = client.get_context(mode="compact", intent="feature")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert "meta" in r or "decisions" in r or "facts" in r
run("T2: get_context", t2_get_context)

def t3_create_decision():
    r = client.create_decision(
        "Use Redis for caching",
        description="Fast key-value store",
        category="infrastructure",
        rationale="Sub-ms latency",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T3: create_decision", t3_create_decision)

def t4_create_fact():
    r = client.create_fact(
        "Project uses Python 3.11",
        fact_type="technical",
        category="runtime",
        source="direct client test",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T4: create_fact", t4_create_fact)

def t5_create_goal():
    r = client.create_goal(
        "Ship v2.0",
        description="Complete rewrite",
        priority="high",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T5: create_goal", t5_create_goal)

def t6_create_task():
    r = client.create_task(
        "Write migration scripts",
        description="DB schema changes",
        priority="high",
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
    assert r.get("status") == "todo"
run("T6: create_task", t6_create_task)

def t7_create_resolution():
    r = client.create_resolution(
        error_summary="ConnectionError: timeout",
        resolution="Increase timeout to 30s",
        resolution_type="fix",
        worked=True,
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("id") > 0
run("T7: create_resolution", t7_create_resolution)

def t8_send_event():
    r = client.send_event(
        "agent_activity",
        title="Analyzed project structure",
        payload={"files_scanned": 42},
    )
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("event_id") > 0
run("T8: send_event", t8_send_event)

def t9_get_activity():
    r = client.get_activity(limit=10)
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert r.get("count", 0) >= 1
run("T9: get_activity", t9_get_activity)

def t10_get_health():
    r = client.get_health()
    assert r.get("ok") is True, f"Expected ok, got {r}"
    assert "decisions" in r or "counts" in r or "health" in r or "active" in r
run("T10: get_health", t10_get_health)


# ===== T11-T13: Adapter refactor =====
print("\n\U0001f4cb T11-T13: Adapter refactor")

def t11_gemini_via_client():
    r = gemini.start_session("Gemini refactored test")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    r2 = gemini.create_decision("Use Cloud Run", description="Serverless containers")
    assert r2.get("ok") is True
    r3 = gemini.create_fact("GCP is primary cloud", fact_type="convention")
    assert r3.get("ok") is True
    r4 = gemini.log_activity("Reviewed architecture")
    assert r4.get("ok") is True
    # Verify adapter exposes _client internally
    assert hasattr(gemini, '_client')
    assert isinstance(gemini._client, UniversalMemoryClient)
run("T11: Gemini adapter uses UniversalMemoryClient", t11_gemini_via_client)

def t12_codex_via_client():
    r = codex.start_session("Codex refactored test")
    assert r.get("ok") is True, f"Expected ok, got {r}"
    r2 = codex.create_decision("Use TypeScript", description="Type safety")
    assert r2.get("ok") is True
    r3 = codex.create_fact("ESLint configured", fact_type="convention")
    assert r3.get("ok") is True
    r4 = codex.log_activity("Linted codebase")
    assert r4.get("ok") is True
    assert hasattr(codex, '_client')
    assert isinstance(codex._client, UniversalMemoryClient)
run("T12: Codex adapter uses UniversalMemoryClient", t12_codex_via_client)

def t13_public_interface_preserved():
    # Verify all public attributes exist on adapters
    for adapter, name in [(gemini, "Gemini"), (codex, "Codex")]:
        assert hasattr(adapter, 'base_url'), f"{name} missing base_url"
        assert hasattr(adapter, 'project_path'), f"{name} missing project_path"
        assert hasattr(adapter, 'cli_name'), f"{name} missing cli_name"
        assert hasattr(adapter, 'agent_name'), f"{name} missing agent_name"
        assert hasattr(adapter, 'provider'), f"{name} missing provider"
        assert hasattr(adapter, 'model_name'), f"{name} missing model_name"
        assert hasattr(adapter, 'session_id'), f"{name} missing session_id"
        # Verify all public methods
        for method in ['start_session', 'get_context', 'create_decision', 'create_fact',
                       'create_goal', 'create_task', 'create_resolution', 'log_activity',
                       'send_event', 'get_activity', 'get_health', '_get', '_post']:
            assert callable(getattr(adapter, method, None)), f"{name} missing {method}"
    # Verify correct defaults
    assert gemini.cli_name == "gemini-cli"
    assert gemini.provider == "google"
    assert codex.cli_name == "codex-cli"
    assert codex.provider == "openai"
    assert gemini.session_id.startswith("gemini_")
    assert codex.session_id.startswith("codex_")
run("T13: Public interfaces preserved", t13_public_interface_preserved)


# ===== T14-T16: DB/API metadata =====
print("\n\U0001f4cb T14-T16: DB/API metadata")

def t14_client_metadata_in_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM universal_events WHERE cli_name='python-test' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    assert row is not None, "No python-test events found"
    assert row["agent_name"] == "test-agent"
    assert row["provider"] == "test"
    assert row["model_name"] == "test-model"
    assert row["session_id"] == client.session_id
run("T14: Direct client metadata saved correctly", t14_client_metadata_in_db)

def t15_all_cli_names_coexist():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT cli_name FROM universal_events ORDER BY cli_name")
    cli_names = [row[0] for row in c.fetchall()]
    conn.close()
    assert "python-test" in cli_names, f"python-test missing from {cli_names}"
    assert "gemini-cli" in cli_names, f"gemini-cli missing from {cli_names}"
    assert "codex-cli" in cli_names, f"codex-cli missing from {cli_names}"
run("T15: All 3 cli_names coexist in universal_events", t15_all_cli_names_coexist)

def t16_context_for_all_agents():
    for agent, name in [(client, "direct"), (gemini, "gemini"), (codex, "codex")]:
        r = agent.get_context(mode="compact")
        assert r.get("ok") is True, f"Context failed for {name}: {r}"
        meta = r.get("meta", {})
        assert meta.get("requesting_agent") == agent.agent_name, \
            f"Wrong agent for {name}: expected {agent.agent_name}, got {meta.get('requesting_agent')}"
run("T16: Context works for all 3 agents", t16_context_for_all_agents)


# ===== T17-T25: Regresie generală =====
print("\n\U0001f4cb T17-T25: Regresie generală")

def t17_api_v1_context():
    r = client._get("/api/v1/context", {"project": pp, "mode": "compact"})
    assert r.get("ok") is True
run("T17: /api/v1/context", t17_api_v1_context)

def t18_api_v1_activity():
    r = client._get("/api/v1/activity", {"project": pp, "limit": "5"})
    assert r.get("ok") is True
run("T18: /api/v1/activity", t18_api_v1_activity)

def t19_api_dashboard():
    r = client._get("/api/dashboard", {"project": pp})
    assert "summary" in r
    assert "decisions" in r
    assert "facts" in r
run("T19: /api/dashboard", t19_api_dashboard)

def t20_mem_context():
    output = run_mem("context", "--mode", "compact")
    assert len(output) > 5, f"Empty: {output}"
run("T20: mem context CLI", t20_mem_context)

def t21_mem_strategy():
    output = run_mem("strategy")
    assert len(output) > 5, f"Empty: {output}"
run("T21: mem strategy CLI", t21_mem_strategy)

def t22_mem_activity():
    output = run_mem("activity")
    assert len(output) > 0
run("T22: mem activity CLI", t22_mem_activity)

def t23_mem_dashboard():
    output = run_mem("dashboard")
    assert len(output) > 0
run("T23: mem dashboard CLI", t23_mem_dashboard)

def t24_web_ui():
    html = (WEB_DIR / "index.html").read_text()
    assert "Memory Control Center" in html
    assert "tab-errors" in html
    js = (WEB_DIR / "app.js").read_text()
    assert "loadDashboard" in js
    assert "loadErrorsTab" in js
run("T24: Web UI files intact", t24_web_ui)

def t25_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity check failed: {result}"
run("T25: PRAGMA integrity_check", t25_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 8B Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
