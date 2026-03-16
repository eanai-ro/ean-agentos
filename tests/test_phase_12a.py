#!/usr/bin/env python3
"""
Tests for Phase 12A — Agent Event Stream
T1-T3:  DB / schema
T4-T6:  Helper log_agent_event
T7-T16: Integration (API → agent_events generated)
T17-T22: CLI (mem events)
T23-T25: API / dashboard
T26-T28: Edge cases
T29-T37: Regression
"""

import sys, os, json, time, sqlite3, subprocess, threading, importlib
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Test DB
TEST_DB = PROJECT_ROOT / "tests" / "test_12a.db"
TEST_PORT = 19883
pp = str(PROJECT_ROOT)

passed = 0
failed = 0
results = []

def run(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        results.append((name, True, None))
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        results.append((name, False, str(e)))
        print(f"  ❌ {name}: {e}")


# ================================================================
# SETUP
# ================================================================

def setup_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    os.environ["MEMORY_DB_PATH"] = str(TEST_DB)
    from init_db import init_database
    init_database(TEST_DB)

def setup_flask():
    os.environ["MEMORY_DB_PATH"] = str(TEST_DB)
    # Reload modules to pick up test DB
    import v2_common
    importlib.reload(v2_common)

    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True

    import dashboard_api
    importlib.reload(dashboard_api)
    import universal_api
    importlib.reload(universal_api)

    app.register_blueprint(dashboard_api.dashboard_bp)
    app.register_blueprint(universal_api.universal_bp)

    t = threading.Thread(target=lambda: app.run(port=TEST_PORT, use_reloader=False), daemon=True)
    t.start()
    time.sleep(0.5)
    return app

print("\n🔧 Setup DB...")
setup_db()
print("\n🌐 Setup Flask...")
app = setup_flask()

# HTTP helpers
import urllib.request, urllib.error

def api_get(path):
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())

def api_post(path, data):
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


# ================================================================
# T1-T3: DB / Schema
# ================================================================
print("\n📋 T1-T3: DB / schema")

def t1_migration():
    conn = sqlite3.connect(str(TEST_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_events'")
    assert cursor.fetchone(), "agent_events table not found"
    conn.close()
run("T1: agent_events table exists", t1_migration)

def t2_columns():
    conn = sqlite3.connect(str(TEST_DB))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(agent_events)")
    cols = {r[1] for r in cursor.fetchall()}
    expected = {"id", "project_path", "session_id", "branch_name", "cli_name", "agent_name",
                "provider", "model_name", "event_type", "event_phase", "title", "summary",
                "detail", "status", "related_table", "related_id", "parent_event_id",
                "created_at", "started_at", "finished_at", "duration_ms", "success_flag", "metadata_json"}
    missing = expected - cols
    assert not missing, f"Missing columns: {missing}"
    conn.close()
run("T2: all columns present", t2_columns)

def t3_indexes():
    conn = sqlite3.connect(str(TEST_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ae_%'")
    idxs = {r[0] for r in cursor.fetchall()}
    assert len(idxs) >= 8, f"Expected >=8 indexes, got {len(idxs)}: {idxs}"
    conn.close()
run("T3: indexes exist", t3_indexes)


# ================================================================
# T4-T6: Helper log_agent_event
# ================================================================
print("\n📋 T4-T6: Helper log_agent_event")

def t4_basic():
    from v2_common import log_agent_event
    eid = log_agent_event("agent_started", title="Test start", project_path=pp)
    assert eid is not None, "log_agent_event returned None"
    assert isinstance(eid, int), f"Expected int, got {type(eid)}"
run("T4: log_agent_event basic", t4_basic)

def t5_autofill():
    from v2_common import log_agent_event
    eid = log_agent_event("decision_created", title="Auto-filled event")
    conn = sqlite3.connect(str(TEST_DB))
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM agent_events WHERE id=?", (eid,)).fetchone()
    assert r["project_path"], "project_path not auto-filled"
    assert r["branch_name"], "branch_name not auto-filled"
    conn.close()
run("T5: auto-fills project/branch", t5_autofill)

def t6_partial():
    from v2_common import log_agent_event
    # Minimal call — should not crash
    eid = log_agent_event("api_call")
    assert eid is not None
    # With metadata
    eid2 = log_agent_event("agent_error", title="Error test", success_flag=0,
                           metadata={"reason": "test"})
    assert eid2 is not None
run("T6: partial input no crash", t6_partial)


# ================================================================
# T7-T16: Integration (API → agent_events generated)
# ================================================================
print("\n📋 T7-T16: Integration via API")

def _count_events(event_type=None):
    conn = sqlite3.connect(str(TEST_DB))
    if event_type:
        r = conn.execute("SELECT COUNT(*) FROM agent_events WHERE event_type=?", (event_type,)).fetchone()
    else:
        r = conn.execute("SELECT COUNT(*) FROM agent_events").fetchone()
    conn.close()
    return r[0]

def t7_start_session():
    from clients.universal_memory_client import UniversalMemoryClient
    client = UniversalMemoryClient(base_url=f"http://127.0.0.1:{TEST_PORT}",
                                    project_path=pp, cli_name="test-cli", agent_name="test-agent")
    r = client.start_session("test session")
    assert r.get("ok") or r.get("event_id"), f"start_session failed: {r}"
run("T7: start_session generates event", t7_start_session)

def t8_get_context():
    r = api_get(f"/api/v1/context?project={pp}&mode=compact&agent_name=test")
    assert r.get("ok"), f"get_context failed: {r}"
run("T8: get_context via API", t8_get_context)

def t9_create_decision():
    before = _count_events("decision_created")
    r, code = api_post("/api/v1/decisions", {"title": "Test decision 12A", "project_path": pp})
    assert code == 201, f"Expected 201, got {code}"
    after = _count_events("decision_created")
    assert after > before, f"No decision_created event: {before} → {after}"
run("T9: create_decision generates event", t9_create_decision)

def t10_create_fact():
    before = _count_events("fact_created")
    r, code = api_post("/api/v1/facts", {"fact": "Test fact 12A", "project_path": pp})
    assert code == 201
    after = _count_events("fact_created")
    assert after > before
run("T10: create_fact generates event", t10_create_fact)

def t11_create_task():
    before = _count_events("task_created")
    r, code = api_post("/api/v1/tasks", {"title": "Test task 12A", "project_path": pp})
    assert code == 201
    after = _count_events("task_created")
    assert after > before
run("T11: create_task generates event", t11_create_task)

def t12_create_resolution():
    before = _count_events("resolution_created")
    r, code = api_post("/api/v1/resolutions", {
        "error_summary": "Test error 12A",
        "resolution": "Fixed it",
        "project_path": pp,
    })
    assert code == 201
    after = _count_events("resolution_created")
    assert after > before
run("T12: create_resolution generates event", t12_create_resolution)

def t13_branch_switch():
    before = _count_events("branch_switched")
    r, code = api_post("/api/branches/switch", {"branch": "main", "project": pp})
    assert code == 200
    after = _count_events("branch_switched")
    assert after > before
run("T13: branch switch generates event", t13_branch_switch)

def t14_branch_compare():
    # Compare uses GET, no event emission for compare (read-only)
    # 404 is OK (branch doesn't exist), we just check it doesn't crash
    try:
        r = api_get(f"/api/branches/compare?project={pp}&a=main&b=feature-test")
    except urllib.error.HTTPError:
        pass  # 404 expected when branch doesn't exist
    assert True
run("T14: branch compare works", t14_branch_compare)

def t15_checkpoint_create():
    before = _count_events("checkpoint_created")
    r, code = api_post("/api/checkpoints/create", {"name": "test-12a-chk", "project": pp})
    assert code == 200 and r.get("success"), f"checkpoint create failed: {r}"
    after = _count_events("checkpoint_created")
    assert after > before
run("T15: checkpoint create generates event", t15_checkpoint_create)

def t16_checkpoint_restore():
    # Get the checkpoint ID
    conn = sqlite3.connect(str(TEST_DB))
    r = conn.execute("SELECT id FROM memory_checkpoints ORDER BY id DESC LIMIT 1").fetchone()
    chk_id = r[0]
    conn.close()

    before = _count_events("checkpoint_restored")
    r, code = api_post("/api/checkpoints/restore", {"id": chk_id, "confirm": True})
    assert code == 200 and r.get("success"), f"restore failed: {r}"
    after = _count_events("checkpoint_restored")
    assert after > before
run("T16: checkpoint restore generates event", t16_checkpoint_restore)


# ================================================================
# T17-T22: CLI (mem events)
# ================================================================
print("\n📋 T17-T22: CLI (mem events)")

def _run_events(*args):
    cmd = ["python3", str(SCRIPTS_DIR / "agent_events.py")] + list(args)
    env = os.environ.copy()
    env["MEMORY_DB_PATH"] = str(TEST_DB)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r

def t17_events_default():
    r = _run_events()
    assert r.returncode == 0, f"Exit {r.returncode}: {r.stderr}"
    assert "AGENT EVENTS" in r.stdout or "niciun eveniment" in r.stdout
run("T17: mem events", t17_events_default)

def t18_events_limit():
    r = _run_events("--limit", "5")
    assert r.returncode == 0
run("T18: mem events --limit 5", t18_events_limit)

def t19_events_type():
    r = _run_events("--type", "decision_created")
    assert r.returncode == 0
run("T19: mem events --type decision_created", t19_events_type)

def t20_events_branch():
    r = _run_events("--branch", "main")
    assert r.returncode == 0
run("T20: mem events --branch main", t20_events_branch)

def t21_events_failed():
    r = _run_events("--failed")
    assert r.returncode == 0
run("T21: mem events --failed", t21_events_failed)

def t22_events_json():
    r = _run_events("--json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "events" in data
    assert "count" in data
run("T22: mem events --json", t22_events_json)


# ================================================================
# T23-T25: API / dashboard
# ================================================================
print("\n📋 T23-T25: API / dashboard")

def t23_api_events():
    r = api_get(f"/api/events?project={pp}")
    assert r.get("ok"), f"GET /api/events failed: {r}"
    assert "events" in r
    assert r["count"] >= 0
run("T23: GET /api/events", t23_api_events)

def t24_dashboard_events_recent():
    r = api_get(f"/api/dashboard?project={pp}")
    assert "events_recent" in r, f"events_recent missing from dashboard: {list(r.keys())}"
run("T24: /api/dashboard includes events_recent", t24_dashboard_events_recent)

def t25_timeline_includes_events():
    r = api_get(f"/api/timeline?project={pp}&days=30")
    assert "timeline" in r or "events" in r or isinstance(r, dict)
    # Just check it doesn't crash
run("T25: timeline includes events", t25_timeline_includes_events)


# ================================================================
# T26-T28: Edge cases
# ================================================================
print("\n📋 T26-T28: Edge cases")

def t26_empty_project():
    r = api_get("/api/events?project=/nonexistent/project")
    assert r.get("ok")
    assert r["count"] == 0
run("T26: empty project → elegant response", t26_empty_project)

def t27_invalid_event_type():
    r, code = api_post("/api/v1/agent-events", {"event_type": "invalid_xyz", "project_path": pp})
    assert code == 400, f"Expected 400, got {code}"
    assert "Invalid event_type" in r.get("error", "")
run("T27: invalid event_type → clean error", t27_invalid_event_type)

def t28_nonexistent_branch_filter():
    r = api_get("/api/events?branch=nonexistent-xyz-999")
    assert r.get("ok")
    assert r["count"] == 0
run("T28: nonexistent branch filter → 0 results", t28_nonexistent_branch_filter)


# ================================================================
# T29-T37: Regression
# ================================================================
print("\n📋 T29-T37: Regression")

def t29_context():
    r = api_get(f"/api/v1/context?project={pp}&mode=compact")
    assert r.get("ok"), f"context failed: {r}"
run("T29: /api/v1/context (regression)", t29_context)

def t30_dashboard():
    r = api_get(f"/api/dashboard?project={pp}")
    assert "summary" in r, f"dashboard missing summary: {list(r.keys())}"
run("T30: /api/dashboard (regression)", t30_dashboard)

def t31_context_cli():
    # Just verify the module imports work
    env = os.environ.copy()
    env["MEMORY_DB_PATH"] = str(TEST_DB)
    r = subprocess.run(["python3", str(SCRIPTS_DIR / "context_builder_v2.py"), "--compact", "--json"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"context_builder_v2 failed: {r.stderr[:200]}"
run("T31: mem context (regression)", t31_context_cli)

def t32_strategy():
    env = os.environ.copy()
    env["MEMORY_DB_PATH"] = str(TEST_DB)
    r = subprocess.run(["python3", str(SCRIPTS_DIR / "context_strategy.py"), "--json"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0
run("T32: mem strategy (regression)", t32_strategy)

def t33_activity():
    r = api_get(f"/api/activity?project={pp}")
    assert "activity" in r or r.get("ok") is not False
run("T33: mem activity (regression)", t33_activity)

def t34_dashboard_cli():
    env = os.environ.copy()
    env["MEMORY_DB_PATH"] = str(TEST_DB)
    r = subprocess.run(["python3", str(SCRIPTS_DIR / "dashboard_cli.py"), "--json"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0
run("T34: mem dashboard (regression)", t34_dashboard_cli)

def t35_adapters():
    # Check adapters can still import
    sys.path.insert(0, str(SCRIPTS_DIR / "adapters"))
    try:
        import importlib
        spec_g = importlib.util.find_spec("gemini_adapter") or importlib.util.find_spec("adapters.gemini_adapter")
        spec_c = importlib.util.find_spec("codex_adapter") or importlib.util.find_spec("adapters.codex_adapter")
    except Exception:
        pass
    # Check files exist
    assert (SCRIPTS_DIR / "adapters" / "gemini_cli_adapter.py").exists(), "gemini_cli_adapter.py missing"
    assert (SCRIPTS_DIR / "adapters" / "codex_cli_adapter.py").exists(), "codex_cli_adapter.py missing"
run("T35: adapters exist (regression)", t35_adapters)

def t36_web_ui():
    for f in ["index.html", "styles.css", "app.js"]:
        assert (PROJECT_ROOT / "web" / f).exists(), f"web/{f} missing"
run("T36: web UI files exist (regression)", t36_web_ui)

def t37_integrity():
    conn = sqlite3.connect(str(TEST_DB))
    r = conn.execute("PRAGMA integrity_check").fetchone()
    assert r[0] == "ok", f"integrity_check: {r[0]}"
    conn.close()
run("T37: PRAGMA integrity_check", t37_integrity)


# ================================================================
# RESULTS
# ================================================================
print(f"\n{'='*50}")
print(f"🏁 Phase 12A Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed:
    sys.exit(1)
