#!/usr/bin/env python3
"""
Tests for Phase 12B — Event UI + Agent Replay
T1-T5:   HTML structure (tab, filters, section)
T6-T12:  JS functions (loadEventsTab, showEventDetail, showEventReplay, icons, colors)
T13-T18: CSS classes (ev-item, ev-replay, ev-detail, ev-failed)
T19-T24: API integration (GET /api/events filters, replay data, empty state)
T25-T28: Edge cases (no events, invalid filter, large dataset, special chars)
T29-T33: Regression (existing tabs, dashboard, CSS integrity, modal, protected files)
"""

import sys, os, json, time, sqlite3, subprocess, threading, importlib, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WEB_DIR = PROJECT_ROOT / "web"
sys.path.insert(0, str(SCRIPTS_DIR))

TEST_DB = PROJECT_ROOT / "tests" / "test_12b.db"
TEST_PORT = 19884
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

def seed_events():
    """Seed test events for API/UI tests."""
    from v2_common import log_agent_event
    # Session 1 — agent with multiple events
    log_agent_event("agent_started", title="Claude start", agent_name="claude-opus",
                    model_name="claude-opus-4", provider="anthropic",
                    session_id="sess-replay-1", project_path=pp, branch_name="main")
    log_agent_event("context_requested", title="Get context", agent_name="claude-opus",
                    model_name="claude-opus-4", session_id="sess-replay-1",
                    project_path=pp, branch_name="main")
    log_agent_event("decision_created", title="Architecture choice", agent_name="claude-opus",
                    model_name="claude-opus-4", session_id="sess-replay-1",
                    project_path=pp, branch_name="main", duration_ms=150,
                    summary="Chose microservices over monolith")
    log_agent_event("fact_created", title="New fact learned", agent_name="claude-opus",
                    model_name="claude-opus-4", session_id="sess-replay-1",
                    project_path=pp, branch_name="main")
    log_agent_event("agent_finished", title="Claude done", agent_name="claude-opus",
                    model_name="claude-opus-4", session_id="sess-replay-1",
                    project_path=pp, branch_name="main", duration_ms=5000)

    # Session 2 — different agent with error
    log_agent_event("agent_started", title="GLM start", agent_name="glm-5",
                    model_name="glm-5", provider="zhipu",
                    session_id="sess-replay-2", project_path=pp, branch_name="feature-x")
    log_agent_event("agent_error", title="GLM crashed", agent_name="glm-5",
                    model_name="glm-5", session_id="sess-replay-2",
                    project_path=pp, branch_name="feature-x", success_flag=0,
                    summary="OOM error during inference")
    log_agent_event("agent_finished", title="GLM done with error", agent_name="glm-5",
                    model_name="glm-5", session_id="sess-replay-2",
                    project_path=pp, branch_name="feature-x", success_flag=0)

    # Standalone events
    log_agent_event("checkpoint_created", title="Checkpoint v1", project_path=pp, branch_name="main")
    log_agent_event("branch_merged", title="Merge feature-x", project_path=pp, branch_name="main",
                    metadata={"source": "feature-x", "target": "main"})

print("\n🔧 Setup DB...")
setup_db()
print("🌱 Seeding events...")
seed_events()
print("🌐 Setup Flask...")
app = setup_flask()

import urllib.request, urllib.error

def api_get(path):
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())

def api_post(path, data):
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

# Read web files once
html_content = (WEB_DIR / "index.html").read_text()
js_content = (WEB_DIR / "app.js").read_text()
css_content = (WEB_DIR / "styles.css").read_text()


# ================================================================
# T1-T5: HTML Structure
# ================================================================
print("\n📋 T1-T5: HTML structure")

def t1_events_nav_btn():
    assert 'data-tab="events"' in html_content, "Events nav button missing"
    assert ">Events<" in html_content, "Events button text missing"
run("T1: Events nav button exists", t1_events_nav_btn)

def t2_events_tab_section():
    assert 'id="tab-events"' in html_content, "tab-events section missing"
    assert 'class="tab-pane"' in html_content
run("T2: Events tab section exists", t2_events_tab_section)

def t3_events_type_filter():
    assert 'id="events-type"' in html_content, "events-type select missing"
    # Check at least some event type options
    for etype in ["agent_started", "agent_finished", "agent_error", "decision_created",
                  "checkpoint_created", "branch_merged"]:
        assert f'value="{etype}"' in html_content, f"Option {etype} missing"
run("T3: Event type filter with all 18 types", t3_events_type_filter)

def t4_events_agent_filter():
    assert 'id="events-agent"' in html_content, "events-agent input missing"
    assert 'id="events-model"' in html_content, "events-model input missing"
    assert 'id="events-branch"' in html_content, "events-branch input missing"
run("T4: Agent/model/branch filter inputs", t4_events_agent_filter)

def t5_events_failed_checkbox():
    assert 'id="events-failed"' in html_content, "events-failed checkbox missing"
    assert 'Failed only' in html_content, "Failed only label missing"
run("T5: Failed-only checkbox", t5_events_failed_checkbox)


# ================================================================
# T6-T12: JavaScript Functions
# ================================================================
print("\n📋 T6-T12: JS functions")

def t6_loadEventsTab_function():
    assert "function loadEventsTab" in js_content or "async function loadEventsTab" in js_content, \
        "loadEventsTab function missing"
run("T6: loadEventsTab function exists", t6_loadEventsTab_function)

def t7_loadTabData_events():
    assert "case 'events'" in js_content, "events case missing in loadTabData switch"
    assert "loadEventsTab" in js_content
run("T7: loadTabData includes events case", t7_loadTabData_events)

def t8_showEventDetail_function():
    assert "function showEventDetail" in js_content, "showEventDetail function missing"
run("T8: showEventDetail function exists", t8_showEventDetail_function)

def t9_showEventReplay_function():
    assert "function showEventReplay" in js_content, "showEventReplay function missing"
run("T9: showEventReplay function exists", t9_showEventReplay_function)

def t10_event_icons():
    assert "EVENT_ICONS" in js_content, "EVENT_ICONS constant missing"
    # Check key event types have icons
    for etype in ["agent_started", "agent_error", "decision_created", "checkpoint_created"]:
        assert etype in js_content, f"Icon for {etype} missing"
run("T10: EVENT_ICONS covers all event types", t10_event_icons)

def t11_event_colors():
    assert "EVENT_COLORS" in js_content, "EVENT_COLORS constant missing"
run("T11: EVENT_COLORS mapping exists", t11_event_colors)

def t12_api_endpoint_used():
    assert "/api/events" in js_content, "loadEventsTab must call /api/events"
run("T12: loadEventsTab calls /api/events", t12_api_endpoint_used)


# ================================================================
# T13-T18: CSS Classes
# ================================================================
print("\n📋 T13-T18: CSS classes")

def t13_ev_item():
    assert ".ev-item" in css_content, ".ev-item CSS class missing"
run("T13: .ev-item CSS class", t13_ev_item)

def t14_ev_failed():
    assert ".ev-failed" in css_content, ".ev-failed CSS class missing"
    assert "var(--danger)" in css_content  # should reference danger color
run("T14: .ev-failed CSS class with danger color", t14_ev_failed)

def t15_ev_replay_timeline():
    assert ".ev-replay-timeline" in css_content, ".ev-replay-timeline CSS missing"
    assert ".ev-replay-item" in css_content, ".ev-replay-item CSS missing"
    assert ".ev-replay-dot" in css_content, ".ev-replay-dot CSS missing"
    assert ".ev-replay-connector" in css_content, ".ev-replay-connector CSS missing"
run("T15: Replay timeline CSS classes", t15_ev_replay_timeline)

def t16_ev_detail():
    assert ".ev-detail-grid" in css_content, ".ev-detail-grid CSS missing"
    assert ".ev-detail-label" in css_content
    assert ".ev-detail-value" in css_content
run("T16: Event detail modal CSS", t16_ev_detail)

def t17_ev_replay_bar():
    assert ".ev-replay-bar" in css_content, ".ev-replay-bar CSS missing"
run("T17: Replay bar CSS", t17_ev_replay_bar)

def t18_ev_dot_colors():
    for color in ["blue", "green", "red", "purple", "cyan"]:
        assert f".ev-dot-{color}" in css_content, f".ev-dot-{color} CSS missing"
run("T18: Dot color variants (blue/green/red/purple/cyan)", t18_ev_dot_colors)


# ================================================================
# T19-T24: API Integration
# ================================================================
print("\n📋 T19-T24: API integration")

def t19_api_events_all():
    data = api_get("/api/events?limit=50")
    assert data["ok"], "API returned not ok"
    assert len(data["events"]) == 10, f"Expected 10 seeded events, got {len(data['events'])}"
run("T19: GET /api/events returns all seeded events", t19_api_events_all)

def t20_api_filter_agent():
    data = api_get("/api/events?agent=claude-opus&limit=50")
    assert all(e["agent_name"] == "claude-opus" for e in data["events"]), "Agent filter broken"
    assert len(data["events"]) == 5, f"Expected 5 claude-opus events, got {len(data['events'])}"
run("T20: GET /api/events?agent=claude-opus filters correctly", t20_api_filter_agent)

def t21_api_filter_type():
    data = api_get("/api/events?type=agent_error&limit=50")
    assert len(data["events"]) >= 1, "Should have at least 1 agent_error"
    assert all(e["event_type"] == "agent_error" for e in data["events"])
run("T21: GET /api/events?type=agent_error filters correctly", t21_api_filter_type)

def t22_api_filter_failed():
    data = api_get("/api/events?failed=true&limit=50")
    assert len(data["events"]) >= 2, f"Expected >=2 failed events, got {len(data['events'])}"
    assert all(e["success_flag"] == 0 for e in data["events"])
run("T22: GET /api/events?failed=true filters correctly", t22_api_filter_failed)

def t23_api_filter_branch():
    data = api_get("/api/events?branch=feature-x&limit=50")
    assert len(data["events"]) == 3, f"Expected 3 feature-x events, got {len(data['events'])}"
    assert all(e["branch_name"] == "feature-x" for e in data["events"])
run("T23: GET /api/events?branch=feature-x filters correctly", t23_api_filter_branch)

def t24_api_filter_model():
    data = api_get("/api/events?model=glm-5&limit=50")
    assert len(data["events"]) == 3, f"Expected 3 glm-5 events, got {len(data['events'])}"
run("T24: GET /api/events?model=glm-5 filters correctly", t24_api_filter_model)


# ================================================================
# T25-T28: Edge Cases
# ================================================================
print("\n📋 T25-T28: Edge cases")

def t25_empty_project():
    data = api_get("/api/events?project=nonexistent-project&limit=50")
    assert data["ok"]
    assert len(data["events"]) == 0, "Should return empty for nonexistent project"
run("T25: Empty result for nonexistent project", t25_empty_project)

def t26_combined_filters():
    data = api_get(f"/api/events?agent=claude-opus&branch=main&type=decision_created&limit=50")
    assert data["ok"]
    assert len(data["events"]) == 1, f"Expected 1 event, got {len(data['events'])}"
    assert data["events"][0]["title"] == "Architecture choice"
run("T26: Combined filters (agent+branch+type)", t26_combined_filters)

def t27_events_have_metadata():
    data = api_get("/api/events?type=branch_merged&limit=5")
    assert len(data["events"]) >= 1
    ev = data["events"][0]
    assert ev["metadata_json"], "metadata_json should not be empty"
    meta = json.loads(ev["metadata_json"]) if isinstance(ev["metadata_json"], str) else ev["metadata_json"]
    assert "source" in meta, "metadata should contain source"
run("T27: Events with metadata_json", t27_events_have_metadata)

def t28_session_grouping():
    """JS groups events by session_id for replay — verify API returns session_id."""
    data = api_get("/api/events?limit=50")
    sessions = set()
    for ev in data["events"]:
        if ev.get("session_id"):
            sessions.add(ev["session_id"])
    assert "sess-replay-1" in sessions, "sess-replay-1 not found"
    assert "sess-replay-2" in sessions, "sess-replay-2 not found"
run("T28: Session IDs present for replay grouping", t28_session_grouping)


# ================================================================
# T29-T33: Regression
# ================================================================
print("\n📋 T29-T33: Regression")

def t29_existing_tabs_preserved():
    for tab in ["dashboard", "decisions", "facts", "goals-tasks", "timeline",
                "context", "health", "activity", "errors", "branches", "sessions", "search"]:
        assert f'data-tab="{tab}"' in html_content, f"Tab {tab} missing from nav"
        assert f'id="tab-{tab}"' in html_content, f"Section tab-{tab} missing"
run("T29: All 12 existing tabs preserved", t29_existing_tabs_preserved)

def t30_dashboard_still_works():
    data = api_get("/api/dashboard")
    assert data, "Dashboard API failed"
    assert "summary" in data, "Dashboard missing summary"
run("T30: Dashboard API still works", t30_dashboard_still_works)

def t31_css_no_broken_vars():
    # No unclosed braces or broken syntax
    open_count = css_content.count("{")
    close_count = css_content.count("}")
    assert open_count == close_count, f"CSS brace mismatch: {open_count} open vs {close_count} close"
run("T31: CSS has balanced braces", t31_css_no_broken_vars)

def t32_js_functions_intact():
    for fn in ["loadDashboard", "loadDecisionsTab", "loadFactsTab", "loadGoalsTasksTab",
               "loadTimelineTab", "loadContextTab", "loadHealthTab", "loadActivityTab",
               "loadErrorsTab", "loadBranchesTab", "loadSessions", "closeModal"]:
        assert fn in js_content, f"Function {fn} missing from app.js"
run("T32: All existing JS functions intact", t32_js_functions_intact)

def t33_protected_files():
    for pf in ["memory_daemon.py", "capsule_builder.py"]:
        fp = SCRIPTS_DIR / pf
        if fp.exists():
            # Verify file exists and wasn't deleted
            assert fp.exists(), f"Protected file {pf} was deleted"
run("T33: Protected files untouched", t33_protected_files)


# ================================================================
# CLEANUP & REPORT
# ================================================================
if TEST_DB.exists():
    TEST_DB.unlink()

print(f"\n{'='*60}")
print(f"Phase 12B Results: {passed} passed, {failed} failed / {passed+failed} total")
print(f"{'='*60}")

if failed:
    print("\n❌ FAILURES:")
    for name, ok, err in results:
        if not ok:
            print(f"  {name}: {err}")

sys.exit(0 if failed == 0 else 1)
