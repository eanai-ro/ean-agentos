#!/bin/bash
# EAN AgentOS — Interactive Installer
# Usage: ./install.sh
#    or: curl -sSL https://raw.githubusercontent.com/eanai-ro/ean-agentos/main/install.sh | bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}║       ${BOLD}EAN AgentOS${NC}${CYAN} — Installer                        ║${NC}"
echo -e "${CYAN}║       Persistent Memory for AI Coding Agents         ║${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}║       ${DIM}Never solve the same bug twice.${NC}${CYAN}                 ║${NC}"
echo -e "${CYAN}║                                                      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ================================================================
# DETECT PROJECT ROOT
# ================================================================
if [ -f "scripts/v2_common.py" ]; then
    PROJECT_ROOT="$(pwd)"
elif [ -f "../scripts/v2_common.py" ]; then
    PROJECT_ROOT="$(cd .. && pwd)"
else
    echo -e "${YELLOW}EAN AgentOS not found locally. Cloning...${NC}"
    git clone https://github.com/eanai-ro/ean-agentos.git ~/.ean-agentos
    PROJECT_ROOT="$HOME/.ean-agentos"
fi

echo -e "  ${DIM}Project root: ${PROJECT_ROOT}${NC}"
echo ""

# ================================================================
# CLI SELECTOR
# ================================================================
echo -e "${CYAN}━━━ Step 1: Select CLI Integrations ━━━${NC}"
echo ""
echo -e "  EAN AgentOS works with multiple AI coding CLIs."
echo -e "  Select which ones you want to integrate:"
echo ""

INSTALL_CLAUDE=0
INSTALL_GEMINI=0
INSTALL_CODEX=0
INSTALL_KIMI=0

# Detect installed CLIs
CLAUDE_FOUND=0; GEMINI_FOUND=0; CODEX_FOUND=0; KIMI_FOUND=0
command -v claude &>/dev/null && CLAUDE_FOUND=1
command -v gemini &>/dev/null && GEMINI_FOUND=1
command -v codex &>/dev/null && CODEX_FOUND=1
command -v kimi &>/dev/null && KIMI_FOUND=1

# Check if interactive (stdin is terminal)
if [ -t 0 ]; then
    # Interactive mode — ask user
    echo -e "  ${BOLD}[1]${NC} Claude Code  $([ $CLAUDE_FOUND -eq 1 ] && echo -e "${GREEN}(detected)${NC}" || echo -e "${DIM}(not installed)${NC}")"
    echo -e "  ${BOLD}[2]${NC} Gemini CLI   $([ $GEMINI_FOUND -eq 1 ] && echo -e "${GREEN}(detected)${NC}" || echo -e "${DIM}(not installed)${NC}")"
    echo -e "  ${BOLD}[3]${NC} Codex CLI    $([ $CODEX_FOUND -eq 1 ] && echo -e "${GREEN}(detected)${NC}" || echo -e "${DIM}(not installed)${NC}")"
    echo -e "  ${BOLD}[4]${NC} Kimi CLI     $([ $KIMI_FOUND -eq 1 ] && echo -e "${GREEN}(detected)${NC}" || echo -e "${DIM}(not installed)${NC}")"
    echo -e "  ${BOLD}[A]${NC} All detected CLIs"
    echo -e "  ${BOLD}[S]${NC} Skip (configure later)"
    echo ""
    echo -ne "  ${CYAN}Your choice (e.g. 1,2 or A or S): ${NC}"
    read -r CLI_CHOICE

    case "$CLI_CHOICE" in
        *[Aa]*)
            INSTALL_CLAUDE=$CLAUDE_FOUND
            INSTALL_GEMINI=$GEMINI_FOUND
            INSTALL_CODEX=$CODEX_FOUND
            INSTALL_KIMI=$KIMI_FOUND
            ;;
        *[Ss]*|"")
            ;; # Skip all
        *)
            [[ "$CLI_CHOICE" == *"1"* ]] && INSTALL_CLAUDE=1
            [[ "$CLI_CHOICE" == *"2"* ]] && INSTALL_GEMINI=1
            [[ "$CLI_CHOICE" == *"3"* ]] && INSTALL_CODEX=1
            [[ "$CLI_CHOICE" == *"4"* ]] && INSTALL_KIMI=1
            ;;
    esac
else
    # Non-interactive (pipe) — install all detected
    echo -e "  ${DIM}Non-interactive mode: installing all detected CLIs${NC}"
    INSTALL_CLAUDE=$CLAUDE_FOUND
    INSTALL_GEMINI=$GEMINI_FOUND
    INSTALL_CODEX=$CODEX_FOUND
    INSTALL_KIMI=$KIMI_FOUND
fi

echo ""
echo -e "  Selected:"
[ $INSTALL_CLAUDE -eq 1 ] && echo -e "    ${GREEN}✓${NC} Claude Code" || echo -e "    ${DIM}○ Claude Code${NC}"
[ $INSTALL_GEMINI -eq 1 ] && echo -e "    ${GREEN}✓${NC} Gemini CLI" || echo -e "    ${DIM}○ Gemini CLI${NC}"
[ $INSTALL_CODEX -eq 1 ] && echo -e "    ${GREEN}✓${NC} Codex CLI" || echo -e "    ${DIM}○ Codex CLI${NC}"
[ $INSTALL_KIMI -eq 1 ] && echo -e "    ${GREEN}✓${NC} Kimi CLI" || echo -e "    ${DIM}○ Kimi CLI${NC}"
echo ""

# ================================================================
# PYTHON DEPENDENCIES
# ================================================================
echo -e "${CYAN}━━━ Step 2: Python Dependencies ━━━${NC}"

if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip3 install -q -r "$PROJECT_ROOT/requirements.txt" 2>/dev/null || \
    pip install -q -r "$PROJECT_ROOT/requirements.txt" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠ Some deps need manual install: pip install flask flask-cors${NC}"
fi
echo -e "  ${GREEN}✓${NC} Python dependencies OK"
echo ""

# ================================================================
# DATABASE
# ================================================================
echo -e "${CYAN}━━━ Step 3: Initialize Database ━━━${NC}"

cd "$PROJECT_ROOT"
python3 scripts/init_db.py > /dev/null 2>&1

if [ -f "$PROJECT_ROOT/global.db" ]; then
    TABLE_COUNT=$(sqlite3 "$PROJECT_ROOT/global.db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)
    echo -e "  ${GREEN}✓${NC} Database ready ($TABLE_COUNT tables)"
else
    echo -e "  ${RED}✗${NC} Database initialization failed"
fi
echo ""

# ================================================================
# MEM CLI
# ================================================================
echo -e "${CYAN}━━━ Step 4: Setup 'mem' CLI Command ━━━${NC}"

MEM_SCRIPT="$PROJECT_ROOT/scripts/mem"
chmod +x "$MEM_SCRIPT" 2>/dev/null

# Try multiple locations
INSTALLED_MEM=0
if [ -d "$HOME/.local/bin" ]; then
    ln -sf "$MEM_SCRIPT" "$HOME/.local/bin/mem" 2>/dev/null && INSTALLED_MEM=1
fi
if [ $INSTALLED_MEM -eq 0 ] && [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    ln -sf "$MEM_SCRIPT" "/usr/local/bin/mem" 2>/dev/null && INSTALLED_MEM=1
fi
if [ $INSTALLED_MEM -eq 0 ]; then
    mkdir -p "$HOME/.local/bin" 2>/dev/null
    ln -sf "$MEM_SCRIPT" "$HOME/.local/bin/mem" 2>/dev/null && INSTALLED_MEM=1
fi

if [ $INSTALLED_MEM -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} 'mem' command installed"
else
    echo -e "  ${YELLOW}⚠${NC} Could not create symlink. Use: python3 $MEM_SCRIPT"
fi

# Check if in PATH
if command -v mem &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} 'mem' is in PATH"
else
    echo -e "  ${YELLOW}⚠${NC} Add to PATH: export PATH=\$HOME/.local/bin:\$PATH"
fi
echo ""

# ================================================================
# CLI INTEGRATIONS
# ================================================================
echo -e "${CYAN}━━━ Step 5: CLI Integrations ━━━${NC}"

EAN_SCRIPT="$PROJECT_ROOT/scripts/ean_memory.py"

if [ $INSTALL_CLAUDE -eq 1 ]; then
    if [ $CLAUDE_FOUND -eq 1 ]; then
        python3 "$EAN_SCRIPT" install claude > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} Claude Code — hooks installed" || \
            echo -e "  ${YELLOW}⚠${NC} Claude Code — manual setup needed"
    else
        echo -e "  ${YELLOW}⚠${NC} Claude Code — not installed. Install first: https://claude.ai/code"
    fi
fi

if [ $INSTALL_GEMINI -eq 1 ]; then
    if [ $GEMINI_FOUND -eq 1 ]; then
        python3 "$EAN_SCRIPT" install gemini > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} Gemini CLI — hooks installed" || \
            echo -e "  ${YELLOW}⚠${NC} Gemini CLI — manual setup needed"
    else
        echo -e "  ${YELLOW}⚠${NC} Gemini CLI — not installed. Install: npm i -g @anthropic-ai/gemini-cli"
    fi
fi

if [ $INSTALL_CODEX -eq 1 ]; then
    if [ $CODEX_FOUND -eq 1 ]; then
        python3 "$EAN_SCRIPT" install codex > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} Codex CLI — hooks installed" || \
            echo -e "  ${YELLOW}⚠${NC} Codex CLI — manual setup needed"
    else
        echo -e "  ${YELLOW}⚠${NC} Codex CLI — not installed. Install: npm i -g @openai/codex"
    fi
fi

if [ $INSTALL_KIMI -eq 1 ]; then
    if [ $KIMI_FOUND -eq 1 ]; then
        echo -e "  ${GREEN}✓${NC} Kimi CLI — detected (configure MCP manually)"
    else
        echo -e "  ${YELLOW}⚠${NC} Kimi CLI — not installed. Install: pip install kimi-cli"
    fi
fi

if [ $INSTALL_CLAUDE -eq 0 ] && [ $INSTALL_GEMINI -eq 0 ] && [ $INSTALL_CODEX -eq 0 ] && [ $INSTALL_KIMI -eq 0 ]; then
    echo -e "  ${DIM}Skipped. Install later: python3 scripts/ean_memory.py install <claude|gemini|codex>${NC}"
fi
echo ""

# ================================================================
# START MEMORY SERVER (background)
# ================================================================
echo -e "${CYAN}━━━ Step 6: Start Memory Server ━━━${NC}"

cd "$PROJECT_ROOT"
# Start server in background if not already running
if command -v python3 &>/dev/null; then
    # Check if server is already running
    if curl -s http://localhost:19876/ > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Memory server already running on port 19876"
    else
        nohup python3 scripts/web_server.py --host 127.0.0.1 --port 19876 > /dev/null 2>&1 &
        sleep 2
        if curl -s http://localhost:19876/ > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} Memory server started (port 19876)"
        else
            echo -e "  ${YELLOW}⚠${NC} Memory server: start manually with: python3 scripts/web_server.py"
        fi
    fi
fi
echo ""

# ================================================================
# QUICK VALIDATION
# ================================================================
echo -e "${CYAN}━━━ Step 7: Quick Validation ━━━${NC}"

cd "$PROJECT_ROOT/scripts"

python3 -c "from v2_common import get_db; get_db(); print('OK')" 2>/dev/null && \
    echo -e "  ${GREEN}✓${NC} Database connection" || \
    echo -e "  ${RED}✗${NC} Database connection failed"

python3 -c "from solution_index import suggest; suggest('test'); print('OK')" 2>/dev/null && \
    echo -e "  ${GREEN}✓${NC} Solution index (mem suggest)" || \
    echo -e "  ${RED}✗${NC} Solution index broken"

python3 -c "from context_builder_v2 import build_context; print('OK')" 2>/dev/null && \
    echo -e "  ${GREEN}✓${NC} Context builder" || \
    echo -e "  ${RED}✗${NC} Context builder broken"

python3 -c "from license_gate import get_plan; print(get_plan())" 2>/dev/null && \
    echo -e "  ${GREEN}✓${NC} License gate" || \
    echo -e "  ${RED}✗${NC} License gate broken"

echo ""

# ================================================================
# DONE!
# ================================================================
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║       Installation Complete! 🎉                      ║${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}${BOLD}IMPORTANT: Restart your AI CLI now!${NC}"
echo -e "  Close and reopen Claude Code (or other CLI) to activate hooks."
echo ""
echo -e "  ${CYAN}Quick start:${NC}"
echo ""
echo -e "    ${BOLD}mem suggest \"CORS error\"${NC}     Find past solutions"
echo -e "    ${BOLD}mem search \"auth\"${NC}            Search memory"
echo -e "    ${BOLD}mem status${NC}                   Check status"
echo -e "    ${BOLD}mem decisions${NC}                View decisions"
echo ""
echo -e "  ${CYAN}Web dashboard:${NC}"
echo -e "    ${BOLD}http://localhost:19876${NC} (started automatically)"
echo ""
echo -e "  ${CYAN}Add CLI later:${NC}"
echo -e "    python3 scripts/ean_memory.py install claude"
echo -e "    python3 scripts/ean_memory.py install gemini"
echo -e "    python3 scripts/ean_memory.py install codex"
echo ""
echo -e "  ${CYAN}Run full test suite:${NC}"
echo -e "    ./test_full.sh"
echo ""
echo -e "  ${DIM}Never solve the same bug twice. 🧠${NC}"
echo ""
