#!/usr/bin/env python3
"""
WEB SERVER - Server Flask pentru vizualizare EAN AgentOS.

Oferă interfață web pentru explorarea memoriei permanente.
Rulează pe portul 19876 (implicit).

API Endpoints:
- GET  /                    → Dashboard HTML
- GET  /api/stats           → Statistici generale
- GET  /api/sessions        → Lista sesiuni (paginat)
- GET  /api/session/<id>    → Detalii sesiune
- GET  /api/search?q=...    → Search (keyword/vector/hybrid)
- GET  /api/costs           → Cost analytics
- GET  /api/summaries       → Auto-summaries

Usage:
    python3 web_server.py                   # Start pe port 19876
    python3 web_server.py --port 8080       # Alt port
    python3 web_server.py --host 0.0.0.0    # Acces extern
"""

import os
import sys
import sqlite3
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

try:
    from flask import Flask, jsonify, request, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("❌ Flask nu este instalat. Rulează: pip install flask flask-cors")
    sys.exit(1)

# Paths
SCRIPTS_DIR = Path(__file__).parent
try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    MEMORY_DIR = Path.home() / ".claude" / "memory"
    GLOBAL_DB = MEMORY_DIR / "global.db"
    if os.environ.get("MEMORY_DB_PATH"):
        GLOBAL_DB = Path(os.environ["MEMORY_DB_PATH"])

# WEB_DIR: prefer env var, then project web/, then default project web/
if os.environ.get("MEMORY_WEB_DIR"):
    WEB_DIR = Path(os.environ["MEMORY_WEB_DIR"])
elif (SCRIPTS_DIR.parent / "web" / "index.html").exists():
    WEB_DIR = SCRIPTS_DIR.parent / "web"
else:
    WEB_DIR = MEMORY_DIR / "web"

# Adaugă scripts în path pentru import
sys.path.insert(0, str(SCRIPTS_DIR))

# Flask app
app = Flask(__name__, static_folder=str(WEB_DIR))
CORS(app)  # Permite CORS pentru development

# V2 Dashboard API Blueprint
try:
    from dashboard_api import dashboard_bp
    app.register_blueprint(dashboard_bp)
except ImportError:
    pass  # Dashboard API optional — nu blochează serverul dacă lipsește

# V6 Universal Agent Memory API Blueprint
try:
    from universal_api import universal_bp
    app.register_blueprint(universal_bp)
except ImportError:
    pass  # Universal API optional


def get_db_connection() -> sqlite3.Connection:
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> Dict:
    """Convertește Row în dict."""
    return dict(row) if row else {}


# ============================================================
# STATIC FILES
# ============================================================

@app.route('/')
def index():
    """Servește dashboard-ul principal."""
    return send_from_directory(str(WEB_DIR), 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    """Servește fișiere statice."""
    return send_from_directory(str(WEB_DIR), filename)


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route('/api/stats')
def api_stats():
    """Returnează statistici generale."""
    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}

    # Sesiuni
    cursor.execute("SELECT COUNT(*) as count FROM sessions")
    stats['sessions_count'] = cursor.fetchone()['count']

    # Mesaje
    cursor.execute("SELECT COUNT(*) as count FROM messages")
    stats['messages_count'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE role='user'")
    stats['user_messages'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE role='assistant'")
    stats['assistant_messages'] = cursor.fetchone()['count']

    # Tool calls
    cursor.execute("SELECT COUNT(*) as count FROM tool_calls")
    stats['tool_calls_count'] = cursor.fetchone()['count']

    # Erori
    cursor.execute("SELECT COUNT(*) as count FROM errors_solutions")
    stats['errors_count'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM errors_solutions WHERE solution_worked=1")
    stats['errors_resolved'] = cursor.fetchone()['count']

    # Embeddings
    cursor.execute("SELECT COUNT(*) as count FROM embeddings")
    stats['embeddings_count'] = cursor.fetchone()['count']

    # Dimensiune DB
    if GLOBAL_DB.exists():
        stats['db_size_mb'] = round(GLOBAL_DB.stat().st_size / (1024 * 1024), 2)

    # Ultima sesiune
    cursor.execute("""
        SELECT session_id, project_path, started_at
        FROM sessions ORDER BY started_at DESC LIMIT 1
    """)
    last = cursor.fetchone()
    if last:
        stats['last_session'] = {
            'id': last['session_id'],
            'project': last['project_path'],
            'started': last['started_at']
        }

    conn.close()
    return jsonify(stats)


@app.route('/api/sessions')
def api_sessions():
    """Returnează lista de sesiuni (paginat)."""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    project = request.args.get('project', None)

    offset = (page - 1) * limit

    conn = get_db_connection()
    cursor = conn.cursor()

    # Count total
    if project:
        cursor.execute("""
            SELECT COUNT(*) FROM sessions WHERE project_path LIKE ?
        """, (f"%{project}%",))
    else:
        cursor.execute("SELECT COUNT(*) FROM sessions")

    total = cursor.fetchone()[0]

    # Fetch sessions
    if project:
        cursor.execute("""
            SELECT session_id, project_path, started_at, ended_at,
                   total_messages, total_tool_calls
            FROM sessions
            WHERE project_path LIKE ?
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
        """, (f"%{project}%", limit, offset))
    else:
        cursor.execute("""
            SELECT session_id, project_path, started_at, ended_at,
                   total_messages, total_tool_calls
            FROM sessions
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

    sessions = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'sessions': sessions,
        'total': total,
        'page': page,
        'limit': limit,
        'pages': (total + limit - 1) // limit
    })


@app.route('/api/session/<session_id>')
def api_session_detail(session_id: str):
    """Returnează detalii pentru o sesiune."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Session info
    cursor.execute("""
        SELECT * FROM sessions
        WHERE session_id = ? OR session_id LIKE ?
    """, (session_id, f"%{session_id}%"))

    session = cursor.fetchone()
    if not session:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404

    result = row_to_dict(session)
    actual_id = session['session_id']

    # Messages
    cursor.execute("""
        SELECT id, role, substr(content, 1, 500) as content, timestamp
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp
        LIMIT 100
    """, (actual_id,))
    result['messages'] = [row_to_dict(r) for r in cursor.fetchall()]

    # Tool calls
    cursor.execute("""
        SELECT id, tool_name, file_path, exit_code, timestamp
        FROM tool_calls
        WHERE session_id = ?
        ORDER BY timestamp
        LIMIT 50
    """, (actual_id,))
    result['tool_calls'] = [row_to_dict(r) for r in cursor.fetchall()]

    # Summary
    cursor.execute("""
        SELECT content, key_topics, files_mentioned
        FROM session_summaries
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (actual_id,))
    summary = cursor.fetchone()
    if summary:
        result['summary'] = row_to_dict(summary)

    conn.close()
    return jsonify(result)


@app.route('/api/search')
def api_search():
    """Căutare în memorie."""
    query = request.args.get('q', '')
    mode = request.args.get('mode', 'hybrid')  # keyword, vector, hybrid
    limit = request.args.get('limit', 20, type=int)
    table = request.args.get('table', None)

    if not query:
        return jsonify({'error': 'Query required'}), 400

    results = []

    if mode == 'keyword':
        # Căutare keyword simplă
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, role, substr(content, 1, 300) as content, timestamp, project_path
            FROM messages
            WHERE content LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (f"%{query}%", limit))
        results = [row_to_dict(r) for r in cursor.fetchall()]
        conn.close()

    elif mode == 'vector':
        try:
            from vector_search import semantic_search
            results = semantic_search(query, limit=limit, source_table=table)
        except ImportError:
            return jsonify({'error': 'Vector search not available'}), 500

    else:  # hybrid
        try:
            from hybrid_search import hybrid_search
            results = hybrid_search(query, limit=limit, table=table)
        except ImportError:
            # Fallback to keyword
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role, substr(content, 1, 300) as content, timestamp, project_path
                FROM messages
                WHERE content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{query}%", limit))
            results = [row_to_dict(r) for r in cursor.fetchall()]
            conn.close()

    return jsonify({
        'query': query,
        'mode': mode,
        'count': len(results),
        'results': results
    })


@app.route('/api/costs')
def api_costs():
    """Returnează cost analytics."""
    period = request.args.get('period', 'today')  # today, week, month

    conn = get_db_connection()
    cursor = conn.cursor()

    if period == 'today':
        date_filter = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT SUM(input_tokens) as input,
                   SUM(output_tokens) as output,
                   SUM(cost_usd) as cost,
                   COUNT(*) as sessions
            FROM token_costs
            WHERE DATE(timestamp) = ?
        """, (date_filter,))
    elif period == 'week':
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT SUM(input_tokens) as input,
                   SUM(output_tokens) as output,
                   SUM(cost_usd) as cost,
                   COUNT(*) as sessions
            FROM token_costs
            WHERE DATE(timestamp) >= ?
        """, (week_ago,))
    else:  # month
        month = datetime.now().strftime('%Y-%m')
        cursor.execute("""
            SELECT SUM(input_tokens) as input,
                   SUM(output_tokens) as output,
                   SUM(cost_usd) as cost,
                   COUNT(*) as sessions
            FROM token_costs
            WHERE strftime('%Y-%m', timestamp) = ?
        """, (month,))

    row = cursor.fetchone()

    result = {
        'period': period,
        'input_tokens': row['input'] or 0,
        'output_tokens': row['output'] or 0,
        'total_cost': round(row['cost'] or 0, 4),
        'sessions_count': row['sessions'] or 0
    }

    # Daily breakdown for charts
    if period == 'week':
        cursor.execute("""
            SELECT DATE(timestamp) as date,
                   SUM(cost_usd) as cost
            FROM token_costs
            WHERE DATE(timestamp) >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date
        """, ((datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),))
        result['daily'] = [row_to_dict(r) for r in cursor.fetchall()]

    conn.close()
    return jsonify(result)


@app.route('/api/summaries')
def api_summaries():
    """Returnează rezumate sesiuni."""
    limit = request.args.get('limit', 10, type=int)
    summary_type = request.args.get('type', None)

    conn = get_db_connection()
    cursor = conn.cursor()

    if summary_type:
        cursor.execute("""
            SELECT ss.*, s.project_path
            FROM session_summaries ss
            LEFT JOIN sessions s ON ss.session_id = s.session_id
            WHERE ss.summary_type = ?
            ORDER BY ss.created_at DESC
            LIMIT ?
        """, (summary_type, limit))
    else:
        cursor.execute("""
            SELECT ss.*, s.project_path
            FROM session_summaries ss
            LEFT JOIN sessions s ON ss.session_id = s.session_id
            ORDER BY ss.created_at DESC
            LIMIT ?
        """, (limit,))

    summaries = [row_to_dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({
        'summaries': summaries,
        'count': len(summaries)
    })


@app.route('/api/messages')
def api_messages():
    """Returnează mesaje recente."""
    limit = request.args.get('limit', 50, type=int)
    role = request.args.get('role', None)
    project = request.args.get('project', None)

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT id, session_id, role, substr(content, 1, 500) as content,
               timestamp, project_path
        FROM messages
        WHERE 1=1
    """
    params = []

    if role:
        query += " AND role = ?"
        params.append(role)

    if project:
        query += " AND project_path LIKE ?"
        params.append(f"%{project}%")

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    messages = [row_to_dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({'messages': messages, 'count': len(messages)})


@app.route('/api/errors')
def api_errors():
    """Returnează erori recente."""
    limit = request.args.get('limit', 20, type=int)
    resolved = request.args.get('resolved', None)

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT id, error_type, substr(error_message, 1, 300) as error_message,
               substr(solution, 1, 300) as solution, solution_worked,
               language, file_path, created_at, session_id, project_path
        FROM errors_solutions
        WHERE 1=1
    """
    params = []

    if resolved is not None:
        query += " AND solution_worked = ?"
        params.append(1 if resolved == 'true' else 0)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    errors = [row_to_dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({'errors': errors, 'count': len(errors)})


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Server web pentru vizualizare EAN AgentOS"
    )
    parser.add_argument("--host", "-H", type=str, default="192.168.205.222",
                        help="Host (default: 192.168.205.222)")
    parser.add_argument("--port", "-p", type=int, default=19876,
                        help="Port (default: 19876)")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Mod debug")

    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  CLAUDE MEMORY WEB SERVER")
    print(f"{'='*50}")
    print(f"\n  URL: http://{args.host}:{args.port}")
    print(f"  Database: {GLOBAL_DB}")
    print(f"  Web files: {WEB_DIR}")
    print(f"\n  Press Ctrl+C to stop\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
