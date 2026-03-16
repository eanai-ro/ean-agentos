#!/usr/bin/env python3
"""
COST TRACKER - Tracking costuri tokeni pentru sesiuni Claude.

Monitorizează și raportează costurile de utilizare pentru diferite modele.
Extrage informații din fișierele JSONL ale sesiunilor.

Model Pricing (per 1M tokens):
- Claude Opus 4.5: $15 input, $75 output
- Claude Sonnet 4: $3 input, $15 output
- GLM-4.7: $0.5 input, $1.5 output

Usage:
    python3 cost_tracker.py --today
    python3 cost_tracker.py --month
    python3 cost_tracker.py --session latest
    python3 cost_tracker.py --scan        # Scanează și salvează
"""

import sys
import os
import sqlite3
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Model pricing per 1M tokens (USD)
MODEL_PRICING = {
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0, "name": "Opus 4.5"},
    "claude-opus-4-5": {"input": 15.0, "output": 75.0, "name": "Opus 4.5"},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "name": "Sonnet 4"},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "name": "Sonnet 4"},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0, "name": "Sonnet 3.5"},
    "claude-3-opus": {"input": 15.0, "output": 75.0, "name": "Opus 3"},
    "glm-4.7": {"input": 0.5, "output": 1.5, "name": "GLM-4.7"},
    "glm-4.5-air": {"input": 0.1, "output": 0.3, "name": "GLM-4.5-Air"},
    # Default pentru modele necunoscute
    "default": {"input": 3.0, "output": 15.0, "name": "Unknown"}
}


def get_db_connection() -> sqlite3.Connection:
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def get_pricing(model: str) -> Dict[str, float]:
    """Returnează pricing pentru un model."""
    # Normalizează numele modelului
    model_lower = model.lower() if model else ""

    for key, pricing in MODEL_PRICING.items():
        if key in model_lower:
            return pricing

    return MODEL_PRICING["default"]


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculează costul pentru un apel."""
    pricing = get_pricing(model)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def extract_tokens_from_jsonl(jsonl_path: Path) -> Dict[str, Any]:
    """
    Extrage informații despre tokeni dintr-un fișier JSONL.

    Returns:
        Dict cu total_input, total_output, model, cost
    """
    result = {
        "total_input": 0,
        "total_output": 0,
        "models": defaultdict(lambda: {"input": 0, "output": 0}),
        "messages_count": 0,
        "cost_usd": 0.0
    }

    try:
        with open(jsonl_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)

                    # Caută usage info în diferite locații
                    usage = None
                    model = None

                    # Format 1: Direct în mesaj
                    if 'message' in data and isinstance(data['message'], dict):
                        usage = data['message'].get('usage')
                        model = data['message'].get('model')

                    # Format 2: La nivel root
                    if not usage and 'usage' in data:
                        usage = data['usage']
                    if not model and 'model' in data:
                        model = data['model']

                    # Procesează usage
                    if usage:
                        input_tokens = usage.get('input_tokens', 0)
                        output_tokens = usage.get('output_tokens', 0)

                        result["total_input"] += input_tokens
                        result["total_output"] += output_tokens
                        result["messages_count"] += 1

                        if model:
                            result["models"][model]["input"] += input_tokens
                            result["models"][model]["output"] += output_tokens

                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"⚠️ Eroare citire {jsonl_path}: {e}")

    # Calculează cost total
    for model, tokens in result["models"].items():
        result["cost_usd"] += calculate_cost(model, tokens["input"], tokens["output"])

    # Dacă nu avem model breakdown dar avem tokeni, folosim default
    if result["total_input"] > 0 and not result["models"]:
        result["cost_usd"] = calculate_cost("default", result["total_input"], result["total_output"])

    return result


def scan_session_costs(
    session_id: Optional[str] = None,
    date_filter: Optional[str] = None,
    save_to_db: bool = True
) -> List[Dict[str, Any]]:
    """
    Scanează fișierele JSONL și extrage costuri.

    Args:
        session_id: Filtrează după session (sau 'latest')
        date_filter: Filtrează după dată (YYYY-MM-DD)
        save_to_db: Salvează în DB

    Returns:
        Lista de rezultate per sesiune
    """
    results = []

    # Găsește fișierele JSONL
    jsonl_files = list(PROJECTS_DIR.glob("*/*.jsonl"))

    if session_id == 'latest':
        # Sortează după modificare și ia ultimul
        jsonl_files = sorted(jsonl_files, key=lambda f: f.stat().st_mtime, reverse=True)
        jsonl_files = jsonl_files[:1]
    elif session_id:
        # Filtrează după session_id
        jsonl_files = [f for f in jsonl_files if session_id in f.stem]

    if date_filter:
        # Filtrează după dată
        target_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        jsonl_files = [
            f for f in jsonl_files
            if datetime.fromtimestamp(f.stat().st_mtime).date() == target_date
        ]

    for jsonl_path in jsonl_files:
        token_info = extract_tokens_from_jsonl(jsonl_path)

        if token_info["total_input"] > 0 or token_info["total_output"] > 0:
            result = {
                "file": str(jsonl_path),
                "session_id": jsonl_path.stem,
                "project": jsonl_path.parent.name,
                "modified_at": datetime.fromtimestamp(jsonl_path.stat().st_mtime).isoformat(),
                **token_info
            }
            results.append(result)

            # Salvează în DB
            if save_to_db:
                save_cost_to_db(result)

    return results


def save_cost_to_db(result: Dict[str, Any]):
    """Salvează costul în baza de date."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determină modelul principal
    main_model = "unknown"
    if result.get("models"):
        main_model = max(result["models"].keys(),
                         key=lambda m: result["models"][m]["input"] + result["models"][m]["output"])

    # Verifică dacă există deja
    cursor.execute("""
        SELECT id FROM token_costs
        WHERE session_id = ? AND model = ?
        LIMIT 1
    """, (result["session_id"], main_model))

    if cursor.fetchone():
        # Update
        cursor.execute("""
            UPDATE token_costs
            SET input_tokens = ?, output_tokens = ?, cost_usd = ?, timestamp = ?
            WHERE session_id = ? AND model = ?
        """, (
            result["total_input"],
            result["total_output"],
            result["cost_usd"],
            result["modified_at"],
            result["session_id"],
            main_model
        ))
    else:
        # Insert
        cursor.execute("""
            INSERT INTO token_costs
            (session_id, model, input_tokens, output_tokens, cost_usd, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            result["session_id"],
            main_model,
            result["total_input"],
            result["total_output"],
            result["cost_usd"],
            result["modified_at"]
        ))

    conn.commit()
    conn.close()


def get_daily_summary(date: str = None) -> Dict[str, Any]:
    """Obține sumar pentru o zi."""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cost_usd) as total_cost,
            COUNT(*) as sessions_count
        FROM token_costs
        WHERE DATE(timestamp) = ?
    """, (date,))

    row = cursor.fetchone()

    # Model breakdown
    cursor.execute("""
        SELECT model,
               SUM(input_tokens) as input,
               SUM(output_tokens) as output,
               SUM(cost_usd) as cost
        FROM token_costs
        WHERE DATE(timestamp) = ?
        GROUP BY model
    """, (date,))

    models = {}
    for r in cursor.fetchall():
        models[r['model']] = {
            'input': r['input'],
            'output': r['output'],
            'cost': r['cost']
        }

    conn.close()

    return {
        'date': date,
        'total_input': row['total_input'] or 0,
        'total_output': row['total_output'] or 0,
        'total_cost': row['total_cost'] or 0.0,
        'sessions_count': row['sessions_count'] or 0,
        'models': models
    }


def get_monthly_summary(year: int = None, month: int = None) -> Dict[str, Any]:
    """Obține sumar lunar."""
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month

    month_str = f"{year}-{month:02d}"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cost_usd) as total_cost,
            COUNT(DISTINCT DATE(timestamp)) as days_active,
            COUNT(*) as sessions_count
        FROM token_costs
        WHERE strftime('%Y-%m', timestamp) = ?
    """, (month_str,))

    row = cursor.fetchone()

    # Per day breakdown
    cursor.execute("""
        SELECT DATE(timestamp) as date,
               SUM(input_tokens) as input,
               SUM(output_tokens) as output,
               SUM(cost_usd) as cost
        FROM token_costs
        WHERE strftime('%Y-%m', timestamp) = ?
        GROUP BY DATE(timestamp)
        ORDER BY date
    """, (month_str,))

    daily = []
    for r in cursor.fetchall():
        daily.append({
            'date': r['date'],
            'input': r['input'],
            'output': r['output'],
            'cost': r['cost']
        })

    conn.close()

    return {
        'month': month_str,
        'total_input': row['total_input'] or 0,
        'total_output': row['total_output'] or 0,
        'total_cost': row['total_cost'] or 0.0,
        'days_active': row['days_active'] or 0,
        'sessions_count': row['sessions_count'] or 0,
        'daily': daily
    }


def format_tokens(tokens: int) -> str:
    """Formatează numărul de tokeni."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.2f}M"
    elif tokens >= 1_000:
        return f"{tokens / 1_000:.1f}K"
    return str(tokens)


def format_cost(cost: float) -> str:
    """Formatează costul."""
    if cost < 0.01:
        return f"${cost:.4f}"
    elif cost < 1:
        return f"${cost:.3f}"
    return f"${cost:.2f}"


def print_daily_report(summary: Dict):
    """Afișează raport zilnic."""
    print("\n" + "="*60)
    print(f"  RAPORT COSTURI - {summary['date']}")
    print("="*60)

    print(f"\n  Sesiuni: {summary['sessions_count']}")
    print(f"  Input tokens: {format_tokens(summary['total_input'])}")
    print(f"  Output tokens: {format_tokens(summary['total_output'])}")
    print(f"  Cost total: {format_cost(summary['total_cost'])}")

    if summary.get('models'):
        print("\n  Per model:")
        for model, data in summary['models'].items():
            pricing = get_pricing(model)
            print(f"    {pricing['name']}:")
            print(f"      Input: {format_tokens(data['input'])}, Output: {format_tokens(data['output'])}")
            print(f"      Cost: {format_cost(data['cost'])}")

    print("\n" + "="*60 + "\n")


def print_monthly_report(summary: Dict):
    """Afișează raport lunar."""
    print("\n" + "="*60)
    print(f"  RAPORT LUNAR - {summary['month']}")
    print("="*60)

    print(f"\n  Zile active: {summary['days_active']}")
    print(f"  Sesiuni totale: {summary['sessions_count']}")
    print(f"  Input tokens: {format_tokens(summary['total_input'])}")
    print(f"  Output tokens: {format_tokens(summary['total_output'])}")
    print(f"  Cost total: {format_cost(summary['total_cost'])}")

    if summary.get('daily'):
        print("\n  Per zi:")
        for day in summary['daily'][-10:]:  # Ultimele 10 zile
            print(f"    {day['date']}: {format_tokens(day['input'] + day['output'])} tok, {format_cost(day['cost'])}")

    # Proiecție pentru luna întreagă
    if summary['days_active'] > 0:
        avg_per_day = summary['total_cost'] / summary['days_active']
        days_in_month = 30
        projected = avg_per_day * days_in_month
        print(f"\n  Proiecție lunară: {format_cost(projected)} (bazat pe media de {format_cost(avg_per_day)}/zi)")

    print("\n" + "="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Tracking costuri tokeni pentru Claude"
    )
    parser.add_argument("--today", "-t", action="store_true",
                        help="Raport pentru azi")
    parser.add_argument("--date", "-d", type=str,
                        help="Raport pentru o dată specifică (YYYY-MM-DD)")
    parser.add_argument("--month", "-m", action="store_true",
                        help="Raport lunar")
    parser.add_argument("--year", type=int,
                        help="Anul pentru raport lunar")
    parser.add_argument("--month-num", type=int,
                        help="Luna pentru raport lunar (1-12)")
    parser.add_argument("--scan", "-s", action="store_true",
                        help="Scanează fișierele JSONL și salvează")
    parser.add_argument("--session", type=str,
                        help="Scanează sesiune specifică (sau 'latest')")
    parser.add_argument("--no-save", action="store_true",
                        help="Nu salva în DB")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output JSON")

    args = parser.parse_args()

    # Scanare
    if args.scan or args.session:
        date_filter = args.date if not args.session else None
        results = scan_session_costs(args.session, date_filter, not args.no_save)

        if args.json:
            # Convert defaultdict to regular dict for JSON
            for r in results:
                if 'models' in r:
                    r['models'] = dict(r['models'])
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"\n📊 Scanate {len(results)} sesiuni\n")
            for r in results:
                print(f"  {r['session_id'][:30]}...")
                print(f"    Input: {format_tokens(r['total_input'])}, Output: {format_tokens(r['total_output'])}")
                print(f"    Cost: {format_cost(r['cost_usd'])}")
        return

    # Raport zilnic
    if args.today or args.date:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        summary = get_daily_summary(date)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print_daily_report(summary)
        return

    # Raport lunar
    if args.month:
        summary = get_monthly_summary(args.year, args.month_num)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print_monthly_report(summary)
        return

    # Help
    parser.print_help()
    print("\nExemple:")
    print("  python3 cost_tracker.py --scan           # Scanează toate sesiunile")
    print("  python3 cost_tracker.py --session latest # Ultima sesiune")
    print("  python3 cost_tracker.py --today          # Raport azi")
    print("  python3 cost_tracker.py --month          # Raport lunar")


if __name__ == "__main__":
    main()
