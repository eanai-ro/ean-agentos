#!/usr/bin/env python3
"""
Transcript Reconciler - Capturează erori din transcript când PostToolUse nu se apelează.

Scanează incremental fișierul JSONL al sesiunii și extrage tool calls cu exit!=0.
Salvează erorile în DB cu dedup prin fingerprint.
Corelează tool_result cu tool_use pentru a obține tool_name corect.

Problema rezolvată:
- Claude Code NU apelează PostToolUse hook pentru comenzi Bash cu exit code != 0
- Dar aceste comenzi APAR în transcript (*.jsonl)
- Reconciler-ul citește transcript-ul și recuperează erorile ratate

Usage:
    python3 transcript_reconciler.py reconcile [--session-id ID]
    python3 transcript_reconciler.py status
"""

import json
import hashlib
import sqlite3
import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple


# === CONFIGURAȚIE ===
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"
MEMORY_DIR = GLOBAL_DB.parent
RECONCILER_STATE_FILE = MEMORY_DIR / ".reconciler_state.json"
SESSION_FILE = MEMORY_DIR / ".current_session"

# Versiune state file (pentru migrări viitoare)
STATE_VERSION = 2

# Limită linii procesate per rulare (pentru performanță)
MAX_LINES_PER_RUN = 200

# Cache settings pentru corelare tool_use -> tool_result
TOOL_CACHE_MAX_SIZE = 200  # Max entries per session
RECENT_TOOL_STACK_SIZE = 20  # Fallback stack size
MAX_TIME_GAP_SECONDS = 30  # Max gap pentru fallback correlation

# Rewind safety settings
TAIL_HASH_SIZE = 512  # Bytes pentru tail hash (detectare truncation)
MIN_REWIND_OFFSET = 1024  # Minimum bytes to rewind on drift detection


def get_db_connection(timeout: int = 30) -> sqlite3.Connection:
    """Obține conexiune la baza de date cu WAL mode și timeout."""
    conn = sqlite3.connect(str(GLOBAL_DB), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_db_schema():
    """Asigură că schema DB are coloanele necesare pentru reconciler."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verifică și adaugă coloane lipsă în errors_solutions
    cursor.execute("PRAGMA table_info(errors_solutions)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    migrations = []

    # Coloane originale
    if 'resolved' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN resolved INTEGER DEFAULT 0")

    if 'source' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN source TEXT DEFAULT 'manual'")

    if 'fingerprint' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN fingerprint TEXT")

    # Coloane noi pentru corelare tool_name
    if 'tool_name_resolved' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN tool_name_resolved TEXT")

    if 'tool_use_id' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN tool_use_id TEXT")

    if 'tool_input_preview' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN tool_input_preview TEXT")

    if 'tool_seq' not in existing_columns:
        migrations.append("ALTER TABLE errors_solutions ADD COLUMN tool_seq INTEGER")

    for migration in migrations:
        try:
            cursor.execute(migration)
            print(f"✓ Migration: {migration[:60]}...")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

    # Creează indexuri dacă lipsesc
    indexes = [
        ("idx_errors_resolved", "CREATE INDEX IF NOT EXISTS idx_errors_resolved ON errors_solutions(resolved)"),
        ("idx_errors_source", "CREATE INDEX IF NOT EXISTS idx_errors_source ON errors_solutions(source)"),
        ("idx_errors_fingerprint", "CREATE UNIQUE INDEX IF NOT EXISTS idx_errors_fingerprint ON errors_solutions(fingerprint) WHERE fingerprint IS NOT NULL"),
        ("idx_errors_tool_name", "CREATE INDEX IF NOT EXISTS idx_errors_tool_name ON errors_solutions(tool_name_resolved)"),
        ("idx_errors_tool_use_id", "CREATE INDEX IF NOT EXISTS idx_errors_tool_use_id ON errors_solutions(tool_use_id)"),
    ]

    for idx_name, idx_sql in indexes:
        try:
            cursor.execute(idx_sql)
        except sqlite3.OperationalError:
            pass  # Index deja există

    conn.commit()
    conn.close()


def compute_tail_hash(file_path: Path, size: int = TAIL_HASH_SIZE) -> str:
    """Calculează hash pentru ultimii N bytes ai fișierului (detectare truncation)."""
    try:
        file_size = file_path.stat().st_size
        if file_size == 0:
            return "empty"

        read_size = min(size, file_size)
        with open(file_path, 'rb') as f:
            f.seek(max(0, file_size - read_size))
            tail_data = f.read(read_size)
        return hashlib.md5(tail_data).hexdigest()
    except (IOError, OSError):
        return "error"


def get_file_metadata(file_path: Path) -> Dict[str, Any]:
    """Obține metadata completă despre fișier pentru drift detection."""
    try:
        stat = file_path.stat()
        return {
            "file_size": stat.st_size,
            "mtime": stat.st_mtime,
            "inode": stat.st_ino,
            "tail_hash": compute_tail_hash(file_path)
        }
    except (IOError, OSError):
        return {
            "file_size": 0,
            "mtime": 0,
            "inode": 0,
            "tail_hash": "error"
        }


def detect_file_drift(current_meta: Dict, saved_meta: Dict, offset: int) -> Tuple[bool, str]:
    """
    Detectează dacă fișierul s-a schimbat în mod neașteptat.

    Returns:
        (drift_detected, reason)
    """
    # Cazul 1: Fișierul s-a micșorat (truncation/rotation)
    if current_meta["file_size"] < saved_meta.get("file_size", 0):
        return True, "file_truncated"

    # Cazul 2: Offset mai mare decât fișierul
    if offset > current_meta["file_size"]:
        return True, "offset_beyond_file"

    # Cazul 3: inode s-a schimbat (fișier înlocuit)
    if saved_meta.get("inode") and current_meta["inode"] != saved_meta["inode"]:
        return True, "inode_changed"

    # Cazul 4: tail_hash diferit când fișierul e mai mic sau egal
    # (sugerează că conținutul anterior s-a modificat)
    if (saved_meta.get("tail_hash") and
        current_meta["file_size"] <= saved_meta.get("file_size", 0) and
        current_meta["tail_hash"] != saved_meta["tail_hash"]):
        return True, "content_modified"

    return False, "ok"


def calculate_safe_rewind_offset(file_size: int, saved_offset: int, drift_reason: str) -> int:
    """
    Calculează un offset sigur pentru rewind când se detectează drift.

    Strategia: rewind la un punct sigur, nu resetează complet.
    """
    if drift_reason == "file_truncated" or drift_reason == "inode_changed":
        # Fișier nou - începem de la 0
        return 0

    if drift_reason == "offset_beyond_file":
        # Offset invalid - rewind cu margine de siguranță
        return max(0, file_size - MIN_REWIND_OFFSET * 2)

    if drift_reason == "content_modified":
        # Conținut modificat - rewind cu MIN_REWIND_OFFSET
        return max(0, saved_offset - MIN_REWIND_OFFSET)

    return saved_offset


def load_reconciler_state() -> Dict[str, Any]:
    """Încarcă starea reconciler-ului din fișier cu suport pentru versiuni."""
    default_state = {
        "version": STATE_VERSION,
        "sessions": {},  # {session_id: {"last_offset": int, "last_line": int, "file_meta": {...}}}
        "total_errors_found": 0,
        "total_runs": 0,
        "last_run_at": None,
        "last_full_rescan_at": None
    }

    if RECONCILER_STATE_FILE.exists():
        try:
            state = json.loads(RECONCILER_STATE_FILE.read_text())

            # Migrare la versiune nouă dacă lipsesc câmpuri
            if state.get("version", 1) < STATE_VERSION:
                log_debug(f"Migrating state from v{state.get('version', 1)} to v{STATE_VERSION}")
                state["version"] = STATE_VERSION
                if "last_full_rescan_at" not in state:
                    state["last_full_rescan_at"] = None
                # Migrare sessions la noul format
                for sid, sdata in state.get("sessions", {}).items():
                    if "file_meta" not in sdata:
                        sdata["file_meta"] = {}

            return state
        except (json.JSONDecodeError, IOError) as e:
            log_error(f"Eroare citire state, resetare: {e}")

    return default_state


def save_reconciler_state(state: Dict[str, Any]):
    """Salvează starea reconciler-ului în fișier."""
    try:
        RECONCILER_STATE_FILE.write_text(json.dumps(state, indent=2))
    except IOError as e:
        log_error(f"Eroare salvare reconciler state: {e}")


def log_error(message: str):
    """Loghează erori."""
    error_log = MEMORY_DIR / "daemon_errors.log"
    timestamp = datetime.now().isoformat()
    with open(error_log, 'a') as f:
        f.write(f"[{timestamp}] RECONCILER: {message}\n")


def log_debug(message: str):
    """Loghează debug."""
    debug_log = MEMORY_DIR / "daemon_debug.log"
    timestamp = datetime.now().isoformat()
    with open(debug_log, 'a') as f:
        f.write(f"[{timestamp}] RECONCILER: {message}\n")


def get_current_session_id() -> Optional[str]:
    """Citește ID-ul sesiunii curente."""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return None


def find_session_transcript(session_id: Optional[str] = None) -> Optional[Path]:
    """Găsește fișierul .jsonl pentru sesiune."""
    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return None

    # Strategie 1: Căută exact după session_id
    if session_id:
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                exact_match = project_dir / f"{session_id}.jsonl"
                if exact_match.exists():
                    return exact_match

    # Strategie 2: Cel mai recent fișier din proiectul curent
    cwd = os.getcwd()
    project_slug = cwd.replace('/', '-').lstrip('-')
    project_dir = projects_dir / project_slug

    if project_dir.exists():
        jsonl_files = list(project_dir.glob("*.jsonl"))
        if jsonl_files:
            return max(jsonl_files, key=lambda f: f.stat().st_mtime)

    # Strategie 3: Cel mai recent fișier din orice proiect
    all_jsonl = list(projects_dir.glob("*/*.jsonl"))
    if all_jsonl:
        return max(all_jsonl, key=lambda f: f.stat().st_mtime)

    return None


def compute_fingerprint(tool_name: str, command: str, exit_code: int, stderr_first_line: str, session_id: str = "") -> str:
    """Calculează fingerprint pentru deduplicare."""
    # Normalizează command
    normalized_cmd = ' '.join(command.split())[:200]  # Collapse whitespace, limitează
    # Normalizează stderr
    normalized_stderr = stderr_first_line.strip()[:100] if stderr_first_line else ""

    # Hash combinat
    content = f"{tool_name}|{normalized_cmd}|{exit_code}|{normalized_stderr}|{session_id}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]


def is_grep_no_match(tool_name: str, exit_code: int, stderr: str) -> bool:
    """
    Verifică dacă e grep exit 1 cu "no match" (nu e eroare reală).

    grep exit codes:
    - 0: Match found
    - 1: No match found (nu e eroare!)
    - 2+: Error
    """
    if tool_name not in ('Bash', 'Unknown'):
        return False

    # Exit 1 cu stderr gol = "no match"
    if exit_code == 1 and (not stderr or not stderr.strip()):
        return True

    return False


# === TOOL CORRELATION CACHE ===

class ToolCorrelationCache:
    """Cache pentru corelarea tool_use -> tool_result."""

    def __init__(self, max_cache_size: int = TOOL_CACHE_MAX_SIZE,
                 stack_size: int = RECENT_TOOL_STACK_SIZE):
        self.tool_cache: Dict[str, Dict[str, Dict]] = {}  # session_id -> {tool_use_id -> info}
        self.recent_stack: Dict[str, deque] = {}  # session_id -> deque of recent tool_use
        self.max_cache_size = max_cache_size
        self.stack_size = stack_size
        self.seq_counter: Dict[str, int] = {}  # session_id -> seq

    def add_tool_use(self, session_id: str, tool_use_id: str, tool_name: str,
                     tool_input: Any, timestamp: str = ""):
        """Adaugă un tool_use în cache."""
        if session_id not in self.tool_cache:
            self.tool_cache[session_id] = {}
            self.recent_stack[session_id] = deque(maxlen=self.stack_size)
            self.seq_counter[session_id] = 0

        # Increment seq
        self.seq_counter[session_id] += 1
        seq = self.seq_counter[session_id]

        # Construiește input preview
        input_preview = ""
        if isinstance(tool_input, dict):
            if 'command' in tool_input:
                input_preview = tool_input['command'][:500]
            elif 'file_path' in tool_input:
                input_preview = tool_input['file_path']
            else:
                input_preview = json.dumps(tool_input)[:500]
        elif isinstance(tool_input, str):
            input_preview = tool_input[:500]

        info = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'input_preview': input_preview,
            'timestamp': timestamp,
            'seq': seq
        }

        # Adaugă în cache principal
        self.tool_cache[session_id][tool_use_id] = info

        # Adaugă în recent stack
        self.recent_stack[session_id].append({
            'tool_use_id': tool_use_id,
            **info
        })

        # Evict dacă cache-ul e prea mare
        if len(self.tool_cache[session_id]) > self.max_cache_size:
            # Șterge cele mai vechi
            oldest_keys = list(self.tool_cache[session_id].keys())[:50]
            for k in oldest_keys:
                del self.tool_cache[session_id][k]

    def get_tool_info(self, session_id: str, tool_use_id: str) -> Optional[Dict]:
        """Obține info despre un tool_use prin ID."""
        if session_id in self.tool_cache:
            return self.tool_cache[session_id].get(tool_use_id)
        return None

    def get_recent_tool(self, session_id: str, timestamp: str = "") -> Optional[Dict]:
        """Obține cel mai recent tool_use ca fallback."""
        if session_id not in self.recent_stack or not self.recent_stack[session_id]:
            return None

        recent = self.recent_stack[session_id][-1]

        # Verifică time gap dacă avem timestamps
        if timestamp and recent.get('timestamp'):
            try:
                t1 = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                t2 = datetime.fromisoformat(recent['timestamp'].replace('Z', '+00:00'))
                gap = abs((t1 - t2).total_seconds())
                if gap > MAX_TIME_GAP_SECONDS:
                    return None  # Prea departe în timp
            except (ValueError, TypeError):
                pass  # Continuă fără verificare de timp

        return recent


def extract_tool_use_from_entry(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extrage toate tool_use events dintr-un entry de transcript."""
    tool_uses = []
    timestamp = data.get('timestamp', '')

    # Format 1: assistant message cu tool_use în content
    if data.get('type') == 'assistant':
        message = data.get('message', {})
        content_list = message.get('content', [])

        for item in content_list:
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'tool_use':
                tool_uses.append({
                    'tool_use_id': item.get('id', ''),
                    'tool_name': item.get('name', 'Unknown'),
                    'tool_input': item.get('input', {}),
                    'timestamp': timestamp
                })

    # Format 2: progress cu nested assistant message
    elif data.get('type') == 'progress':
        progress_data = data.get('data', {})
        message = progress_data.get('message', {})

        if message.get('type') == 'assistant':
            inner_message = message.get('message', {})
            content_list = inner_message.get('content', [])

            for item in content_list:
                if not isinstance(item, dict):
                    continue
                if item.get('type') == 'tool_use':
                    tool_uses.append({
                        'tool_use_id': item.get('id', ''),
                        'tool_name': item.get('name', 'Unknown'),
                        'tool_input': item.get('input', {}),
                        'timestamp': timestamp
                    })

    return tool_uses


def extract_tool_errors_from_transcript(
    transcript_path: Path,
    start_offset: int = 0,
    max_lines: int = MAX_LINES_PER_RUN,
    tool_cache: Optional[ToolCorrelationCache] = None
) -> Tuple[List[Dict[str, Any]], int, int, Dict[str, int]]:
    """
    Extrage tool calls cu erori din transcript cu corelare tool_name.

    Returns:
        (errors_list, new_offset, lines_processed, stats)
    """
    errors = []
    current_offset = start_offset
    lines_processed = 0
    stats = {'resolved': 0, 'unknown': 0, 'tool_uses_found': 0}

    if tool_cache is None:
        tool_cache = ToolCorrelationCache()

    # Extrage session_id din transcript path
    session_id = transcript_path.stem  # Numele fișierului fără extensie

    try:
        with open(transcript_path, 'r') as f:
            # Seek la offset
            f.seek(start_offset)

            # Folosim readline() în loc de for loop pentru a putea folosi f.tell()
            while lines_processed < max_lines:
                line = f.readline()
                if not line:  # EOF
                    break

                lines_processed += 1
                current_offset = f.tell()

                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # === PASUL 1: Extrage și cache-uiește tool_use events ===
                tool_uses = extract_tool_use_from_entry(data)
                for tu in tool_uses:
                    if tu['tool_use_id']:
                        tool_cache.add_tool_use(
                            session_id=session_id,
                            tool_use_id=tu['tool_use_id'],
                            tool_name=tu['tool_name'],
                            tool_input=tu['tool_input'],
                            timestamp=tu['timestamp']
                        )
                        stats['tool_uses_found'] += 1

                # === PASUL 2: Căutăm entries cu tool_result erori ===
                entry_type = data.get('type', '')
                if entry_type not in ('tool_result', 'tool_use_result', 'assistant', 'user', 'progress'):
                    continue

                # Extrage informații despre tool call
                tool_info = extract_tool_info_from_entry(data)
                if not tool_info:
                    continue

                tool_name = tool_info.get('tool_name', 'Unknown')
                exit_code = tool_info.get('exit_code')
                stderr = tool_info.get('stderr', '')
                command = tool_info.get('command', '')
                stdout = tool_info.get('stdout', '')
                timestamp = tool_info.get('timestamp', '')
                tool_use_id = tool_info.get('tool_use_id', '')

                # Verifică dacă e eroare reală
                if exit_code is None or exit_code == 0:
                    continue

                # === PASUL 3: Corelează cu tool_use pentru a obține tool_name ===
                resolved_tool_name = tool_name
                input_preview = command
                tool_seq = None

                # Strategie A: Corelare prin tool_use_id
                if tool_use_id:
                    cached_info = tool_cache.get_tool_info(session_id, tool_use_id)
                    if cached_info:
                        resolved_tool_name = cached_info.get('tool_name', tool_name)
                        input_preview = cached_info.get('input_preview', command)
                        tool_seq = cached_info.get('seq')
                        stats['resolved'] += 1
                    else:
                        # Strategie B: Fallback la recent tool
                        recent = tool_cache.get_recent_tool(session_id, timestamp)
                        if recent:
                            resolved_tool_name = recent.get('tool_name', tool_name)
                            input_preview = recent.get('input_preview', command)
                            tool_seq = recent.get('seq')
                            stats['resolved'] += 1
                        else:
                            stats['unknown'] += 1
                else:
                    # Fără tool_use_id - încercăm fallback
                    recent = tool_cache.get_recent_tool(session_id, timestamp)
                    if recent:
                        resolved_tool_name = recent.get('tool_name', tool_name)
                        input_preview = recent.get('input_preview', command)
                        tool_seq = recent.get('seq')
                        stats['resolved'] += 1
                    else:
                        stats['unknown'] += 1

                # Skip grep "no match" (exit 1 fără eroare reală)
                if is_grep_no_match(resolved_tool_name, exit_code, stderr):
                    log_debug(f"Skip grep no-match: exit={exit_code}")
                    continue

                # E eroare reală - adaugă la listă
                error_entry = {
                    'tool_name': resolved_tool_name,
                    'tool_use_id': tool_use_id,
                    'tool_input_preview': input_preview,
                    'tool_seq': tool_seq,
                    'command': command,
                    'exit_code': exit_code,
                    'stderr': stderr,
                    'stdout': stdout,
                    'timestamp': timestamp,
                }
                errors.append(error_entry)

    except Exception as e:
        log_error(f"Eroare citire transcript {transcript_path}: {e}")

    return errors, current_offset, lines_processed, stats


def extract_tool_info_from_entry(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrage informații despre tool dintr-un entry de transcript."""
    result = {}

    # Timestamp
    result['timestamp'] = data.get('timestamp', datetime.now().isoformat())

    # Format Claude Code: type="user" cu content[].type="tool_result"
    if data.get('type') == 'user':
        message = data.get('message', {})
        content_list = message.get('content', [])

        for item in content_list:
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'tool_result':
                result['tool_use_id'] = item.get('tool_use_id', '')

                # Verifică is_error flag
                is_error = item.get('is_error', False)
                tool_content = item.get('content', '')

                # Parse tool result
                if isinstance(tool_content, dict):
                    result['stdout'] = tool_content.get('stdout', '')
                    result['stderr'] = tool_content.get('stderr', '')
                    result['tool_name'] = 'Bash'

                    if tool_content.get('interrupted'):
                        result['exit_code'] = 130
                    elif is_error:
                        result['exit_code'] = 1
                    elif result['stderr']:
                        result['exit_code'] = 1
                    else:
                        result['exit_code'] = 0

                elif isinstance(tool_content, str):
                    result['stdout'] = ''
                    result['stderr'] = tool_content if is_error else ''
                    result['tool_name'] = 'Unknown'

                    if is_error:
                        result['exit_code'] = 1
                    else:
                        result['exit_code'] = 0

                # Folosește toolUseResult dacă există
                if data.get('toolUseResult'):
                    tool_use_result = data.get('toolUseResult', '')
                    if 'Error:' in tool_use_result or is_error:
                        result['stderr'] = tool_use_result
                        result['exit_code'] = 1

                if result.get('exit_code', 0) != 0:
                    return result

    # Format vechi / direct tool_result
    elif data.get('type') == 'tool_result':
        result['tool_use_id'] = data.get('tool_use_id', '')
        content = data.get('content', {})

        if isinstance(content, dict):
            result['stdout'] = content.get('stdout', '')
            result['stderr'] = content.get('stderr', '')
            result['tool_name'] = 'Bash'

            if content.get('interrupted'):
                result['exit_code'] = 130
            elif result['stderr']:
                result['exit_code'] = 1
            else:
                result['exit_code'] = 0
        elif isinstance(content, str):
            result['stdout'] = content
            result['exit_code'] = 0

        return result if result.get('exit_code') else None

    # Format progress cu agent_progress
    elif data.get('type') == 'progress':
        progress_data = data.get('data', {})
        message = progress_data.get('message', {})

        if message.get('type') == 'user':
            inner_message = message.get('message', {})
            content_list = inner_message.get('content', [])

            for item in content_list:
                if not isinstance(item, dict):
                    continue
                if item.get('type') == 'tool_result':
                    is_error = item.get('is_error', False)

                    if is_error:
                        result['tool_use_id'] = item.get('tool_use_id', '')
                        tool_content = item.get('content', '')
                        result['stderr'] = tool_content if isinstance(tool_content, str) else str(tool_content)
                        result['stdout'] = ''
                        result['exit_code'] = 1
                        result['tool_name'] = 'Unknown'
                        return result

    return None


def save_errors_to_db(errors: List[Dict[str, Any]], session_id: str, project_path: str) -> Tuple[int, int, int]:
    """
    Salvează erorile în DB cu deduplicare HARD prin INSERT OR IGNORE.

    Folosește UNIQUE INDEX pe fingerprint pentru dedup garantat atomic.

    Returns:
        (saved_count, resolved_count, unknown_count)
    """
    if not errors:
        return 0, 0, 0

    conn = get_db_connection()
    cursor = conn.cursor()
    saved_count = 0
    resolved_count = 0
    unknown_count = 0
    skipped_count = 0

    for error in errors:
        tool_name = error.get('tool_name', 'Unknown')
        tool_use_id = error.get('tool_use_id', '')
        tool_input_preview = error.get('tool_input_preview', '')
        tool_seq = error.get('tool_seq')
        command = error.get('command', '')
        exit_code = error.get('exit_code', 1)
        stderr = error.get('stderr', '')
        timestamp = error.get('timestamp', datetime.now().isoformat())

        # Calculează fingerprint
        stderr_first_line = stderr.split('\n')[0] if stderr else ''
        fingerprint = compute_fingerprint(tool_name, command or tool_input_preview, exit_code, stderr_first_line, session_id)

        # Construiește mesaj de eroare compact
        display_name = tool_name if tool_name != 'Unknown' else 'Tool'
        if command:
            error_message = f"{display_name} exit {exit_code}: {command[:100]}"
        elif tool_input_preview:
            error_message = f"{display_name} exit {exit_code}: {tool_input_preview[:100]}"
        else:
            error_message = f"{display_name} exit {exit_code}: {stderr_first_line[:200] if stderr_first_line else 'Unknown error'}"

        # INSERT OR IGNORE - dedup atomic garantat prin UNIQUE INDEX
        cursor.execute("""
            INSERT OR IGNORE INTO errors_solutions
            (error_type, error_message, stack_trace, session_id, project_path,
             created_at, resolved, source, fingerprint,
             tool_name_resolved, tool_use_id, tool_input_preview, tool_seq)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'tool_error',
            error_message[:5000],
            stderr[:10000] if stderr else None,
            session_id,
            project_path,
            timestamp,
            0,  # resolved = 0 (unresolved)
            'auto_reconciler',
            fingerprint,
            tool_name,
            tool_use_id,
            tool_input_preview[:500] if tool_input_preview else None,
            tool_seq
        ))

        # Verifică dacă s-a inserat (rowcount = 1) sau ignorat (rowcount = 0)
        if cursor.rowcount > 0:
            saved_count += 1
            if tool_name != 'Unknown':
                resolved_count += 1
            else:
                unknown_count += 1
            log_debug(f"Eroare salvată: {error_message[:50]}...")
        else:
            skipped_count += 1

    conn.commit()
    conn.close()

    if skipped_count > 0:
        log_debug(f"Skipped {skipped_count} duplicate errors (fingerprint exists)")

    return saved_count, resolved_count, unknown_count


def reconcile(session_id: Optional[str] = None, max_lines: int = MAX_LINES_PER_RUN,
              force_full_scan: bool = False) -> Dict[str, Any]:
    """
    Rulează reconciliere incrementală pe transcript cu drift detection.

    Args:
        session_id: ID-ul sesiunii (opțional, folosește curentă dacă lipsește)
        max_lines: Limită linii procesate
        force_full_scan: Forțează scanare de la 0 (reset)

    Returns:
        Dict cu rezultatul reconcilierii
    """
    import time
    start_time = time.time()

    result = {
        "status": "ok",
        "new_errors": 0,
        "lines_processed": 0,
        "last_offset": 0,
        "session_id": None,
        "transcript_path": None,
        "duration_ms": 0,
        "tool_names_resolved": 0,
        "tool_names_unknown": 0,
        "tool_uses_found": 0,
        "drift_detected": False,
        "drift_reason": None,
        "rewind_applied": False
    }

    # Asigură schema DB
    ensure_db_schema()

    # Determină session_id
    if not session_id:
        session_id = get_current_session_id()

    if not session_id:
        result["status"] = "no_session"
        return result

    result["session_id"] = session_id

    # Găsește transcript
    transcript_path = find_session_transcript(session_id)
    if not transcript_path or not transcript_path.exists():
        result["status"] = "no_transcript"
        return result

    result["transcript_path"] = str(transcript_path)

    # Încarcă starea
    state = load_reconciler_state()
    session_state = state.get("sessions", {}).get(session_id, {
        "last_offset": 0,
        "last_line": 0,
        "file_meta": {}
    })

    saved_offset = session_state.get("last_offset", 0)
    saved_file_meta = session_state.get("file_meta", {})

    # === DRIFT DETECTION ===
    current_file_meta = get_file_metadata(transcript_path)

    if force_full_scan:
        start_offset = 0
        result["rewind_applied"] = True
        result["drift_reason"] = "force_full_scan"
        log_debug("Force full scan requested, starting from offset 0")
    else:
        # Verifică drift
        drift_detected, drift_reason = detect_file_drift(
            current_file_meta, saved_file_meta, saved_offset
        )

        if drift_detected:
            result["drift_detected"] = True
            result["drift_reason"] = drift_reason

            # Calculează offset sigur pentru rewind
            start_offset = calculate_safe_rewind_offset(
                current_file_meta["file_size"], saved_offset, drift_reason
            )
            result["rewind_applied"] = True

            log_debug(f"Drift detected ({drift_reason}): offset {saved_offset} -> {start_offset}")
        else:
            start_offset = saved_offset

    # Creează cache pentru corelare
    tool_cache = ToolCorrelationCache()

    # Extrage erori din transcript
    errors, new_offset, lines_processed, stats = extract_tool_errors_from_transcript(
        transcript_path,
        start_offset=start_offset,
        max_lines=max_lines,
        tool_cache=tool_cache
    )

    result["lines_processed"] = lines_processed
    result["last_offset"] = new_offset
    result["tool_uses_found"] = stats['tool_uses_found']

    # Salvează erorile în DB
    project_path = os.getcwd()
    saved_count, resolved_count, unknown_count = save_errors_to_db(errors, session_id, project_path)
    result["new_errors"] = saved_count
    result["tool_names_resolved"] = resolved_count
    result["tool_names_unknown"] = unknown_count

    # Update starea cu file metadata
    if "sessions" not in state:
        state["sessions"] = {}

    state["sessions"][session_id] = {
        "last_offset": new_offset,
        "last_line": session_state.get("last_line", 0) + lines_processed,
        "file_meta": get_file_metadata(transcript_path),  # Actualizează metadata
        "last_scan_at": datetime.utcnow().isoformat() + "Z"
    }
    state["total_errors_found"] = state.get("total_errors_found", 0) + saved_count
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["last_run_at"] = datetime.utcnow().isoformat() + "Z"

    if force_full_scan:
        state["last_full_rescan_at"] = datetime.utcnow().isoformat() + "Z"

    save_reconciler_state(state)

    # Durata
    result["duration_ms"] = int((time.time() - start_time) * 1000)

    log_debug(f"Reconcile done: {saved_count} erori noi ({resolved_count} resolved, {unknown_count} unknown), "
              f"{lines_processed} linii, {result['duration_ms']}ms, drift={result['drift_detected']}")

    return result


def get_status() -> Dict[str, Any]:
    """Returnează statusul reconciler-ului cu statistici detaliate."""
    state = load_reconciler_state()

    # Adaugă statistici din DB
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE source = 'auto_reconciler'")
        auto_errors = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE resolved = 0")
        unresolved = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE source = 'auto_reconciler' AND tool_name_resolved IS NOT NULL AND tool_name_resolved != 'Unknown'")
        resolved_tool_names = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE source = 'auto_reconciler' AND (tool_name_resolved IS NULL OR tool_name_resolved = 'Unknown')")
        unknown_tool_names = cursor.fetchone()[0]

        conn.close()

        state["db_stats"] = {
            "auto_reconciler_errors": auto_errors,
            "unresolved_errors": unresolved,
            "resolved_tool_names": resolved_tool_names,
            "unknown_tool_names": unknown_tool_names
        }
    except Exception as e:
        state["db_stats"] = {"error": str(e)}

    return state


def show_recent_errors(limit: int = 20) -> List[Dict]:
    """Afișează ultimele erori cu tool_name și preview."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, tool_name_resolved, tool_input_preview,
               substr(error_message, 1, 100) as msg,
               created_at, session_id
        FROM errors_solutions
        WHERE source = 'auto_reconciler'
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    results = []
    for row in cursor.fetchall():
        results.append({
            'id': row[0],
            'tool_name': row[1] or 'Unknown',
            'input_preview': (row[2] or '')[:80],
            'message': row[3],
            'created_at': row[4],
            'session_id': row[5]
        })

    conn.close()
    return results


# === RECOVERY COMMANDS ===

def reset_reconciler(session_id: Optional[str] = None, all_sessions: bool = False) -> Dict[str, Any]:
    """
    Resetează starea reconciler-ului pentru rescan complet.

    Args:
        session_id: Reset doar această sesiune
        all_sessions: Reset toate sesiunile

    Returns:
        Dict cu rezultatul reset-ului
    """
    result = {
        "status": "ok",
        "sessions_reset": [],
        "message": ""
    }

    state = load_reconciler_state()

    if all_sessions:
        # Reset toate
        sessions_reset = list(state.get("sessions", {}).keys())
        state["sessions"] = {}
        state["last_full_rescan_at"] = None
        result["sessions_reset"] = sessions_reset
        result["message"] = f"Reset {len(sessions_reset)} sessions"
        log_debug(f"Reset ALL sessions: {len(sessions_reset)}")

    elif session_id:
        # Reset doar sesiunea specificată
        if session_id in state.get("sessions", {}):
            del state["sessions"][session_id]
            result["sessions_reset"] = [session_id]
            result["message"] = f"Reset session {session_id}"
            log_debug(f"Reset session: {session_id}")
        else:
            result["status"] = "not_found"
            result["message"] = f"Session {session_id} not found in state"

    else:
        # Reset sesiunea curentă
        current_session = get_current_session_id()
        if current_session and current_session in state.get("sessions", {}):
            del state["sessions"][current_session]
            result["sessions_reset"] = [current_session]
            result["message"] = f"Reset current session {current_session}"
            log_debug(f"Reset current session: {current_session}")
        else:
            result["status"] = "no_session"
            result["message"] = "No current session to reset"

    save_reconciler_state(state)
    return result


def verify_reconciler(session_id: Optional[str] = None, fix: bool = False) -> Dict[str, Any]:
    """
    Verifică integritatea stării reconciler-ului.

    Checks:
    1. State file valid și parsabil
    2. Offset-uri valide pentru fișierele existente
    3. File metadata coerență
    4. DB errors count vs state count

    Args:
        session_id: Verifică doar această sesiune (sau toate dacă None)
        fix: Repară problemele găsite

    Returns:
        Dict cu rezultatul verificării
    """
    result = {
        "status": "ok",
        "checks_passed": 0,
        "checks_failed": 0,
        "issues": [],
        "fixes_applied": []
    }

    # Check 1: State file parsabil
    try:
        state = load_reconciler_state()
        result["checks_passed"] += 1
    except Exception as e:
        result["checks_failed"] += 1
        result["issues"].append(f"State file corrupt: {e}")
        if fix:
            # Reset state complet
            save_reconciler_state({
                "version": STATE_VERSION,
                "sessions": {},
                "total_errors_found": 0,
                "total_runs": 0,
                "last_run_at": None,
                "last_full_rescan_at": None
            })
            result["fixes_applied"].append("Reset corrupt state file")
        return result

    # Check 2: Verifică fiecare sesiune
    sessions_to_check = [session_id] if session_id else list(state.get("sessions", {}).keys())

    for sid in sessions_to_check:
        session_state = state["sessions"].get(sid, {})
        transcript_path = find_session_transcript(sid)

        if not transcript_path or not transcript_path.exists():
            result["checks_failed"] += 1
            result["issues"].append(f"Session {sid[:16]}...: transcript not found")
            if fix:
                del state["sessions"][sid]
                result["fixes_applied"].append(f"Removed orphan session {sid[:16]}...")
            continue

        # Verifică offset valid
        offset = session_state.get("last_offset", 0)
        file_size = transcript_path.stat().st_size

        if offset > file_size:
            result["checks_failed"] += 1
            result["issues"].append(f"Session {sid[:16]}...: offset {offset} > file_size {file_size}")
            if fix:
                state["sessions"][sid]["last_offset"] = 0
                state["sessions"][sid]["file_meta"] = {}
                result["fixes_applied"].append(f"Reset offset for {sid[:16]}...")
        else:
            result["checks_passed"] += 1

        # Verifică file metadata
        saved_meta = session_state.get("file_meta", {})
        if saved_meta:
            current_meta = get_file_metadata(transcript_path)
            drift, reason = detect_file_drift(current_meta, saved_meta, offset)
            if drift:
                result["issues"].append(f"Session {sid[:16]}...: drift detected ({reason})")
                # Nu e neapărat o eroare, dar e informativ
            else:
                result["checks_passed"] += 1

    # Check 3: DB consistency
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE source = 'auto_reconciler'")
        db_count = cursor.fetchone()[0]

        state_count = state.get("total_errors_found", 0)

        if db_count != state_count:
            result["issues"].append(f"Count mismatch: DB has {db_count}, state says {state_count}")
            if fix:
                state["total_errors_found"] = db_count
                result["fixes_applied"].append(f"Updated state count: {state_count} -> {db_count}")
        else:
            result["checks_passed"] += 1

        conn.close()
    except Exception as e:
        result["checks_failed"] += 1
        result["issues"].append(f"DB check failed: {e}")

    # Check 4: UNIQUE index există
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_errors_fingerprint'")
        row = cursor.fetchone()
        if row and 'UNIQUE' in row[0].upper():
            result["checks_passed"] += 1
        else:
            result["checks_failed"] += 1
            result["issues"].append("UNIQUE index on fingerprint missing or not unique")
            if fix:
                ensure_db_schema()
                result["fixes_applied"].append("Re-created UNIQUE index on fingerprint")
        conn.close()
    except Exception as e:
        result["checks_failed"] += 1
        result["issues"].append(f"Index check failed: {e}")

    # Salvează fix-urile dacă au fost aplicate
    if fix and result["fixes_applied"]:
        save_reconciler_state(state)

    # Status final
    if result["checks_failed"] > 0:
        result["status"] = "issues_found"

    return result


# === MAIN ===
def main():
    """Entry point pentru CLI."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]

    if command == "reconcile":
        session_id = None
        force = False
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--session-id" and i + 1 < len(sys.argv):
                session_id = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] in ("--force", "-f"):
                force = True
                i += 1
            else:
                i += 1

        result = reconcile(session_id=session_id, force_full_scan=force)
        print(json.dumps(result, indent=2))

    elif command == "status":
        status = get_status()
        print(json.dumps(status, indent=2))

    elif command == "migrate":
        ensure_db_schema()
        print(json.dumps({"status": "ok", "message": "Schema migrated"}))

    elif command == "recent":
        limit = 20
        if len(sys.argv) >= 3:
            try:
                limit = int(sys.argv[2])
            except ValueError:
                pass

        errors = show_recent_errors(limit)
        for e in errors:
            print(f"[{e['id']}] {e['tool_name']}: {e['input_preview'][:50]}... | {e['message'][:40]}...")

    elif command == "reset":
        # Reset state pentru rescan
        session_id = None
        all_sessions = False
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--session-id" and i + 1 < len(sys.argv):
                session_id = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] in ("--all", "-a"):
                all_sessions = True
                i += 1
            else:
                i += 1

        result = reset_reconciler(session_id=session_id, all_sessions=all_sessions)
        print(json.dumps(result, indent=2))

    elif command == "verify":
        # Verifică integritatea
        session_id = None
        fix = False
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--session-id" and i + 1 < len(sys.argv):
                session_id = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] in ("--fix", "-f"):
                fix = True
                i += 1
            else:
                i += 1

        result = verify_reconciler(session_id=session_id, fix=fix)
        print(json.dumps(result, indent=2))

        # Exit code pentru CI/scripts
        if result["status"] != "ok":
            sys.exit(1)

    elif command in ("help", "--help", "-h"):
        print_usage()

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        print_usage()
        sys.exit(1)


def print_usage():
    """Afișează help pentru CLI."""
    print("""
Transcript Reconciler - Capturează erori din transcript

COMENZI:
  reconcile [--session-id ID] [--force]
      Rulează reconciliere incrementală pe transcript.
      --force/-f: Forțează scanare de la 0 (ignoră offset salvat)

  status
      Afișează starea reconciler-ului cu statistici.

  recent [LIMIT]
      Afișează ultimele N erori capturate (default 20).

  reset [--session-id ID] [--all]
      Resetează starea pentru rescan complet.
      --all/-a: Reset toate sesiunile

  verify [--session-id ID] [--fix]
      Verifică integritatea stării reconciler-ului.
      --fix/-f: Repară automat problemele găsite

  migrate
      Aplică migrările de schemă DB.

  help
      Afișează acest help.

EXEMPLE:
  # Reconciliere normală
  python3 transcript_reconciler.py reconcile

  # Forțează rescan complet
  python3 transcript_reconciler.py reconcile --force

  # Verifică și repară probleme
  python3 transcript_reconciler.py verify --fix

  # Reset pentru sesiunea curentă
  python3 transcript_reconciler.py reset

  # Reset toate sesiunile
  python3 transcript_reconciler.py reset --all
""")


if __name__ == "__main__":
    main()
