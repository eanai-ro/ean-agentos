#!/usr/bin/env python3
"""
VECTOR SEARCH - Căutare semantică în EAN AgentOS.

Folosește Chroma DB și SentenceTransformers pentru căutare semantică.

Funcționalități:
- init_chroma() - Inițializare Chroma persistent storage
- embed_content(text) - Generare embedding cu SentenceTransformer
- add_to_index(source_table, source_id, content) - Adaugă în index
- semantic_search(query, limit=10) - Căutare semantică
- sync_missing_embeddings() - Sincronizare batch pentru mesaje existente

Usage:
    python3 vector_search.py "căutare semantică"
    python3 vector_search.py --sync              # Sincronizează embeddings lipsă
    python3 vector_search.py --stats             # Statistici index
"""

import sys
import os
import sqlite3
import hashlib
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# Paths
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from v2_common import resolve_db_path
    GLOBAL_DB = resolve_db_path()
except ImportError:
    GLOBAL_DB = Path.home() / ".claude" / "memory" / "global.db"
MEMORY_DIR = GLOBAL_DB.parent
CHROMA_DIR = MEMORY_DIR / "chroma"

# Model de embedding
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "ean_agentos"

# Lazy loading pentru dependențe grele
_chroma_client = None
_collection = None
_embedding_model = None


def check_dependencies() -> Tuple[bool, str]:
    """Verifică dacă dependențele sunt instalate."""
    missing = []

    try:
        import chromadb
    except ImportError:
        missing.append("chromadb")

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        missing.append("sentence-transformers")

    if missing:
        return False, f"Lipsesc dependențe: {', '.join(missing)}. Instalează cu: pip install {' '.join(missing)}"

    return True, "OK"


def get_embedding_model():
    """Lazy loading pentru modelul de embedding."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        print(f"📦 Încărcare model embedding: {EMBEDDING_MODEL}...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print("✓ Model încărcat")
    return _embedding_model


def init_chroma():
    """Inițializează Chroma DB cu persistent storage."""
    global _chroma_client, _collection

    if _chroma_client is not None:
        return _collection

    import chromadb
    from chromadb.config import Settings

    # Asigură-te că directorul există
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # Inițializare client persistent
    _chroma_client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )

    # Obține sau creează collection
    _collection = _chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # Folosește cosine similarity
    )

    return _collection


def get_db_connection() -> sqlite3.Connection:
    """Obține conexiune la baza de date."""
    conn = sqlite3.connect(str(GLOBAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


def hash_content(content: str) -> str:
    """Calculează SHA256 hash pentru conținut."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def embed_content(text: str) -> List[float]:
    """Generează embedding pentru text."""
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def add_to_index(
    source_table: str,
    source_id: int,
    content: str,
    metadata: Optional[Dict] = None
) -> Optional[str]:
    """
    Adaugă conținut în indexul vectorial.

    Args:
        source_table: Tabelul sursă (messages, tool_calls, etc.)
        source_id: ID-ul din tabelul sursă
        content: Conținutul de indexat
        metadata: Metadata adițională

    Returns:
        chroma_id dacă succes, None altfel
    """
    if not content or len(content.strip()) < 10:
        return None

    collection = init_chroma()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Calculează hash pentru deduplicare
    content_hash = hash_content(content)

    # Verifică dacă există deja
    cursor.execute("""
        SELECT chroma_id FROM embeddings
        WHERE source_table = ? AND source_id = ?
    """, (source_table, source_id))

    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing['chroma_id']

    # Generează ID unic pentru Chroma
    chroma_id = f"{source_table}_{source_id}_{content_hash[:8]}"

    # Generează embedding
    try:
        embedding = embed_content(content[:8000])  # Limitează la 8000 caractere
    except Exception as e:
        print(f"⚠️ Eroare embedding: {e}")
        conn.close()
        return None

    # Pregătește metadata
    doc_metadata = {
        "source_table": source_table,
        "source_id": source_id,
        "content_hash": content_hash,
        "indexed_at": datetime.now().isoformat(),
        "content_length": len(content)
    }
    if metadata:
        doc_metadata.update(metadata)

    # Adaugă în Chroma
    try:
        collection.add(
            ids=[chroma_id],
            embeddings=[embedding],
            documents=[content[:1000]],  # Salvează primele 1000 caractere în Chroma
            metadatas=[doc_metadata]
        )
    except Exception as e:
        print(f"⚠️ Eroare Chroma add: {e}")
        conn.close()
        return None

    # Salvează referință în SQLite
    cursor.execute("""
        INSERT INTO embeddings (source_table, source_id, content_hash, chroma_id, model)
        VALUES (?, ?, ?, ?, ?)
    """, (source_table, source_id, content_hash, chroma_id, EMBEDDING_MODEL))

    conn.commit()
    conn.close()

    return chroma_id


def semantic_search(
    query: str,
    limit: int = 10,
    source_table: Optional[str] = None,
    min_score: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Căutare semantică în memoria indexată.

    Args:
        query: Textul de căutat
        limit: Număr maxim de rezultate
        source_table: Filtrează după tabelul sursă (opțional)
        min_score: Scor minim de similaritate (0-1)

    Returns:
        Lista de rezultate cu scor și metadata
    """
    collection = init_chroma()

    # Generează embedding pentru query
    query_embedding = embed_content(query)

    # Construiește where clause
    where_clause = None
    if source_table:
        where_clause = {"source_table": source_table}

    # Caută în Chroma
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit * 2,  # Ia mai multe pentru filtrare
        where=where_clause,
        include=["documents", "metadatas", "distances"]
    )

    # Procesează rezultatele
    processed = []
    if results and results['ids'] and results['ids'][0]:
        for i, chroma_id in enumerate(results['ids'][0]):
            # Cosine distance -> similarity score
            distance = results['distances'][0][i] if results['distances'] else 0
            score = 1 - distance  # Convertește distanță în similaritate

            if score < min_score:
                continue

            metadata = results['metadatas'][0][i] if results['metadatas'] else {}
            document = results['documents'][0][i] if results['documents'] else ""

            processed.append({
                'chroma_id': chroma_id,
                'score': round(score, 4),
                'document': document,
                'source_table': metadata.get('source_table'),
                'source_id': metadata.get('source_id'),
                'content_length': metadata.get('content_length', 0),
                'indexed_at': metadata.get('indexed_at')
            })

    # Sortează și limitează
    processed.sort(key=lambda x: x['score'], reverse=True)
    return processed[:limit]


def get_full_content(source_table: str, source_id: int) -> Optional[str]:
    """Obține conținutul complet din baza de date."""
    conn = get_db_connection()
    cursor = conn.cursor()

    content = None

    if source_table == 'messages':
        cursor.execute("SELECT content FROM messages WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        if row:
            content = row['content']
    elif source_table == 'tool_calls':
        cursor.execute("SELECT tool_input, tool_result FROM tool_calls WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        if row:
            content = f"Input: {row['tool_input']}\nResult: {row['tool_result']}"
    elif source_table == 'bash_history':
        cursor.execute("SELECT command, output FROM bash_history WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        if row:
            content = f"Command: {row['command']}\nOutput: {row['output']}"
    elif source_table == 'errors_solutions':
        cursor.execute("SELECT error_message, solution FROM errors_solutions WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        if row:
            content = f"Error: {row['error_message']}\nSolution: {row['solution']}"

    conn.close()
    return content


def sync_missing_embeddings(
    table: str = 'messages',
    batch_size: int = 100,
    max_items: int = 1000
) -> int:
    """
    Sincronizează embeddings pentru înregistrări care nu au încă.

    Args:
        table: Tabelul de sincronizat
        batch_size: Dimensiunea batch-ului
        max_items: Număr maxim de itemi de procesat

    Returns:
        Numărul de embeddings create
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Găsește înregistrări fără embedding
    if table == 'messages':
        cursor.execute(f"""
            SELECT m.id, m.content, m.role, m.session_id
            FROM messages m
            LEFT JOIN embeddings e ON e.source_table = 'messages' AND e.source_id = m.id
            WHERE e.id IS NULL
              AND m.content IS NOT NULL
              AND LENGTH(m.content) > 20
            ORDER BY m.timestamp DESC
            LIMIT ?
        """, (max_items,))
    elif table == 'bash_history':
        cursor.execute(f"""
            SELECT b.id, b.command, b.output, b.session_id
            FROM bash_history b
            LEFT JOIN embeddings e ON e.source_table = 'bash_history' AND e.source_id = b.id
            WHERE e.id IS NULL
              AND b.command IS NOT NULL
            ORDER BY b.timestamp DESC
            LIMIT ?
        """, (max_items,))
    else:
        print(f"⚠️ Tabel necunoscut: {table}")
        conn.close()
        return 0

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"✓ Toate înregistrările din {table} au deja embeddings")
        return 0

    print(f"📊 Găsite {len(rows)} înregistrări fără embedding în {table}")

    created = 0
    for i, row in enumerate(rows):
        if table == 'messages':
            content = row['content']
            metadata = {
                'role': row['role'],
                'session_id': row['session_id']
            }
        elif table == 'bash_history':
            content = f"{row['command']}\n{row['output'] or ''}"
            metadata = {
                'session_id': row['session_id']
            }
        else:
            continue

        chroma_id = add_to_index(table, row['id'], content, metadata)
        if chroma_id:
            created += 1

        # Progress
        if (i + 1) % batch_size == 0:
            print(f"  Procesat {i + 1}/{len(rows)} ({created} create)")

    print(f"✓ Create {created} embeddings pentru {table}")
    return created


def get_index_stats() -> Dict[str, Any]:
    """Returnează statistici despre indexul vectorial."""
    stats = {
        'chroma_dir': str(CHROMA_DIR),
        'chroma_exists': CHROMA_DIR.exists(),
        'embeddings_count': 0,
        'by_table': {},
        'chroma_count': 0
    }

    # Statistici SQLite
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM embeddings")
    stats['embeddings_count'] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT source_table, COUNT(*) as cnt
        FROM embeddings
        GROUP BY source_table
    """)
    for row in cursor.fetchall():
        stats['by_table'][row['source_table']] = row['cnt']

    conn.close()

    # Statistici Chroma
    if CHROMA_DIR.exists():
        try:
            collection = init_chroma()
            stats['chroma_count'] = collection.count()
        except Exception as e:
            stats['chroma_error'] = str(e)

    # Dimensiune pe disc
    if CHROMA_DIR.exists():
        total_size = sum(f.stat().st_size for f in CHROMA_DIR.rglob('*') if f.is_file())
        stats['chroma_size_mb'] = round(total_size / (1024 * 1024), 2)

    return stats


def print_results(results: List[Dict], query: str):
    """Afișează rezultatele căutării."""
    print(f"\n{'='*60}")
    print(f"  CĂUTARE SEMANTICĂ: '{query}'")
    print(f"  Găsite {len(results)} rezultate")
    print(f"{'='*60}")

    if not results:
        print("\n  Nu s-au găsit rezultate.")
        return

    for i, r in enumerate(results, 1):
        print(f"\n--- Rezultat {i} (scor: {r['score']}) ---")
        print(f"  Sursă: {r['source_table']} #{r['source_id']}")
        print(f"  Indexat: {r.get('indexed_at', 'N/A')}")

        # Afișează conținut
        doc = r.get('document', '')[:300]
        if doc:
            print(f"  Conținut: {doc}...")


def main():
    parser = argparse.ArgumentParser(
        description="Căutare semantică în EAN AgentOS"
    )
    parser.add_argument("query", nargs="?", help="Text de căutat")
    parser.add_argument("--limit", "-l", type=int, default=10,
                        help="Număr maxim de rezultate (default: 10)")
    parser.add_argument("--table", "-t", type=str,
                        help="Filtrează după tabel (messages, bash_history, etc.)")
    parser.add_argument("--min-score", "-m", type=float, default=0.3,
                        help="Scor minim de similaritate (default: 0.3)")
    parser.add_argument("--sync", "-s", action="store_true",
                        help="Sincronizează embeddings lipsă")
    parser.add_argument("--sync-table", type=str, default="messages",
                        help="Tabel de sincronizat (default: messages)")
    parser.add_argument("--stats", action="store_true",
                        help="Afișează statistici index")
    parser.add_argument("--full", "-f", action="store_true",
                        help="Afișează conținutul complet")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output în format JSON")

    args = parser.parse_args()

    # Verifică dependențe
    ok, msg = check_dependencies()
    if not ok:
        print(f"❌ {msg}")
        sys.exit(1)

    # Statistici
    if args.stats:
        stats = get_index_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("\n" + "="*60)
            print("  STATISTICI INDEX VECTORIAL")
            print("="*60)
            print(f"\n  Chroma Dir: {stats['chroma_dir']}")
            print(f"  Embeddings în SQLite: {stats['embeddings_count']}")
            print(f"  Documente în Chroma: {stats.get('chroma_count', 'N/A')}")
            print(f"  Dimensiune pe disc: {stats.get('chroma_size_mb', 'N/A')} MB")
            if stats['by_table']:
                print("\n  Per tabel:")
                for table, count in stats['by_table'].items():
                    print(f"    - {table}: {count}")
        return

    # Sincronizare
    if args.sync:
        print(f"🔄 Sincronizare embeddings pentru {args.sync_table}...")
        created = sync_missing_embeddings(args.sync_table)
        print(f"✓ Finalizat: {created} embeddings create")
        return

    # Căutare
    if not args.query:
        parser.print_help()
        print("\nExemple:")
        print("  python3 vector_search.py 'docker compose'")
        print("  python3 vector_search.py 'authentication' --table messages")
        print("  python3 vector_search.py --sync")
        print("  python3 vector_search.py --stats")
        return

    results = semantic_search(
        args.query,
        limit=args.limit,
        source_table=args.table,
        min_score=args.min_score
    )

    if args.json:
        # Adaugă conținut complet dacă cerut
        if args.full:
            for r in results:
                r['full_content'] = get_full_content(r['source_table'], r['source_id'])
        print(json.dumps(results, indent=2))
    else:
        print_results(results, args.query)

        # Afișează conținut complet dacă cerut
        if args.full and results:
            print("\n" + "="*60)
            print("  CONȚINUT COMPLET")
            print("="*60)
            for i, r in enumerate(results[:3], 1):  # Primele 3
                content = get_full_content(r['source_table'], r['source_id'])
                if content:
                    print(f"\n--- #{i} ({r['source_table']} #{r['source_id']}) ---")
                    print(content[:2000])


if __name__ == "__main__":
    main()
