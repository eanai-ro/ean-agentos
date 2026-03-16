#!/usr/bin/env python3
"""
Memory Daemon pentru Claude Code - Salvează TOTUL în memorie permanentă.

Acest script este apelat de hooks-urile Claude Code pentru:
- SessionStart: Începe o sesiune nouă
- Stop: Finalizează sesiunea
- PreToolUse: Backup fișiere înainte de modificări
- PostToolUse: Salvează rezultatul tuturor acțiunilor
- UserPromptSubmit: Salvează toate prompt-urile utilizatorului

Usage:
    python3 memory_daemon.py <event_type>

Event types: session_start, session_end, pre_tool, post_tool, user_prompt
"""

import sys
import os
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import uuid
import time


# === CONFIGURAȚIE ===
# MEMORY_DIR is configurable via env var. Hooks set this to the project root.
# Default: project root (ean-cc-mem-kit/).
_DAEMON_PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = Path(os.environ.get("MEMORY_DIR", str(_DAEMON_PROJECT_ROOT)))
GLOBAL_DB = MEMORY_DIR / "global.db"
SESSIONS_DIR = MEMORY_DIR / "sessions"
FILE_VERSIONS_DIR = MEMORY_DIR / "file_versions"
SCRIPTS_DIR = MEMORY_DIR / "scripts"

# Sesiune curentă (persistă între apeluri via fișier)
SESSION_FILE = MEMORY_DIR / ".current_session"

# === CONTEXT MONITOR CONFIG (FAZA 1 - SAFE MODE) ===
MONITOR_STATE_FILE = MEMORY_DIR / ".context_monitor_state.json"
MONITOR_RUN_MIN_INTERVAL = 30       # Minimum 30 secunde între rulări
MONITOR_CHECKPOINT_MIN_INTERVAL = 600  # Minimum 10 minute între checkpoint-uri
MAX_CONTEXT_TOKENS = int(os.environ.get('CLAUDE_MAX_TOKENS', 200000))

# === TELEGRAM ALERT CONFIG ===
TG_ALERT_STATE_FILE = MEMORY_DIR / ".tg_alert_state.json"
TG_ALERT_DEBOUNCE_SECONDS = 300  # 5 minute între alerte

# Project-scoped memory
PROJECT_MEMORY_DIR = ".claude-memory"
PROJECT_DB_NAME = "project.db"


def get_project_db_path() -> Optional[Path]:
    """Găsește DB-ul specific proiectului dacă există."""
    cwd = Path.cwd()
    # Caută .claude-memory în directorul curent sau părinți (până la 5 nivele)
    for _ in range(5):
        project_db = cwd / PROJECT_MEMORY_DIR / PROJECT_DB_NAME
        if project_db.exists():
            return project_db
        if cwd.parent == cwd:  # Am ajuns la root
            break
        cwd = cwd.parent
    return None


def get_active_db_path() -> Path:
    """Returnează calea DB-ului activ (project sau global)."""
    project_db = get_project_db_path()
    return project_db if project_db else GLOBAL_DB


def is_project_scoped() -> bool:
    """Verifică dacă folosim memorie per proiect."""
    return get_project_db_path() is not None


# === SCRUBBING CONFIGURATION ===
import re
from typing import Tuple

SCRUB_ENABLED = os.environ.get("MEMORY_SCRUB_DISABLE", "0") != "1"
SCRUB_DEBUG = os.environ.get("MEMORY_SCRUB_DEBUG", "0") == "1"
SCRUB_WHITELIST_FILE = MEMORY_DIR / "scrub_whitelist.txt"

# Pattern-uri pentru detectare secrete
SCRUB_PATTERNS = [
    # Authorization headers
    (r'Authorization:\s*Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', 'bearer_token'),
    (r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', 'bearer_token'),

    # API keys
    (r'sk-[A-Za-z0-9]{20,}', 'openai_key'),
    (r'xox[baprs]-[A-Za-z0-9-]{10,}', 'slack_token'),
    (r'AIza[0-9A-Za-z\-_]{20,}', 'google_key'),
    (r'ghp_[A-Za-z0-9]{30,}', 'github_token'),
    (r'github_pat_[A-Za-z0-9_]+', 'github_pat'),
    (r'AKIA[0-9A-Z]{16}', 'aws_key'),

    # JSON tokens
    (r'"(api_key|token|access_token|refresh_token)"\s*:\s*"[^"]{10,}"', 'json_token'),

    # PEM blocks
    (r'-----BEGIN (?:RSA |EC |OPENSSH |)(?:PRIVATE |)KEY-----.*?-----END (?:RSA |EC |OPENSSH |)(?:PRIVATE |)KEY-----', 'pem_key'),
]

def load_whitelist():
    """Încarcă pattern-uri whitelisted."""
    if not SCRUB_WHITELIST_FILE.exists():
        return []
    try:
        return [line.strip() for line in SCRUB_WHITELIST_FILE.read_text().splitlines() if line.strip()]
    except:
        return []

# === AUDIT LOGGING & DETECTION EVENTS ===

def audit_log_write(action_type: str, table_name: str, row_id: str = None,
                    fingerprint: str = None, severity: str = "INFO",
                    change_summary: str = "", actor: str = "system"):
    """Scrie în audit_log pentru trasabilitate."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_log
            (ts, action_type, table_name, row_id, fingerprint, severity, change_summary, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            action_type,
            table_name,
            row_id,
            fingerprint,
            severity,
            change_summary,
            actor
        ))

        conn.commit()
        conn.close()
    except Exception as e:
        log_error(f"audit_log_write failed: {e}")

def get_rule_weight(pattern_id: str) -> int:
    """Obține weight pentru un pattern_id din detection_rules."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT weight FROM detection_rules WHERE pattern_id = ?", (pattern_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0]
        else:
            return 50  # Default weight dacă pattern_id nu există
    except:
        return 50

def calculate_score(pattern_id: str, confidence: str) -> int:
    """Calculează score bazat pe weight + confidence."""
    weight = get_rule_weight(pattern_id)

    # Ajustare bazată pe confidence
    if confidence == "HIGH":
        multiplier = 1.0
    elif confidence == "MED":
        multiplier = 0.7
    elif confidence == "LOW":
        multiplier = 0.4
    else:
        multiplier = 0.5

    return int(weight * multiplier)

def detection_event_write(source: str, pattern_id: str, category: str,
                          score: int, confidence: str, table_name: str = None,
                          row_id: str = None, excerpt: str = "", decision: str = "scrub"):
    """Scrie în detection_events pentru FP scoring."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Truncate excerpt la max 80 chars (safe snippet)
        excerpt_safe = (excerpt or "")[:80]

        cursor.execute("""
            INSERT INTO detection_events
            (ts, source, pattern_id, category, score, confidence, table_name, row_id, excerpt, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            source,
            pattern_id,
            category,
            score,
            confidence,
            table_name,
            row_id,
            excerpt_safe,
            decision
        ))

        conn.commit()
        conn.close()
    except Exception as e:
        log_error(f"detection_event_write failed: {e}")

def scrub_text(text: str) -> Tuple[str, Dict]:
    """Mascare secrete în text."""
    if not SCRUB_ENABLED or not text:
        return text, {}

    whitelist = load_whitelist()
    scrubbed_count = {}
    result = text

    for pattern, secret_type in SCRUB_PATTERNS:
        matches = re.finditer(pattern, result, re.DOTALL | re.IGNORECASE)
        for match in matches:
            matched_text = match.group(0)

            # Check whitelist
            if any(re.search(wl, matched_text) for wl in whitelist):
                continue

            # Mascare
            if secret_type == 'pem_key':
                replacement = '****REDACTED_PEM****'
            elif len(matched_text) > 12:
                # Păstrează primele 4 + ultimele 4
                replacement = f"{matched_text[:4]}****REDACTED****{matched_text[-4:]}"
            else:
                replacement = '****REDACTED****'

            result = result.replace(matched_text, replacement)
            scrubbed_count[secret_type] = scrubbed_count.get(secret_type, 0) + 1

            # === DETECTION EVENT LOGGING ===
            # Log detection pentru FP scoring
            pattern_id = secret_type  # ex: bearer_token, openai_key
            confidence = "HIGH" if secret_type in ["pem_key", "bearer_token", "jwt_token"] else "MED"
            score = calculate_score(pattern_id, confidence)
            excerpt_safe = replacement[:80]  # Safe snippet (deja masked)

            detection_event_write(
                source="scrub",
                pattern_id=pattern_id,
                category=secret_type,
                score=score,
                confidence=confidence,
                table_name="messages",  # Default, va fi override în handlers
                row_id=None,
                excerpt=excerpt_safe,
                decision="scrub"
            )

    if SCRUB_DEBUG and scrubbed_count:
        log_debug(f"Scrubbed: {scrubbed_count}")

    # === AUDIT LOG (rezumat) ===
    if scrubbed_count:
        summary = ", ".join([f"{k}: {v}" for k, v in scrubbed_count.items()])
        audit_log_write(
            action_type="scrub",
            table_name="messages",  # Default
            severity="INFO",
            change_summary=f"Scrubbed {sum(scrubbed_count.values())} secrets: {summary}",
            actor="scrubbing"
        )

    return result, scrubbed_count

def scrub_payload(obj: Any) -> Tuple[Any, Dict]:
    """Recursiv scrub pe dict/list/str."""
    if not SCRUB_ENABLED:
        return obj, {}

    total_scrubbed = {}

    if isinstance(obj, str):
        result, counts = scrub_text(obj)
        for k, v in counts.items():
            total_scrubbed[k] = total_scrubbed.get(k, 0) + v
        return result, total_scrubbed

    elif isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            scrubbed_value, counts = scrub_payload(value)
            result[key] = scrubbed_value
            for k, v in counts.items():
                total_scrubbed[k] = total_scrubbed.get(k, 0) + v
        return result, total_scrubbed

    elif isinstance(obj, list):
        result = []
        for item in obj:
            scrubbed_item, counts = scrub_payload(item)
            result.append(scrubbed_item)
            for k, v in counts.items():
                total_scrubbed[k] = total_scrubbed.get(k, 0) + v
        return result, total_scrubbed

    else:
        return obj, {}


# === QUARANTINE GUARD ===
GUARD_ENABLED = os.environ.get("MEMORY_GUARD_ENABLE", "1") == "1"
GUARD_BLOCK_LEVEL = os.environ.get("MEMORY_GUARD_BLOCK_LEVEL", "HIGH")  # CRITICAL/HIGH/MEDIUM
QUARANTINE_DIR = MEMORY_DIR / "quarantine"
GUARD_STATE_FILE = MEMORY_DIR / ".guard_state.json"

# Pattern-uri mai agresive decât scrub (detectare după scrub)
GUARD_PATTERNS = [
    (r'-----BEGIN .*PRIVATE KEY-----', 'CRITICAL', 'pem_private'),
    (r'Authorization:\s*Bearer', 'CRITICAL', 'bearer_auth'),
    (r'(access_token|refresh_token|id_token)["\s:]+[A-Za-z0-9\-_\.]{20,}', 'CRITICAL', 'jwt_token'),
    (r'sk-[A-Za-z0-9]{20,}', 'HIGH', 'openai_key'),
    (r'ghp_[A-Za-z0-9]{30,}', 'HIGH', 'github_token'),
    (r'AKIA[0-9A-Z]{16}', 'HIGH', 'aws_access_key'),
    (r'[A-Za-z0-9\-_]{45,}', 'MEDIUM', 'generic_token'),  # Heuristic
]

# Excluderi (nu bloca)
GUARD_EXCLUDES = [
    r'toolu_[A-Za-z0-9]+',  # Claude tool IDs
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',  # UUIDs
    r'REDACTED',  # Already scrubbed
]

def guard_detect(text_or_payload: Any) -> Dict:
    """Detectează secrete în payload după scrubbing."""
    if not GUARD_ENABLED:
        return {"hits": [], "severity": None}

    # Convertește la text pentru scanning
    if isinstance(text_or_payload, dict):
        text = json.dumps(text_or_payload)
    elif isinstance(text_or_payload, str):
        text = text_or_payload
    else:
        text = str(text_or_payload)

    hits = []
    max_severity = None
    severity_order = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}

    for pattern, severity, secret_type in GUARD_PATTERNS:
        matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            matched_text = match.group(0)

            # Check excludes
            if any(re.search(exc, matched_text) for exc in GUARD_EXCLUDES):
                continue

            hits.append({"type": secret_type, "severity": severity, "field": "content"})

            if max_severity is None or severity_order[severity] > severity_order.get(max_severity, 0):
                max_severity = severity

    return {"hits": hits, "severity": max_severity}

def should_block(severity: str) -> bool:
    """Determină dacă severity declanșează blocare."""
    severity_order = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}
    block_order = severity_order.get(GUARD_BLOCK_LEVEL, 2)
    return severity_order.get(severity, 0) >= block_order

def quarantine_write(event_type: str, scrubbed_payload: Dict, guard_meta: Dict):
    """Scrie în quarantine în loc de DB."""
    QUARANTINE_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    qfile = QUARANTINE_DIR / f"q_{timestamp}_{event_type}.json"

    entry = {
        "ts": datetime.now().isoformat(),
        "event_type": event_type,
        "session_id": get_current_session_id(),
        "project": get_project_path(),
        "guard": guard_meta,
        "payload": {"scrubbed": True, "data": scrubbed_payload}
    }

    qfile.write_text(json.dumps(entry, indent=2))

    # Update guard state
    update_guard_state(guard_meta["severity"])

    # === AUDIT LOG ===
    severity_map = {"CRITICAL": "CRITICAL", "HIGH": "HIGH", "MEDIUM": "WARN"}
    audit_severity = severity_map.get(guard_meta.get("severity"), "WARN")

    audit_log_write(
        action_type="quarantine",
        table_name="quarantine",
        row_id=str(qfile.name),
        severity=audit_severity,
        change_summary=f"Blocked {event_type}: {len(guard_meta.get('hits', []))} hits detected",
        actor="guard"
    )

    # === DETECTION EVENTS ===
    # Log fiecare hit ca detection event
    for hit in guard_meta.get("hits", []):
        pattern_id = hit.get("type", "unknown")
        confidence = "HIGH" if guard_meta.get("severity") == "CRITICAL" else "MED"
        score = calculate_score(pattern_id, confidence)

        detection_event_write(
            source="guard",
            pattern_id=pattern_id,
            category=hit.get("type", "unknown"),
            score=score,
            confidence=confidence,
            table_name=event_type,
            row_id=None,
            excerpt="[QUARANTINED]",
            decision="quarantine"
        )

    log_error(f"🔒 QUARANTINE: {event_type} blocked - {guard_meta}")

def update_guard_state(severity: str):
    """Actualizează counters în guard state."""
    if GUARD_STATE_FILE.exists():
        try:
            state = json.loads(GUARD_STATE_FILE.read_text())
        except:
            state = {}
    else:
        state = {}

    state["total_blocked"] = state.get("total_blocked", 0) + 1
    by_sev = state.get("by_severity", {})
    by_sev[severity] = by_sev.get(severity, 0) + 1
    state["by_severity"] = by_sev
    state["last_block_ts"] = datetime.now().isoformat()

    GUARD_STATE_FILE.write_text(json.dumps(state, indent=2))


# === FUNCȚII UTILITARE ===

def get_db_connection(timeout: int = 30, use_global: bool = False) -> sqlite3.Connection:
    """Obține conexiune la baza de date activă (project sau global) cu WAL mode și timeout."""
    db_path = GLOBAL_DB if use_global else get_active_db_path()
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    # Activează WAL mode pentru concurență mai bună
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # 30 secunde timeout
    conn.execute("PRAGMA synchronous=NORMAL")  # Performanță mai bună cu WAL
    return conn


def db_execute_with_retry(func, max_retries: int = 3, delay: float = 0.5):
    """Execută o funcție DB cu retry în caz de lock."""
    import time
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1))  # Backoff exponențial
                    continue
            raise
    if last_error:
        raise last_error


def get_current_session_id() -> Optional[str]:
    """Citește ID-ul sesiunii curente."""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return None


def set_current_session_id(session_id: str):
    """Salvează ID-ul sesiunii curente."""
    SESSION_FILE.write_text(session_id)


def clear_current_session():
    """Șterge sesiunea curentă."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def generate_session_id() -> str:
    """Generează un ID unic pentru sesiune."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]
    return f"session_{timestamp}_{unique}"


def get_project_path() -> str:
    """Obține calea proiectului curent."""
    return os.getcwd()


def hash_content(content: str) -> str:
    """Calculează hash SHA256 pentru conținut."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def find_session_transcript(session_id: str) -> Optional[Path]:
    """Găsește fișierul .jsonl pentru sesiunea curentă."""
    projects_dir = Path.home() / ".claude" / "projects"

    # Strategie 1: Căută direct după UUID-ul sesiunii (nume fișier = session_id.jsonl)
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            # Încearcă potrivire exactă cu session_id
            exact_match = project_dir / f"{session_id}.jsonl"
            if exact_match.exists():
                return exact_match

    # Strategie 2: Caută în fișiere după sessionId în conținut
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            for jsonl_file in project_dir.glob("*.jsonl"):
                try:
                    with open(jsonl_file, 'r') as f:
                        # Verifică primele 10 linii pentru sessionId
                        for i, line in enumerate(f):
                            if i > 10:
                                break
                            if line.strip():
                                data = json.loads(line)
                                if data.get('sessionId') == session_id:
                                    return jsonl_file
                except:
                    continue

    # Strategie 3: Fallback - cel mai recent fișier din proiectul curent
    cwd = os.getcwd()
    project_slug = cwd.replace('/', '-').lstrip('-')
    project_dir = projects_dir / project_slug

    if project_dir.exists():
        jsonl_files = list(project_dir.glob("*.jsonl"))
        if jsonl_files:
            return max(jsonl_files, key=lambda f: f.stat().st_mtime)

    # Strategie 4: Cel mai recent fișier din orice proiect
    all_jsonl = list(projects_dir.glob("*/*.jsonl"))
    if all_jsonl:
        return max(all_jsonl, key=lambda f: f.stat().st_mtime)

    return None


def extract_assistant_responses_from_transcript(transcript_path: Path, session_id: str) -> list:
    """Extrage toate răspunsurile asistentului din transcript."""
    responses = []

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)

                    # Verifică dacă e mesaj de tip assistant
                    if data.get('type') == 'assistant':
                        message = data.get('message', {})
                        content_list = message.get('content', [])
                        timestamp = data.get('timestamp', '')
                        msg_uuid = data.get('uuid', '')

                        # Extrage textul din content
                        text_parts = []
                        for item in content_list:
                            if item.get('type') == 'text':
                                text_parts.append(item.get('text', ''))

                        if text_parts:
                            responses.append({
                                'uuid': msg_uuid,
                                'timestamp': timestamp,
                                'text': '\n'.join(text_parts)
                            })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log_error(f"Eroare citire transcript: {e}")

    return responses


def save_assistant_responses_to_db(responses: list, session_id: str):
    """Salvează răspunsurile asistentului în baza de date (optimizat pentru viteză)."""
    if not responses:
        return 0

    # Limitează la ultimele 50 răspunsuri pentru performanță
    responses = responses[-50:]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Obține toate uuid-urile deja salvate într-o singură interogare
    cursor.execute("""
        SELECT message_type FROM messages
        WHERE session_id = ? AND role = 'assistant'
    """, (session_id,))
    existing_uuids = {row[0] for row in cursor.fetchall()}

    # Filtrează răspunsurile noi
    project_path = get_project_path()
    new_responses = [
        (session_id, 'assistant', resp['text'], resp.get('uuid', 'response'),
         project_path, resp.get('timestamp', datetime.now().isoformat()))
        for resp in responses
        if resp.get('uuid', '') not in existing_uuids
    ]

    # Insert batch
    if new_responses:
        cursor.executemany("""
            INSERT INTO messages
            (session_id, role, content, message_type, project_path, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, new_responses)

    conn.commit()
    conn.close()

    saved_count = len(new_responses)
    log_debug(f"Salvate {saved_count} răspunsuri assistant din transcript")
    return saved_count


def read_stdin_json() -> Optional[Dict]:
    """Citește JSON de la stdin (trimis de hooks)."""
    try:
        if not sys.stdin.isatty():
            data = sys.stdin.read()
            if data.strip():
                return json.loads(data)
    except Exception as e:
        log_error(f"Eroare citire stdin: {e}")
    return None


def save_curated_memory(memory_type: str, content: str, session_id: str, metadata: dict = None):
    """Salvează în tabelul curated_memory."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO curated_memory (type, content, session_id, project_path, metadata)
        VALUES (?, ?, ?, ?, ?)
    """, (
        memory_type,
        content,
        session_id,
        get_project_path(),
        json.dumps(metadata) if metadata else None
    ))

    conn.commit()
    conn.close()


def log_error(message: str):
    """Loghează erori într-un fișier."""
    error_log = MEMORY_DIR / "daemon_errors.log"
    timestamp = datetime.now().isoformat()
    with open(error_log, 'a') as f:
        f.write(f"[{timestamp}] {message}\n")


def log_debug(message: str):
    """Loghează mesaje debug (pentru dezvoltare)."""
    debug_log = MEMORY_DIR / "daemon_debug.log"
    timestamp = datetime.now().isoformat()
    with open(debug_log, 'a') as f:
        f.write(f"[{timestamp}] {message}\n")


# === COMPACT TRACE (DIAGNOSTIC) ===
COMPACT_TRACE_FILE = MEMORY_DIR / "compact_trace.log"

def trace_log(event_type: str, extra_data: Optional[Dict[str, Any]] = None):
    """
    Loghează eveniment în compact_trace.log pentru diagnostic compactare.

    Fiecare entry conține:
    - timestamp
    - event_type (user_prompt, post_tool, session_start, session_end, stop, compact_detected)
    - session_id
    - project_path
    - monitor_state (threshold, context_pct, checkpoint_id)
    - reconciler_stats (total_runs, auto_errors)

    Args:
        event_type: Tipul evenimentului
        extra_data: Date adiționale specifice evenimentului
    """
    try:
        timestamp = datetime.now().isoformat()
        session_id = get_current_session_id() or "unknown"
        project_path = get_project_path()

        # Monitor state
        monitor_state = load_monitor_state()
        monitor_info = {
            "last_threshold": monitor_state.get("last_threshold", "unknown"),
            "last_context_pct": monitor_state.get("last_context_pct", 0),
            "last_checkpoint_id": monitor_state.get("last_checkpoint_id")
        }

        # Reconciler stats (lightweight)
        reconciler_stats = {}
        reconciler_state_file = MEMORY_DIR / ".reconciler_state.json"
        if reconciler_state_file.exists():
            try:
                rs = json.loads(reconciler_state_file.read_text())
                reconciler_stats = {
                    "total_runs": rs.get("total_runs", 0),
                    "total_errors_found": rs.get("total_errors_found", 0)
                }
            except (json.JSONDecodeError, IOError):
                pass

        entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "session_id": session_id[:16] if session_id else "unknown",
            "project_path": project_path.split("/")[-1] if project_path else "unknown",
            "monitor": monitor_info,
            "reconciler": reconciler_stats
        }

        if extra_data:
            entry["extra"] = extra_data

        # Append to trace file
        with open(COMPACT_TRACE_FILE, 'a') as f:
            f.write(json.dumps(entry) + "\n")

    except Exception as e:
        log_error(f"trace_log error: {e}")


# === CONTEXT MONITOR INTEGRATION (FAZA 1 - SAFE MODE) ===

def load_monitor_state() -> Dict[str, Any]:
    """Încarcă starea monitorului din fișier."""
    if MONITOR_STATE_FILE.exists():
        try:
            return json.loads(MONITOR_STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "last_run_at": None,
        "last_checkpoint_at": None,
        "last_checkpoint_id": None,
        "last_threshold": "ok",
        "last_context_pct": 0
    }


def save_monitor_state(state: Dict[str, Any]):
    """Salvează starea monitorului în fișier."""
    try:
        MONITOR_STATE_FILE.write_text(json.dumps(state, indent=2))
    except IOError as e:
        log_error(f"Eroare salvare monitor state: {e}")


def should_run_monitor(state: Dict[str, Any]) -> bool:
    """Verifică dacă monitorul poate rula (throttling)."""
    last_run = state.get("last_run_at")
    if not last_run:
        return True

    try:
        last_run_dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
        elapsed = (datetime.now(last_run_dt.tzinfo) - last_run_dt).total_seconds()
        return elapsed >= MONITOR_RUN_MIN_INTERVAL
    except (ValueError, TypeError):
        return True


def can_create_checkpoint(state: Dict[str, Any]) -> tuple[bool, str]:
    """Verifică dacă poate crea checkpoint (throttling 10 min)."""
    last_cp = state.get("last_checkpoint_at")
    if not last_cp:
        return True, "no_previous"

    try:
        last_cp_dt = datetime.fromisoformat(last_cp.replace('Z', '+00:00'))
        elapsed = (datetime.now(last_cp_dt.tzinfo) - last_cp_dt).total_seconds()
        if elapsed >= MONITOR_CHECKPOINT_MIN_INTERVAL:
            return True, f"elapsed_{int(elapsed)}s"
        return False, f"throttled_wait_{int(MONITOR_CHECKPOINT_MIN_INTERVAL - elapsed)}s"
    except (ValueError, TypeError):
        return True, "parse_error"


def run_context_monitor(
    simulate_percent: Optional[int] = None,
    force: bool = False,
    reason_suffix: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Rulează context_monitor și gestionează acțiunile (SAFE MODE).

    Args:
        simulate_percent: Pentru teste - simulează un procent specific
        force: Ignoră throttling (doar pentru teste)
        reason_suffix: Sufix pentru reason (ex: "_simulated")

    Returns:
        Dict cu rezultatul sau None dacă throttled/eroare
    """
    state = load_monitor_state()

    # Check throttling (skip dacă force)
    if not force and not should_run_monitor(state):
        log_debug("Context monitor throttled (run interval)")
        return None

    # Import context_monitor ca library
    try:
        import sys
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))

        from context_monitor import check_context, create_checkpoint as cm_create_checkpoint

    except ImportError as e:
        log_error(f"Nu pot importa context_monitor: {e}")
        return None

    # Obține status context
    try:
        if simulate_percent is not None:
            status = check_context(context_percentage=simulate_percent)
        else:
            status = check_context(use_estimate=True)
    except Exception as e:
        log_error(f"Eroare check_context: {e}")
        return None

    # Convertește dataclass în dict
    result = {
        "context_percentage": status.context_percentage,
        "tokens_estimated": status.tokens_estimated,
        "threshold": status.threshold,
        "should_warn": status.should_warn,
        "should_checkpoint": status.should_checkpoint,
        "should_preclear": status.should_preclear,
        "actions": status.actions,
        "checkpoint_created": False,
        "throttled": False
    }

    # Update state
    state["last_run_at"] = datetime.utcnow().isoformat() + "Z"
    state["last_threshold"] = status.threshold
    state["last_context_pct"] = status.context_percentage

    # Acțiuni la praguri
    if status.threshold == "warn":
        log_debug(f"CONTEXT WARN: {status.context_percentage}% - aproape de limită")

    elif status.threshold in ("checkpoint", "preclear"):
        can_cp, cp_reason = can_create_checkpoint(state)

        # force ignoră run_interval, dar NU ignoră checkpoint_interval (safety)
        if can_cp:
            # Creează checkpoint
            reason = f"threshold_auto{reason_suffix}" if not simulate_percent else f"threshold_simulated{reason_suffix}"

            try:
                checkpoint_id = cm_create_checkpoint(
                    reason=reason,
                    context_pct=status.context_percentage
                )

                if checkpoint_id:
                    log_debug(f"CHECKPOINT CREAT: {checkpoint_id} ({status.context_percentage}%)")
                    state["last_checkpoint_at"] = datetime.utcnow().isoformat() + "Z"
                    state["last_checkpoint_id"] = checkpoint_id
                    result["checkpoint_created"] = True
                    result["checkpoint_id"] = checkpoint_id

            except Exception as e:
                log_error(f"Eroare creare checkpoint: {e}")
        else:
            log_debug(f"CHECKPOINT THROTTLED: {cp_reason}")
            result["throttled"] = True
            result["throttle_reason"] = cp_reason

    if status.threshold == "preclear":
        log_warning(f"PRECLEAR_HINT: {status.context_percentage}% context - recomand /clear + reseed manual")

    # Salvează starea
    save_monitor_state(state)

    return result


def log_warning(message: str):
    """Loghează warning-uri într-un fișier separat (mai vizibile)."""
    warning_log = MEMORY_DIR / "daemon_warnings.log"
    timestamp = datetime.now().isoformat()
    with open(warning_log, 'a') as f:
        f.write(f"[{timestamp}] WARNING: {message}\n")
    # Scrie și în debug log pentru completitudine
    log_debug(f"WARNING: {message}")


# === TRANSCRIPT RECONCILER INTEGRATION ===

def run_reconciler(session_id: Optional[str] = None, max_lines: int = 100) -> Optional[Dict[str, Any]]:
    """
    Rulează transcript reconciler pentru a captura erori ratate de PostToolUse.

    Args:
        session_id: ID-ul sesiunii (opțional)
        max_lines: Limită linii procesate (pentru performanță)

    Returns:
        Dict cu rezultatul sau None dacă eșuează
    """
    try:
        # Import reconciler
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))

        from transcript_reconciler import reconcile

        result = reconcile(session_id=session_id, max_lines=max_lines)

        if result.get("new_errors", 0) > 0:
            log_debug(f"RECONCILER: {result['new_errors']} erori noi capturate din transcript")

        return result

    except ImportError as e:
        log_debug(f"Reconciler nu e disponibil: {e}")
        return None
    except Exception as e:
        log_error(f"Eroare reconciler: {e}")
        return None


def build_preclear_hint(monitor_result: Optional[Dict[str, Any]], state: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Construiește hint-ul de preclear pentru output JSON.

    Args:
        monitor_result: Rezultatul de la run_context_monitor()
        state: Starea monitorului (opțional, se încarcă dacă lipsește)

    Returns:
        Dict cu hint-ul sau None dacă nu e preclear
    """
    if not monitor_result:
        return None

    if monitor_result.get("threshold") != "preclear":
        return None

    if state is None:
        state = load_monitor_state()

    # Determină checkpoint_id: fie din result (tocmai creat), fie din state (ultimul)
    checkpoint_id = monitor_result.get("checkpoint_id")
    if not checkpoint_id:
        checkpoint_id = state.get("last_checkpoint_id")

    hint = {
        "message": "PRECLEAR: recomand /clear + reseed manual",
        "context_percentage": monitor_result.get("context_percentage"),
        "tokens_estimated": monitor_result.get("tokens_estimated"),
        "checkpoint_id": checkpoint_id,
        "threshold": "preclear"
    }

    # Trimite alertă Telegram (cu debounce)
    send_telegram_preclear_alert(hint)

    return hint


def send_telegram_preclear_alert(hint: Dict[str, Any]) -> bool:
    """
    Trimite alertă Telegram la preclear (cu debounce 5 minute).

    Returns:
        True dacă s-a trimis, False dacă debounce sau eroare
    """
    import subprocess

    try:
        # Verifică debounce
        last_alert_time = 0
        if TG_ALERT_STATE_FILE.exists():
            try:
                state = json.loads(TG_ALERT_STATE_FILE.read_text())
                last_alert_time = state.get("last_preclear_alert", 0)
            except:
                pass

        now = time.time()
        if now - last_alert_time < TG_ALERT_DEBOUNCE_SECONDS:
            log_warning(f"TG alert skipped (debounce): {int(now - last_alert_time)}s since last")
            return False

        # Construiește mesajul
        pct = hint.get("context_percentage", "?")
        tokens = hint.get("tokens_estimated", "?")
        checkpoint = hint.get("checkpoint_id", "none")
        session_id = get_current_session_id() or "unknown"

        message = (
            f"⚠️ PRECLEAR ALERT ({pct}%)\n"
            f"Tokens: ~{tokens:,}\n" if isinstance(tokens, int) else f"Tokens: {tokens}\n"
            f"Checkpoint: #{checkpoint}\n"
            f"Session: {session_id[:16]}\n"
            f"Recomand: /clear + reseed"
        )

        # Trimite via 'say --tg --silent'
        say_path = Path.home() / ".local/bin/say"
        if say_path.exists():
            result = subprocess.run(
                ["python3", str(say_path), "--tg", "--silent", message],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                # Salvează timestamp
                TG_ALERT_STATE_FILE.write_text(json.dumps({
                    "last_preclear_alert": now,
                    "last_checkpoint": checkpoint
                }))
                log_warning(f"TG alert sent: PRECLEAR {pct}%")
                return True
            else:
                log_warning(f"TG alert failed: {result.stderr.decode()[:100]}")
        else:
            log_warning("TG alert skipped: say command not found")

    except Exception as e:
        log_warning(f"TG alert error: {e}")

    return False


# === HANDLERS PENTRU EVENIMENTE ===

def get_memory_context(project_path: str, limit_messages: int = 10, limit_errors: int = 5) -> str:
    """Generează context compact din memoria permanentă."""
    context_parts = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Statistici rapide
        cursor.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM messages")
        total_messages = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE solution IS NOT NULL")
        solved_errors = cursor.fetchone()[0]

        context_parts.append(f"📊 MEMORIE: {total_sessions} sesiuni, {total_messages} mesaje, {solved_errors} erori rezolvate")

        # 2. Ultimele mesaje relevante pentru acest proiect
        cursor.execute("""
            SELECT role, substr(content, 1, 300) as content, timestamp
            FROM messages
            WHERE project_path = ? OR project_path LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (project_path, f"{project_path}%", limit_messages))

        messages = cursor.fetchall()
        if messages:
            context_parts.append("\n💬 ULTIMELE CONVERSAȚII (acest proiect):")
            for msg in reversed(messages):  # Cronologic
                role_icon = "👤" if msg[0] == 'user' else "🤖"
                content = msg[1].replace('\n', ' ')[:200]
                context_parts.append(f"  {role_icon} {content}...")

        # 3. Erori rezolvate recent (pentru a nu le repeta)
        cursor.execute("""
            SELECT error_type, substr(error_message, 1, 100), substr(solution, 1, 200)
            FROM errors_solutions
            WHERE solution IS NOT NULL AND solution_worked = 1
            ORDER BY resolved_at DESC
            LIMIT ?
        """, (limit_errors,))

        errors = cursor.fetchall()
        if errors:
            context_parts.append("\n✅ ERORI REZOLVATE RECENT:")
            for err in errors:
                context_parts.append(f"  • {err[0]}: {err[1]}")
                if err[2]:
                    context_parts.append(f"    → Soluție: {err[2]}")

        # 4. Fișiere modificate recent în acest proiect
        cursor.execute("""
            SELECT DISTINCT file_path
            FROM tool_calls
            WHERE (project_path = ? OR project_path LIKE ?)
              AND tool_name IN ('Edit', 'Write')
              AND file_path IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 5
        """, (project_path, f"{project_path}%"))

        files = cursor.fetchall()
        if files:
            context_parts.append("\n📝 FIȘIERE MODIFICATE RECENT:")
            for f in files:
                context_parts.append(f"  • {f[0]}")

        # 5. Ultimele decizii importante (mesaje assistant cu keywords)
        cursor.execute("""
            SELECT substr(content, 1, 200)
            FROM messages
            WHERE role = 'assistant'
              AND (content LIKE '%configurat%' OR content LIKE '%creat%'
                   OR content LIKE '%instalat%' OR content LIKE '%rezolvat%')
            ORDER BY timestamp DESC
            LIMIT 3
        """)

        decisions = cursor.fetchall()
        if decisions:
            context_parts.append("\n⚙️ DECIZII RECENTE:")
            for d in decisions:
                context_parts.append(f"  • {d[0].replace(chr(10), ' ')}...")

        conn.close()

    except Exception as e:
        context_parts.append(f"⚠️ Eroare încărcare context: {e}")

    return '\n'.join(context_parts)


def handle_session_start(data: Optional[Dict] = None):
    """Începe o sesiune nouă și o înregistrează în baza de date."""
    # TRACE: Log session start
    trace_log("session_start", {"trigger": "hook"})

    session_id = generate_session_id()
    project_path = get_project_path()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO sessions (session_id, project_path, started_at)
        VALUES (?, ?, ?)
    """, (session_id, project_path, datetime.now().isoformat()))

    conn.commit()
    conn.close()

    set_current_session_id(session_id)

    # Creează și fișier Markdown pentru sesiune (human-readable)
    session_md = SESSIONS_DIR / f"{session_id}.md"
    with open(session_md, 'w') as f:
        f.write(f"# Sesiune: {session_id}\n\n")
        f.write(f"**Început:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Proiect:** {project_path}\n\n")
        f.write("---\n\n")
        f.write("## Activități\n\n")

    log_debug(f"Sesiune nouă începută: {session_id}")

    # ÎNCARCĂ ȘI AFIȘEAZĂ CONTEXT DIN MEMORIA PERMANENTĂ
    memory_context = get_memory_context(project_path)

    # Output pentru hook - include contextul din memorie
    print(memory_context)
    print(json.dumps({"status": "ok", "session_id": session_id}))


def handle_session_end(data: Optional[Dict] = None):
    """Finalizează sesiunea curentă și salvează toate răspunsurile din transcript."""
    # TRACE: Log session end / stop
    trace_log("session_end", {"trigger": "stop_hook"})

    session_id = get_current_session_id()
    if not session_id:
        log_debug("handle_session_end: Nu există sesiune activă")
        return

    # === EXTRAGE ȘI SALVEAZĂ RĂSPUNSURILE ASISTENTULUI DIN TRANSCRIPT ===
    saved_responses = 0
    try:
        transcript_path = find_session_transcript(session_id)
        if transcript_path:
            log_debug(f"Transcript găsit: {transcript_path}")
            responses = extract_assistant_responses_from_transcript(transcript_path, session_id)
            saved_responses = save_assistant_responses_to_db(responses, session_id)
            log_debug(f"Extrase și salvate {saved_responses} răspunsuri din {len(responses)} găsite")
        else:
            log_debug("Nu s-a găsit transcript pentru sesiune")
    except Exception as e:
        log_error(f"Eroare la extragerea răspunsurilor din transcript: {e}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Actualizează sesiunea
    cursor.execute("""
        UPDATE sessions
        SET ended_at = ?,
            total_messages = (SELECT COUNT(*) FROM messages WHERE session_id = ?),
            total_tool_calls = (SELECT COUNT(*) FROM tool_calls WHERE session_id = ?)
        WHERE session_id = ?
    """, (datetime.now().isoformat(), session_id, session_id, session_id))

    # Actualizează statisticile
    cursor.execute("""
        INSERT OR REPLACE INTO session_stats (session_id, date)
        VALUES (?, ?)
    """, (session_id, datetime.now().date().isoformat()))

    conn.commit()
    conn.close()

    # Finalizează fișierul Markdown
    session_md = SESSIONS_DIR / f"{session_id}.md"
    if session_md.exists():
        with open(session_md, 'a') as f:
            f.write(f"\n---\n\n**Încheiat:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # === TRANSCRIPT RECONCILER - FINAL SWEEP (capturează toate erorile ratate) ===
    final_reconciler_errors = 0
    try:
        reconciler_result = run_reconciler(session_id=session_id, max_lines=500)  # Mai multe linii la final
        if reconciler_result:
            final_reconciler_errors = reconciler_result.get("new_errors", 0)
            if final_reconciler_errors > 0:
                log_debug(f"RECONCILER FINAL: {final_reconciler_errors} erori capturate")
    except Exception as e:
        log_error(f"Eroare reconciler în session_end: {e}")

    # === CONTEXT MONITOR - FINAL SNAPSHOT (force) ===
    final_checkpoint_id = None
    try:
        monitor_result = run_context_monitor(force=True, reason_suffix="_session_end")
        if monitor_result and monitor_result.get("checkpoint_created"):
            final_checkpoint_id = monitor_result.get("checkpoint_id")
            log_debug(f"Final checkpoint creat: {final_checkpoint_id}")
    except Exception as e:
        log_error(f"Eroare monitor în session_end: {e}")

    # === KNOWLEDGE EXTRACTION V1 (Faza 17X) ===
    knowledge_extracted = 0
    try:
        from knowledge_extractor import run_extraction
        ke_result = run_extraction(session_id)
        knowledge_extracted = ke_result.get("extracted", 0)
        ke_saved = ke_result.get("saved", {})
        if knowledge_extracted > 0:
            log_debug(f"Knowledge extracted: {knowledge_extracted} candidates, "
                      f"saved D:{ke_saved.get('decision', 0)} F:{ke_saved.get('fact', 0)} "
                      f"R:{ke_saved.get('resolution', 0)}")
    except Exception as e:
        log_error(f"Eroare knowledge extraction în session_end: {e}")

    # === AUTOMATIC BACKUP V1 (Faza 17Y) ===
    backup_file = None
    try:
        from backup_manager import create_backup
        backup_result = create_backup(reason="session_end", session_id=session_id)
        if backup_result["success"]:
            backup_file = backup_result["filename"]
            log_debug(f"Auto-backup creat: {backup_file}")
        else:
            log_debug(f"Auto-backup skip/fail: {backup_result.get('error', 'unknown')}")
    except Exception as e:
        log_error(f"Eroare auto-backup în session_end: {e}")

    clear_current_session()
    log_debug(f"Sesiune încheiată: {session_id}, {saved_responses} răspunsuri salvate din transcript")

    print(json.dumps({
        "status": "ok",
        "session_id": session_id,
        "ended": True,
        "assistant_responses_saved": saved_responses,
        "reconciler_errors_captured": final_reconciler_errors,
        "final_checkpoint": final_checkpoint_id,
        "knowledge_extracted": knowledge_extracted,
        "backup": backup_file
    }))


def handle_pre_tool(data: Optional[Dict] = None):
    """
    Apelat ÎNAINTE de executarea unui tool.
    Salvează versiunea curentă a fișierelor pentru Edit/Write.
    """
    if not data:
        data = read_stdin_json() or {}

    session_id = get_current_session_id()
    if not session_id:
        # Creează sesiune dacă nu există
        handle_session_start()
        session_id = get_current_session_id()

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    # Pentru Edit, Write, MultiEdit - salvăm versiunea curentă a fișierului
    if tool_name in ['Edit', 'Write', 'MultiEdit']:
        file_path = tool_input.get('file_path', '')
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                content_hash = hash_content(content)

                conn = get_db_connection()
                cursor = conn.cursor()

                # Verificăm dacă avem deja această versiune (deduplicare)
                cursor.execute("""
                    SELECT id FROM file_versions
                    WHERE file_path = ? AND content_hash = ?
                    LIMIT 1
                """, (file_path, content_hash))

                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO file_versions
                        (file_path, content_hash, content, size_bytes, session_id, change_type, project_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        file_path,
                        content_hash,
                        content,
                        len(content.encode('utf-8')),
                        session_id,
                        f"before_{tool_name.lower()}",
                        get_project_path()
                    ))
                    conn.commit()
                    log_debug(f"Backup salvat pentru: {file_path}")

                conn.close()
            except Exception as e:
                log_error(f"Eroare backup fișier {file_path}: {e}")

    print(json.dumps({"status": "ok", "action": "pre_tool", "tool": tool_name}))


def handle_post_tool(data: Optional[Dict] = None):
    """
    Apelat DUPĂ executarea unui tool.
    Salvează TOTUL în baza de date.
    """
    if not data:
        data = read_stdin_json() or {}

    # TRACE: Log post_tool event
    tool_name = data.get('tool_name', 'unknown') if data else 'unknown'
    trace_log("post_tool", {"tool": tool_name})

    # DEBUG: Log ce primim de la Claude Code
    log_debug(f"POST_TOOL RAW DATA keys: {list(data.keys()) if data else 'EMPTY'}")
    if data:
        log_debug(f"POST_TOOL tool_name: {data.get('tool_name', 'N/A')}")
        tool_resp_raw = data.get('tool_response')
        log_debug(f"POST_TOOL tool_response type: {type(tool_resp_raw)}, value: {str(tool_resp_raw)[:200] if tool_resp_raw else 'NONE'}")

    session_id = get_current_session_id()
    if not session_id:
        handle_session_start()
        session_id = get_current_session_id()

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})
    duration_ms = data.get('duration_ms', 0)

    # Claude Code trimite 'tool_response' ca dict pentru Bash
    tool_response_raw = data.get('tool_response') or data.get('tool_result', '')
    tool_result = ''
    exit_code = None
    error_output = ''

    if isinstance(tool_response_raw, dict):
        # Bash tool: extrage stdout, stderr
        stdout = tool_response_raw.get('stdout', '')
        stderr = tool_response_raw.get('stderr', '')
        tool_result = stdout
        error_output = stderr

        # Extrage comanda pentru a determina dacă e o comandă de "afișare date"
        command = ''
        if isinstance(tool_input, dict):
            command = tool_input.get('command', '')

        # Comenzi care doar afișează date - nu detecta erori din stdout-ul lor
        display_commands = ['sqlite3', 'grep', 'tail', 'head', 'cat', 'less', 'more', 'awk', 'sed']
        is_display_command = any(cmd in command.split()[0] if command else False for cmd in display_commands)

        # Detectează erori DOAR din stderr (nu din stdout care poate conține text cu "error")
        if stderr and stderr.strip():
            exit_code = 1  # Orice în stderr e eroare
        elif tool_response_raw.get('interrupted'):
            exit_code = 1
        elif is_display_command:
            # Comenzile de afișare date nu generează erori în stdout
            exit_code = 0
        else:
            # Verifică pattern-uri clare de eroare în stdout
            # Pattern-urile trebuie să fie la ÎNCEPUTUL liniei (prima linie non-goală)
            error_patterns = [
                'Traceback (most recent call last)',  # Python traceback
                'SyntaxError:', 'NameError:', 'TypeError:', 'ValueError:',
                'ImportError:', 'ModuleNotFoundError:', 'FileNotFoundError:',
                'PermissionError:', 'OSError:', 'RuntimeError:', 'AttributeError:',
                'KeyError:', 'IndexError:', 'ZeroDivisionError:',
            ]
            # Pattern-uri generice - verifică doar la început de linie
            line_start_patterns = [
                'command not found',
                'No such file or directory',
                'Permission denied',
                'ENOENT:', 'EACCES:',
            ]

            # Verifică DOAR prima linie non-goală pentru pattern-uri Python
            first_line = ''
            if stdout:
                for line in stdout.split('\n'):
                    if line.strip():
                        first_line = line.strip()
                        break

            has_python_error = any(pattern in first_line for pattern in error_patterns)

            # Verifică pattern-uri generice la începutul oricărei linii
            has_line_error = False
            if stdout:
                for line in stdout.split('\n'):
                    line_stripped = line.strip()
                    if any(line_stripped.startswith(pattern) for pattern in line_start_patterns):
                        has_line_error = True
                        break

            exit_code = 1 if (has_python_error or has_line_error) else 0
    elif isinstance(tool_response_raw, str):
        tool_result = tool_response_raw
        exit_code = 0  # Nu putem determina fără context
    else:
        exit_code = 0

    # Extrage file_path dacă există
    file_path = None
    if isinstance(tool_input, dict):
        file_path = tool_input.get('file_path') or tool_input.get('path')

    # === SCRUB TOOL DATA ===
    tool_input_scrubbed, _ = scrub_payload(tool_input)
    tool_result_scrubbed, _ = scrub_text(str(tool_result) if tool_result else "")
    error_output_scrubbed, _ = scrub_text(str(error_output) if error_output else "")

    # === GUARD CHECK ===
    # Verifică toate componentele pentru secrete
    guard_check_payload = {
        "tool_input": tool_input_scrubbed,
        "tool_result": tool_result_scrubbed,
        "error_output": error_output_scrubbed
    }
    guard_result = guard_detect(guard_check_payload)
    if guard_result["hits"] and should_block(guard_result["severity"]):
        quarantine_write("post_tool", {
            "tool_name": tool_name,
            "tool_input": tool_input_scrubbed,
            "tool_result": tool_result_scrubbed[:500],
            "error_output": error_output_scrubbed[:500]
        }, guard_result)
        print(json.dumps({"status": "quarantined", "reason": "secret_detected", "severity": guard_result["severity"]}))
        return  # NU INSERT ÎN DB

    conn = get_db_connection()
    cursor = conn.cursor()

    # Salvează tool call
    cursor.execute("""
        INSERT INTO tool_calls
        (session_id, tool_name, tool_input, tool_result, exit_code, duration_ms,
         success, project_path, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        tool_name,
        json.dumps(tool_input_scrubbed) if isinstance(tool_input_scrubbed, dict) else str(tool_input_scrubbed),
        tool_result_scrubbed[:50000] if tool_result_scrubbed else None,  # SCRUBBED
        exit_code,
        duration_ms,
        exit_code == 0 if exit_code is not None else True,
        get_project_path(),
        file_path
    ))

    # Pentru Bash - salvează și în bash_history
    if tool_name == 'Bash':
        command = tool_input.get('command', '') if isinstance(tool_input, dict) else str(tool_input)
        command_scrubbed, _ = scrub_text(command)  # SCRUB command

        cursor.execute("""
            INSERT INTO bash_history
            (session_id, command, working_directory, exit_code, output, error_output, duration_ms, project_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            command_scrubbed,  # SCRUBBED
            get_project_path(),
            exit_code,
            tool_result_scrubbed[:50000] if tool_result_scrubbed else None,  # SCRUBBED
            error_output_scrubbed[:50000] if error_output_scrubbed else None,  # SCRUBBED
            duration_ms,
            get_project_path()
        ))

    # Detectează erori și le salvează automat
    if exit_code and exit_code != 0:
        # Preferă error_output_scrubbed, apoi tool_result_scrubbed
        error_msg = error_output_scrubbed if error_output_scrubbed else (tool_result_scrubbed if tool_result_scrubbed else "Unknown error")
        cursor.execute("""
            INSERT INTO errors_solutions
            (error_type, error_message, file_path, session_id, project_path, language)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "tool_error",
            error_msg[:5000],  # SCRUBBED
            file_path,
            session_id,
            get_project_path(),
            detect_language(file_path) if file_path else None
        ))
        log_debug(f"EROARE DETECTATĂ ȘI SALVATĂ: {tool_name} - {error_msg[:100]}")

    conn.commit()
    conn.close()

    # Actualizează fișierul Markdown al sesiunii
    session_md = SESSIONS_DIR / f"{session_id}.md"
    if session_md.exists():
        with open(session_md, 'a') as f:
            timestamp = datetime.now().strftime('%H:%M:%S')
            status = "✓" if (exit_code == 0 or exit_code is None) else "✗"
            f.write(f"- `{timestamp}` {status} **{tool_name}**")
            if file_path:
                f.write(f" - `{file_path}`")
            f.write("\n")

    log_debug(f"Tool salvat: {tool_name} (exit: {exit_code})")

    # === TRANSCRIPT RECONCILER (lightweight, 50 linii) ===
    # Rulează pentru a captura erori din tool calls anterioare care nu au declanșat PostToolUse
    reconciler_errors = 0
    try:
        reconciler_result = run_reconciler(session_id=session_id, max_lines=50)
        if reconciler_result:
            reconciler_errors = reconciler_result.get("new_errors", 0)
    except Exception:
        pass  # Nu bloca post_tool dacă reconciler eșuează

    # === CONTEXT MONITOR (SAFE MODE) ===
    output = {"status": "ok", "action": "post_tool", "tool": tool_name}
    if reconciler_errors > 0:
        output["reconciler_errors"] = reconciler_errors
    try:
        monitor_result = run_context_monitor()
        if monitor_result:
            log_debug(f"Monitor post_tool: {monitor_result.get('threshold')} ({monitor_result.get('context_percentage')}%)")
            # Adaugă hint doar la preclear
            preclear_hint = build_preclear_hint(monitor_result)
            if preclear_hint:
                output["monitor_hint"] = preclear_hint
    except Exception as e:
        log_error(f"Eroare monitor în post_tool: {e}")

    print(json.dumps(output))


def handle_user_prompt(data: Optional[Dict] = None):
    """Salvează prompt-ul utilizatorului."""
    if not data:
        data = read_stdin_json() or {}

    # TRACE: Log user prompt event
    trace_log("user_prompt", {"has_data": bool(data)})

    session_id = get_current_session_id()
    if not session_id:
        handle_session_start()
        session_id = get_current_session_id()

    prompt = data.get('prompt', '') or data.get('content', '') or data.get('message', '')

    if not prompt:
        log_debug("handle_user_prompt: Prompt gol")
        return

    # === SCRUB PROMPT ===
    prompt_scrubbed, scrub_meta = scrub_text(prompt)

    # === GUARD CHECK ===
    guard_result = guard_detect(prompt_scrubbed)
    if guard_result["hits"] and should_block(guard_result["severity"]):
        quarantine_write("user_prompt", {"prompt": prompt_scrubbed}, guard_result)
        print(json.dumps({"status": "quarantined", "reason": "secret_detected", "severity": guard_result["severity"]}))
        return  # NU INSERT ÎN DB

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages
        (session_id, role, content, message_type, project_path)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session_id,
        'user',
        prompt_scrubbed,  # <-- SCRUBBED
        'prompt',
        get_project_path()
    ))

    conn.commit()
    conn.close()

    # Actualizează fișierul Markdown
    session_md = SESSIONS_DIR / f"{session_id}.md"
    if session_md.exists():
        with open(session_md, 'a') as f:
            timestamp = datetime.now().strftime('%H:%M:%S')
            # Limitează la primele 200 caractere pentru Markdown (folosește scrubbed)
            preview = prompt_scrubbed[:200] + "..." if len(prompt_scrubbed) > 200 else prompt_scrubbed
            preview = preview.replace('\n', ' ')
            f.write(f"\n### [{timestamp}] User:\n> {preview}\n\n")

    log_debug(f"Prompt salvat: {len(prompt_scrubbed)} caractere")

    # === TRANSCRIPT RECONCILER (capturează erori ratate) ===
    reconciler_result = None
    try:
        reconciler_result = run_reconciler(session_id=session_id, max_lines=100)
    except Exception as e:
        log_debug(f"Reconciler skip în user_prompt: {e}")

    # === CONTEXT MONITOR (SAFE MODE) ===
    output = {"status": "ok", "action": "user_prompt", "length": len(prompt_scrubbed)}
    if reconciler_result and reconciler_result.get("new_errors", 0) > 0:
        output["reconciler_errors"] = reconciler_result["new_errors"]
    try:
        monitor_result = run_context_monitor()
        if monitor_result:
            log_debug(f"Monitor user_prompt: {monitor_result.get('threshold')} ({monitor_result.get('context_percentage')}%)")
            # Adaugă hint doar la preclear
            preclear_hint = build_preclear_hint(monitor_result)
            if preclear_hint:
                output["monitor_hint"] = preclear_hint
    except Exception as e:
        log_error(f"Eroare monitor în user_prompt: {e}")

    print(json.dumps(output))


def handle_assistant_response(data: Optional[Dict] = None):
    """Salvează răspunsul asistentului (dacă este disponibil)."""
    if not data:
        data = read_stdin_json() or {}

    session_id = get_current_session_id()
    if not session_id:
        return

    response = data.get('response', '') or data.get('prompt_response', '') or data.get('content', '')
    if not response:
        return

    # === SCRUB RESPONSE ===
    response_scrubbed, _ = scrub_text(response)

    # === GUARD CHECK ===
    guard_result = guard_detect(response_scrubbed)
    if guard_result["hits"] and should_block(guard_result["severity"]):
        quarantine_write("assistant_response", {"response": response_scrubbed}, guard_result)
        return  # NU INSERT ÎN DB

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages
        (session_id, role, content, message_type, project_path)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session_id,
        'assistant',
        response_scrubbed,  # <-- SCRUBBED
        'response',
        get_project_path()
    ))

    conn.commit()
    conn.close()

    log_debug(f"Răspuns salvat: {len(response_scrubbed)} caractere")


def detect_language(file_path: Optional[str]) -> Optional[str]:
    """Detectează limbajul de programare din extensia fișierului."""
    if not file_path:
        return None

    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.jsx': 'javascript',
        '.java': 'java',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.sh': 'bash',
        '.bash': 'bash',
        '.sql': 'sql',
        '.html': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.md': 'markdown',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
    }

    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext)


# === MAIN ===

def handle_monitor_test(simulate_percent: int, force: bool = False):
    """Handler pentru teste monitor (CLI)."""
    result = run_context_monitor(
        simulate_percent=simulate_percent,
        force=force,
        reason_suffix="_test"
    )

    if result:
        # Adaugă hint doar la preclear
        preclear_hint = build_preclear_hint(result)
        if preclear_hint:
            result["monitor_hint"] = preclear_hint

        print(json.dumps(result, indent=2))
        # Exit code bazat pe threshold
        threshold = result.get("threshold", "ok")
        if threshold == "preclear":
            sys.exit(3)
        elif threshold == "checkpoint":
            sys.exit(2)
        elif threshold == "warn":
            sys.exit(1)
        sys.exit(0)
    else:
        print(json.dumps({"status": "throttled_or_error"}))
        sys.exit(0)


def handle_monitor_state():
    """Afișează starea curentă a monitorului."""
    state = load_monitor_state()
    print(json.dumps(state, indent=2))


def handle_reconcile_now():
    """Rulează reconciler manual și afișează rezultatul."""
    session_id = get_current_session_id()

    result = run_reconciler(session_id=session_id, max_lines=500)

    if result:
        # Adaugă statistici din DB
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE source = 'auto_reconciler'")
            result["total_auto_errors"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE resolved = 0")
            result["unresolved_errors"] = cursor.fetchone()[0]

            # Ultimele 3 erori
            cursor.execute("""
                SELECT session_id, error_type, substr(error_message, 1, 100), created_at
                FROM errors_solutions
                ORDER BY created_at DESC
                LIMIT 3
            """)
            result["recent_errors"] = [
                {"session_id": r[0], "type": r[1], "message": r[2], "created_at": r[3]}
                for r in cursor.fetchall()
            ]

            conn.close()
        except Exception as e:
            result["db_error"] = str(e)

        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "error", "message": "Reconciler failed"}))


def handle_reconciler_status():
    """Afișează statusul reconciler-ului."""
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))

        from transcript_reconciler import get_status
        status = get_status()
        print(json.dumps(status, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))


def main():
    """Entry point - procesează argumentele și apelează handler-ul corespunzător."""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: memory_daemon.py <event_type>"}))
        sys.exit(1)

    event_type = sys.argv[1]

    # Asigură-te că directoarele există
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    FILE_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # === CLI SPECIAL PENTRU TESTE MONITOR ===
    if event_type == "monitor_test":
        if len(sys.argv) < 4 or sys.argv[2] != "--simulate":
            print(json.dumps({"error": "Usage: memory_daemon.py monitor_test --simulate <percent> [--force]"}))
            sys.exit(1)
        try:
            simulate_pct = int(sys.argv[3])
            force = "--force" in sys.argv
            handle_monitor_test(simulate_pct, force)
        except ValueError:
            print(json.dumps({"error": "Invalid percent value"}))
            sys.exit(1)
        return

    if event_type == "monitor_state":
        handle_monitor_state()
        return

    if event_type == "reconcile_now":
        handle_reconcile_now()
        return

    if event_type == "reconciler_status":
        handle_reconciler_status()
        return

    # === COMPACT TRACE COMMANDS ===
    if event_type == "compact_test":
        # Simulează un event de tip compact (manual)
        trace_log("compact_test", {"source": "cli_manual"})
        print(json.dumps({"status": "ok", "action": "compact_test logged"}))
        return

    if event_type == "trace_status":
        # Afișează ultimele 10 intrări din compact_trace.log
        if COMPACT_TRACE_FILE.exists():
            try:
                lines = COMPACT_TRACE_FILE.read_text().strip().split('\n')
                recent = lines[-10:] if len(lines) > 10 else lines
                entries = [json.loads(l) for l in recent if l.strip()]
                print(json.dumps({"status": "ok", "count": len(entries), "recent": entries}, indent=2))
            except Exception as e:
                print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(json.dumps({"status": "ok", "count": 0, "recent": [], "message": "No trace file yet"}))
        return

    if event_type == "pre_compact":
        # Handler pentru PreCompact hook (dacă e configurat)
        trace_log("pre_compact", {"source": "hook"})
        print(json.dumps({"status": "ok", "action": "pre_compact logged"}))
        return

    handlers = {
        'session_start': handle_session_start,
        'session_end': handle_session_end,
        'pre_tool': handle_pre_tool,
        'post_tool': handle_post_tool,
        'user_prompt': handle_user_prompt,
        'assistant_response': handle_assistant_response,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler()
        except Exception as e:
            log_error(f"Eroare în handler {event_type}: {e}")
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
    else:
        print(json.dumps({"error": f"Unknown event type: {event_type}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
