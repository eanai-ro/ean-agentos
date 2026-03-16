#!/usr/bin/env python3
"""
Teste Faza 11B: MCP Bridge (Model Context Protocol)

T1-T3:   MCP server structure & imports
T4-T6:   MCP tool registration
T7-T9:   Context tools (via API)
T10-T13: Memory write tools (via API)
T14-T16: Branch tools (via API)
T17-T19: Observability tools (via API)
T20-T22: Edge cases
T23-T25: Regresie generală
"""

import os
import sys
import json
import sqlite3
import subprocess
import tempfile
import threading
from pathlib import Path
from datetime import datetime

TEST_DIR = tempfile.mkdtemp(prefix="mem_test_11b_")
TEST_DB = os.path.join(TEST_DIR, "test.db")
os.environ["MEMORY_DB_PATH"] = TEST_DB

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
PROJECT_ROOT = Path(__file__).parent.parent
MCP_DIR = PROJECT_ROOT / "mcp_server"
PROJECT_PATH = str(PROJECT_ROOT)

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
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Use SQLite", "Simplitate", "technical", "active", "confirmed", pp, "main"))
c.execute("INSERT INTO learned_facts (fact, fact_type, category, confidence, is_pinned, is_active, project_path, branch) VALUES (?,?,?,?,?,?,?,?)",
          ("WAL mode required", "convention", "sqlite", "confirmed", 1, 1, pp, "main"))
c.execute("INSERT INTO goals (title, description, priority, status, project_path, branch) VALUES (?,?,?,?,?,?)",
          ("Complete V2", "Full impl", "high", "active", pp, "main"))
c.execute("INSERT INTO tasks (title, priority, status, goal_id, project_path, branch) VALUES (?,?,?,?,?,?)",
          ("Build API", "high", "in_progress", 1, pp, "main"))
c.execute("INSERT INTO memory_branches (name, project_path, parent_branch, description) VALUES (?,?,?,?)",
          ("feature-mcp", pp, "main", "MCP feature"))
c.execute("INSERT INTO decisions (title, description, category, status, confidence, project_path, branch) VALUES (?,?,?,?,?,?,?)",
          ("Use MCP", "Protocol", "technical", "active", "high", pp, "feature-mcp"))
c.execute("INSERT INTO error_patterns (error_signature, solution, count, project_path) VALUES (?,?,?,?)",
          ("import_error_xyz", "pip install xyz", 5, pp))
c.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path) VALUES (?,?,?,?,?)",
          ("checkpoint_create", 1, "Checkpoint: pre-mcp", "5 entities", pp))
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
server = make_server("127.0.0.1", 19882, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

BASE_URL = "http://127.0.0.1:19882"

# Configure MCP tools to use our test server
os.environ["MEMORY_BASE_URL"] = BASE_URL
os.environ["MEMORY_PROJECT_PATH"] = pp

# Reload config module to pick up env vars
import importlib
sys.path.insert(0, str(PROJECT_ROOT))
import mcp_server.config
importlib.reload(mcp_server.config)

# Reload tools module to pick up new config
import mcp_server.tools
importlib.reload(mcp_server.tools)


# ===== T1-T3: MCP server structure & imports =====
print("\n\U0001f4cb T1-T3: MCP server structure")

def t1_server_file_exists():
    assert (MCP_DIR / "server.py").exists(), "server.py missing"
    assert (MCP_DIR / "tools.py").exists(), "tools.py missing"
    assert (MCP_DIR / "config.py").exists(), "config.py missing"
    assert (MCP_DIR / "__init__.py").exists(), "__init__.py missing"
run("T1: mcp_server/ files exist", t1_server_file_exists)

def t2_server_imports():
    from mcp_server.server import mcp
    assert mcp is not None, "mcp server not created"
    assert mcp.name == "Universal Agent Memory", f"Wrong name: {mcp.name}"
run("T2: server.py imports correctly", t2_server_imports)

def t3_config_env():
    importlib.reload(mcp_server.config)
    from mcp_server.config import BASE_URL as bu, PROJECT_PATH as pp_conf
    assert bu == BASE_URL, f"BASE_URL not set: {bu}"
    assert pp_conf == pp, f"PROJECT_PATH not set: {pp_conf}"
run("T3: config reads env vars", t3_config_env)


# ===== T4-T6: MCP tool registration =====
print("\n\U0001f4cb T4-T6: MCP tool registration")

def t4_tool_count():
    from mcp_server.server import mcp
    tools = mcp._tool_manager._tools
    assert len(tools) >= 13, f"Expected >=13 tools, got {len(tools)}"
run("T4: at least 13 tools registered", t4_tool_count)

def t5_tool_names():
    from mcp_server.server import mcp
    tools = set(mcp._tool_manager._tools.keys())
    required = {
        "memory_get_context",
        "memory_create_decision", "memory_create_fact",
        "memory_create_goal", "memory_create_task", "memory_create_resolution",
        "memory_list_branches", "memory_switch_branch",
        "memory_compare_branches", "memory_merge_branch",
        "memory_get_health", "memory_get_activity", "memory_get_timeline",
    }
    missing = required - tools
    assert not missing, f"Missing tools: {missing}"
run("T5: all required tool names present", t5_tool_names)

def t6_tool_descriptions():
    from mcp_server.server import mcp
    tools = mcp._tool_manager._tools
    for name, tool in tools.items():
        desc = tool.description or ""
        assert len(desc) > 10, f"Tool {name} has no/short description: {desc[:30]}"
run("T6: all tools have descriptions", t6_tool_descriptions)


# ===== T7-T9: Context tools =====
print("\n\U0001f4cb T7-T9: Context tools via API")

def t7_get_context():
    from mcp_server.tools import get_context
    result = get_context(mode="compact", project_path=pp)
    assert result.get("ok") is True, f"get_context failed: {result}"
    assert "decisions" in result, f"No decisions in context: {result}"
run("T7: get_context returns ok", t7_get_context)

def t8_get_context_full():
    from mcp_server.tools import get_context
    result = get_context(mode="full", project_path=pp)
    assert result.get("ok") is True, f"get_context full failed: {result}"
run("T8: get_context mode=full", t8_get_context_full)

def t9_get_context_with_intent():
    from mcp_server.tools import get_context
    result = get_context(mode="compact", intent="debugging", project_path=pp)
    assert result.get("ok") is True, f"get_context with intent failed: {result}"
run("T9: get_context with intent", t9_get_context_with_intent)


# ===== T10-T13: Memory write tools =====
print("\n\U0001f4cb T10-T13: Memory write tools via API")

def t10_create_decision():
    from mcp_server.tools import create_decision
    result = create_decision("Use MCP Protocol", description="For agent comms",
                              category="architectural", project_path=pp)
    assert result.get("ok") is True, f"create_decision failed: {result}"
    assert "id" in result, f"No id in result: {result}"
run("T10: create_decision via MCP tool", t10_create_decision)

def t11_create_fact():
    from mcp_server.tools import create_fact
    result = create_fact("MCP uses stdio transport", fact_type="technical",
                          category="protocol", project_path=pp)
    assert result.get("ok") is True, f"create_fact failed: {result}"
run("T11: create_fact via MCP tool", t11_create_fact)

def t12_create_task():
    from mcp_server.tools import create_task
    result = create_task("Test MCP server", priority="high", project_path=pp)
    assert result.get("ok") is True, f"create_task failed: {result}"
run("T12: create_task via MCP tool", t12_create_task)

def t13_create_resolution():
    from mcp_server.tools import create_resolution
    result = create_resolution("MCP timeout error", "Increase timeout to 30s",
                                worked=True, project_path=pp)
    assert result.get("ok") is True, f"create_resolution failed: {result}"
run("T13: create_resolution via MCP tool", t13_create_resolution)


# ===== T14-T16: Branch tools =====
print("\n\U0001f4cb T14-T16: Branch tools via API")

def t14_list_branches():
    from mcp_server.tools import list_branches
    result = list_branches(project_path=pp)
    assert "branches" in result, f"No branches: {result}"
    names = [b["name"] for b in result["branches"]]
    assert "main" in names, f"main missing: {names}"
    assert "feature-mcp" in names, f"feature-mcp missing: {names}"
run("T14: list_branches via MCP tool", t14_list_branches)

def t15_compare_branches():
    from mcp_server.tools import compare_branches
    result = compare_branches(branch_a="main", branch_b="feature-mcp", project_path=pp)
    assert "summary" in result, f"No summary: {result}"
    s = result["summary"]
    assert s["branch_a"] == "main", f"Wrong branch_a: {s}"
    assert s["branch_b"] == "feature-mcp", f"Wrong branch_b: {s}"
run("T15: compare_branches via MCP tool", t15_compare_branches)

def t16_switch_branch():
    from mcp_server.tools import switch_branch
    result = switch_branch("feature-mcp", project_path=pp)
    assert result.get("success") is True, f"switch_branch failed: {result}"
    # Switch back
    switch_branch("main", project_path=pp)
run("T16: switch_branch via MCP tool", t16_switch_branch)


# ===== T17-T19: Observability tools =====
print("\n\U0001f4cb T17-T19: Observability tools via API")

def t17_get_health():
    from mcp_server.tools import get_health
    result = get_health(project_path=pp)
    assert "decisions" in result, f"No decisions count: {result}"
    assert "facts" in result, f"No facts count: {result}"
    assert result["decisions"] > 0, f"Expected decisions > 0: {result}"
run("T17: get_health via MCP tool", t17_get_health)

def t18_get_activity():
    from mcp_server.tools import get_activity
    result = get_activity(limit=10, project_path=pp)
    assert "activity" in result, f"No activity: {result}"
run("T18: get_activity via MCP tool", t18_get_activity)

def t19_get_timeline():
    from mcp_server.tools import get_timeline
    result = get_timeline(days=30, limit=10, project_path=pp)
    assert "timeline" in result, f"No timeline: {result}"
run("T19: get_timeline via MCP tool", t19_get_timeline)


# ===== T20-T22: Edge cases =====
print("\n\U0001f4cb T20-T22: Edge cases")

def t20_empty_project_path():
    """Tools with empty project_path should use configured default."""
    from mcp_server.tools import get_health
    result = get_health(project_path=None)
    assert "decisions" in result or "error" not in result, f"Failed with None project: {result}"
run("T20: empty project_path uses default", t20_empty_project_path)

def t21_compare_nonexistent():
    from mcp_server.tools import compare_branches
    result = compare_branches(branch_a="main", branch_b="nonexistent-xyz", project_path=pp)
    assert "error" in result, f"Expected error for nonexistent: {result}"
run("T21: compare nonexistent branch → error", t21_compare_nonexistent)

def t22_docs_exist():
    docs_mcp = PROJECT_ROOT / "docs" / "mcp.md"
    assert docs_mcp.exists(), "docs/mcp.md missing"
    content = docs_mcp.read_text()
    assert "MCP" in content, "docs/mcp.md has no MCP content"
    assert "claude" in content.lower() or "Claude" in content, "No Claude reference"
run("T22: docs/mcp.md exists", t22_docs_exist)


# ===== T23-T25: Regresie generală =====
print("\n\U0001f4cb T23-T25: Regresie generală")

def t23_api_dashboard():
    from clients.universal_memory_client import UniversalMemoryClient
    client = UniversalMemoryClient(base_url=BASE_URL, project_path=pp,
                                    cli_name="test", agent_name="test",
                                    provider="test", model_name="test")
    r = client._get("/api/dashboard", {"project": pp})
    assert "summary" in r, f"No summary: {r}"
run("T23: /api/dashboard (regression)", t23_api_dashboard)

def t24_api_v1_context():
    from clients.universal_memory_client import UniversalMemoryClient
    client = UniversalMemoryClient(base_url=BASE_URL, project_path=pp,
                                    cli_name="test", agent_name="test",
                                    provider="test", model_name="test")
    r = client._get("/api/v1/context", {"project": pp, "mode": "compact"})
    assert r.get("ok") is True, f"Expected ok: {r}"
run("T24: /api/v1/context (regression)", t24_api_v1_context)

def t25_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA integrity_check")
    result = c.fetchone()[0]
    conn.close()
    assert result == "ok", f"Integrity failed: {result}"
run("T25: PRAGMA integrity_check", t25_integrity)


# ===== Cleanup =====
server.shutdown()

# ===== SUMMARY =====
print(f"\n{'='*50}")
print(f"\U0001f3c1 Phase 11B Results: {passed} passed, {failed} failed out of {passed+failed}")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
