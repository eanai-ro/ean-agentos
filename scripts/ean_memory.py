#!/usr/bin/env python3
"""
ean-memory — Installer & Runtime CLI for Universal Agent Memory.

Commands:
    ean-memory install claude|gemini|codex   Install integration for an agent
    ean-memory start [--port PORT]           Start the memory server
    ean-memory stop                          Stop the memory server
    ean-memory status                        Show runtime status
    ean-memory test                          Quick validation (server, API, DB)
    ean-memory doctor                        Detailed diagnostics
    ean-memory uninstall claude|gemini|codex  Remove integration for an agent
"""

import argparse
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# === CONSTANTS ===

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
MCP_SERVER_DIR = PROJECT_ROOT / "mcp_server"
PID_FILE = PROJECT_ROOT / ".ean-memory.pid"
DEFAULT_PORT = 19876
DEFAULT_HOST = "0.0.0.0"
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from v2_common import resolve_db_path as _resolve_db_path
    MEMORY_DB_DEFAULT = _resolve_db_path()
except ImportError:
    MEMORY_DB_DEFAULT = Path.home() / ".claude" / "memory" / "global.db"

# Agent-specific paths
CLAUDE_DIR = Path.home() / ".claude"
GEMINI_DIR = Path.home() / ".gemini"
CODEX_DIR = Path.home() / ".codex"

# Adapters
GEMINI_ADAPTER = SCRIPTS_DIR / "adapters" / "gemini_cli_adapter.py"
CODEX_ADAPTER = SCRIPTS_DIR / "adapters" / "codex_cli_adapter.py"
CODEX_WATCHER = SCRIPTS_DIR / "codex_rollout_watcher.py"
UNIVERSAL_CLIENT = SCRIPTS_DIR / "clients" / "universal_memory_client.py"


# === HELPERS ===

def _ok(msg):
    print(f"  \033[32m✅ {msg}\033[0m")

def _warn(msg):
    print(f"  \033[33m⚠️  {msg}\033[0m")

def _err(msg):
    print(f"  \033[31m❌ {msg}\033[0m")

def _info(msg):
    print(f"  \033[36mℹ️  {msg}\033[0m")

def _header(title):
    print(f"\n\033[1m{'='*60}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'='*60}\033[0m\n")

def _port_in_use(port):
    """Check if port is currently in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0
    except (PermissionError, OSError):
        return False

def _api_healthy(port=DEFAULT_PORT):
    """Check if API server responds to health check."""
    try:
        url = f"http://localhost:{port}/api/v1/health"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get("ok", False)
    except Exception:
        return False

def _get_pid():
    """Read PID from pidfile, verify process exists."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # check if alive
        return pid
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return None

def _backup_file(path):
    """Create timestamped backup of a file."""
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".backup_{ts}{path.suffix}")
    shutil.copy2(path, backup)
    return backup

def _which(cmd):
    """Check if a command exists in PATH."""
    return shutil.which(cmd)

def _db_path():
    """Determine the database path. Mirrors resolve_db_path() from v2_common.py:
    1. MEMORY_DB_PATH env var (override explicit)
    2. <project_root>/global.db (canonical V2)
    3. ~/.claude/memory/global.db (legacy fallback)
    """
    env_path = os.environ.get("MEMORY_DB_PATH")
    if env_path:
        return Path(env_path)
    project_db = PROJECT_ROOT / "global.db"
    if project_db.exists():
        return project_db
    if MEMORY_DB_DEFAULT.exists():
        return MEMORY_DB_DEFAULT
    # Default: project-local (init_db will create it)
    return project_db


# === DISCOVERY ===

def _detect_environment():
    """Detect available agents and system state."""
    env = {}

    # Claude Code
    env["claude_available"] = _which("claude") is not None
    env["claude_dir"] = CLAUDE_DIR.exists()
    env["claude_mcp_json"] = (CLAUDE_DIR / ".mcp.json").exists()
    env["ean_memory_db"] = MEMORY_DB_DEFAULT.exists()

    # Gemini CLI
    env["gemini_available"] = _which("gemini") is not None
    env["gemini_dir"] = GEMINI_DIR.exists()
    env["gemini_adapter_installed"] = (GEMINI_DIR / "gemini_cli_adapter.py").exists()

    # Codex CLI
    env["codex_available"] = _which("codex") is not None
    env["codex_dir"] = CODEX_DIR.exists()
    env["codex_adapter_installed"] = (CODEX_DIR / "codex_cli_adapter.py").exists()

    # Server
    env["port_in_use"] = _port_in_use(DEFAULT_PORT)
    env["api_healthy"] = _api_healthy() if env["port_in_use"] else False
    env["pid"] = _get_pid()

    # MCP
    env["mcp_server_exists"] = (MCP_SERVER_DIR / "server.py").exists()

    # DB
    db = _db_path()
    env["db_path"] = str(db)
    env["db_exists"] = db.exists()

    return env


# === HOOKS HELPERS ===

HOOKS_DIR = SCRIPTS_DIR / "hooks"
EAN_MEMORY_DIR = Path.home() / ".ean-memory"
SETTINGS_JSON = Path.home() / ".claude" / "settings.json"

# Tag used to identify our hooks (for dedup and uninstall)
_HOOK_TAG = "ean-memory"

def _build_hooks_config():
    """Build the hooks config dict that ean-memory installs into settings.json."""
    return {
        "PreToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash {HOOKS_DIR / 'pre_tool.sh'}",
                        "timeout": 5000
                    }
                ]
            }
        ],
        "PostToolUse": [
            {
                "matcher": ".*",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash {HOOKS_DIR / 'post_tool.sh'}",
                        "timeout": 10000
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash {HOOKS_DIR / 'session_start.sh'}",
                        "timeout": 5000
                    }
                ]
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash {HOOKS_DIR / 'session_end.sh'}",
                        "timeout": 10000
                    }
                ]
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash {HOOKS_DIR / 'user_prompt.sh'}",
                        "timeout": 3000
                    }
                ]
            }
        ],
        "PreCompact": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash {HOOKS_DIR / 'pre_compact.sh'}",
                        "timeout": 5000
                    }
                ]
            }
        ],
    }


def _is_our_hook(hook_entry):
    """Check if a hook entry was installed by ean-memory (by checking command path)."""
    if isinstance(hook_entry, dict):
        for h in hook_entry.get("hooks", []):
            cmd = h.get("command", "")
            if "ean-agentos" in cmd or "ean-memory" in cmd or str(HOOKS_DIR) in cmd:
                return True
    return False


def _merge_hooks_into_settings(settings):
    """Merge ean-memory hooks into existing settings.json, deduplicating."""
    our_hooks = _build_hooks_config()

    if "hooks" not in settings:
        settings["hooks"] = {}

    for event_type, our_entries in our_hooks.items():
        existing = settings["hooks"].get(event_type, [])

        # Remove any previous ean-memory hooks (dedup)
        cleaned = [e for e in existing if not _is_our_hook(e)]

        # Append our hooks
        cleaned.extend(our_entries)
        settings["hooks"][event_type] = cleaned

    return settings


def _remove_hooks_from_settings(settings):
    """Remove only ean-memory hooks from settings.json."""
    hooks = settings.get("hooks", {})
    for event_type in list(hooks.keys()):
        cleaned = [e for e in hooks[event_type] if not _is_our_hook(e)]
        if cleaned:
            hooks[event_type] = cleaned
        else:
            del hooks[event_type]
    if not hooks:
        del settings["hooks"]
    return settings


def _install_hooks():
    """Install hooks into ~/.claude/settings.json with backup + merge."""
    # Read existing settings
    settings = {}
    if SETTINGS_JSON.exists():
        try:
            settings = json.loads(SETTINGS_JSON.read_text())
        except json.JSONDecodeError:
            _warn("settings.json invalid, se va recrea")

    # Backup
    if SETTINGS_JSON.exists():
        backup = _backup_file(SETTINGS_JSON)
        if backup:
            _info(f"Backup settings.json: {backup}")

    # Merge
    settings = _merge_hooks_into_settings(settings)

    # Write
    SETTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_JSON.write_text(json.dumps(settings, indent=2) + "\n")

    # Create MEMORY_DIR
    EAN_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (EAN_MEMORY_DIR / "sessions").mkdir(exist_ok=True)
    (EAN_MEMORY_DIR / "file_versions").mkdir(exist_ok=True)

    return True


def _uninstall_hooks():
    """Remove ean-memory hooks from ~/.claude/settings.json."""
    if not SETTINGS_JSON.exists():
        return False

    settings = {}
    try:
        settings = json.loads(SETTINGS_JSON.read_text())
    except json.JSONDecodeError:
        return False

    if "hooks" not in settings:
        return False

    # Backup
    backup = _backup_file(SETTINGS_JSON)
    if backup:
        _info(f"Backup settings.json: {backup}")

    settings = _remove_hooks_from_settings(settings)
    SETTINGS_JSON.write_text(json.dumps(settings, indent=2) + "\n")
    return True


# === GEMINI HOOKS HELPERS ===

GEMINI_HOOKS_DIR = SCRIPTS_DIR / "hooks" / "gemini"
GEMINI_SETTINGS_JSON = GEMINI_DIR / "settings.json"
GEMINI_HOOK_SCRIPT = GEMINI_HOOKS_DIR / "gemini_hook.py"


def _build_gemini_hooks_config():
    """Build Gemini CLI hooks config dict."""
    hook_cmd = f"python3 {GEMINI_HOOK_SCRIPT}"
    return {
        "SessionStart": [
            {
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} session_start", "timeout": 5000}
                ]
            }
        ],
        "BeforeAgent": [
            {
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} user_prompt", "timeout": 3000}
                ]
            }
        ],
        "AfterAgent": [
            {
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} assistant_response", "timeout": 5000}
                ]
            }
        ],
        "BeforeTool": [
            {
                "matcher": "replace|write_file|multi_edit",
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} pre_tool", "timeout": 5000}
                ]
            }
        ],
        "AfterTool": [
            {
                "matcher": ".*",
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} post_tool", "timeout": 10000}
                ]
            }
        ],
        "SessionEnd": [
            {
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} session_end", "timeout": 10000}
                ]
            }
        ],
        "PreCompress": [
            {
                "hooks": [
                    {"type": "command", "command": f"{hook_cmd} pre_compact", "timeout": 5000}
                ]
            }
        ],
    }


def _is_our_gemini_hook(hook_entry):
    """Check if a Gemini hook entry was installed by ean-memory."""
    if isinstance(hook_entry, dict):
        for h in hook_entry.get("hooks", []):
            cmd = h.get("command", "")
            if "ean-agentos" in cmd or "gemini_hook.py" in cmd:
                return True
    return False


def _merge_gemini_hooks(settings):
    """Merge ean-memory hooks into Gemini settings, deduplicating."""
    our_hooks = _build_gemini_hooks_config()

    if "hooks" not in settings:
        settings["hooks"] = {}

    for event_type, our_entries in our_hooks.items():
        existing = settings["hooks"].get(event_type, [])
        cleaned = [e for e in existing if not _is_our_gemini_hook(e)]
        cleaned.extend(our_entries)
        settings["hooks"][event_type] = cleaned

    return settings


def _remove_gemini_hooks(settings):
    """Remove only ean-memory hooks from Gemini settings."""
    hooks = settings.get("hooks", {})
    for event_type in list(hooks.keys()):
        cleaned = [e for e in hooks[event_type] if not _is_our_gemini_hook(e)]
        if cleaned:
            hooks[event_type] = cleaned
        else:
            del hooks[event_type]
    if not hooks and "hooks" in settings:
        del settings["hooks"]
    return settings


def _install_gemini_hooks():
    """Install hooks into ~/.gemini/settings.json with backup + merge."""
    settings = {}
    if GEMINI_SETTINGS_JSON.exists():
        try:
            settings = json.loads(GEMINI_SETTINGS_JSON.read_text())
        except json.JSONDecodeError:
            _warn("Gemini settings.json invalid, se va recrea")

    if GEMINI_SETTINGS_JSON.exists():
        backup = _backup_file(GEMINI_SETTINGS_JSON)
        if backup:
            _info(f"Backup Gemini settings.json: {backup}")

    settings = _merge_gemini_hooks(settings)

    GEMINI_SETTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    GEMINI_SETTINGS_JSON.write_text(json.dumps(settings, indent=2) + "\n")

    EAN_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (EAN_MEMORY_DIR / "sessions").mkdir(exist_ok=True)
    (EAN_MEMORY_DIR / "file_versions").mkdir(exist_ok=True)

    return True


def _uninstall_gemini_hooks():
    """Remove ean-memory hooks from ~/.gemini/settings.json."""
    if not GEMINI_SETTINGS_JSON.exists():
        return False

    try:
        settings = json.loads(GEMINI_SETTINGS_JSON.read_text())
    except json.JSONDecodeError:
        return False

    if "hooks" not in settings:
        return False

    backup = _backup_file(GEMINI_SETTINGS_JSON)
    if backup:
        _info(f"Backup Gemini settings.json: {backup}")

    settings = _remove_gemini_hooks(settings)
    GEMINI_SETTINGS_JSON.write_text(json.dumps(settings, indent=2) + "\n")
    return True


# === INSTALL COMMANDS ===

def _install_claude(args):
    """Install Universal Agent Memory integration for Claude Code."""
    _header("INSTALL — Claude Code")

    env = _detect_environment()

    if not env["claude_dir"]:
        _err(f"Directorul {CLAUDE_DIR} nu există. Instalează Claude Code mai întâi.")
        return False

    _ok(f"Directorul Claude Code găsit: {CLAUDE_DIR}")

    steps_done = 0

    # Step 1: Check/add MCP server to .mcp.json
    mcp_json_path = CLAUDE_DIR / ".mcp.json"
    mcp_config = {}

    if mcp_json_path.exists():
        try:
            mcp_config = json.loads(mcp_json_path.read_text())
        except json.JSONDecodeError:
            _warn(f".mcp.json existent dar invalid, se va recrea")
            backup = _backup_file(mcp_json_path)
            if backup:
                _info(f"Backup: {backup}")

    if "mcpServers" not in mcp_config:
        mcp_config["mcpServers"] = {}

    if "universal-memory" in mcp_config.get("mcpServers", {}):
        _ok("MCP server 'universal-memory' deja configurat în .mcp.json")
        steps_done += 1
    else:
        # Backup existing config
        if mcp_json_path.exists():
            backup = _backup_file(mcp_json_path)
            if backup:
                _info(f"Backup config existent: {backup}")

        mcp_config["mcpServers"]["universal-memory"] = {
            "command": "python3",
            "args": [str(MCP_SERVER_DIR / "server.py")],
            "env": {
                "MEMORY_BASE_URL": f"http://localhost:{DEFAULT_PORT}",
                "MEMORY_PROJECT_PATH": str(Path.home()),
                "MEMORY_CLI_NAME": "claude-code",
                "MEMORY_AGENT_NAME": "claude-code",
                "MEMORY_MODEL_NAME": "claude-opus-4-6",
                "MEMORY_PROVIDER": "anthropic"
            }
        }
        mcp_json_path.write_text(json.dumps(mcp_config, indent=2) + "\n")
        _ok(f"MCP server adăugat în {mcp_json_path}")
        steps_done += 1

    # Step 2: Install hooks into settings.json
    _info("Configurez hooks pentru captură automată...")
    if _install_hooks():
        _ok("Hooks configurate în settings.json (6 event types)")
        _info(f"  DB path: {EAN_MEMORY_DIR / 'global.db'}")
        _info(f"  Sessions: {EAN_MEMORY_DIR / 'sessions'}")
        steps_done += 1
    else:
        _err("Nu am putut configura hooks")

    # Step 3: Initialize DB with all tables (core + V2)
    db_path = EAN_MEMORY_DIR / "global.db"
    try:
        init_db_script = SCRIPTS_DIR / "init_db.py"
        if init_db_script.exists():
            env_copy = os.environ.copy()
            env_copy["MEMORY_DB_PATH"] = str(db_path)
            result = subprocess.run(
                ["python3", str(init_db_script)],
                capture_output=True, timeout=10, env=env_copy
            )
            if result.returncode == 0:
                _ok(f"Baza de date inițializată: {db_path}")
            else:
                _warn(f"Init DB warning: {result.stderr.decode()[:200]}")
        else:
            _warn("init_db.py nu a fost găsit")
    except Exception as e:
        _warn(f"Init DB fallback: {e}")
    steps_done += 1

    # Step 4: Check universal client
    if UNIVERSAL_CLIENT.exists():
        _ok(f"Client universal disponibil: {UNIVERSAL_CLIENT}")
    else:
        _err(f"Client universal lipsă: {UNIVERSAL_CLIENT}")
    steps_done += 1

    print()
    _ok(f"Claude Code integration completă ({steps_done} pași)")
    print()
    print("  Ce s-a configurat:")
    print(f"    • Hooks: 6 event types în {SETTINGS_JSON}")
    print(f"    • MCP:   universal-memory în .mcp.json")
    print(f"    • DB:    {db_path}")
    print()
    print("  Pași următori:")
    print("    1. Pornește serverul: ean-memory start")
    print("    2. Repornește Claude Code (hooks se activează automat)")
    print("    3. Verifică: ean-memory test")
    print()
    print("  Captură automată activă pentru:")
    print("    ✓ Mesaje utilizator (UserPromptSubmit)")
    print("    ✓ Tool calls (PostToolUse)")
    print("    ✓ Backup fișiere (PreToolUse: Edit/Write)")
    print("    ✓ Erori (detectate automat)")
    print("    ✓ Sesiuni (SessionStart/Stop)")
    return True


def _install_gemini(args):
    """Install Universal Agent Memory integration for Gemini CLI."""
    _header("INSTALL — Gemini CLI")

    env = _detect_environment()

    if not env["gemini_dir"]:
        _warn(f"Directorul {GEMINI_DIR} nu există.")
        _info("Creez directorul...")
        GEMINI_DIR.mkdir(parents=True, exist_ok=True)

    _ok(f"Directorul Gemini: {GEMINI_DIR}")

    steps_done = 0

    # Step 1: Copy adapter + client (for API mode, optional)
    dest = GEMINI_DIR / "gemini_cli_adapter.py"
    if dest.exists():
        if dest.read_bytes() == GEMINI_ADAPTER.read_bytes():
            _ok("Adaptorul Gemini deja instalat (versiune curentă)")
        else:
            backup = _backup_file(dest)
            _info(f"Backup adaptor vechi: {backup}")
            shutil.copy2(GEMINI_ADAPTER, dest)
            _ok("Adaptorul Gemini actualizat")
    else:
        shutil.copy2(GEMINI_ADAPTER, dest)
        _ok(f"Adaptor copiat: {dest}")

    client_dest = GEMINI_DIR / "universal_memory_client.py"
    if client_dest.exists():
        if client_dest.read_bytes() == UNIVERSAL_CLIENT.read_bytes():
            _ok("Client universal deja instalat (versiune curentă)")
        else:
            shutil.copy2(UNIVERSAL_CLIENT, client_dest)
            _ok("Client universal actualizat")
    else:
        shutil.copy2(UNIVERSAL_CLIENT, client_dest)
        _ok(f"Client universal copiat: {client_dest}")
    steps_done += 1

    # Step 2: Install hooks for automatic capture
    _info("Configurez hooks pentru captură automată...")
    if _install_gemini_hooks():
        _ok("Hooks configurate în Gemini settings.json (7 event types)")
        _info(f"  DB path: {EAN_MEMORY_DIR / 'global.db'}")
        _info(f"  Sessions: {EAN_MEMORY_DIR / 'sessions'}")
        steps_done += 1
    else:
        _err("Nu am putut configura hooks Gemini")

    # Step 3: Initialize DB with all tables
    db_path = EAN_MEMORY_DIR / "global.db"
    try:
        init_db_script = SCRIPTS_DIR / "init_db.py"
        if init_db_script.exists():
            env_copy = os.environ.copy()
            env_copy["MEMORY_DB_PATH"] = str(db_path)
            result = subprocess.run(
                ["python3", str(init_db_script)],
                capture_output=True, timeout=10, env=env_copy
            )
            if result.returncode == 0:
                _ok(f"Baza de date inițializată: {db_path}")
            else:
                _warn(f"Init DB warning: {result.stderr.decode()[:200]}")
        else:
            _warn("init_db.py nu a fost găsit")
    except Exception as e:
        _warn(f"Init DB fallback: {e}")
    steps_done += 1

    # Step 4: Create integration config
    config_dest = GEMINI_DIR / "memory_config.json"
    config = {
        "memory_server": f"http://localhost:{DEFAULT_PORT}",
        "provider": "google",
        "agent_name": "gemini-agent",
        "cli_name": "gemini-cli",
        "auto_context": True,
        "context_mode": "compact"
    }
    if config_dest.exists():
        _ok("Configurare memorie deja existentă")
    else:
        config_dest.write_text(json.dumps(config, indent=2) + "\n")
        _ok(f"Configurare memorie creată: {config_dest}")
    steps_done += 1

    print()
    _ok(f"Gemini CLI integration completă ({steps_done} pași)")
    print()
    print("  Ce s-a configurat:")
    print(f"    • Hooks: 7 event types în {GEMINI_SETTINGS_JSON}")
    print(f"    • Adapter: {dest}")
    print(f"    • DB:    {db_path}")
    print()
    print("  Pași următori:")
    print("    1. Repornește Gemini CLI (hooks se activează automat)")
    print("    2. Verifică: ean-memory status")
    print()
    print("  Captură automată activă pentru:")
    print("    ✓ Mesaje utilizator (BeforeAgent)")
    print("    ✓ Răspunsuri asistent (AfterAgent)")
    print("    ✓ Tool calls (AfterTool)")
    print("    ✓ Backup fișiere (BeforeTool: replace/write_file)")
    print("    ✓ Erori (detectate automat)")
    print("    ✓ Sesiuni (SessionStart/SessionEnd)")
    print("    ✓ Pre-compress (PreCompress)")
    return True


def _codex_watcher_service_path():
    """Returnează calea systemd user service pentru Codex watcher."""
    return Path.home() / ".config" / "systemd" / "user" / "ean-codex-watcher.service"


def _systemctl_user_available():
    """Verifică dacă systemctl --user este disponibil în sesiunea curentă."""
    if _which("systemctl") is None:
        return False, "systemctl nu este în PATH"
    try:
        ret = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True, text=True, timeout=5
        )
        if ret.returncode == 0:
            return True, ""
        msg = (ret.stderr or ret.stdout or "").strip()
        return False, msg or "systemctl --user indisponibil"
    except Exception as e:
        return False, str(e)


def _run_systemctl_user(args):
    """Rulează systemctl --user și întoarce subprocess.CompletedProcess."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True, text=True
    )


def _install_codex_watcher():
    """Instalează și pornește Codex rollout watcher ca systemd user service."""
    service_path = _codex_watcher_service_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)

    watcher_path = CODEX_WATCHER.resolve()
    python_path = Path(sys.executable).resolve()
    watcher_cmd = f"{shlex.quote(str(python_path))} {shlex.quote(str(watcher_path))} --watch --interval 10"
    service_content = (
        "[Unit]\n"
        "Description=EAN Memory - Codex CLI Rollout Watcher\n"
        "After=default.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={watcher_path.parent}\n"
        f"ExecStart={watcher_cmd}\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        f"Environment=MEMORY_DIR={EAN_MEMORY_DIR}\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    service_path.write_text(service_content)
    _ok(f"Serviciu systemd creat: {service_path}")

    available, reason = _systemctl_user_available()
    if not available:
        _warn("systemd --user indisponibil; watcher-ul nu poate fi pornit ca serviciu")
        if reason:
            _info(f"  motiv: {reason}")
        _info(f"  rulează manual: {python_path} {watcher_path} --watch --interval 10")
        return False

    # Reload și pornește
    reload_ret = _run_systemctl_user(["daemon-reload"])
    if reload_ret.returncode != 0:
        _warn("systemctl daemon-reload a eșuat")
        _info((reload_ret.stderr or reload_ret.stdout or "").strip()[:220])
        return False
    enable_ret = _run_systemctl_user(["enable", "ean-codex-watcher.service"])
    if enable_ret.returncode != 0:
        _warn("systemctl enable a eșuat")
        _info((enable_ret.stderr or enable_ret.stdout or "").strip()[:220])
    start_ret = _run_systemctl_user(["start", "ean-codex-watcher.service"])
    if start_ret.returncode != 0:
        _warn("systemctl start a eșuat")
        _info((start_ret.stderr or start_ret.stdout or "").strip()[:220])
        _info(f"  rulează manual: {python_path} {watcher_path} --watch --interval 10")
        return False

    # Verifică starea
    ret = _run_systemctl_user(["is-active", "--quiet", "ean-codex-watcher.service"])
    if ret.returncode == 0:
        _ok("Watcher pornit și activ (systemd user service)")
    else:
        _warn("Serviciul systemd nu a pornit — poți rula manual:")
        _info(f"  {python_path} {watcher_path} --watch --interval 10")
        return False

    return True


def _uninstall_codex_watcher():
    """Oprește și elimină Codex watcher systemd service."""
    service_path = _codex_watcher_service_path()
    state_file = EAN_MEMORY_DIR / "codex_watcher_state.json"

    available, _ = _systemctl_user_available()
    if available:
        _run_systemctl_user(["stop", "ean-codex-watcher.service"])
        _run_systemctl_user(["disable", "ean-codex-watcher.service"])

    if service_path.exists():
        service_path.unlink()
        if available:
            _run_systemctl_user(["daemon-reload"])
        _ok("Serviciu systemd Codex watcher eliminat")
        removed = True
    else:
        _info("Nu exista serviciu systemd pentru Codex watcher")
        removed = False

    if state_file.exists():
        state_file.unlink()
        _ok(f"State watcher șters: {state_file}")
        removed = True

    return removed


def _install_codex(args):
    """Install Universal Agent Memory integration for Codex CLI."""
    _header("INSTALL — Codex CLI")

    env = _detect_environment()

    if not env["codex_dir"]:
        _warn(f"Directorul {CODEX_DIR} nu există.")
        _info("Creez directorul...")
        CODEX_DIR.mkdir(parents=True, exist_ok=True)

    _ok(f"Directorul Codex: {CODEX_DIR}")

    steps_done = 0

    # Step 1: Copy adapter + client
    dest = CODEX_DIR / "codex_cli_adapter.py"
    if dest.exists():
        if dest.read_bytes() == CODEX_ADAPTER.read_bytes():
            _ok("Adaptorul Codex deja instalat (versiune curentă)")
        else:
            backup = _backup_file(dest)
            _info(f"Backup adaptor vechi: {backup}")
            shutil.copy2(CODEX_ADAPTER, dest)
            _ok("Adaptorul Codex actualizat")
    else:
        shutil.copy2(CODEX_ADAPTER, dest)
        _ok(f"Adaptor copiat: {dest}")
    steps_done += 1

    # Step 2: Copy universal client (dependency)
    client_dest = CODEX_DIR / "universal_memory_client.py"
    if client_dest.exists():
        if client_dest.read_bytes() == UNIVERSAL_CLIENT.read_bytes():
            _ok("Client universal deja instalat (versiune curentă)")
        else:
            backup = _backup_file(client_dest)
            _info(f"Backup client vechi: {backup}")
            shutil.copy2(UNIVERSAL_CLIENT, client_dest)
            _ok("Client universal actualizat")
    else:
        shutil.copy2(UNIVERSAL_CLIENT, client_dest)
        _ok(f"Client universal copiat: {client_dest}")
    steps_done += 1

    # Step 3: Init DB (same DB used by watcher/memory_daemon)
    EAN_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    db_path = EAN_MEMORY_DIR / "global.db"
    _info(f"Inițializez baza de date: {db_path}")
    init_env = os.environ.copy()
    init_env["MEMORY_DB_PATH"] = str(db_path)
    init_res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "init_db.py")],
        env=init_env, capture_output=True, text=True
    )
    if init_res.returncode == 0:
        _ok(f"Baza de date: {db_path}")
    else:
        _warn("Init DB a eșuat")
        _info((init_res.stderr or init_res.stdout or "").strip()[:220])
    steps_done += 1

    # Step 4: Import rollout history (--once)
    _info("Import istoric Codex (rollout JSONL)...")
    try:
        result = subprocess.run(
            [sys.executable, str(CODEX_WATCHER), "--once"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "MEMORY_DIR": str(EAN_MEMORY_DIR)}
        )
        if result.returncode != 0:
            _warn(f"Import istoric a eșuat (rc={result.returncode})")
            if result.stderr:
                _info(result.stderr.strip().splitlines()[-1][:220])
        elif "daemon non-zero" in (result.stderr or ""):
            _warn("Import istoric a avut erori parțiale (vezi logs watcher)")
        # Parsăm numărul de evenimente din stderr
        for line in (result.stderr or "").splitlines():
            if "once complete" in line:
                _ok(line.replace("[CODEX-WATCHER] ", ""))
                break
        else:
            _info("Import istoric rulat (fără rezumat explicit)")
    except subprocess.TimeoutExpired:
        _warn("Import timeout (>120s) — va continua în background cu watcher-ul")
    steps_done += 1

    # Step 5: Install + start watcher service
    _info("Instalez Codex rollout watcher (systemd user service)...")
    watcher_ok = _install_codex_watcher()
    if not watcher_ok:
        _warn("Watcher service neactiv; fallback manual disponibil")
    steps_done += 1

    # Step 6: Config
    config_dest = CODEX_DIR / "memory_config.json"
    config = {
        "memory_dir": str(EAN_MEMORY_DIR),
        "provider": "openai",
        "agent_name": "codex",
        "cli_name": "codex-cli",
        "model_name": "o3",
        "auto_capture": True,
        "watcher_mode": "systemd"
    }
    if config_dest.exists():
        _ok("Configurare memorie deja existentă")
    else:
        config_dest.write_text(json.dumps(config, indent=2) + "\n")
        _ok(f"Configurare memorie creată: {config_dest}")
    steps_done += 1

    print()
    _ok(f"Codex CLI integration completă ({steps_done} pași)")
    print()
    print("  Auto-captură activă:")
    print("    ✓ Mesaje user/assistant")
    print("    ✓ Tool calls (function_call / function_call_output)")
    print("    ✓ Sesiuni")
    print("    ✓ Istoric importat")
    print()
    print("  Watcher: systemctl --user status ean-codex-watcher")
    print("  Manual:  python3 scripts/codex_rollout_watcher.py --once")
    print("  Status:  python3 scripts/codex_rollout_watcher.py --status")
    print()
    return True


def _install_kimi(args):
    """Install EAN AgentOS integration for Kimi CLI."""
    _header("INSTALL — Kimi CLI")

    kimi_config_dir = Path.home() / ".config" / "kimi"
    kimi_config_file = kimi_config_dir / "kimi-cli.toml"

    # Alternativ: ~/.kimi/config.toml
    alt_config = Path.home() / ".kimi" / "config.toml"

    config_file = kimi_config_file if kimi_config_file.exists() else alt_config

    if not config_file.parent.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        _info(f"Creat directorul: {config_file.parent}")

    # Determine DB path
    db_path = str(PROJECT_ROOT / "global.db")

    # MCP server path
    mcp_server = str(PROJECT_ROOT / "mcp_server" / "server.py")

    # Build TOML config for Kimi
    mcp_config = f"""
# EAN AgentOS — Kimi CLI Memory Integration
# Auto-generated by ean_memory.py install kimi

[mcp]
enabled = true

[[mcp.servers]]
name = "universal-memory"
command = "python3"
args = ["{mcp_server}"]

[mcp.servers.env]
MEMORY_DB_PATH = "{db_path}"
MEMORY_BASE_URL = "http://localhost:19876"
MEMORY_CLI_NAME = "kimi-cli"
MEMORY_AGENT_NAME = "kimi-cli"
"""

    if config_file.exists():
        # Backup existing config
        backup = _backup_file(config_file)
        _info(f"Backup: {backup}")

        # Check if already configured
        existing = config_file.read_text()
        if "universal-memory" in existing:
            _ok("MCP server 'universal-memory' deja configurat")
        else:
            # Append MCP config
            with open(config_file, 'a') as f:
                f.write(mcp_config)
            _ok("MCP server adăugat la configurația existentă")
    else:
        config_file.write_text(mcp_config)
        _ok(f"Configurație Kimi creată: {config_file}")

    # Init DB
    EAN_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    db_actual = Path(db_path)
    if not db_actual.exists():
        _info("Inițializez baza de date...")
        init_env = os.environ.copy()
        init_env["MEMORY_DB_PATH"] = db_path
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "init_db.py")],
                      env=init_env, capture_output=True)
    _ok(f"Baza de date: {db_path}")

    _ok("Kimi CLI integration completă")
    print()
    _info("Pași următori:")
    _info("  1. Repornește Kimi CLI")
    _info("  2. Verifică cu: kimi --help")
    print()


def cmd_install(args):
    """Route install command to the right agent installer."""
    installers = {
        "claude": _install_claude,
        "gemini": _install_gemini,
        "codex": _install_codex,
        "kimi": _install_kimi,
    }
    target = args.target
    if target not in installers:
        _err(f"Target necunoscut: {target}")
        print(f"  Disponibile: {', '.join(installers.keys())}")
        return
    installers[target](args)


# === UNINSTALL ===

def cmd_uninstall(args):
    """Remove integration for an agent."""
    target = args.target
    _header(f"UNINSTALL — {target.title()}")

    if target == "claude":
        # 1. Remove MCP server
        mcp_json = CLAUDE_DIR / ".mcp.json"
        if mcp_json.exists():
            try:
                config = json.loads(mcp_json.read_text())
                if "universal-memory" in config.get("mcpServers", {}):
                    backup = _backup_file(mcp_json)
                    _info(f"Backup: {backup}")
                    del config["mcpServers"]["universal-memory"]
                    mcp_json.write_text(json.dumps(config, indent=2) + "\n")
                    _ok("MCP server 'universal-memory' eliminat din .mcp.json")
                else:
                    _info("MCP server nu era configurat")
            except json.JSONDecodeError:
                _err("Nu pot parsa .mcp.json")
        else:
            _info("Nu există .mcp.json")

        # 2. Remove hooks from settings.json
        if _uninstall_hooks():
            _ok("Hooks eliminate din settings.json")
        else:
            _info("Nu existau hooks ean-memory în settings.json")

    elif target == "gemini":
        # 1. Remove adapter files
        for f in ["gemini_cli_adapter.py", "universal_memory_client.py", "memory_config.json"]:
            p = GEMINI_DIR / f
            if p.exists():
                p.unlink()
                _ok(f"Șters: {p}")
            else:
                _info(f"Nu există: {p}")

        # 2. Remove hooks from Gemini settings.json
        if _uninstall_gemini_hooks():
            _ok("Hooks eliminate din Gemini settings.json")
        else:
            _info("Nu existau hooks ean-memory în Gemini settings.json")

    elif target == "codex":
        # 1. Stop and remove watcher service
        if _uninstall_codex_watcher():
            _ok("Codex watcher oprit și eliminat")
        else:
            _info("Nu exista watcher activ")

        # 2. Remove adapter files
        for f in ["codex_cli_adapter.py", "universal_memory_client.py", "memory_config.json"]:
            p = CODEX_DIR / f
            if p.exists():
                p.unlink()
                _ok(f"Șters: {p}")
            else:
                _info(f"Nu există: {p}")
    else:
        _err(f"Target necunoscut: {target}")
        return

    print()
    _ok(f"Integrare {target} dezinstalată.")
    _info("Baza de date și datele din memorie NU au fost șterse.")


# === RUNTIME ===

def cmd_start(args):
    """Start the memory server."""
    _header("START — Universal Agent Memory Server")

    port = getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT
    host = getattr(args, "host", DEFAULT_HOST) or DEFAULT_HOST

    # Check if already running
    pid = _get_pid()
    if pid:
        _warn(f"Serverul deja rulează (PID {pid})")
        if _api_healthy(port):
            _ok(f"API răspunde pe http://localhost:{port}")
        return

    if _port_in_use(port):
        _err(f"Portul {port} este deja ocupat de alt proces")
        _info("Folosește --port ALTPORT sau oprește procesul existent")
        return

    # Init DB
    db_path = _db_path()
    os.environ["MEMORY_DB_PATH"] = str(db_path)

    try:
        subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, '{SCRIPTS_DIR}'); "
             f"from init_db import init_database; "
             f"init_database('{db_path}')"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass  # DB init is best-effort; server will handle it

    # Start server in background
    log_file = PROJECT_ROOT / ".ean-memory-server.log"
    with open(log_file, "a") as logf:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPTS_DIR / "web_server.py"),
             "--port", str(port), "--host", host],
            stdout=logf, stderr=logf,
            start_new_session=True,
        )

    PID_FILE.write_text(str(proc.pid))

    # Wait for server to become ready
    for i in range(15):
        time.sleep(0.5)
        if _api_healthy(port):
            _ok(f"Server pornit (PID {proc.pid})")
            _ok(f"API: http://localhost:{port}")
            _ok(f"Dashboard: http://localhost:{port}")
            _info(f"DB: {db_path}")
            _info(f"Log: {log_file}")
            _info(f"PID: {PID_FILE}")
            return

    # Check if process is still alive
    if proc.poll() is not None:
        _err(f"Serverul s-a oprit imediat (exit code: {proc.returncode})")
        _info(f"Verifică logul: {log_file}")
    else:
        _warn("Serverul pornit dar API nu răspunde încă")
        _info(f"PID: {proc.pid}, Log: {log_file}")


def cmd_stop(args):
    """Stop the memory server."""
    _header("STOP — Universal Agent Memory Server")

    pid = _get_pid()
    if not pid:
        # Try to find by port
        if _port_in_use(DEFAULT_PORT):
            _warn(f"Portul {DEFAULT_PORT} e ocupat dar nu am PID salvat")
            _info("Folosește: lsof -i :19876 pentru a găsi procesul")
        else:
            _info("Serverul nu rulează")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for graceful shutdown
        for _ in range(10):
            time.sleep(0.3)
            try:
                os.kill(pid, 0)
            except OSError:
                break

        PID_FILE.unlink(missing_ok=True)
        _ok(f"Server oprit (PID {pid})")
    except OSError as e:
        _err(f"Nu pot opri procesul {pid}: {e}")
        PID_FILE.unlink(missing_ok=True)


def cmd_status(args):
    """Show runtime status."""
    _header("STATUS — Universal Agent Memory")

    env = _detect_environment()

    # Server
    pid = env["pid"]
    if pid:
        _ok(f"Server: RUNNING (PID {pid})")
    else:
        _err("Server: NOT RUNNING")

    # Port
    if env["port_in_use"]:
        _ok(f"Port {DEFAULT_PORT}: IN USE")
    else:
        _err(f"Port {DEFAULT_PORT}: FREE")

    # API
    if env["api_healthy"]:
        _ok("API: HEALTHY")
        try:
            url = f"http://localhost:{DEFAULT_PORT}/api/v1/health"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
                stats = []
                for key in ["decisions", "facts", "goals", "tasks", "resolutions"]:
                    if key in data:
                        stats.append(f"{key}={data[key]}")
                if stats:
                    _info(f"Entități: {', '.join(stats)}")
        except Exception:
            pass
    else:
        _err("API: NOT RESPONDING")

    # DB
    print()
    if env["db_exists"]:
        db = Path(env["db_path"])
        size_mb = db.stat().st_size / (1024 * 1024)
        _ok(f"DB: {env['db_path']} ({size_mb:.1f} MB)")
    else:
        _warn(f"DB: {env['db_path']} (nu există încă)")

    # MCP
    if env["mcp_server_exists"]:
        _ok("MCP Server: disponibil")
    else:
        _warn("MCP Server: nu există")

    # Agents
    print()
    print("  Agenți detectați:")
    if env["claude_available"]:
        _ok(f"Claude Code: instalat")
    else:
        _info("Claude Code: nu e în PATH")

    if env["gemini_available"]:
        _ok("Gemini CLI: instalat")
    elif env["gemini_dir"]:
        _info("Gemini CLI: director există, CLI nu e în PATH")
    else:
        _info("Gemini CLI: nedetectat")

    if env["codex_available"]:
        _ok("Codex CLI: instalat")
    elif env["codex_dir"]:
        _info("Codex CLI: director există, CLI nu e în PATH")
    else:
        _info("Codex CLI: nedetectat")

    # Integrations installed
    print()
    print("  Integrări instalate:")
    # Claude MCP
    if env["claude_mcp_json"]:
        try:
            mcp = json.loads((CLAUDE_DIR / ".mcp.json").read_text())
            if "universal-memory" in mcp.get("mcpServers", {}):
                _ok("Claude: MCP server configurat")
            else:
                _warn("Claude: .mcp.json există dar fără universal-memory")
        except Exception:
            _warn("Claude: .mcp.json invalid")
    else:
        _info("Claude: MCP neconfigurat")

    if env["gemini_adapter_installed"]:
        _ok("Gemini: adaptor instalat")
    else:
        _info("Gemini: adaptor neinstalat")

    if env["codex_adapter_installed"]:
        _ok("Codex: adaptor instalat")
    else:
        _info("Codex: adaptor neinstalat")


# === DIAGNOSTICS ===

def cmd_test(args):
    """Quick validation: server, API, DB, context."""
    _header("TEST — Quick Validation")

    passed = 0
    total = 0

    def check(name, condition, detail=""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            _ok(f"{name}" + (f" — {detail}" if detail else ""))
        else:
            _err(f"{name}" + (f" — {detail}" if detail else ""))

    # T1: Server
    port_up = _port_in_use(DEFAULT_PORT)
    check("Server port", port_up, f"localhost:{DEFAULT_PORT}")

    # T2: API health
    api_ok = _api_healthy()
    check("API health", api_ok)

    # T3: DB exists
    db = _db_path()
    check("Database", db.exists(), str(db))

    # T4: DB integrity
    if db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db))
            r = conn.execute("PRAGMA integrity_check").fetchone()
            ok = r[0] == "ok"
            conn.close()
            check("DB integrity", ok, r[0])
        except Exception as e:
            check("DB integrity", False, str(e))
    else:
        check("DB integrity", False, "DB nu există")

    # T5: Context endpoint
    if api_ok:
        try:
            url = f"http://localhost:{DEFAULT_PORT}/api/v1/context?mode=compact"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
                check("Context API", data.get("ok", False))
        except Exception as e:
            check("Context API", False, str(e))
    else:
        check("Context API", False, "API nu răspunde")

    # T6: MCP server file
    check("MCP server", (MCP_SERVER_DIR / "server.py").exists())

    # T7: Adapters present
    check("Gemini adapter", GEMINI_ADAPTER.exists())
    check("Codex adapter", CODEX_ADAPTER.exists())
    check("Universal client", UNIVERSAL_CLIENT.exists())

    print()
    color = "\033[32m" if passed == total else "\033[33m" if passed >= total - 2 else "\033[31m"
    print(f"  {color}Rezultat: {passed}/{total} PASS\033[0m")
    print()


def cmd_doctor(args):
    """Detailed diagnostics."""
    _header("DOCTOR — Detailed Diagnostics")

    env = _detect_environment()
    issues = []

    # Section 1: Core files
    print("  \033[1m[1/6] Fișiere core\033[0m")
    core_files = [
        (SCRIPTS_DIR / "web_server.py", "Web server"),
        (SCRIPTS_DIR / "mem", "CLI principal"),
        (SCRIPTS_DIR / "universal_api.py", "Universal API"),
        (SCRIPTS_DIR / "dashboard_api.py", "Dashboard API"),
        (SCRIPTS_DIR / "context_builder_v2.py", "Context builder"),
        (SCRIPTS_DIR / "init_db.py", "DB initializer"),
        (SCRIPTS_DIR / "v2_common.py", "Utilități partajate"),
        (SCRIPTS_DIR / "branch_manager.py", "Branch manager"),
        (MCP_SERVER_DIR / "server.py", "MCP server"),
    ]
    for path, name in core_files:
        if path.exists():
            _ok(name)
        else:
            _err(f"{name}: LIPSĂ ({path})")
            issues.append(f"Fișier lipsă: {path}")
    print()

    # Section 2: Database
    print("  \033[1m[2/6] Baza de date\033[0m")
    db = _db_path()
    if db.exists():
        _ok(f"Locație: {db}")
        size_mb = db.stat().st_size / (1024 * 1024)
        _ok(f"Dimensiune: {size_mb:.1f} MB")
        try:
            import sqlite3
            conn = sqlite3.connect(str(db))
            r = conn.execute("PRAGMA integrity_check").fetchone()
            if r[0] == "ok":
                _ok("Integritate: OK")
            else:
                _err(f"Integritate: {r[0]}")
                issues.append("DB integrity check failed")

            wal = conn.execute("PRAGMA journal_mode").fetchone()
            _ok(f"Journal mode: {wal[0]}")

            # Check key tables
            tables = [t[0] for t in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            expected = ["decisions", "learned_facts", "goals", "tasks",
                        "error_resolutions", "agent_events", "agent_activity_log"]
            missing = [t for t in expected if t not in tables]
            if missing:
                _err(f"Tabele lipsă: {', '.join(missing)}")
                issues.append(f"Tabele lipsă: {', '.join(missing)}")
            else:
                _ok(f"Tabele V2: toate prezente ({len(expected)}/{len(expected)})")

            conn.close()
        except Exception as e:
            _err(f"Eroare DB: {e}")
            issues.append(f"DB error: {e}")
    else:
        _warn(f"DB nu există: {db}")
        _info("Va fi creată automat la 'ean-memory start'")
    print()

    # Section 3: Server & API
    print("  \033[1m[3/6] Server & API\033[0m")
    if env["port_in_use"]:
        _ok(f"Port {DEFAULT_PORT}: activ")
    else:
        _info(f"Port {DEFAULT_PORT}: liber (serverul nu rulează)")

    if env["api_healthy"]:
        _ok("API /api/v1/health: OK")
        # Test a few more endpoints
        for ep in ["/api/v1/context?mode=compact", "/api/dashboard"]:
            try:
                url = f"http://localhost:{DEFAULT_PORT}{ep}"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    _ok(f"Endpoint {ep.split('?')[0]}: OK")
            except Exception:
                _warn(f"Endpoint {ep.split('?')[0]}: FAIL")
    else:
        if env["port_in_use"]:
            _err("Portul activ dar API nu răspunde")
            issues.append("Port activ dar API nu răspunde")
    print()

    # Section 4: Adapters & Clients
    print("  \033[1m[4/6] Adaptoare & Clienți\033[0m")
    adapters = [
        (GEMINI_ADAPTER, "Gemini adapter (sursă)"),
        (CODEX_ADAPTER, "Codex adapter (sursă)"),
        (UNIVERSAL_CLIENT, "Universal client (sursă)"),
        (GEMINI_DIR / "gemini_cli_adapter.py", "Gemini adapter (instalat)"),
        (CODEX_DIR / "codex_cli_adapter.py", "Codex adapter (instalat)"),
    ]
    for path, name in adapters:
        if path.exists():
            _ok(name)
        else:
            _info(f"{name}: neinstalat")
    print()

    # Section 5: Agent Detection
    print("  \033[1m[5/6] Detectare agenți\033[0m")
    for name, avail, dir_exists in [
        ("Claude Code", env["claude_available"], env["claude_dir"]),
        ("Gemini CLI", env["gemini_available"], env["gemini_dir"]),
        ("Codex CLI", env["codex_available"], env["codex_dir"]),
    ]:
        if avail:
            _ok(f"{name}: disponibil")
        elif dir_exists:
            _info(f"{name}: director există, CLI nu e în PATH")
        else:
            _info(f"{name}: nedetectat")
    print()

    # Section 6: Configuration
    print("  \033[1m[6/6] Configurare\033[0m")
    # Check Claude MCP config
    if env["claude_mcp_json"]:
        try:
            mcp = json.loads((CLAUDE_DIR / ".mcp.json").read_text())
            if "universal-memory" in mcp.get("mcpServers", {}):
                _ok("Claude MCP: universal-memory configurat")
            else:
                _info("Claude MCP: .mcp.json fără universal-memory")
        except Exception:
            _err("Claude MCP: .mcp.json invalid")
            issues.append(".mcp.json invalid")

    # Check requirements
    try:
        from importlib.metadata import version as pkg_version
        flask_ver = pkg_version("flask")
        _ok(f"Flask: instalat (v{flask_ver})")
    except Exception:
        _err("Flask: LIPSĂ — pip install flask")
        issues.append("Flask neinstalat")

    # Web UI
    web_dir = PROJECT_ROOT / "web"
    if (web_dir / "index.html").exists():
        _ok("Web UI: present")
    else:
        _warn("Web UI: lipsă")

    # Summary
    print()
    if issues:
        _warn(f"Probleme găsite: {len(issues)}")
        for issue in issues:
            print(f"    • {issue}")
    else:
        _ok("Nicio problemă detectată!")
    print()


# === MAIN ===

def main():
    parser = argparse.ArgumentParser(
        prog="ean-memory",
        description="Universal Agent Memory — Installer & Runtime CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  install claude|gemini|codex  Install agent integration
  uninstall claude|gemini|codex  Remove agent integration
  start [--port PORT]          Start memory server
  stop                         Stop memory server
  status                       Show runtime status
  test                         Quick validation
  doctor                       Detailed diagnostics
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    # install
    install_p = subparsers.add_parser("install", help="Install agent integration")
    install_p.add_argument("target", choices=["claude", "gemini", "codex", "kimi"],
                           help="Agent to install")

    # uninstall
    uninstall_p = subparsers.add_parser("uninstall", help="Remove agent integration")
    uninstall_p.add_argument("target", choices=["claude", "gemini", "codex", "kimi"],
                             help="Agent to uninstall")

    # start
    start_p = subparsers.add_parser("start", help="Start memory server")
    start_p.add_argument("--port", type=int, default=DEFAULT_PORT,
                         help=f"Port (default: {DEFAULT_PORT})")
    start_p.add_argument("--host", default=DEFAULT_HOST,
                         help=f"Host (default: {DEFAULT_HOST})")

    # stop
    subparsers.add_parser("stop", help="Stop memory server")

    # status
    subparsers.add_parser("status", help="Show runtime status")

    # test
    subparsers.add_parser("test", help="Quick validation")

    # doctor
    subparsers.add_parser("doctor", help="Detailed diagnostics")

    args = parser.parse_args()

    commands = {
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "test": cmd_test,
        "doctor": cmd_doctor,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
