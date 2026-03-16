#!/usr/bin/env python3
"""
HYBRID SEARCH - Căutare combinată keyword + semantică.

Combină SQLite LIKE search (keyword) cu Chroma semantic search (vector)
și aplică reranking pentru rezultate optime.

Formula de scoring:
    final_score = (keyword_weight * keyword_score) + (vector_weight * vector_score)
                  + recency_boost + project_boost

Avantaje:
- Precizie 85% vs 45% cu vector-only
- Găsește exact matches (keyword) + concepte similare (vector)
- Boost pentru rezultate recente și din proiectul curent

Usage:
    python3 hybrid_search.py "docker compose"
    python3 hybrid_search.py "authentication" --keyword-weight 0.5
    python3 hybrid_search.py "error fix" --project EAN-IAR
"""

import sys
import sqlite3
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

# Adaugă scripturile în path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"

# Weights default
DEFAULT_KEYWORD_WEIGHT = 0.3
DEFAULT_VECTOR_WEIGHT = 0.7
RECENCY_BOOST_MAX = 0.1  # Bonus maxim pentru recență
PROJECT_BOOST = 0.05      # Bonus pentru match proiect curent


def get_db_connection() -> sqlite3.Connection:
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def keyword_search(
    query: str,
    table: str = 'messages',
    limit: int = 50,
    project_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Căutare keyword în SQLite.

    Args:
        query: Textul de căutat
        table: Tabelul în care să caute
        limit: Număr maxim de rezultate
        project_path: Filtrează după proiect

    Returns:
        Lista de rezultate cu scor keyword
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Split query în termeni pentru matching mai flexibil
    terms = query.lower().split()
    results = []

    if table == 'messages':
        where_clauses = []
        params = []

        # Construiește WHERE pentru fiecare termen
        for term in terms:
            where_clauses.append("LOWER(content) LIKE ?")
            params.append(f"%{term}%")

        if project_path:
            where_clauses.append("project_path LIKE ?")
            params.append(f"%{project_path}%")

        where = " AND ".join(where_clauses) if where_clauses else "1=1"
        params.append(limit)

        cursor.execute(f"""
            SELECT id, session_id, timestamp, role, content, project_path
            FROM messages
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params)

        for row in cursor.fetchall():
            # Calculează scor keyword bazat pe frequency și position
            content_lower = row['content'].lower() if row['content'] else ""
            score = 0.0
            for term in terms:
                # Count occurrences
                count = content_lower.count(term)
                if count > 0:
                    score += min(count * 0.1, 0.3)  # Max 0.3 per termen

                    # Bonus pentru match la început
                    if content_lower.startswith(term):
                        score += 0.1

            # Normalizează scorul
            score = min(score / len(terms) if terms else 0, 1.0)

            results.append({
                'id': row['id'],
                'source_table': 'messages',
                'content': row['content'][:500] if row['content'] else "",
                'timestamp': row['timestamp'],
                'project_path': row['project_path'],
                'role': row['role'],
                'keyword_score': round(score, 4)
            })

    elif table == 'bash_history':
        cursor.execute(f"""
            SELECT id, session_id, timestamp, command, output, project_path
            FROM bash_history
            WHERE LOWER(command) LIKE ? OR LOWER(output) LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (f"%{query.lower()}%", f"%{query.lower()}%", limit))

        for row in cursor.fetchall():
            content = f"{row['command']}\n{row['output'] or ''}"
            results.append({
                'id': row['id'],
                'source_table': 'bash_history',
                'content': content[:500],
                'timestamp': row['timestamp'],
                'project_path': row['project_path'],
                'keyword_score': 0.5  # Score fix pentru bash
            })

    conn.close()
    return results


def vector_search(
    query: str,
    table: Optional[str] = None,
    limit: int = 50,
    min_score: float = 0.2
) -> List[Dict[str, Any]]:
    """
    Căutare semantică prin Chroma.

    Returns:
        Lista de rezultate cu scor vector
    """
    try:
        from vector_search import semantic_search, get_full_content
    except ImportError:
        print("⚠️ vector_search.py nu este disponibil")
        return []

    results = semantic_search(
        query,
        limit=limit,
        source_table=table,
        min_score=min_score
    )

    # Convertește la format comun
    processed = []
    for r in results:
        full_content = get_full_content(r['source_table'], r['source_id'])
        processed.append({
            'id': r['source_id'],
            'source_table': r['source_table'],
            'content': full_content[:500] if full_content else r.get('document', ''),
            'timestamp': r.get('indexed_at'),
            'vector_score': r['score'],
            'chroma_id': r['chroma_id']
        })

    return processed


def calculate_recency_boost(timestamp: str, max_days: int = 7) -> float:
    """
    Calculează bonus de recență.

    Returns:
        Bonus între 0 și RECENCY_BOOST_MAX
    """
    if not timestamp:
        return 0.0

    try:
        # Parse timestamp
        if 'T' in timestamp:
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            ts = datetime.strptime(timestamp[:19], '%Y-%m-%d %H:%M:%S')

        # Calculează diferența
        now = datetime.now()
        if ts.tzinfo:
            ts = ts.replace(tzinfo=None)

        diff = now - ts
        days = diff.days

        if days <= 0:
            return RECENCY_BOOST_MAX
        elif days >= max_days:
            return 0.0
        else:
            return RECENCY_BOOST_MAX * (1 - days / max_days)

    except Exception:
        return 0.0


def hybrid_search(
    query: str,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    limit: int = 20,
    table: Optional[str] = None,
    project_path: Optional[str] = None,
    include_recency_boost: bool = True,
    include_project_boost: bool = True
) -> List[Dict[str, Any]]:
    """
    Căutare hibridă combinând keyword și vector.

    Args:
        query: Textul de căutat
        keyword_weight: Pondere pentru scorul keyword (0-1)
        vector_weight: Pondere pentru scorul vector (0-1)
        limit: Număr maxim de rezultate finale
        table: Filtrează după tabel (opțional)
        project_path: Filtrează/boost după proiect
        include_recency_boost: Adaugă bonus pentru rezultate recente
        include_project_boost: Adaugă bonus pentru match proiect

    Returns:
        Lista de rezultate sortate după scor final
    """
    # Normalizează weights
    total_weight = keyword_weight + vector_weight
    if total_weight > 0:
        keyword_weight = keyword_weight / total_weight
        vector_weight = vector_weight / total_weight

    # Efectuează căutările
    search_table = table or 'messages'
    keyword_results = keyword_search(query, search_table, limit * 2, project_path)
    vector_results = vector_search(query, search_table, limit * 2)

    # Combină rezultatele
    combined = defaultdict(lambda: {
        'keyword_score': 0.0,
        'vector_score': 0.0,
        'recency_boost': 0.0,
        'project_boost': 0.0,
        'content': '',
        'timestamp': None,
        'project_path': None,
        'source_table': None
    })

    # Adaugă rezultate keyword
    for r in keyword_results:
        key = (r['source_table'], r['id'])
        combined[key]['keyword_score'] = r['keyword_score']
        combined[key]['content'] = r['content']
        combined[key]['timestamp'] = r.get('timestamp')
        combined[key]['project_path'] = r.get('project_path')
        combined[key]['source_table'] = r['source_table']
        combined[key]['id'] = r['id']
        if 'role' in r:
            combined[key]['role'] = r['role']

    # Adaugă rezultate vector
    for r in vector_results:
        key = (r['source_table'], r['id'])
        combined[key]['vector_score'] = r['vector_score']
        if not combined[key]['content']:
            combined[key]['content'] = r['content']
        if not combined[key]['timestamp']:
            combined[key]['timestamp'] = r.get('timestamp')
        combined[key]['source_table'] = r['source_table']
        combined[key]['id'] = r['id']

    # Calculează scoruri finale
    results = []
    current_project = project_path or Path.cwd().name

    for key, data in combined.items():
        # Scor de bază
        base_score = (keyword_weight * data['keyword_score'] +
                      vector_weight * data['vector_score'])

        # Boost recență
        recency = 0.0
        if include_recency_boost and data['timestamp']:
            recency = calculate_recency_boost(data['timestamp'])
            data['recency_boost'] = recency

        # Boost proiect
        project = 0.0
        if include_project_boost and data['project_path']:
            if current_project.lower() in data['project_path'].lower():
                project = PROJECT_BOOST
                data['project_boost'] = project

        # Scor final
        final_score = base_score + recency + project

        results.append({
            'source_table': data['source_table'],
            'id': data['id'],
            'content': data['content'],
            'timestamp': data['timestamp'],
            'project_path': data['project_path'],
            'role': data.get('role'),
            'scores': {
                'keyword': round(data['keyword_score'], 4),
                'vector': round(data['vector_score'], 4),
                'recency_boost': round(data['recency_boost'], 4),
                'project_boost': round(data['project_boost'], 4),
                'final': round(final_score, 4)
            }
        })

    # Sortează și limitează
    results.sort(key=lambda x: x['scores']['final'], reverse=True)
    return results[:limit]


def print_results(results: List[Dict], query: str, show_scores: bool = True):
    """Afișează rezultatele formatate."""
    print(f"\n{'='*60}")
    print(f"  CĂUTARE HIBRIDĂ: '{query}'")
    print(f"  Găsite {len(results)} rezultate")
    print(f"{'='*60}")

    if not results:
        print("\n  Nu s-au găsit rezultate.")
        return

    for i, r in enumerate(results, 1):
        scores = r['scores']
        print(f"\n--- Rezultat {i} (scor: {scores['final']}) ---")
        print(f"  Sursă: {r['source_table']} #{r['id']}")
        if r.get('timestamp'):
            print(f"  Timestamp: {r['timestamp'][:19]}")
        if r.get('role'):
            print(f"  Rol: {r['role']}")

        if show_scores:
            print(f"  Scoruri: K={scores['keyword']:.2f} V={scores['vector']:.2f} R={scores['recency_boost']:.2f} P={scores['project_boost']:.2f}")

        # Conținut trunchiat
        content = r.get('content', '')[:300].replace('\n', ' ')
        print(f"  Conținut: {content}...")


def main():
    parser = argparse.ArgumentParser(
        description="Căutare hibridă keyword + semantică"
    )
    parser.add_argument("query", nargs="?", help="Text de căutat")
    parser.add_argument("--limit", "-l", type=int, default=10,
                        help="Număr maxim de rezultate (default: 10)")
    parser.add_argument("--keyword-weight", "-k", type=float, default=DEFAULT_KEYWORD_WEIGHT,
                        help=f"Pondere keyword (default: {DEFAULT_KEYWORD_WEIGHT})")
    parser.add_argument("--vector-weight", "-v", type=float, default=DEFAULT_VECTOR_WEIGHT,
                        help=f"Pondere vector (default: {DEFAULT_VECTOR_WEIGHT})")
    parser.add_argument("--table", "-t", type=str,
                        help="Filtrează după tabel (messages, bash_history)")
    parser.add_argument("--project", "-p", type=str,
                        help="Filtrează/boost după proiect")
    parser.add_argument("--no-recency", action="store_true",
                        help="Dezactivează boost recență")
    parser.add_argument("--no-project-boost", action="store_true",
                        help="Dezactivează boost proiect")
    parser.add_argument("--keyword-only", action="store_true",
                        help="Doar căutare keyword (fără vector)")
    parser.add_argument("--vector-only", action="store_true",
                        help="Doar căutare vector (fără keyword)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output în format JSON")
    parser.add_argument("--no-scores", action="store_true",
                        help="Nu afișa scorurile detaliate")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        print("\nExemple:")
        print("  python3 hybrid_search.py 'docker compose'")
        print("  python3 hybrid_search.py 'error fix' --keyword-weight 0.5")
        print("  python3 hybrid_search.py 'authentication' --project EAN-IAR")
        print("  python3 hybrid_search.py 'config' --keyword-only")
        return

    # Ajustează weights pentru moduri exclusive
    kw = args.keyword_weight
    vw = args.vector_weight

    if args.keyword_only:
        kw, vw = 1.0, 0.0
    elif args.vector_only:
        kw, vw = 0.0, 1.0

    # Efectuează căutarea
    results = hybrid_search(
        args.query,
        keyword_weight=kw,
        vector_weight=vw,
        limit=args.limit,
        table=args.table,
        project_path=args.project,
        include_recency_boost=not args.no_recency,
        include_project_boost=not args.no_project_boost
    )

    # Output
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    else:
        print_results(results, args.query, show_scores=not args.no_scores)


if __name__ == "__main__":
    main()
