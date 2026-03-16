#!/usr/bin/env python3
"""
Context Builder V2 - Construiește context compact și relevant din memoria V2.

Moduri:
    --compact       (default) Context scurt ~400-800 tokeni
    --full          Context extins, fără budget
    --survival      Ultra-scurt ~200-300 tokeni
    --delta         Doar schimbări de la ultimul snapshot
    --json          Output JSON

Opțiuni:
    --project PATH  Path proiect (default: curent)
    --budget N      Token budget explicit
    --intent X      Override intent (debugging/feature/deploy/docs/refactor/review/explore)
    --query Q       Topic/query for keyword relevance ranking (17Z)
"""

import sys
import os
import json
import argparse
import re
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from v2_common import (
    get_db, get_current_model, get_current_project_path, get_current_intent,
    get_current_branch, format_timestamp, truncate, SNAPSHOT_FILE, INTENT_PRIORITIES,
)


# === SCORING ===

def _age_days(ts_str):
    """Returnează vârsta în zile a unui timestamp ISO."""
    if not ts_str:
        return 999
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now() - dt.replace(tzinfo=None)).days
    except (ValueError, TypeError):
        return 999


def _recency_score(age_days, compact=False):
    """Scor recență. Compact mode penalizează mai agresiv."""
    if compact:
        if age_days <= 7:
            return 10
        if age_days <= 30:
            return 5
        if age_days <= 60:
            return 2
        return 0
    else:
        if age_days <= 30:
            return 10
        if age_days <= 90:
            return 5
        if age_days <= 180:
            return 2
        return 0


PRIORITY_SCORES = {"critical": 15, "high": 10, "medium": 5, "low": 2}
STATUS_SCORES = {"in_progress": 15, "blocked": 12, "todo": 5}


# === 17Z: KEYWORD RELEVANCE ===

# Cuvinte fără valoare semantică (stop words minimale EN+RO)
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "and", "but", "or", "not", "no", "if", "then", "than", "so", "up",
    "it", "its", "this", "that", "these", "those", "he", "she", "they",
    "we", "i", "you", "my", "your", "our", "their", "what", "which",
    "who", "when", "where", "how", "all", "each", "every", "both",
    "de", "la", "in", "si", "sau", "cu", "pe", "din", "pentru", "ca",
    "nu", "un", "o", "este", "sunt", "am", "a", "ai", "au", "se",
})


def _tokenize(text):
    """Tokenizare simplă: lowercase, split pe non-alfanumerice, exclude stop words."""
    if not text:
        return set()
    words = set(re.findall(r'[a-z0-9_]+', text.lower()))
    return words - _STOP_WORDS


def _keyword_relevance(entity_text, query_tokens):
    """Scor de relevanță bazat pe overlap de cuvinte-cheie.

    Returns: 0.0 - 1.0 (fracția de query tokens găsite în entity text)
    """
    if not query_tokens or not entity_text:
        return 0.0
    entity_tokens = _tokenize(entity_text)
    if not entity_tokens:
        return 0.0
    overlap = query_tokens & entity_tokens
    return len(overlap) / len(query_tokens)


# Intent-ul curent generează keywords implicite
_INTENT_KEYWORDS = {
    "debugging": {"error", "bug", "fix", "crash", "exception", "traceback", "failed", "broken", "issue", "debug"},
    "feature": {"feature", "implement", "add", "create", "build", "new", "functionality"},
    "deploy": {"deploy", "production", "release", "ci", "cd", "docker", "server", "config"},
    "refactor": {"refactor", "clean", "rename", "extract", "simplify", "pattern", "debt", "restructure"},
    "docs": {"document", "readme", "guide", "api", "spec", "manual", "reference"},
    "review": {"review", "check", "audit", "quality", "lint", "test", "verify"},
    "explore": {"explore", "understand", "architecture", "structure", "how", "where", "why"},
}


def _build_query_tokens(intent=None, query=None):
    """Construiește setul de tokens din intent + query explicit."""
    tokens = set()
    if intent and intent in _INTENT_KEYWORDS:
        tokens.update(_INTENT_KEYWORDS[intent])
    if query:
        tokens.update(_tokenize(query))
    return tokens


# === 17Z: UNIFIED RANKING ===

# Weights pentru scorul final unificat
_TYPE_WEIGHTS = {
    "decision": 1.2,       # Decizii = cel mai important
    "resolution": 1.1,     # Rezolvări = foarte valoroase
    "fact": 1.0,           # Facts = baseline
    "goal": 0.9,           # Goals
    "task": 0.8,           # Tasks
}

# Top-K per mode (total items, nu per tip)
_UNIFIED_TOP_K = {
    "survival": 8,
    "compact": 20,
    "full": 60,
}


def _entity_text(entity, entity_type):
    """Extrage textul relevant dintr-o entitate pentru keyword matching."""
    if entity_type == "decision":
        return (entity.get("title") or "") + " " + (entity.get("category") or "")
    elif entity_type == "fact":
        return (entity.get("fact") or "") + " " + (entity.get("fact_type") or "") + " " + (entity.get("category") or "")
    elif entity_type == "resolution":
        return (entity.get("error_summary") or "") + " " + (entity.get("resolution") or "")
    elif entity_type == "goal":
        return entity.get("title") or ""
    elif entity_type == "task":
        return entity.get("title") or ""
    return ""


def _unified_score(entity, entity_type, query_tokens, intent=None, compact=False):
    """Calculează scor unificat pentru o entitate.

    Componente (0-100 scala):
    - memory_score: 0-100 din memory_scoring.py (dacă disponibil)
    - keyword_relevance: 0-30 (overlap cu query/intent tokens)
    - intent_boost: 0-15 (matching explicit intent → tip entitate)
    - type_weight: multiplicator 0.8-1.2

    Returns: (score, breakdown_dict)
    """
    breakdown = {"type": entity_type, "id": entity.get("id")}

    # 1. Memory scoring (refolosim engine-ul existent)
    memory_score = 0
    try:
        from memory_scoring import score_decision, score_fact, score_resolution
        if entity_type == "decision":
            ms = score_decision(entity)
            memory_score = ms["total"]
        elif entity_type == "fact":
            ms = score_fact(entity)
            memory_score = ms["total"]
        elif entity_type == "resolution":
            ms = score_resolution(entity)
            memory_score = ms["total"]
        else:
            # Goals/tasks — scor simplu bazat pe prioritate + recency
            age = _age_days(entity.get("created_at"))
            priority = entity.get("priority", "medium")
            memory_score = PRIORITY_SCORES.get(priority, 5) + _recency_score(age, compact)
            if entity_type == "task":
                memory_score += STATUS_SCORES.get(entity.get("status", ""), 0)
    except ImportError:
        # Fallback dacă memory_scoring nu e disponibil
        age = _age_days(entity.get("created_at"))
        memory_score = _recency_score(age, compact) + 10
    breakdown["memory_score"] = round(memory_score, 1)

    # 2. Keyword relevance (0-30)
    kw_raw = _keyword_relevance(_entity_text(entity, entity_type), query_tokens)
    kw_score = round(kw_raw * 30, 1)
    breakdown["keyword_relevance"] = kw_score

    # 3. Intent boost (0-15)
    intent_boost = 0
    if intent:
        if intent == "debugging" and entity_type == "resolution":
            intent_boost = 15
        elif intent == "debugging" and entity_type == "fact" and entity.get("fact_type") == "gotcha":
            intent_boost = 10
        elif intent in ("deploy", "refactor") and entity_type == "decision":
            intent_boost = 12
        elif intent == "feature" and entity_type in ("goal", "task"):
            intent_boost = 10
        elif intent == "docs" and entity_type in ("decision", "fact"):
            intent_boost = 8
    breakdown["intent_boost"] = intent_boost

    # 4. Type weight
    type_w = _TYPE_WEIGHTS.get(entity_type, 1.0)
    breakdown["type_weight"] = type_w

    # Scor final
    raw = memory_score + kw_score + intent_boost
    final = round(raw * type_w, 1)
    breakdown["final_score"] = final

    return final, breakdown


# === DATA FETCHERS ===

def fetch_project_profile(cursor, project_path):
    """Profilul proiectului curent."""
    cursor.execute(
        "SELECT * FROM project_profiles WHERE project_path = ?",
        (project_path,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def fetch_decisions(cursor, project_path, limit, intent=None, compact=False, branch=None):
    """Decizii active, prioritizate: proiect > globale, recente primele."""
    branch = branch or "main"
    cursor.execute("""
        SELECT id, title, category, confidence, created_at, model_used,
               CASE WHEN project_path = ? THEN 10 ELSE 0 END as proj_score
        FROM decisions
        WHERE status = 'active' AND (branch = ? OR branch IS NULL)
        ORDER BY proj_score DESC, created_at DESC
        LIMIT ?
    """, (project_path, branch, limit))
    rows = [dict(r) for r in cursor.fetchall()]

    # Intent scoring: boost convention decisions for deploy/refactor
    if intent and compact:
        for r in rows:
            age = _age_days(r.get("created_at"))
            r["_score"] = r["proj_score"] + _recency_score(age, compact=True)
            if intent in ("deploy", "refactor") and r.get("category") == "convention":
                r["_score"] += 15
            if intent == "feature" and r.get("category") in ("technical", "architectural"):
                r["_score"] += 10
        rows.sort(key=lambda x: x.get("_score", 0), reverse=True)

    return rows


def fetch_facts(cursor, project_path, limit, intent=None, compact=False, branch=None):
    """Facts: pinned primele, apoi relevante proiectului."""
    branch = branch or "main"
    cursor.execute("""
        SELECT id, fact, fact_type, category, is_pinned, confidence, created_at,
               CASE WHEN is_pinned = 1 THEN 100 ELSE 0 END +
               CASE WHEN project_path = ? THEN 10 ELSE 0 END as score
        FROM learned_facts
        WHERE is_active = 1 AND (branch = ? OR branch IS NULL)
        ORDER BY score DESC, created_at DESC
        LIMIT ?
    """, (project_path, branch, limit))
    rows = [dict(r) for r in cursor.fetchall()]

    # Intent scoring
    if intent and compact:
        for r in rows:
            age = _age_days(r.get("created_at"))
            base = 100 if r.get("is_pinned") else 0
            r["_score"] = base + r.get("score", 0) + _recency_score(age, compact=True)
            # Pinned facts nu sunt penalizate de aging
            if r.get("is_pinned"):
                r["_score"] += 50
            if intent == "debugging" and r.get("fact_type") == "gotcha":
                r["_score"] += 20
            if intent in ("deploy", "refactor") and r.get("fact_type") == "convention":
                r["_score"] += 15
        rows.sort(key=lambda x: x.get("_score", 0), reverse=True)

    return rows


def fetch_goals(cursor, project_path, limit, intent=None, compact=False, branch=None):
    """Goals active, prioritizate."""
    branch = branch or "main"
    cursor.execute("""
        SELECT g.id, g.title, g.priority, g.target_date, g.created_at,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id) as total_tasks,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id = g.id AND t.status = 'done') as done_tasks,
               CASE WHEN g.project_path = ? THEN 10 ELSE 0 END as proj_score
        FROM goals g
        WHERE g.status = 'active' AND (g.branch = ? OR g.branch IS NULL)
        ORDER BY proj_score DESC,
                 CASE g.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                      WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END,
                 g.created_at DESC
        LIMIT ?
    """, (project_path, branch, limit))
    return [dict(r) for r in cursor.fetchall()]


def fetch_tasks(cursor, project_path, limit, intent=None, compact=False, branch=None):
    """Tasks active, prioritizate: in_progress > blocked > todo."""
    branch = branch or "main"
    cursor.execute("""
        SELECT t.id, t.title, t.priority, t.status, t.goal_id, t.blocked_by, t.created_at,
               CASE WHEN t.project_path = ? THEN 10 ELSE 0 END as proj_score
        FROM tasks t
        WHERE t.status IN ('in_progress', 'blocked', 'todo') AND (t.branch = ? OR t.branch IS NULL)
        ORDER BY proj_score DESC,
                 CASE t.status WHEN 'in_progress' THEN 0 WHEN 'blocked' THEN 1 WHEN 'todo' THEN 2 END,
                 CASE t.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                      WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END
        LIMIT ?
    """, (project_path, branch, limit))
    rows = [dict(r) for r in cursor.fetchall()]

    # Intent: debugging → blocked tasks first
    if intent == "debugging" and compact:
        rows.sort(key=lambda t: (0 if t["status"] == "blocked" else 1, t.get("proj_score", 0) * -1))

    return rows


def fetch_resolutions(cursor, project_path, limit, intent=None, compact=False, branch=None):
    """Rezolvări recente utile. worked=1 prioritizate."""
    branch = branch or "main"
    cursor.execute("""
        SELECT id, error_id, error_summary, resolution, resolution_type,
               model_used, worked, created_at,
               CASE WHEN project_path = ? THEN 10 ELSE 0 END as proj_score
        FROM error_resolutions
        WHERE (branch = ? OR branch IS NULL)
        ORDER BY
            CASE WHEN worked = 1 THEN 0 ELSE 1 END,
            proj_score DESC, created_at DESC
        LIMIT ?
    """, (project_path, branch, limit))
    rows = [dict(r) for r in cursor.fetchall()]

    if intent == "debugging" and compact:
        # Boost worked resolutions
        for r in rows:
            r["_score"] = (20 if r.get("worked") else 0) + r.get("proj_score", 0)
        rows.sort(key=lambda x: x.get("_score", 0), reverse=True)

    return rows


# === LIMITS CALCULATOR ===

def _get_limits(mode, intent=None):
    """Returnează (d_limit, f_limit, g_limit, t_limit, r_limit) pe bază de mod."""
    if mode == "survival":
        return 3, 3, 2, 3, 2
    elif mode == "compact":
        base = {"d": 4, "f": 5, "g": 3, "t": 5, "r": 3}
        # Intent-aware adjustments
        if intent == "debugging":
            base["r"] = 5
            base["d"] = 2
        elif intent == "feature":
            base["g"] = 5
            base["t"] = 7
            base["r"] = 2
        elif intent in ("deploy", "refactor"):
            base["d"] = 5
            base["f"] = 6
            base["r"] = 4
        elif intent == "docs":
            base["d"] = 5
            base["f"] = 6
            base["g"] = 2
        return base["d"], base["f"], base["g"], base["t"], base["r"]
    else:  # full
        return 10, 15, 10, 15, 10


# === BUDGET MANAGEMENT ===

def _estimate_tokens(text):
    """Estimare grosieră: ~4 caractere per token."""
    return len(text) // 4


def _apply_budget(sections, budget):
    """Reduce secțiunile dacă depășesc budget-ul."""
    total = sum(_estimate_tokens(s) for s in sections.values())
    if total <= budget:
        return sections

    # Ordinea de tăiere: resolutions > tasks > facts > goals > decisions
    trim_order = ["resolutions", "tasks", "facts", "goals"]
    for key in trim_order:
        if key not in sections:
            continue
        lines = sections[key].strip().split("\n")
        while len(lines) > 2 and sum(_estimate_tokens(s) for s in sections.values()) > budget:
            lines.pop()
            sections[key] = "\n".join(lines)
        total = sum(_estimate_tokens(s) for s in sections.values())
        if total <= budget:
            break

    return sections


# === FORMATTERS (TEXT) ===

def fmt_model(model_id, provider):
    if model_id == "unknown":
        return "Model: unknown"
    return f"Model: {model_id} ({provider})"


def fmt_intent(intent):
    if not intent:
        return ""
    return f"Intent: {intent}"


def fmt_profile(profile, compact=False):
    if not profile:
        return "Project: (no profile)"
    lines = [f"Project: {profile.get('project_name') or '—'}"]
    if not compact and profile.get("description"):
        lines.append(f"  {truncate(profile['description'], 80)}")
    if profile.get("tech_stack"):
        try:
            stack = json.loads(profile["tech_stack"])
            lines.append(f"  Stack: {', '.join(stack)}")
        except (json.JSONDecodeError, TypeError):
            lines.append(f"  Stack: {profile['tech_stack']}")
    if not compact and profile.get("conventions"):
        try:
            conv = json.loads(profile["conventions"])
            parts = [f"{k}={v}" for k, v in conv.items()]
            lines.append(f"  Conventions: {', '.join(parts)}")
        except (json.JSONDecodeError, TypeError):
            pass
    if not compact and profile.get("notes"):
        lines.append(f"  Notes: {truncate(profile['notes'], 80)}")
    return "\n".join(lines)


def fmt_decisions(decisions, compact=False):
    if not decisions:
        return ""
    trunc = 40 if compact else 60
    lines = ["Decisions:"]
    for d in decisions:
        model_tag = f" [{d['model_used']}]" if d.get("model_used") and not compact else ""
        lines.append(f"  #{d['id']} [{d['category']}] {truncate(d['title'], trunc)}{model_tag}")
    return "\n".join(lines)


def fmt_facts(facts, compact=False):
    if not facts:
        return ""
    trunc = 45 if compact else 65
    lines = ["Facts:"]
    for f in facts:
        pin = "PIN " if f["is_pinned"] else ""
        lines.append(f"  #{f['id']} {pin}[{f['fact_type']}] {truncate(f['fact'], trunc)}")
    return "\n".join(lines)


def fmt_goals(goals, compact=False):
    if not goals:
        return ""
    trunc = 35 if compact else 50
    lines = ["Goals:"]
    for g in goals:
        total = g.get("total_tasks") or 0
        done = g.get("done_tasks") or 0
        progress = f" ({done}/{total})" if total > 0 else ""
        target = f" target:{g['target_date']}" if g.get("target_date") and not compact else ""
        lines.append(f"  #{g['id']} [{g['priority']}] {truncate(g['title'], trunc)}{progress}{target}")
    return "\n".join(lines)


def fmt_tasks(tasks, compact=False):
    if not tasks:
        return ""
    trunc = 30 if compact else 45
    status_icons = {"in_progress": "WIP", "blocked": "BLOCKED", "todo": "TODO"}
    lines = ["Tasks:"]
    for t in tasks:
        icon = status_icons.get(t["status"], t["status"])
        goal_ref = f" (g#{t['goal_id']})" if t.get("goal_id") else ""
        blocked = f" :{truncate(t['blocked_by'], 20)}" if t.get("blocked_by") and not compact else ""
        lines.append(f"  #{t['id']} {icon} [{t['priority']}] {truncate(t['title'], trunc)}{goal_ref}{blocked}")
    return "\n".join(lines)


def fmt_resolutions(resolutions, compact=False):
    if not resolutions:
        return ""
    err_trunc = 20 if compact else 30
    fix_trunc = 30 if compact else 40
    lines = ["Recent fixes:"]
    for r in resolutions:
        err = truncate(r.get("error_summary") or "", err_trunc)
        fix = truncate(r["resolution"], fix_trunc)
        lines.append(f"  #{r['id']} {err} -> {fix}")
    return "\n".join(lines)


# === FORMATTERS (JSON) ===

def to_json_output(model_id, provider, profile, decisions, facts, goals, tasks, resolutions, intent=None, mode="compact"):
    """Generează output JSON structurat."""
    return {
        "meta": {"mode": mode, "intent": intent, "generated_at": datetime.now().isoformat()},
        "model": {"model_id": model_id, "provider": provider},
        "project": {
            "name": profile.get("project_name") if profile else None,
            "path": profile.get("project_path") if profile else None,
            "description": profile.get("description") if profile else None,
            "tech_stack": _safe_json_parse(profile.get("tech_stack")) if profile else None,
            "conventions": _safe_json_parse(profile.get("conventions")) if profile else None,
            "notes": profile.get("notes") if profile else None,
        },
        "decisions": [
            {"id": d["id"], "title": d["title"], "category": d["category"],
             "confidence": d.get("confidence"), "model": d.get("model_used")}
            for d in decisions
        ],
        "facts": [
            {"id": f["id"], "fact": f["fact"], "type": f["fact_type"],
             "category": f.get("category"), "pinned": bool(f["is_pinned"])}
            for f in facts
        ],
        "goals": [
            {"id": g["id"], "title": g["title"], "priority": g["priority"],
             "target_date": g.get("target_date"),
             "tasks_done": g.get("done_tasks", 0), "tasks_total": g.get("total_tasks", 0)}
            for g in goals
        ],
        "tasks": [
            {"id": t["id"], "title": t["title"], "priority": t["priority"],
             "status": t["status"], "goal_id": t.get("goal_id"),
             "blocked_by": t.get("blocked_by")}
            for t in tasks
        ],
        "resolutions": [
            {"id": r["id"], "error_summary": r.get("error_summary"),
             "resolution": r["resolution"], "type": r.get("resolution_type"),
             "model": r.get("model_used")}
            for r in resolutions
        ],
    }


def _safe_json_parse(val):
    if not val:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# === SNAPSHOT CACHE ===

SNAPSHOT_TTL_SECONDS = 600  # 10 minute


def _load_snapshot():
    """Încarcă snapshot din cache dacă valid (TTL + same intent/model)."""
    if not SNAPSHOT_FILE.exists():
        return None
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        # Check TTL
        gen_at = data.get("meta", {}).get("generated_at")
        if gen_at:
            dt = datetime.fromisoformat(gen_at)
            age = (datetime.now() - dt).total_seconds()
            if age > SNAPSHOT_TTL_SECONDS:
                return None
        # Check intent/model match
        current_intent = get_current_intent()
        from v2_common import get_current_model as _gcm
        current_model, _ = _gcm()
        if data.get("meta", {}).get("intent") != current_intent:
            return None
        if data.get("model", {}).get("model_id") != current_model:
            return None
        return data
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _save_snapshot(json_data):
    """Salvează snapshot în cache."""
    try:
        SNAPSHOT_FILE.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
    except OSError:
        pass


def _compute_delta(old_snapshot, new_data):
    """Calculează delta între snapshot-ul vechi și datele noi."""
    delta = {"added": {}, "removed": {}, "changed": {}}
    sections = ["decisions", "facts", "goals", "tasks", "resolutions"]

    for section in sections:
        old_items = {item["id"]: item for item in old_snapshot.get(section, [])}
        new_items = {item["id"]: item for item in new_data.get(section, [])}

        old_ids = set(old_items.keys())
        new_ids = set(new_items.keys())

        added = new_ids - old_ids
        removed = old_ids - new_ids

        if added:
            delta["added"][section] = [new_items[i] for i in added]
        if removed:
            delta["removed"][section] = [old_items[i] for i in removed]

        # Detect changes in common items (simple: compare JSON)
        for common_id in old_ids & new_ids:
            if json.dumps(old_items[common_id], sort_keys=True) != json.dumps(new_items[common_id], sort_keys=True):
                delta["changed"].setdefault(section, []).append(new_items[common_id])

    return delta


def _fmt_delta(delta):
    """Formatează delta ca text."""
    lines = []
    has_changes = False

    for section, items in delta.get("added", {}).items():
        has_changes = True
        lines.append(f"  + {section}: {len(items)} adăugat(e)")
        for item in items:
            title = item.get("title") or item.get("fact") or item.get("resolution") or "?"
            lines.append(f"    + #{item['id']} {truncate(title, 50)}")

    for section, items in delta.get("removed", {}).items():
        has_changes = True
        lines.append(f"  - {section}: {len(items)} eliminat(e)")
        for item in items:
            title = item.get("title") or item.get("fact") or item.get("resolution") or "?"
            lines.append(f"    - #{item['id']} {truncate(title, 50)}")

    for section, items in delta.get("changed", {}).items():
        has_changes = True
        lines.append(f"  ~ {section}: {len(items)} modificat(e)")
        for item in items:
            title = item.get("title") or item.get("fact") or item.get("resolution") or "?"
            lines.append(f"    ~ #{item['id']} {truncate(title, 50)}")

    if not has_changes:
        lines.append("  (nicio schimbare)")

    return "\n".join(lines)


# === MAIN BUILD ===

def _ranked_select(decisions, facts, goals, tasks, resolutions,
                   intent=None, query=None, mode="compact"):
    """17Z: Ranking unificat cross-type. Selectează top-K cele mai relevante.

    Returnează tuple (decisions, facts, goals, tasks, resolutions) filtrate și ordonate.
    """
    query_tokens = _build_query_tokens(intent, query)
    is_compact = mode in ("compact", "survival")
    top_k = _UNIFIED_TOP_K.get(mode, 20)

    # Construiește lista unificată cu scoruri
    scored = []
    for entity in decisions:
        score, breakdown = _unified_score(entity, "decision", query_tokens, intent, is_compact)
        scored.append(("decision", entity, score, breakdown))
    for entity in facts:
        score, breakdown = _unified_score(entity, "fact", query_tokens, intent, is_compact)
        scored.append(("fact", entity, score, breakdown))
    for entity in goals:
        score, breakdown = _unified_score(entity, "goal", query_tokens, intent, is_compact)
        scored.append(("goal", entity, score, breakdown))
    for entity in tasks:
        score, breakdown = _unified_score(entity, "task", query_tokens, intent, is_compact)
        scored.append(("task", entity, score, breakdown))
    for entity in resolutions:
        score, breakdown = _unified_score(entity, "resolution", query_tokens, intent, is_compact)
        scored.append(("resolution", entity, score, breakdown))

    # Sortează după scor descrescător
    scored.sort(key=lambda x: x[2], reverse=True)

    # Selectează top-K
    selected = scored[:top_k]

    # Separă înapoi pe tipuri, păstrând ordinea relativă
    out_decisions = [e for t, e, s, b in selected if t == "decision"]
    out_facts = [e for t, e, s, b in selected if t == "fact"]
    out_goals = [e for t, e, s, b in selected if t == "goal"]
    out_tasks = [e for t, e, s, b in selected if t == "task"]
    out_resolutions = [e for t, e, s, b in selected if t == "resolution"]

    return out_decisions, out_facts, out_goals, out_tasks, out_resolutions


def build_context(project_path=None, output_json=False, mode="compact",
                  budget=None, intent_override=None, delta=False, branch=None,
                  query=None):
    """Construiește și afișează contextul V2.

    mode: "compact" (default, ~400-800 tok), "full" (no budget), "survival" (~200-300 tok)
    query: topic/query text for keyword relevance ranking (17Z)
    """
    project_path = project_path or get_current_project_path()
    intent = intent_override or get_current_intent()
    branch = branch or get_current_branch()
    is_compact = mode in ("compact", "survival")

    # Default budgets per mode
    if budget is None:
        if mode == "survival":
            budget = 300
        elif mode == "compact":
            budget = 700
        else:
            budget = 99999  # full = no limit

    # Delta mode: load old snapshot first
    old_snapshot = None
    if delta:
        old_snapshot = _load_snapshot()

    # 17Z: Overfetch — luăm mai multe items decât limita finală, pentru ranking
    # Limitele vechi rămân ca fallback per tip
    d_limit, f_limit, g_limit, t_limit, r_limit = _get_limits(mode, intent)
    # Overfetch 2x pentru ranking mai bun (doar în compact/survival)
    overfetch = 2 if is_compact else 1

    conn = get_db()
    cursor = conn.cursor()

    # Fetch all data (overfetch)
    model_id, provider = get_current_model()
    profile = fetch_project_profile(cursor, project_path)
    decisions = fetch_decisions(cursor, project_path, d_limit * overfetch, intent, is_compact, branch=branch)
    facts = fetch_facts(cursor, project_path, f_limit * overfetch, intent, is_compact, branch=branch)
    goals = fetch_goals(cursor, project_path, g_limit * overfetch, intent, is_compact, branch=branch)
    tasks = fetch_tasks(cursor, project_path, t_limit * overfetch, intent, is_compact, branch=branch)
    resolutions = fetch_resolutions(cursor, project_path, r_limit * overfetch, intent, is_compact, branch=branch)

    # 17Z: Unified ranking — rerank cross-type cu memory_scoring + keyword relevance
    try:
        decisions, facts, goals, tasks, resolutions = _ranked_select(
            decisions, facts, goals, tasks, resolutions,
            intent=intent, query=query, mode=mode,
        )
    except Exception:
        # Fallback: trunchiem la limitele originale (comportament vechi)
        decisions = decisions[:d_limit]
        facts = facts[:f_limit]
        goals = goals[:g_limit]
        tasks = tasks[:t_limit]
        resolutions = resolutions[:r_limit]

    # Last checkpoint (best effort)
    last_checkpoint = None
    try:
        cursor.execute("""
            SELECT id, name, created_at FROM memory_checkpoints
            WHERE project_path=? ORDER BY created_at DESC LIMIT 1
        """, (project_path,))
        row = cursor.fetchone()
        if row:
            last_checkpoint = dict(row)
    except Exception:
        pass

    # Intelligence data (best effort — nu blochează dacă modulele lipsesc)
    patterns = []
    conflicts = []
    stale_summary = ""
    try:
        from error_patterns import fetch_patterns_for_context, fmt_patterns
        p_limit = 2 if mode == "survival" else 3
        patterns = fetch_patterns_for_context(cursor, project_path, limit=p_limit)
    except Exception:
        pass
    try:
        from decision_analyzer import fetch_conflicts_for_context, fmt_conflicts
        conflicts = fetch_conflicts_for_context(cursor, project_path, limit=2)
    except Exception:
        pass
    try:
        from memory_cleanup import fetch_stale_summary_for_context
        if mode != "survival":
            stale_summary = fetch_stale_summary_for_context(cursor)
    except Exception:
        pass

    conn.close()

    # JSON output (also used for snapshot/delta)
    json_data = to_json_output(model_id, provider, profile, decisions, facts,
                               goals, tasks, resolutions, intent, mode)
    if branch != "main":
        json_data.setdefault("meta", {})["branch"] = branch

    # Delta mode
    if delta:
        if old_snapshot:
            delta_result = _compute_delta(old_snapshot, json_data)
            # Save new snapshot
            _save_snapshot(json_data)

            if output_json:
                print(json.dumps({"delta": delta_result, "snapshot": json_data}, indent=2, ensure_ascii=False))
                return

            proj_name = project_path.split("/")[-1] if "/" in project_path else project_path
            print(f"\n{'='*50}")
            print(f"  DELTA CONTEXT — {proj_name}")
            print(f"{'='*50}\n")
            print(_fmt_delta(delta_result))
            print(f"\n--- delta ---")
            return
        else:
            # No previous snapshot → full context + save
            _save_snapshot(json_data)
            if not output_json:
                print("  (niciun snapshot anterior — generat context complet + snapshot salvat)\n")
            # Fall through to normal output

    # Save snapshot for future delta
    _save_snapshot(json_data)

    if output_json:
        print(json.dumps(json_data, indent=2, ensure_ascii=False))
        return

    # Text output
    sections = {}
    sections["model"] = fmt_model(model_id, provider)
    if branch != "main":
        sections["branch"] = f"Branch: {branch}"
    intent_line = fmt_intent(intent)
    if intent_line:
        sections["intent"] = intent_line
    sections["profile"] = fmt_profile(profile, compact=is_compact)

    if decisions:
        sections["decisions"] = fmt_decisions(decisions, compact=is_compact)
    if facts:
        sections["facts"] = fmt_facts(facts, compact=is_compact)
    if goals:
        sections["goals"] = fmt_goals(goals, compact=is_compact)
    if tasks:
        sections["tasks"] = fmt_tasks(tasks, compact=is_compact)
    if resolutions:
        sections["resolutions"] = fmt_resolutions(resolutions, compact=is_compact)

    # Intelligence sections
    if patterns:
        try:
            sections["patterns"] = fmt_patterns(patterns, compact=is_compact)
        except Exception:
            pass
    if conflicts:
        try:
            sections["conflicts"] = fmt_conflicts(conflicts, compact=is_compact)
        except Exception:
            pass
    if stale_summary:
        sections["stale"] = stale_summary

    # Last checkpoint
    if last_checkpoint:
        age = _age_days(last_checkpoint.get("created_at"))
        if age == 0:
            age_str = "today"
        elif age == 1:
            age_str = "1d ago"
        else:
            age_str = f"{age}d ago"
        sections["checkpoint"] = f"Last checkpoint: {last_checkpoint['name']} ({age_str})"

    # Apply budget (not for full mode)
    if mode != "full":
        sections = _apply_budget(sections, budget)

    # Print
    proj_name = project_path.split("/")[-1] if "/" in project_path else project_path
    mode_label = {"compact": "COMPACT", "full": "FULL", "survival": "SURVIVAL"}.get(mode, mode.upper())
    print(f"\n{'='*50}")
    print(f"  CONTEXT V2 [{mode_label}] — {proj_name}")
    print(f"{'='*50}\n")

    section_order = ["model", "branch", "intent", "profile", "checkpoint", "decisions", "facts", "goals", "tasks",
                      "resolutions", "patterns", "conflicts", "stale"]
    for key in section_order:
        if key in sections and sections[key]:
            print(sections[key])
            if key != "intent":
                print()

    # Token estimate
    total_text = "\n".join(sections.values())
    est_tokens = _estimate_tokens(total_text)
    print(f"--- ~{est_tokens} tokens ({mode_label}, budget: {budget}) ---")


# === BACKWARD COMPAT ===

def build_context_compat(project_path=None, output_json=False, full=False, budget=2000):
    """Interfață compatibilă cu apelurile vechi din reload_memory.py."""
    mode = "full" if full else "compact"
    build_context(project_path=project_path, output_json=output_json, mode=mode, budget=budget)


def main():
    parser = argparse.ArgumentParser(description="Context Builder V2")
    parser.add_argument("--project", "-p", help="Path proiect (default: curent)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--full", action="store_true", help="Context extins (fără budget)")
    parser.add_argument("--compact", action="store_true", help="Context compact (~400-800 tok, default)")
    parser.add_argument("--survival", action="store_true", help="Ultra-scurt (~200-300 tok)")
    parser.add_argument("--delta", action="store_true", help="Doar schimbări față de ultimul snapshot")
    parser.add_argument("--budget", "-b", type=int, help="Token budget explicit")
    parser.add_argument("--intent", "-i", help="Override intent (debugging/feature/deploy/docs/refactor/review/explore)")
    parser.add_argument("--query", "-q", help="Topic/query for keyword relevance ranking (17Z)")
    parser.add_argument("--branch", help="Override branch (default: curent)")

    args = parser.parse_args()

    # Determine mode
    if args.survival:
        mode = "survival"
    elif args.full:
        mode = "full"
    else:
        mode = "compact"

    build_context(
        project_path=args.project,
        output_json=args.json,
        mode=mode,
        budget=args.budget,
        intent_override=args.intent,
        query=args.query,
        delta=args.delta,
        branch=args.branch,
    )


if __name__ == "__main__":
    main()
