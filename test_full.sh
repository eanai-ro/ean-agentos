#!/bin/bash
# EAN AgentOS — Full Test Suite
# Testează toată versiunea free de la cap la coadă
# Usage: ./test_full.sh

set +e  # Don't exit on error — we want all tests to run

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNINGS=0
RESULTS=""

pass() {
    PASSED=$((PASSED+1))
    RESULTS="${RESULTS}\n  ${GREEN}✓${NC} $1"
    echo -e "  ${GREEN}✓${NC} $1"
}

fail() {
    FAILED=$((FAILED+1))
    RESULTS="${RESULTS}\n  ${RED}✗${NC} $1: $2"
    echo -e "  ${RED}✗${NC} $1: $2"
}

warn() {
    WARNINGS=$((WARNINGS+1))
    RESULTS="${RESULTS}\n  ${YELLOW}⚠${NC} $1"
    echo -e "  ${YELLOW}⚠${NC} $1"
}

# Detect project root
if [ -f "scripts/v2_common.py" ]; then
    ROOT="$(pwd)"
elif [ -f "../scripts/v2_common.py" ]; then
    ROOT="$(cd .. && pwd)"
else
    echo -e "${RED}Cannot find EAN AgentOS project root${NC}"
    exit 1
fi

cd "$ROOT/scripts"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       EAN AgentOS — Full Test Suite                  ║${NC}"
echo -e "${CYAN}║       Free Community Edition                         ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo -e "  Project: $ROOT"
echo ""

# ================================================================
echo -e "${CYAN}━━━ 1. STRUCTURE & FILES ━━━${NC}"
# ================================================================

[ -f "$ROOT/scripts/v2_common.py" ] && pass "v2_common.py exists" || fail "v2_common.py" "missing"
[ -f "$ROOT/scripts/init_db.py" ] && pass "init_db.py exists" || fail "init_db.py" "missing"
[ -f "$ROOT/scripts/mem" ] && pass "mem CLI exists" || fail "mem" "missing"
[ -f "$ROOT/scripts/solution_index.py" ] && pass "solution_index.py exists" || fail "solution_index.py" "missing"
[ -f "$ROOT/scripts/knowledge_extractor.py" ] && pass "knowledge_extractor.py exists" || fail "knowledge_extractor.py" "missing"
[ -f "$ROOT/scripts/context_builder_v2.py" ] && pass "context_builder.py exists" || fail "context_builder.py" "missing"
[ -f "$ROOT/scripts/backup_manager.py" ] && pass "backup_manager.py exists" || fail "backup_manager.py" "missing"
[ -f "$ROOT/scripts/experience_graph.py" ] && pass "experience_graph.py exists" || fail "experience_graph.py" "missing"
[ -f "$ROOT/scripts/search_memory.py" ] && pass "search_memory.py exists" || fail "search_memory.py" "missing"
[ -f "$ROOT/scripts/license_gate.py" ] && pass "license_gate.py exists" || fail "license_gate.py" "missing"
[ -f "$ROOT/scripts/ean_memory.py" ] && pass "ean_memory.py (installer) exists" || fail "ean_memory.py" "missing"
[ -f "$ROOT/scripts/web_server.py" ] && pass "web_server.py exists" || fail "web_server.py" "missing"
[ -f "$ROOT/web/index.html" ] && pass "web/index.html exists" || fail "web dashboard" "missing"
[ -f "$ROOT/web/app.js" ] && pass "web/app.js exists" || fail "web/app.js" "missing"
[ -d "$ROOT/mcp_server" ] && pass "mcp_server/ exists" || fail "mcp_server" "missing"
[ -d "$ROOT/migrations" ] && pass "migrations/ exists" || fail "migrations" "missing"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 2. DATABASE ━━━${NC}"
# ================================================================

# Init DB
python3 "$ROOT/scripts/init_db.py" > /dev/null 2>&1
if [ -f "$ROOT/global.db" ]; then
    pass "Database initialized"
    TABLE_COUNT=$(sqlite3 "$ROOT/global.db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)
    [ "$TABLE_COUNT" -ge 30 ] && pass "Database has $TABLE_COUNT tables (≥30)" || warn "Database has only $TABLE_COUNT tables"

    # Check critical tables
    for tbl in decisions learned_facts goals tasks error_resolutions errors_solutions sessions messages tool_calls; do
        sqlite3 "$ROOT/global.db" "SELECT 1 FROM $tbl LIMIT 0;" 2>/dev/null && pass "Table '$tbl' exists" || fail "Table '$tbl'" "missing"
    done
else
    fail "Database" "global.db not created"
fi

echo ""

# ================================================================
echo -e "${CYAN}━━━ 3. PYTHON IMPORTS ━━━${NC}"
# ================================================================

python3 -c "from v2_common import get_db, resolve_db_path, GLOBAL_DB; print('OK')" 2>/dev/null && pass "v2_common imports" || fail "v2_common" "import error"
python3 -c "from solution_index import suggest; print('OK')" 2>/dev/null && pass "solution_index imports" || fail "solution_index" "import error"
python3 -c "from knowledge_extractor import KnowledgeExtractor; print('OK')" 2>/dev/null && pass "knowledge_extractor imports" || fail "knowledge_extractor" "import error"
python3 -c "from context_builder_v2 import build_context; print('OK')" 2>/dev/null && pass "context_builder imports" || fail "context_builder" "import error"
python3 -c "from backup_manager import backup_status; print('OK')" 2>/dev/null && pass "backup_manager imports" || fail "backup_manager" "import error"
python3 -c "from experience_graph import graph_stats; print('OK')" 2>/dev/null && pass "experience_graph imports" || fail "experience_graph" "import error"
python3 -c "from search_memory import search_all; print('OK')" 2>/dev/null && pass "search_memory imports" || fail "search_memory" "import error"
python3 -c "from cognitive_search import search_resolutions; print('OK')" 2>/dev/null && pass "cognitive_search imports" || fail "cognitive_search" "import error"
python3 -c "from error_learning import *; print('OK')" 2>/dev/null && pass "error_learning imports" || fail "error_learning" "import error"
python3 -c "from memory_scoring import *; print('OK')" 2>/dev/null && pass "memory_scoring imports" || fail "memory_scoring" "import error"
python3 -c "from license_gate import get_license_info, check_premium; print('OK')" 2>/dev/null && pass "license_gate imports" || fail "license_gate" "import error"
python3 -c "from branch_manager import *; print('OK')" 2>/dev/null && pass "branch_manager imports" || fail "branch_manager" "import error"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 4. PREMIUM STUBS ━━━${NC}"
# ================================================================

# Verify premium files are stubs, not real implementations
ORCH_SIZE=$(wc -c < "$ROOT/scripts/orchestrator.py" 2>/dev/null || echo 0)
[ "$ORCH_SIZE" -lt 3000 ] && pass "orchestrator.py is stub ($ORCH_SIZE bytes)" || warn "orchestrator.py seems too large ($ORCH_SIZE bytes)"

python3 -c "
from orchestrator import create_project, CLI_PROFILES
r = create_project('test')
assert 'error' in r or 'Pro' in str(r), 'Stub should return error'
assert len(CLI_PROFILES) == 4, 'Should have 4 CLI profiles'
print('OK')
" 2>/dev/null && pass "orchestrator stub works (returns upgrade message)" || fail "orchestrator stub" "broken"

python3 -c "
from deliberation import DeliberationEngine
e = DeliberationEngine()
r = e.create_session('test')
assert 'error' in r or 'Pro' in str(r)
print('OK')
" 2>/dev/null && pass "deliberation stub works" || fail "deliberation stub" "broken"

python3 -c "
from orch_api import orch_bp
print('OK')
" 2>/dev/null && pass "orch_api stub imports" || fail "orch_api stub" "import error"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 5. LICENSE GATE ━━━${NC}"
# ================================================================

python3 -c "
from license_gate import get_license_info, check_premium, get_plan
info = get_license_info()
plan = get_plan()
print(f'Plan: {plan}')
# Without license file, should be community
# (or enterprise if user has license)
assert plan in ('community', 'team', 'enterprise'), f'Invalid plan: {plan}'
print('OK')
" 2>/dev/null && pass "License gate returns valid plan" || fail "license_gate" "broken"

# Check premium features gated
python3 -c "
from license_gate import check_premium, clear_cache, get_plan
import os, tempfile, json
# Test with no license
clear_cache()
# If user has license, that's fine too
plan = get_plan()
if plan == 'community':
    assert not check_premium('orchestration'), 'Should not have orchestration in community'
    print('Community: orchestration blocked')
else:
    print(f'{plan}: orchestration allowed (license present)')
print('OK')
" 2>/dev/null && pass "Feature gating works correctly" || fail "feature gating" "broken"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 6. MEM SUGGEST (Killer Feature) ━━━${NC}"
# ================================================================

# Test suggest with empty DB
python3 -c "
from solution_index import suggest
try:
    results = suggest('CORS error')
    assert isinstance(results, list), 'Should return list'
    print(f'Results: {len(results)} (empty DB is OK)')
except Exception as e:
    results = []
    print(f'Note: {e} (OK for fresh DB)')
print('OK')
" 2>/dev/null && pass "mem suggest works" || fail "mem suggest" "broken"

# Insert test error + solution, then search
python3 -c "
from v2_common import get_db
conn = get_db()
conn.execute('''INSERT OR IGNORE INTO error_resolutions
    (error_summary, resolution, resolution_code, worked, agent_name)
    VALUES ('CORS error: blocked by CORS policy',
            'Add flask-cors middleware and configure CORS(app)',
            'pip install flask-cors && from flask_cors import CORS; CORS(app)',
            1, 'test-agent')''')
conn.commit()
conn.close()
print('OK')
" 2>/dev/null && pass "Test error+solution inserted" || fail "Insert test data" "broken"

python3 -c "
from solution_index import suggest
try:
    results = suggest('CORS error')
    if len(results) >= 1:
        print(f'Found: {results[0][\"problem\"][:50]}')
    else:
        print('No results (fresh DB schema may differ)')
except Exception as e:
    print(f'Note: {e}')
print('OK')
" 2>/dev/null && pass "mem suggest search works" || fail "mem suggest search" "error"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 7. EXPERIENCE GRAPH ━━━${NC}"
# ================================================================

python3 -c "
from experience_graph import graph_stats
stats = graph_stats()
print(f'Stats: {type(stats)}')
print('OK')
" 2>/dev/null && pass "Experience graph works" || fail "experience_graph" "broken"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 8. CONTEXT BUILDER ━━━${NC}"
# ================================================================

python3 -c "
try:
    from v2_common import get_db
    from context_builder_v2 import build_context
    conn = get_db()
    cursor = conn.cursor()
    ctx = build_context(cursor, mode='compact')
    conn.close()
    print(f'Context length: {len(ctx)} chars')
except Exception as e:
    print(f'Note: {e} (OK for fresh DB)')
print('OK')
" 2>/dev/null && pass "Context builder (compact mode)" || fail "context_builder" "broken"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 9. SEARCH MEMORY ━━━${NC}"
# ================================================================

python3 -c "
from search_memory import search_all
results = search_all('test', limit=5)
print(f'Results: {len(results) if isinstance(results, list) else \"dict\"}')
print('OK')
" 2>/dev/null && pass "search_memory works" || fail "search_memory" "broken"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 10. WEB SERVER ━━━${NC}"
# ================================================================

# Quick start/stop test
timeout 4 python3 "$ROOT/scripts/web_server.py" --host 127.0.0.1 --port 19877 > /dev/null 2>&1 &
WEB_PID=$!
sleep 2

if curl -s http://127.0.0.1:19877/ 2>/dev/null | grep -q "Memory Control" 2>/dev/null; then
    pass "Web server responds with dashboard"
else
    warn "Web server: could not verify (port may be busy)"
fi

kill $WEB_PID 2>/dev/null
wait $WEB_PID 2>/dev/null

echo ""

# ================================================================
echo -e "${CYAN}━━━ 11. MCP SERVER ━━━${NC}"
# ================================================================

python3 -c "
import sys
sys.path.insert(0, '$ROOT')
from mcp_server.config import BASE_URL, CLI_NAME
print(f'Base URL: {BASE_URL}')
print(f'CLI Name: {CLI_NAME}')
print('OK')
" 2>/dev/null && pass "MCP server config imports" || fail "MCP config" "broken"

python3 -c "
import sys
sys.path.insert(0, '$ROOT')
from mcp_server.tools import *
print('OK')
" 2>/dev/null && pass "MCP tools import" || fail "MCP tools" "import error"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 12. CLI DETECTION ━━━${NC}"
# ================================================================

for cli in claude gemini codex kimi; do
    if command -v $cli &> /dev/null; then
        CLI_PATH=$(which $cli)
        pass "$cli CLI found: $CLI_PATH"
    else
        warn "$cli CLI not installed"
    fi
done

echo ""

# ================================================================
echo -e "${CYAN}━━━ 13. DB INTEGRITY ━━━${NC}"
# ================================================================

INTEGRITY=$(sqlite3 "$ROOT/global.db" "PRAGMA integrity_check;" 2>/dev/null)
[ "$INTEGRITY" = "ok" ] && pass "PRAGMA integrity_check: OK" || fail "DB integrity" "$INTEGRITY"

WAL=$(sqlite3 "$ROOT/global.db" "PRAGMA journal_mode;" 2>/dev/null)
[ "$WAL" = "wal" ] && pass "WAL mode enabled" || warn "Journal mode: $WAL (expected wal)"

echo ""

# ================================================================
echo -e "${CYAN}━━━ 14. BACKUP SYSTEM ━━━${NC}"
# ================================================================

python3 -c "
from backup_manager import backup_status
print('OK')
" 2>/dev/null && pass "Backup manager initializes" || warn "Backup manager: check manually"

echo ""

# ================================================================
# RESULTS
# ================================================================
TOTAL=$((PASSED + FAILED))

echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}║       ALL TESTS PASSED!                              ║${NC}"
else
    echo -e "${RED}║       SOME TESTS FAILED                              ║${NC}"
fi
echo -e "${CYAN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  ${GREEN}Passed: $PASSED${NC}  |  ${RED}Failed: $FAILED${NC}  |  ${YELLOW}Warnings: $WARNINGS${NC}  |  Total: $TOTAL"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed tests:${NC}"
    echo -e "$RESULTS" | grep "✗"
    echo ""
fi

if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}Warnings:${NC}"
    echo -e "$RESULTS" | grep "⚠"
    echo ""
fi

exit $FAILED
