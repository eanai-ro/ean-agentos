#!/usr/bin/env python3
"""
Tests for Phase 13 — Public Memory Standard + Adapter Specification
T1.  All spec documents exist
T2.  README references all specs
T3.  JSON examples in spec-memory-schema.md are valid JSON
T4.  Compatibility matrix is complete (all clients, all features)
T5.  Branch spec reflects implemented operations
T6.  Event spec reflects actual taxonomy
T7.  Adapter spec matches Gemini/Codex/UniversalMemoryClient/MCP
T8.  Validator accepts valid payloads
T9.  Validator rejects invalid payloads
T10. No breaking API changes (endpoints still registered)
T11. Existing docs not invalidated
"""

import sys, os, json, re, importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DOCS_DIR = PROJECT_ROOT / "docs"
sys.path.insert(0, str(SCRIPTS_DIR))

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
# T1: All spec documents exist
# ================================================================
print("\n📋 T1: Spec documents")

def t1_docs_exist():
    required = [
        "spec-memory-schema.md",
        "spec-events.md",
        "spec-adapters.md",
        "spec-branches.md",
        "compatibility.md",
    ]
    for doc in required:
        fp = DOCS_DIR / doc
        assert fp.exists(), f"Missing: docs/{doc}"
        content = fp.read_text()
        assert len(content) > 500, f"docs/{doc} too short ({len(content)} chars)"
run("T1: All 5 spec documents exist and have content", t1_docs_exist)


# ================================================================
# T2: README references specs
# ================================================================
print("\n📋 T2: README references")

def t2_readme_refs():
    readme = (PROJECT_ROOT / "README.md").read_text()
    for doc in ["spec-memory-schema.md", "spec-events.md", "spec-adapters.md",
                "spec-branches.md", "compatibility.md"]:
        assert doc in readme, f"README.md doesn't reference {doc}"
    assert "spec_validator" in readme, "README doesn't mention spec_validator"
run("T2: README references all spec documents", t2_readme_refs)


# ================================================================
# T3: JSON examples are valid
# ================================================================
print("\n📋 T3: JSON examples")

def t3_json_examples():
    schema_doc = (DOCS_DIR / "spec-memory-schema.md").read_text()
    events_doc = (DOCS_DIR / "spec-events.md").read_text()

    # Extract all JSON blocks
    json_blocks = re.findall(r'```json\n(.*?)```', schema_doc + events_doc, re.DOTALL)
    assert len(json_blocks) >= 5, f"Expected >=5 JSON blocks, found {len(json_blocks)}"

    for i, block in enumerate(json_blocks):
        # Some blocks may be arrays of objects — try parsing
        block = block.strip()
        if not block:
            continue
        try:
            json.loads(block)
        except json.JSONDecodeError as e:
            raise AssertionError(f"Invalid JSON in block {i+1}: {e}\n{block[:100]}...")
run("T3: All JSON examples parse correctly", t3_json_examples)


# ================================================================
# T4: Compatibility matrix is complete
# ================================================================
print("\n📋 T4: Compatibility matrix")

def t4_compatibility():
    compat = (DOCS_DIR / "compatibility.md").read_text()
    # All clients mentioned
    for client in ["Claude Code", "Gemini CLI", "Codex CLI", "UniversalMemoryClient",
                   "MCP Server", "Web Dashboard", "Python SDK"]:
        assert client in compat, f"Compatibility matrix missing client: {client}"
    # Key features mentioned
    for feature in ["Create decision", "Create fact", "Get context", "Health check",
                    "Switch branch", "Create checkpoint"]:
        assert feature in compat, f"Compatibility matrix missing feature: {feature}"
run("T4: Compatibility matrix covers all clients and key features", t4_compatibility)


# ================================================================
# T5: Branch spec reflects implementation
# ================================================================
print("\n📋 T5: Branch spec")

def t5_branch_spec():
    spec = (DOCS_DIR / "spec-branches.md").read_text()
    # All operations
    for op in ["Create Branch", "Switch Branch", "List Branches", "Compare Branches",
               "Replay Branch", "Merge Branch", "Delete Branch", "Detect Conflicts"]:
        assert op in spec, f"Branch spec missing operation: {op}"
    # Merge strategies
    assert "merge" in spec and "replace" in spec, "Missing merge strategies"
    # Conflict detection
    assert "conflict" in spec.lower(), "Missing conflict detection"
    # Branch-aware tables
    for table in ["decisions", "learned_facts", "goals", "tasks", "error_resolutions"]:
        assert table in spec, f"Branch spec missing table: {table}"
run("T5: Branch spec covers all implemented operations", t5_branch_spec)


# ================================================================
# T6: Event spec reflects taxonomy
# ================================================================
print("\n📋 T6: Event spec")

def t6_event_spec():
    spec = (DOCS_DIR / "spec-events.md").read_text()
    # Import actual constants
    from v2_common import VALID_AGENT_EVENT_TYPES, VALID_EVENT_PHASES
    # All 18 types
    for et in VALID_AGENT_EVENT_TYPES:
        assert et in spec, f"Event spec missing type: {et}"
    # All phases
    for phase in VALID_EVENT_PHASES:
        assert phase in spec, f"Event spec missing phase: {phase}"
    # Three-table explanation
    assert "universal_events" in spec, "Missing universal_events context"
    assert "agent_activity_log" in spec, "Missing agent_activity_log context"
    assert "agent_events" in spec, "Missing agent_events context"
run("T6: Event spec covers all 18 types and 4 phases", t6_event_spec)


# ================================================================
# T7: Adapter spec matches implementations
# ================================================================
print("\n📋 T7: Adapter spec")

def t7_adapter_spec():
    spec = (DOCS_DIR / "spec-adapters.md").read_text()
    # Required metadata fields
    for field in ["cli_name", "agent_name", "provider", "model_name", "session_id", "project_path"]:
        assert field in spec, f"Adapter spec missing metadata field: {field}"
    # Required methods
    for method in ["start_session", "get_context", "create_decision", "create_fact",
                   "create_goal", "create_task", "create_resolution", "send_event",
                   "get_activity", "get_health"]:
        assert method in spec, f"Adapter spec missing method: {method}"
    # Existing adapters mentioned
    assert "GeminiMemoryAdapter" in spec, "Missing Gemini adapter reference"
    assert "CodexMemoryAdapter" in spec, "Missing Codex adapter reference"
    assert "MCP Server" in spec, "Missing MCP server reference"
    assert "UniversalMemoryClient" in spec, "Missing client reference"
run("T7: Adapter spec covers metadata, methods, and all implementations", t7_adapter_spec)


# ================================================================
# T8: Validator accepts valid payloads
# ================================================================
print("\n📋 T8-T9: Validator")

def t8_validator_valid():
    from spec_validator import validate_decision, validate_fact, validate_task, \
                               validate_goal, validate_resolution, validate_event

    # Valid decision
    errs = validate_decision({"title": "Use Redis", "description": "For caching", "category": "technical"})
    assert not errs, f"Valid decision rejected: {errs}"

    # Valid fact
    errs = validate_fact({"fact": "Redis port is 6379", "fact_type": "technical"})
    assert not errs, f"Valid fact rejected: {errs}"

    # Valid task
    errs = validate_task({"title": "Write tests", "status": "todo", "priority": "high"})
    assert not errs, f"Valid task rejected: {errs}"

    # Valid goal
    errs = validate_goal({"title": "Launch v2", "priority": "critical"})
    assert not errs, f"Valid goal rejected: {errs}"

    # Valid resolution
    errs = validate_resolution({"resolution": "pip install xyz", "resolution_type": "dependency"})
    assert not errs, f"Valid resolution rejected: {errs}"

    # Valid event
    errs = validate_event({"event_type": "agent_started", "title": "Test", "event_phase": "start"})
    assert not errs, f"Valid event rejected: {errs}"

    # Minimal payloads (only required fields)
    assert not validate_decision({"title": "X"})
    assert not validate_fact({"fact": "X"})
    assert not validate_task({"title": "X"})
    assert not validate_goal({"title": "X"})
    assert not validate_resolution({"resolution": "X"})
    assert not validate_event({"event_type": "api_call"})
run("T8: Validator accepts all valid payloads", t8_validator_valid)


# ================================================================
# T9: Validator rejects invalid payloads
# ================================================================

def t9_validator_invalid():
    from spec_validator import validate_decision, validate_fact, validate_task, \
                               validate_goal, validate_resolution, validate_event

    # Missing required
    errs = validate_decision({})
    assert len(errs) >= 1, "Should reject decision without title"
    assert any("title" in e for e in errs)

    errs = validate_fact({})
    assert len(errs) >= 1, "Should reject fact without fact"

    errs = validate_event({})
    assert len(errs) >= 1, "Should reject event without event_type"

    # Invalid enum values
    errs = validate_decision({"title": "X", "category": "bogus"})
    assert len(errs) >= 1, "Should reject invalid category"

    errs = validate_task({"title": "X", "status": "invalid_status"})
    assert len(errs) >= 1, "Should reject invalid task status"

    errs = validate_event({"event_type": "nonexistent_type"})
    assert len(errs) >= 1, "Should reject invalid event_type"

    errs = validate_event({"event_type": "agent_started", "event_phase": "bogus"})
    assert len(errs) >= 1, "Should reject invalid event_phase"

    errs = validate_event({"event_type": "agent_started", "success_flag": 5})
    assert len(errs) >= 1, "Should reject invalid success_flag"

    errs = validate_event({"event_type": "agent_started", "duration_ms": -1})
    assert len(errs) >= 1, "Should reject negative duration"

    # Empty required string
    errs = validate_decision({"title": ""})
    assert len(errs) >= 1, "Should reject empty title"
    errs = validate_decision({"title": "  "})
    assert len(errs) >= 1, "Should reject whitespace-only title"
run("T9: Validator rejects invalid payloads gracefully", t9_validator_invalid)


# ================================================================
# T10: No breaking API changes
# ================================================================
print("\n📋 T10-T11: Regression")

def t10_api_unchanged():
    # Verify Flask blueprints still register all expected endpoints
    os.environ.setdefault("MEMORY_DB_PATH", str(PROJECT_ROOT / "tests" / "test_13_temp.db"))
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

    # Universal API
    for ep in ["/api/v1/decisions", "/api/v1/facts", "/api/v1/goals", "/api/v1/tasks",
               "/api/v1/resolutions", "/api/v1/events", "/api/v1/context",
               "/api/v1/agent-events", "/api/v1/health", "/api/v1/activity"]:
        assert ep in rules, f"Missing endpoint: {ep}"

    # Dashboard API
    for ep in ["/api/dashboard", "/api/branches", "/api/checkpoints",
               "/api/health", "/api/events", "/api/timeline"]:
        assert ep in rules, f"Missing endpoint: {ep}"

    # Cleanup temp
    temp_db = PROJECT_ROOT / "tests" / "test_13_temp.db"
    if temp_db.exists():
        temp_db.unlink()
run("T10: All API endpoints still registered", t10_api_unchanged)


# ================================================================
# T11: Existing docs not invalidated
# ================================================================

def t11_existing_docs():
    existing = ["quickstart.md", "architecture.md", "api.md", "adapters.md",
                "branches.md", "configuration.md", "mcp.md"]
    for doc in existing:
        fp = DOCS_DIR / doc
        assert fp.exists(), f"Existing doc deleted: docs/{doc}"
        content = fp.read_text()
        assert len(content) > 100, f"docs/{doc} appears truncated"
run("T11: All 7 existing docs preserved", t11_existing_docs)


# ================================================================
# CLEANUP & REPORT
# ================================================================
temp_db = PROJECT_ROOT / "tests" / "test_13_temp.db"
if temp_db.exists():
    temp_db.unlink()

print(f"\n{'='*60}")
print(f"Phase 13 Results: {passed} passed, {failed} failed / {passed+failed} total")
print(f"{'='*60}")

if failed:
    print("\n❌ FAILURES:")
    for name, ok, err in results:
        if not ok:
            print(f"  {name}: {err}")

sys.exit(0 if failed == 0 else 1)
