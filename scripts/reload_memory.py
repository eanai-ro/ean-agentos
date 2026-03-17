#!/usr/bin/env python3
"""
RELOAD MEMORY - Reîncarcă context din memoria permanentă.

Folosește acest script DUPĂ AUTO-COMPACT sau la începutul unei sesiuni noi
pentru a reîncărca contextul complet.

Utilizare:
    python3 scripts/reload_memory.py
    python3 scripts/reload_memory.py --full
    python3 scripts/reload_memory.py --project /cale/proiect
"""

import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta

try:
    from v2_common import resolve_db_path
    DB_PATH = resolve_db_path()
except ImportError:
    DB_PATH = Path.home() / ".claude" / "memory" / "global.db"


def get_db():
    return sqlite3.connect(DB_PATH)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def reload_context(full=False, project_filter=None, days=7):
    """Reîncarcă contextul din memoria permanentă."""

    conn = get_db()
    cursor = conn.cursor()

    # Header
    print("\n" + "🧠"*30)
    print("  MEMORIA PERMANENTĂ - CONTEXT REÎNCĂRCAT")
    print("🧠"*30)

    # 1. STATISTICI GENERALE
    print_section("📊 STATISTICI GENERALE")

    cursor.execute("SELECT COUNT(*) FROM sessions")
    sessions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM messages")
    messages = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tool_calls")
    tools = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM messages WHERE role='user'")
    user_msgs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM messages WHERE role='assistant'")
    assistant_msgs = cursor.fetchone()[0]

    print(f"  Sesiuni totale: {sessions}")
    print(f"  Mesaje utilizator: {user_msgs}")
    print(f"  Răspunsuri Claude: {assistant_msgs}")
    print(f"  Tool calls: {tools}")

    # 2. ULTIMELE SESIUNI
    print_section("📅 ULTIMELE SESIUNI")

    cursor.execute("""
        SELECT session_id, project_path, started_at
        FROM sessions
        ORDER BY started_at DESC
        LIMIT 5
    """)

    for row in cursor.fetchall():
        session_id, project, started = row
        project_name = Path(project).name if project else "N/A"
        print(f"  • {started[:16]} - {project_name}")

    # 3. PROIECTE LUCRATE RECENT
    print_section("📁 PROIECTE LUCRATE RECENT")

    cursor.execute("""
        SELECT DISTINCT project_path, MAX(started_at) as last_used
        FROM sessions
        WHERE project_path IS NOT NULL
        GROUP BY project_path
        ORDER BY last_used DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        project, last_used = row
        if project:
            print(f"  • {project}")

    # 4. ULTIMELE MESAJE IMPORTANTE (user + assistant)
    print_section("💬 ULTIMELE CONVERSAȚII")

    limit = 20 if full else 10

    cursor.execute(f"""
        SELECT timestamp, role, substr(content, 1, 200) as content
        FROM messages
        ORDER BY timestamp DESC
        LIMIT {limit}
    """)

    for row in cursor.fetchall():
        timestamp, role, content = row
        icon = "👤" if role == "user" else "🤖"
        content_clean = content.replace('\n', ' ')[:150]
        print(f"\n  {icon} [{timestamp[:16]}]")
        print(f"     {content_clean}...")

    # 5. ULTIMELE COMENZI BASH
    print_section("⚡ ULTIMELE COMENZI")

    cursor.execute(f"""
        SELECT timestamp, tool_input, exit_code
        FROM tool_calls
        WHERE tool_name = 'Bash'
        ORDER BY timestamp DESC
        LIMIT {10 if full else 5}
    """)

    for row in cursor.fetchall():
        timestamp, tool_input, exit_code = row
        try:
            import json
            cmd = json.loads(tool_input).get('command', '')[:100]
            status = "✅" if exit_code == 0 else "❌"
            print(f"  {status} {cmd}")
        except Exception:
            pass

    # 6. FIȘIERE MODIFICATE RECENT
    print_section("📝 FIȘIERE MODIFICATE RECENT")

    cursor.execute("""
        SELECT DISTINCT file_path, MAX(timestamp) as last_mod
        FROM tool_calls
        WHERE tool_name IN ('Edit', 'Write') AND file_path IS NOT NULL
        GROUP BY file_path
        ORDER BY last_mod DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        file_path, last_mod = row
        if file_path:
            print(f"  • {file_path}")

    # 7. DECIZII/CONFIGURĂRI IMPORTANTE (caută keywords)
    print_section("⚙️ DECIZII ȘI CONFIGURĂRI SALVATE")

    keywords = ['configurat', 'stabilit', 'decis', 'setat', 'creat', 'instalat', 'adăugat']

    for keyword in keywords[:3]:  # Limitează pentru a nu fi prea lung
        cursor.execute(f"""
            SELECT substr(content, 1, 150)
            FROM messages
            WHERE role = 'assistant' AND content LIKE '%{keyword}%'
            ORDER BY timestamp DESC
            LIMIT 2
        """)

        results = cursor.fetchall()
        if results:
            for row in results:
                content = row[0].replace('\n', ' ')
                print(f"  • {content}...")

    # 8. ERORI RECENTE (dacă există)
    cursor.execute("SELECT COUNT(*) FROM errors_solutions")
    errors_count = cursor.fetchone()[0]

    if errors_count > 0:
        print_section("⚠️ ERORI ÎNREGISTRATE")
        cursor.execute("""
            SELECT error_type, substr(error_message, 1, 100), solution
            FROM errors_solutions
            ORDER BY created_at DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            err_type, err_msg, solution = row
            print(f"  • {err_type}: {err_msg}")
            if solution:
                print(f"    Soluție: {solution[:100]}")

    # Footer
    print("\n" + "="*60)
    print("  CONTEXT REÎNCĂRCAT DIN MEMORIA PERMANENTĂ")
    print("  Folosește search_memory.py pentru căutări specifice")
    print("="*60 + "\n")

    conn.close()


def get_cost_stats():
    """Obține statistici de cost pentru azi."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT SUM(input_tokens) as input, SUM(output_tokens) as output,
                   SUM(cost_usd) as cost
            FROM token_costs WHERE DATE(timestamp) = ?
        """, (today,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return {
                'input': row[0],
                'output': row[1],
                'cost': row[2] or 0
            }
    except Exception:
        pass
    return None


def load_progressive_context(level: int):
    """Încarcă context cu progressive disclosure."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from progressive_loader import get_full_context, print_context
        context = get_full_context(level=level)
        print_context(context)
    except ImportError:
        print("⚠️ progressive_loader.py nu este disponibil")


def reload_context_v2(project_path=None, full=False, budget=2000, compact=False, survival=False,
                      auto=False, trigger="manual"):
    """Context Builder V2 — context structurat din tabelele V2.

    Folosește context_builder_v2.py. Dacă eșuează, returnează False
    pentru fallback la varianta veche.

    auto=True: folosește context_strategy pentru selecție automată.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from context_builder_v2 import build_context

        if auto:
            from context_strategy import choose_context_mode
            strategy = choose_context_mode(trigger=trigger, project_path=project_path, budget=budget if budget != 2000 else None)
            mode = strategy["mode"]
            effective_budget = strategy["budget"]
            # Delta mode
            is_delta = (mode == "delta")
            if is_delta:
                mode = "compact"  # delta uses compact formatting
            build_context(
                project_path=project_path,
                output_json=False,
                mode=mode,
                budget=effective_budget,
                delta=is_delta,
            )
        else:
            if survival:
                mode = "survival"
            elif full:
                mode = "full"
            else:
                mode = "compact"
            build_context(
                project_path=project_path,
                output_json=False,
                mode=mode,
                budget=budget,
            )
        return True
    except Exception as e:
        print(f"\n⚠️  Context Builder V2 a eșuat: {e}")
        print("   Revert la contextul clasic...\n")
        return False


def main():
    parser = argparse.ArgumentParser(description='Reîncarcă context din memoria permanentă')
    parser.add_argument('--full', '-f', action='store_true', help='Afișează mai multe detalii')
    parser.add_argument('--project', '-p', type=str, help='Filtrează după proiect')
    parser.add_argument('--days', '-d', type=int, default=7, help='Ultimele N zile')
    parser.add_argument('--level', '-l', type=int, choices=[1, 2, 3, 4, 5],
                        help='Nivel disclosure (1=minimal, 5=expanded)')
    parser.add_argument('--costs', '-c', action='store_true', help='Afișează statistici cost')
    parser.add_argument('--v2', action='store_true',
                        help='Folosește Context Builder V2 (decisions, facts, goals, tasks, resolutions)')
    parser.add_argument('--compact', action='store_true',
                        help='Context compact V2 (~400-800 tok)')
    parser.add_argument('--survival', action='store_true',
                        help='Context ultra-scurt V2 (~200-300 tok)')
    parser.add_argument('--auto', action='store_true',
                        help='Selecție automată mod context (strategy engine)')
    parser.add_argument('--trigger', type=str, default='manual',
                        choices=['session_start', 'session_refresh', 'post_compact', 'manual'],
                        help='Trigger pentru auto-strategy (default: manual)')
    parser.add_argument('--budget', '-b', type=int, default=2000,
                        help='Token budget pentru V2 (default: 2000)')

    args = parser.parse_args()

    if not DB_PATH.exists():
        print("❌ Baza de date nu există!")
        return

    # Progressive disclosure mode
    if args.level:
        load_progressive_context(args.level)
        return

    # Cost stats only
    if args.costs:
        costs = get_cost_stats()
        if costs:
            print("\n" + "="*40)
            print("  COSTURI AZI")
            print("="*40)
            print(f"  Input: {costs['input']:,} tokens")
            print(f"  Output: {costs['output']:,} tokens")
            print(f"  Cost: ${costs['cost']:.4f}")
            print("="*40 + "\n")
        else:
            print("Nu există date de cost pentru azi")
        return

    # V2 mode: context structurat din tabelele V2
    if args.auto or args.v2 or args.compact or args.survival:
        success = reload_context_v2(
            project_path=args.project,
            full=args.full,
            budget=args.budget,
            compact=args.compact,
            survival=args.survival,
            auto=args.auto,
            trigger=args.trigger,
        )
        if success:
            # Adaugă cost stats la final
            costs = get_cost_stats()
            if costs:
                print_section("💰 COSTURI AZI")
                print(f"  Input: {costs['input']:,} tok | Output: {costs['output']:,} tok")
                print(f"  Cost estimat: ${costs['cost']:.4f}")
            return
        # Fallback: continuă cu varianta clasică
        print("   Folosesc contextul clasic ca fallback.\n")

    reload_context(full=args.full, project_filter=args.project, days=args.days)

    # Adaugă cost stats la finalul output-ului normal
    costs = get_cost_stats()
    if costs:
        print_section("💰 COSTURI AZI")
        print(f"  Input: {costs['input']:,} tok | Output: {costs['output']:,} tok")
        print(f"  Cost estimat: ${costs['cost']:.4f}")


if __name__ == "__main__":
    main()
