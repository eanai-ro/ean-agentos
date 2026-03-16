#!/usr/bin/env python3
"""
Kimi Context Loader
Încarcă context relevant la startup pentru Kimi Code CLI

Usage:
    # În ~/.bashrc sau înainte de a rula kimi:
    export KIMI_AUTO_CONTEXT=1
    
    # Sau manual:
    python3 kimi_context_loader.py
    
Acest script generează un context string care poate fi:
1. Copiat manual la începutul conversației
2. Injectat via Kimi system prompt (dacă suportă)
3. Folosit ca prim mesaj în conversație
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

MEMORY_DIR = Path.home() / ".kimi" / "memory"
DB_PATH = MEMORY_DIR / "global.db"

# Fallback la Claude DB
if not DB_PATH.exists():
    CLAUDE_DB = Path.home() / ".claude" / "memory" / "global.db"
    if CLAUDE_DB.exists():
        DB_PATH = CLAUDE_DB


class ContextLoader:
    """Încarcă context relevant din memorie."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.context_parts = []
    
    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def load_stats(self):
        """Încarcă statistici generale."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        msg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM sessions")
        sess_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM errors_solutions WHERE resolved = 1")
        err_resolved = cursor.fetchone()[0]
        
        conn.close()
        
        self.context_parts.append(f"""
🧠 MEMORIE PERMANENTĂ ACTIVĂ
═══════════════════════════════════════════════════════════
💬 Mesaje salvate: {msg_count:,}
📁 Sesiuni: {sess_count:,}
✅ Erori rezolvate: {err_resolved}
💾 DB: {self.db_path}
""")
    
    def load_recent_errors(self, limit: int = 3):
        """Încarcă erori recente nerezolvate."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT error_message, error_type, tool_name_resolved, created_at
            FROM errors_solutions
            WHERE resolved = 0 OR resolved IS NULL
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            self.context_parts.append("\n❌ ERORI RECENTE NEREZOLVATE:")
            for row in rows:
                self.context_parts.append(
                    f"  • [{row['created_at'][:10]}] {row['error_type']} "
                    f"({row['tool_name_resolved'] or 'N/A'})"
                )
                msg = row['error_message'][:100].replace('\n', ' ')
                self.context_parts.append(f"    {msg}...")
    
    def load_recent_commands(self, project_hint: Optional[str] = None, limit: int = 5):
        """Încarcă comenzi bash recente."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        
        if project_hint:
            cursor.execute("""
                SELECT command, working_directory, timestamp
                FROM bash_history
                WHERE timestamp >= ? AND working_directory LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, f"%{project_hint}%", limit))
        else:
            cursor.execute("""
                SELECT command, working_directory, timestamp
                FROM bash_history
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            self.context_parts.append("\n💻 COMENZI RECENTE:")
            for row in rows:
                cmd = row['command'][:60]
                self.context_parts.append(f"  $ {cmd}")
    
    def load_project_context(self, project_path: str, hours: int = 48):
        """Încarcă context specific proiectului."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        # Găsește sesiuni recente pentru proiect
        cursor.execute("""
            SELECT DISTINCT s.session_id, s.started_at, s.summary
            FROM sessions s
            JOIN messages m ON s.session_id = m.session_id
            WHERE s.project_path LIKE ? AND m.timestamp >= ?
            ORDER BY s.started_at DESC
            LIMIT 3
        """, (f"%{project_path}%", cutoff))
        
        sessions = cursor.fetchall()
        
        if sessions:
            self.context_parts.append(f"\n📂 PROIECT: {project_path}")
            self.context_parts.append(f"   Ultimele sesiuni ({hours}h):")
            
            for sess in sessions:
                self.context_parts.append(f"   • {sess['started_at'][:16]} - {sess['summary'] or 'Fără rezumat'}")
                
                # Ultimele mesaje din sesiune
                cursor.execute("""
                    SELECT role, substr(content, 1, 80) as content_preview
                    FROM messages
                    WHERE session_id = ? AND role IN ('user', 'assistant')
                    ORDER BY timestamp DESC
                    LIMIT 2
                """, (sess['session_id'],))
                
                messages = cursor.fetchall()
                for msg in messages:
                    role_emoji = "👤" if msg['role'] == 'user' else "🤖"
                    self.context_parts.append(f"     {role_emoji} {msg['content_preview']}...")
        
        conn.close()
    
    def load_patterns(self, limit: int = 3):
        """Încarcă patterns populare."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pattern_name, pattern_type, description
            FROM patterns
            WHERE usage_count > 0
            ORDER BY usage_count DESC, quality_score DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            self.context_parts.append("\n🔧 PATTERNS POPULARE:")
            for row in rows:
                desc = row['description'] or "Fără descriere"
                self.context_parts.append(f"  • [{row['pattern_type']}] {row['pattern_name']}: {desc[:50]}...")
    
    def generate_context(self, 
                        project_path: Optional[str] = None,
                        include_stats: bool = True,
                        include_errors: bool = True,
                        include_commands: bool = True,
                        include_patterns: bool = False) -> str:
        """Generează context complet."""
        
        if include_stats:
            self.load_stats()
        
        if project_path:
            self.load_project_context(project_path)
        
        if include_errors:
            self.load_recent_errors()
        
        if include_commands:
            self.load_recent_commands(project_hint=project_path)
        
        if include_patterns:
            self.load_patterns()
        
        self.context_parts.append("\n" + "═" * 60)
        self.context_parts.append("💡 Poți cere: 'Caută în memorie cum am...'")
        
        return "\n".join(self.context_parts)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kimi Context Loader")
    parser.add_argument("--project", "-p", help="Cale proiect")
    parser.add_argument("--no-stats", action="store_true", help="Fără statistici")
    parser.add_argument("--no-errors", action="store_true", help="Fără erori")
    parser.add_argument("--no-commands", action="store_true", help="Fără comenzi")
    parser.add_argument("--patterns", action="store_true", help="Include patterns")
    parser.add_argument("--copy", "-c", action="store_true", help="Copiază în clipboard")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"❌ DB nu există: {DB_PATH}")
        sys.exit(1)
    
    loader = ContextLoader(DB_PATH)
    context = loader.generate_context(
        project_path=args.project,
        include_stats=not args.no_stats,
        include_errors=not args.no_errors,
        include_commands=not args.no_commands,
        include_patterns=args.patterns
    )
    
    print(context)
    
    if args.copy:
        try:
            import pyperclip
            pyperclip.copy(context)
            print("\n📋 Context copiat în clipboard!")
        except ImportError:
            print("\n⚠️  Instalează pyperclip pentru copy: pip install pyperclip")


if __name__ == "__main__":
    main()
