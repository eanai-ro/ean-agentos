#!/usr/bin/env python3
"""
Universal Agent Memory API — Flask Blueprint.

Prefix: /api/v1/...

Strat nou, independent de dashboard API, orientat pe integrare programatică.
Orice agent / CLI / model poate folosi aceste endpoint-uri pentru a:
- trimite evenimente
- salva decisions / facts / goals / tasks / resolutions
- cere context
- citi activity log
- verifica health

Nu depinde de CLI-ul actual. Nu depinde de dashboard.
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from flask import Blueprint, jsonify, request

from v2_common import (
    get_db, get_current_model, get_current_intent, get_current_session_id,
    get_current_branch, set_current_model, set_current_intent, invalidate_snapshot,
    log_agent_activity, log_agent_event,
    VALID_INTENTS, VALID_DECISION_CATEGORIES, VALID_CONFIDENCE_LEVELS,
    VALID_PRIORITIES, VALID_GOAL_STATUSES, VALID_TASK_STATUSES,
    VALID_FACT_TYPES, VALID_RESOLUTION_TYPES, VALID_ACTION_TYPES,
    VALID_AGENT_EVENT_TYPES, CROSS_AGENT_TABLES,
)

universal_bp = Blueprint("universal_api", __name__)


# ============================================================
# HELPERS
# ============================================================

VALID_EVENT_TYPES = (
    "session_start", "context_build", "decision_create", "fact_create",
    "goal_create", "task_update", "error_detected", "error_resolved",
    "checkpoint_create", "checkpoint_restore", "agent_activity",
)


def _parse_json():
    """Parse request JSON with clean error."""
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"ok": False, "error": "Request body must be valid JSON"}), 400)
    return data, None


def _require(data, field):
    """Check required field, return (value, error_response)."""
    val = data.get(field)
    if val is None or (isinstance(val, str) and not val.strip()):
        return None, (jsonify({"ok": False, "error": f"Field '{field}' is required"}), 400)
    return val.strip() if isinstance(val, str) else val, None


def _extract_agent_meta(data):
    """Extract common agent metadata from request payload."""
    return {
        "cli_name": (data.get("cli_name") or "").strip() or None,
        "agent_name": (data.get("agent_name") or "").strip() or None,
        "provider": (data.get("provider") or "").strip() or None,
        "model_name": (data.get("model_name") or "").strip() or None,
        "session_id": (data.get("session_id") or "").strip() or None,
        "project_path": (data.get("project_path") or "").strip() or None,
        "branch": (data.get("branch") or "").strip() or None,
    }


def _project(data):
    """Get project_path from data or fallback."""
    pp = (data.get("project_path") or "").strip()
    if pp:
        return pp
    return str(Path.cwd())


def _ok(extra=None):
    """Standard success response."""
    r = {"ok": True}
    if extra:
        r.update(extra)
    return jsonify(r)


# ============================================================
# POST /api/v1/events — Universal event ingestion
# ============================================================

@universal_bp.route("/api/v1/events", methods=["POST"])
def api_v1_events():
    data, err = _parse_json()
    if err:
        return err

    event_type, err = _require(data, "event_type")
    if err:
        return err

    if event_type not in VALID_EVENT_TYPES:
        return jsonify({"ok": False, "error": f"Invalid event_type. Valid: {', '.join(VALID_EVENT_TYPES)}"}), 400

    meta = _extract_agent_meta(data)
    project = _project(data)
    payload = data.get("payload")
    title = (data.get("title") or "").strip() or event_type

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO universal_events
        (event_type, title, project_path, session_id, cli_name, agent_name, provider, model_name, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event_type, title, project,
        meta["session_id"], meta["cli_name"], meta["agent_name"],
        meta["provider"], meta["model_name"],
        json.dumps(payload) if payload else None,
    ))
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return _ok({"event_id": event_id, "event_type": event_type})


# ============================================================
# POST /api/v1/decisions
# ============================================================

@universal_bp.route("/api/v1/decisions", methods=["POST"])
def api_v1_decisions():
    data, err = _parse_json()
    if err:
        return err

    title, err = _require(data, "title")
    if err:
        return err

    description = (data.get("description") or "").strip() or title
    category = (data.get("category") or "technical").strip()
    if category not in VALID_DECISION_CATEGORIES:
        category = "technical"
    confidence = (data.get("confidence") or "high").strip()
    if confidence not in VALID_CONFIDENCE_LEVELS:
        confidence = "high"
    rationale = (data.get("rationale") or "").strip() or None

    meta = _extract_agent_meta(data)
    project = _project(data)

    branch = meta["branch"] or get_current_branch()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decisions
        (title, description, category, status, confidence, rationale,
         project_path, source_session, model_used, provider, created_by, branch)
        VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title, description, category, confidence, rationale,
        project, meta["session_id"],
        meta["model_name"], meta["provider"],
        meta["agent_name"] or meta["cli_name"] or "api",
        branch,
    ))
    decision_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_agent_activity(
        "decision", f"Create via API: {title}", "decision", decision_id,
        agent_name=meta["agent_name"], model_id=meta["model_name"], provider=meta["provider"],
    )
    log_agent_event(
        "decision_created", title=title, related_table="decisions", related_id=decision_id,
        cli_name=meta["cli_name"], agent_name=meta["agent_name"],
        provider=meta["provider"], model_name=meta["model_name"],
        session_id=meta["session_id"], project_path=project, branch_name=branch,
    )

    return _ok({"id": decision_id, "title": title}), 201


# ============================================================
# POST /api/v1/facts
# ============================================================

@universal_bp.route("/api/v1/facts", methods=["POST"])
def api_v1_facts():
    data, err = _parse_json()
    if err:
        return err

    fact, err = _require(data, "fact")
    if err:
        return err

    fact_type = (data.get("fact_type") or "technical").strip()
    if fact_type not in VALID_FACT_TYPES:
        fact_type = "technical"
    category = (data.get("category") or "").strip() or None
    confidence = (data.get("confidence") or "high").strip()
    if confidence not in VALID_CONFIDENCE_LEVELS:
        confidence = "high"
    is_pinned = 1 if data.get("is_pinned") else 0
    source = (data.get("source") or "").strip() or None

    meta = _extract_agent_meta(data)
    project = _project(data)
    branch = meta["branch"] or get_current_branch()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO learned_facts
        (fact, fact_type, category, confidence, is_pinned, is_active, source,
         project_path, source_session, model_used, provider, created_by, branch)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
    """, (
        fact, fact_type, category, confidence, is_pinned, source,
        project, meta["session_id"],
        meta["model_name"], meta["provider"],
        meta["agent_name"] or meta["cli_name"] or "api",
        branch,
    ))
    fact_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_agent_activity(
        "learn", f"Create via API: {fact[:60]}", "fact", fact_id,
        agent_name=meta["agent_name"], model_id=meta["model_name"], provider=meta["provider"],
    )
    log_agent_event(
        "fact_created", title=fact[:80], related_table="learned_facts", related_id=fact_id,
        cli_name=meta["cli_name"], agent_name=meta["agent_name"],
        provider=meta["provider"], model_name=meta["model_name"],
        session_id=meta["session_id"], project_path=project, branch_name=branch,
    )

    return _ok({"id": fact_id, "fact": fact}), 201


# ============================================================
# POST /api/v1/goals
# ============================================================

@universal_bp.route("/api/v1/goals", methods=["POST"])
def api_v1_goals():
    data, err = _parse_json()
    if err:
        return err

    title, err = _require(data, "title")
    if err:
        return err

    description = (data.get("description") or "").strip() or None
    priority = (data.get("priority") or "medium").strip()
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    target_date = (data.get("target_date") or "").strip() or None

    meta = _extract_agent_meta(data)
    project = _project(data)
    branch = meta["branch"] or get_current_branch()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO goals
        (title, description, priority, status, target_date,
         project_path, source_session, created_by, branch)
        VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
    """, (
        title, description, priority, target_date,
        project, meta["session_id"],
        meta["agent_name"] or meta["cli_name"] or "api",
        branch,
    ))
    goal_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_agent_activity(
        "goal", f"Create via API: {title}", "goal", goal_id,
        agent_name=meta["agent_name"], model_id=meta["model_name"], provider=meta["provider"],
    )
    log_agent_event(
        "goal_created", title=title, related_table="goals", related_id=goal_id,
        cli_name=meta["cli_name"], agent_name=meta["agent_name"],
        provider=meta["provider"], model_name=meta["model_name"],
        session_id=meta["session_id"], project_path=project, branch_name=branch,
    )

    return _ok({"id": goal_id, "title": title}), 201


# ============================================================
# POST /api/v1/tasks
# ============================================================

@universal_bp.route("/api/v1/tasks", methods=["POST"])
def api_v1_tasks():
    data, err = _parse_json()
    if err:
        return err

    title, err = _require(data, "title")
    if err:
        return err

    description = (data.get("description") or "").strip() or None
    priority = (data.get("priority") or "medium").strip()
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    status = (data.get("status") or "todo").strip()
    if status not in VALID_TASK_STATUSES:
        status = "todo"
    goal_id = data.get("goal_id")
    blocked_by = (data.get("blocked_by") or "").strip() or None

    meta = _extract_agent_meta(data)
    project = _project(data)
    branch = meta["branch"] or get_current_branch()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks
        (title, description, priority, status, goal_id, blocked_by,
         project_path, source_session, created_by, branch)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title, description, priority, status, goal_id, blocked_by,
        project, meta["session_id"],
        meta["agent_name"] or meta["cli_name"] or "api",
        branch,
    ))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_agent_activity(
        "task", f"Create via API: {title}", "task", task_id,
        agent_name=meta["agent_name"], model_id=meta["model_name"], provider=meta["provider"],
    )
    log_agent_event(
        "task_created", title=title, related_table="tasks", related_id=task_id,
        cli_name=meta["cli_name"], agent_name=meta["agent_name"],
        provider=meta["provider"], model_name=meta["model_name"],
        session_id=meta["session_id"], project_path=project, branch_name=branch,
    )

    return _ok({"id": task_id, "title": title, "status": status}), 201


# ============================================================
# POST /api/v1/resolutions
# ============================================================

@universal_bp.route("/api/v1/resolutions", methods=["POST"])
def api_v1_resolutions():
    data, err = _parse_json()
    if err:
        return err

    error_summary, err = _require(data, "error_summary")
    if err:
        return err
    resolution, err = _require(data, "resolution")
    if err:
        return err

    resolution_type = (data.get("resolution_type") or "fix").strip()
    if resolution_type not in VALID_RESOLUTION_TYPES:
        resolution_type = "fix"
    resolution_code = (data.get("resolution_code") or "").strip() or None
    worked = 1 if data.get("worked", True) else 0

    meta = _extract_agent_meta(data)
    project = _project(data)
    branch = meta["branch"] or get_current_branch()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO error_resolutions
        (error_summary, resolution, resolution_code, resolution_type,
         model_used, provider, agent_name, worked,
         project_path, source_session, branch)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        error_summary, resolution, resolution_code, resolution_type,
        meta["model_name"], meta["provider"], meta["agent_name"], worked,
        project, meta["session_id"],
        branch,
    ))
    res_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_agent_activity(
        "resolve", f"Create via API: {error_summary[:60]}", "resolution", res_id,
        agent_name=meta["agent_name"], model_id=meta["model_name"], provider=meta["provider"],
    )
    log_agent_event(
        "resolution_created", title=error_summary[:80], related_table="error_resolutions", related_id=res_id,
        cli_name=meta["cli_name"], agent_name=meta["agent_name"],
        provider=meta["provider"], model_name=meta["model_name"],
        session_id=meta["session_id"], project_path=project, branch_name=branch,
    )

    return _ok({"id": res_id, "error_summary": error_summary}), 201


# ============================================================
# GET /api/v1/context
# ============================================================

@universal_bp.route("/api/v1/context")
def api_v1_context():
    project = request.args.get("project", str(Path.cwd()))
    mode = request.args.get("mode", "compact")
    intent = request.args.get("intent")
    agent_name = request.args.get("agent_name")
    model_name = request.args.get("model_name")
    branch = request.args.get("branch")

    valid_modes = ("compact", "full", "survival", "delta")
    if mode not in valid_modes:
        return jsonify({"ok": False, "error": f"Invalid mode. Valid: {', '.join(valid_modes)}"}), 400

    if intent and intent not in VALID_INTENTS:
        return jsonify({"ok": False, "error": f"Invalid intent. Valid: {', '.join(VALID_INTENTS)}"}), 400

    try:
        from context_builder_v2 import (
            fetch_project_profile, fetch_decisions, fetch_facts, fetch_goals,
            fetch_tasks, fetch_resolutions, to_json_output, _get_limits,
        )

        # Use provided intent or fall back to current
        effective_intent = intent or get_current_intent()
        is_compact = mode in ("compact", "survival")
        d_limit, f_limit, g_limit, t_limit, r_limit = _get_limits(mode, effective_intent)

        conn = get_db()
        cursor = conn.cursor()

        # Use provided model or fall back to current
        if model_name:
            m_id = model_name
            m_prov = request.args.get("provider", "unknown")
        else:
            m_id, m_prov = get_current_model()

        effective_branch = branch or get_current_branch()

        profile = fetch_project_profile(cursor, project)
        decisions = fetch_decisions(cursor, project, d_limit, effective_intent, is_compact, branch=effective_branch)
        facts = fetch_facts(cursor, project, f_limit, effective_intent, is_compact, branch=effective_branch)
        goals = fetch_goals(cursor, project, g_limit, effective_intent, is_compact, branch=effective_branch)
        tasks = fetch_tasks(cursor, project, t_limit, effective_intent, is_compact, branch=effective_branch)
        resolutions = fetch_resolutions(cursor, project, r_limit, effective_intent, is_compact, branch=effective_branch)
        conn.close()

        json_data = to_json_output(m_id, m_prov, profile, decisions, facts,
                                    goals, tasks, resolutions, effective_intent, mode)
        json_data["ok"] = True
        if effective_branch != "main":
            json_data.setdefault("meta", {})["branch"] = effective_branch
        if agent_name:
            json_data.setdefault("meta", {})["requesting_agent"] = agent_name

        return jsonify(json_data)

    except Exception as e:
        return jsonify({"ok": False, "error": f"Context build failed: {str(e)}"}), 500


# ============================================================
# GET /api/v1/activity
# ============================================================

@universal_bp.route("/api/v1/activity")
def api_v1_activity():
    project = request.args.get("project")
    agent = request.args.get("agent")
    model = request.args.get("model")
    action_type = request.args.get("type")
    limit = min(max(1, request.args.get("limit", 30, type=int)), 100)

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM agent_activity_log WHERE 1=1"
    params = []

    if project:
        query += " AND project_path = ?"
        params.append(project)
    if agent:
        query += " AND agent_name = ?"
        params.append(agent)
    if model:
        query += " AND model_id = ?"
        params.append(model)
    if action_type:
        query += " AND action_type = ?"
        params.append(action_type)

    query += f" ORDER BY created_at DESC LIMIT {limit}"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"ok": True, "activity": rows, "count": len(rows)})


# ============================================================
# GET /api/v1/health
# ============================================================

@universal_bp.route("/api/v1/health")
def api_v1_health():
    project = request.args.get("project", str(Path.cwd()))

    conn = get_db()
    cursor = conn.cursor()
    health = {"project": project}

    for key, table, where in [
        ("decisions", "decisions", "status='active'"),
        ("facts", "learned_facts", "is_active=1"),
        ("goals", "goals", "status='active'"),
        ("tasks", "tasks", "status IN ('todo','in_progress','blocked')"),
    ]:
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {where} AND project_path=?", (project,))
        health[key] = cursor.fetchone()[0]

    for key, table in [("patterns", "error_patterns"), ("checkpoints", "memory_checkpoints"),
                        ("resolutions", "error_resolutions")]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE project_path=?", (project,))
            health[key] = cursor.fetchone()[0]
        except Exception:
            health[key] = 0

    # Universal events count
    try:
        cursor.execute("SELECT COUNT(*) FROM universal_events WHERE project_path=?", (project,))
        health["events"] = cursor.fetchone()[0]
    except Exception:
        health["events"] = 0

    # Activity count
    try:
        cursor.execute("SELECT COUNT(*) FROM agent_activity_log WHERE project_path=?", (project,))
        health["activity_entries"] = cursor.fetchone()[0]
    except Exception:
        health["activity_entries"] = 0

    # Agent events count
    try:
        cursor.execute("SELECT COUNT(*) FROM agent_events WHERE project_path=?", (project,))
        health["agent_events"] = cursor.fetchone()[0]
    except Exception:
        health["agent_events"] = 0

    conn.close()
    return jsonify({"ok": True, **health})


# ============================================================
# POST /api/v1/agent-events — Agent Event Stream ingestion
# ============================================================

@universal_bp.route("/api/v1/agent-events", methods=["POST"])
def api_v1_agent_events_post():
    data, err = _parse_json()
    if err:
        return err

    event_type, err = _require(data, "event_type")
    if err:
        return err

    if event_type not in VALID_AGENT_EVENT_TYPES:
        return jsonify({"ok": False, "error": f"Invalid event_type. Valid: {', '.join(VALID_AGENT_EVENT_TYPES)}"}), 400

    meta = _extract_agent_meta(data)
    project = _project(data)

    event_id = log_agent_event(
        event_type=event_type,
        title=(data.get("title") or "").strip() or None,
        summary=(data.get("summary") or "").strip() or None,
        detail=(data.get("detail") or "").strip() or None,
        event_phase=(data.get("event_phase") or "end").strip(),
        status=(data.get("status") or "completed").strip(),
        project_path=project,
        session_id=meta["session_id"],
        branch_name=meta.get("branch"),
        cli_name=meta["cli_name"],
        agent_name=meta["agent_name"],
        provider=meta["provider"],
        model_name=meta["model_name"],
        related_table=(data.get("related_table") or "").strip() or None,
        related_id=data.get("related_id"),
        parent_event_id=data.get("parent_event_id"),
        started_at=(data.get("started_at") or "").strip() or None,
        finished_at=(data.get("finished_at") or "").strip() or None,
        duration_ms=data.get("duration_ms"),
        success_flag=0 if data.get("success_flag") == 0 or data.get("success_flag") is False else 1,
        metadata=data.get("metadata"),
    )

    if event_id:
        return _ok({"event_id": event_id, "event_type": event_type}), 201
    return jsonify({"ok": False, "error": "Failed to create event"}), 500


# ============================================================
# GET /api/v1/agent-events — Query agent events
# ============================================================

@universal_bp.route("/api/v1/agent-events")
def api_v1_agent_events_get():
    project = request.args.get("project")
    agent = request.args.get("agent")
    model = request.args.get("model")
    event_type = request.args.get("type")
    branch = request.args.get("branch")
    failed = request.args.get("failed")
    limit = min(max(1, request.args.get("limit", 30, type=int)), 200)

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM agent_events WHERE 1=1"
    params = []

    if project:
        query += " AND project_path = ?"
        params.append(project)
    if agent:
        query += " AND agent_name = ?"
        params.append(agent)
    if model:
        query += " AND model_name = ?"
        params.append(model)
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    if branch:
        query += " AND branch_name = ?"
        params.append(branch)
    if failed:
        query += " AND success_flag = 0"

    query += f" ORDER BY created_at DESC LIMIT {limit}"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"ok": True, "events": rows, "count": len(rows)})


# ============================================================
# GET /api/v1/search — Unified Cognitive Search
# ============================================================

@universal_bp.route("/api/v1/search")
def api_v1_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "Missing 'q' parameter"}), 400

    scope = request.args.get("scope", "all")
    limit = min(max(1, request.args.get("limit", 30, type=int)), 200)

    try:
        from cognitive_search import unified_search
        results, counts = unified_search(query, scope=scope, limit=limit)
        return jsonify({"ok": True, "query": query, "scope": scope,
                        "total": len(results), "source_counts": counts,
                        "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# POST /api/v1/capture — Raw data capture/ingest endpoint
# ============================================================

@universal_bp.route("/api/v1/capture", methods=["POST"])
def api_v1_capture():
    """Ingest raw data into memory (messages, tool_calls, errors).

    Accepts:
        type: "message" | "tool_call" | "error" | "bash"
        + type-specific fields
    """
    data, err = _parse_json()
    if err:
        return err

    capture_type = (data.get("type") or "").strip()
    if capture_type not in ("message", "tool_call", "error", "bash"):
        return jsonify({"ok": False,
            "error": "Invalid type. Valid: message, tool_call, error, bash"}), 400

    meta = _extract_agent_meta(data)
    if not meta["session_id"]:
        from datetime import datetime as _dt
        meta["session_id"] = f"capture_{_dt.now().strftime('%Y%m%d_%H%M%S')}"
    project = _project(data)

    conn = get_db()
    cursor = conn.cursor()

    try:
        if capture_type == "message":
            content = (data.get("content") or "").strip()
            if not content:
                return jsonify({"ok": False, "error": "Missing 'content'"}), 400
            cursor.execute("""
                INSERT INTO messages (session_id, timestamp, role, content, message_type, project_path)
                VALUES (?, datetime('now'), ?, ?, ?, ?)
            """, (meta["session_id"], data.get("role", "assistant"), content,
                  data.get("message_type", "capture"), project))

        elif capture_type == "tool_call":
            tool_name = (data.get("tool_name") or "").strip()
            if not tool_name:
                return jsonify({"ok": False, "error": "Missing 'tool_name'"}), 400
            cursor.execute("""
                INSERT INTO tool_calls (session_id, timestamp, tool_name, tool_input,
                    tool_result, exit_code, duration_ms, success, error_message, project_path, file_path)
                VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (meta["session_id"], tool_name, data.get("tool_input"),
                  data.get("tool_result"), data.get("exit_code"),
                  data.get("duration_ms"), 1 if data.get("success", True) else 0,
                  data.get("error_message"), project, data.get("file_path")))

        elif capture_type == "error":
            error_message = (data.get("error_message") or "").strip()
            if not error_message:
                return jsonify({"ok": False, "error": "Missing 'error_message'"}), 400

            import hashlib
            import re
            msg_norm = re.sub(r"'[^']*'", "'X'", error_message.lower())
            msg_norm = re.sub(r'"[^"]*"', '"X"', msg_norm)
            msg_norm = re.sub(r'\b\d+\b', 'N', msg_norm)
            fp_key = f"{(data.get('error_type') or 'unknown').lower()}::{msg_norm}"
            fp = hashlib.md5(fp_key.encode()).hexdigest()[:16]

            cursor.execute("""
                INSERT INTO errors_solutions
                (error_type, error_message, file_path, language, framework,
                 solution, solution_worked, resolved, created_at, session_id,
                 project_path, source, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)
            """, (data.get("error_type", "unknown"), error_message,
                  data.get("file_path"), data.get("language"),
                  data.get("framework"), data.get("solution"),
                  1 if data.get("solution_worked") else None,
                  1 if data.get("solution") else 0,
                  meta["session_id"], project,
                  data.get("source", "api_capture"), fp))

        elif capture_type == "bash":
            command = (data.get("command") or "").strip()
            if not command:
                return jsonify({"ok": False, "error": "Missing 'command'"}), 400
            cursor.execute("""
                INSERT INTO bash_history
                (session_id, timestamp, command, working_directory, exit_code,
                 output, error_output, duration_ms, project_path)
                VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """, (meta["session_id"], command, data.get("working_directory"),
                  data.get("exit_code"), data.get("output"),
                  data.get("error_output"), data.get("duration_ms"), project))

        conn.commit()
        row_id = cursor.lastrowid
        conn.close()

        return _ok({"id": row_id, "type": capture_type}), 201

    except Exception as e:
        conn.close()
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/errors/find — Error learning: find similar errors
# ============================================================

@universal_bp.route("/api/v1/errors/find")
def api_v1_errors_find():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "Missing 'q' parameter"}), 400

    limit = min(max(1, request.args.get("limit", 20, type=int)), 100)

    conn = get_db()
    cursor = conn.cursor()

    # Search error_resolutions (V2)
    cursor.execute("""
        SELECT id, error_summary, resolution, resolution_type, model_used,
               agent_name, worked, reuse_count, created_at
        FROM error_resolutions
        WHERE error_summary LIKE ? OR resolution LIKE ?
        ORDER BY worked DESC, reuse_count DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))
    structured = [dict(r) for r in cursor.fetchall()]

    # Search errors_solutions (raw)
    cursor.execute("""
        SELECT id, error_type, error_message, solution, solution_worked,
               resolved, language, file_path, created_at
        FROM errors_solutions
        WHERE error_message LIKE ? OR solution LIKE ?
        ORDER BY resolved DESC, solution_worked DESC LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))
    raw = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({"ok": True, "query": query,
                    "structured_resolutions": structured,
                    "raw_errors": raw,
                    "total": len(structured) + len(raw)})


# ============================================================
# GET /api/v1/traces — Reasoning Traces
# ============================================================

@universal_bp.route("/api/v1/traces")
def api_v1_traces():
    session = request.args.get("session")
    agent = request.args.get("agent")
    branch = request.args.get("branch")
    limit = min(max(1, request.args.get("limit", 100, type=int)), 500)

    try:
        from reasoning_trace import build_trace, trace_summary

        roots = build_trace(session_id=session, agent_name=agent, branch=branch, limit=limit)

        def _clean(events):
            result = []
            for e in events:
                ec = {k: v for k, v in e.items() if k != "_children"}
                children = e.get("_children", [])
                if children:
                    ec["children"] = _clean(children)
                result.append(ec)
            return result

        summary = trace_summary(roots)
        return jsonify({"ok": True, "trace": _clean(roots), "summary": summary})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/traces/entity — Trace per entity
# ============================================================

@universal_bp.route("/api/v1/traces/entity")
def api_v1_traces_entity():
    table = request.args.get("table", "").strip()
    entity_id = request.args.get("id", type=int)

    if not table or entity_id is None:
        return jsonify({"ok": False, "error": "Missing 'table' and 'id' parameters"}), 400

    try:
        from reasoning_trace import find_trace_for_entity, trace_summary

        roots = find_trace_for_entity(table, entity_id)

        def _clean(events):
            result = []
            for e in events:
                ec = {k: v for k, v in e.items() if k != "_children"}
                children = e.get("_children", [])
                if children:
                    ec["children"] = _clean(children)
                result.append(ec)
            return result

        summary = trace_summary(roots)
        return jsonify({"ok": True, "trace": _clean(roots), "summary": summary})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/replay — Experience Replay
# ============================================================

@universal_bp.route("/api/v1/replay")
def api_v1_replay():
    session = request.args.get("session")
    agent = request.args.get("agent")
    branch = request.args.get("branch")
    days = request.args.get("days", 7, type=int)
    limit = min(max(1, request.args.get("limit", 200, type=int)), 500)

    try:
        from experience_replay import (
            replay_session, replay_agent, replay_branch_rich, replay_summary,
        )

        if session:
            timeline = replay_session(session, limit=limit)
        elif agent:
            timeline = replay_agent(agent, days=days, limit=limit)
        elif branch:
            timeline = replay_branch_rich(branch, days=days, limit=limit)
        else:
            return jsonify({"ok": False, "error": "Provide 'session', 'agent', or 'branch' parameter"}), 400

        # Clean for JSON
        clean = []
        for item in timeline:
            c = {k: v for k, v in item.items() if not k.startswith("_") or k == "_entity"}
            if "_entity" in c:
                c["entity"] = {k: v for k, v in c.pop("_entity").items() if not k.startswith("_")}
            c["source"] = item.get("_source", "?")
            clean.append(c)

        summary = replay_summary(timeline)
        return jsonify({"ok": True, "replay": clean, "summary": summary})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/learnings/candidates — Cross-Agent Learning candidates
# ============================================================

@universal_bp.route("/api/v1/learnings/candidates")
def api_v1_learnings_candidates():
    threshold = request.args.get("threshold", 5, type=int)
    try:
        from cross_agent_learning import scan_candidates
        candidates = scan_candidates(threshold=threshold)
        return jsonify({"ok": True, "candidates": candidates, "count": len(candidates)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/learnings/suggest — Cross-Agent suggestions
# ============================================================

@universal_bp.route("/api/v1/learnings/suggest")
def api_v1_learnings_suggest():
    agent = request.args.get("agent", "").strip()
    if not agent:
        return jsonify({"ok": False, "error": "Missing 'agent' parameter"}), 400

    try:
        from cross_agent_learning import suggest_for_agent
        suggestions = suggest_for_agent(agent)
        return jsonify({"ok": True, "suggestions": suggestions, "count": len(suggestions)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/learnings/promoted — List promoted items
# ============================================================

@universal_bp.route("/api/v1/learnings/promoted")
def api_v1_learnings_promoted():
    try:
        from cross_agent_learning import list_promoted, stats
        items = list_promoted()
        s = stats()
        return jsonify({"ok": True, "promoted": items, "count": len(items), "stats": s})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# POST /api/v1/learnings/promote — Promote item to global
# ============================================================

@universal_bp.route("/api/v1/learnings/promote", methods=["POST"])
def api_v1_learnings_promote():
    data, err = _parse_json()
    if err:
        return err

    table, err = _require(data, "table")
    if err:
        return err
    entity_id = data.get("id")
    if entity_id is None:
        return jsonify({"ok": False, "error": "Field 'id' is required"}), 400

    if table not in CROSS_AGENT_TABLES:
        return jsonify({"ok": False,
            "error": f"Invalid table. Valid: {', '.join(CROSS_AGENT_TABLES)}"}), 400

    try:
        from cross_agent_learning import promote
        success = promote(table, int(entity_id))
        if success:
            return _ok({"table": table, "id": entity_id, "promoted": True})
        return jsonify({"ok": False, "error": "Item not found or promotion failed"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/memory/score — Score an entity
# ============================================================

@universal_bp.route("/api/v1/memory/score")
def api_v1_memory_score():
    table = request.args.get("table", "").strip()
    entity_id = request.args.get("id", type=int)

    if not table or entity_id is None:
        return jsonify({"ok": False, "error": "Missing 'table' and 'id' parameters"}), 400

    try:
        from memory_scoring import score_entity
        result = score_entity(table, entity_id)
        if result:
            return jsonify({"ok": True, **result})
        return jsonify({"ok": False, "error": "Entity not found or unsupported table"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/memory/scores — Score all entities
# ============================================================

@universal_bp.route("/api/v1/memory/scores")
def api_v1_memory_scores():
    table = request.args.get("table")
    limit = min(max(1, request.args.get("limit", 50, type=int)), 200)

    try:
        from memory_scoring import score_all
        results = score_all(table=table, limit=limit)
        return jsonify({"ok": True, "scores": results, "count": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/memory/suggest — Problem → Solution lookup
# ============================================================

@universal_bp.route("/api/v1/memory/suggest")
def api_v1_memory_suggest():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "Missing 'q' parameter"}), 400

    limit = min(max(1, request.args.get("limit", 10, type=int)), 50)

    try:
        from solution_index import suggest
        results = suggest(query, limit=limit)
        return jsonify({"ok": True, "query": query, "solutions": results, "count": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/memory/experiences — Experience graph for entity
# ============================================================

@universal_bp.route("/api/v1/memory/experiences")
def api_v1_memory_experiences():
    table = request.args.get("table", "").strip()
    entity_id = request.args.get("id", type=int)

    if not table or entity_id is None:
        return jsonify({"ok": False, "error": "Missing 'table' and 'id' parameters"}), 400

    try:
        from experience_graph import get_neighbors
        data = get_neighbors(table, entity_id)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# GET /api/v1/memory/agents — Agent reputations
# ============================================================

@universal_bp.route("/api/v1/memory/agents")
def api_v1_memory_agents():
    try:
        from memory_scoring import list_agents, recalc_agent_reputation
        agents = list_agents()
        if not agents:
            # Auto-calculate if empty
            recalc_agent_reputation()
            agents = list_agents()
        return jsonify({"ok": True, "agents": agents, "count": len(agents)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
