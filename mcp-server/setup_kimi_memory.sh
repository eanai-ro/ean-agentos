#!/bin/bash
# Setup Kimi Memory MCP Server
# Rulează: bash setup_kimi_memory.sh

set -e

echo "🚀 Setup Kimi Memory MCP Server"
echo "================================"

# 1. Creează directoarele
MEMORY_DIR="$HOME/.kimi/memory"
mkdir -p "$MEMORY_DIR/scripts"
mkdir -p "$MEMORY_DIR/mcp-server"
mkdir -p "$MEMORY_DIR/backups"

echo "✅ Directoare create"

# 2. Copiază MCP server
cp kimi_memory_server.py "$MEMORY_DIR/mcp-server/"
chmod +x "$MEMORY_DIR/mcp-server/kimi_memory_server.py"

echo "✅ MCP server copiat"

# 3. Copiază DB din Claude (dacă există)
CLAUDE_DB="$HOME/.ean-agentos/global.db"
KIMI_DB="$MEMORY_DIR/global.db"

if [ -f "$CLAUDE_DB" ]; then
    if [ -f "$KIMI_DB" ]; then
        echo "⚠️  DB există deja în Kimi. Backup înainte de suprascriere?"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cp "$CLAUDE_DB" "$KIMI_DB"
            echo "✅ DB copiat din Claude"
        fi
    else
        cp "$CLAUDE_DB" "$KIMI_DB"
        echo "✅ DB copiat din Claude"
    fi
else
    echo "❌ DB Claude nu există. Creezi DB nou?"
    # Aici poți adăuga inițializare DB nou
fi

# 4. Creează symlink pentru CLI
CLI_SCRIPT="$MEMORY_DIR/mcp-server/kimi_memory_server.py"
SYMLINK="$HOME/.local/bin/kimi-memory"

if [ -d "$HOME/.local/bin" ]; then
    ln -sf "$CLI_SCRIPT" "$SYMLINK" 2>/dev/null || true
    echo "✅ Symlink creat: kimii-memory"
fi

# 5. Detectează config Kimi
KIMI_CONFIG="$HOME/.config/kimi/kimi-cli.toml"
KIMI_CONFIG_OLD="$HOME/.kimi/config.toml"

if [ -f "$KIMI_CONFIG" ]; then
    CONFIG_FILE="$KIMI_CONFIG"
elif [ -f "$KIMI_CONFIG_OLD" ]; then
    CONFIG_FILE="$KIMI_CONFIG_OLD"
else
    CONFIG_FILE=""
fi

echo ""
echo "📋 Următorii pași:"
echo "=================="

if [ -n "$CONFIG_FILE" ]; then
    echo ""
    echo "1. Adaugă în $CONFIG_FILE:"
    echo ""
    cat << 'EOF'
[mcp]
enabled = true

[[mcp.servers]]
name = "memory"
command = "python3"
args = ["$HOME/.kimi/memory/mcp-server/kimi_memory_server.py"]
EOF
else
    echo "1. Nu am găsit config Kimi. Creează manual:"
    echo "   ~/.config/kimi/kimi-cli.toml"
fi

echo ""
echo "2. Setează environment variable (adaugă în ~/.bashrc):"
echo "   export MEMORY_DB_PATH=\"$HOME/.kimi/memory/global.db\""
echo ""
echo "3. Testează standalone:"
echo "   python3 $MEMORY_DIR/mcp-server/kimi_memory_server.py stats"
echo ""
echo "4. Pornește Kimi și întreabă-mă:"
echo "   'Caută în memorie cum am configurat Docker'"
echo ""
echo "🎉 Setup complet!"
