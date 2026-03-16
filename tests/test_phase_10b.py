#!/usr/bin/env python3
"""
Teste Faza 10B: Branch UI + Merge Preview

T1-T5:   POST /api/branches/switch
T6-T10:  POST /api/branches/merge (preview + execute)
T11-T15: GET endpoints (branches, compare, replay) — regression
T16-T20: UI files (HTML, CSS, JS presence)
T21-T24: Edge cases
T25-T28: Regresie generală
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
import threading
import re
from pathlib import Path
from datetime import datetime

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_10b_")
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

# Feature branch
c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
          ("feature-ui", pp, "main", "UI Feature"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Use React", "Frontend", "technical", "active", "high", pp, "feature-ui"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Tailwind CSS", "Styling", "technical", "active", "high", pp, "feature-ui"))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, branch) VALUES (?,?,?,?,?,?,?,?)",
          ("React 18 required", "technical", "frontend", "high", 0, 1, pp, "feature-ui"))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, branch) VALUES (?,?,?,?,?,?)",
          ("Build UI", "Frontend UI", "medium", "active", pp, "feature-ui"))
c.execute("INSERT INTO tasks (title, priority, status, project_path, branch) VALUES (?,?,?,?,?)",
          ("Setup React", "high", "todo", pp, "feature-ui"))
c.execute("INSERT INTO error_resolutions (error_summary, resolution, worked, project_path, branch) VALUES (?,?,?,?,?)",
          ("npm install fail", "rm node_modules && npm i", 1, pp, "feature-ui"))

# Merge-test branch
c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
          ("merge-src", pp, "main", "Merge source"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Merge10b decision", "Test", "technical", "active", "high", pp, "merge-src"))

# Conflict branch (shared title)
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Shared config", "Main version", "convention", "active", "high", pp, "main"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Shared config", "Feature version", "convention", "active", "high", pp, "feature-ui"))

# Empty branch
c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
          ("empty-branch", pp, "main", "Empty for testing"))

# Checkpoint + timeline for regression
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))
c.execute("INSERT INTO memory_checkpoints (project_path, name, description, model, intent, context_mode, decisions_count, facts_count, goals_count, tasks_count, patterns_count) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (pp, "pre-10b", "Before 10B", "opus", "feature", "auto", 2, 1, 1, 1, 1))
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path) VALUES (?,?,?,?,?)",
          ("checkpoint_create", 1, "Checkpoint: pre-10b", "5 entities", pp))

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
server = make_server("127.0.0.1", 19881, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

BASE_URL = "http://127.0.0.1:19881"

from clients.universal_memory_client import UniversalMemoryClient
client = UniversalMemoryClient(base_url=BASE_URL, project_path=pp,
                                cli_name="test-10b", agent_name="tester",
                                provider="test", model_name="test")


def post_json(path, body):
    """POST helper using raw requests."""
    import urllib.request
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


# ===== T1-T5: POST /api/branches/switch =====
print("\n\U0001f4cb T1-T5: POST /api/branches/switch")

def t1_switch_to_feature():
    r = post_json("/api/branches/switch", {"branch": "feature-ui", "project": pp})
    assert r.get("success") is True, f"Switch failed: {r}"
    assert r.get("branch") == "feature-ui", f"Wrong branch: {r}"
run("T1: switch to feature-ui", t1_switch_to_feature)

def t2_switch_to_main():
    r = post_json("/api/branches/switch", {"branch": "main", "project": pp})
    assert r.get("success") is True, f"Switch failed: {r}"
    assert r.get("branch") == "main", f"Wrong branch: {r}"
run("T2: switch to main", t2_switch_to_main)

def t3_switch_nonexistent():
    r = post_json("/api/branches/switch", {"branch": "nonexistent-xyz", "project": pp})
    assert r.get("success") is False, f"Expected failure: {r}"
run("T3: switch to nonexistent → error", t3_switch_nonexistent)

def t4_switch_empty_name():
    r = post_json("/api/branches/switch", {"branch": "", "project": pp})
    assert r.get("success") is False, f"Expected failure: {r}"
run("T4: switch empty name → error", t4_switch_empty_name)

def t5_switch_reflects_current():
    post_json("/api/branches/switch", {"branch": "feature-ui", "project": pp})
    r = client._get("/api/branches", {"project": pp})
    assert r.get("current") == "feature-ui", f"Expected feature-ui as current: {r}"
    # Switch back
    post_json("/api/branches/switch", {"branch": "main", "project": pp})
run("T5: switch reflects in GET /api/branches current", t5_switch_reflects_current)


# ===== T6-T10: POST /api/branches/merge =====
print("\n\U0001f4cb T6-T10: POST /api/branches/merge")

def t6_merge_preview():
    r = post_json("/api/branches/merge", {"source": "merge-src", "target": "main", "project": pp})
    assert r.get("needs_confirm") is True, f"Expected needs_confirm: {r}"
    assert "preview" in r, f"No preview: {r}"
    preview = r["preview"]
    assert "summary" in preview, f"No summary in preview: {preview}"
run("T6: merge preview (needs_confirm)", t6_merge_preview)

def t7_merge_execute():
    r = post_json("/api/branches/merge", {"source": "merge-src", "target": "main", "confirm": True, "project": pp})
    assert r.get("success") is True, f"Merge failed: {r}"
    assert r.get("entities_merged", 0) > 0, f"No entities merged: {r}"
run("T7: merge execute (confirm=true)", t7_merge_execute)

def t8_merge_verify_moved():
    """After merge, entities from merge-src should now be on main."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT branch FROM decisions WHERE title='Merge10b decision' AND project_path=?", (pp,))
    row = c.fetchone()
    conn.close()
    assert row is not None, "Merged decision not found"
    assert row["branch"] == "main", f"Decision not moved to main: {row['branch']}"
run("T8: verify merged entities moved to target", t8_merge_verify_moved)

def t9_merge_same_branch():
    r = post_json("/api/branches/merge", {"source": "main", "target": "main", "project": pp})
    assert r.get("success") is False, f"Expected failure: {r}"
run("T9: merge same branch → error", t9_merge_same_branch)

def t10_merge_nonexistent():
    r = post_json("/api/branches/merge", {"source": "nonexistent", "target": "main", "project": pp})
    assert r.get("success") is False, f"Expected failure: {r}"
run("T10: merge nonexistent → error", t10_merge_nonexistent)


# ===== T11-T15: GET endpoints regression =====
print("\n\U0001f4cb T11-T15: GET endpoints regression")

def t11_get_branches():
    r = client._get("/api/branches", {"project": pp})
    assert "branches" in r, f"No branches: {r}"
    names = [b["name"] for b in r["branches"]]
    assert "main" in names, f"main missing: {names}"
    assert "feature-ui" in names, f"feature-ui missing: {names}"
    assert "current" in r, f"No current: {r}"
run("T11: GET /api/branches", t11_get_branches)

def t12_get_compare():
    r = client._get("/api/branches/compare", {"project": pp, "a": "main", "b": "feature-ui"})
    assert "summary" in r, f"No summary: {r}"
    assert "only_a" in r, f"No only_a: {r}"
    assert "only_b" in r, f"No only_b: {r}"
    assert "conflicts" in r, f"No conflicts: {r}"
    s = r["summary"]
    assert s["branch_a"] == "main", f"Wrong branch_a: {s}"
    assert s["branch_b"] == "feature-ui", f"Wrong branch_b: {s}"
run("T12: GET /api/branches/compare", t12_get_compare)

def t13_get_replay():
    r = client._get("/api/branches/replay", {"project": pp, "branch": "feature-ui"})
    assert "events" in r, f"No events: {r}"
    assert r.get("branch") == "feature-ui", f"Wrong branch: {r}"
    assert len(r["events"]) > 0, f"No events found: {r}"
run("T13: GET /api/branches/replay", t13_get_replay)

def t14_compare_nonexistent():
    r = client._get("/api/branches/compare", {"project": pp, "a": "main", "b": "nonexistent"})
    assert "error" in r, f"Expected error: {r}"
run("T14: compare nonexistent → error", t14_compare_nonexistent)

def t15_replay_empty():
    r = client._get("/api/branches/replay", {"project": pp, "branch": "empty-branch"})
    assert "events" in r, f"No events key: {r}"
    assert len(r["events"]) == 0, f"Expected empty events: {r}"
run("T15: replay empty branch → empty events", t15_replay_empty)


# ===== T16-T20: UI files =====
print("\n\U0001f4cb T16-T20: UI files")

def t16_html_branches_tab():
    content = (WEB_DIR / "index.html").read_text()
    assert 'data-tab="branches"' in content, "No branches tab button"
    assert 'id="tab-branches"' in content, "No branches tab section"
run("T16: index.html has branches tab", t16_html_branches_tab)

def t17_html_branches_content():
    content = (WEB_DIR / "index.html").read_text()
    assert 'id="branches-content"' in content, "No branches-content container"
run("T17: index.html has branches-content div", t17_html_branches_content)

def t18_css_branch_styles():
    content = (WEB_DIR / "styles.css").read_text()
    assert ".branch-card" in content, "No .branch-card style"
    assert ".branch-current" in content, "No .branch-current style"
    assert ".branch-chip" in content, "No .branch-chip style"
    assert ".compare-section" in content, "No .compare-section style"
    assert ".merge-summary" in content, "No .merge-summary style"
run("T18: styles.css has branch styles", t18_css_branch_styles)

def t19_js_load_branches():
    content = (WEB_DIR / "app.js").read_text()
    assert "loadBranchesTab" in content, "No loadBranchesTab function"
    assert "doBranchSwitch" in content, "No doBranchSwitch function"
    assert "showBranchCompare" in content, "No showBranchCompare function"
    assert "showMergePreview" in content, "No showMergePreview function"
run("T19: app.js has branch functions", t19_js_load_branches)

def t20_js_branch_chip():
    content = (WEB_DIR / "app.js").read_text()
    assert "_currentBranch" in content, "No _currentBranch variable"
    assert "branch-chip" in content, "No branch-chip in topbar"
run("T20: app.js has branch chip in topbar", t20_js_branch_chip)


# ===== T21-T24: Edge cases =====
print("\n\U0001f4cb T21-T24: Edge cases")

def t21_switch_preserves_entities():
    """Switching branch doesn't modify DB entities."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM decisions WHERE project_path=?", (pp,))
    before = c.fetchone()[0]
    conn.close()

    post_json("/api/branches/switch", {"branch": "feature-ui", "project": pp})
    post_json("/api/branches/switch", {"branch": "main", "project": pp})

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM decisions WHERE project_path=?", (pp,))
    after = c.fetchone()[0]
    conn.close()
    assert before == after, f"Entity count changed: {before} → {after}"
run("T21: switch preserves entity count", t21_switch_preserves_entities)

def t22_merge_preview_has_summary():
    r = post_json("/api/branches/merge", {"source": "feature-ui", "target": "main", "project": pp})
    assert r.get("needs_confirm") is True, f"Expected preview: {r}"
    preview = r["preview"]
    s = preview.get("summary", {})
    assert "only_in_a" in s, f"No only_in_a: {s}"
    assert "only_in_b" in s, f"No only_in_b: {s}"
    assert "conflicts" in s, f"No conflicts: {s}"
run("T22: merge preview has full summary", t22_merge_preview_has_summary)

def t23_merge_no_source():
    r = post_json("/api/branches/merge", {"source": "", "target": "main", "project": pp})
    assert r.get("success") is False, f"Expected failure: {r}"
run("T23: merge empty source → error", t23_merge_no_source)

def t24_compare_identical():
    r = client._get("/api/branches/compare", {"project": pp, "a": "main", "b": "main"})
    s = r.get("summary", {})
    assert s.get("identical") is True, f"Expected identical: {s}"
run("T24: compare main vs main → identical", t24_compare_identical)


# ===== T25-T28: Regresie generală =====
print("\n\U0001f4cb T25-T28: Regresie generală")

def t25_mem_context():
    output = run_mem("context", "--compact")
    assert len(output) > 10, f"Empty context: {output}"
run("T25: mem context (regression)", t25_mem_context)

def t26_api_dashboard():
    r = client._get("/api/dashboard", {"project": pp})
    assert "summary" in r, f"No summary: {r}"
    assert "decisions" in r, f"No decisions: {r}"
run("T26: /api/dashboard (regression)", t26_api_dashboard)

def t27_api_v1_context():
    r = client._get("/api/v1/context", {"project": pp, "mode": "compact"})
    assert r.get("ok") is True, f"Expected ok: {r}"
run("T27: /api/v1/context (regression)", t27_api_v1_context)

def t28_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity failed: {result}"
run("T28: PRAGMA integrity_check", t28_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 10B Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
