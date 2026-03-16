#!/usr/bin/env python3
"""
Context Strategy - Selecție automată a modului de context optim.

Decide automat între: survival, compact, full, delta
în funcție de: intent, snapshot, trigger, dimensiune estimată.

Utilizare:
    # Ca modul
    from context_strategy import choose_context_mode
    result = choose_context_mode(trigger="session_start")

    # Ca CLI
    python3 context_strategy.py              # Afișează strategia curentă
    python3 context_strategy.py --trigger session_start
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import (
    get_db, get_current_model, get_current_project_path, get_current_intent,
    SNAPSHOT_FILE,
)


# === STRATEGY LOG ===

STRATEGY_LOG_FILE = Path(__file__).parent.parent / ".context_strategy.log"
MAX_LOG_LINES = 50


def _log_strategy(result: dict):
    """Loghează decizia de strategie în .context_strategy.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"[{ts}] mode={result['mode']} trigger={result['trigger']} "
        f"intent={result.get('intent') or '-'} "
        f"snapshot={'valid' if result.get('snapshot_valid') else 'none'} "
        f"reason={result['reason']}"
    )
    try:
        lines = []
        if STRATEGY_LOG_FILE.exists():
            lines = STRATEGY_LOG_FILE.read_text().strip().split("\n")
        lines.append(entry)
        # Keep only last N lines
        if len(lines) > MAX_LOG_LINES:
            lines = lines[-MAX_LOG_LINES:]
        STRATEGY_LOG_FILE.write_text("\n".join(lines) + "\n")
    except OSError:
        pass


# === SNAPSHOT CHECK ===

SNAPSHOT_TTL_SECONDS = 600  # 10 minute


def _snapshot_is_valid() -> bool:
    """Verifică dacă snapshot-ul curent e valid (TTL + intent/model match)."""
    if not SNAPSHOT_FILE.exists():
        return False
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        gen_at = data.get("meta", {}).get("generated_at")
        if not gen_at:
            return False
        dt = datetime.fromisoformat(gen_at)
        age = (datetime.now() - dt).total_seconds()
        if age > SNAPSHOT_TTL_SECONDS:
            return False
        # Check intent match
        current_intent = get_current_intent()
        if data.get("meta", {}).get("intent") != current_intent:
            return False
        # Check model match
        current_model, _ = get_current_model()
        if data.get("model", {}).get("model_id") != current_model:
            return False
        return True
    except (json.JSONDecodeError, OSError, ValueError):
        return False


def _snapshot_age_seconds() -> float:
    """Returnează vârsta snapshot-ului în secunde, sau -1 dacă nu există."""
    if not SNAPSHOT_FILE.exists():
        return -1
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        gen_at = data.get("meta", {}).get("generated_at")
        if not gen_at:
            return -1
        dt = datetime.fromisoformat(gen_at)
        return (datetime.now() - dt).total_seconds()
    except (json.JSONDecodeError, OSError, ValueError):
        return -1


# === DATA SIZE ESTIMATE ===

def _estimate_data_volume(project_path: str = None) -> dict:
    """Estimare rapidă a volumului de date relevante."""
    project_path = project_path or get_current_project_path()
    counts = {"decisions": 0, "facts": 0, "goals": 0, "tasks": 0, "resolutions": 0}
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM decisions WHERE status='active'")
        counts["decisions"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM learned_facts WHERE is_active=1")
        counts["facts"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM goals WHERE status='active'")
        counts["goals"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('in_progress','blocked','todo')")
        counts["tasks"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM error_resolutions")
        counts["resolutions"] = cursor.fetchone()[0]
        conn.close()
    except Exception:
        pass
    counts["total"] = sum(counts.values())
    return counts


def _estimate_tokens_for_mode(mode: str, volume: dict) -> int:
    """Estimare grosieră tokeni per mod, bazată pe volumul de date."""
    # Tokeni per item estimați
    tpi = {"survival": 15, "compact": 25, "full": 45}
    per_item = tpi.get(mode, 25)

    # Base overhead (model + profile + headers)
    base = {"survival": 40, "compact": 80, "full": 120}.get(mode, 80)

    # Limits per mode
    limits = {
        "survival": {"decisions": 3, "facts": 3, "goals": 2, "tasks": 3, "resolutions": 2},
        "compact": {"decisions": 5, "facts": 6, "goals": 4, "tasks": 6, "resolutions": 4},
        "full": {"decisions": 10, "facts": 15, "goals": 10, "tasks": 15, "resolutions": 10},
    }
    mode_limits = limits.get(mode, limits["compact"])

    total = base
    for key, limit in mode_limits.items():
        actual = min(volume.get(key, 0), limit)
        total += actual * per_item

    return total


# === STRATEGY ENGINE ===

# Intents care cer full mode
FULL_MODE_INTENTS = ("deploy",)
# Intents care cer compact mode
COMPACT_MODE_INTENTS = ("debugging", "feature", "refactor", "review", "docs", "explore")


def choose_context_mode(
    trigger: str = "manual",
    project_path: str = None,
    budget: int = None,
) -> dict:
    """Alege modul de context optim.

    Args:
        trigger: Ce a declanșat generarea
            - "session_start": început sesiune → survival
            - "session_refresh": refresh mid-session → delta dacă snapshot valid
            - "post_compact": după auto-compact → compact
            - "manual": utilizatorul a cerut explicit → compact
        project_path: Path proiect (default: curent)
        budget: Budget explicit (overrides mode default budget)

    Returns:
        dict cu: mode, trigger, intent, reason, estimated_tokens, snapshot_valid, budget
    """
    intent = get_current_intent()
    snapshot_valid = _snapshot_is_valid()
    snapshot_age = _snapshot_age_seconds()
    volume = _estimate_data_volume(project_path)

    result = {
        "trigger": trigger,
        "intent": intent,
        "snapshot_valid": snapshot_valid,
        "snapshot_age_s": round(snapshot_age, 1) if snapshot_age >= 0 else None,
        "data_volume": volume,
    }

    # === DECISION TREE ===

    # 1. Session start → survival (rapid, minim tokeni)
    if trigger == "session_start":
        mode = "survival"
        reason = "session_start: orientare rapidă"
        # Excepție: deploy intent → full chiar și la start
        if intent in FULL_MODE_INTENTS:
            mode = "full"
            reason = f"session_start + intent={intent}: context complet necesar"

    # 2. Session refresh cu snapshot valid → delta
    elif trigger == "session_refresh":
        if snapshot_valid:
            mode = "delta"
            reason = f"snapshot valid ({snapshot_age:.0f}s): doar schimbări"
        else:
            mode = "compact"
            reason = "snapshot invalid/lipsă: regenerare compact"

    # 3. Post-compact → compact (context pierdut, refacere)
    elif trigger == "post_compact":
        mode = "compact"
        reason = "post_compact: refacere context pierdut"
        if intent in FULL_MODE_INTENTS:
            mode = "full"
            reason = f"post_compact + intent={intent}: context complet"

    # 4. Manual/default → bazat pe intent
    else:
        if intent in FULL_MODE_INTENTS:
            mode = "full"
            reason = f"intent={intent}: context complet recomandat"
        elif intent in COMPACT_MODE_INTENTS:
            mode = "compact"
            reason = f"intent={intent}: compact optimizat"
        elif snapshot_valid and snapshot_age < 120:
            # Snapshot foarte recent (<2 min) → delta
            mode = "delta"
            reason = f"snapshot recent ({snapshot_age:.0f}s): delta eficient"
        else:
            mode = "compact"
            reason = "default: compact bilanț optim"

    # === BUDGET CHECK & DOWNGRADE ===

    estimated = _estimate_tokens_for_mode(mode, volume)
    effective_budget = budget or {"survival": 300, "compact": 700, "full": 99999, "delta": 500}.get(mode, 700)

    if mode != "delta" and estimated > effective_budget:
        # Downgrade
        if mode == "full":
            mode = "compact"
            estimated = _estimate_tokens_for_mode("compact", volume)
            reason += " → downgrade full→compact (budget)"
        if mode == "compact" and estimated > effective_budget:
            mode = "survival"
            estimated = _estimate_tokens_for_mode("survival", volume)
            reason += " → downgrade compact→survival (budget)"

    result["mode"] = mode
    result["reason"] = reason
    result["estimated_tokens"] = estimated
    result["budget"] = effective_budget

    # Log
    _log_strategy(result)

    return result


# === CLI ===

def print_strategy(result: dict):
    """Afișează strategia curentă."""
    print(f"\n{'='*50}")
    print(f"  CONTEXT STRATEGY")
    print(f"{'='*50}\n")

    print(f"  Mode recomandat:  {result['mode'].upper()}")
    print(f"  Trigger:          {result['trigger']}")
    print(f"  Intent:           {result.get('intent') or '(nesetat)'}")
    print(f"  Snapshot:         {'valid' if result.get('snapshot_valid') else 'invalid/lipsă'}", end="")
    if result.get("snapshot_age_s") is not None and result["snapshot_age_s"] >= 0:
        print(f" ({result['snapshot_age_s']:.0f}s)")
    else:
        print()
    print(f"  Tokeni estimați:  ~{result['estimated_tokens']}")
    print(f"  Budget:           {result['budget']}")
    print(f"  Motiv:            {result['reason']}")

    vol = result.get("data_volume", {})
    if vol:
        print(f"\n  Date disponibile:")
        print(f"    Decisions: {vol.get('decisions', 0)}")
        print(f"    Facts:     {vol.get('facts', 0)}")
        print(f"    Goals:     {vol.get('goals', 0)}")
        print(f"    Tasks:     {vol.get('tasks', 0)}")
        print(f"    Resolutions: {vol.get('resolutions', 0)}")
        print(f"    Total:     {vol.get('total', 0)}")

    print(f"\n{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Context Strategy - Selecție automată mod context")
    parser.add_argument("--trigger", "-t", default="manual",
                        choices=["session_start", "session_refresh", "post_compact", "manual"],
                        help="Ce a declanșat generarea")
    parser.add_argument("--project", "-p", help="Path proiect")
    parser.add_argument("--budget", "-b", type=int, help="Budget explicit")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    result = choose_context_mode(
        trigger=args.trigger,
        project_path=args.project,
        budget=args.budget,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_strategy(result)


if __name__ == "__main__":
    main()
