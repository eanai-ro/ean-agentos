#!/usr/bin/env python3
"""
Dashboard API - Flask Blueprint cu endpoint-uri V2 pentru dashboard memorie.

Endpoint-uri:
    GET /api/dashboard       Dashboard agregat
    GET /api/decisions       Decizii
    GET /api/facts           Facts
    GET /api/goals           Goals
    GET /api/tasks           Tasks
    GET /api/patterns        Error patterns
    GET /api/timeline        Timeline events
    GET /api/checkpoints     Checkpoints
    GET /api/context         Context builder output
    GET /api/health          Memory health counters
    GET /api/activity        Agent activity log

    POST /api/checkpoints/create    Create checkpoint
    POST /api/checkpoints/restore   Restore checkpoint
    POST /api/intent/set            Set current intent
    POST /api/model/set             Set current model
    POST /api/facts/pin             Pin a fact
    POST /api/facts/unpin           Unpin a fact
    POST /api/facts/promote         Promote fact (pin + set confidence=confirmed)
    POST /api/tasks/update-status   Update task status

    GET  /api/review/pending        Auto-extracted items pending review
    POST /api/review/approve        Approve an auto-extracted item
    POST /api/review/reject         Reject an auto-extracted item
    GET  /api/review/stats          Review statistics per type
"""

import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

# Ensure scripts dir is in path for v2_common imports
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from flask import Blueprint, jsonify, request

from v2_common import (
    get_db, get_current_project_path, get_current_model, get_current_intent,
    get_current_branch, set_current_branch, clear_current_branch,
    set_current_model, set_current_intent, invalidate_snapshot,
    log_agent_activity, log_agent_event,
    SNAPSHOT_FILE, VALID_INTENTS, VALID_TASK_STATUSES, BRANCH_ENTITY_TABLES,
)

dashboard_bp = Blueprint("dashboard_api", __name__)


def _get_project():
    """Returnează project_path din query param sau default."""
    return request.args.get("project", get_current_project_path())


def _get_limit(default=10, max_val=50):
    """Parse limit din query params cu validare."""
    try:
        val = int(request.args.get("limit", default))
        return min(max(1, val), max_val)
    except (ValueError, TypeError):
        return default


def _safe_json(val):
    """Parse JSON safely, return raw string on failure."""
    if not val:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def _snapshot_status():
    """Status snapshot cache."""
    if not SNAPSHOT_FILE.exists():
        return "none"
    try:
        data = json.loads(SNAPSHOT_FILE.read_text())
        gen_at = data.get("meta", {}).get("generated_at")
        if gen_at:
            dt = datetime.fromisoformat(gen_at)
            age_secs = (datetime.now() - dt).total_seconds()
            if age_secs < 600:
                return "valid"
            return "expired"
    except Exception:
        pass
    return "invalid"


# ============================================================
# GET /api/dashboard - Aggregated dashboard
# ============================================================

@dashboard_bp.route("/api/dashboard")
def api_dashboard():
    """Dashboard agregat — refolosește logica din dashboard_cli.build_dashboard."""
    project = _get_project()
    conn = get_db()
    cursor = conn.cursor()

    result = {}

    # Project summary
    model_id, provider = get_current_model()
    intent = get_current_intent()

    last_chk = None
    try:
        cursor.execute(
            "SELECT id, name, created_at FROM memory_checkpoints WHERE project_path=? ORDER BY created_at DESC LIMIT 1",
            (project,))
        row = cursor.fetchone()
        if row:
            last_chk = {"id": row["id"], "name": row["name"], "created_at": row["created_at"]}
    except Exception:
        pass

    result["summary"] = {
        "project_path": project,
        "project_name": project.split("/")[-1] if "/" in project else project,
        "model": model_id,
        "provider": provider,
        "intent": intent,
        "last_checkpoint": last_chk,
        "snapshot_status": _snapshot_status(),
    }

    # Decisions (max 5)
    cursor.execute("""
        SELECT id, title, category, confidence, status, created_at
        FROM decisions WHERE status='active' AND project_path=?
        ORDER BY created_at DESC LIMIT 5
    """, (project,))
    result["decisions"] = [dict(r) for r in cursor.fetchall()]

    # Conflict check
    try:
        from decision_analyzer import detect_conflicts
        conflicts = detect_conflicts(cursor, project)
        conflict_ids = set()
        for c in conflicts:
            conflict_ids.add(c.get("id_a"))
            conflict_ids.add(c.get("id_b"))
        for d in result["decisions"]:
            d["has_conflict"] = d["id"] in conflict_ids
    except Exception:
        pass

    # Facts (max 8)
    cursor.execute("""
        SELECT id, fact, fact_type, category, is_pinned, confidence
        FROM learned_facts WHERE is_active=1 AND project_path=?
        ORDER BY is_pinned DESC, created_at DESC LIMIT 8
    """, (project,))
    result["facts"] = [dict(r) for r in cursor.fetchall()]

    # Goals (max 5)
    cursor.execute("""
        SELECT g.id, g.title, g.priority, g.status, g.target_date,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id) as total_tasks,
               (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id AND t.status='done') as done_tasks
        FROM goals g WHERE g.status='active' AND g.project_path=?
        ORDER BY CASE g.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT 5
    """, (project,))
    result["goals"] = [dict(r) for r in cursor.fetchall()]

    # Tasks (max 8)
    cursor.execute("""
        SELECT id, title, priority, status, goal_id, blocked_by
        FROM tasks WHERE status IN ('in_progress','blocked','todo') AND project_path=?
        ORDER BY
            CASE status WHEN 'in_progress' THEN 0 WHEN 'blocked' THEN 1 WHEN 'todo' THEN 2 END,
            CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT 8
    """, (project,))
    result["tasks"] = [dict(r) for r in cursor.fetchall()]

    # Error intelligence
    cursor.execute("""
        SELECT id, error_summary, resolution, worked
        FROM error_resolutions WHERE project_path=? AND worked=1
        ORDER BY created_at DESC LIMIT 3
    """, (project,))
    result["resolutions"] = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT id, error_signature, solution, count
        FROM error_patterns WHERE project_path=?
        ORDER BY count DESC LIMIT 3
    """, (project,))
    result["patterns"] = [dict(r) for r in cursor.fetchall()]

    # Timeline recent (7 days)
    since = (datetime.now() - timedelta(days=7)).isoformat()
    events = []
    try:
        cursor.execute(
            "SELECT event_type, title, created_at FROM timeline_events WHERE project_path=? AND created_at>=? ORDER BY created_at DESC LIMIT 5",
            (project, since))
        for r in cursor.fetchall():
            events.append({"type": r["event_type"], "title": r["title"], "date": r["created_at"]})
    except Exception:
        pass
    cursor.execute(
        "SELECT title, created_at FROM decisions WHERE project_path=? AND created_at>=? ORDER BY created_at DESC LIMIT 3",
        (project, since))
    for r in cursor.fetchall():
        events.append({"type": "decision", "title": r["title"], "date": r["created_at"]})
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    result["timeline"] = events[:8]

    # Activity recent
    try:
        cursor.execute("""
            SELECT agent_name, model_id, action_type, action_summary, success, created_at
            FROM agent_activity_log
            WHERE project_path=? AND created_at>=?
            ORDER BY created_at DESC LIMIT 5
        """, (project, since))
        result["activity_recent"] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        result["activity_recent"] = []

    # Agent events recent
    try:
        cursor.execute("""
            SELECT event_type, title, agent_name, model_name, success_flag, created_at
            FROM agent_events
            WHERE project_path=? AND created_at>=?
            ORDER BY created_at DESC LIMIT 5
        """, (project, since))
        result["events_recent"] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        result["events_recent"] = []

    # Health
    result["health"] = _build_health(cursor, project)

    conn.close()
    return jsonify(result)


# ============================================================
# GET /api/activity
# ============================================================

@dashboard_bp.route("/api/activity")
def api_activity():
    project = _get_project()
    limit = _get_limit(30, 100)
    agent = request.args.get("agent")
    model = request.args.get("model")
    action_type = request.args.get("type")
    failed_only = request.args.get("failed") == "true"

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
    if failed_only:
        query += " AND success = 0"

    query += f" ORDER BY created_at DESC LIMIT {limit}"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"activity": rows, "count": len(rows)})


# ============================================================
# GET /api/decisions
# ============================================================

@dashboard_bp.route("/api/decisions")
def api_decisions():
    project = _get_project()
    status = request.args.get("status", "active")
    limit = _get_limit(10, 50)

    conn = get_db()
    cursor = conn.cursor()

    if status == "all":
        cursor.execute("""
            SELECT id, title, description, category, status, confidence, rationale,
                   stale_after_days, model_used, provider, created_at, updated_at
            FROM decisions WHERE project_path=?
            ORDER BY created_at DESC LIMIT ?
        """, (project, limit))
    else:
        cursor.execute("""
            SELECT id, title, description, category, status, confidence, rationale,
                   stale_after_days, model_used, provider, created_at, updated_at
            FROM decisions WHERE status=? AND project_path=?
            ORDER BY created_at DESC LIMIT ?
        """, (status, project, limit))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"decisions": rows, "count": len(rows), "project": project})


# ============================================================
# GET /api/facts
# ============================================================

@dashboard_bp.route("/api/facts")
def api_facts():
    project = _get_project()
    limit = _get_limit(10, 50)
    pinned = request.args.get("pinned")

    conn = get_db()
    cursor = conn.cursor()

    sql = "SELECT id, fact, fact_type, category, confidence, is_pinned, source, created_at FROM learned_facts WHERE is_active=1 AND project_path=?"
    params = [project]

    if pinned == "true":
        sql += " AND is_pinned=1"
    elif pinned == "false":
        sql += " AND is_pinned=0"

    sql += " ORDER BY is_pinned DESC, created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"facts": rows, "count": len(rows), "project": project})


# ============================================================
# GET /api/goals
# ============================================================

@dashboard_bp.route("/api/goals")
def api_goals():
    project = _get_project()
    status = request.args.get("status", "active")
    limit = _get_limit(10, 50)

    conn = get_db()
    cursor = conn.cursor()

    if status == "all":
        cursor.execute("""
            SELECT g.id, g.title, g.description, g.priority, g.status, g.target_date,
                   g.completed_at, g.created_at,
                   (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id) as total_tasks,
                   (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id AND t.status='done') as done_tasks
            FROM goals g WHERE g.project_path=?
            ORDER BY g.created_at DESC LIMIT ?
        """, (project, limit))
    else:
        cursor.execute("""
            SELECT g.id, g.title, g.description, g.priority, g.status, g.target_date,
                   g.completed_at, g.created_at,
                   (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id) as total_tasks,
                   (SELECT COUNT(*) FROM tasks t WHERE t.goal_id=g.id AND t.status='done') as done_tasks
            FROM goals g WHERE g.status=? AND g.project_path=?
            ORDER BY CASE g.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
            LIMIT ?
        """, (status, project, limit))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"goals": rows, "count": len(rows), "project": project})


# ============================================================
# GET /api/tasks
# ============================================================

@dashboard_bp.route("/api/tasks")
def api_tasks():
    project = _get_project()
    status = request.args.get("status")
    limit = _get_limit(10, 50)

    conn = get_db()
    cursor = conn.cursor()

    sql = """SELECT id, title, description, priority, status, goal_id, blocked_by, created_at, updated_at
             FROM tasks WHERE project_path=?"""
    params = [project]

    if status:
        sql += " AND status=?"
        params.append(status)
    else:
        sql += " AND status IN ('in_progress','blocked','todo')"

    sql += """ ORDER BY
        CASE status WHEN 'in_progress' THEN 0 WHEN 'blocked' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END,
        CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT ?"""
    params.append(limit)

    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"tasks": rows, "count": len(rows), "project": project})


# ============================================================
# GET /api/patterns
# ============================================================

@dashboard_bp.route("/api/patterns")
def api_patterns():
    project = _get_project()
    limit = _get_limit(10, 30)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, error_signature, solution, count, first_seen, last_seen
        FROM error_patterns WHERE project_path=?
        ORDER BY count DESC LIMIT ?
    """, (project, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"patterns": rows, "count": len(rows), "project": project})


# ============================================================
# GET /api/timeline
# ============================================================

@dashboard_bp.route("/api/timeline")
def api_timeline():
    project = _get_project()
    days = request.args.get("days", 30, type=int)
    limit = _get_limit(20, 100)
    since = (datetime.now() - timedelta(days=days)).isoformat()

    conn = get_db()
    cursor = conn.cursor()
    events = []

    # Timeline events table
    try:
        cursor.execute(
            "SELECT event_type, event_id, title, detail, created_at FROM timeline_events WHERE project_path=? AND created_at>=? ORDER BY created_at DESC LIMIT ?",
            (project, since, limit))
        for r in cursor.fetchall():
            events.append({"type": r["event_type"], "id": r["event_id"],
                           "title": r["title"], "detail": r["detail"], "date": r["created_at"]})
    except Exception:
        pass

    # Decisions
    cursor.execute(
        "SELECT id, title, category, created_at FROM decisions WHERE project_path=? AND created_at>=? ORDER BY created_at DESC LIMIT ?",
        (project, since, limit))
    for r in cursor.fetchall():
        events.append({"type": "decision", "id": r["id"],
                       "title": r["title"], "detail": r["category"], "date": r["created_at"]})

    # Pinned facts
    cursor.execute(
        "SELECT id, fact, updated_at FROM learned_facts WHERE is_pinned=1 AND project_path=? AND updated_at>=? ORDER BY updated_at DESC LIMIT ?",
        (project, since, limit))
    for r in cursor.fetchall():
        events.append({"type": "fact_promoted", "id": r["id"],
                       "title": r["fact"], "detail": None, "date": r["updated_at"]})

    # Error patterns
    cursor.execute(
        "SELECT id, error_signature, count, last_seen FROM error_patterns WHERE project_path=? AND last_seen>=? ORDER BY last_seen DESC LIMIT ?",
        (project, since, limit))
    for r in cursor.fetchall():
        events.append({"type": "pattern_detected", "id": r["id"],
                       "title": r["error_signature"], "detail": f"x{r['count']}", "date": r["last_seen"]})

    events.sort(key=lambda e: e.get("date") or "", reverse=True)

    conn.close()
    return jsonify({"timeline": events[:limit], "count": len(events[:limit]),
                     "days": days, "project": project})


# ============================================================
# GET /api/checkpoints
# ============================================================

@dashboard_bp.route("/api/checkpoints")
def api_checkpoints():
    project = _get_project()
    limit = _get_limit(10, 50)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, description, created_at, model, intent, context_mode,
               decisions_count, facts_count, goals_count, tasks_count, patterns_count, restored_count
        FROM memory_checkpoints WHERE project_path=?
        ORDER BY created_at DESC LIMIT ?
    """, (project, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"checkpoints": rows, "count": len(rows), "project": project})


# ============================================================
# GET /api/context
# ============================================================

@dashboard_bp.route("/api/context")
def api_context():
    project = _get_project()
    mode = request.args.get("mode", "compact")
    budget = request.args.get("budget", type=int)

    valid_modes = ("compact", "full", "survival", "delta")
    if mode not in valid_modes:
        return jsonify({"error": f"Invalid mode: {mode}. Valid: {', '.join(valid_modes)}"}), 400

    try:
        from context_builder_v2 import build_context
        import io
        from contextlib import redirect_stdout

        # Capture JSON output
        old_argv = sys.argv
        sys.argv = ["context_builder_v2.py"]

        # Build context data directly (reuse internal logic)
        from context_builder_v2 import (
            fetch_project_profile, fetch_decisions, fetch_facts, fetch_goals,
            fetch_tasks, fetch_resolutions, to_json_output, _get_limits,
        )

        intent = get_current_intent()
        is_compact = mode in ("compact", "survival")
        d_limit, f_limit, g_limit, t_limit, r_limit = _get_limits(mode, intent)

        conn = get_db()
        cursor = conn.cursor()
        model_id, provider = get_current_model()
        profile = fetch_project_profile(cursor, project)
        decisions = fetch_decisions(cursor, project, d_limit, intent, is_compact)
        facts = fetch_facts(cursor, project, f_limit, intent, is_compact)
        goals = fetch_goals(cursor, project, g_limit, intent, is_compact)
        tasks = fetch_tasks(cursor, project, t_limit, intent, is_compact)
        resolutions = fetch_resolutions(cursor, project, r_limit, intent, is_compact)
        conn.close()

        json_data = to_json_output(model_id, provider, profile, decisions, facts,
                                    goals, tasks, resolutions, intent, mode)

        sys.argv = old_argv
        return jsonify(json_data)

    except Exception as e:
        return jsonify({"error": f"Context build failed: {str(e)}"}), 500


# ============================================================
# GET /api/health
# ============================================================

@dashboard_bp.route("/api/health")
def api_health():
    project = _get_project()
    conn = get_db()
    cursor = conn.cursor()
    result = _build_health(cursor, project)
    conn.close()
    return jsonify(result)


# ============================================================
# POST /api/checkpoints/create
# ============================================================

@dashboard_bp.route("/api/checkpoints/create", methods=["POST"])
def api_checkpoint_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "message": "Checkpoint name is required"}), 400

    description = (data.get("description") or "").strip()
    project = data.get("project") or get_current_project_path()
    mode = data.get("mode") or "auto"

    conn = get_db()
    cursor = conn.cursor()
    model_id, _ = get_current_model()
    intent = get_current_intent()

    # Collect entities
    cursor.execute("SELECT * FROM decisions WHERE status='active' AND project_path=?", (project,))
    decisions = cursor.fetchall()

    if mode == "compact":
        cursor.execute("SELECT * FROM learned_facts WHERE is_active=1 AND is_pinned=1 AND project_path=?", (project,))
    else:
        cursor.execute("SELECT * FROM learned_facts WHERE is_active=1 AND project_path=?", (project,))
    facts = cursor.fetchall()

    cursor.execute("SELECT * FROM goals WHERE status='active' AND project_path=?", (project,))
    goals = cursor.fetchall()

    cursor.execute("SELECT * FROM tasks WHERE status IN ('todo','in_progress','blocked') AND project_path=?", (project,))
    tasks = cursor.fetchall()

    cursor.execute("SELECT * FROM error_patterns WHERE project_path=?", (project,))
    patterns = cursor.fetchall()

    # Create checkpoint
    cursor.execute("""
        INSERT INTO memory_checkpoints
        (project_path, name, description, model, intent, context_mode,
         decisions_count, facts_count, goals_count, tasks_count, patterns_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (project, name, description, model_id, intent, mode,
          len(decisions), len(facts), len(goals), len(tasks), len(patterns)))
    checkpoint_id = cursor.lastrowid

    # Save snapshots
    for d in decisions:
        cursor.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
                       (checkpoint_id, "decision", d["id"], json.dumps(dict(d))))
    for f in facts:
        cursor.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
                       (checkpoint_id, "fact", f["id"], json.dumps(dict(f))))
    for g in goals:
        cursor.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
                       (checkpoint_id, "goal", g["id"], json.dumps(dict(g))))
    for t in tasks:
        cursor.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
                       (checkpoint_id, "task", t["id"], json.dumps(dict(t))))
    for p in patterns:
        cursor.execute("INSERT INTO checkpoint_data (checkpoint_id, entity_type, entity_id, snapshot_json) VALUES (?,?,?,?)",
                       (checkpoint_id, "pattern", p["id"], json.dumps(dict(p))))

    total = len(decisions) + len(facts) + len(goals) + len(tasks) + len(patterns)

    # Timeline event
    cursor.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path) VALUES (?,?,?,?,?)",
                   ("checkpoint_create", checkpoint_id, f"Checkpoint: {name}", f"{total} entities saved", project))

    conn.commit()
    conn.close()

    log_agent_activity("checkpoint", f"Create via UI: {name} ({total} entities)", "checkpoint", checkpoint_id)
    log_agent_event(
        "checkpoint_created", title=f"Checkpoint: {name}",
        summary=f"{total} entities saved", related_table="memory_checkpoints",
        related_id=checkpoint_id, project_path=project,
    )

    return jsonify({
        "success": True,
        "message": f"Checkpoint '{name}' created with {total} entities",
        "checkpoint_id": checkpoint_id,
        "entities": total,
    })


# ============================================================
# POST /api/checkpoints/restore
# ============================================================

@dashboard_bp.route("/api/checkpoints/restore", methods=["POST"])
def api_checkpoint_restore():
    data = request.get_json(silent=True) or {}
    checkpoint_id = data.get("id")
    confirm = data.get("confirm", False)

    if not checkpoint_id:
        return jsonify({"success": False, "message": "Checkpoint ID is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM memory_checkpoints WHERE id=?", (checkpoint_id,))
    chk = cursor.fetchone()

    if not chk:
        conn.close()
        return jsonify({"success": False, "message": f"Checkpoint #{checkpoint_id} not found"}), 404

    total = chk["decisions_count"] + chk["facts_count"] + chk["goals_count"] + chk["tasks_count"]

    if not confirm:
        conn.close()
        return jsonify({
            "success": False,
            "needs_confirm": True,
            "message": f"Restore '{chk['name']}'? This will archive current entities and restore {total} from checkpoint.",
            "checkpoint": {"id": chk["id"], "name": chk["name"], "created_at": chk["created_at"], "entities": total},
        })

    project = chk["project_path"]
    now = datetime.now().isoformat()

    # Archive current
    cursor.execute("UPDATE decisions SET status='archived', updated_at=? WHERE status='active' AND project_path=?", (now, project))
    cursor.execute("UPDATE learned_facts SET is_active=0, updated_at=? WHERE is_active=1 AND project_path=?", (now, project))
    cursor.execute("UPDATE goals SET status='paused', updated_at=? WHERE status='active' AND project_path=?", (now, project))
    cursor.execute("UPDATE tasks SET status='cancelled', updated_at=? WHERE status IN ('todo','in_progress','blocked') AND project_path=?", (now, project))

    # Restore from snapshot
    cursor.execute("SELECT entity_type, entity_id, snapshot_json FROM checkpoint_data WHERE checkpoint_id=?", (checkpoint_id,))
    restored = 0
    for row in cursor.fetchall():
        etype = row["entity_type"]
        d = json.loads(row["snapshot_json"])
        if etype == "decision":
            cursor.execute("SELECT id FROM decisions WHERE id=?", (d["id"],))
            if cursor.fetchone():
                cursor.execute("UPDATE decisions SET status=?, confidence=?, updated_at=? WHERE id=?",
                               (d.get("status", "active"), d.get("confidence", "high"), now, d["id"]))
            restored += 1
        elif etype == "fact":
            cursor.execute("SELECT id FROM learned_facts WHERE id=?", (d["id"],))
            if cursor.fetchone():
                cursor.execute("UPDATE learned_facts SET is_active=1, is_pinned=?, updated_at=? WHERE id=?",
                               (d.get("is_pinned", 0), now, d["id"]))
            restored += 1
        elif etype == "goal":
            cursor.execute("SELECT id FROM goals WHERE id=?", (d["id"],))
            if cursor.fetchone():
                cursor.execute("UPDATE goals SET status=?, priority=?, updated_at=? WHERE id=?",
                               (d.get("status", "active"), d.get("priority", "medium"), now, d["id"]))
            restored += 1
        elif etype == "task":
            cursor.execute("SELECT id FROM tasks WHERE id=?", (d["id"],))
            if cursor.fetchone():
                cursor.execute("UPDATE tasks SET status=?, priority=?, updated_at=? WHERE id=?",
                               (d.get("status", "todo"), d.get("priority", "medium"), now, d["id"]))
            restored += 1

    cursor.execute("UPDATE memory_checkpoints SET restored_count = restored_count + 1 WHERE id=?", (checkpoint_id,))
    cursor.execute("INSERT INTO timeline_events (event_type, event_id, title, detail, project_path) VALUES (?,?,?,?,?)",
                   ("checkpoint_restore", checkpoint_id, f"Restored: {chk['name']}", f"{restored} entities", project))

    conn.commit()
    conn.close()

    log_agent_activity("checkpoint", f"Restore via UI: {chk['name']} ({restored} entities)", "checkpoint", checkpoint_id)
    log_agent_event(
        "checkpoint_restored", title=f"Restored: {chk['name']}",
        summary=f"{restored} entities restored", related_table="memory_checkpoints",
        related_id=checkpoint_id, project_path=project,
    )

    return jsonify({
        "success": True,
        "message": f"Checkpoint '{chk['name']}' restored ({restored} entities)",
        "restored": restored,
    })


# ============================================================
# POST /api/intent/set
# ============================================================

@dashboard_bp.route("/api/intent/set", methods=["POST"])
def api_set_intent():
    data = request.get_json(silent=True) or {}
    intent = (data.get("intent") or "").strip()

    if not intent:
        return jsonify({"success": False, "message": "Intent is required"}), 400

    if intent not in VALID_INTENTS:
        return jsonify({"success": False, "message": f"Invalid intent. Valid: {', '.join(VALID_INTENTS)}"}), 400

    set_current_intent(intent)
    invalidate_snapshot()
    log_agent_activity("session_start", f"Set intent via UI: {intent}")

    return jsonify({"success": True, "message": f"Intent set to '{intent}'", "intent": intent})


# ============================================================
# POST /api/model/set
# ============================================================

@dashboard_bp.route("/api/model/set", methods=["POST"])
def api_set_model():
    data = request.get_json(silent=True) or {}
    model_id = (data.get("model_id") or "").strip()
    provider = (data.get("provider") or "anthropic").strip()

    if not model_id:
        return jsonify({"success": False, "message": "model_id is required"}), 400

    set_current_model(model_id, provider)
    invalidate_snapshot()
    log_agent_activity("session_start", f"Set model via UI: {model_id} ({provider})")

    return jsonify({"success": True, "message": f"Model set to '{model_id}' ({provider})", "model_id": model_id, "provider": provider})


# ============================================================
# POST /api/facts/pin, /api/facts/unpin, /api/facts/promote
# ============================================================

@dashboard_bp.route("/api/facts/pin", methods=["POST"])
def api_fact_pin():
    return _update_fact_pin(True)


@dashboard_bp.route("/api/facts/unpin", methods=["POST"])
def api_fact_unpin():
    return _update_fact_pin(False)


def _update_fact_pin(pin_value):
    data = request.get_json(silent=True) or {}
    fact_id = data.get("id")
    if not fact_id:
        return jsonify({"success": False, "message": "Fact ID is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact, is_active, is_pinned FROM learned_facts WHERE id=?", (fact_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": f"Fact #{fact_id} not found"}), 404

    if not row["is_active"]:
        conn.close()
        return jsonify({"success": False, "message": f"Fact #{fact_id} is inactive"}), 400

    action = "pin" if pin_value else "unpin"
    cursor.execute("UPDATE learned_facts SET is_pinned=?, updated_at=datetime('now') WHERE id=?",
                   (1 if pin_value else 0, fact_id))
    conn.commit()
    conn.close()

    log_agent_activity("learn", f"{action.title()} fact #{fact_id} via UI", "fact", fact_id)

    return jsonify({"success": True, "message": f"Fact #{fact_id} {action}ned", "id": fact_id, "is_pinned": 1 if pin_value else 0})


@dashboard_bp.route("/api/facts/promote", methods=["POST"])
def api_fact_promote():
    """Promote = pin + set confidence to confirmed."""
    data = request.get_json(silent=True) or {}
    fact_id = data.get("id")
    if not fact_id:
        return jsonify({"success": False, "message": "Fact ID is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact, is_active FROM learned_facts WHERE id=?", (fact_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": f"Fact #{fact_id} not found"}), 404

    if not row["is_active"]:
        conn.close()
        return jsonify({"success": False, "message": f"Fact #{fact_id} is inactive"}), 400

    cursor.execute("UPDATE learned_facts SET is_pinned=1, confidence='confirmed', updated_at=datetime('now') WHERE id=?", (fact_id,))
    conn.commit()
    conn.close()

    log_agent_activity("learn", f"Promote fact #{fact_id} via UI (pin+confirmed)", "fact", fact_id)

    return jsonify({"success": True, "message": f"Fact #{fact_id} promoted (pinned + confirmed)", "id": fact_id})


# ============================================================
# POST /api/tasks/update-status
# ============================================================

@dashboard_bp.route("/api/tasks/update-status", methods=["POST"])
def api_task_update_status():
    data = request.get_json(silent=True) or {}
    task_id = data.get("id")
    new_status = (data.get("status") or "").strip()

    if not task_id:
        return jsonify({"success": False, "message": "Task ID is required"}), 400

    allowed = ("in_progress", "done", "blocked")
    if new_status not in allowed:
        return jsonify({"success": False, "message": f"Invalid status. Allowed: {', '.join(allowed)}"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, status FROM tasks WHERE id=?", (task_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": f"Task #{task_id} not found"}), 404

    extra = ""
    if new_status == "done":
        extra = ", resolved_at=datetime('now')"
    elif new_status == "blocked":
        blocked_by = data.get("blocked_by", "")
        if blocked_by:
            extra = f", blocked_by=?"

    if new_status == "blocked" and data.get("blocked_by"):
        cursor.execute(f"UPDATE tasks SET status=?, updated_at=datetime('now'){extra} WHERE id=?",
                       (new_status, data["blocked_by"], task_id))
    else:
        cursor.execute(f"UPDATE tasks SET status=?, updated_at=datetime('now'){extra} WHERE id=?",
                       (new_status, task_id))

    conn.commit()
    conn.close()

    log_agent_activity("task", f"Task #{task_id} → {new_status} via UI", "task", task_id)

    return jsonify({
        "success": True,
        "message": f"Task #{task_id} → {new_status}",
        "id": task_id,
        "old_status": row["status"],
        "new_status": new_status,
    })


# ============================================================
# GET /api/branches — List all branches
# ============================================================

@dashboard_bp.route("/api/branches")
def api_branches():
    project = _get_project()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, parent_branch, description, created_at, is_active
        FROM memory_branches WHERE project_path=? AND is_active=1
        ORDER BY created_at
    """, (project,))
    branches = [dict(r) for r in cursor.fetchall()]

    # Count entities per branch
    counts = {}
    for table in BRANCH_ENTITY_TABLES:
        try:
            cursor.execute(f"SELECT branch, COUNT(*) as cnt FROM {table} WHERE project_path=? GROUP BY branch", (project,))
            for row in cursor.fetchall():
                b = row["branch"] or "main"
                counts.setdefault(b, 0)
                counts[b] += row["cnt"]
        except Exception:
            pass

    # Always include main
    result = [{"name": "main", "parent_branch": None, "description": None,
               "created_at": None, "entity_count": counts.get("main", 0)}]
    for b in branches:
        b["entity_count"] = counts.get(b["name"], 0)
        result.append(b)

    current = get_current_branch()
    conn.close()
    return jsonify({"branches": result, "current": current, "count": len(result), "project": project})


# ============================================================
# GET /api/branches/compare — Compare two branches
# ============================================================

@dashboard_bp.route("/api/branches/compare")
def api_branches_compare():
    project = _get_project()
    branch_a = request.args.get("a", "main")
    branch_b = request.args.get("b")

    if not branch_b:
        return jsonify({"error": "Query param 'b' is required (branch to compare)"}), 400

    conn = get_db()
    cursor = conn.cursor()

    from branch_manager import compare_branches, _ensure_branch_exists
    for b in (branch_a, branch_b):
        if not _ensure_branch_exists(conn, b, project):
            conn.close()
            return jsonify({"error": f"Branch '{b}' does not exist"}), 404

    data = compare_branches(cursor, branch_a, branch_b, project)
    conn.close()
    return jsonify(data)


# ============================================================
# GET /api/branches/replay — Replay branch history
# ============================================================

@dashboard_bp.route("/api/branches/replay")
def api_branches_replay():
    project = _get_project()
    branch = request.args.get("branch", "main")
    days = request.args.get("days", type=int)
    limit = min(max(1, request.args.get("limit", 50, type=int)), 200)

    conn = get_db()
    cursor = conn.cursor()

    from branch_manager import replay_branch, _ensure_branch_exists
    if not _ensure_branch_exists(conn, branch, project):
        conn.close()
        return jsonify({"error": f"Branch '{branch}' does not exist"}), 404

    since_date = None
    if days:
        from datetime import timedelta as td
        since_date = (datetime.now() - td(days=days)).isoformat()

    events = replay_branch(cursor, branch, project, since_date, limit)
    conn.close()

    return jsonify({"branch": branch, "events": events, "count": len(events), "project": project})


# ============================================================
# POST /api/branches — Create a new branch
# ============================================================

@dashboard_bp.route("/api/branches", methods=["POST"])
def api_branches_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip() or None
    parent = (data.get("parent") or data.get("from") or "main").strip()
    project = data.get("project") or get_current_project_path()
    agent = (data.get("agent_name") or "").strip() or None

    if not name:
        return jsonify({"success": False, "message": "Branch name is required"}), 400

    if name == "main":
        return jsonify({"success": False, "message": "Cannot create branch 'main' (reserved)"}), 400

    conn = get_db()
    cursor = conn.cursor()

    from branch_manager import _ensure_branch_exists
    if not _ensure_branch_exists(conn, parent, project):
        conn.close()
        return jsonify({"success": False, "message": f"Parent branch '{parent}' does not exist"}), 404

    try:
        cursor.execute("""
            INSERT INTO memory_branches (name, project_path, parent_branch, description, created_by)
            VALUES (?, ?, ?, ?, 'api')
        """, (name, project, parent, description))
        conn.commit()
        conn.close()
        log_agent_activity("branch", f"Created branch '{name}' (parent: {parent}) via API", agent_name=agent)
        log_agent_event("branch_created", title=f"Branch '{name}' created", project_path=project, agent_name=agent)
        return jsonify({
            "success": True,
            "message": f"Branch '{name}' created",
            "branch": name,
            "parent": parent,
        }), 201
    except Exception as e:
        conn.close()
        if "UNIQUE constraint" in str(e):
            return jsonify({"success": False, "message": f"Branch '{name}' already exists"}), 409
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================
# DELETE /api/branches — Delete a branch
# ============================================================

@dashboard_bp.route("/api/branches/<branch_name>", methods=["DELETE"])
def api_branches_delete(branch_name):
    branch_name = branch_name.strip()
    data = request.get_json(silent=True) or {}
    project = data.get("project") or request.args.get("project") or get_current_project_path()
    agent = (data.get("agent_name") or request.args.get("agent_name") or "").strip() or None

    if branch_name == "main":
        return jsonify({"success": False, "message": "Cannot delete branch 'main' (reserved)"}), 400

    conn = get_db()
    cursor = conn.cursor()

    from branch_manager import _ensure_branch_exists
    if not _ensure_branch_exists(conn, branch_name, project):
        conn.close()
        return jsonify({"success": False, "message": f"Branch '{branch_name}' does not exist"}), 404

    # Count entities on this branch before deleting
    entity_count = 0
    for table in ["decisions", "learned_facts", "tasks", "error_resolutions"]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE branch = ? AND project_path = ?",
                           (branch_name, project))
            entity_count += cursor.fetchone()[0]
        except Exception:
            pass

    try:
        cursor.execute("DELETE FROM memory_branches WHERE name = ? AND project_path = ?",
                       (branch_name, project))
        conn.commit()
        conn.close()
        log_agent_activity("branch", f"Deleted branch '{branch_name}' ({entity_count} entities) via API", agent_name=agent)
        log_agent_event("branch_deleted", title=f"Branch '{branch_name}' deleted", project_path=project, agent_name=agent)
        return jsonify({
            "success": True,
            "message": f"Branch '{branch_name}' deleted",
            "branch": branch_name,
            "entities_orphaned": entity_count,
        })
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================
# POST /api/branches/switch — Switch branch
# ============================================================

@dashboard_bp.route("/api/branches/switch", methods=["POST"])
def api_branches_switch():
    data = request.get_json(silent=True) or {}
    branch = (data.get("branch") or "").strip()
    project = data.get("project") or get_current_project_path()
    agent = (data.get("agent_name") or "").strip() or None

    if not branch:
        return jsonify({"success": False, "message": "Branch name is required"}), 400

    if branch == "main":
        clear_current_branch()
        log_agent_activity("branch", "Switch to main via API", agent_name=agent)
        log_agent_event("branch_switched", title="Switch to main", project_path=project, agent_name=agent)
        return jsonify({"success": True, "message": "Switched to branch: main", "branch": "main"})

    conn = get_db()
    from branch_manager import _ensure_branch_exists
    if not _ensure_branch_exists(conn, branch, project):
        conn.close()
        return jsonify({"success": False, "message": f"Branch '{branch}' does not exist"}), 404

    conn.close()
    set_current_branch(branch)
    log_agent_activity("branch", f"Switch to {branch} via API", agent_name=agent)
    log_agent_event("branch_switched", title=f"Switch to {branch}", project_path=project, agent_name=agent)
    return jsonify({"success": True, "message": f"Switched to branch: {branch}", "branch": branch})


# ============================================================
# POST /api/branches/merge — Merge branch
# ============================================================

@dashboard_bp.route("/api/branches/merge", methods=["POST"])
def api_branches_merge():
    data = request.get_json(silent=True) or {}
    source = (data.get("source") or "").strip()
    target = (data.get("target") or "main").strip()
    confirm = data.get("confirm", False)
    strategy = data.get("strategy", "merge")
    project = data.get("project") or get_current_project_path()
    agent = (data.get("agent_name") or "").strip() or None

    if not source:
        return jsonify({"success": False, "message": "Source branch is required"}), 400

    if source == target:
        return jsonify({"success": False, "message": "Source and target cannot be the same"}), 400

    conn = get_db()
    cursor = conn.cursor()

    from branch_manager import _ensure_branch_exists, compare_branches
    for b in (source, target):
        if not _ensure_branch_exists(conn, b, project):
            conn.close()
            return jsonify({"success": False, "message": f"Branch '{b}' does not exist"}), 404

    # Preview (compare)
    preview = compare_branches(cursor, source, target, project)

    if not confirm:
        conn.close()
        return jsonify({
            "success": False,
            "needs_confirm": True,
            "message": f"Merge '{source}' into '{target}'?",
            "preview": preview,
        })

    # Execute merge
    total_merged = 0
    for table in BRANCH_ENTITY_TABLES:
        try:
            cursor.execute(f"UPDATE {table} SET branch=? WHERE branch=? AND project_path=?",
                          (target, source, project))
            total_merged += cursor.rowcount
        except Exception:
            pass

    # Log merge
    conflicts_count = preview.get("summary", {}).get("conflicts", 0)
    cursor.execute("""
        INSERT INTO branch_merge_log
        (source_branch, target_branch, project_path, strategy, conflicts_found, entities_merged)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (source, target, project, strategy, conflicts_count, total_merged))

    conn.commit()
    conn.close()

    log_agent_activity("branch", f"Merge {source} → {target} via API ({total_merged} entities)", "branch", agent_name=agent)
    log_agent_event(
        "branch_merged", title=f"Merge {source} → {target}",
        summary=f"{total_merged} entities merged", project_path=project, agent_name=agent,
        metadata={"source": source, "target": target, "entities": total_merged, "conflicts": conflicts_count},
    )

    return jsonify({
        "success": True,
        "message": f"Merge completed: {source} → {target} ({total_merged} entities)",
        "entities_merged": total_merged,
        "conflicts": conflicts_count,
    })


# ============================================================
# GET /api/errors — Erori și soluții (din errors_solutions)
# ============================================================

@dashboard_bp.route("/api/errors")
def api_errors():
    project = request.args.get("project")
    filter_type = request.args.get("filter", "all")
    limit = _get_limit(30, 100)

    conn = get_db()
    cursor = conn.cursor()

    sql = "SELECT id, error_type, error_message, solution, solution_worked, file_path, language, framework, created_at, resolved_at, project_path FROM errors_solutions WHERE 1=1"
    params = []

    if project:
        sql += " AND project_path = ?"
        params.append(project)

    if filter_type == "resolved":
        sql += " AND solution IS NOT NULL AND solution_worked = 1"
    elif filter_type == "unresolved":
        sql += " AND (solution IS NULL OR solution_worked IS NULL OR solution_worked = 0)"

    sql += f" ORDER BY created_at DESC LIMIT {limit}"
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"errors": rows, "count": len(rows)})


# ============================================================
# GET /api/events — Agent event stream
# ============================================================

@dashboard_bp.route("/api/events")
def api_events():
    project = request.args.get("project")
    agent = request.args.get("agent")
    model = request.args.get("model")
    event_type = request.args.get("type")
    branch = request.args.get("branch")
    failed = request.args.get("failed")
    limit = _get_limit(30, 200)

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
    try:
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
    except Exception:
        rows = []
    conn.close()

    return jsonify({"ok": True, "events": rows, "count": len(rows)})


# ============================================================
# HELPERS
# ============================================================

def _build_health(cursor, project):
    """Construiește health counters. Refolosit de /api/dashboard și /api/health."""
    health = {"project": project}

    for key, table, where in [
        ("decisions", "decisions", "status='active'"),
        ("facts", "learned_facts", "is_active=1"),
        ("goals", "goals", "status='active'"),
        ("tasks", "tasks", "status IN ('todo','in_progress','blocked')"),
    ]:
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {where} AND project_path=?", (project,))
        health[key] = cursor.fetchone()[0]

    try:
        cursor.execute("SELECT COUNT(*) FROM error_patterns WHERE project_path=?", (project,))
        health["patterns"] = cursor.fetchone()[0]
    except Exception:
        health["patterns"] = 0

    try:
        cursor.execute("SELECT COUNT(*) FROM memory_checkpoints WHERE project_path=?", (project,))
        health["checkpoints"] = cursor.fetchone()[0]
    except Exception:
        health["checkpoints"] = 0

    try:
        cursor.execute("SELECT COUNT(*) FROM error_resolutions WHERE project_path=?", (project,))
        health["resolutions"] = cursor.fetchone()[0]
    except Exception:
        health["resolutions"] = 0

    # Stale counts
    stale = {}
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM learned_facts WHERE is_active=1 AND is_pinned=0 AND project_path=? AND created_at < datetime('now', '-180 days')",
            (project,))
        stale["stale_facts"] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='todo' AND project_path=? AND created_at < datetime('now', '-90 days')",
            (project,))
        stale["stale_tasks"] = cursor.fetchone()[0]
    except Exception:
        pass
    health["stale"] = stale

    # Conflicts
    try:
        from decision_analyzer import detect_conflicts
        conflicts = detect_conflicts(cursor, project)
        health["conflicts"] = len(conflicts)
    except Exception:
        health["conflicts"] = 0

    return health


# ============================================================
# REVIEW API (Faza 18C) — Review auto-extracted items
# ============================================================

@dashboard_bp.route("/api/review/pending")
def api_review_pending():
    """GET /api/review/pending — Items auto-extracted nerevizuite."""
    conn = get_db()
    cursor = conn.cursor()
    project = _get_project()
    limit = _get_limit(default=50, max_val=200)

    items = []
    # Decisions
    try:
        cursor.execute("""
            SELECT id, title, description, category, extraction_confidence, topics,
                   source_session_id, created_at
            FROM decisions
            WHERE auto_extracted = 1 AND status = 'active' AND project_path = ?
            ORDER BY created_at DESC LIMIT ?
        """, (project, limit))
        for row in cursor.fetchall():
            items.append({
                "type": "decision", "id": row[0], "text": row[1],
                "description": row[2], "category": row[3],
                "confidence": row[4], "topics": row[5],
                "session_id": row[6], "created_at": row[7],
            })
    except Exception:
        pass

    # Facts
    try:
        cursor.execute("""
            SELECT id, fact, fact_type, category, extraction_confidence, topics,
                   source_session_id, created_at
            FROM learned_facts
            WHERE auto_extracted = 1 AND is_active = 1 AND project_path = ?
            ORDER BY created_at DESC LIMIT ?
        """, (project, limit))
        for row in cursor.fetchall():
            items.append({
                "type": "fact", "id": row[0], "text": row[1],
                "fact_type": row[2], "category": row[3],
                "confidence": row[4], "topics": row[5],
                "session_id": row[6], "created_at": row[7],
            })
    except Exception:
        pass

    # Resolutions
    try:
        cursor.execute("""
            SELECT id, resolution, error_summary, extraction_confidence, topics,
                   source_session_id, created_at
            FROM error_resolutions
            WHERE auto_extracted = 1 AND project_path = ?
            ORDER BY created_at DESC LIMIT ?
        """, (project, limit))
        for row in cursor.fetchall():
            items.append({
                "type": "resolution", "id": row[0], "text": row[1],
                "error_summary": row[2],
                "confidence": row[3], "topics": row[4],
                "session_id": row[5], "created_at": row[6],
            })
    except Exception:
        pass

    # Sort by created_at desc
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return jsonify({"items": items, "count": len(items)})


@dashboard_bp.route("/api/review/approve", methods=["POST"])
def api_review_approve():
    """POST /api/review/approve — Aprobă un item auto-extracted (marchează ca confirmat)."""
    data = request.get_json(silent=True) or {}
    item_type = data.get("type")
    item_id = data.get("id")

    if not item_type or not item_id:
        return jsonify({"error": "type and id required"}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        if item_type == "decision":
            cursor.execute(
                "UPDATE decisions SET confidence = 'confirmed', auto_extracted = 2 WHERE id = ?",
                (item_id,))
        elif item_type == "fact":
            cursor.execute(
                "UPDATE learned_facts SET confidence = 'confirmed', auto_extracted = 2 WHERE id = ?",
                (item_id,))
        elif item_type == "resolution":
            cursor.execute(
                "UPDATE error_resolutions SET worked = 1, auto_extracted = 2 WHERE id = ?",
                (item_id,))
        else:
            return jsonify({"error": f"Unknown type: {item_type}"}), 400

        conn.commit()
        log_agent_activity("review", f"Approved {item_type} #{item_id}")
        return jsonify({"success": True, "action": "approved", "type": item_type, "id": item_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard_bp.route("/api/review/reject", methods=["POST"])
def api_review_reject():
    """POST /api/review/reject — Rejectează un item auto-extracted."""
    data = request.get_json(silent=True) or {}
    item_type = data.get("type")
    item_id = data.get("id")

    if not item_type or not item_id:
        return jsonify({"error": "type and id required"}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        if item_type == "decision":
            cursor.execute(
                "UPDATE decisions SET status = 'rejected', auto_extracted = -1 WHERE id = ?",
                (item_id,))
        elif item_type == "fact":
            cursor.execute(
                "UPDATE learned_facts SET is_active = 0, auto_extracted = -1 WHERE id = ?",
                (item_id,))
        elif item_type == "resolution":
            cursor.execute(
                "UPDATE error_resolutions SET worked = 0, auto_extracted = -1 WHERE id = ?",
                (item_id,))
        else:
            return jsonify({"error": f"Unknown type: {item_type}"}), 400

        conn.commit()
        log_agent_activity("review", f"Rejected {item_type} #{item_id}")
        return jsonify({"success": True, "action": "rejected", "type": item_type, "id": item_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard_bp.route("/api/review/stats")
def api_review_stats():
    """GET /api/review/stats — Statistici review: pending/approved/rejected per type."""
    conn = get_db()
    cursor = conn.cursor()
    project = _get_project()

    stats = {}
    for table, item_type, active_col in [
        ("decisions", "decision", "status = 'active'"),
        ("learned_facts", "fact", "is_active = 1"),
        ("error_resolutions", "resolution", "1=1"),
    ]:
        try:
            # Pending (auto_extracted = 1)
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE auto_extracted = 1 AND {active_col} AND project_path = ?",
                (project,))
            pending = cursor.fetchone()[0]

            # Approved (auto_extracted = 2)
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE auto_extracted = 2 AND project_path = ?",
                (project,))
            approved = cursor.fetchone()[0]

            # Rejected (auto_extracted = -1)
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE auto_extracted = -1 AND project_path = ?",
                (project,))
            rejected = cursor.fetchone()[0]

            stats[item_type] = {"pending": pending, "approved": approved, "rejected": rejected}
        except Exception:
            stats[item_type] = {"pending": 0, "approved": 0, "rejected": 0}

    return jsonify(stats)
