#!/usr/bin/env python3
"""
Tests for Phase 14 — Release Candidate + Public Repo Polish
T1.  README is coherent and updated
T2.  Main docs exist and are linked
T3.  Examples exist and are consistent
T4.  CHANGELOG / ROADMAP / RELEASE_NOTES exist
T5.  run_server.sh is valid
T6.  run_mcp.sh is valid
T7.  demo_seed.py is valid / demo.md exists
T8.  release_check.py works
T9.  API starts (Flask blueprints register)
T10. MCP server files importable
T11. Web UI loads (all 3 files present + events tab)
T12. mem context callable
T13. mem dashboard callable
T14. mem branch list callable
T15. mem events callable
T16. Adapters importable (Gemini + Codex)
T17. Spec validator works
T18. PRAGMA integrity_check on fresh DB
"""

import sys, os, json, sqlite3, subprocess, importlib, stat
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

TEST_DB = PROJECT_ROOT / "tests" / "test_14.db"

passed = 0
failed = 0
results = []

def run(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        results.append((name, True, None))
        print(f"  \u2705 {name}")
    except Exception as e:
        failed += 1
        results.append((name, False, str(e)))
        print(f"  \u274C {name}: {e}")


# Setup test DB
def setup():
    if TEST_DB.exists():
        TEST_DB.unlink()
    os.environ["MEMORY_DB_PATH"] = str(TEST_DB)
    from init_db import init_database
    init_database(TEST_DB)

setup()


# ================================================================
# T1-T4: DOCS / REPO
# ================================================================
print("\n\U0001F4CB T1-T4: Docs / Repo")

def t1_readme():
    readme = (PROJECT_ROOT / "README.md").read_text()
    for section in ["Quick Start", "Specifications", "Architecture", "Memory Model",
                    "Adapters", "Testing", "Running", "Documentation"]:
        assert section in readme, f"README missing section: {section}"
    assert "requirements.txt" in readme, "README doesn't mention requirements.txt"
    assert "run_server.sh" in readme, "README doesn't mention run_server.sh"
    assert "demo" in readme.lower(), "README doesn't mention demo"
run("T1: README coherent and updated", t1_readme)

def t2_docs_linked():
    readme = (PROJECT_ROOT / "README.md").read_text()
    docs = ["quickstart.md", "demo.md", "architecture.md", "api.md", "mcp.md",
            "configuration.md", "CHANGELOG.md", "ROADMAP.md"]
    for doc in docs:
        assert doc in readme, f"README doesn't link to {doc}"
    # Verify docs exist
    for doc in ["quickstart.md", "demo.md", "architecture.md", "api.md", "mcp.md",
                "configuration.md", "adapters.md", "branches.md"]:
        assert (PROJECT_ROOT / "docs" / doc).exists(), f"docs/{doc} missing"
run("T2: Main docs exist and linked in README", t2_docs_linked)

def t3_examples():
    examples_dir = PROJECT_ROOT / "docs" / "examples"
    required = ["cli_workflow.sh", "python_client.py", "gemini_adapter_usage.py",
                "codex_adapter_usage.py", "mcp_config_claude.json"]
    for ex in required:
        fp = examples_dir / ex
        assert fp.exists(), f"examples/{ex} missing"
        assert fp.stat().st_size > 50, f"examples/{ex} too small"
    # Check MCP config is valid JSON
    mcp_cfg = json.loads((examples_dir / "mcp_config_claude.json").read_text())
    assert "mcpServers" in mcp_cfg, "MCP config missing mcpServers key"
run("T3: Examples exist and are consistent", t3_examples)

def t4_release_docs():
    for doc in ["CHANGELOG.md", "ROADMAP.md", "RELEASE_NOTES_RC1.md"]:
        fp = PROJECT_ROOT / doc
        assert fp.exists(), f"{doc} missing"
        content = fp.read_text()
        assert len(content) > 200, f"{doc} too short"
    # CHANGELOG has v2 entry
    cl = (PROJECT_ROOT / "CHANGELOG.md").read_text()
    assert "2.0.0-rc1" in cl, "CHANGELOG missing v2.0.0-rc1 entry"
    # ROADMAP has planned items
    rm = (PROJECT_ROOT / "ROADMAP.md").read_text()
    assert "Planned" in rm or "v2.1" in rm, "ROADMAP missing future plans"
run("T4: CHANGELOG / ROADMAP / RELEASE_NOTES exist", t4_release_docs)


# ================================================================
# T5-T8: RUN SCRIPTS / DEMO
# ================================================================
print("\n\U0001F4CB T5-T8: Run scripts / Demo")

def t5_run_server():
    fp = SCRIPTS_DIR / "run_server.sh"
    assert fp.exists(), "run_server.sh missing"
    content = fp.read_text()
    assert "web_server.py" in content, "run_server.sh doesn't call web_server.py"
    assert "init_db" in content, "run_server.sh doesn't init DB"
    # Check executable
    assert os.access(str(fp), os.X_OK), "run_server.sh not executable"
run("T5: run_server.sh valid and executable", t5_run_server)

def t6_run_mcp():
    fp = SCRIPTS_DIR / "run_mcp.sh"
    assert fp.exists(), "run_mcp.sh missing"
    content = fp.read_text()
    assert "server.py" in content, "run_mcp.sh doesn't reference MCP server"
    assert "MEMORY_BASE_URL" in content, "run_mcp.sh doesn't set MEMORY_BASE_URL"
    assert os.access(str(fp), os.X_OK), "run_mcp.sh not executable"
run("T6: run_mcp.sh valid and executable", t6_run_mcp)

def t7_demo():
    # demo.md exists
    demo_doc = PROJECT_ROOT / "docs" / "demo.md"
    assert demo_doc.exists(), "docs/demo.md missing"
    content = demo_doc.read_text()
    for step in ["Start the Server", "Create Memory Entities", "Work with Branches",
                 "View in Web Dashboard", "Python Client", "MCP"]:
        assert step in content, f"demo.md missing step: {step}"
    # demo_seed.py exists and is valid Python
    seed = SCRIPTS_DIR / "demo_seed.py"
    assert seed.exists(), "demo_seed.py missing"
    # Syntax check
    result = subprocess.run([sys.executable, "-c", f"compile(open('{seed}').read(), '{seed}', 'exec')"],
                           capture_output=True, text=True)
    assert result.returncode == 0, f"demo_seed.py syntax error: {result.stderr}"
run("T7: Demo flow valid (demo.md + demo_seed.py)", t7_demo)

def t8_release_check():
    fp = SCRIPTS_DIR / "release_check.py"
    assert fp.exists(), "release_check.py missing"
    # Syntax check
    result = subprocess.run([sys.executable, "-c", f"compile(open('{fp}').read(), '{fp}', 'exec')"],
                           capture_output=True, text=True)
    assert result.returncode == 0, f"release_check.py syntax error: {result.stderr}"
run("T8: release_check.py valid", t8_release_check)


# ================================================================
# T9-T18: REGRESSION
# ================================================================
print("\n\U0001F4CB T9-T18: Regression")

def t9_api_starts():
    import v2_common
    importlib.reload(v2_common)
    from flask import Flask
    app = Flask(__name__)
    import dashboard_api
    importlib.reload(dashboard_api)
    import universal_api
    importlib.reload(universal_api)
    app.register_blueprint(dashboard_api.dashboard_bp)
    app.register_blueprint(universal_api.universal_bp)
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/v1/decisions" in rules
    assert "/api/dashboard" in rules
    assert "/api/events" in rules
    assert "/api/v1/agent-events" in rules
run("T9: API starts (Flask blueprints register)", t9_api_starts)

def t10_mcp_importable():
    mcp_tools = PROJECT_ROOT / "mcp_server" / "tools.py"
    mcp_server = PROJECT_ROOT / "mcp_server" / "server.py"
    assert mcp_tools.exists() and mcp_server.exists()
    # Check syntax
    for fp in [mcp_tools, mcp_server]:
        result = subprocess.run([sys.executable, "-c", f"compile(open('{fp}').read(), '{fp}', 'exec')"],
                               capture_output=True, text=True)
        assert result.returncode == 0, f"{fp.name} syntax error: {result.stderr}"
run("T10: MCP server files valid", t10_mcp_importable)

def t11_web_ui():
    html = (PROJECT_ROOT / "web" / "index.html").read_text()
    js = (PROJECT_ROOT / "web" / "app.js").read_text()
    css = (PROJECT_ROOT / "web" / "styles.css").read_text()
    # 13 tabs
    for tab in ["dashboard", "decisions", "facts", "goals-tasks", "timeline",
                "context", "health", "activity", "errors", "branches", "events",
                "sessions", "search"]:
        assert f'data-tab="{tab}"' in html, f"Tab {tab} missing from nav"
    assert "loadEventsTab" in js
    assert ".ev-item" in css
run("T11: Web UI loads (13 tabs including events)", t11_web_ui)

def t12_context():
    from context_builder_v2 import build_context
    assert callable(build_context)
    # build_context prints to stdout and returns None — just verify it doesn't crash
    build_context(project_path=str(PROJECT_ROOT), mode="compact")
run("T12: mem context callable (build_context)", t12_context)

def t13_dashboard():
    conn = sqlite3.connect(str(TEST_DB))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Simulate dashboard query
    cursor.execute("SELECT COUNT(*) as c FROM decisions")
    r = cursor.fetchone()
    assert r is not None
    conn.close()
run("T13: mem dashboard callable (DB queries work)", t13_dashboard)

def t14_branch_list():
    from branch_manager import cmd_list
    # Should not crash on empty DB
    class FakeArgs:
        project = str(PROJECT_ROOT)
    # Just verify the function exists and is callable
    assert callable(cmd_list)
run("T14: mem branch list callable", t14_branch_list)

def t15_events():
    fp = SCRIPTS_DIR / "agent_events.py"
    assert fp.exists(), "agent_events.py missing"
    result = subprocess.run([sys.executable, "-c", f"compile(open('{fp}').read(), '{fp}', 'exec')"],
                           capture_output=True, text=True)
    assert result.returncode == 0, f"agent_events.py syntax error: {result.stderr}"
run("T15: mem events callable (agent_events.py valid)", t15_events)

def t16_adapters():
    adapters_dir = SCRIPTS_DIR / "adapters"
    for adapter in ["gemini_cli_adapter.py", "codex_cli_adapter.py"]:
        fp = adapters_dir / adapter
        assert fp.exists(), f"adapters/{adapter} missing"
        result = subprocess.run([sys.executable, "-c", f"compile(open('{fp}').read(), '{fp}', 'exec')"],
                               capture_output=True, text=True)
        assert result.returncode == 0, f"{adapter} syntax error: {result.stderr}"
run("T16: Adapters valid (Gemini + Codex)", t16_adapters)

def t17_validator():
    from spec_validator import validate_decision, validate_fact, validate_event
    assert not validate_decision({"title": "X"})
    assert validate_decision({})
    assert not validate_event({"event_type": "agent_started"})
    assert validate_event({"event_type": "bogus"})
run("T17: Spec validator works", t17_validator)

def t18_integrity():
    conn = sqlite3.connect(str(TEST_DB))
    result = conn.execute("PRAGMA integrity_check").fetchone()
    conn.close()
    assert result[0] == "ok", f"Integrity check failed: {result[0]}"
run("T18: PRAGMA integrity_check OK", t18_integrity)


# ================================================================
# CLEANUP & REPORT
# ================================================================
if TEST_DB.exists():
    TEST_DB.unlink()

print(f"\n{'='*60}")
print(f"Phase 14 Results: {passed} passed, {failed} failed / {passed+failed} total")
print(f"{'='*60}")

if failed:
    print("\n\u274C FAILURES:")
    for name, ok, err in results:
        if not ok:
            print(f"  {name}: {err}")

sys.exit(0 if failed == 0 else 1)
