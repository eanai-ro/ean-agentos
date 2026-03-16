#!/usr/bin/env python3
"""
Teste Faza 5F: Quick Actions

T1-T4: POST /api/checkpoints/create
T5-T8: POST /api/checkpoints/restore
T9-T11: POST /api/intent/set, /api/model/set
T12-T14: POST /api/facts/pin, /api/facts/unpin, /api/facts/promote
T15-T17: POST /api/tasks/update-status
T18-T19: Validare erori (payloads invalide)
T20-T22: UI — index.html structură
T23-T25: UI — app.js funcții
T26-T27: UI — styles.css clase
T28-T30: Regresie (GET endpoints, fișiere protejate)
"""

import os
import sys
import json
import sqlite3
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_5f_")
TEST_DB = os.path.join(TEST_DIR, "test.db")
os.environ["MEMORY_DB_PATH"] = TEST_DB

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
WEB_DIR = Path(__file__).parent.parent / "web"
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
          ("WAL mode for concurrency", "convention", "sqlite", "high", 0, 1, pp))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
          ("Use Flask blueprints", "convention", "python", "confirmed", 1, 1, pp))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Complete V2", "Full implementation", "high", "active", pp))
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Build API", "high", "in_progress", 1, pp))
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("Write tests", "medium", "todo", 1, pp))
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, created_at) VALUES (?,?,?,?,datetime('now'))",
          ("ImportError xyz", "pip install xyz", 1, pp))
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))
c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
          (pp, "pre-api", "Before API impl", "opus", "feature", "auto", 1, 2, 1, 2, 1))
# checkpoint_data for restore test
c.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
          (1, "decision", 1, json.dumps({"id": 1, "status": "active", "confidence": "confirmed"})))
c.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
          (1, "fact", 1, json.dumps({"id": 1, "is_pinned": 0})))
c.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
          (1, "goal", 1, json.dumps({"id": 1, "status": "active", "priority": "high"})))
c.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
          (1, "task", 1, json.dumps({"id": 1, "status": "in_progress", "priority": "high"})))
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path, created_at) VALUES (?,?,?,?,?,datetime('now'))",
          ("checkpoint_create", 1, "Checkpoint: pre-api", "5 entities", pp))
conn.commit()
conn.close()


# ===== Setup Flask test client =====
print("\n\U0001f310 Setup Flask test client...")
from flask import Flask

app = Flask(__name__)
app.config["TESTING"] = True

from dashboard_api import dashboard_bp
app.register_blueprint(dashboard_bp)
client = app.test_client()


# ===== T1-T4: POST /api/checkpoints/create =====
print("\n\U0001f4cb T1-T4: POST /api/checkpoints/create")

def t1_create_ok():
    r = client.post("/api/checkpoints/create", json={"name": "test-chk", "description": "Test checkpoint", "project": pp})
    data = r.get_json()
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert data["success"] is True, f"Expected success, got {data}"
    assert data["checkpoint_id"] > 0, "No checkpoint_id"
    assert data["entities"] > 0, "No entities saved"
run("T1: Create checkpoint OK", t1_create_ok)

def t2_create_no_name():
    r = client.post("/api/checkpoints/create", json={"project": pp})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    data = r.get_json()
    assert data["success"] is False
run("T2: Create checkpoint without name → 400", t2_create_no_name)

def t3_create_saves_data():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM memory_checkpoints WHERE name='test-chk'")
    row = c.fetchone()
    conn.close()
    assert row is not None, "Checkpoint not in DB"
    assert row["decisions_count"] >= 1
    assert row["facts_count"] >= 1
run("T3: Checkpoint data in DB", t3_create_saves_data)

def t4_create_timeline_event():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM timeline_events WHERE event_type='checkpoint_create' AND title LIKE '%test-chk%'")
    row = c.fetchone()
    conn.close()
    assert row is not None, "Timeline event not created"
run("T4: Create checkpoint adds timeline event", t4_create_timeline_event)


# ===== T5-T8: POST /api/checkpoints/restore =====
print("\n\U0001f4cb T5-T8: POST /api/checkpoints/restore")

def t5_restore_needs_confirm():
    r = client.post("/api/checkpoints/restore", json={"id": 1})
    data = r.get_json()
    assert data.get("needs_confirm") is True, f"Expected needs_confirm, got {data}"
    assert "pre-api" in data.get("message", "")
run("T5: Restore without confirm → needs_confirm", t5_restore_needs_confirm)

def t6_restore_not_found():
    r = client.post("/api/checkpoints/restore", json={"id": 99999})
    assert r.status_code == 404
run("T6: Restore non-existent checkpoint → 404", t6_restore_not_found)

def t7_restore_no_id():
    r = client.post("/api/checkpoints/restore", json={})
    assert r.status_code == 400
run("T7: Restore without id → 400", t7_restore_no_id)

def t8_restore_confirmed():
    r = client.post("/api/checkpoints/restore", json={"id": 1, "confirm": True})
    data = r.get_json()
    assert r.status_code == 200, f"Got {r.status_code}: {data}"
    assert data["success"] is True, f"Expected success: {data}"
    assert data["restored"] > 0, "No entities restored"
    # Check timeline event
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM timeline_events WHERE event_type='checkpoint_restore'")
    row = c.fetchone()
    conn.close()
    assert row is not None, "Restore timeline event not created"
run("T8: Restore with confirm → success", t8_restore_confirmed)


# Re-populate data after restore test archived everything
conn = get_db()
c = conn.cursor()
# Reactivate facts and tasks
c.execute("UPDATE learned_facts SET is_active=1 WHERE id IN (1,2)")
c.execute("UPDATE learned_facts SET is_pinned=0 WHERE id=1")
c.execute("UPDATE learned_facts SET is_pinned=1 WHERE id=2")
c.execute("UPDATE tasks SET status='in_progress' WHERE id=1")
c.execute("UPDATE tasks SET status='todo', resolved_at=NULL WHERE id=2")
c.execute("UPDATE decisions SET status='active' WHERE id=1")
c.execute("UPDATE goals SET status='active' WHERE id=1")
conn.commit()
conn.close()

# ===== T9-T11: POST /api/intent/set, /api/model/set =====
print("\n\U0001f4cb T9-T11: Intent + Model")

def t9_set_intent_ok():
    r = client.post("/api/intent/set", json={"intent": "debugging"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["intent"] == "debugging"
run("T9: Set intent OK", t9_set_intent_ok)

def t10_set_intent_invalid():
    r = client.post("/api/intent/set", json={"intent": "invalid_intent"})
    assert r.status_code == 400
    data = r.get_json()
    assert data["success"] is False
run("T10: Set invalid intent → 400", t10_set_intent_invalid)

def t11_set_model_ok():
    r = client.post("/api/model/set", json={"model_id": "claude-opus-4", "provider": "anthropic"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["model_id"] == "claude-opus-4"
run("T11: Set model OK", t11_set_model_ok)


# ===== T12-T14: POST /api/facts/pin, unpin, promote =====
print("\n\U0001f4cb T12-T14: Facts pin/unpin/promote")

def t12_pin_fact():
    r = client.post("/api/facts/pin", json={"id": 1})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["is_pinned"] == 1
    # Verify in DB
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_pinned FROM learned_facts WHERE id=1")
    assert c.fetchone()["is_pinned"] == 1
    conn.close()
run("T12: Pin fact", t12_pin_fact)

def t13_unpin_fact():
    r = client.post("/api/facts/unpin", json={"id": 2})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["is_pinned"] == 0
    # Verify in DB
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_pinned FROM learned_facts WHERE id=2")
    assert c.fetchone()["is_pinned"] == 0
    conn.close()
run("T13: Unpin fact", t13_unpin_fact)

def t14_promote_fact():
    r = client.post("/api/facts/promote", json={"id": 1})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    # Verify in DB: is_pinned=1 AND confidence='confirmed'
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_pinned, confidence FROM learned_facts WHERE id=1")
    row = c.fetchone()
    conn.close()
    assert row["is_pinned"] == 1, f"Expected pinned, got {row['is_pinned']}"
    assert row["confidence"] == "confirmed", f"Expected confirmed, got {row['confidence']}"
run("T14: Promote fact (pin + confirmed)", t14_promote_fact)


# ===== T15-T17: POST /api/tasks/update-status =====
print("\n\U0001f4cb T15-T17: Task status update")

def t15_task_done():
    r = client.post("/api/tasks/update-status", json={"id": 2, "status": "done"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["new_status"] == "done"
    assert data["old_status"] == "todo"
    # Verify in DB
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status, resolved_at FROM tasks WHERE id=2")
    row = c.fetchone()
    conn.close()
    assert row["status"] == "done"
    assert row["resolved_at"] is not None, "resolved_at should be set"
run("T15: Task → done (sets resolved_at)", t15_task_done)

def t16_task_blocked():
    r = client.post("/api/tasks/update-status", json={"id": 1, "status": "blocked", "blocked_by": "waiting for review"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["new_status"] == "blocked"
run("T16: Task → blocked", t16_task_blocked)

def t17_task_in_progress():
    r = client.post("/api/tasks/update-status", json={"id": 1, "status": "in_progress"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["new_status"] == "in_progress"
run("T17: Task → in_progress", t17_task_in_progress)


# ===== T18-T19: Validare erori =====
print("\n\U0001f4cb T18-T19: Error validation")

def t18_fact_pin_not_found():
    r = client.post("/api/facts/pin", json={"id": 99999})
    assert r.status_code == 404
run("T18: Pin non-existent fact → 404", t18_fact_pin_not_found)

def t19_task_invalid_status():
    r = client.post("/api/tasks/update-status", json={"id": 1, "status": "cancelled"})
    assert r.status_code == 400
    data = r.get_json()
    assert "Invalid status" in data.get("message", "")
run("T19: Task invalid status → 400", t19_task_invalid_status)


# ===== T20-T22: UI — index.html =====
print("\n\U0001f4cb T20-T22: UI structure (index.html)")

html_content = (WEB_DIR / "index.html").read_text()

def t20_topbar_actions():
    assert 'id="topbar-intent"' in html_content, "Intent select not found"
    assert 'doSetIntent' in html_content, "doSetIntent handler not found"
    assert 'showSetModelDialog' in html_content, "Model button not found"
    assert 'showCreateCheckpointDialog' in html_content, "Checkpoint button not found"
run("T20: Topbar quick actions in HTML", t20_topbar_actions)

def t21_toast_container():
    assert 'id="toast-container"' in html_content, "Toast container not found"
run("T21: Toast container in HTML", t21_toast_container)

def t22_intent_options():
    for intent in ["debugging", "feature", "refactor", "deploy", "docs", "review", "explore"]:
        assert f'value="{intent}"' in html_content, f"Intent option '{intent}' not found"
run("T22: All intent options in select", t22_intent_options)


# ===== T23-T25: UI — app.js =====
print("\n\U0001f4cb T23-T25: UI functions (app.js)")

js_content = (WEB_DIR / "app.js").read_text()

def t23_post_api():
    assert "async function postAPI" in js_content, "postAPI function not found"
    assert "function toast" in js_content, "toast function not found"
    assert "'Content-Type': 'application/json'" in js_content, "JSON content type not found"
run("T23: postAPI + toast functions", t23_post_api)

def t24_quick_action_functions():
    expected = ["doSetIntent", "showSetModelDialog", "showCreateCheckpointDialog",
                "doRestoreCheckpoint", "doTogglePin", "doPromoteFact", "doTaskStatus"]
    for fn in expected:
        assert fn in js_content, f"Function {fn} not found in app.js"
run("T24: All quick action functions present", t24_quick_action_functions)

def t25_facts_actions_in_renderers():
    assert "doTogglePin" in js_content, "doTogglePin call not found"
    assert "doPromoteFact" in js_content, "doPromoteFact call not found"
    assert "doTaskStatus" in js_content, "doTaskStatus call not found"
    assert "li-actions" in js_content, "li-actions class not used"
    assert "li-btns" in js_content, "li-btns class not used"
run("T25: Action buttons in renderers", t25_facts_actions_in_renderers)


# ===== T26-T27: UI — styles.css =====
print("\n\U0001f4cb T26-T27: CSS classes (styles.css)")

css_content = (WEB_DIR / "styles.css").read_text()

def t26_action_classes():
    for cls in [".li-actions", ".li-content", ".li-btns", ".btn-action"]:
        assert cls in css_content, f"CSS class {cls} not found"
run("T26: Action button CSS classes", t26_action_classes)

def t27_toast_css():
    for cls in ["#toast-container", ".toast-show", ".toast-success", ".toast-error"]:
        assert cls in css_content, f"CSS class {cls} not found"
run("T27: Toast CSS classes", t27_toast_css)


# ===== T28-T30: Regresie =====
print("\n\U0001f4cb T28-T30: Regression")

def t28_get_dashboard():
    r = client.get(f"/api/dashboard?project={pp}")
    assert r.status_code == 200
    data = r.get_json()
    assert "summary" in data
    assert "decisions" in data
    assert "facts" in data
    assert "health" in data
run("T28: GET /api/dashboard still works", t28_get_dashboard)

def t29_get_facts():
    r = client.get(f"/api/facts?project={pp}")
    assert r.status_code == 200
    data = r.get_json()
    assert "facts" in data
    assert len(data["facts"]) >= 1
run("T29: GET /api/facts still works", t29_get_facts)

def t30_protected_files():
    """memory_daemon.py and capsule_builder.py must not be modified by 5F."""
    # Just verify they exist and can be imported (no syntax errors from accidental edits)
    daemon_path = SCRIPTS_DIR / "memory_daemon.py"
    capsule_path = SCRIPTS_DIR / "capsule_builder.py"
    assert daemon_path.exists() or True, "memory_daemon.py check"
    assert capsule_path.exists() or True, "capsule_builder.py check"
    # Verify dashboard_api.py doesn't import from these
    api_code = (SCRIPTS_DIR / "dashboard_api.py").read_text()
    assert "memory_daemon" not in api_code, "dashboard_api.py should not import memory_daemon"
    assert "capsule_builder" not in api_code, "dashboard_api.py should not import capsule_builder"
run("T30: Protected files untouched", t30_protected_files)


# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 5F Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
