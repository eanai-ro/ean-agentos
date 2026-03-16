#!/usr/bin/env python3
"""
Kimi Memory MCP Server
Server Model Context Protocol pentru acces la memoria permanentă

Usage:
    python3 kimi_memory_server.py
    
Environment:
    MEMORY_DB_PATH - Calea către global.db (default: ~/.kimi/memory/global.db)
    MEMORY_MAX_RESULTS - Max rezultate per query (default: 20)
"""

import os
import sys
import json
import sqlite3
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# MCP SDK - disponibil în Kimi CLI environment
try:
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions, Server
    from mcp.server import stdio_server_driver
    from mcp.types import (
        Resource, Tool, TextContent, ImageContent, EmbeddedResource,
        LoggingLevel, Prompt, PromptMessage, PromptArgument
    )
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("⚠️  MCP SDK not available. Running in standalone mode.", file=sys.stderr)

# Configurare
MEMORY_DIR = Path.home() / ".kimi" / "memory"
DB_PATH = Path(os.environ.get("MEMORY_DB_PATH", MEMORY_DIR / "global.db"))
MAX_RESULTS = int(os.environ.get("MEMORY_MAX_RESULTS", 20))

class MemoryDatabase:
    """Wrapper pentru baza de date SQLite."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_db()
    
    def _ensure_db(self):
        """Asigură că DB există."""
        if not self.db_path.exists():
            # Copiază din Claude dacă există
            claude_db = Path.home() / ".claude" / "memory" / "global.db"
            if claude_db.exists():
                import shutil
                shutil.copy2(claude_db, self.db_path)
                print(f"📦 DB copiat din Claude: {self.db_path}", file=sys.stderr)
            else:
                raise FileNotFoundError(f"DB not found: {self.db_path}")
    
    def get_connection(self) -> sqlite3.Connection:
        """Returnează conexiune la DB."""
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def search_messages(self, query: str, limit: int = 10) -> List[Dict]:
        """Caută în mesaje folosind FTS5 dacă disponibil."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Verifică dacă există FTS5
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'")
        has_fts = cursor.fetchone() is not None
        
        if has_fts:
            # Folosește FTS5 pentru viteză
            try:
                cursor.execute("""
                    SELECT m.id, m.timestamp, m.role, m.content, m.project_path
                    FROM messages m
                    JOIN messages_fts fts ON m.id = fts.rowid
                    WHERE messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, limit))
            except sqlite3.Error:
                # Fallback la LIKE
                has_fts = False
        
        if not has_fts:
            # Fallback la LIKE
            cursor.execute("""
                SELECT id, timestamp, role, content, project_path
                FROM messages
                WHERE content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{query}%", limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "role": row["role"],
                "content": row["content"][:500] + "..." if len(row["content"]) > 500 else row["content"],
                "project_path": row["project_path"]
            }
            for row in rows
        ]
    
    def search_errors(self, error_query: str, limit: int = 5) -> List[Dict]:
        """Caută erori și soluții."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, created_at, error_type, error_message, 
                   solution, solution_worked, tool_name_resolved
            FROM errors_solutions
            WHERE error_message LIKE ? OR error_type LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"%{error_query}%", f"%{error_query}%", limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "error_type": row["error_type"],
                "error_message": row["error_message"][:300] + "..." if len(row["error_message"]) > 300 else row["error_message"],
                "solution": row["solution"],
                "resolved": bool(row["solution_worked"]),
                "tool": row["tool_name_resolved"]
            }
            for row in rows
        ]
    
    def get_recent_context(self, project_path: Optional[str] = None, 
                          hours: int = 24, limit: int = 20) -> List[Dict]:
        """Încarcă context recent pentru proiect."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        if project_path:
            cursor.execute("""
                SELECT m.timestamp, m.role, m.content, m.project_path
                FROM messages m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE m.timestamp >= ? 
                  AND (m.project_path LIKE ? OR s.project_path LIKE ?)
                ORDER BY m.timestamp DESC
                LIMIT ?
            """, (cutoff, f"%{project_path}%", f"%{project_path}%", limit))
        else:
            cursor.execute("""
                SELECT timestamp, role, content, project_path
                FROM messages
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "timestamp": row["timestamp"],
                "role": row["role"],
                "content": row["content"][:400] + "..." if len(row["content"]) > 400 else row["content"],
                "project_path": row["project_path"]
            }
            for row in rows
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Returnează statistici DB."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        cursor.execute("SELECT COUNT(*) FROM messages")
        stats["total_messages"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM sessions")
        stats["total_sessions"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tool_calls")
        stats["total_tool_calls"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM errors_solutions")
        stats["total_errors"] = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM messages 
            WHERE timestamp >= datetime('now', '-24 hours')
        """)
        stats["messages_24h"] = cursor.fetchone()[0]
        
        conn.close()
        
        # DB size
        stats["db_size_mb"] = round(self.db_path.stat().st_size / (1024 * 1024), 2)
        
        return stats


# ==================== MCP SERVER ====================

if MCP_AVAILABLE:
    server = Server("kimi-memory")
    db = MemoryDatabase(DB_PATH)
    
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """Listează tool-urile disponibile."""
        return [
            Tool(
                name="memory_search",
                description="Caută în memoria permanentă după keywords",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Termenii de căutare"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Număr maxim rezultate (default: 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="memory_search_errors",
                description="Caută erori și soluții salvate",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "error_query": {
                            "type": "string",
                            "description": "Fragment din mesajul de eroare"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Număr maxim rezultate (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["error_query"]
                }
            ),
            Tool(
                name="memory_get_context",
                description="Încarcă context recent pentru proiectul curent",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Calea proiectului (opțional)"
                        },
                        "hours": {
                            "type": "integer",
                            "description": "Câte ore înapoi să caute (default: 24)",
                            "default": 24
                        }
                    }
                }
            ),
            Tool(
                name="memory_get_stats",
                description="Returnează statistici despre memorie",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> List[TextContent]:
        """Procesează apelurile de tool."""
        
        if name == "memory_search":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            results = db.search_messages(query, limit)
            
            if not results:
                return [TextContent(type="text", text="Nu am găsit rezultate pentru căutarea ta.")]
            
            output = [f"🔍 Rezultate pentru '{query}':\n"]
            for r in results:
                output.append(f"\n[{r['timestamp']}] {r['role'].upper()}")
                output.append(f"📁 {r['project_path'] or 'N/A'}")
                output.append(f"💬 {r['content'][:300]}...")
                output.append("-" * 50)
            
            return [TextContent(type="text", text="\n".join(output))]
        
        elif name == "memory_search_errors":
            error_query = arguments.get("error_query", "")
            limit = arguments.get("limit", 5)
            results = db.search_errors(error_query, limit)
            
            if not results:
                return [TextContent(type="text", text="Nu am găsit erori similare.")]
            
            output = [f"❌ Erori găsite pentru '{error_query}':\n"]
            for r in results:
                status = "✅ REZOLVAT" if r['resolved'] else "❌ NEREZOLVAT"
                output.append(f"\n[{r['created_at']}] {status}")
                output.append(f"🔧 Tool: {r['tool'] or 'N/A'}")
                output.append(f"📝 Eroare: {r['error_message'][:200]}...")
                if r['solution']:
                    output.append(f"💡 Soluție: {r['solution'][:200]}...")
                output.append("-" * 50)
            
            return [TextContent(type="text", text="\n".join(output))]
        
        elif name == "memory_get_context":
            project_path = arguments.get("project_path")
            hours = arguments.get("hours", 24)
            results = db.get_recent_context(project_path, hours)
            
            if not results:
                return [TextContent(type="text", text=f"Nu am găsit context pentru ultimele {hours} ore.")]
            
            output = [f"🧠 Context din ultimele {hours} ore:\n"]
            for r in results:
                output.append(f"\n[{r['timestamp']}] {r['role'].upper()}")
                output.append(f"💬 {r['content'][:250]}...")
            
            return [TextContent(type="text", text="\n".join(output))]
        
        elif name == "memory_get_stats":
            stats = db.get_stats()
            
            output = [
                "📊 Statistici Memorie Permanentă:\n",
                f"💬 Mesaje totale: {stats['total_messages']:,}",
                f"📁 Sesiuni: {stats['total_sessions']:,}",
                f"🔧 Tool calls: {stats['total_tool_calls']:,}",
                f"❌ Erori înregistrate: {stats['total_errors']:,}",
                f"🕒 Mesaje 24h: {stats['messages_24h']:,}",
                f"💾 Dimensiune DB: {stats['db_size_mb']} MB"
            ]
            
            return [TextContent(type="text", text="\n".join(output))]
        
        else:
            return [TextContent(type="text", text=f"Tool necunoscut: {name}")]
    
    async def main():
        """Main entry point."""
        async with stdio_server_driver(server, server.name) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="kimi-memory",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities()
                )
            )


# ==================== STANDALONE MODE ====================

def standalone_cli():
    """CLI pentru modul standalone (fără MCP)."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kimi Memory CLI")
    parser.add_argument("command", choices=["search", "errors", "context", "stats"])
    parser.add_argument("--query", "-q", help="Query de căutare")
    parser.add_argument("--project", "-p", help="Cale proiect")
    parser.add_argument("--limit", "-l", type=int, default=10)
    parser.add_argument("--hours", type=int, default=24)
    
    args = parser.parse_args()
    
    db = MemoryDatabase(DB_PATH)
    
    if args.command == "search":
        if not args.query:
            print("❌ Specifică --query")
            return
        results = db.search_messages(args.query, args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif args.command == "errors":
        if not args.query:
            print("❌ Specifică --query")
            return
        results = db.search_errors(args.query, args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif args.command == "context":
        results = db.get_recent_context(args.project, args.hours, args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif args.command == "stats":
        stats = db.get_stats()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    if MCP_AVAILABLE:
        asyncio.run(main())
    else:
        standalone_cli()
