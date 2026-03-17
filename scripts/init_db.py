#!/usr/bin/env python3
"""
Inițializare bază de date SQLite pentru sistemul de EAN AgentOS.
Creează schema pentru global.db și project.db.
"""

import sqlite3
import os
from pathlib import Path

SCHEMA = """
-- SESIUNI - Înregistrează fiecare sesiune Claude Code
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    project_path TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    summary TEXT,
    total_messages INTEGER DEFAULT 0,
    total_tool_calls INTEGER DEFAULT 0
);

-- ============================================================
-- FUNCȚIONALITĂȚI NOI CLAUDE-MEM (2026-02-03)
-- ============================================================

-- EMBEDDINGS - Referințe către Chroma pentru căutare semantică
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,        -- 'messages', 'tool_calls', etc.
    source_id INTEGER NOT NULL,
    content_hash TEXT NOT NULL,        -- SHA256 pentru deduplicare
    chroma_id TEXT UNIQUE,             -- ID în Chroma collection
    model TEXT DEFAULT 'all-MiniLM-L6-v2',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DISCLOSURE CONFIG - Niveluri de progressive disclosure
CREATE TABLE IF NOT EXISTS disclosure_config (
    id INTEGER PRIMARY KEY,
    level INTEGER NOT NULL UNIQUE,     -- 1-5
    name TEXT NOT NULL,                -- 'minimal', 'summary', etc.
    max_tokens INTEGER NOT NULL,       -- Budget per nivel
    description TEXT
);

-- CONTENT SUMMARIES - Rezumate pre-generate pentru disclosure rapid
CREATE TABLE IF NOT EXISTS content_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    disclosure_level INTEGER NOT NULL,
    summary TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_table, source_id, disclosure_level)
);

-- SESSION SUMMARIES - Rezumate automate per sesiune
CREATE TABLE IF NOT EXISTS session_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary_type TEXT NOT NULL,        -- 'auto', 'manual', 'daily_digest'
    content TEXT NOT NULL,
    key_topics TEXT,                   -- JSON array
    files_mentioned TEXT,              -- JSON array
    errors_resolved INTEGER DEFAULT 0,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'auto',    -- 'auto', 'user', 'claude'
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- TOKEN COSTS - Tracking costuri per mesaj/sesiune
CREATE TABLE IF NOT EXISTS token_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    message_id INTEGER,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,
    cost_usd REAL,                     -- Calculat din model pricing
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- COST SUMMARY - Sumar zilnic costuri
CREATE TABLE IF NOT EXISTS cost_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    model_breakdown TEXT,              -- JSON {model: {tokens, cost}}
    sessions_count INTEGER DEFAULT 0
);

-- MESAJE - Salvează TOATE mesajele (user + assistant + system)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    role TEXT NOT NULL,  -- user/assistant/system
    content TEXT NOT NULL,
    message_type TEXT,  -- prompt/response/error/info
    tokens_estimated INTEGER,
    project_path TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- TOOL CALLS - Toate acțiunile executate (Bash, Edit, Write, Read, etc.)
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tool_name TEXT NOT NULL,  -- Bash, Edit, Write, Read, Glob, Grep, etc.
    tool_input TEXT,  -- JSON complet al inputului
    tool_result TEXT,  -- Rezultatul executării
    exit_code INTEGER,
    duration_ms INTEGER,
    success BOOLEAN DEFAULT 1,
    error_message TEXT,
    project_path TEXT,
    file_path TEXT,  -- Pentru Edit/Write/Read - calea fișierului afectat
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- VERSIUNI FIȘIERE - Backup complet înainte de orice modificare
CREATE TABLE IF NOT EXISTS file_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,  -- SHA256 pentru deduplicare
    content TEXT NOT NULL,  -- Conținutul complet al fișierului
    size_bytes INTEGER,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    change_type TEXT NOT NULL,  -- before_edit/before_write/before_delete/snapshot
    project_path TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- ERORI ȘI SOLUȚII - Învățare din problemele rezolvate
CREATE TABLE IF NOT EXISTS errors_solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type TEXT NOT NULL,  -- syntax_error, runtime_error, import_error, etc.
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    file_path TEXT,
    line_number INTEGER,
    language TEXT,  -- python, javascript, bash, etc.
    framework TEXT,  -- fastapi, react, django, etc.
    solution TEXT,
    solution_code TEXT,
    solution_worked BOOLEAN,
    attempts INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    session_id TEXT,
    project_path TEXT,
    tags TEXT,  -- JSON array pentru căutare
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- PATTERNS/MODULE REUTILIZABILE - Cod care poate fi refolosit
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_name TEXT NOT NULL,
    pattern_type TEXT NOT NULL,  -- code_snippet, architecture, config, fix, template
    description TEXT,
    code TEXT NOT NULL,
    language TEXT,
    framework TEXT,
    file_path_original TEXT,  -- De unde a fost extras
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_project TEXT,
    tags TEXT,  -- JSON array
    quality_score INTEGER DEFAULT 0  -- 0-100, bazat pe utilizări cu succes
);

-- COMENZI BASH - Istoric complet de comenzi
CREATE TABLE IF NOT EXISTS bash_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    command TEXT NOT NULL,
    working_directory TEXT,
    exit_code INTEGER,
    output TEXT,
    error_output TEXT,
    duration_ms INTEGER,
    project_path TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- STATISTICI SESIUNI - Pentru analiză și raportare
CREATE TABLE IF NOT EXISTS session_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    date DATE NOT NULL,
    files_created INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    errors_encountered INTEGER DEFAULT 0,
    errors_resolved INTEGER DEFAULT 0,
    tests_run INTEGER DEFAULT 0,
    tests_passed INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- INDEX-URI PENTRU CĂUTARE RAPIDĂ
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_file ON tool_calls(file_path);
CREATE INDEX IF NOT EXISTS idx_file_versions_path ON file_versions(file_path);
CREATE INDEX IF NOT EXISTS idx_file_versions_hash ON file_versions(content_hash);
CREATE INDEX IF NOT EXISTS idx_errors_type ON errors_solutions(error_type);
CREATE INDEX IF NOT EXISTS idx_errors_language ON errors_solutions(language);
CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_language ON patterns(language);
CREATE INDEX IF NOT EXISTS idx_bash_session ON bash_history(session_id);
CREATE INDEX IF NOT EXISTS idx_bash_command ON bash_history(command);

-- INDEX-URI PENTRU NOILE TABELE
CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON embeddings(content_hash);
CREATE INDEX IF NOT EXISTS idx_embeddings_chroma ON embeddings(chroma_id);
CREATE INDEX IF NOT EXISTS idx_summaries_session ON session_summaries(session_id);
CREATE INDEX IF NOT EXISTS idx_summaries_type ON session_summaries(summary_type);
CREATE INDEX IF NOT EXISTS idx_content_summaries_source ON content_summaries(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_token_costs_session ON token_costs(session_id);
CREATE INDEX IF NOT EXISTS idx_token_costs_timestamp ON token_costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_cost_summary_date ON cost_summary(date);

-- VIEW pentru căutare rapidă în mesaje recente
CREATE VIEW IF NOT EXISTS recent_messages AS
SELECT * FROM messages
ORDER BY timestamp DESC
LIMIT 1000;

-- VIEW pentru erori nerezolvate
CREATE VIEW IF NOT EXISTS unresolved_errors AS
SELECT * FROM errors_solutions
WHERE solution_worked IS NULL OR solution_worked = 0
ORDER BY created_at DESC;

-- VIEW pentru patterns populare
CREATE VIEW IF NOT EXISTS popular_patterns AS
SELECT * FROM patterns
WHERE usage_count > 0
ORDER BY usage_count DESC, quality_score DESC;
"""

# ============================================================
# V2 SCHEMA (2026-03-11) - Decisions, Goals, Tasks, Facts, Profiles
# ============================================================
SCHEMA_V2 = """
-- DECISIONS - Decizii arhitecturale, tehnice, de proiect
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'technical',
    status TEXT NOT NULL DEFAULT 'active',
    confidence TEXT DEFAULT 'high',
    rationale TEXT,
    alternatives_considered TEXT,
    superseded_by INTEGER,
    stale_after_days INTEGER DEFAULT 90,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (superseded_by) REFERENCES decisions(id)
);

-- GOALS - Obiective pe termen mediu/lung
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'active',
    target_date TEXT,
    completed_at TIMESTAMP,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TASKS - Acțiuni concrete, legate opțional de goals
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'todo',
    blocked_by TEXT,
    resolved_at TIMESTAMP,
    assigned_session TEXT,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);

-- LEARNED_FACTS - Cunoștințe dobândite
CREATE TABLE IF NOT EXISTS learned_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    fact_type TEXT NOT NULL DEFAULT 'technical',
    category TEXT,
    confidence TEXT DEFAULT 'high',
    is_pinned INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    source TEXT,
    superseded_by INTEGER,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (superseded_by) REFERENCES learned_facts(id)
);

-- PROJECT_PROFILES - Profil per proiect
CREATE TABLE IF NOT EXISTS project_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL UNIQUE,
    project_name TEXT,
    description TEXT,
    tech_stack TEXT,
    conventions TEXT,
    important_files TEXT,
    notes TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_sessions INTEGER DEFAULT 0,
    source_session TEXT,
    created_by TEXT DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- V2 INDEXES
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_category ON decisions(category);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_path);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_stale ON decisions(stale_after_days, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_project_status ON decisions(project_path, status);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_priority ON goals(priority);
CREATE INDEX IF NOT EXISTS idx_goals_project ON goals(project_path);
CREATE INDEX IF NOT EXISTS idx_goals_project_status ON goals(project_path, status);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_path);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_path, status);

CREATE INDEX IF NOT EXISTS idx_facts_type ON learned_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_facts_pinned ON learned_facts(is_pinned);
CREATE INDEX IF NOT EXISTS idx_facts_active ON learned_facts(is_active);
CREATE INDEX IF NOT EXISTS idx_facts_project ON learned_facts(project_path);
CREATE INDEX IF NOT EXISTS idx_facts_category ON learned_facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_project_active ON learned_facts(project_path, is_active);

CREATE INDEX IF NOT EXISTS idx_profiles_project ON project_profiles(project_path);
CREATE INDEX IF NOT EXISTS idx_profiles_last_active ON project_profiles(last_active_at);
"""

# ============================================================
# V2C SCHEMA (2026-03-11) - Error Intelligence + Model Attribution
# ============================================================
SCHEMA_V2C = """
-- ERROR_RESOLUTIONS - Rezolvări structurate pentru erori
CREATE TABLE IF NOT EXISTS error_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id INTEGER,
    error_fingerprint TEXT,
    error_summary TEXT,
    resolution TEXT NOT NULL,
    resolution_code TEXT,
    resolution_type TEXT DEFAULT 'fix',
    model_used TEXT,
    provider TEXT,
    agent_name TEXT,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    worked INTEGER DEFAULT 1,
    reuse_count INTEGER DEFAULT 0,
    FOREIGN KEY (error_id) REFERENCES errors_solutions(id),
    FOREIGN KEY (source_session) REFERENCES sessions(session_id)
);

-- MODEL_USAGE_LOG - Logare model/provider per acțiune
CREATE TABLE IF NOT EXISTS model_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    model_id TEXT NOT NULL,
    provider TEXT,
    agent_name TEXT,
    action_type TEXT NOT NULL,
    action_ref_table TEXT,
    action_ref_id INTEGER,
    project_path TEXT,
    success_flag INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    metadata TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- INDEXES: error_resolutions
CREATE INDEX IF NOT EXISTS idx_error_res_error_id ON error_resolutions(error_id);
CREATE INDEX IF NOT EXISTS idx_error_res_fingerprint ON error_resolutions(error_fingerprint);
CREATE INDEX IF NOT EXISTS idx_error_res_model ON error_resolutions(model_used);
CREATE INDEX IF NOT EXISTS idx_error_res_provider ON error_resolutions(provider);
CREATE INDEX IF NOT EXISTS idx_error_res_project ON error_resolutions(project_path);
CREATE INDEX IF NOT EXISTS idx_error_res_type ON error_resolutions(resolution_type);
CREATE INDEX IF NOT EXISTS idx_error_res_created ON error_resolutions(created_at);
CREATE INDEX IF NOT EXISTS idx_error_res_worked ON error_resolutions(worked);

CREATE INDEX IF NOT EXISTS idx_model_log_session ON model_usage_log(session_id);
CREATE INDEX IF NOT EXISTS idx_model_log_model ON model_usage_log(model_id);
CREATE INDEX IF NOT EXISTS idx_model_log_provider ON model_usage_log(provider);
CREATE INDEX IF NOT EXISTS idx_model_log_action ON model_usage_log(action_type);
CREATE INDEX IF NOT EXISTS idx_model_log_ref ON model_usage_log(action_ref_table, action_ref_id);
CREATE INDEX IF NOT EXISTS idx_model_log_project ON model_usage_log(project_path);
CREATE INDEX IF NOT EXISTS idx_model_log_created ON model_usage_log(created_at);
"""

# Date inițiale pentru disclosure_config
DISCLOSURE_CONFIG_INIT = """
INSERT OR IGNORE INTO disclosure_config (id, level, name, max_tokens, description) VALUES
(1, 1, 'minimal', 50, 'ID + timestamp only'),
(2, 2, 'summary', 150, 'ID + title + type'),
(3, 3, 'detailed', 500, 'Summary + context'),
(4, 4, 'full', 2000, 'Complete content'),
(5, 5, 'expanded', 5000, 'Full + related items');
"""


def ensure_fts_and_checkpoints(conn):
    """
    Adds:
      - FTS5 virtual tables + triggers for messages/tool_calls/bash_history
      - checkpoints table (continuation capsules)
    Safe to call multiple times.
    """
    cur = conn.cursor()

    # --- FTS5: MESSAGES ---
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content,
        session_id UNINDEXED,
        project_path UNINDEXED,
        content='messages',
        content_rowid='id'
    );
    """)

    # Sync triggers for messages -> messages_fts
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content, session_id, project_path)
        VALUES (new.id, new.content, new.session_id, new.project_path);
    END;
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content, session_id, project_path)
        VALUES('delete', old.id, old.content, old.session_id, old.project_path);
    END;
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content, session_id, project_path)
        VALUES('delete', old.id, old.content, old.session_id, old.project_path);
        INSERT INTO messages_fts(rowid, content, session_id, project_path)
        VALUES (new.id, new.content, new.session_id, new.project_path);
    END;
    """)

    # --- FTS5: TOOL_CALLS ---
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS tool_calls_fts USING fts5(
        tool_name,
        tool_input,
        tool_result,
        session_id UNINDEXED,
        project_path UNINDEXED,
        file_path UNINDEXED,
        content='tool_calls',
        content_rowid='id'
    );
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS tool_calls_ai AFTER INSERT ON tool_calls BEGIN
        INSERT INTO tool_calls_fts(rowid, tool_name, tool_input, tool_result, session_id, project_path, file_path)
        VALUES (new.id, new.tool_name, new.tool_input, new.tool_result, new.session_id, new.project_path, new.file_path);
    END;
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS tool_calls_ad AFTER DELETE ON tool_calls BEGIN
        INSERT INTO tool_calls_fts(tool_calls_fts, rowid, tool_name, tool_input, tool_result, session_id, project_path, file_path)
        VALUES('delete', old.id, old.tool_name, old.tool_input, old.tool_result, old.session_id, old.project_path, old.file_path);
    END;
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS tool_calls_au AFTER UPDATE ON tool_calls BEGIN
        INSERT INTO tool_calls_fts(tool_calls_fts, rowid, tool_name, tool_input, tool_result, session_id, project_path, file_path)
        VALUES('delete', old.id, old.tool_name, old.tool_input, old.tool_result, old.session_id, old.project_path, old.file_path);
        INSERT INTO tool_calls_fts(rowid, tool_name, tool_input, tool_result, session_id, project_path, file_path)
        VALUES (new.id, new.tool_name, new.tool_input, new.tool_result, new.session_id, new.project_path, new.file_path);
    END;
    """)

    # --- FTS5: BASH_HISTORY ---
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS bash_history_fts USING fts5(
        command,
        output,
        error_output,
        session_id UNINDEXED,
        project_path UNINDEXED,
        working_directory UNINDEXED,
        content='bash_history',
        content_rowid='id'
    );
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS bash_history_ai AFTER INSERT ON bash_history BEGIN
        INSERT INTO bash_history_fts(rowid, command, output, error_output, session_id, project_path, working_directory)
        VALUES (new.id, new.command, new.output, new.error_output, new.session_id, new.project_path, new.working_directory);
    END;
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS bash_history_ad AFTER DELETE ON bash_history BEGIN
        INSERT INTO bash_history_fts(bash_history_fts, rowid, command, output, error_output, session_id, project_path, working_directory)
        VALUES('delete', old.id, old.command, old.output, old.error_output, old.session_id, old.project_path, old.working_directory);
    END;
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS bash_history_au AFTER UPDATE ON bash_history BEGIN
        INSERT INTO bash_history_fts(bash_history_fts, rowid, command, output, error_output, session_id, project_path, working_directory)
        VALUES('delete', old.id, old.command, old.output, old.error_output, old.session_id, old.project_path, old.working_directory);
        INSERT INTO bash_history_fts(rowid, command, output, error_output, session_id, project_path, working_directory)
        VALUES (new.id, new.command, new.output, new.error_output, new.session_id, new.project_path, new.working_directory);
    END;
    """)

    # --- CHECKPOINTS (capsules pentru continuitate) ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checkpoint_id TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        session_id TEXT,
        project_path TEXT,

        context_percentage INTEGER,          -- estimare 0..100
        tokens_estimated INTEGER,            -- tokeni la momentul checkpoint

        capsule TEXT,                        -- JSON cu schema deterministă
        capsule_text TEXT,                   -- markdown scurt (seed prompt)
        conversation_summary TEXT,           -- rezumat mai lung opțional

        active_files TEXT,                   -- JSON array cu fișierele active
        pending_tasks TEXT,                  -- JSON array cu task-uri în așteptare

        needs_reseed INTEGER DEFAULT 0       -- 1 dacă trebuie reseed
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project_path);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON checkpoints(created_at);")

    conn.commit()
    print("✓ FTS5 tables + triggers + checkpoints created/verified")


def ensure_v2_tables(conn):
    """
    Adds V2 tables: decisions, goals, tasks, learned_facts, project_profiles.
    Safe to call multiple times (CREATE TABLE IF NOT EXISTS).
    """
    cur = conn.cursor()
    for statement in SCHEMA_V2.split(';'):
        statement = statement.strip()
        if statement:
            cur.execute(statement)
    conn.commit()
    print("✓ V2 tables created/verified (decisions, goals, tasks, learned_facts, project_profiles)")


def ensure_v2c_tables(conn):
    """
    Adds V2C tables: error_resolutions, model_usage_log.
    Also adds model_used/provider columns to decisions and learned_facts.
    Safe to call multiple times.
    """
    cur = conn.cursor()

    # Creează tabelele noi
    for statement in SCHEMA_V2C.split(';'):
        statement = statement.strip()
        if statement:
            cur.execute(statement)

    # ALTER TABLE: adaugă coloane pe tabelele V2 existente
    alter_columns = [
        ("decisions", "model_used", "TEXT"),
        ("decisions", "provider", "TEXT"),
        ("learned_facts", "model_used", "TEXT"),
        ("learned_facts", "provider", "TEXT"),
    ]
    for table, col, col_type in alter_columns:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # Coloana există deja

    conn.commit()
    print("✓ V2C tables created/verified (error_resolutions, model_usage_log) + ALTER TABLE decisions/learned_facts")


def ensure_intelligence_tables(conn):
    """
    Adds Intelligence Layer tables: error_patterns.
    Safe to call multiple times.
    """
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS error_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_signature TEXT NOT NULL,
            solution TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            first_seen TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now')),
            project_path TEXT,
            auto_promoted INTEGER DEFAULT 0
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_error_patterns_sig ON error_patterns(error_signature)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_error_patterns_count ON error_patterns(count DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_error_patterns_project ON error_patterns(project_path)")
    conn.commit()
    print("✓ Intelligence tables created/verified (error_patterns)")


def ensure_checkpoint_tables(conn):
    """
    Adds Checkpoint + Timeline tables: memory_checkpoints, checkpoint_data, timeline_events.
    Safe to call multiple times.
    """
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            model TEXT,
            intent TEXT,
            context_mode TEXT,
            decisions_count INTEGER DEFAULT 0,
            facts_count INTEGER DEFAULT 0,
            goals_count INTEGER DEFAULT 0,
            tasks_count INTEGER DEFAULT 0,
            patterns_count INTEGER DEFAULT 0,
            restored_count INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checkpoint_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            FOREIGN KEY (checkpoint_id) REFERENCES memory_checkpoints(id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            event_id INTEGER,
            title TEXT NOT NULL,
            detail TEXT,
            project_path TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Indexes
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_mchk_project ON memory_checkpoints(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_mchk_created ON memory_checkpoints(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_mchk_name ON memory_checkpoints(name)",
        "CREATE INDEX IF NOT EXISTS idx_chkdata_checkpoint ON checkpoint_data(checkpoint_id)",
        "CREATE INDEX IF NOT EXISTS idx_chkdata_type ON checkpoint_data(entity_type)",
        "CREATE INDEX IF NOT EXISTS idx_chkdata_entity ON checkpoint_data(entity_type, entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_timeline_project ON timeline_events(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_timeline_created ON timeline_events(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_timeline_type ON timeline_events(event_type)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Checkpoint tables created/verified (memory_checkpoints, checkpoint_data, timeline_events)")


def ensure_activity_log_tables(conn):
    """Creează tabelul agent_activity_log dacă nu există."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            project_path TEXT,
            agent_name TEXT,
            model_id TEXT,
            provider TEXT,
            action_type TEXT NOT NULL,
            action_summary TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            success INTEGER DEFAULT 1,
            error_message TEXT,
            duration_ms INTEGER,
            tokens_used INTEGER,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_activity_project ON agent_activity_log(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_activity_agent ON agent_activity_log(agent_name)",
        "CREATE INDEX IF NOT EXISTS idx_activity_model ON agent_activity_log(model_id)",
        "CREATE INDEX IF NOT EXISTS idx_activity_type ON agent_activity_log(action_type)",
        "CREATE INDEX IF NOT EXISTS idx_activity_created ON agent_activity_log(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_activity_session ON agent_activity_log(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_activity_entity ON agent_activity_log(entity_type, entity_id)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Activity log table created/verified (agent_activity_log)")


def ensure_universal_events_table(conn):
    """Creează tabelul universal_events pentru Universal Agent Memory API."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS universal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            title TEXT,
            project_path TEXT,
            session_id TEXT,
            cli_name TEXT,
            agent_name TEXT,
            provider TEXT,
            model_name TEXT,
            payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_uev_project ON universal_events(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_uev_type ON universal_events(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_uev_created ON universal_events(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_uev_cli ON universal_events(cli_name)",
        "CREATE INDEX IF NOT EXISTS idx_uev_agent ON universal_events(agent_name)",
        "CREATE INDEX IF NOT EXISTS idx_uev_session ON universal_events(session_id)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Universal events table created/verified (universal_events)")


def ensure_branch_tables(conn):
    """Creează tabelele pentru Memory Branches + adaugă coloana branch pe entity tables."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_path TEXT NOT NULL,
            parent_branch TEXT DEFAULT 'main',
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            created_by TEXT DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            UNIQUE(name, project_path)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS branch_merge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_branch TEXT NOT NULL,
            target_branch TEXT NOT NULL,
            project_path TEXT NOT NULL,
            strategy TEXT DEFAULT 'merge',
            conflicts_found INTEGER DEFAULT 0,
            conflicts_resolved INTEGER DEFAULT 0,
            entities_merged INTEGER DEFAULT 0,
            merged_at TEXT DEFAULT (datetime('now')),
            merged_by TEXT DEFAULT 'user',
            notes TEXT
        )
    """)
    # Add branch column to entity tables
    for table in ("decisions", "goals", "tasks", "learned_facts", "error_resolutions"):
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN branch TEXT DEFAULT 'main'")
        except Exception:
            pass  # Column already exists
    # Indexes
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_branches_project ON memory_branches(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_branches_name ON memory_branches(name, project_path)",
        "CREATE INDEX IF NOT EXISTS idx_branches_active ON memory_branches(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_merge_log_project ON branch_merge_log(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_merge_log_source ON branch_merge_log(source_branch)",
        "CREATE INDEX IF NOT EXISTS idx_merge_log_target ON branch_merge_log(target_branch)",
        "CREATE INDEX IF NOT EXISTS idx_decisions_branch ON decisions(branch)",
        "CREATE INDEX IF NOT EXISTS idx_goals_branch ON goals(branch)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_branch ON tasks(branch)",
        "CREATE INDEX IF NOT EXISTS idx_facts_branch ON learned_facts(branch)",
        "CREATE INDEX IF NOT EXISTS idx_resolutions_branch ON error_resolutions(branch)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Branch tables created/verified (memory_branches, branch_merge_log)")


def ensure_agent_events_table(conn):
    """Creează tabelul agent_events pentru Agent Event Stream."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT,
            session_id TEXT,
            branch_name TEXT,
            cli_name TEXT,
            agent_name TEXT,
            provider TEXT,
            model_name TEXT,
            event_type TEXT NOT NULL,
            event_phase TEXT DEFAULT 'end',
            title TEXT,
            summary TEXT,
            detail TEXT,
            status TEXT DEFAULT 'completed',
            related_table TEXT,
            related_id INTEGER,
            parent_event_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            started_at TEXT,
            finished_at TEXT,
            duration_ms INTEGER,
            success_flag INTEGER DEFAULT 1,
            metadata_json TEXT,
            FOREIGN KEY (parent_event_id) REFERENCES agent_events(id)
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_ae_project ON agent_events(project_path)",
        "CREATE INDEX IF NOT EXISTS idx_ae_session ON agent_events(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_ae_branch ON agent_events(branch_name)",
        "CREATE INDEX IF NOT EXISTS idx_ae_agent ON agent_events(agent_name)",
        "CREATE INDEX IF NOT EXISTS idx_ae_model ON agent_events(model_name)",
        "CREATE INDEX IF NOT EXISTS idx_ae_type ON agent_events(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_ae_created ON agent_events(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_ae_success ON agent_events(success_flag)",
        "CREATE INDEX IF NOT EXISTS idx_ae_parent ON agent_events(parent_event_id)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Agent events table created/verified (agent_events)")


def ensure_intelligence_layer_tables(conn):
    """Creates agent_reputation + experience_links tables for Memory Intelligence Layer."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_reputation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL UNIQUE,
            total_contributions INTEGER DEFAULT 0,
            successful_contributions INTEGER DEFAULT 0,
            failed_contributions INTEGER DEFAULT 0,
            promoted_count INTEGER DEFAULT 0,
            weight REAL DEFAULT 1.0,
            last_updated TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS experience_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_table TEXT NOT NULL,
            from_id INTEGER NOT NULL,
            to_table TEXT NOT NULL,
            to_id INTEGER NOT NULL,
            link_type TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            created_at TEXT DEFAULT (datetime('now')),
            created_by TEXT DEFAULT 'auto'
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_agent_rep_name ON agent_reputation(agent_name)",
        "CREATE INDEX IF NOT EXISTS idx_agent_rep_weight ON agent_reputation(weight DESC)",
        "CREATE INDEX IF NOT EXISTS idx_explinks_from ON experience_links(from_table, from_id)",
        "CREATE INDEX IF NOT EXISTS idx_explinks_to ON experience_links(to_table, to_id)",
        "CREATE INDEX IF NOT EXISTS idx_explinks_type ON experience_links(link_type)",
        "CREATE INDEX IF NOT EXISTS idx_explinks_created ON experience_links(created_at)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Intelligence layer tables created/verified (agent_reputation, experience_links)")


def ensure_cross_agent_columns(conn):
    """Adds is_global + promoted_from_agent columns to decisions, learned_facts, error_resolutions."""
    cur = conn.cursor()
    for table in ("decisions", "learned_facts", "error_resolutions"):
        for col, col_type, default in [
            ("is_global", "INTEGER", "0"),
            ("promoted_from_agent", "TEXT", None),
        ]:
            try:
                if default is not None:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}")
                else:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists
    # Indexes
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_decisions_global ON decisions(is_global)",
        "CREATE INDEX IF NOT EXISTS idx_facts_global ON learned_facts(is_global)",
        "CREATE INDEX IF NOT EXISTS idx_resolutions_global ON error_resolutions(is_global)",
    ]:
        cur.execute(idx)
    conn.commit()
    print("✓ Cross-agent learning columns created/verified (is_global, promoted_from_agent)")


def ensure_orchestration_tables(conn):
    """Creates orchestration tables for Faza 18D: MCP Orchestration V1."""
    migration_path = Path(__file__).parent.parent / "migrations" / "017_orchestration.sql"
    if migration_path.exists():
        sql = migration_path.read_text()
        # Strip comment lines before splitting on ';'
        lines = [l for l in sql.split('\n') if not l.strip().startswith('--')]
        clean_sql = '\n'.join(lines)
        cur = conn.cursor()
        for statement in clean_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cur.execute(statement)
                except sqlite3.OperationalError:
                    pass  # Table/index already exists
        conn.commit()
        print("✓ Orchestration tables created/verified (18D)")
    else:
        print(f"⚠ Migration file not found: {migration_path}")


def ensure_skill_observations_table(conn):
    """Creates orch_skill_observations table for Faza 20: Skill Learning."""
    migration_path = Path(__file__).parent.parent / "migrations" / "019_skill_observations.sql"
    if migration_path.exists():
        conn.executescript(migration_path.read_text())
        conn.commit()
        print("✓ Skill observations table created/verified (20)")


def ensure_reviews_table(conn):
    """Creates orch_reviews table for Faza 18H: Peer Review Workflow."""
    migration_path = Path(__file__).parent.parent / "migrations" / "018_reviews.sql"
    if migration_path.exists():
        conn.executescript(migration_path.read_text())
        conn.commit()
        print("✓ Reviews table created/verified (18H)")


def ensure_observability_tables(conn):
    """Migration 006: Audit log, detection rules, detection events."""
    migration_path = Path(__file__).parent.parent / "migrations" / "006_observability_tables.sql"
    if migration_path.exists():
        conn.executescript(migration_path.read_text())
        conn.commit()
        print("✓ Observability tables created/verified (006)")
    else:
        print(f"⚠ Migration file not found: {migration_path}")


def ensure_cli_agent_columns(conn):
    """Migration 020: Adaugă cli_name și agent_name la messages și sessions."""
    cur = conn.cursor()
    tables_cols = {
        "messages": [("cli_name", "TEXT"), ("agent_name", "TEXT")],
        "sessions": [("cli_name", "TEXT"), ("agent_name", "TEXT")],
    }
    for table, cols in tables_cols.items():
        for col, col_type in cols:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists
    # Indexes
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_cli ON messages(cli_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_cli ON sessions(cli_name)")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    print("✓ CLI/Agent columns added (020)")


def init_database(db_path: Path) -> bool:
    """Inițializează baza de date cu schema completă."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Executăm fiecare statement separat din SCHEMA
        for statement in SCHEMA.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except sqlite3.OperationalError as e:
                    # Ignoră erori pentru GENERATED ALWAYS (SQLite < 3.31)
                    if "GENERATED ALWAYS" in str(e):
                        # Fallback pentru versiuni vechi SQLite
                        statement = statement.replace(
                            "total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED",
                            "total_tokens INTEGER DEFAULT 0"
                        )
                        cursor.execute(statement)
                    else:
                        raise

        # Inițializează disclosure_config cu valori default
        for statement in DISCLOSURE_CONFIG_INIT.split(';'):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)

        conn.commit()

        # Adaugă FTS5 + checkpoints (safe to call multiple times)
        ensure_fts_and_checkpoints(conn)

        # V2: decisions, goals, tasks, learned_facts, project_profiles
        ensure_v2_tables(conn)

        # V2C: error_resolutions, model_usage_log + ALTER TABLE
        ensure_v2c_tables(conn)

        # Intelligence Layer: error_patterns
        ensure_intelligence_tables(conn)

        # Checkpoints + Timeline
        ensure_checkpoint_tables(conn)

        # V5E: Agent Activity Log
        ensure_activity_log_tables(conn)

        # Migration 006: Observability (audit_log, detection_rules, detection_events)
        ensure_observability_tables(conn)

        # V6: Universal Events
        ensure_universal_events_table(conn)

        # V9: Memory Branches
        ensure_branch_tables(conn)

        # V12A: Agent Event Stream
        ensure_agent_events_table(conn)

        # V15C: Cross-Agent Learning
        ensure_cross_agent_columns(conn)

        # V15D: Memory Intelligence Layer
        ensure_intelligence_layer_tables(conn)

        # Migration 020: CLI/Agent tracking columns
        ensure_cli_agent_columns(conn)

        conn.close()
        return True
    except Exception as e:
        print(f"Eroare la inițializarea bazei de date: {e}")
        return False


def main():
    """Inițializează toate bazele de date necesare."""
    # Baza de date globală — folosește resolve_db_path() unified
    try:
        from v2_common import resolve_db_path
        global_db = resolve_db_path()
    except ImportError:
        env_db = os.environ.get("MEMORY_DB_PATH")
        global_db = Path(env_db) if env_db else Path.home() / ".claude" / "memory" / "global.db"

    print(f"Inițializare {global_db}...")
    if init_database(global_db):
        print(f"✓ Baza de date globală creată: {global_db}")
    else:
        print(f"✗ Eroare la crearea bazei de date globale")
        return 1

    # Verificare
    conn = sqlite3.connect(str(global_db))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    conn.close()

    print(f"\nTabele create: {len(tables)}")
    for table in tables:
        print(f"  - {table[0]}")

    print("\n✓ Inițializare completă!")
    return 0


if __name__ == "__main__":
    exit(main())
