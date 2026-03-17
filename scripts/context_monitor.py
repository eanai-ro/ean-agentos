#!/usr/bin/env python3
"""
Context Monitor - Monitorizare nivel context și declanșare checkpoint-uri.

Modul de funcționare:
- Mod A (real): primește context_percentage din payload extern
- Mod B (fallback): estimează din DB (tokens ≈ len(text)/4)

Praguri:
- 70% → warn (log)
- 85% → checkpoint (salvare capsulă)
- 92% → preclear (pregătire /clear)

FAZA 1: Doar warn + checkpoint, fără /clear automat.

Usage:
    # Import ca library
    from context_monitor import check_context, estimate_context_from_db

    # CLI - estimare din DB
    python3 context_monitor.py --estimate --print-json

    # CLI - simulare prag specific
    python3 context_monitor.py --simulate-percent 86

    # CLI - mod real (când avem context_percentage)
    python3 context_monitor.py --context-percent 73
"""

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# === CONFIGURAȚIE ===
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"
MEMORY_DIR = GLOBAL_DB.parent
SESSION_FILE = MEMORY_DIR / ".current_session"
SCRIPTS_DIR = MEMORY_DIR / "scripts"

# Praguri (configurabile)
WARN_THRESHOLD = 70
CHECKPOINT_THRESHOLD = 85
PRECLEAR_THRESHOLD = 92

# Limit context (tokens) - Claude Code default
CONTEXT_LIMIT_TOKENS = 200_000

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class ContextStatus:
    """Rezultatul monitorizării contextului."""
    context_percentage: int
    tokens_estimated: int
    threshold: str  # 'ok', 'warn', 'checkpoint', 'preclear'
    should_warn: bool
    should_checkpoint: bool
    should_preclear: bool
    actions: list


def get_db_connection() -> sqlite3.Connection:
    """Conexiune la DB cu WAL mode."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_current_session_id() -> Optional[str]:
    """Citește ID-ul sesiunii curente."""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return None


def estimate_context_from_db(
    session_id: Optional[str] = None,
    context_limit: int = CONTEXT_LIMIT_TOKENS
) -> tuple[int, int]:
    """
    Estimează context percentage din DB.

    Calculează tokens din:
    - messages (content)
    - tool_calls (tool_input + tool_result)

    Returns:
        (tokens_estimated, context_percentage)
    """
    if session_id is None:
        session_id = get_current_session_id()

    if not session_id:
        logger.warning("Nu există sesiune curentă, returnez 0%")
        return 0, 0

    conn = get_db_connection()
    try:
        # Estimare tokeni din mesaje
        cur = conn.execute("""
            SELECT COALESCE(SUM(LENGTH(content)), 0) as total_chars
            FROM messages
            WHERE session_id = ?
        """, (session_id,))
        msg_chars = cur.fetchone()['total_chars']

        # Estimare tokeni din tool calls
        cur = conn.execute("""
            SELECT COALESCE(SUM(
                LENGTH(COALESCE(tool_input, '')) +
                LENGTH(COALESCE(tool_result, ''))
            ), 0) as total_chars
            FROM tool_calls
            WHERE session_id = ?
        """, (session_id,))
        tool_chars = cur.fetchone()['total_chars']

        total_chars = msg_chars + tool_chars
        # Estimare tokeni: ~4 caractere per token (aproximativ)
        tokens_estimated = total_chars // 4

        # Calculează procentul
        context_percentage = min(100, (tokens_estimated * 100) // context_limit)

        logger.debug(f"Session {session_id}: {total_chars} chars, ~{tokens_estimated} tokens, {context_percentage}%")

        return tokens_estimated, context_percentage

    finally:
        conn.close()


def determine_threshold(percentage: int) -> str:
    """Determină pragul atins."""
    if percentage >= PRECLEAR_THRESHOLD:
        return 'preclear'
    elif percentage >= CHECKPOINT_THRESHOLD:
        return 'checkpoint'
    elif percentage >= WARN_THRESHOLD:
        return 'warn'
    return 'ok'


def check_context(
    context_percentage: Optional[int] = None,
    tokens: Optional[int] = None,
    use_estimate: bool = False,
    session_id: Optional[str] = None
) -> ContextStatus:
    """
    Verifică nivelul contextului și determină acțiunile necesare.

    Args:
        context_percentage: Procentul real (dacă e disponibil)
        tokens: Numărul de tokeni (dacă e disponibil)
        use_estimate: Dacă true, estimează din DB
        session_id: ID-ul sesiunii (opțional)

    Returns:
        ContextStatus cu praguri și acțiuni
    """
    # Mod A: procentaj real dat
    if context_percentage is not None:
        tokens_est = tokens if tokens else (context_percentage * CONTEXT_LIMIT_TOKENS) // 100
    # Mod B: estimare din DB
    elif use_estimate:
        tokens_est, context_percentage = estimate_context_from_db(session_id)
    else:
        # Default: 0%
        tokens_est = 0
        context_percentage = 0

    threshold = determine_threshold(context_percentage)

    # Determină acțiuni
    should_warn = context_percentage >= WARN_THRESHOLD
    should_checkpoint = context_percentage >= CHECKPOINT_THRESHOLD
    should_preclear = context_percentage >= PRECLEAR_THRESHOLD

    actions = []
    if should_warn and threshold == 'warn':
        actions.append('log_warning')
    if should_checkpoint and threshold in ('checkpoint', 'preclear'):
        actions.append('create_checkpoint')
    if should_preclear:
        actions.append('prepare_preclear')

    return ContextStatus(
        context_percentage=context_percentage,
        tokens_estimated=tokens_est,
        threshold=threshold,
        should_warn=should_warn,
        should_checkpoint=should_checkpoint,
        should_preclear=should_preclear,
        actions=actions
    )


def create_checkpoint(reason: str = "auto", context_pct: int = 0) -> Optional[str]:
    """
    Creează checkpoint apelând capsule_builder.py.

    Returns:
        checkpoint_id dacă succes, None altfel
    """
    capsule_script = SCRIPTS_DIR / "capsule_builder.py"

    if not capsule_script.exists():
        logger.error(f"capsule_builder.py nu există: {capsule_script}")
        return None

    cmd = [
        sys.executable,
        str(capsule_script),
        "--reason", reason,
        "--context-pct", str(context_pct),
        "--json-output"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            # Extrage checkpoint_id din output (prima linie ar trebui să fie JSON)
            try:
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines:
                    if line.startswith('{'):
                        data = json.loads(line)
                        checkpoint_id = data.get('checkpoint_id')
                        logger.info(f"Checkpoint creat: {checkpoint_id}")
                        return checkpoint_id
            except json.JSONDecodeError:
                pass

            logger.info("Checkpoint creat (ID necunoscut)")
            return "unknown"
        else:
            logger.error(f"Eroare capsule_builder: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        logger.error("Timeout la crearea checkpoint-ului")
        return None
    except Exception as e:
        logger.error(f"Eroare la crearea checkpoint-ului: {e}")
        return None


def run_monitor(
    context_percentage: Optional[int] = None,
    use_estimate: bool = False,
    simulate_percent: Optional[int] = None,
    auto_checkpoint: bool = True,
    print_json: bool = False
) -> ContextStatus:
    """
    Rulează monitorul și execută acțiunile necesare.

    Args:
        context_percentage: Procentul real (Mod A)
        use_estimate: Estimare din DB (Mod B)
        simulate_percent: Simulare prag specific (pentru teste)
        auto_checkpoint: Creează checkpoint automat dacă necesar
        print_json: Afișează rezultatul ca JSON

    Returns:
        ContextStatus
    """
    # Simulare are prioritate (pentru teste)
    if simulate_percent is not None:
        context_percentage = simulate_percent
        use_estimate = False

    # Verifică contextul
    status = check_context(
        context_percentage=context_percentage,
        use_estimate=use_estimate
    )

    # Log la praguri
    if status.threshold == 'warn':
        logger.warning(f"Context la {status.context_percentage}% - se apropie de limită")
    elif status.threshold == 'checkpoint':
        logger.warning(f"Context la {status.context_percentage}% - se creează checkpoint")
    elif status.threshold == 'preclear':
        logger.warning(f"Context la {status.context_percentage}% - pregătire preclear!")

    # Acțiuni automate (FAZA 1: doar checkpoint)
    if auto_checkpoint and status.should_checkpoint:
        reason = "threshold_auto"
        if simulate_percent is not None:
            reason = "threshold_simulated"

        checkpoint_id = create_checkpoint(
            reason=reason,
            context_pct=status.context_percentage
        )

        if checkpoint_id:
            logger.info(f"Checkpoint creat automat: {checkpoint_id}")

    # Output JSON
    if print_json:
        print(json.dumps(asdict(status), indent=2))

    return status


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Context Monitor - monitorizare nivel context și checkpoint-uri automate"
    )

    parser.add_argument(
        '--context-percent', '-c',
        type=int,
        help='Context percentage real (Mod A)'
    )
    parser.add_argument(
        '--estimate', '-e',
        action='store_true',
        help='Estimează din DB (Mod B fallback)'
    )
    parser.add_argument(
        '--simulate-percent', '-s',
        type=int,
        help='Simulează un prag specific (pentru teste)'
    )
    parser.add_argument(
        '--no-auto-checkpoint',
        action='store_true',
        help='Dezactivează checkpoint automat'
    )
    parser.add_argument(
        '--print-json', '-j',
        action='store_true',
        help='Afișează rezultatul ca JSON'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Mod verbose (debug logging)'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validare: cel puțin o metodă de obținere a procentajului
    if args.context_percent is None and not args.estimate and args.simulate_percent is None:
        parser.print_help()
        print("\nEroare: Specifică --context-percent, --estimate sau --simulate-percent")
        sys.exit(1)

    status = run_monitor(
        context_percentage=args.context_percent,
        use_estimate=args.estimate,
        simulate_percent=args.simulate_percent,
        auto_checkpoint=not args.no_auto_checkpoint,
        print_json=args.print_json
    )

    # Exit code bazat pe prag
    if status.threshold == 'preclear':
        sys.exit(3)
    elif status.threshold == 'checkpoint':
        sys.exit(2)
    elif status.threshold == 'warn':
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
