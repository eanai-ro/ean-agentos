#!/usr/bin/env python3
"""
Fact Promoter - Promovare automată a facts importante.

Scorul de importanță crește dacă:
- fact-ul apare frecvent în context (simulate: decision/resolution text match)
- fact-ul e folosit în rezolvări
- fact-ul e vechi dar încă activ (longevitate)

Comenzi:
    fact_promoter.py scan             Scanează și calculează scoruri
    fact_promoter.py list             Listează candidați pentru promovare
    fact_promoter.py promote          Promovează automat (pin facts cu scor mare)
"""

import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import get_db, truncate, get_current_project_path

PROMOTE_THRESHOLD = 5  # Scor minim pentru auto-promote


def _score_fact(fact_row, cursor):
    """Calculează scorul de importanță al unui fact."""
    score = 0
    fact_text = (fact_row["fact"] or "").lower()
    fact_id = fact_row["id"]

    # 1. Longevitate: >30 zile activ = +2, >90 = +3
    try:
        created = datetime.fromisoformat(fact_row["created_at"].replace("Z", "+00:00"))
        age_days = (datetime.now() - created.replace(tzinfo=None)).days
        if age_days > 90:
            score += 3
        elif age_days > 30:
            score += 2
        elif age_days > 7:
            score += 1
    except (ValueError, TypeError, AttributeError):
        pass

    # 2. Deja pinned = +0 (nu re-promovăm)
    if fact_row["is_pinned"]:
        return 0  # Skip already pinned

    # 3. Referințe în decisions (title sau description conține cuvinte din fact)
    words = [w for w in fact_text.split() if len(w) > 4][:5]
    for word in words:
        cursor.execute(
            "SELECT COUNT(*) FROM decisions WHERE status='active' AND (lower(title) LIKE ? OR lower(description) LIKE ?)",
            (f"%{word}%", f"%{word}%"))
        refs = cursor.fetchone()[0]
        if refs > 0:
            score += min(refs, 3)

    # 4. Referințe în error_resolutions
    for word in words:
        cursor.execute(
            "SELECT COUNT(*) FROM error_resolutions WHERE lower(resolution) LIKE ? OR lower(error_summary) LIKE ?",
            (f"%{word}%", f"%{word}%"))
        refs = cursor.fetchone()[0]
        if refs > 0:
            score += min(refs, 3)

    # 5. Tip fact bonus
    if fact_row["fact_type"] == "gotcha":
        score += 2  # gotcha facts sunt mai valoroase
    elif fact_row["fact_type"] == "convention":
        score += 1

    # 6. Confidence bonus
    try:
        confidence = fact_row["confidence"]
    except (KeyError, IndexError):
        confidence = None
    if confidence == "confirmed":
        score += 2
    elif confidence == "high":
        score += 1

    return score


def cmd_scan(args):
    """Scanează facts și calculează scoruri."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM learned_facts WHERE is_active = 1")
    facts = cursor.fetchall()

    results = []
    for fact in facts:
        score = _score_fact(fact, cursor)
        results.append({"id": fact["id"], "fact": fact["fact"], "score": score,
                        "is_pinned": fact["is_pinned"], "fact_type": fact["fact_type"]})

    conn.close()

    # Sort by score desc
    results.sort(key=lambda x: x["score"], reverse=True)

    candidates = [r for r in results if r["score"] >= PROMOTE_THRESHOLD]

    print(f"\n📊 Fact Scoring: {len(facts)} facts scanate")
    print(f"   Candidați promovare (scor >= {PROMOTE_THRESHOLD}): {len(candidates)}\n")

    if results:
        print(f"{'ID':>4} {'Score':>5} {'Pin':>3} {'Type':>12} {'Fact':<45}")
        print("-" * 75)
        for r in results[:15]:
            pin = "📌" if r["is_pinned"] else ""
            promote = " ⬆" if r["score"] >= PROMOTE_THRESHOLD else ""
            print(f"{r['id']:>4} {r['score']:>5} {pin:>3} {r['fact_type']:>12} {truncate(r['fact'], 45)}{promote}")

    return results


def cmd_promote(args):
    """Promovează automat facts cu scor mare → pin."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM learned_facts WHERE is_active = 1 AND is_pinned = 0")
    facts = cursor.fetchall()

    promoted = 0
    for fact in facts:
        score = _score_fact(fact, cursor)
        if score >= PROMOTE_THRESHOLD:
            cursor.execute("UPDATE learned_facts SET is_pinned = 1, updated_at = ? WHERE id = ?",
                           (datetime.now().isoformat(), fact["id"]))
            promoted += 1
            print(f"  📌 #{fact['id']} (scor {score}): {truncate(fact['fact'], 50)}")

    conn.commit()
    conn.close()

    if promoted:
        print(f"\n✅ {promoted} facts promovate (pinned)")
    else:
        print("  (niciun fact atinge pragul de promovare)")


def cmd_list(args):
    """Listează candidați pentru promovare."""
    results = cmd_scan(args)
    candidates = [r for r in results if r["score"] >= PROMOTE_THRESHOLD]
    if candidates:
        print(f"\n  Rulează `mem promote` pentru a pina automat {len(candidates)} facts.")


def main():
    parser = argparse.ArgumentParser(description="Fact Promoter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scan", help="Scanează și calculează scoruri")
    sub.add_parser("list", help="Listează candidați promovare")
    sub.add_parser("promote", help="Promovează automat")

    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "promote":
        cmd_promote(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
