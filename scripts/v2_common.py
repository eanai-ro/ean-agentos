#!/usr/bin/env python3
"""
V2 Common - Utilități partajate pentru scripturile V2.

Centralizează: conexiune DB, session ID, project path, formatare output.
"""

import os
import re
import json
import hashlib
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any


# === CENTRALIZED LOGGING ===
def get_logger(name: str) -> logging.Logger:
    """Get a logger with file + stderr output. Usage: logger = get_logger(__name__)"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG if os.environ.get("EAN_DEBUG") else logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
        # Stderr handler (always)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        # File handler (if writable)
        try:
            log_dir = Path(__file__).parent.parent
            fh = logging.FileHandler(str(log_dir / "ean-agentos.log"), encoding="utf-8")
            fh.setFormatter(fmt)
            fh.setLevel(logging.WARNING)  # Only warnings+ to file
            logger.addHandler(fh)
        except (OSError, PermissionError):
            pass
    return logger


# === PATHS ===
# DB-ul se rezolvă relativ la locația scriptului: scripts/ → parent = project root
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent

# Legacy compatibility path
_LEGACY_DB = Path.home() / ".claude" / "memory" / "global.db"


def resolve_db_path() -> Path:
    """Rezolvă path-ul DB universal. Ordinea:
    1. MEMORY_DB_PATH env var (override explicit)
    2. <project_root>/global.db (canonical V2)
    3. ~/.ean-agentos/global.db (legacy fallback)
    """
    env_db = os.environ.get("MEMORY_DB_PATH")
    if env_db:
        return Path(env_db)

    project_db = PROJECT_ROOT / "global.db"
    if project_db.exists():
        return project_db

    if _LEGACY_DB.exists():
        return _LEGACY_DB

    # Default: project-local (chiar dacă nu există încă — init_db o va crea)
    return project_db


GLOBAL_DB = resolve_db_path()

SESSION_FILE = PROJECT_ROOT / ".current_session"
MODEL_FILE = PROJECT_ROOT / ".current_model"
INTENT_FILE = PROJECT_ROOT / ".current_intent"
BRANCH_FILE = PROJECT_ROOT / ".current_branch"
SNAPSHOT_FILE = PROJECT_ROOT / ".context_snapshot.json"


def get_db() -> sqlite3.Connection:
    """Conexiune la baza de date cu WAL mode și row_factory."""
    if not GLOBAL_DB.exists():
        print(f"❌ Baza de date nu există: {GLOBAL_DB}")
        raise SystemExit(1)
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_current_session_id() -> Optional[str]:
    """Citește ID-ul sesiunii curente din .current_session."""
    if SESSION_FILE.exists():
        content = SESSION_FILE.read_text().strip()
        if content:
            return content
    return None


def get_current_project_path() -> str:
    """Returnează project_path din CWD."""
    return str(Path.cwd())


def format_timestamp(ts: Optional[str]) -> str:
    """Convertește ISO timestamp în format human readable."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return ts[:16] if len(ts) >= 16 else ts


def truncate(text: Optional[str], max_len: int = 60) -> str:
    """Trunchiază text la max_len caractere."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def format_table(rows: List[Dict[str, Any]], columns: List[tuple]) -> str:
    """
    Formatează rânduri ca tabel text aliniat.

    columns: lista de (header, key, width)
    Exemplu: [("ID", "id", 5), ("Titlu", "title", 40)]
    """
    if not rows:
        return "  (niciun rezultat)"

    # Header
    header_parts = []
    for header, _, width in columns:
        header_parts.append(f"{header:<{width}}" if width > 0 else header)
    header_line = "  ".join(header_parts)

    # Separator
    sep_parts = []
    for _, _, width in columns:
        sep_parts.append("-" * max(width, len(header_parts[0])))
    sep_line = "  ".join(sep_parts)

    # Rows
    lines = [header_line, sep_line]
    for row in rows:
        row_parts = []
        for _, key, width in columns:
            val = str(row.get(key, "") or "")
            if len(val) > width and width > 3:
                val = val[:width - 3] + "..."
            row_parts.append(f"{val:<{width}}")
        lines.append("  ".join(row_parts))

    return "\n".join(lines)


def get_current_model() -> tuple:
    """Returnează (model_id, provider) din .current_model sau fallback."""
    if MODEL_FILE.exists():
        try:
            data = json.loads(MODEL_FILE.read_text())
            return data.get("model_id", "unknown"), data.get("provider", "unknown")
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback: variabilă de mediu
    model = os.environ.get("CLAUDE_MODEL", "unknown")
    provider = os.environ.get("CLAUDE_PROVIDER", "anthropic")
    return model, provider


def set_current_model(model_id: str, provider: str = "anthropic", agent_name: Optional[str] = None):
    """Setează modelul curent în .current_model."""
    data = {
        "model_id": model_id,
        "provider": provider,
        "set_at": datetime.now().isoformat(),
    }
    if agent_name:
        data["agent_name"] = agent_name
    MODEL_FILE.write_text(json.dumps(data, indent=2))


def clear_current_model():
    """Șterge .current_model."""
    if MODEL_FILE.exists():
        MODEL_FILE.unlink()


VALID_INTENTS = ("debugging", "feature", "deploy", "docs", "refactor", "review", "explore")

# Intent → secțiuni prioritare
INTENT_PRIORITIES = {
    "debugging": ["resolutions", "tasks_blocked", "facts_gotcha"],
    "feature": ["goals", "decisions", "tasks"],
    "deploy": ["facts_convention", "resolutions", "decisions"],
    "docs": ["profile", "decisions", "facts"],
    "refactor": ["decisions", "facts_convention", "goals"],
    "review": ["decisions", "facts", "resolutions"],
    "explore": ["profile", "facts", "goals"],
}


def get_current_intent() -> Optional[str]:
    """Citește intenția sesiunii curente din .current_intent."""
    if INTENT_FILE.exists():
        try:
            content = INTENT_FILE.read_text().strip()
            if content:
                data = json.loads(content)
                return data.get("intent")
        except (json.JSONDecodeError, OSError):
            pass
    return None


def set_current_intent(intent: str):
    """Setează intenția sesiunii curente."""
    data = {
        "intent": intent,
        "set_at": datetime.now().isoformat(),
    }
    INTENT_FILE.write_text(json.dumps(data, indent=2))


def clear_current_intent():
    """Șterge .current_intent."""
    if INTENT_FILE.exists():
        INTENT_FILE.unlink()


def invalidate_snapshot():
    """Invalidează snapshot-ul cached (la schimbare intent/model)."""
    if SNAPSHOT_FILE.exists():
        SNAPSHOT_FILE.unlink()


def get_current_branch() -> str:
    """Citește branch-ul curent din .current_branch. Default: 'main'."""
    if BRANCH_FILE.exists():
        try:
            content = BRANCH_FILE.read_text().strip()
            if content:
                data = json.loads(content)
                return data.get("branch", "main")
        except (json.JSONDecodeError, OSError):
            pass
    return "main"


def set_current_branch(branch: str):
    """Setează branch-ul curent în .current_branch."""
    data = {
        "branch": branch,
        "set_at": datetime.now().isoformat(),
    }
    BRANCH_FILE.write_text(json.dumps(data, indent=2))


def clear_current_branch():
    """Resetează la main (șterge .current_branch)."""
    if BRANCH_FILE.exists():
        BRANCH_FILE.unlink()


# Entity tables care suportă branch
BRANCH_ENTITY_TABLES = ("decisions", "goals", "tasks", "learned_facts", "error_resolutions")


def error_fingerprint(error_type: str, error_message: str, file_path: Optional[str] = None) -> str:
    """Generează fingerprint normalizat pentru deduplicare erori."""
    normalized = re.sub(r'line \d+', 'line N', error_message)
    normalized = re.sub(r'/[^\s]+/', '/.../', normalized)
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', normalized)
    normalized = re.sub(r'\d{2}:\d{2}:\d{2}', 'TIME', normalized)
    normalized = normalized[:200].strip().lower()

    key = f"{error_type}:{normalized}"
    if file_path:
        ext = Path(file_path).suffix
        key += f":{ext}"

    return hashlib.md5(key.encode()).hexdigest()[:16]


# Constante pentru validare
VALID_DECISION_CATEGORIES = ("technical", "architectural", "tooling", "convention", "process")
VALID_DECISION_STATUSES = ("active", "superseded", "reconsidered", "archived")
VALID_CONFIDENCE_LEVELS = ("confirmed", "high", "medium", "low")
VALID_PRIORITIES = ("critical", "high", "medium", "low")
VALID_GOAL_STATUSES = ("active", "completed", "paused", "abandoned")
VALID_TASK_STATUSES = ("todo", "in_progress", "done", "blocked", "cancelled")
VALID_FACT_TYPES = ("technical", "preference", "convention", "environment", "gotcha")
VALID_RESOLUTION_TYPES = ("fix", "workaround", "config_change", "dependency", "rollback")
VALID_ACTION_TYPES = ("session_start", "decision", "fix", "code_gen", "review", "query", "learn", "resolve", "checkpoint", "goal", "task", "profile")

# Agent Event Stream — taxonomie
VALID_AGENT_EVENT_TYPES = (
    "agent_started", "agent_finished", "agent_error",
    "context_requested", "context_received",
    "decision_created", "fact_created", "goal_created",
    "task_created", "task_updated", "resolution_created",
    "branch_created", "branch_switched", "branch_compared", "branch_merged", "branch_deleted",
    "checkpoint_created", "checkpoint_restored",
    "api_call", "ui_action",
    "learning_promoted",
    "orch_project_created", "orch_task_claimed", "orch_task_completed",
    "orch_deliberation_started", "orch_round_advanced",
    "orch_vote_cast", "orch_synthesis_completed",
)

VALID_EVENT_PHASES = ("start", "progress", "end", "error")

# === ORCHESTRATION CONSTANTS ===
VALID_CLI_NAMES = ("claude-code", "gemini-cli", "codex-cli", "kimi-cli")
ORCH_TASK_STATUSES = ("pending", "assigned", "in_progress", "done", "failed", "blocked")
ORCH_PROJECT_STATUSES = ("active", "paused", "completed", "failed")
ORCH_AGENT_STATUSES = ("online", "busy", "offline")
DELIBERATION_PHASES = {
    "quick": {"rounds": 2, "phases": ["proposal", "synthesis"]},
    "deep": {"rounds": 4, "phases": ["proposal", "analysis", "refinement", "synthesis"]},
    "expert": {"rounds": 6, "phases": ["proposal", "analysis", "critique", "refinement", "vote", "synthesis"]},
}
ORCH_MESSAGE_TYPES = ("info", "question", "answer", "review", "correction", "handoff")

# Tables that support cross-agent learning (is_global + promoted_from_agent)
CROSS_AGENT_TABLES = ("decisions", "learned_facts", "error_resolutions")

# Experience link types for the experience graph
VALID_LINK_TYPES = (
    "error_caused_by",       # error_resolutions → errors_solutions (what error caused this)
    "resolved_by",           # errors_solutions → error_resolutions (what resolution fixed this)
    "pattern_of",            # error_patterns → errors_solutions (pattern groups errors)
    "decision_led_to",       # decisions → errors_solutions (decision caused error)
    "decision_resolved_by",  # decisions → error_resolutions (decision informed fix)
    "fact_from_resolution",  # learned_facts → error_resolutions (learning from fix)
    "attempted_with",        # error_resolutions → error_resolutions (alternative attempts)
)

# Default agent weight for unknown agents
DEFAULT_AGENT_WEIGHT = 1.0


def log_agent_event(
    event_type: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    detail: Optional[str] = None,
    event_phase: str = "end",
    status: str = "completed",
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    branch_name: Optional[str] = None,
    cli_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    related_table: Optional[str] = None,
    related_id: Optional[int] = None,
    parent_event_id: Optional[int] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    duration_ms: Optional[int] = None,
    success_flag: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Logează un eveniment agent în agent_events. Returnează ID-ul sau None.

    Completează automat project_path, session_id, branch_name, model/provider
    din state files dacă nu sunt furnizate explicit.
    """
    try:
        # Auto-fill from state files
        if not project_path:
            project_path = get_current_project_path()
        if not session_id:
            session_id = get_current_session_id()
        if not branch_name:
            branch_name = get_current_branch()
        if not model_name or not provider:
            m_id, m_prov = get_current_model()
            if not model_name and m_id != "unknown":
                model_name = m_id
            if not provider and m_prov != "unknown":
                provider = m_prov

        now = datetime.now().isoformat()
        if not finished_at and event_phase == "end":
            finished_at = now

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_events
            (project_path, session_id, branch_name, cli_name, agent_name,
             provider, model_name, event_type, event_phase, title, summary,
             detail, status, related_table, related_id, parent_event_id,
             started_at, finished_at, duration_ms, success_flag, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_path, session_id, branch_name, cli_name, agent_name,
            provider, model_name, event_type, event_phase,
            title or event_type, summary, detail, status,
            related_table, related_id, parent_event_id,
            started_at, finished_at, duration_ms, success_flag,
            json.dumps(metadata) if metadata else None,
        ))
        conn.commit()
        event_id = cursor.lastrowid
        conn.close()
        return event_id
    except Exception:
        return None


def log_agent_activity(
    action_type: str,
    action_summary: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    tokens_used: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    agent_name: Optional[str] = None,
    model_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> Optional[int]:
    """Logează o activitate agent în agent_activity_log. Returnează ID-ul sau None."""
    try:
        if not model_id:
            model_id, provider_fallback = get_current_model()
            if model_id == "unknown":
                model_id = None
            if not provider:
                provider = provider_fallback if provider_fallback != "unknown" else None

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_activity_log
            (session_id, project_path, agent_name, model_id, provider,
             action_type, action_summary, entity_type, entity_id,
             success, error_message, duration_ms, tokens_used, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            get_current_session_id(),
            get_current_project_path(),
            agent_name,
            model_id,
            provider,
            action_type,
            action_summary,
            entity_type,
            entity_id,
            1 if success else 0,
            error_message,
            duration_ms,
            tokens_used,
            json.dumps(metadata) if metadata else None,
        ))
        conn.commit()
        activity_id = cursor.lastrowid
        conn.close()
        return activity_id
    except Exception:
        # Nu lăsăm logging-ul să spargă operația principală
        return None
