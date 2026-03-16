#!/usr/bin/env python3
"""
Solution Index — problem → solution lookup cu confidence scoring.

`mem suggest "error message"` returnează soluții ordonate după scor.

Caută în: error_resolutions, errors_solutions, error_patterns.
Scorul final = match_quality * confidence_score (din memory_scoring).

CLI: solution_index.py suggest "query" [--limit N] [--json]
     solution_index.py rebuild [--json]
"""

import sys
import json
import re
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from v2_common import get_db, format_timestamp, truncate


# ============================================================
# TEXT MATCHING
# ============================================================

def _normalize_error(text: str) -> str:
    """Normalize error text for matching."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"line \d+", "line N", text)
    text = re.sub(r"/[^\s]+/", "/.../", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", text)
    text = re.sub(r"\d{2}:\d{2}:\d{2}", "TIME", text)
    text = re.sub(r"'[^']*'", "'X'", text)
    text = re.sub(r'"[^"]*"', '"X"', text)
    text = re.sub(r"\b0x[0-9a-f]+\b", "ADDR", text)
    return text[:300]


def _fingerprint(text: str) -> str:
    """Generate fingerprint for matching."""
    normalized = _normalize_error(text)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _word_overlap(text1: str, text2: str) -> float:
    """Word-level Jaccard similarity. Returns 0.0-1.0."""
    if not text1 or not text2:
        return 0.0
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    # Remove very common words
    stop = {"the", "a", "an", "is", "in", "to", "for", "of", "and", "or", "not", "no", "error", "at"}
    words1 -= stop
    words2 -= stop
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _match_quality(query: str, candidate_text: str) -> float:
    """Calculate match quality 0.0-1.0 between query and candidate."""
    if not query or not candidate_text:
        return 0.0

    q_lower = query.lower()
    c_lower = candidate_text.lower()

    # Exact substring match = highest
    if q_lower in c_lower or c_lower in q_lower:
        return 1.0

    # Normalized match
    q_norm = _normalize_error(query)
    c_norm = _normalize_error(candidate_text)
    if q_norm == c_norm:
        return 0.95

    # Fingerprint match
    if _fingerprint(query) == _fingerprint(candidate_text):
        return 0.9

    # Word overlap
    overlap = _word_overlap(query, candidate_text)
    return overlap


# ============================================================
# CONFIDENCE SCORING (lightweight, inline)
# ============================================================

def _resolution_confidence(res: Dict) -> float:
    """Quick confidence score for a resolution (0-100)."""
    score = 0.0
    if res.get("worked"):
        score += 40
    reuse = res.get("reuse_count", 0) or 0
    score += min(reuse * 8, 24)
    if res.get("is_global"):
        score += 15
    if res.get("resolution_code"):
        score += 10
    # Recency bonus
    created = res.get("created_at", "")
    if created:
        try:
            from datetime import timedelta
            age = datetime.now() - datetime.fromisoformat(created.replace("Z", "+00:00"))
            if age < timedelta(days=7):
                score += 11
            elif age < timedelta(days=30):
                score += 7
            elif age < timedelta(days=90):
                score += 3
        except (ValueError, TypeError):
            pass
    return min(score, 100)


def _raw_error_confidence(err: Dict) -> float:
    """Quick confidence score for a raw error solution."""
    score = 0.0
    if err.get("solution_worked"):
        score += 40
    if err.get("solution"):
        score += 20
    if err.get("resolved_at"):
        score += 15
    # Attempts inversely proportional
    attempts = err.get("attempts", 1) or 1
    if attempts == 1:
        score += 10
    elif attempts <= 3:
        score += 5
    return min(score, 100)


def _pattern_confidence(pat: Dict) -> float:
    """Quick confidence for error pattern."""
    score = 0.0
    count = pat.get("count", 1) or 1
    score += min(count * 10, 40)
    if pat.get("auto_promoted"):
        score += 20
    if pat.get("solution"):
        score += 25
    return min(score, 100)


# ============================================================
# SUGGEST
# ============================================================

def suggest(query: str, limit: int = 10) -> List[Dict]:
    """Find solutions for an error query, ordered by combined score."""
    conn = get_db()
    cursor = conn.cursor()
    candidates = []

    # 1. Search error_resolutions (V2 structured)
    cursor.execute("""
        SELECT id, error_summary, resolution, resolution_code, resolution_type,
               worked, reuse_count, agent_name, model_used, created_at,
               is_global, promoted_from_agent
        FROM error_resolutions
        ORDER BY worked DESC, reuse_count DESC
        LIMIT 200
    """)
    for row in cursor.fetchall():
        d = dict(row)
        match = _match_quality(query, d.get("error_summary", ""))
        if match < 0.15:
            continue
        confidence = _resolution_confidence(d)
        combined = round(match * 0.4 + confidence * 0.6, 1)
        candidates.append({
            "source": "error_resolutions",
            "id": d["id"],
            "problem": truncate(d.get("error_summary", ""), 80),
            "solution": d.get("resolution", ""),
            "solution_code": d.get("resolution_code"),
            "resolution_type": d.get("resolution_type"),
            "worked": d.get("worked"),
            "reuse_count": d.get("reuse_count", 0),
            "agent": d.get("agent_name"),
            "match_quality": round(match * 100, 1),
            "confidence": round(confidence, 1),
            "combined_score": combined,
            "is_global": d.get("is_global", 0),
        })

    # 2. Search errors_solutions (raw)
    cursor.execute("""
        SELECT id, error_type, error_message, solution, solution_code,
               solution_worked, resolved_at, attempts, language, file_path, created_at
        FROM errors_solutions
        WHERE solution IS NOT NULL AND solution != ''
        ORDER BY solution_worked DESC, resolved_at DESC
        LIMIT 200
    """)
    for row in cursor.fetchall():
        d = dict(row)
        match = _match_quality(query, d.get("error_message", ""))
        if match < 0.15:
            continue
        confidence = _raw_error_confidence(d)
        combined = round(match * 0.4 + confidence * 0.6, 1)
        candidates.append({
            "source": "errors_solutions",
            "id": d["id"],
            "problem": truncate(d.get("error_message", ""), 80),
            "solution": d.get("solution", ""),
            "solution_code": d.get("solution_code"),
            "resolution_type": d.get("error_type"),
            "worked": d.get("solution_worked"),
            "reuse_count": 0,
            "agent": None,
            "match_quality": round(match * 100, 1),
            "confidence": round(confidence, 1),
            "combined_score": combined,
            "is_global": 0,
        })

    # 3. Search error_patterns
    cursor.execute("""
        SELECT id, error_signature, solution, count, auto_promoted
        FROM error_patterns
        WHERE solution IS NOT NULL AND solution != ''
        ORDER BY count DESC
        LIMIT 100
    """)
    for row in cursor.fetchall():
        d = dict(row)
        match = _match_quality(query, d.get("error_signature", ""))
        if match < 0.15:
            continue
        confidence = _pattern_confidence(d)
        combined = round(match * 0.4 + confidence * 0.6, 1)
        candidates.append({
            "source": "error_patterns",
            "id": d["id"],
            "problem": truncate(d.get("error_signature", ""), 80),
            "solution": d.get("solution", ""),
            "solution_code": None,
            "resolution_type": "pattern",
            "worked": True,
            "reuse_count": d.get("count", 0),
            "agent": None,
            "match_quality": round(match * 100, 1),
            "confidence": round(confidence, 1),
            "combined_score": combined,
            "is_global": 0,
        })

    conn.close()

    # Sort by combined score
    candidates.sort(key=lambda x: -x["combined_score"])

    # Deduplicate by similar solutions
    seen_solutions = set()
    unique = []
    for c in candidates:
        sol_key = _normalize_error(c["solution"])[:100]
        if sol_key in seen_solutions:
            continue
        seen_solutions.add(sol_key)
        unique.append(c)
        if len(unique) >= limit:
            break

    return unique


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Solution Index — problem → solution lookup")
    sub = parser.add_subparsers(dest="command")

    # suggest
    p_suggest = sub.add_parser("suggest", help="Find solutions for an error")
    p_suggest.add_argument("query", help="Error message to search for")
    p_suggest.add_argument("--limit", type=int, default=10)
    p_suggest.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "suggest":
        results = suggest(args.query, limit=args.limit)
        if args.json:
            print(json.dumps({"query": args.query, "solutions": results, "count": len(results)},
                           indent=2, default=str))
        else:
            print(f"\n💡 SOLUTIONS FOR: {truncate(args.query, 60)}")
            print("=" * 70)
            if not results:
                print("  (nicio soluție găsită)")
            else:
                for i, r in enumerate(results, 1):
                    worked_icon = "✅" if r["worked"] else "❌"
                    global_icon = "🌟" if r["is_global"] else ""
                    print(f"\n  {i}. [{r['combined_score']:.0f}pts] {worked_icon} {global_icon} {r['source']}#{r['id']}")
                    print(f"     Problem:  {r['problem']}")
                    print(f"     Solution: {truncate(r['solution'], 70)}")
                    if r["solution_code"]:
                        print(f"     Code:     {truncate(r['solution_code'], 70)}")
                    print(f"     Match: {r['match_quality']}% | Confidence: {r['confidence']}% | "
                          f"Reuse: {r['reuse_count']} | Agent: {r['agent'] or '—'}")
                print(f"\n  Total: {len(results)} solutions found")


if __name__ == "__main__":
    main()
